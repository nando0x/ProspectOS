import { useEffect, useState } from "react"
import { AnimatePresence } from "framer-motion"
import { LayoutGrid, List, Loader2, Trash2 } from "lucide-react"
import { useLeads } from "@/hooks/useLeads"
import { useSelecaoLeads } from "@/hooks/useSelecaoLeads"
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver"
import { useBulkMutations } from "@/hooks/useBulkMutations"
import { LeadCard } from "@/components/leads/LeadCard"
import { EmptyState } from "@/components/leads/EmptyState"
import { BulkActionsBar } from "@/components/leads/BulkActionsBar"
import { KanbanBoard } from "@/components/leads/KanbanBoard"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { cn } from "@/lib/utils"
import type { FiltrosLeads, Lead } from "@/types/lead"

interface LeadGridProps {
  filtros: FiltrosLeads
  filtrosEmUso: boolean
  onLimparFiltros: () => void
  onSelecionarLead: (lead: Lead) => void
  onNovaBusca?: () => void
}

export function LeadGrid({
  filtros,
  filtrosEmUso,
  onLimparFiltros,
  onSelecionarLead,
  onNovaBusca,
}: LeadGridProps) {
  const [visualizacao, setVisualizacao] = useState<"lista" | "kanban">("lista")

  // Kanban precisa de todos os status do funil — não aplica filtro de status
  const filtrosEfetivos: FiltrosLeads =
    visualizacao === "kanban" ? { ...filtros, status: "" } : filtros

  const { leads, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useLeads(filtrosEfetivos)
  const { selecionados, alternar, limpar, quantidade } = useSelecaoLeads(
    JSON.stringify(filtrosEfetivos)
  )
  const { excluirEmLoteDefinitivamente } = useBulkMutations()
  const modoIgnorados = filtros.status === "ignorado"

  const sentinelaRef = useIntersectionObserver(
    () => fetchNextPage(),
    visualizacao === "lista" && Boolean(hasNextPage) && !isFetchingNextPage
  )

  useEffect(() => {
    if (visualizacao === "kanban" && hasNextPage && !isFetchingNextPage) {
      void fetchNextPage()
    }
  }, [visualizacao, hasNextPage, isFetchingNextPage, fetchNextPage])

  const kanbanCarregando =
    visualizacao === "kanban" && (isLoading || hasNextPage || isFetchingNextPage)

  const leadsForaDoFunil = leads.filter((l) =>
    ["recusou", "ignorado"].includes(l.status)
  ).length
  const leadsNoFunil = leads.length - leadsForaDoFunil

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {visualizacao === "kanban" ? (
            kanbanCarregando ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                Carregando leads do Kanban…
              </>
            ) : (
              `${leadsNoFunil} lead(s) no funil`
            )
          ) : isLoading ? (
            "Carregando…"
          ) : (
            `${leads.length} lead(s) carregado(s)`
          )}
        </p>

        <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn("h-7 px-2", visualizacao === "lista" && "bg-accent")}
            onClick={() => setVisualizacao("lista")}
          >
            <List className="size-3.5" />
            Lista
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn("h-7 px-2", visualizacao === "kanban" && "bg-accent")}
            onClick={() => setVisualizacao("kanban")}
          >
            <LayoutGrid className="size-3.5" />
            Kanban
          </Button>
        </div>

        {modoIgnorados && visualizacao === "lista" && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="size-4" />
                Esvaziar ignorados
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  Excluir todos os {leads.length} lead(s) ignorado(s)?
                </AlertDialogTitle>
                <AlertDialogDescription>
                  Isso apaga de vez todos os leads ignorados carregados nesta
                  lista. Não tem como desfazer, e se a mesma busca rodar de
                  novo no futuro, eles podem voltar a aparecer como leads
                  novos.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() =>
                    excluirEmLoteDefinitivamente.mutate(
                      leads.map((l) => l.place_id)
                    )
                  }
                >
                  Excluir todos
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>

      {isLoading && leads.length === 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[150px]" />
          ))}
        </div>
      ) : leads.length === 0 ? (
        <EmptyState
          filtrosEmUso={filtrosEmUso}
          onLimparFiltros={onLimparFiltros}
          onNovaBusca={onNovaBusca}
        />
      ) : visualizacao === "kanban" ? (
        <>
          <KanbanBoard leads={leads} onSelecionarLead={onSelecionarLead} />
          {leadsForaDoFunil > 0 && (
            <p className="text-xs text-muted-foreground">
              {leadsForaDoFunil} lead(s) recusado(s)/ignorado(s) não aparecem
              no Kanban — use a visualização em Lista para vê-los.
            </p>
          )}
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {leads.map((lead) => (
              <LeadCard
                key={lead.place_id}
                lead={lead}
                onClick={() => onSelecionarLead(lead)}
                selecionado={selecionados.has(lead.place_id)}
                onAlternarSelecao={() => alternar(lead.place_id)}
              />
            ))}
          </div>
          {hasNextPage && (
            <div ref={sentinelaRef} className="flex justify-center py-6">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          )}
        </>
      )}

      <AnimatePresence>
        {quantidade > 0 && visualizacao === "lista" && (
          <BulkActionsBar
            placeIdsSelecionados={Array.from(selecionados)}
            onLimparSelecao={limpar}
            modoIgnorados={modoIgnorados}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
