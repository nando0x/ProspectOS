import { Link } from "react-router-dom"
import { Clock } from "lucide-react"
import { StatTile } from "@/components/dashboard/StatTile"
import { Skeleton } from "@/components/ui/skeleton"
import { MetaSemanalCard } from "@/components/dashboard/MetaSemanalCard"
import { useFollowUpsHoje, useMetricasCombinadas } from "@/hooks/useCombinado"
import { LABEL_STATUS } from "@/lib/constants"
import { formatarTempoRelativo } from "@/lib/formatters"

export function VisaoGeralCombinada() {
  const { data: metricas, isLoading } = useMetricasCombinadas()
  const { leads: followUps, isLoading: carregandoFollowUps } =
    useFollowUpsHoje()

  if (isLoading || !metricas) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-[74px]" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <MetaSemanalCard />

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          Visão geral (Google Maps + Instagram)
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
          <StatTile rotulo="Leads ativos" valor={metricas.total} />
          <StatTile rotulo="Ativos no Maps" valor={metricas.maps.total} />
          <StatTile rotulo="Ativos no Instagram" valor={metricas.instagram.total} />
          <StatTile
            rotulo="Contatados"
            valor={metricas.por_status.contatado ?? 0}
          />
          <StatTile
            rotulo="Fechados"
            valor={metricas.por_status.fechou ?? 0}
            variante="destaque"
          />
          <StatTile
            rotulo="Taxa de conversão"
            valor={`${metricas.taxa_conversao}%`}
            variante="destaque"
          />
          <StatTile
            rotulo="Follow-ups p/ hoje"
            valor={metricas.lembretes_hoje}
            variante={metricas.lembretes_hoje > 0 ? "alerta" : "default"}
          />
        </div>
      </div>

      {!carregandoFollowUps && followUps.length > 0 && (
        <div className="rounded-xl border border-warning/40 bg-warning/10 p-4">
          <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium">
            <Clock className="size-4 text-warning" />
            Follow-ups de hoje ({followUps.length})
          </h3>
          <div className="space-y-2">
            {followUps.map((lead) => (
              <div
                key={`${lead.canal}-${lead.place_id}`}
                className="flex items-center justify-between gap-2 rounded-lg bg-card px-3 py-2 text-sm"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{lead.titulo}</p>
                  <p className="text-xs text-muted-foreground">
                    {lead.canal === "maps" ? "Google Maps" : "Instagram"} ·{" "}
                    {LABEL_STATUS[lead.status]} ·{" "}
                    {formatarTempoRelativo(lead.proximo_followup) === "hoje"
                      ? "vence hoje"
                      : `venceu ${formatarTempoRelativo(lead.proximo_followup)}`}
                  </p>
                </div>
                <Link
                  to={lead.canal === "maps" ? "/leads" : "/instagram"}
                  className="shrink-0 text-xs font-medium text-primary hover:underline"
                >
                  Abrir
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
