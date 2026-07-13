import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { useLeadHistorico } from "@/hooks/useLeadHistorico"
import { formatarTempoRelativo } from "@/lib/formatters"
import { LABEL_STATUS } from "@/lib/constants"

interface LeadHistoryAccordionProps {
  placeId: string
}

export function LeadHistoryAccordion({ placeId }: LeadHistoryAccordionProps) {
  return (
    <Accordion type="single" collapsible>
      <AccordionItem value="historico">
        <AccordionTrigger className="text-sm">
          Histórico de status
        </AccordionTrigger>
        <AccordionContent>
          <HistoricoConteudo placeId={placeId} />
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}

function HistoricoConteudo({ placeId }: { placeId: string }) {
  const { data: historico, isLoading } = useLeadHistorico(placeId, true)

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Carregando...</p>
  }

  if (!historico || historico.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nenhuma mudança de status registrada ainda.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      {historico.map((item, i) => (
        <div key={i} className="text-sm">
          <span className="text-muted-foreground">
            {item.status_anterior ? LABEL_STATUS[item.status_anterior] : "—"}
          </span>
          {" → "}
          <span className="font-medium">{LABEL_STATUS[item.status_novo]}</span>
          <span className="ml-2 text-xs text-muted-foreground">
            {formatarTempoRelativo(item.alterado_em)}
          </span>
        </div>
      ))}
    </div>
  )
}
