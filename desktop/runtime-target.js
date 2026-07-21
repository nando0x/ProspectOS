const path = require("path");
const fs = require("fs");

const SCHEMA_VERSION = 1;

const SUPPORTED_TARGETS = Object.freeze([
  "darwin-arm64",
  "darwin-x64",
  "win32-x64",
  "linux-x64",
]);

const PLATFORM_MAP = Object.freeze({ darwin: "darwin", win32: "win32", linux: "linux" });

const ARCH_MAP = Object.freeze({
  arm64: "arm64",
  aarch64: "arm64",
  x64: "x64",
  amd64: "x64",
  x86_64: "x64",
});

function normalizePlatform(platform) {
  return PLATFORM_MAP[platform] || null;
}

function normalizeArchitecture(arch) {
  return ARCH_MAP[String(arch).toLowerCase()] || null;
}

function getCurrentTarget() {
  const platform = normalizePlatform(process.platform);
  const arch = normalizeArchitecture(process.arch);
  if (!platform || !arch) {
    throw new Error(`Runtime target não suportado: ${process.platform}-${process.arch}`);
  }
  return `${platform}-${arch}`;
}

function safeJoin(root, relativePath) {
  if (path.isAbsolute(relativePath)) {
    throw new Error(`Path absoluto não é permitido: ${relativePath}`);
  }

  if (/^[a-zA-Z]:\\/.test(relativePath)) {
    throw new Error(`Path absoluto não é permitido: ${relativePath}`);
  }

  const normalized = path.normalize(relativePath);
  if (normalized.startsWith("..")) {
    throw new Error(`Path traversal detectado: ${relativePath}`);
  }

  const resolved = path.resolve(root, normalized);
  if (!resolved.startsWith(path.resolve(root))) {
    throw new Error(`Path traversal detectado: ${relativePath}`);
  }

  return resolved;
}

function loadRuntimeManifest(manifestPath) {
  const resolved = path.resolve(manifestPath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`Runtime manifest não encontrado: ${resolved}`);
  }

  let data;
  try {
    data = JSON.parse(fs.readFileSync(resolved, "utf-8"));
  } catch (err) {
    throw new Error(`Runtime manifest inválido (JSON mal formatado): ${err.message}`);
  }

  if (!data || typeof data !== "object") {
    throw new Error("Runtime manifest inválido: esperado um objeto JSON");
  }

  if (data.schemaVersion !== SCHEMA_VERSION) {
    throw new Error(
      `Runtime manifest schemaVersion não suportada: ${data.schemaVersion}. Esperada: ${SCHEMA_VERSION}`
    );
  }

  if (!data.targets || typeof data.targets !== "object") {
    throw new Error("Runtime manifest inválido: campo 'targets' ausente ou inválido");
  }

  for (const [targetKey, targetVal] of Object.entries(data.targets)) {
    if (!targetVal || typeof targetVal !== "object") {
      throw new Error(`Runtime manifest inválido: target "${targetKey}" não é um objeto`);
    }
    for (const resource of ["backend", "scraper"]) {
      const entry = targetVal[resource];
      if (!entry || typeof entry !== "object") {
        throw new Error(
          `Runtime manifest inválido: target "${targetKey}" não possui "${resource}"`
        );
      }
      if (!entry.name || typeof entry.name !== "string" || entry.name.trim() === "") {
        throw new Error(
          `Runtime manifest inválido: target "${targetKey}" "${resource}.name" inválido`
        );
      }
      if (entry.name.includes("..") || path.isAbsolute(entry.name)) {
        throw new Error(
          `Runtime manifest inválido: target "${targetKey}" "${resource}.name" contém path traversal ou path absoluto: ${entry.name}`
        );
      }
    }
  }

  return data;
}

function getTargetConfig(manifest, target) {
  if (!manifest.targets[target]) {
    throw new Error(`Runtime target não suportado: ${target}`);
  }
  return manifest.targets[target];
}

function resolvePackagedBackend(targetConfig, resourcesPath) {
  const name = targetConfig.backend.name;
  const resolved = safeJoin(resourcesPath, name);
  return { path: resolved, name };
}

function resolveDevelopmentBackend(targetConfig, devRoot) {
  const name = path.basename(targetConfig.backend.name);
  const relative = path.join("backend", "dist", "ProspectOS", name);
  const resolved = safeJoin(devRoot, relative);
  return { path: resolved, name };
}

function resolvePackagedScraper(targetConfig, resourcesPath) {
  const name = targetConfig.scraper.name;
  const resolved = safeJoin(resourcesPath, name);
  return { path: resolved, name };
}

function resolveDevelopmentScraper(targetConfig, devRoot) {
  const name = path.basename(targetConfig.scraper.name);
  const resolved = safeJoin(devRoot, name);
  return { path: resolved, name };
}

function validateExecutable(filePath, label) {
  if (!fs.existsSync(filePath)) {
    const err = new Error(`${label} não encontrado: ${filePath}`);
    err.code = "ENOENT";
    err.label = label;
    err.filePath = filePath;
    throw err;
  }

  const stat = fs.statSync(filePath);
  if (stat.isDirectory()) {
    const err = new Error(`${label} é um diretório, não um executável: ${filePath}`);
    err.code = "EISDIR";
    err.label = label;
    err.filePath = filePath;
    throw err;
  }

  if (process.platform !== "win32") {
    const mode = stat.mode & fs.constants.S_IXUSR;
    if (!mode) {
      const err = new Error(
        `${label} não possui permissão de execução: ${filePath}`
      );
      err.code = "EACCES";
      err.label = label;
      err.filePath = filePath;
      throw err;
    }
  }
}

function resolveRuntimeTarget({ packaged, manifestPath, resourcesPath, devRoot }) {
  const manifest = loadRuntimeManifest(manifestPath);
  const currentTarget = getCurrentTarget();
  const targetConfig = getTargetConfig(manifest, currentTarget);

  const backend = packaged
    ? resolvePackagedBackend(targetConfig, resourcesPath)
    : resolveDevelopmentBackend(targetConfig, devRoot);

  const scraper = packaged
    ? resolvePackagedScraper(targetConfig, resourcesPath)
    : resolveDevelopmentScraper(targetConfig, devRoot);

  return {
    target: currentTarget,
    backendPath: backend.path,
    backendName: backend.name,
    scraperPath: scraper.path,
    scraperName: scraper.name,
    manifest,
    targetConfig,
  };
}

module.exports = {
  SCHEMA_VERSION,
  SUPPORTED_TARGETS,
  PLATFORM_MAP,
  ARCH_MAP,
  normalizePlatform,
  normalizeArchitecture,
  getCurrentTarget,
  safeJoin,
  loadRuntimeManifest,
  getTargetConfig,
  resolvePackagedBackend,
  resolveDevelopmentBackend,
  resolvePackagedScraper,
  resolveDevelopmentScraper,
  validateExecutable,
  resolveRuntimeTarget,
};
