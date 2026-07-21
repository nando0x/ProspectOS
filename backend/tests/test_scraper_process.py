"""Tests for scraper_process.py — line parser, process runner, concurrency, shutdown."""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper_process import (
    parse_scraper_line,
    LineCategory,
    ScraperProcessRunner,
    ScraperProcessResult,
    GRACE_PERIOD_SECONDS,
)


# ── Parser tests ──────────────────────────────────────────────────────────

class TestParseScraperLine:
    def test_empty_line(self):
        result = parse_scraper_line("stdout", "")
        assert result.category == LineCategory.EMPTY

    def test_newline_only(self):
        result = parse_scraper_line("stderr", "\n")
        assert result.category == LineCategory.EMPTY

    def test_crlf(self):
        result = parse_scraper_line("stdout", "hello\r\n")
        assert result.category == LineCategory.UNSTRUCTURED
        assert result.raw == "hello"

    def test_unstructured_text(self):
        result = parse_scraper_line("stdout", "INFO: starting browser")
        assert result.category == LineCategory.UNSTRUCTURED
        assert result.raw == "INFO: starting browser"

    def test_valid_json_progress_stdout(self):
        line = json.dumps({"level": "info", "message": "12 places found", "jobid": "abc"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.PROGRESS
        assert result.places_found == 12
        assert result.message == "12 places found"
        assert result.level == "info"

    def test_valid_json_progress_stderr(self):
        line = json.dumps({"level": "info", "message": "5 places found", "jobid": "def"})
        result = parse_scraper_line("stderr", line)
        assert result.category == LineCategory.PROGRESS
        assert result.places_found == 5
        assert result.stream == "stderr"

    def test_job_finished(self):
        line = json.dumps({"level": "info", "message": "job finished", "jobid": "abc"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.LIFECYCLE
        assert result.is_job_finished is True

    def test_scrapemate_exited(self):
        line = json.dumps({"level": "info", "message": "scrapemate exited"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.LIFECYCLE
        assert result.message == "scrapemate exited"

    def test_error_level(self):
        line = json.dumps({"level": "error", "message": "connection refused", "jobid": "x"})
        result = parse_scraper_line("stderr", line)
        assert result.category == LineCategory.ERROR
        assert result.level == "error"
        assert result.message == "connection refused"

    def test_warning_level(self):
        line = json.dumps({"level": "warn", "message": "rate limit approaching"})
        result = parse_scraper_line("stderr", line)
        assert result.category == LineCategory.DIAGNOSTIC
        assert result.level == "warn"

    def test_debug_level(self):
        line = json.dumps({"level": "debug", "message": "navigating to page"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.DIAGNOSTIC
        assert result.level == "debug"

    def test_json_without_message(self):
        line = json.dumps({"level": "info", "extra": "data"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.DIAGNOSTIC

    def test_json_array(self):
        result = parse_scraper_line("stdout", '["a", "b"]')
        assert result.category == LineCategory.UNSTRUCTURED

    def test_json_primitive(self):
        result = parse_scraper_line("stdout", '"just a string"')
        assert result.category == LineCategory.UNSTRUCTURED

    def test_invalid_json(self):
        result = parse_scraper_line("stdout", "{bad json}")
        assert result.category == LineCategory.UNSTRUCTURED

    def test_invalid_json_similar(self):
        result = parse_scraper_line("stderr", "not json at all")
        assert result.category == LineCategory.UNSTRUCTURED

    def test_unicode(self):
        line = json.dumps({"level": "info", "message": "café e padaria"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.DIAGNOSTIC
        assert "café" in result.message

    def test_long_message(self):
        msg = "x" * 10000
        line = json.dumps({"level": "info", "message": msg})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.DIAGNOSTIC
        assert len(result.message) == 10000

    def test_stream_label_preserved(self):
        result = parse_scraper_line("stderr", "hello")
        assert result.stream == "stderr"
        result2 = parse_scraper_line("stdout", "hello")
        assert result2.stream == "stdout"

    def test_places_found_zero_if_not_digit(self):
        line = json.dumps({"level": "info", "message": "abc places found"})
        result = parse_scraper_line("stdout", line)
        assert result.category == LineCategory.PROGRESS
        assert result.places_found == 0

    def test_places_found_multiple_digits(self):
        line = json.dumps({"level": "info", "message": "150 places found"})
        result = parse_scraper_line("stdout", line)
        assert result.places_found == 150


# ── Runner tests (fake processes) ─────────────────────────────────────────

class TestScraperProcessRunner:

    def make_runner(self):
        return ScraperProcessRunner()

    def test_success_progress_in_stderr(self, tmp_path):
        script = (
            "import sys, json\n"
            "msg = json.dumps({'level': 'info', 'message': '3 places found'})\n"
            "print(msg, file=sys.stderr)\n"
            "msg2 = json.dumps({'level': 'info', 'message': 'job finished'})\n"
            "print(msg2, file=sys.stderr)\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0
        assert result.progress.places_found == 3
        assert result.progress.jobs_finished == 1
        assert not result.terminated
        assert not result.killed

    def test_success_progress_in_stdout(self, tmp_path):
        script = (
            "import sys, json\n"
            "msg = json.dumps({'level': 'info', 'message': '7 places found'})\n"
            "print(msg)\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0
        assert result.progress.places_found == 7

    def test_both_streams_no_deadlock(self, tmp_path):
        script = (
            "import sys, json\n"
            "for i in range(100):\n"
            "    p = {'level': 'info', 'message': f'{i} places found'}\n"
            "    print(json.dumps(p), file=sys.stderr)\n"
            "    print(json.dumps(p))\n"
            "    sys.stderr.flush()\n"
            "    sys.stdout.flush()\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0
        assert result.progress.places_found > 0

    def test_large_stderr(self, tmp_path):
        script = (
            "import sys\n"
            "for i in range(5000):\n"
            "    print('x' * 1000, file=sys.stderr)\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0
        assert len(result.tail_stderr) <= 50

    def test_exit_code_2(self, tmp_path):
        script = "import sys; sys.exit(2)"
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 2

    def test_exit_code_1(self, tmp_path):
        script = "import sys; sys.exit(1)"
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 1

    def test_error_message_preserved(self, tmp_path):
        script = (
            "import sys, json\n"
            "err = json.dumps({'level': 'error', 'message': 'connection failed'})\n"
            "print(err, file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert len(result.errors) >= 1
        assert "connection failed" in result.errors[0]

    def test_timeout_terminates_then_kills(self, tmp_path):
        script = (
            "import time\n"
            "while True:\n"
            "    print('alive', flush=True)\n"
            "    time.sleep(0.05)\n"
        )
        runner = self.make_runner()
        start = time.monotonic()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
            timeout=0.5,
        )
        duration = time.monotonic() - start
        assert result.terminated
        assert duration < 15
        assert result.return_code != 0 or result.killed

    def test_cancel_event(self, tmp_path):
        script = (
            "import time\n"
            "while True:\n"
            "    print('alive', flush=True)\n"
            "    time.sleep(0.05)\n"
        )
        cancel = threading.Event()
        runner = self.make_runner()

        def delayed_cancel():
            time.sleep(0.3)
            cancel.set()

        t = threading.Thread(target=delayed_cancel, daemon=True)
        t.start()
        start = time.monotonic()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
            cancel_event=cancel,
        )
        duration = time.monotonic() - start
        assert result.terminated
        assert duration < 15

    def test_progress_callback_called(self, tmp_path):
        script = (
            "import sys, json\n"
            "p = json.dumps({'level': 'info', 'message': '5 places found'})\n"
            "print(p, file=sys.stderr)\n"
        )
        received = []
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
            progress_callback=lambda p: received.append(p),
        )
        assert len(received) >= 1
        assert received[0].places_found == 5

    def test_simultaneous_stdout_stderr(self, tmp_path):
        script = (
            "import sys, json, threading\n"
            "def writer(stream):\n"
            "    for i in range(50):\n"
            "        p = json.dumps({'level': 'info', 'message': f'{i} from {stream.name}'})\n"
            "        print(p, file=stream)\n"
            "        stream.flush()\n"
            "t1 = threading.Thread(target=writer, args=(sys.stdout,), daemon=True)\n"
            "t2 = threading.Thread(target=writer, args=(sys.stderr,), daemon=True)\n"
            "t1.start(); t2.start()\n"
            "t1.join(); t2.join()\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0
        assert not result.killed

    def test_stdout_closes_first(self, tmp_path):
        script = (
            "import sys\n"
            "sys.stdout.close()\n"
            "print('only stderr', file=sys.stderr)\n"
        )
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0

    def test_no_newline_at_end(self, tmp_path):
        script = "import sys; sys.stdout.write('no newline')"
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.return_code == 0

    def test_duration_recorded(self, tmp_path):
        script = "import time; time.sleep(0.1)"
        runner = self.make_runner()
        result = runner.run(
            executable=Path(sys.executable),
            args=["-c", script],
            cwd=tmp_path,
            env={"PYTHONIOENCODING": "utf-8"},
        )
        assert result.duration_seconds >= 0.1
