import { useEffect, useState } from "react"
import { Copy, MessageCircleReply, Sparkles } from "lucide-react"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useInstagramLeadMutations } from "@/hooks/useInstagramLeadMutations"
import { useClipboard } from "@/hooks/useClipboard"
import { InstagramTagsFollowupForm } from "@/components/instagram/InstagramTagsFollowupForm"
import { InstagramObservacoesForm } from "@/components/instagram/InstagramObservacoesForm"
import { InstagramLeadHistoryAccordion } from "@/components/instagram/InstagramLeadHistoryAccordion"
import { PrioridadeBadge } from "@/components/instagram/PrioridadeBadge"
import { DeleteLeadButton } from "@/components/lead-detail/DeleteLeadButton"
import { TemplateSelector } from "@/components/shared/TemplateSelector"
import { LABEL_STATUS } from "@/lib/constants"
import { formatarTempoRelativo } from "@/lib/formatters"
import { STATUS_VALIDOS, type StatusLead } from "@/types/lead"
import type { LeadInstagram } from "@/types/instagram"

interface InstagramLeadDetailModalProps {
  lead: LeadInstagram | null
  onClose: () => void
}

export function InstagramLeadDetailModal({
  lead,
  onClose,
}: InstagramLeadDetailModalProps) {
  const mutations = useInstagramLeadMutations(lead?.id ?? 0, lead?.post_id ?? 0)
  const { copiado, copiar } = useClipboard()
  const [sugestaoDm, setSugestaoDm] = useState(lead?.sugestao_dm ?? "")

  useEffect(() => {
    setSugestaoDm(lead?.sugestao_dm ?? "")
  }, [lead?.id, lead?.sugestao_dm])

  if (!lead) return null

  const handleGerar = (tipo: "contato" | "followup") => {
    const jaTinhaSugestao = sugestaoDm.trim().length > 0
    mutations.gerarMensagem.mutate(
      { tipo, forcarNova: jaTinhaSugestao },
      {
        onSuccess: (resposta) => {
          setSugestaoDm(resposta.mensagem)
          if (resposta.avisos?.length) {
            toast.warning(
              `${resposta.avisos.join(" ")} (usado: ${resposta.provedor ?? "?"})`
            )
          } else {
            toast.success("Mensagem gerada com sucesso.")
          }
        },
      }
    )
  }

  const handleSalvarSugestaoDm = () => {
    if (sugestaoDm === (lead.sugestao_dm ?? "")) return
    mutations.salvarSugestaoDm.mutate(sugestaoDm)
  }

  return (
    <Dialog open={Boolean(lead)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[88vh] max-w-[calc(100%-2rem)] overflow-y-auto p-0 sm:max-w-3xl">
        <DialogHeader className="border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <DialogTitle>@{lead.username}</DialogTitle>
            <PrioridadeBadge prioridade={lead.prioridade} />
          </div>
          <p className="text-sm text-muted-foreground">
            {lead.full_name || "Sem nome"} · {lead.seguidores ?? 0} seguidores
          </p>
        </DialogHeader>

        <div className="grid gap-6 p-6 md:grid-cols-[minmax(0,320px)_1px_1fr]">
          <div className="space-y-5">
            <div className="space-y-1.5">
              <Select
                value={lead.status}
                onValueChange={(v) => mutations.atualizarStatus.mutate(v as StatusLead)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_VALIDOS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {LABEL_STATUS[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <InstagramTagsFollowupForm
              lead={lead}
              onSalvar={(input) => mutations.salvarTagsFollowup.mutate(input)}
              salvando={mutations.salvarTagsFollowup.isPending}
            />

            <hr className="border-border" />

            <InstagramObservacoesForm
              lead={lead}
              onSalvar={(obs) => mutations.salvarObservacoes.mutate(obs)}
              salvando={mutations.salvarObservacoes.isPending}
            />

            <hr className="border-border" />

            <InstagramLeadHistoryAccordion leadId={lead.id} />
          </div>

          <div className="hidden bg-border md:block" />

          <div className="flex flex-col gap-4">
            {(lead.biography || lead.comentarios.length > 0 || lead.justificativa) && (
              <details className="text-sm">
                <summary className="cursor-pointer select-none text-sm font-medium text-muted-foreground hover:text-foreground">
                  Bio, comentários e detalhes da análise
                </summary>
                <div className="mt-2 flex flex-col gap-3">
                  {lead.biography && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-muted-foreground">
                        Bio
                      </p>
                      <p className="whitespace-pre-line">{lead.biography}</p>
                    </div>
                  )}

                  {lead.comentarios.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-muted-foreground">
                        Comentários
                      </p>
                      <div className="rounded-md bg-muted/40 p-2">
                        {lead.comentarios.map((comentario, i) => (
                          <p key={i} className="whitespace-pre-line">
                            "{comentario}"
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {lead.justificativa && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-muted-foreground">
                        Justificativa da análise
                      </p>
                      <p className="italic">{lead.justificativa}</p>
                    </div>
                  )}
                </div>
              </details>
            )}

            <div className="flex flex-col gap-3 rounded-lg bg-accent/40 p-3">
              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Sugestão de DM
                </p>
                <Textarea
                  value={sugestaoDm}
                  onChange={(e) => setSugestaoDm(e.target.value)}
                  onBlur={handleSalvarSugestaoDm}
                  placeholder="Nenhuma sugestão de DM ainda"
                  className="min-h-[100px] resize-none border-none bg-transparent p-0 shadow-none focus-visible:ring-0"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => handleGerar("contato")}
                    disabled={mutations.gerarMensagem.isPending}
                  >
                    <Sparkles className="size-4" />
                    {mutations.gerarMensagem.isPending
                      ? "Gerando..."
                      : "Gerar copy de contato"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleGerar("followup")}
                    disabled={mutations.gerarMensagem.isPending}
                  >
                    <MessageCircleReply className="size-4" />
                    Gerar copy de follow-up
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-fit"
                    onClick={() => copiar(sugestaoDm)}
                  >
                    <Copy className="size-4" />
                    {copiado ? "Copiado!" : "Copiar sugestão de DM"}
                  </Button>
                </div>
              </div>

              <hr className="border-border/60" />

              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Follow-up
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      mutations.marcarFollowupEnviado.mutate({
                        followUpsEnviadosAnterior: lead.follow_ups_enviados,
                        ultimoFollowupEmAnterior: lead.ultimo_followup_em,
                        proximoFollowupAnterior: lead.proximo_followup,
                      })
                    }
                    disabled={mutations.marcarFollowupEnviado.isPending}
                  >
                    Marquei follow-up
                  </Button>
                  {lead.follow_ups_enviados > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {lead.follow_ups_enviados} follow-up(s) enviado(s)
                      {lead.ultimo_followup_em &&
                        ` · último em ${formatarTempoRelativo(lead.ultimo_followup_em)}`}
                    </p>
                  )}
                </div>
              </div>

              <hr className="border-border/60" />

              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Templates
                </p>
                <TemplateSelector
                  textoAtual={sugestaoDm}
                  onUsarTemplate={setSugestaoDm}
                  nichoSugerido={lead.nicho}
                />
              </div>
            </div>

            <div className="mt-auto pt-2">
              <DeleteLeadButton
                nomeLead={`@${lead.username}`}
                definitivo={lead.status === "ignorado"}
                onConfirmar={() => {
                  if (lead.status === "ignorado") {
                    mutations.excluirDefinitivamente.mutate(undefined, {
                      onSuccess: onClose,
                    })
                  } else {
                    mutations.ignorar.mutate(lead.status, { onSuccess: onClose })
                  }
                }}
              />
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
