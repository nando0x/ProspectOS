export type AutorMensagem = "vendedor" | "lead"
export type OrigemMensagem = "whatsapp" | "manual" | "app"

export type EstagioNegociacao =
  | "primeiro_contato"
  | "descoberta"
  | "interesse"
  | "objecao"
  | "negociacao"
  | "fechamento"
  | "esfriou"

export interface MensagemConversa {
  id: number
  autor: AutorMensagem
  texto: string
  enviada_em: string
  origem: OrigemMensagem
}

export interface AnaliseConversa {
  estagio: EstagioNegociacao
  leitura: string
  objetivo: string
  resposta_sugerida: string
  evitar: string[]
  provedor?: string | null
  avisos?: string[]
  mensagens_consideradas?: number
  criada_em?: string
}

export interface ConversaResposta {
  mensagens: MensagemConversa[]
  analise: AnaliseConversa | null
}

export interface EstadoCaptura {
  ativa: boolean
  visto_em: string | null
  telefone: string | null
  seletores_ok: boolean
  detalhe: string | null
}

export const LABEL_ESTAGIO: Record<EstagioNegociacao, string> = {
  primeiro_contato: "Primeiro contato",
  descoberta: "Descoberta",
  interesse: "Interesse",
  objecao: "Objeção",
  negociacao: "Negociação",
  fechamento: "Fechamento",
  esfriou: "Esfriou",
}

/** Cor do badge do estágio: verde conforme avança, laranja em objeção, cinza quando esfria. */
export const COR_ESTAGIO: Record<EstagioNegociacao, string> = {
  primeiro_contato: "bg-muted text-muted-foreground",
  descoberta: "bg-info/15 text-info",
  interesse: "bg-success/15 text-success",
  objecao: "bg-warning/15 text-warning",
  negociacao: "bg-success/15 text-success",
  fechamento: "bg-success/25 text-success",
  esfriou: "bg-muted text-muted-foreground",
}
