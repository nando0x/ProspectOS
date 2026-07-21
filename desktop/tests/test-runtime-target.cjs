const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const { mkdtempSync, writeFileSync, mkdirSync, chmodSync, rmSync } = require("node:fs");
const { join } = require("node:path");
const { tmpdir } = require("node:os");

const rt = require("../runtime-target.js");

describe("normalizePlatform", () => {
  it("maps darwin to darwin", () => {
    assert.equal(rt.normalizePlatform("darwin"), "darwin");
  });
  it("maps win32 to win32", () => {
    assert.equal(rt.normalizePlatform("win32"), "win32");
  });
  it("maps linux to linux", () => {
    assert.equal(rt.normalizePlatform("linux"), "linux");
  });
  it("returns null for unknown", () => {
    assert.equal(rt.normalizePlatform("freebsd"), null);
  });
  it("returns null for empty string", () => {
    assert.equal(rt.normalizePlatform(""), null);
  });
});

describe("normalizeArchitecture", () => {
  it("maps arm64 to arm64", () => {
    assert.equal(rt.normalizeArchitecture("arm64"), "arm64");
  });
  it("maps aarch64 to arm64", () => {
    assert.equal(rt.normalizeArchitecture("aarch64"), "arm64");
  });
  it("maps x64 to x64", () => {
    assert.equal(rt.normalizeArchitecture("x64"), "x64");
  });
  it("maps amd64 to x64", () => {
    assert.equal(rt.normalizeArchitecture("AMD64"), "x64");
  });
  it("maps x86_64 to x64", () => {
    assert.equal(rt.normalizeArchitecture("x86_64"), "x64");
  });
  it("returns null for unknown", () => {
    assert.equal(rt.normalizeArchitecture("ia32"), null);
  });
  it("is case insensitive", () => {
    assert.equal(rt.normalizeArchitecture("ARM64"), "arm64");
    assert.equal(rt.normalizeArchitecture("AMD64"), "x64");
  });
});

describe("getCurrentTarget", () => {
  it("returns something like darwin-arm64 on this machine", () => {
    const target = rt.getCurrentTarget();
    assert.ok(target.includes("-"));
    const [plat, arch] = target.split("-");
    assert.ok(["darwin", "win32", "linux"].includes(plat));
    assert.ok(["arm64", "x64"].includes(arch));
  });
});

describe("safeJoin", () => {
  const root = "/tmp/test-root";

  it("joins a normal relative path", () => {
    assert.equal(rt.safeJoin(root, "backend/ProspectOS"), "/tmp/test-root/backend/ProspectOS");
  });
  it("joins with subdirectories", () => {
    assert.equal(rt.safeJoin(root, "scraper/google-maps-scraper"), "/tmp/test-root/scraper/google-maps-scraper");
  });
  it("rejects absolute path", () => {
    assert.throws(() => rt.safeJoin(root, "/etc/passwd"), /n[aã]o/);
  });
  it("rejects traversal with ../", () => {
    assert.throws(() => rt.safeJoin(root, "../outside"), /traversal/);
  });
  it("rejects deep traversal", () => {
    assert.throws(() => rt.safeJoin(root, "../../etc/passwd"), /traversal/);
  });
  it("rejects Windows absolute path", () => {
    assert.throws(() => rt.safeJoin(root, "C:\\absolute.exe"), /n[aã]o/);
  });
  it("handles path with spaces", () => {
    assert.equal(rt.safeJoin(root, "my app/backend"), "/tmp/test-root/my app/backend");
  });
  it("rejects traversal even after normalization", () => {
    assert.throws(() => rt.safeJoin(root, "foo/../../etc/passwd"), /traversal/);
  });
});

describe("loadRuntimeManifest", () => {
  let tmpDir;
  let manifestPath;

  before(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "rt-test-"));
    manifestPath = join(tmpDir, "runtime-targets.json");
  });

  after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("loads a valid manifest", () => {
    writeFileSync(manifestPath, JSON.stringify({
      schemaVersion: 1,
      targets: {
        "darwin-arm64": {
          backend: { name: "ProspectOS" },
          scraper: { name: "google-maps-scraper" },
        },
        "win32-x64": {
          backend: { name: "ProspectOS.exe" },
          scraper: { name: "google-maps-scraper.exe" },
        },
      },
    }));
    const manifest = rt.loadRuntimeManifest(manifestPath);
    assert.equal(manifest.schemaVersion, 1);
    assert.ok(manifest.targets["darwin-arm64"]);
    assert.equal(manifest.targets["darwin-arm64"].backend.name, "ProspectOS");
  });

  it("throws on file not found", () => {
    assert.throws(() => rt.loadRuntimeManifest("/nao/existe.json"), /n[aã]o encontrado/);
  });

  it("throws on invalid JSON", () => {
    writeFileSync(manifestPath, "not json");
    assert.throws(() => rt.loadRuntimeManifest(manifestPath), /JSON mal formatado/);
  });

  it("throws on wrong schemaVersion", () => {
    writeFileSync(manifestPath, JSON.stringify({ schemaVersion: 999, targets: {} }));
    assert.throws(() => rt.loadRuntimeManifest(manifestPath), /schemaVersion/);
  });

  it("throws on missing targets", () => {
    writeFileSync(manifestPath, JSON.stringify({ schemaVersion: 1 }));
    assert.throws(() => rt.loadRuntimeManifest(manifestPath), /targets.*ausente/);
  });

  it("throws on empty name", () => {
    writeFileSync(manifestPath, JSON.stringify({
      schemaVersion: 1,
      targets: { "darwin-arm64": { backend: { name: "" }, scraper: { name: "x" } } },
    }));
    assert.throws(() => rt.loadRuntimeManifest(manifestPath), /name.*inv[aá]lido/);
  });

  it("throws on traversal in name", () => {
    writeFileSync(manifestPath, JSON.stringify({
      schemaVersion: 1,
      targets: { "darwin-arm64": { backend: { name: "../../bin" }, scraper: { name: "x" } } },
    }));
    assert.throws(() => rt.loadRuntimeManifest(manifestPath), /traversal/);
  });

  it("throws on absolute path in name", () => {
    writeFileSync(manifestPath, JSON.stringify({
      schemaVersion: 1,
      targets: { "darwin-arm64": { backend: { name: "/absolute/path" }, scraper: { name: "x" } } },
    }));
    assert.throws(() => rt.loadRuntimeManifest(manifestPath), /path absoluto|traversal/);
  });
});

describe("getTargetConfig", () => {
  const manifest = {
    schemaVersion: 1,
    targets: {
      "darwin-arm64": { backend: { name: "P" }, scraper: { name: "S" } },
    },
  };

  it("returns config for existing target", () => {
    const cfg = rt.getTargetConfig(manifest, "darwin-arm64");
    assert.equal(cfg.backend.name, "P");
  });

  it("throws for missing target", () => {
    assert.throws(() => rt.getTargetConfig(manifest, "linux-arm64"), /n[aã]o suportado/);
  });
});

describe("resolvePackagedBackend", () => {
  it("resolves backend name under resourcesPath", () => {
    const result = rt.resolvePackagedBackend(
      { backend: { name: "ProspectOS.exe" }, scraper: { name: "x" } },
      "/opt/app/resources",
    );
    assert.equal(result.path, "/opt/app/resources/ProspectOS.exe");
  });

  it("works for macOS name without extension", () => {
    const result = rt.resolvePackagedBackend(
      { backend: { name: "ProspectOS" }, scraper: { name: "x" } },
      "/opt/app/resources",
    );
    assert.equal(result.path, "/opt/app/resources/ProspectOS");
  });
});

describe("resolveDevelopmentBackend", () => {
  it("resolves with .exe", () => {
    const result = rt.resolveDevelopmentBackend(
      { backend: { name: "ProspectOS.exe" }, scraper: { name: "x" } },
      "/project",
    );
    assert.equal(result.path, "/project/backend/dist/ProspectOS/ProspectOS.exe");
  });

  it("works for macOS without extension", () => {
    const result = rt.resolveDevelopmentBackend(
      { backend: { name: "ProspectOS" }, scraper: { name: "x" } },
      "/project",
    );
    assert.equal(result.path, "/project/backend/dist/ProspectOS/ProspectOS");
  });
});

describe("resolveDevelopmentScraper", () => {
  it("resolves under devRoot", () => {
    const result = rt.resolveDevelopmentScraper(
      { backend: { name: "P" }, scraper: { name: "google-maps-scraper" } },
      "/project/backend",
    );
    assert.equal(result.path, "/project/backend/google-maps-scraper");
  });

  it("works with .exe for Windows", () => {
    const result = rt.resolveDevelopmentScraper(
      { backend: { name: "P" }, scraper: { name: "google-maps-scraper.exe" } },
      "/project/backend",
    );
    assert.equal(result.path, "/project/backend/google-maps-scraper.exe");
  });
});

describe("validateExecutable", () => {
  let tmpDir;
  let exePath;
  let dirPath;

  before(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "rt-validate-"));
    exePath = join(tmpDir, "executable");
    dirPath = join(tmpDir, "mydir");
    mkdirSync(dirPath);
    writeFileSync(exePath, "fake binary content");
    if (process.platform !== "win32") {
      chmodSync(exePath, 0o755);
    }
  });

  after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("passes for existing executable", () => {
    rt.validateExecutable(exePath, "Backend");
  });

  it("throws for non-existent file", () => {
    assert.throws(() => rt.validateExecutable(join(tmpDir, "nope"), "X"), /n[aã]o encontrado/);
  });

  it("throws for directory", () => {
    assert.throws(() => rt.validateExecutable(dirPath, "Dir"), /diret[oó]rio/);
  });

  it("throws for non-executable on non-Windows", () => {
    if (process.platform === "win32") return;
    const noexec = join(tmpDir, "noexec");
    writeFileSync(noexec, "content");
    assert.throws(() => rt.validateExecutable(noexec, "NE"), /permiss[aã]o de execu[cç][aã]o/);
  });
});

describe("resolveRuntimeTarget integration", () => {
  let tmpDir;
  let manifestPath;
  let resourcesPath;

  before(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "rt-integration-"));
    manifestPath = join(tmpDir, "runtime-targets.json");
    resourcesPath = join(tmpDir, "resources");
    mkdirSync(resourcesPath);

    writeFileSync(join(resourcesPath, "ProspectOS"), "fake backend", { mode: 0o755 });

    writeFileSync(manifestPath, JSON.stringify({
      schemaVersion: 1,
      targets: {
        "darwin-arm64": {
          backend: { name: "ProspectOS" },
          scraper: { name: "google-maps-scraper" },
        },
        "win32-x64": {
          backend: { name: "ProspectOS.exe" },
          scraper: { name: "google-maps-scraper.exe" },
        },
      },
    }));
  });

  after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("resolves darwin-arm64 packaged backend", () => {
    const origPlatform = process.platform;
    const origArch = process.arch;
    Object.defineProperty(process, "platform", { value: "darwin", configurable: true });
    Object.defineProperty(process, "arch", { value: "arm64", configurable: true });

    try {
      const result = rt.resolveRuntimeTarget({
        packaged: true, manifestPath, resourcesPath, devRoot: tmpDir,
      });
      assert.equal(result.target, "darwin-arm64");
      assert.ok(result.backendPath.endsWith("ProspectOS"));
    } finally {
      Object.defineProperty(process, "platform", { value: origPlatform, configurable: true });
      Object.defineProperty(process, "arch", { value: origArch, configurable: true });
    }
  });

  it("resolves darwin-arm64 dev backend", () => {
    const origPlatform = process.platform;
    const origArch = process.arch;
    Object.defineProperty(process, "platform", { value: "darwin", configurable: true });
    Object.defineProperty(process, "arch", { value: "arm64", configurable: true });

    try {
      const result = rt.resolveRuntimeTarget({
        packaged: false, manifestPath, resourcesPath, devRoot: tmpDir,
      });
      assert.equal(result.target, "darwin-arm64");
      assert.ok(result.backendPath.includes("backend/dist/ProspectOS/ProspectOS"));
    } finally {
      Object.defineProperty(process, "platform", { value: origPlatform, configurable: true });
      Object.defineProperty(process, "arch", { value: origArch, configurable: true });
    }
  });

  it("resolves win32-x64 with .exe extension", () => {
    const origPlatform = process.platform;
    const origArch = process.arch;
    Object.defineProperty(process, "platform", { value: "win32", configurable: true });
    Object.defineProperty(process, "arch", { value: "x64", configurable: true });

    try {
      const result = rt.resolveRuntimeTarget({
        packaged: true, manifestPath, resourcesPath, devRoot: tmpDir,
      });
      assert.equal(result.target, "win32-x64");
      assert.ok(result.backendPath.endsWith("ProspectOS.exe"));
      assert.ok(result.scraperPath.endsWith("google-maps-scraper.exe"));
    } finally {
      Object.defineProperty(process, "platform", { value: origPlatform, configurable: true });
      Object.defineProperty(process, "arch", { value: origArch, configurable: true });
    }
  });

  it("throws for unsupported target", () => {
    const origPlatform = process.platform;
    const origArch = process.arch;
    Object.defineProperty(process, "platform", { value: "linux", configurable: true });
    Object.defineProperty(process, "arch", { value: "arm64", configurable: true });

    try {
      assert.throws(() => {
        rt.resolveRuntimeTarget({ packaged: true, manifestPath, resourcesPath, devRoot: tmpDir });
      }, /n[aã]o suportado/);
    } finally {
      Object.defineProperty(process, "platform", { value: origPlatform, configurable: true });
      Object.defineProperty(process, "arch", { value: origArch, configurable: true });
    }
  });

  it("throws for missing target in manifest", () => {
    const origPlatform = process.platform;
    const origArch = process.arch;
    Object.defineProperty(process, "platform", { value: "darwin", configurable: true });
    Object.defineProperty(process, "arch", { value: "arm64", configurable: true });

    try {
      const minimal = join(tmpDir, "minimal.json");
      writeFileSync(minimal, JSON.stringify({
        schemaVersion: 1,
        targets: { "win32-x64": { backend: { name: "x.exe" }, scraper: { name: "y.exe" } } },
      }));
      assert.throws(() => {
        rt.resolveRuntimeTarget({ packaged: true, manifestPath: minimal, resourcesPath, devRoot: tmpDir });
      }, /suportado/);
    } finally {
      Object.defineProperty(process, "platform", { value: origPlatform, configurable: true });
      Object.defineProperty(process, "arch", { value: origArch, configurable: true });
    }
  });
});
