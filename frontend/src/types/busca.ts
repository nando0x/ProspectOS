export type EtapaBusca = "scraping" | "verificando_sites" | ""

export interface EstadoBusca {
  rodando: boolean
  mensagem: string
  etapa: EtapaBusca
  empresas_encontradas: number
  empresas_processadas: number
  /** Busca por mapa: qual pino está sendo processado (0 quando busca por texto) */
  area_atual: number
  total_areas: number
  progresso_atual?: number | null
  progresso_total?: number | null
}

/** Um pino no mapa com raio de busca. `id` existe só no frontend (chave de lista). */
export interface AreaBusca {
  id: string
  lat: number
  lng: number
  raio_m: number
  rotulo: string
}

export type AreaBuscaPayload = Omit<AreaBusca, "id">

/** Uma busca passada (da tabela jobs do backend). */
export interface BuscaHistorico {
  id: number
  status: "rodando" | "concluido" | "erro" | "interrompido"
  mensagem: string | null
  progresso_atual: number
  progresso_total: number
  iniciado_em: string
  finalizado_em: string | null
}
