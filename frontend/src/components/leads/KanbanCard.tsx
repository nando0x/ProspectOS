import { Archive, Star } from "lucide-react"
import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { formatarNota, followupVencidoOuHoje } from "@/lib/formatters"
import { useLeadMutations } from "@/hooks/useLeadMutations"
import { FollowupBadge } from "@/components/leads/FollowupBadge"
import { LeadDificilBadge } from "@/components/leads/LeadDificilBadge"
import { TagChips } from "@/components/leads/TagChips"
import type { Lead } from "@/types/lead"

interface KanbanCardProps {
  lead: Lead
  onClick: () => void
}

export function KanbanCard({ lead, onClick }: KanbanCardProps) {
  const vencido = followupVencidoOuHoje(lead.proximo_followup)
  const { ignorar } = useLeadMutations(lead.place_id)
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: lead.place_id })

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Translate.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
      }}
      {...attributes}
      {...listeners}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick()
      }}
      aria-label={`Abrir detalhes de ${lead.nome}`}
      className={cn(
        "min-w-0 w-full cursor-grab flex flex-col gap-1.5 rounded-lg border border-border bg-card p-3 text-left text-sm shadow-sm transition-colors hover:bg-accent/40 active:cursor-grabbing",
        vencido && "ring-2 ring-warning"
      )}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <h4 className="min-w-0 flex-1 truncate font-medium leading-snug">{lead.nome}</h4>
        <div className="flex flex-col items-end gap-1">
          {vencido && <FollowupBadge />}
          {lead.lead_dificil && <LeadDificilBadge />}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {lead.categoria || "Sem categoria"}
      </p>
      <TagChips tags={lead.tags} />
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Star className="size-3 fill-warning text-warning" />
        <span>{formatarNota(lead.nota)}</span>
      </div>

      {lead.lead_dificil && (
        <Button
          size="sm"
          variant="outline"
          className="h-7 w-fit border-destructive/40 text-xs text-destructive hover:bg-destructive/10"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation()
            ignorar.mutate(lead.status)
          }}
        >
          <Archive className="size-3.5" />
          Arquivar
        </Button>
      )}
    </div>
  )
}
