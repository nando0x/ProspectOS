import { httpClient } from "@/services/httpClient"
import type { HistoricoStatusItem, RespostaMarcarFollowup, StatusLead } from "@/types/lead"
import type {
  EstadoAnaliseInstagram,
  FunilInstagram,
  LeadInstagram,
  MetricasInstagram,
  PorNichoInstagram,
  PostInstagram,
  RespostaGerarMensagemInstagram,
} from "@/types/instagram"

export const instagramService = {
  analisar: (postUrl: string, nichoAlvo?: string) =>
    httpClient.post<{ ok: true; post_id: number }>("/api/instagram/analisar", {
      post_url: postUrl,
      nicho_alvo: nichoAlvo || undefined,
    }),

  consultarStatus: () =>
    httpClient.get<EstadoAnaliseInstagram>("/api/instagram/status"),

  retomarAnalise: (postId: number) =>
    httpClient.post<{ ok: true; post_id: number }>(
      `/api/instagram/posts/${postId}/retomar`
    ),

  listarPosts: (arquivados = false) =>
    httpClient.get<{ posts: PostInstagram[] }>(
      `/api/instagram/posts${arquivados ? "?arquivados=true" : ""}`
    ),

  arquivarPost: (postId: number) =>
    httpClient.post<{ ok: true }>(`/api/instagram/posts/${postId}/arquivar`),

  desarquivarPost: (postId: number) =>
    httpClient.post<{ ok: true }>(`/api/instagram/posts/${postId}/desarquivar`),

  excluirPostDefinitivamente: (postId: number) =>
    httpClient.delete<{ ok: true }>(`/api/instagram/posts/${postId}`),

  listarLeads: (
    postId: number,
    filtros?: { status?: string; nicho?: string; busca?: string }
  ) => {
    const params = new URLSearchParams()
    if (filtros?.status) params.set("status", filtros.status)
    if (filtros?.nicho) params.set("nicho", filtros.nicho)
    if (filtros?.busca) params.set("busca", filtros.busca)
    const query = params.toString()
    return httpClient.get<{ leads: LeadInstagram[] }>(
      `/api/instagram/posts/${postId}/leads${query ? `?${query}` : ""}`
    )
  },

  atualizarStatus: (leadId: number, status: StatusLead) =>
    httpClient.post<{ ok: true }>(`/api/instagram/leads/${leadId}/status`, {
      status,
    }),

  historico: (leadId: number) =>
    httpClient.get<HistoricoStatusItem[]>(
      `/api/instagram/leads/${leadId}/historico`
    ),

  listarNichos: () => httpClient.get<string[]>("/api/instagram/nichos"),

  metricas: () => httpClient.get<MetricasInstagram>("/api/instagram/metricas"),

  funil: () => httpClient.get<FunilInstagram>("/api/instagram/analytics/funil"),

  porNicho: () =>
    httpClient.get<PorNichoInstagram>("/api/instagram/analytics/por-nicho"),

  ignorar: (leadId: number) =>
    httpClient.post<{ ok: true }>(`/api/instagram/leads/${leadId}/ignorar`),

  excluirDefinitivamente: (leadId: number) =>
    httpClient.delete<{ ok: true }>(`/api/instagram/leads/${leadId}`),

  atualizarStatusEmLote: (leadIds: number[], status: StatusLead) =>
    httpClient.post<{ ok: true; atualizados: number }>(
      "/api/instagram/leads/bulk-status",
      { lead_ids: leadIds, status }
    ),

  ignorarEmLote: (leadIds: number[]) =>
    httpClient.post<{ ok: true; atualizados: number }>(
      "/api/instagram/leads/bulk-ignorar",
      { lead_ids: leadIds }
    ),

  excluirEmLoteDefinitivamente: (leadIds: number[]) =>
    httpClient.post<{ ok: true; excluidos: number }>(
      "/api/instagram/leads/bulk-excluir",
      { lead_ids: leadIds }
    ),

  atualizarObservacoes: (leadId: number, observacoes: string) =>
    httpClient.post<{ ok: true }>(
      `/api/instagram/leads/${leadId}/observacoes`,
      { observacoes }
    ),

  atualizarTags: (leadId: number, tags: string) =>
    httpClient.post<{ ok: true }>(`/api/instagram/leads/${leadId}/tags`, {
      tags,
    }),

  atualizarFollowup: (leadId: number, proximoFollowup: string | null) =>
    httpClient.post<{ ok: true }>(`/api/instagram/leads/${leadId}/followup`, {
      proximo_followup: proximoFollowup,
    }),

  marcarFollowupEnviado: (leadId: number) =>
    httpClient.post<RespostaMarcarFollowup>(
      `/api/instagram/leads/${leadId}/marcar-followup-enviado`
    ),

  desfazerFollowupEnviado: (
    leadId: number,
    anterior: {
      followUpsEnviadosAnterior: number
      ultimoFollowupEmAnterior: string | null
      proximoFollowupAnterior: string | null
    }
  ) =>
    httpClient.post<{ ok: true }>(
      `/api/instagram/leads/${leadId}/desfazer-followup-enviado`,
      {
        follow_ups_enviados_anterior: anterior.followUpsEnviadosAnterior,
        ultimo_followup_em_anterior: anterior.ultimoFollowupEmAnterior,
        proximo_followup_anterior: anterior.proximoFollowupAnterior,
      }
    ),

  gerarMensagem: (
    leadId: number,
    tipo: "contato" | "followup",
    forcarNova = false
  ) =>
    httpClient.post<RespostaGerarMensagemInstagram>(
      `/api/instagram/leads/${leadId}/gerar-mensagem`,
      { tipo, forcar_nova: forcarNova }
    ),

  salvarSugestaoDm: (leadId: number, sugestaoDm: string) =>
    httpClient.post<{ ok: true }>(`/api/instagram/leads/${leadId}/sugestao-dm`, {
      sugestao_dm: sugestaoDm,
    }),

  obterSessao: () =>
    httpClient.get<SessaoInstagram>("/api/instagram/sessao"),

  login: (dados: { usuario: string; senha: string; codigo_2fa?: string }) =>
    httpClient.post<RespostaLoginInstagram>("/api/instagram/login", dados),

  sairSessao: () => httpClient.delete<{ ok: true }>("/api/instagram/sessao"),
}

export interface SessaoInstagram {
  logada: boolean
  usuario: string | null
}

export type RespostaLoginInstagram =
  | { ok: true; usuario: string }
  | { precisa_2fa: true }

export function urlExportarCsvInstagram(postId: number) {
  return `/api/instagram/posts/${postId}/exportar`
}
