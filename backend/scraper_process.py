"""Process runner for google-maps-scraper with concurrent stdout/stderr reading,
progress JSON parsing, graceful termination, and timeout handling."""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)

GRACE_PERIOD_SECONDS = 10
TAIL_LIMIT = 50


class LineCategory(Enum):
    EMPTY = auto()
    UNSTRUCTURED = auto()
    PROGRESS = auto()
    LIFECYCLE = auto()
    DIAGNOSTIC = auto()
    ERROR = auto()


@dataclass
class StreamLine:
    stream: str
    text: str
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.monotonic()


@dataclass
class ParsedScraperLine:
    category: LineCategory
    raw: str
    stream: str
    message: str = ""
    level: str = ""
    job_id: str = ""
    places_found: int = 0
    is_job_finished: bool = False


@dataclass
class ScraperProgressEvent:
    places_found: int = 0
    jobs_finished: int = 0


@dataclass
class ScraperProcessResult:
    return_code: int
    progress: ScraperProgressEvent
    tail_stdout: list[str]
    tail_stderr: list[str]
    errors: list[str]
    duration_seconds: float
    terminated: bool
    killed: bool


def parse_scraper_line(stream: str, line: str) -> ParsedScraperLine:
    text = line.rstrip("\n\r")
    if not text:
        return ParsedScraperLine(category=LineCategory.EMPTY, raw=text, stream=stream)

    obj = _try_parse_json(text)
    if obj is None:
        return ParsedScraperLine(
            category=LineCategory.UNSTRUCTURED, raw=text, stream=stream,
        )

    if not isinstance(obj, dict):
        return ParsedScraperLine(
            category=LineCategory.UNSTRUCTURED, raw=text, stream=stream,
        )

    message = obj.get("message", "")
    level = obj.get("level", "")
    job_id = obj.get("jobid", "")

    if level == "error":
        return ParsedScraperLine(
            category=LineCategory.ERROR, raw=text, stream=stream,
            message=message, level=level, job_id=job_id,
        )

    if message == "job finished":
        return ParsedScraperLine(
            category=LineCategory.LIFECYCLE, raw=text, stream=stream,
            message=message, level=level, job_id=job_id,
            is_job_finished=True,
        )

    if message.endswith("places found"):
        parts = message.split(" ", 1)
        count = int(parts[0]) if parts[0].isdigit() else 0
        return ParsedScraperLine(
            category=LineCategory.PROGRESS, raw=text, stream=stream,
            message=message, level=level, job_id=job_id,
            places_found=count,
        )

    if message == "scrapemate exited":
        return ParsedScraperLine(
            category=LineCategory.LIFECYCLE, raw=text, stream=stream,
            message=message, level=level, job_id=job_id,
        )

    if level in ("info", "debug", "warn"):
        return ParsedScraperLine(
            category=LineCategory.DIAGNOSTIC, raw=text, stream=stream,
            message=message, level=level, job_id=job_id,
        )

    return ParsedScraperLine(
        category=LineCategory.UNSTRUCTURED, raw=text, stream=stream,
        message=message, level=level, job_id=job_id,
    )


def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _stream_reader(pipe, stream_name: str, q: queue.Queue, sentinel: object):
    try:
        for raw_line in iter(pipe.readline, ""):
            q.put(StreamLine(stream=stream_name, text=raw_line))
    except ValueError:
        pass
    finally:
        q.put(sentinel)
        try:
            pipe.close()
        except OSError:
            pass


class ScraperProcessRunner:
    def __init__(self):
        self._sentinel = object()
        self._queue: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []

    def run(
        self,
        executable: Path,
        args: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        progress_callback: Callable[[ParsedScraperLine], None] | None = None,
        cancel_event: threading.Event | None = None,
        timeout: float | None = None,
    ) -> ScraperProcessResult:
        start = time.monotonic()
        terminated = False
        killed = False
        progress = ScraperProgressEvent()
        tail_stdout: list[str] = []
        tail_stderr: list[str] = []
        errors: list[str] = []
        seen_messages: set[str] = set()

        cmd = [str(executable), *args]

        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        pipes_open = 0
        if process.stdout is not None:
            pipes_open += 1
            t_out = threading.Thread(
                target=_stream_reader,
                args=(process.stdout, "stdout", self._queue, self._sentinel),
                daemon=True,
            )
            t_out.start()
            self._threads.append(t_out)
        if process.stderr is not None:
            pipes_open += 1
            t_err = threading.Thread(
                target=_stream_reader,
                args=(process.stderr, "stderr", self._queue, self._sentinel),
                daemon=True,
            )
            t_err.start()
            self._threads.append(t_err)

        sentinels_left = pipes_open
        deadline = (start + timeout) if timeout else None

        try:
            while sentinels_left > 0:
                remaining = _deadline_remaining(deadline)
                if remaining is not None and remaining <= 0:
                    terminated = True
                    process.terminate()
                    _wait_with_grace(process)
                    if process.poll() is None:
                        killed = True
                        process.kill()
                        process.wait()
                    break

                if cancel_event and cancel_event.is_set():
                    terminated = True
                    process.terminate()
                    _wait_with_grace(process)
                    if process.poll() is None:
                        killed = True
                        process.kill()
                        process.wait()
                    break

                try:
                    item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if item is self._sentinel:
                    sentinels_left -= 1
                    continue

                tail = tail_stderr if item.stream == "stderr" else tail_stdout
                tail.append(item.text)
                if len(tail) > TAIL_LIMIT:
                    tail.pop(0)

                parsed = parse_scraper_line(item.stream, item.text)

                if parsed.category == LineCategory.ERROR:
                    errors.append(parsed.message or item.text.strip())

                dedup_key = f"{parsed.job_id}:{parsed.message}:{item.stream}"
                if parsed.category in (LineCategory.PROGRESS, LineCategory.LIFECYCLE):
                    if dedup_key not in seen_messages:
                        seen_messages.add(dedup_key)
                        if parsed.places_found:
                            progress.places_found += parsed.places_found
                        if parsed.is_job_finished:
                            progress.jobs_finished += 1

                if progress_callback:
                    progress_callback(parsed)

        finally:
            if process.poll() is None:
                terminated = True
                process.terminate()
                _wait_with_grace(process)
                if process.poll() is None:
                    killed = True
                    process.kill()
                    process.wait()

            _cleanup_pipes(process)
            _join_threads(self._threads, timeout=5)
            self._threads.clear()

        duration = time.monotonic() - start
        returncode = process.returncode

        return ScraperProcessResult(
            return_code=returncode,
            progress=progress,
            tail_stdout=tail_stdout,
            tail_stderr=tail_stderr,
            errors=errors,
            duration_seconds=duration,
            terminated=terminated,
            killed=killed,
        )


def _deadline_remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return deadline - time.monotonic()


def _wait_with_grace(process: subprocess.Popen, grace: float = GRACE_PERIOD_SECONDS):
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass


def _cleanup_pipes(process: subprocess.Popen):
    for pipe_name in ("stdout", "stderr"):
        pipe = getattr(process, pipe_name, None)
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass


def _join_threads(threads: list[threading.Thread], timeout: float):
    for t in threads:
        t.join(timeout=timeout)
