import { httpClient } from "@/services/httpClient"
import type { Configuracoes, ProvedorIA } from "@/types/config"

export const configService = {
  listar: () => httpClient.get<Configuracoes>("/api/configuracoes"),

  salvar: (chave: ProvedorIA, valor: string) =>
    httpClient.post<{ ok: true; mascarada: string }>("/api/configuracoes", {
      chave,
      valor,
    }),

  obterProxiesScraper: () =>
    httpClient.get<{ configurado: boolean; proxies: string }>(
      "/api/configuracoes/scraper-proxies"
    ),

  salvarProxiesScraper: (proxies: string) =>
    httpClient.post<{ ok: true; configurado: boolean }>(
      "/api/configuracoes/scraper-proxies",
      { proxies }
    ),

  obterPerfilVendedor: () =>
    httpClient.get<PerfilVendedor>("/api/configuracoes/perfil-vendedor"),

  salvarPerfilVendedor: (perfil: PerfilVendedor) =>
    httpClient.post<{ ok: true }>("/api/configuracoes/perfil-vendedor", perfil),

  obterFonteMaps: () =>
    httpClient.get<FonteMaps>("/api/configuracoes/fonte-maps"),

  salvarFonteMaps: (fonte: FonteMapsTipo, chave?: string) =>
    httpClient.post<{
      ok: true
      fonte: FonteMapsTipo
      chave_configurada: boolean
      mascarada: string | null
    }>("/api/configuracoes/fonte-maps", { fonte, chave: chave || undefined }),
}

export type FonteMapsTipo = "scraper" | "places"

export interface FonteMaps {
  fonte: FonteMapsTipo
  chave_configurada: boolean
  mascarada: string | null
  link_obter_chave: string
}

export interface PerfilVendedor {
  nome: string
  apresentacao: string
  diferencial: string
}
