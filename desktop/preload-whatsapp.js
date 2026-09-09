/**
 * Leitor PASSIVO da janela do WhatsApp Web.
 *
 * Contrato de segurança e de comportamento (não afrouxar sem pensar duas vezes):
 *  - PASSIVO: só observa o que já está renderizado no chat que o usuário abriu.
 *    Nunca clica, nunca navega, nunca abre conversa, nunca envia nada. O padrão
 *    de tráfego que o WhatsApp vê continua sendo o de uma pessoa usando o site.
 *  - NADA é exposto à página. Este preload roda em contexto isolado e fala com o
 *    processo principal por ipcRenderer direto. Não há contextBridge, então o
 *    JavaScript do WhatsApp (conteúdo remoto, não confiável) não alcança o IPC.
 *  - Falha em silêncio é proibida: se os seletores pararem de casar (a Meta muda
 *    o DOM sem aviso), reportamos "não consegui ler" para o app avisar o usuário
 *    e ele cair no registro manual.
 */

const { ipcRenderer } = require("electron");

// Tudo que depende do DOM do WhatsApp mora aqui. Quando a Meta mudar o layout,
// é este bloco - e só ele - que precisa de ajuste.
const SELETORES = {
  painelConversa: "#main",
  // cada mensagem tem data-id no formato "<true|false>_<jid>@c.us_<hash>"
  // (true = enviada por você). É o identificador mais estável do WhatsApp Web.
  linhaMensagem: "#main div[data-id]",
  // atributo com "[HH:MM, DD/MM/AAAA] Nome: " - fonte confiável de horário
  metadados: "div[data-pre-plain-text]",
  texto: "span.selectable-text, span[dir='ltr'], span[dir='auto']",
};

const INTERVALO_ENVIO_MS = 1500; // agrupa rajadas de mutação num lote só
// Só conversa individual (@c.us). Grupos têm JID "<criador>-<timestamp>@g.us" e
// são deliberadamente ignorados: capturar grupo significaria gravar mensagens de
// terceiros que não são o lead.
const RE_DATA_ID = /^(true|false)_(\d+)@c\.us_/;
const RE_PRE_PLAIN = /\[(\d{1,2}):(\d{2})(?::(\d{2}))?,\s*(\d{1,2})\/(\d{1,2})\/(\d{4})\]/;

let pendentes = new Map(); // chave -> mensagem (dedup dentro do próprio lote)
let jaEnviadas = new Set(); // o que já mandamos nesta sessão da janela
let temporizador = null;
let telefoneAtual = null;
let ultimoAvisoDeFalha = 0;

/** "[00:35, 26/07/2026]" -> ISO local. Sem o atributo, usa a hora de agora. */
function horarioParaIso(prePlainText) {
  const casado = RE_PRE_PLAIN.exec(prePlainText || "");
  if (!casado) return new Date().toISOString().slice(0, 19);
  const [, hora, minuto, segundo, dia, mes, ano] = casado;
  const pad = (n) => String(n).padStart(2, "0");
  return `${ano}-${pad(mes)}-${pad(dia)}T${pad(hora)}:${minuto}:${segundo || "00"}`;
}

function extrairTexto(linha) {
  const nos = linha.querySelectorAll(SELETORES.texto);
  if (!nos.length) return "";
  // a última ocorrência costuma ser o corpo da mensagem (as anteriores são
  // citação/prévia de link); junta as linhas preservando quebras
  const alvo = nos[nos.length - 1];
  return (alvo.innerText || alvo.textContent || "").trim();
}

/** Lê o que está na tela agora. Retorna {mensagens, telefone} sem tocar em nada. */
function lerConversaVisivel() {
  const linhas = document.querySelectorAll(SELETORES.linhaMensagem);
  const mensagens = [];
  let telefone = null;

  for (const linha of linhas) {
    const dataId = linha.getAttribute("data-id") || "";
    const casado = RE_DATA_ID.exec(dataId);
    if (!casado) continue; // não é uma linha de mensagem de contato individual

    const [, souEu, jid] = casado;
    telefone = telefone || jid;

    // mídia/áudio sem legenda: registra um marcador em vez de sumir com a
    // mensagem - a IA precisa saber que houve troca, mesmo sem o conteúdo
    const texto = extrairTexto(linha) || "[mensagem sem texto: mídia ou áudio]";

    const blocoMeta = linha.querySelector(SELETORES.metadados);
    mensagens.push({
      autor: souEu === "true" ? "vendedor" : "lead",
      texto,
      enviada_em: horarioParaIso(blocoMeta && blocoMeta.getAttribute("data-pre-plain-text")),
      id_externo: dataId,
    });
  }

  return { mensagens, telefone };
}

function agendarEnvio() {
  if (temporizador) return;
  temporizador = setTimeout(() => {
    temporizador = null;
    enviarLote();
  }, INTERVALO_ENVIO_MS);
}

function enviarLote() {
  if (!pendentes.size || !telefoneAtual) return;
  const mensagens = Array.from(pendentes.values());
  pendentes = new Map();
  mensagens.forEach((m) => jaEnviadas.add(m.id_externo));
  ipcRenderer.send("whatsapp:mensagens", { telefone: telefoneAtual, mensagens });
}

function coletar() {
  let leitura;
  try {
    leitura = lerConversaVisivel();
  } catch (erro) {
    reportarFalhaDeLeitura(String(erro && erro.message));
    return;
  }

  if (!leitura.telefone) {
    // sem nenhuma linha reconhecível: ou nenhum chat está aberto (normal), ou
    // os seletores quebraram (problema). Só avisamos se o painel existe.
    if (document.querySelector(SELETORES.painelConversa)) {
      reportarFalhaDeLeitura("nenhuma mensagem reconhecida no chat aberto");
    }
    return;
  }

  if (leitura.telefone !== telefoneAtual) {
    // usuário trocou de conversa: zera o que era da conversa anterior
    telefoneAtual = leitura.telefone;
    pendentes = new Map();
    jaEnviadas = new Set();
    ipcRenderer.send("whatsapp:conversa-mudou", { telefone: telefoneAtual });
  }

  for (const mensagem of leitura.mensagens) {
    if (!jaEnviadas.has(mensagem.id_externo)) {
      pendentes.set(mensagem.id_externo, mensagem);
    }
  }
  if (pendentes.size) agendarEnvio();
}

/** Avisa o app (no máximo uma vez por minuto) que a leitura parou de funcionar. */
function reportarFalhaDeLeitura(detalhe) {
  const agora = Date.now();
  if (agora - ultimoAvisoDeFalha < 60_000) return;
  ultimoAvisoDeFalha = agora;
  ipcRenderer.send("whatsapp:leitura-falhou", { detalhe });
}

function iniciarObservador() {
  const alvo = document.querySelector(SELETORES.painelConversa) || document.body;
  const observador = new MutationObserver(() => coletar());
  observador.observe(alvo, { childList: true, subtree: true, characterData: true });
  coletar(); // primeira leitura do que já está na tela
}

// nunca roda dentro de iframe (o WhatsApp usa iframes auxiliares; observar ali
// só geraria ruído e leituras parciais)
if (window.top !== window) {
  // eslint-disable-next-line no-empty-function
} else window.addEventListener("DOMContentLoaded", () => {
  // o WhatsApp Web monta a interface depois do load (QR, sincronização),
  // então esperamos o painel aparecer em vez de assumir que já existe
  const aguardar = setInterval(() => {
    if (document.querySelector(SELETORES.painelConversa) || document.body) {
      clearInterval(aguardar);
      iniciarObservador();
    }
  }, 1000);
  setTimeout(() => clearInterval(aguardar), 120_000);
});
