import { useEffect, useState } from "react"

/** `chaveContexto` identifica o conjunto de leads em tela (post + filtros).
 * Quando muda, a seleção é limpa - evita ação em lote sobre leads invisíveis. */
export function useSelecaoLeadsInstagram(chaveContexto?: string) {
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set())

  useEffect(() => {
    setSelecionados(new Set())
  }, [chaveContexto])

  const alternar = (leadId: number) => {
    setSelecionados((atual) => {
      const novo = new Set(atual)
      if (novo.has(leadId)) {
        novo.delete(leadId)
      } else {
        novo.add(leadId)
      }
      return novo
    })
  }

  const limpar = () => setSelecionados(new Set())

  return {
    selecionados,
    alternar,
    limpar,
    quantidade: selecionados.size,
  }
}
