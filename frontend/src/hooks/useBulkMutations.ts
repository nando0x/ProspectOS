import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { leadsService } from "@/services/leadsService"
import { useInvalidarLeads } from "@/hooks/useInvalidarLeads"
import { tocarSom } from "@/hooks/useSom"
import type { StatusLead } from "@/types/lead"

export function useBulkMutations() {
  const invalidarListaEMetricas = useInvalidarLeads()

  const atualizarStatusEmLote = useMutation({
    mutationFn: (input: { placeIds: string[]; status: StatusLead }) =>
      leadsService.atualizarStatusEmLote(input.placeIds, input.status),
    onSuccess: (resposta) => {
      invalidarListaEMetricas()
      toast.success(`${resposta.atualizados} lead(s) atualizado(s).`)
    },
  })

  const ignorarEmLote = useMutation({
    mutationFn: (placeIds: string[]) => leadsService.ignorarEmLote(placeIds),
    onSuccess: (resposta) => {
      invalidarListaEMetricas()
      toast.success(`${resposta.atualizados} lead(s) ignorado(s).`)
    },
  })

  const excluirEmLoteDefinitivamente = useMutation({
    mutationFn: (placeIds: string[]) =>
      leadsService.excluirEmLoteDefinitivamente(placeIds),
    onSuccess: (resposta) => {
      invalidarListaEMetricas()
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
