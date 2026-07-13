import type { StatusLead } from "@/types/lead"

export interface MetricasCombinadas {
  total: number
  por_status: Record<string, number>
  taxa_conversao: number
  lembretes_hoje: number
  maps: { total: number; lembretes_hoje: number }
  instagram: { total: number; lembretes_hoje: number }
}

export type CanalLead = "maps" | "instagram"

export interface FollowUpHoje {
  place_id: string
  titulo: string
  proximo_followup: string
  status: StatusLead
  canal: CanalLead
}

export interface MetaSemanal {
  meta: number
  progresso: number
  faltam: number
  porcentagem: number
  inicio_semana: string
}
