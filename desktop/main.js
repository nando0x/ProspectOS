/**
 * Shell de desktop do ProspectOS.
 *
 * Papel deste processo:
 *  1. resolver os paths da aplicação via Electron (app.getPath);
 *  2. subir o backend empacotado (PyInstaller) como processo filho ("sidecar")
 *     passando os paths resolvidos nas variáveis PROSPECTOS_*;
 *  3. descobrir em que porta ele ficou (lê "LISTENING_ON=<porta>" do stdout,
 *     com fallback pro porta.txt em PROSPECTOS_DATA_DIR);
 *  4. abrir a janela apontando pra http://127.0.0.1:<porta>;
 *  5. encerrar o backend junto com a janela;
 *  6. auto-update via GitHub Releases (electron-updater) - baixa em segundo
 *     plano e instala no próximo fechamento do app.
 */

const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const {
  resolveRuntimeTarget,
  validateExecutable,
  loadRuntimeManifest,
} = require("./runtime-target.js");

let janela = null;
let backend = null;
let backendEncerradoDeProposito = false;
let PROSPECTOS_DATA_DIR = null;
let PROSPECTOS_LOG_DIR = null;

// só uma instância do app por vez (a segunda só foca a janela da primeira)
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

function resolverBackend() {
  const manifestPath = path.join(__dirname, "..", "shared", "runtime-targets.json");
  const resourcesPath = app.isPackaged ? process.resourcesPath : path.join(__dirname, "..");
  const devRoot = path.join(__dirname, "..");

  const result = resolveRuntimeTarget({
    packaged: app.isPackaged,
    manifestPath,
    resourcesPath,
    devRoot,
  });

  return result.backendPath;
}

function arquivoDaPorta() {
  return path.join(PROSPECTOS_DATA_DIR, "porta.txt");
}

/** Resolve paths do ProspectOS usando Electron como autoridade. */
function resolverPaths() {
  PROSPECTOS_DATA_DIR = app.getPath("userData");
  PROSPECTOS_LOG_DIR = app.getPath("logs");

  // Garantir que não haja duplicação do nome "ProspectOS"
  // (app.getPath("userData") já termina em "ProspectOS" quando empacotado)
  const nomeBase = path.basename(PROSPECTOS_DATA_DIR);
  if (nomeBase !== "ProspectOS") {
    // Em dev o app name pode ser "prospectos-desktop"; normaliza
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
  const PROSPECTOS_RESOURCE_DIR = process.resourcesPath || path.join(__dirname, "..");

  // Cria diretórios antes do spawn
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

/** Sobe o backend e resolve com a porta anunciada. */
function subirBackend(pathsResolvidos) {
  return new Promise((resolver, rejeitar) => {
    const exe = resolverBackend();
    const runtimeTarget = require("./runtime-target.js").getCurrentTarget();
    const manifestPath = path.join(__dirname, "..", "shared", "runtime-targets.json");

    try {
      validateExecutable(exe, "Backend do ProspectOS");
    } catch (err) {
      rejeitar(
        new Error(
          `Backend não encontrado para ${runtimeTarget}:\n${exe}\n\n` +
          `Verifique se o backend foi compilado (modo desenvolvimento) ou ` +
          `se a instalação está íntegra (modo empacotado).\n` +
          `Target: ${runtimeTarget}\nManifesto: ${manifestPath}`
        )
      );
      return;
    }

    console.log(
      `runtime target: ${runtimeTarget}\n` +
      `backend executable: ${exe}\n` +
      `runtime manifest: ${manifestPath}`
    );

    // apaga o porta.txt velho pra não ler porta de uma execução anterior
    try {
      fs.unlinkSync(arquivoDaPorta());
    } catch {
      /* não existia, tudo bem */
    }

    backend = spawn(exe, [], {
      env: {
        ...process.env,
        PROSPECTOS_NO_BROWSER: "1",
        PROSPECTOS_DATA_DIR: pathsResolvidos.PROSPECTOS_DATA_DIR,
        PROSPECTOS_LOG_DIR: pathsResolvidos.PROSPECTOS_LOG_DIR,
        PROSPECTOS_TEMP_DIR: pathsResolvidos.PROSPECTOS_TEMP_DIR,
        PROSPECTOS_RESOURCE_DIR: pathsResolvidos.PROSPECTOS_RESOURCE_DIR,
        PROSPECTOS_RUNTIME_MANIFEST: manifestPath,
        PROSPECTOS_RUNTIME_TARGET: runtimeTarget,
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    let resolvido = false;

    const aoAchArPorta = (porta) => {
      if (resolvido) return;
      resolvido = true;
      resolver(porta);
    };

    backend.stdout.on("data", (dados) => {
      const casado = String(dados).match(/LISTENING_ON=(\d+)/);
      if (casado) aoAchArPorta(Number(casado[1]));
    });

    backend.on("exit", (codigo) => {
      if (backendEncerradoDeProposito) return;
      if (!resolvido) {
        rejeitar(new Error(`O backend encerrou antes de subir (código ${codigo}).`));
      } else {
        // backend caiu com o app aberto: avisa e fecha
        dialog.showErrorBox(
          "ProspectOS",
          "O motor do ProspectOS parou de responder. O aplicativo será fechado."
        );
        app.quit();
      }
    });

    // fallback: se o stdout não entregar (ex.: pipe perdido), lê o porta.txt
    const inicio = Date.now();
    const intervalo = setInterval(() => {
      if (resolvido) {
        clearInterval(intervalo);
        return;
      }
      try {
        const porta = Number(fs.readFileSync(arquivoDaPorta(), "utf-8").trim());
        if (porta > 0) {
          clearInterval(intervalo);
          aoAchArPorta(porta);
        }
      } catch {
        /* arquivo ainda não existe */
      }
      if (Date.now() - inicio > 30_000) {
        clearInterval(intervalo);
        if (!resolvido) rejeitar(new Error("O backend não subiu em 30 segundos."));
      }
    }, 500);
  });
}

function criarJanela(porta) {
  janela = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1000,
    minHeight: 640,
    icon: path.join(__dirname, "prospectos.ico"),
    autoHideMenuBar: true,
    webPreferences: {
      // a interface é o React servido pelo backend - sem necessidade de Node no renderer
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  janela.loadURL(`http://127.0.0.1:${porta}`);
  janela.on("closed", () => {
    janela = null;
  });
}

function configurarAutoUpdate() {
  // Em dev (não empacotado) o updater não tem o que checar
  if (!app.isPackaged) return;
  try {
    const { autoUpdater } = require("electron-updater");
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true; // instala sozinho ao fechar o app
    autoUpdater.checkForUpdatesAndNotify().catch(() => {
      /* sem internet ou sem release novo - segue o jogo */
    });
  } catch {
    /* updater indisponível não pode impedir o app de abrir */
  }
}

app.whenReady().then(async () => {
  try {
    const pathsResolvidos = resolverPaths();
    const porta = await subirBackend(pathsResolvidos);
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
});

app.on("window-all-closed", () => {
  // encerra o backend junto com a janela (não deixamos processo órfão)
  backendEncerradoDeProposito = true;
  if (backend && !backend.killed) backend.kill();
  app.quit();
});

app.on("before-quit", () => {
  backendEncerradoDeProposito = true;
  if (backend && !backend.killed) backend.kill();
});
