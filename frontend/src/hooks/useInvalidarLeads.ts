import { useQueryClient } from "@tanstack/react-query"

export function useInvalidarLeads() {
  const queryClient = useQueryClient()

  return () => {
    queryClient.invalidateQueries({ queryKey: ["leads"] })
    queryClient.invalidateQueries({ queryKey: ["metricas"] })
    queryClient.invalidateQueries({ queryKey: ["metricas-combinadas"] })
    queryClient.invalidateQueries({ queryKey: ["follow-ups-hoje"] })
    queryClient.invalidateQueries({ queryKey: ["meta-semanal"] })
  }
}
