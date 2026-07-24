import { useMemo, useState } from "react"
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core"
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable"
import { useDroppable } from "@dnd-kit/core"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { LABEL_STATUS, COR_STATUS } from "@/lib/constants"
import { KanbanCard } from "@/components/leads/KanbanCard"
import { leadsService } from "@/services/leadsService"
import { useInvalidarLeads } from "@/hooks/useInvalidarLeads"
import { tocarSom } from "@/hooks/useSom"
import type { Lead, StatusLead } from "@/types/lead"

const COLUNAS_FUNIL: StatusLead[] = ["novo", "contatado", "respondeu", "fechou"]

interface KanbanColunaProps {
  status: StatusLead
  leads: Lead[]
  onSelecionarLead: (lead: Lead) => void
}

function KanbanColuna({ status, leads, onSelecionarLead }: KanbanColunaProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status })

  return (
    <div
      className={cn(
        "flex h-[70vh] max-h-[720px] min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-muted/20 transition-colors",
        isOver && "bg-accent/40 ring-2 ring-primary/50"
      )}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border/60 px-3 py-2">
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
            COR_STATUS[status]
          )}
        >
          {LABEL_STATUS[status]}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {leads.length}
        </span>
      </div>

      <SortableContext
        items={leads.map((l) => l.place_id)}
        strategy={verticalListSortingStrategy}
      >
        <div
          ref={setNodeRef}
          className="flex min-h-0 flex-1 flex-col gap-2 overflow-x-hidden overflow-y-auto p-2.5"
        >
          {leads.map((lead) => (
            <KanbanCard
              key={lead.place_id}
              lead={lead}
              onClick={() => onSelecionarLead(lead)}
            />
          ))}
        </div>
      </SortableContext>
    </div>
  )
}

interface KanbanBoardProps {
  leads: Lead[]
  onSelecionarLead: (lead: Lead) => void
}

export function KanbanBoard({ leads, onSelecionarLead }: KanbanBoardProps) {
  const invalidarListaEMetricas = useInvalidarLeads()
  const [leadArrastado, setLeadArrastado] = useState<Lead | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  const leadsPorStatus = useMemo(() => {
    const grupos: Record<string, Lead[]> = {}
    for (const status of COLUNAS_FUNIL) grupos[status] = []
    for (const lead of leads) {
      if (grupos[lead.status]) grupos[lead.status].push(lead)
    }
    return grupos
  }, [leads])

  const handleDragStart = (event: DragStartEvent) => {
    const lead = leads.find((l) => l.place_id === event.active.id)
    setLeadArrastado(lead ?? null)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    setLeadArrastado(null)
    const { active, over } = event
    if (!over) return

    const lead = leads.find((l) => l.place_id === active.id)
    if (!lead) return

    const novoStatus = COLUNAS_FUNIL.includes(over.id as StatusLead)
      ? (over.id as StatusLead)
      : leads.find((l) => l.place_id === over.id)?.status

    if (!novoStatus || novoStatus === lead.status) return

    leadsService.atualizarStatus(lead.place_id, novoStatus).then(
      () => {
        invalidarListaEMetricas()
        tocarSom(novoStatus === "fechou" ? "lead-fechou" : "card-movido")
        toast.success(`Movido para ${LABEL_STATUS[novoStatus]}.`)
      },
      () => toast.error("Não foi possível mover o lead. Tente novamente.")
    )
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {COLUNAS_FUNIL.map((status) => (
          <KanbanColuna
            key={status}
            status={status}
            leads={leadsPorStatus[status]}
            onSelecionarLead={onSelecionarLead}
          />
        ))}
      </div>

      <DragOverlay>
        {leadArrastado && (
          <KanbanCard lead={leadArrastado} onClick={() => {}} />
        )}
      </DragOverlay>
    </DndContext>
  )
}
