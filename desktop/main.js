/**
 * Shell de desktop do ProspectOS.
 *
 * Papel deste processo:
 *  1. subir o backend empacotado (PyInstaller) como processo filho ("sidecar");
 *  2. descobrir em que porta ele ficou (lê "LISTENING_ON=<porta>" do stdout,
 *     com fallback pro porta.txt em %APPDATA%\ProspectOS);
 *  3. abrir a janela apontando pra http://127.0.0.1:<porta>;
 *  4. abrir links de WhatsApp numa janela interna de WhatsApp Web (sessão
 *     persistente - escaneia o QR uma vez) e links externos no navegador real;
 *  5. encerrar o backend junto com a janela;
 *  6. auto-update via GitHub Releases: baixa em segundo plano e, quando pronto,
 *     oferece "Reiniciar agora" - também dá pra checar manualmente no menu
 *     Ajuda → Verificar atualizações.
 */

const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

let janela = null;
let janelaWhatsapp = null;
let backend = null;
let backendEncerradoDeProposito = false;
let atualizacaoBaixada = false;

const ICONE = path.join(__dirname, "prospectos.ico");

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

    const aoAcharPorta = (porta) => {
      if (resolvido) return;
      resolvido = true;
      resolver(porta);
    };

    backend.stdout.on("data", (dados) => {
      const casado = String(dados).match(/LISTENING_ON=(\d+)/);
      if (casado) aoAcharPorta(Number(casado[1]));
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
          aoAcharPorta(porta);
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

// ---------------------------------------------------------------------------
// WhatsApp Web em janela interna
// ---------------------------------------------------------------------------

const REGEX_WHATSAPP = /^https:\/\/(wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)/;

/** Converte wa.me/api.whatsapp.com direto pro WhatsApp Web (pula o interstício). */
function urlParaWhatsappWeb(url) {
  try {
    const u = new URL(url);
    if (u.hostname === "wa.me") {
      const telefone = u.pathname.replace(/\D/g, "");
      const texto = u.searchParams.get("text") || "";
      return `https://web.whatsapp.com/send?phone=${telefone}&text=${encodeURIComponent(texto)}`;
    }
    if (u.hostname === "api.whatsapp.com") {
      return `https://web.whatsapp.com/send${u.search}`;
    }
    return url;
  } catch {
    return url;
  }
}

/** User agent de Chrome puro: o WhatsApp Web recusa navegadores "desconhecidos". */
function userAgentChrome() {
  return app.userAgentFallback.replace(/\s?(Electron|prospectos-desktop|ProspectOS)\/[\d.]+/g, "");
}

function abrirWhatsapp(url) {
  const destino = urlParaWhatsappWeb(url);

  if (janelaWhatsapp && !janelaWhatsapp.isDestroyed()) {
    janelaWhatsapp.loadURL(destino, { userAgent: userAgentChrome() });
    if (janelaWhatsapp.isMinimized()) janelaWhatsapp.restore();
    janelaWhatsapp.focus();
    return;
  }

  janelaWhatsapp = new BrowserWindow({
    width: 1150,
    height: 820,
    minWidth: 800,
    minHeight: 600,
    icon: ICONE,
    title: "WhatsApp · ProspectOS",
    autoHideMenuBar: true,
    webPreferences: {
      // sessão própria e persistente: o login (QR) sobrevive a restarts do app
      partition: "persist:whatsapp",
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  janelaWhatsapp.webContents.setUserAgent(userAgentChrome());
  janelaWhatsapp.loadURL(destino, { userAgent: userAgentChrome() });
  janelaWhatsapp.on("closed", () => {
    janelaWhatsapp = null;
  });
}

/** Links que saem do app: WhatsApp vira janela interna, o resto abre no navegador. */
function rotearLinksExternos(conteudo, porta) {
  conteudo.setWindowOpenHandler(({ url }) => {
    if (REGEX_WHATSAPP.test(url)) {
      abrirWhatsapp(url);
      return { action: "deny" };
    }
    if (/^https?:\/\//.test(url) && !url.startsWith(`http://127.0.0.1:${porta}`)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });
}

// ---------------------------------------------------------------------------
// Janela principal + menu
// ---------------------------------------------------------------------------

function criarJanela(porta) {
  janela = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1000,
    minHeight: 640,
    icon: ICONE,
    autoHideMenuBar: true,
    webPreferences: {
      // a interface é o React servido pelo backend - sem necessidade de Node no renderer
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  rotearLinksExternos(janela.webContents, porta);
  janela.loadURL(`http://127.0.0.1:${porta}`);
  janela.on("closed", () => {
    janela = null;
    // a janela principal manda: fechou o app, fecha o WhatsApp junto
    if (janelaWhatsapp && !janelaWhatsapp.isDestroyed()) janelaWhatsapp.close();
  });
}

function montarMenu() {
  const modelo = [
    {
      label: "Arquivo",
      submenu: [{ role: "close", label: "Fechar janela" }, { role: "quit", label: "Sair" }],
    },
    {
      label: "Exibir",
      submenu: [
        { role: "reload", label: "Recarregar" },
        { role: "togglefullscreen", label: "Tela cheia" },
        { type: "separator" },
        { role: "zoomIn", label: "Aumentar zoom" },
        { role: "zoomOut", label: "Diminuir zoom" },
        { role: "resetZoom", label: "Zoom padrão" },
      ],
    },
    {
      label: "Ajuda",
      submenu: [
        { label: "Verificar atualizações", click: () => verificarAtualizacoes(true) },
        { type: "separator" },
        {
          label: "ProspectOS no GitHub",
          click: () => shell.openExternal("https://github.com/nando0x/ProspectOS"),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(modelo));
}

// ---------------------------------------------------------------------------
// Auto-update com aviso "Reiniciar agora"
// ---------------------------------------------------------------------------

function obterAutoUpdater() {
  try {
    return require("electron-updater").autoUpdater;
  } catch {
    return null;
  }
}

function configurarAutoUpdate() {
  if (!app.isPackaged) return;
  const autoUpdater = obterAutoUpdater();
  if (!autoUpdater) return;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true; // mesmo em "Depois", instala ao fechar

  autoUpdater.on("update-downloaded", (info) => {
    atualizacaoBaixada = true;
    if (!janela) return;
    dialog
      .showMessageBox(janela, {
        type: "info",
        title: "Atualização pronta",
        message: `Nova versão disponível: v${info.version}`,
        detail:
          "A atualização já foi baixada. Reinicie agora para aplicar, ou continue " +
          "trabalhando - ela será instalada quando você fechar o ProspectOS.",
        buttons: ["Reiniciar agora", "Depois"],
        defaultId: 0,
        cancelId: 1,
      })
      .then(({ response }) => {
        if (response === 0) {
          backendEncerradoDeProposito = true;
          if (backend && !backend.killed) backend.kill();
          autoUpdater.quitAndInstall();
        }
      });
  });

  // checa no início e a cada 4 horas com o app aberto
  autoUpdater.checkForUpdates().catch(() => {});
  setInterval(() => autoUpdater.checkForUpdates().catch(() => {}), 4 * 60 * 60 * 1000);
}

/** Checagem manual (menu Ajuda). Com `avisar`, dá retorno mesmo sem novidade. */
function verificarAtualizacoes(avisar) {
  if (!app.isPackaged) {
    if (avisar) dialog.showMessageBox(janela, { message: "Em modo de desenvolvimento não há atualizações." });
    return;
  }
  const autoUpdater = obterAutoUpdater();
  if (!autoUpdater) return;

  if (atualizacaoBaixada) {
    // já tem uma pronta: reoferece o restart
    autoUpdater.emit("update-downloaded", { version: "nova" });
    return;
  }

  autoUpdater
    .checkForUpdates()
    .then((resultado) => {
      const atual = app.getVersion();
      const remota = resultado?.updateInfo?.version;
      if (avisar && (!remota || remota === atual)) {
        dialog.showMessageBox(janela, {
          type: "info",
          title: "Atualizações",
          message: `Você já está na versão mais recente (v${atual}).`,
        });
      }
      // se houver versão nova, o download começa sozinho e o evento
      // update-downloaded mostra o aviso de reiniciar
    })
    .catch(() => {
      if (avisar) {
        dialog.showMessageBox(janela, {
          type: "warning",
          title: "Atualizações",
          message: "Não foi possível verificar atualizações agora. Confira sua internet.",
        });
      }
    });
}

// ---------------------------------------------------------------------------
// Ciclo de vida
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  try {
    montarMenu();
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
