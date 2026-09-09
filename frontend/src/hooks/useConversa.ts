import { useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { conversaService } from "@/services/conversaService"
import type { AutorMensagem } from "@/types/conversa"

const chaveConversa = (canal: string, leadRef: string) => ["conversa", canal, leadRef]

/** Histórico + última análise. Enquanto a captura do WhatsApp está viva,
 * atualiza a cada 2,5s (mensagem nova pode chegar a qualquer momento); parada,
 * cai pra 20s, porque só o próprio usuário muda algo no modo manual. */
export function useConversa(canal: string, leadRef: string, capturaAtiva: boolean) {
  return useQuery({
    queryKey: chaveConversa(canal, leadRef),
    queryFn: () => conversaService.obter(canal, leadRef),
    refetchInterval: capturaAtiva ? 2500 : 20000,
    refetchIntervalInBackground: true,
  })
}

export function useEstadoCaptura() {
  return useQuery({
    queryKey: ["estado-captura"],
    queryFn: conversaService.estadoCaptura,
    refetchInterval: 5000,
  })
}

/** No app de desktop, a janela do WhatsApp empurra eventos assim que captura
 * algo - isso tira o atraso do polling. No navegador, window.prospectOS não
 * existe e o hook simplesmente não faz nada. */
export function useEventosDoCockpit(canal: string, leadRef: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const ponte = window.prospectOS
    if (!ponte?.aoReceber) return

    const cancelarNovas = ponte.aoReceber("cockpit:mensagens-novas", () => {
      queryClient.invalidateQueries({ queryKey: chaveConversa(canal, leadRef) })
    })
    const cancelarFalha = ponte.aoReceber("cockpit:leitura-falhou", () => {
      queryClient.invalidateQueries({ queryKey: ["estado-captura"] })
    })
    return () => {
      cancelarNovas()
      cancelarFalha()
    }
  }, [canal, leadRef, queryClient])
}

export function useConversaMutations(canal: string, leadRef: string) {
  const queryClient = useQueryClient()
  const invalidar = () =>
    queryClient.invalidateQueries({ queryKey: chaveConversa(canal, leadRef) })

  const adicionarMensagem = useMutation({
    mutationFn: (dados: { autor: AutorMensagem; texto: string }) =>
      conversaService.adicionarMensagem(canal, leadRef, dados),
    onSuccess: invalidar,
    onError: (erro: Error) => toast.error(erro.message),
  })

  const removerMensagem = useMutation({
    mutationFn: (mensagemId: number) =>
      conversaService.removerMensagem(canal, leadRef, mensagemId),
    onSuccess: invalidar,
    onError: (erro: Error) => toast.error(erro.message),
  })

  const analisar = useMutation({
    mutationFn: () => conversaService.analisar(canal, leadRef),
    onSuccess: (analise) => {
      invalidar()
      if (analise.avisos?.length) {
        toast.warning(`${analise.avisos.join(" ")} (usado: ${analise.provedor ?? "?"})`)
      } else {
        toast.success("Conversa analisada.")
      }
    },
    onError: (erro: Error) => toast.error(erro.message),
  })

  return { adicionarMensagem, removerMensagem, analisar }
}
