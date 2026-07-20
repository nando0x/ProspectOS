import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { instagramService } from "@/services/instagramService"
import { tocarSom } from "@/hooks/useSom"
import type { EstadoAnaliseInstagram } from "@/types/instagram"

export function useAnaliseInstagram() {
  const queryClient = useQueryClient()
  const [poll, setPoll] = useState(false)
  const [resultadoFinal, setResultadoFinal] = useState<EstadoAnaliseInstagram | null>(
    null
  )

  const aoDisparar = () => {
    setResultadoFinal(null)
    // descarta o status cacheado da análise anterior (rodando:false) - senão o
    // effect veria !rodando e concluiria na hora com o resultado antigo
    queryClient.removeQueries({ queryKey: ["instagram-status"] })
    setPoll(true)
  }

  const dispararAnalise = useMutation({
    mutationFn: ({ postUrl, nichoAlvo }: { postUrl: string; nichoAlvo?: string }) =>
      instagramService.analisar(postUrl, nichoAlvo),
    onSuccess: aoDisparar,
  })

  const retomarAnalise = useMutation({
    mutationFn: (postId: number) => instagramService.retomarAnalise(postId),
    onSuccess: aoDisparar,
  })

  const statusAnalise = useQuery({
    queryKey: ["instagram-status"],
    queryFn: instagramService.consultarStatus,
    enabled: poll,
    refetchInterval: (query) => (query.state.data?.rodando ? 2000 : false),
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (poll && statusAnalise.data && !statusAnalise.data.rodando) {
      setPoll(false)
      setResultadoFinal(statusAnalise.data)
      queryClient.invalidateQueries({ queryKey: ["instagram-posts"] })
      tocarSom("analise-instagram-concluida")
    }
  }, [poll, statusAnalise.data, queryClient])

  const limparResultado = () => setResultadoFinal(null)

  return {
    dispararAnalise,
    retomarAnalise,
    statusAnalise,
    pollingAtivo: poll,
    resultadoFinal,
    limparResultado,
  }
}
