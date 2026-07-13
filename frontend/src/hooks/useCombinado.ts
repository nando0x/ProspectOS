import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { combinadoService } from "@/services/combinadoService"

export function useMetricasCombinadas() {
  return useQuery({
    queryKey: ["metricas-combinadas"],
    queryFn: combinadoService.metricas,
  })
}

export function useFollowUpsHoje() {
  const query = useQuery({
    queryKey: ["follow-ups-hoje"],
    queryFn: combinadoService.followUpsHoje,
  })

  return { leads: query.data?.leads ?? [], ...query }
}

export function useFunilCombinado() {
  return useQuery({
    queryKey: ["analytics", "funil-combinado"],
    queryFn: combinadoService.funilCombinado,
  })
}

export function usePorNichoCombinado() {
  return useQuery({
    queryKey: ["analytics", "por-nicho-combinado"],
    queryFn: combinadoService.porNichoCombinado,
  })
}

export function useMetaSemanal() {
  return useQuery({
    queryKey: ["meta-semanal"],
    queryFn: combinadoService.metaSemanal,
  })
}

export function useSalvarMetaSemanal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (meta: number) => combinadoService.salvarMetaSemanal(meta),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meta-semanal"] })
      toast.success("Meta semanal salva.")
    },
  })
}
