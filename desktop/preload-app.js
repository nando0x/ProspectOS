/**
 * Preload da janela principal: expõe ao React uma superfície mínima e somente
 * de leitura para saber que está rodando no app de desktop e para ouvir os
 * eventos do cockpit (mensagem capturada, conversa trocada, leitura quebrada).
 *
 * Só o que está aqui é visível para a interface - nada de ipcRenderer solto,
 * nada de Node. A interface NÃO consegue disparar ações no WhatsApp por aqui:
 * a ponte é de mão única, do WhatsApp para o app.
 */

const { contextBridge, ipcRenderer } = require("electron");

const EVENTOS = [
  "cockpit:mensagens-novas",
  "cockpit:conversa-mudou",
  "cockpit:conversa-sem-lead",
  "cockpit:leitura-falhou",
];

contextBridge.exposeInMainWorld("prospectOS", {
  desktop: true,
  versao: process.env.npm_package_version || null,

  /** Assina um evento do cockpit. Devolve a função de cancelamento. */
  aoReceber(evento, callback) {
    if (!EVENTOS.includes(evento)) return () => {};
    const ouvinte = (_evento, dados) => callback(dados);
    ipcRenderer.on(evento, ouvinte);
    return () => ipcRenderer.removeListener(evento, ouvinte);
  },
});
