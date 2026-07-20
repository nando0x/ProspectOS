/**
 * Shell de desktop do ProspectOS.
 *
 * Papel deste processo:
 *  1. subir o backend empacotado (PyInstaller) como processo filho ("sidecar");
 *  2. descobrir em que porta ele ficou (lê "LISTENING_ON=<porta>" do stdout,
 *     com fallback pro porta.txt em %APPDATA%\ProspectOS);
 *  3. abrir a janela apontando pra http://127.0.0.1:<porta>;
 *  4. encerrar o backend junto com a janela;
 *  5. auto-update via GitHub Releases (electron-updater) - baixa em segundo
 *     plano e instala no próximo fechamento do app.
 */

const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

let janela = null;
let backend = null;
let backendEncerradoDeProposito = false;

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

function caminhoDoBackend() {
  if (app.isPackaged) {
    // empacotado: o bundle do PyInstaller vai junto como extraResource
    return path.join(process.resourcesPath, "backend", "ProspectOS.exe");
  }
  // dev: usa o bundle buildado na pasta do projeto
  return path.join(__dirname, "..", "backend", "dist", "ProspectOS", "ProspectOS.exe");
}

function arquivoDaPorta() {
  return path.join(process.env.APPDATA, "ProspectOS", "porta.txt");
}

/** Sobe o backend e resolve com a porta anunciada. */
function subirBackend() {
  return new Promise((resolver, rejeitar) => {
    const exe = caminhoDoBackend();
    if (!fs.existsSync(exe)) {
      rejeitar(new Error(`Backend não encontrado em: ${exe}`));
      return;
    }

    // apaga o porta.txt velho pra não ler porta de uma execução anterior
    try {
      fs.unlinkSync(arquivoDaPorta());
    } catch {
      /* não existia, tudo bem */
    }

    backend = spawn(exe, [], {
      env: { ...process.env, PROSPECTOS_NO_BROWSER: "1" },
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
    const porta = await subirBackend();
    criarJanela(porta);
    configurarAutoUpdate();
  } catch (erro) {
    dialog.showErrorBox(
      "ProspectOS não conseguiu iniciar",
      `${erro.message}\n\nVeja os logs em %APPDATA%\\ProspectOS\\logs\\prospeccao.log`
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
