import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { tarefasService } from "@/services/tarefasService"
import { leadsService } from "@/services/leadsService"
import { instagramService } from "@/services/instagramService"
import { tocarSom } from "@/hooks/useSom"
import { useInvalidarLeads } from "@/hooks/useInvalidarLeads"
import type { TarefaFollowup } from "@/types/tarefas"

export function useTarefasHoje() {
  const queryClient = useQueryClient()
  const invalidarLeads = useInvalidarLeads()

  const tarefas = useQuery({
    queryKey: ["tarefas-hoje"],
    queryFn: tarefasService.tarefasHoje,
  })

  const invalidar = () => {
    invalidarLeads()
    queryClient.invalidateQueries({ queryKey: ["tarefas-hoje"] })
    queryClient.invalidateQueries({ queryKey: ["instagram-posts"] })
  }

  const marcarFollowupEnviado = useMutation({
    mutationFn: (tarefa: TarefaFollowup) =>
      tarefa.canal === "maps"
        ? leadsService.marcarFollowupEnviado(String(tarefa.id))
        : instagramService.marcarFollowupEnviado(Number(tarefa.id)),
    onSuccess: (resposta) => {
      invalidar()
      tocarSom("followup-marcado")
      toast.success(
        `Follow-up registrado. Próximo sugerido: ${resposta.proximo_followup_sugerido}`
      )
    },
  })

  const marcarContatado = useMutation({
    mutationFn: (placeId: string) => leadsService.atualizarStatus(placeId, "contatado"),
    onSuccess: () => {
      invalidar()
      tocarSom("card-movido")
      toast.success("Lead marcado como contatado.")
    },
  })

  return { tarefas, marcarFollowupEnviado, marcarContatado }
}
