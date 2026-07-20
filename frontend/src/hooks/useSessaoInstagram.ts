import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { instagramService } from "@/services/instagramService"

export function useSessaoInstagram() {
  return useQuery({
    queryKey: ["sessao-instagram"],
    queryFn: instagramService.obterSessao,
  })
}

export function useLoginInstagram() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: instagramService.login,
    onSuccess: (dados) => {
      if ("ok" in dados) {
        queryClient.invalidateQueries({ queryKey: ["sessao-instagram"] })
        toast.success(`Conectado como @${dados.usuario}.`)
      }
      // precisa_2fa: o card trata mostrando o campo de código
    },
    onError: (erro: Error) => {
      toast.error(erro.message)
    },
  })
}

export function useSairInstagram() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: instagramService.sairSessao,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessao-instagram"] })
      toast.success("Sessão do Instagram encerrada.")
    },
  })
}
