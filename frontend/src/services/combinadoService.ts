import { httpClient } from "@/services/httpClient"
import type { FollowUpHoje, MetaSemanal, MetricasCombinadas } from "@/types/combinado"
import type { FunilResposta, PorNichoResposta } from "@/types/analytics"

export const combinadoService = {
  metricas: () =>
    httpClient.get<MetricasCombinadas>("/api/metricas-combinadas"),

  followUpsHoje: () =>
    httpClient.get<{ leads: FollowUpHoje[] }>("/api/follow-ups-hoje"),

  funilCombinado: () =>
    httpClient.get<FunilResposta>("/api/analytics/funil-combinado"),

  porNichoCombinado: () =>
    httpClient.get<PorNichoResposta>("/api/analytics/por-nicho-combinado"),

  metaSemanal: () => httpClient.get<MetaSemanal>("/api/meta-semanal"),

  salvarMetaSemanal: (meta: number) =>
    httpClient.post<{ ok: true; meta: number }>("/api/meta-semanal", { meta }),
}
