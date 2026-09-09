import { httpClient } from "@/services/httpClient"
import type {
  AnaliseConversa,
  AutorMensagem,
  ConversaResposta,
  EstadoCaptura,
} from "@/types/conversa"

const base = (canal: string, leadRef: string) =>
  `/api/conversa/${canal}/${encodeURIComponent(leadRef)}`

export const conversaService = {
  obter: (canal: string, leadRef: string) =>
    httpClient.get<ConversaResposta>(`${base(canal, leadRef)}/mensagens`),

  adicionarMensagem: (
    canal: string,
    leadRef: string,
    dados: { autor: AutorMensagem; texto: string; origem?: string }
  ) => httpClient.post<{ ok: true } & ConversaResposta>(`${base(canal, leadRef)}/mensagens`, dados),

  removerMensagem: (canal: string, leadRef: string, mensagemId: number) =>
    httpClient.delete<{ ok: true } & ConversaResposta>(
      `${base(canal, leadRef)}/mensagens/${mensagemId}`
    ),

  analisar: (canal: string, leadRef: string) =>
    httpClient.post<AnaliseConversa>(`${base(canal, leadRef)}/analisar`),

  estadoCaptura: () => httpClient.get<EstadoCaptura>("/api/conversa/estado-captura"),

  /** Avisa o backend de quem é a conversa que está prestes a abrir no WhatsApp. */
  registrarLeadAtivo: (canal: string, leadRef: string) =>
    httpClient.post<{ ok: true }>("/api/conversa/lead-ativo", { canal, lead_ref: leadRef }),
}
