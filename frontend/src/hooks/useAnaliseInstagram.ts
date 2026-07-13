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

  const dispararAnalise = useMutation({
    mutationFn: ({ postUrl, nichoAlvo }: { postUrl: string; nichoAlvo?: string }) =>
      instagramService.analisar(postUrl, nichoAlvo),
    onSuccess: () => {
      setResultadoFinal(null)
      setPoll(true)
    },
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
    statusAnalise,
    pollingAtivo: poll,
    resultadoFinal,
    limparResultado,
  }
}
