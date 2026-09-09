import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ExternalLink, FileDown, Flame, MessagesSquare, RefreshCw } from "lucide-react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useLeadMutations } from "@/hooks/useLeadMutations"
import { formatarNota } from "@/lib/formatters"
import { SiteStatusBadge } from "@/components/leads/SiteStatusBadge"
import { InstagramIcon } from "@/components/icons/InstagramIcon"
import { EstrategiaCard } from "@/components/lead-detail/EstrategiaCard"
import { RaioXSite } from "@/components/lead-detail/RaioXSite"
import { LeadStatusSelect } from "@/components/lead-detail/LeadStatusSelect"
import { LeadTagsFollowupForm } from "@/components/lead-detail/LeadTagsFollowupForm"
import { LeadObservacoesForm } from "@/components/lead-detail/LeadObservacoesForm"
import { LeadMessageGenerator } from "@/components/lead-detail/LeadMessageGenerator"
import { LeadHistoryAccordion } from "@/components/lead-detail/LeadHistoryAccordion"
import { DeleteLeadButton } from "@/components/lead-detail/DeleteLeadButton"
import type { Lead } from "@/types/lead"

interface LeadDetailModalProps {
  lead: Lead | null
  onClose: () => void
}

export function LeadDetailModal({ lead, onClose }: LeadDetailModalProps) {
  const mutations = useLeadMutations(lead?.place_id ?? "")

  if (!lead) return null

  return (
    <Dialog open={Boolean(lead)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-[calc(100%-2rem)] overflow-y-auto p-0 sm:max-w-6xl">
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle>{lead.nome}</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {lead.categoria || "Sem categoria"} · {lead.endereco || "sem endereço"} · nota{" "}
            {formatarNota(lead.nota)}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <SiteStatusBadge
              siteStatus={lead.site_status}
              siteProblemas={lead.site_problemas}
            />
            <span
              className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary"
              title="Score de prioridade"
            >
              <Flame className="size-3" />
              {lead.score}
            </span>
            {lead.site_url && (
              <a
                href={lead.site_url.startsWith("http") ? lead.site_url : `https://${lead.site_url}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                <ExternalLink className="size-3" />
                Ver site atual
              </a>
            )}
            {lead.instagram_url && (
              <a
                href={lead.instagram_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-instagram-mid underline-offset-2 hover:underline"
              >
                <InstagramIcon className="size-3" />
                Instagram do negócio
              </a>
            )}
            <button
              type="button"
              onClick={() => mutations.reanalisarSite.mutate()}
              disabled={mutations.reanalisarSite.isPending}
              title="Re-roda a análise do site agora: status, problemas e raio-X atualizados na hora"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:opacity-60"
            >
              <RefreshCw
                className={cn("size-3", mutations.reanalisarSite.isPending && "animate-spin")}
              />
              {mutations.reanalisarSite.isPending ? "Reanalisando..." : "Reanalisar site"}
            </button>

            <Link
              to={`/conversas/${encodeURIComponent(lead.place_id)}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-success underline-offset-2 hover:underline"
            >
              <MessagesSquare className="size-3.5" />
              Cockpit de conversa
            </Link>
          </div>
        </DialogHeader>

        <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,320px)_1px_1fr]">
          <div className="space-y-5">
            <LeadStatusSelect
              status={lead.status}
              onChange={(status) => mutations.atualizarStatus.mutate(status)}
            />

            <LeadTagsFollowupForm
              lead={lead}
              onSalvar={(input) => mutations.salvarTagsFollowup.mutate(input)}
              salvando={mutations.salvarTagsFollowup.isPending}
            />

            <hr className="border-border" />

            <LeadObservacoesForm
              lead={lead}
              onSalvar={(obs) => mutations.salvarObservacoes.mutate(obs)}
              salvando={mutations.salvarObservacoes.isPending}
            />

            <hr className="border-border" />

            <LeadHistoryAccordion placeId={lead.place_id} />
          </div>

          <div className="hidden bg-border lg:block" />

          {/* Em telas largas, a área de trabalho vira duas colunas:
              estratégia + raio-X | mensagem + ações */}
          <div className="grid min-w-0 gap-5 xl:grid-cols-2 xl:items-start">
            <div className="min-w-0 space-y-5">
              <EstrategiaCard lead={lead} />

              {lead.site_checklist && <RaioXSite checklist={lead.site_checklist} />}
            </div>

            <div className="flex min-w-0 flex-col gap-4">
              <LeadMessageGenerator
                lead={lead}
                gerarMensagem={mutations.gerarMensagem}
                marcarFollowupEnviado={mutations.marcarFollowupEnviado}
              />

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                <Button
                  size="sm"
                  variant="outline"
                  asChild
                  title={
                    lead.site_status === "site_ruim"
                      ? "Gera o PDF com os problemas do site em linguagem simples + nota do Google PageSpeed (pode levar ~30s)"
                      : "Gera o PDF mostrando o que a ausência de site está custando"
                  }
                >
                  <a href={`/api/leads/${encodeURIComponent(lead.place_id)}/diagnostico.pdf`}>
                    <FileDown className="size-4" />
                    Baixar diagnóstico (PDF)
                  </a>
                </Button>

                <DeleteLeadButton
                  nomeLead={lead.nome}
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
        </div>
      </DialogContent>
    </Dialog>
  )
}
