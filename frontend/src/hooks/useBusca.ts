import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { buscaService } from "@/services/buscaService"
import { useInvalidarLeads } from "@/hooks/useInvalidarLeads"
import { notificar, pedirPermissaoNotificacao } from "@/hooks/useNotificacaoNavegador"
import { tocarSom } from "@/hooks/useSom"
import type { AreaBuscaPayload, EstadoBusca } from "@/types/busca"

export function useBusca() {
  const queryClient = useQueryClient()
  const invalidarListaEMetricas = useInvalidarLeads()
  const [poll, setPoll] = useState(false)
  const [resultadoFinal, setResultadoFinal] = useState<EstadoBusca | null>(null)
  const viuRodandoRef = useRef(false)

  useEffect(() => {
    let ativo = true
    buscaService.consultarStatus().then((status) => {
      if (!ativo) return
      queryClient.setQueryData(["busca-status"], status)
      if (status.rodando) {
        viuRodandoRef.current = true
        setPoll(true)
      }
    })
    return () => {
      ativo = false
    }
  }, [queryClient])

  const aoDisparar = () => {
    setResultadoFinal(null)
    viuRodandoRef.current = true
    // remove o status cacheado da busca ANTERIOR (rodando:false) - senão o
    // effect abaixo veria !rodando e dispararia "conclusão" instantânea com o
    // resultado antigo antes desta busca começar
    queryClient.removeQueries({ queryKey: ["busca-status"] })
    setPoll(true)
    pedirPermissaoNotificacao()
  }

  const dispararBusca = useMutation({
    mutationFn: (queries: string) => buscaService.disparar(queries),
    onSuccess: aoDisparar,
  })

  const dispararBuscaMapa = useMutation({
    mutationFn: ({ nichos, areas }: { nichos: string[]; areas: AreaBuscaPayload[] }) =>
      buscaService.dispararPorMapa(nichos, areas),
    onSuccess: aoDisparar,
  })

  const statusBusca = useQuery({
    queryKey: ["busca-status"],
    queryFn: buscaService.consultarStatus,
    enabled: poll,
    refetchInterval: (query) => (query.state.data?.rodando ? 2000 : false),
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (statusBusca.data?.rodando) {
      viuRodandoRef.current = true
    }
  }, [statusBusca.data?.rodando])

  useEffect(() => {
    if (!poll || !statusBusca.data || statusBusca.data.rodando) return
    if (!viuRodandoRef.current) return

    setPoll(false)
    setResultadoFinal(statusBusca.data)
    queryClient.invalidateQueries({ queryKey: ["nichos"] })
    invalidarListaEMetricas()

    const mensagemConclusao = statusBusca.data.mensagem
    if (mensagemConclusao) {
      notificar("Busca de leads concluída", mensagemConclusao)
      tocarSom("busca-maps-concluida")
    }
  }, [poll, statusBusca.data, queryClient, invalidarListaEMetricas])

  const limparResultado = () => setResultadoFinal(null)

  return {
    dispararBusca,
    dispararBuscaMapa,
    statusBusca,
    pollingAtivo: poll,
    resultadoFinal,
    limparResultado,
  }
}
