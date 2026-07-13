import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { instagramService } from "@/services/instagramService"
import { tocarSom } from "@/hooks/useSom"
import type { StatusLead } from "@/types/lead"

export function useBulkMutationsInstagram(postId: number) {
  const queryClient = useQueryClient()

  const invalidar = () => {
    queryClient.invalidateQueries({ queryKey: ["instagram-leads", postId] })
    queryClient.invalidateQueries({ queryKey: ["instagram-posts"] })
    queryClient.invalidateQueries({ queryKey: ["instagram-metricas"] })
    queryClient.invalidateQueries({ queryKey: ["instagram-analytics"] })
    queryClient.invalidateQueries({ queryKey: ["instagram-nichos"] })
    queryClient.invalidateQueries({ queryKey: ["metricas-combinadas"] })
    queryClient.invalidateQueries({ queryKey: ["follow-ups-hoje"] })
    queryClient.invalidateQueries({ queryKey: ["meta-semanal"] })
  }

  const atualizarStatusEmLote = useMutation({
    mutationFn: (input: { leadIds: number[]; status: StatusLead }) =>
      instagramService.atualizarStatusEmLote(input.leadIds, input.status),
    onSuccess: (resposta) => {
      invalidar()
      toast.success(`${resposta.atualizados} lead(s) atualizado(s).`)
    },
  })

  const ignorarEmLote = useMutation({
    mutationFn: (leadIds: number[]) => instagramService.ignorarEmLote(leadIds),
    onSuccess: (resposta) => {
      invalidar()
      toast.success(`${resposta.atualizados} lead(s) ignorado(s).`)
    },
  })

  const excluirEmLoteDefinitivamente = useMutation({
    mutationFn: (leadIds: number[]) =>
      instagramService.excluirEmLoteDefinitivamente(leadIds),
    onSuccess: (resposta) => {
      invalidar()
      tocarSom("apagar-lead")
      toast.success(`${resposta.excluidos} lead(s) excluído(s) definitivamente.`)
    },
  })

  return {
    atualizarStatusEmLote,
    ignorarEmLote,
    excluirEmLoteDefinitivamente,
  }
}
