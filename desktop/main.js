const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

const {
  resolveRuntimeTarget,
  validateExecutable,
} = require("./runtime-target.js");

let janela = null;
let backend = null;
let backendEncerradoDeProposito = false;
let limpando = null;
let PROSPECTOS_DATA_DIR = null;
let PROSPECTOS_LOG_DIR = null;
let PROSPECTOS_RESOURCE_DIR = null;

const BACKEND_STARTUP_TIMEOUT_MS = 30_000;
const BACKEND_SHUTDOWN_GRACE_MS = 10_000;
const PROSPECTOS_TEMP_DIR = null;

const primeiraInstancia = app.requestSingleInstanceLock();
if (!primeiraInstancia) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (janela) {
      if (janela.isMinimized()) janela.restore();
      janela.focus();
    }
  });
}

function manifestPath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "shared", "runtime-targets.json")
    : path.join(__dirname, "..", "shared", "runtime-targets.json");
}

function resolverBackend() {
  const runtime = resolveRuntimeTarget({
    packaged: app.isPackaged,
    manifestPath: manifestPath(),
    resourcesPath: process.resourcesPath || path.join(__dirname, ".."),
    devRoot: path.join(__dirname, ".."),
  });
  return runtime.backendPath;
}

function arquivoDaPorta() {
  return path.join(PROSPECTOS_DATA_DIR, "porta.txt");
}

function resolverPaths() {
  PROSPECTOS_DATA_DIR = app.getPath("userData");
  PROSPECTOS_LOG_DIR = app.getPath("logs");

  const nomeBase = path.basename(PROSPECTOS_DATA_DIR);
  if (nomeBase !== "ProspectOS") {
    PROSPECTOS_DATA_DIR = path.join(path.dirname(PROSPECTOS_DATA_DIR), "ProspectOS");
    PROSPECTOS_LOG_DIR = path.join(
      process.platform === "darwin"
        ? path.join(app.getPath("home"), "Library", "Logs", "ProspectOS")
        : path.dirname(PROSPECTOS_DATA_DIR),
      "ProspectOS",
      "logs"
    );
  }

  const PROSPECTOS_TEMP_DIR = path.join(app.getPath("temp"), "ProspectOS");
  PROSPECTOS_RESOURCE_DIR = process.resourcesPath || path.join(__dirname, "..");

  try {
    fs.mkdirSync(PROSPECTOS_DATA_DIR, { recursive: true });
    fs.mkdirSync(PROSPECTOS_LOG_DIR, { recursive: true });
    fs.mkdirSync(PROSPECTOS_TEMP_DIR, { recursive: true });
  } catch (erro) {
    throw new Error(
      `Não foi possível criar os diretórios do ProspectOS:\n${erro.message}`
    );
  }

  return { PROSPECTOS_DATA_DIR, PROSPECTOS_LOG_DIR, PROSPECTOS_TEMP_DIR, PROSPECTOS_RESOURCE_DIR };
}

function ambienteBackend(pathsResolvidos) {
  const runtimeTarget = require("./runtime-target.js").getCurrentTarget();

  return {
    ...process.env,
    PROSPECTOS_NO_BROWSER: "1",
    PROSPECTOS_DATA_DIR: pathsResolvidos.PROSPECTOS_DATA_DIR,
    PROSPECTOS_LOG_DIR: pathsResolvidos.PROSPECTOS_LOG_DIR,
    PROSPECTOS_TEMP_DIR: pathsResolvidos.PROSPECTOS_TEMP_DIR,
    PROSPECTOS_CACHE_DIR: path.join(app.getPath("cache"), "ProspectOS"),
    PROSPECTOS_RESOURCE_DIR: pathsResolvidos.PROSPECTOS_RESOURCE_DIR,
    PROSPECTOS_RUNTIME_MANIFEST: manifestPath(),
    PROSPECTOS_PLAYWRIGHT_RUNTIME_MANIFEST: path.join(
      path.dirname(manifestPath()),
      "playwright-runtime-targets.json"
    ),
    PROSPECTOS_RUNTIME_TARGET: runtimeTarget,
  };
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let data = "";
      res.on("data", (chunk) => { data += chunk; });
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    });
    req.on("error", reject);
    req.setTimeout(5000, () => { req.destroy(); reject(new Error("timeout")); });
    req.end();
  });
}

function subirBackend(pathsResolvidos) {
  return new Promise((resolver, rejeitar) => {
    const exe = resolverBackend();

    try {
      validateExecutable(exe, "Backend do ProspectOS");
    } catch (err) {
      rejeitar(new Error(
        `Backend não encontrado:\n${exe}\n\nVerifique se o backend foi compilado.\n`
      ));
      return;
    }

    console.log(`backend: ${exe}`);

    try { fs.unlinkSync(arquivoDaPorta()); } catch { }

    backend = spawn(exe, [], {
      cwd: path.dirname(exe),
      env: ambienteBackend(pathsResolvidos),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: process.platform === "win32",
    });

    let resolvido = false;
    const backwardLog = [];

    function capturar(dados) {
      const linhas = String(dados).split("\n").filter(Boolean);
      for (const linha of linhas) {
        backwardLog.push(linha);
        if (backwardLog.length > 200) backwardLog.shift();
        const casado = linha.match(/LISTENING_ON=(\d+)/);
        if (casado) onPorta(Number(casado[1]));
      }
    }

    function onPorta(porta) {
      if (resolvido) return;
      resolvido = true;
      resolver(porta);
    }

    backend.stdout.on("data", capturar);
    backend.stderr.on("data", capturar);

    backend.on("exit", (codigo, sinal) => {
      if (backendEncerradoDeProposito) return;
      if (!resolvido) {
        const tail = backwardLog.slice(-50).join("\n");
        rejeitar(new Error(
          `O backend encerrou antes de subir (código ${codigo}, sinal ${sinal}).\n\n` +
          `Últimos logs:\n${tail}`
        ));
      } else {
        dialog.showErrorBox(
          "ProspectOS",
          "O motor do ProspectOS parou de responder. O aplicativo será fechado."
        );
        app.quit();
      }
    });

    const inicio = Date.now();
    const intervalo = setInterval(() => {
      if (resolvido) { clearInterval(intervalo); return; }
      try {
        const porta = Number(fs.readFileSync(arquivoDaPorta(), "utf-8").trim());
        if (porta > 0 && porta <= 65535) {
          clearInterval(intervalo);
          onPorta(porta);
        }
      } catch { }
      if (Date.now() - inicio > BACKEND_STARTUP_TIMEOUT_MS) {
        clearInterval(intervalo);
        if (!resolvido) {
          const tail = backwardLog.slice(-50).join("\n");
          rejeitar(new Error(
            `O backend não subiu em ${BACKEND_STARTUP_TIMEOUT_MS / 1000} segundos.\n\n` +
            `Últimos logs:\n${tail}`
          ));
        }
      }
    }, 500);
  });
}

async function aguardarReadiness(porta) {
  const deadline = Date.now() + 15_000;
  let ultimoErro = null;

  while (Date.now() < deadline) {
    try {
      const resp = await httpGet(`http://127.0.0.1:${porta}/`);
      if (resp.status >= 200 && resp.status < 400) {
        return;
      }
      ultimoErro = new Error(`HTTP ${resp.status}`);
    } catch (err) {
      ultimoErro = err;
    }
    await new Promise((r) => setTimeout(r, 500));
  }

  throw new Error(
    `Backend não respondeu após 15 segundos na porta ${porta}.\n${ultimoErro?.message || ""}`
  );
}

function criarJanela(porta) {
  janela = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1000,
    minHeight: 640,
    icon: path.join(__dirname, "prospectos.ico"),
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  janela.loadURL(`http://127.0.0.1:${porta}`);
  janela.once("ready-to-show", () => { janela.show(); });
  janela.on("closed", () => { janela = null; });
}

function configurarAutoUpdate() {
  if (!app.isPackaged) return;
  if (process.env.PROSPECTOS_DISABLE_UPDATES === "1") return;
  try {
    const { autoUpdater } = require("electron-updater");
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.checkForUpdatesAndNotify().catch(() => {});
  } catch { }
}

async function iniciar() {
  try {
    const pathsResolvidos = resolverPaths();
    const porta = await subirBackend(pathsResolvidos);
    await aguardarReadiness(porta);
    criarJanela(porta);
    configurarAutoUpdate();
  } catch (erro) {
    const logPath = PROSPECTOS_LOG_DIR
      ? path.join(PROSPECTOS_LOG_DIR, "prospeccao.log")
      : "logs/prospeccao.log";
    dialog.showErrorBox(
      "ProspectOS não conseguiu iniciar",
      `${erro.message}\n\nVeja os logs em: ${logPath}`
    );
    app.quit();
  }
}

async function limparBackend() {
  if (limpando) return limpando;
  limpando = (async () => {
    backendEncerradoDeProposito = true;
    if (!backend || backend.killed) return;

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        try { backend.kill("SIGKILL"); } catch { }
      }, BACKEND_SHUTDOWN_GRACE_MS);

      backend.on("exit", () => {
        clearTimeout(timeout);
        resolve();
      });

      backend.on("error", () => {
        clearTimeout(timeout);
        resolve();
      });

      try { backend.kill("SIGTERM"); } catch { }
    });
  })();
  return limpando;
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    if (backend && !backend.killed) {
      criarJanela(
        Number(fs.readFileSync(arquivoDaPorta(), "utf-8").trim()) || 5000
      );
    } else {
      iniciar();
    }
  }
});

app.on("before-quit", async (event) => {
  if (!backendEncerradoDeProposito) {
    event.preventDefault();
    await limparBackend();
    app.quit();
  }
});

app.on("will-quit", () => {
  if (backend && !backend.killed) {
    try { backend.kill("SIGKILL"); } catch { }
  }
});

app.whenReady().then(iniciar);
