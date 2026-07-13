import { httpClient } from "@/services/httpClient"
import type {
  FiltrosLeads,
  GerarMensagemResposta,
  HistoricoStatusItem,
  PaginaLeads,
  RespostaMarcarFollowup,
  StatusLead,
} from "@/types/lead"

const TAMANHO_PAGINA = 30

function montarQueryString(
  filtros: Partial<FiltrosLeads>,
  offset: number
): string {
  const params = new URLSearchParams()
  if (filtros.busca) params.set("busca", filtros.busca)
  if (filtros.status) params.set("status", filtros.status)
  if (filtros.nicho) params.set("nicho", filtros.nicho)
  if (filtros.nota_min) params.set("nota_min", filtros.nota_min)
  params.set("limit", String(TAMANHO_PAGINA))
  params.set("offset", String(offset))
  return params.toString()
}

export const leadsService = {
  listar: (filtros: Partial<FiltrosLeads>, offset: number) =>
    httpClient.get<PaginaLeads>(
      `/api/leads?${montarQueryString(filtros, offset)}`
    ),

  historico: (placeId: string) =>
    httpClient.get<HistoricoStatusItem[]>(
      `/api/leads/${encodeURIComponent(placeId)}/historico`
    ),

  atualizarStatus: (placeId: string, status: StatusLead) =>
    httpClient.post<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}/status`,
      { status }
    ),

  ignorar: (placeId: string) =>
    httpClient.post<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}/ignorar`
    ),

  atualizarObservacoes: (placeId: string, observacoes: string) =>
    httpClient.post<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}/observacoes`,
      { observacoes }
    ),

  atualizarTags: (placeId: string, tags: string) =>
    httpClient.post<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}/tags`,
      { tags }
    ),

  atualizarFollowup: (placeId: string, proximoFollowup: string | null) =>
    httpClient.post<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}/followup`,
      { proximo_followup: proximoFollowup }
    ),

  gerarMensagem: (
    placeId: string,
    forcarNova: boolean,
    tipo: "contato" | "followup" = "contato"
  ) =>
    httpClient.post<GerarMensagemResposta>(
      `/api/leads/${encodeURIComponent(placeId)}/gerar-mensagem`,
      { forcar_nova: forcarNova, tipo }
    ),

  marcarFollowupEnviado: (placeId: string) =>
    httpClient.post<RespostaMarcarFollowup>(
      `/api/leads/${encodeURIComponent(placeId)}/marcar-followup-enviado`
    ),

  desfazerFollowupEnviado: (
    placeId: string,
    anterior: {
      followUpsEnviadosAnterior: number
      ultimoFollowupEmAnterior: string | null
      proximoFollowupAnterior: string | null
    }
  ) =>
    httpClient.post<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}/desfazer-followup-enviado`,
      {
        follow_ups_enviados_anterior: anterior.followUpsEnviadosAnterior,
        ultimo_followup_em_anterior: anterior.ultimoFollowupEmAnterior,
        proximo_followup_anterior: anterior.proximoFollowupAnterior,
      }
    ),

  atualizarStatusEmLote: (placeIds: string[], status: StatusLead) =>
    httpClient.post<{ ok: true; atualizados: number }>(
      "/api/leads/bulk-status",
      { place_ids: placeIds, status }
    ),

  ignorarEmLote: (placeIds: string[]) =>
    httpClient.post<{ ok: true; atualizados: number }>(
      "/api/leads/bulk-ignorar",
      { place_ids: placeIds }
    ),

  excluirDefinitivamente: (placeId: string) =>
    httpClient.delete<{ ok: true }>(
      `/api/leads/${encodeURIComponent(placeId)}`
    ),

  excluirEmLoteDefinitivamente: (placeIds: string[]) =>
    httpClient.post<{ ok: true; excluidos: number }>(
      "/api/leads/bulk-excluir",
      { place_ids: placeIds }
    ),
}

export const EXPORTAR_CSV_URL = "/api/exportar"

export function urlExportarCsv(filtros: Partial<FiltrosLeads>): string {
  const params = new URLSearchParams()
  if (filtros.busca) params.set("busca", filtros.busca)
  if (filtros.status) params.set("status", filtros.status)
  if (filtros.nicho) params.set("nicho", filtros.nicho)
  if (filtros.nota_min) params.set("nota_min", filtros.nota_min)
  const query = params.toString()
  return `${EXPORTAR_CSV_URL}${query ? `?${query}` : ""}`
}
