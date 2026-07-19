import { httpClient } from "@/services/httpClient"
import { ajustarSaudacao } from "@/lib/saudacao"
import type { TarefasHoje } from "@/types/tarefas"

export const tarefasService = {
  tarefasHoje: () => httpClient.get<TarefasHoje>("/api/tarefas-hoje"),
}

/** Link wa.me com a mensagem já preenchida no campo de texto do WhatsApp -
 * com a saudação ajustada pra hora atual (a copy pode ter sido gerada horas atrás). */
export function linkWhatsappComMensagem(
  whatsappLink: string,
  mensagem?: string | null
): string {
  if (!mensagem) return whatsappLink
  return `${whatsappLink}?text=${encodeURIComponent(ajustarSaudacao(mensagem))}`
}
