import { useEffect, useState } from "react"

/** `chaveContexto` identifica o conjunto de leads em tela (ex.: filtros serializados).
 * Quando muda, a seleção é limpa - evita que uma ação em lote rode sobre leads
 * que não estão mais visíveis. */
export function useSelecaoLeads(chaveContexto?: string) {
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set())

  useEffect(() => {
    setSelecionados(new Set())
  }, [chaveContexto])

  const alternar = (placeId: string) => {
    setSelecionados((atual) => {
      const novo = new Set(atual)
      if (novo.has(placeId)) {
        novo.delete(placeId)
      } else {
        novo.add(placeId)
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
