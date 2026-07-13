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
}
