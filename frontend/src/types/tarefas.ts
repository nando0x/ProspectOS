import type { StatusLead } from "@/types/lead"

export interface TarefaFollowup {
  id: string | number
  canal: "maps" | "instagram"
  titulo: string
  status: StatusLead
  proximo_followup: string
  follow_ups_enviados: number
  ultimo_followup_em: string | null
  mensagem: string | null
  whatsapp_link?: string | null
  telefone?: string | null
  username?: string
  instagram_url?: string | null
}

export interface LeadQuente {
  id: string
  canal: "maps"
  titulo: string
  categoria: string | null
  nota: number | null
  num_avaliacoes: number | null
  site_status: "sem_site" | "site_ruim" | null
  site_problemas: string | null
  whatsapp_link: string | null
  telefone: string | null
  mensagem: string | null
  instagram_url: string | null
  score: number
}

export interface TarefasHoje {
  followups: TarefaFollowup[]
  novos_quentes: LeadQuente[]
}
