import { Loader2 } from "lucide-react"
import type { EstadoBusca } from "@/types/busca"

interface BuscaProgressProps {
  estado: EstadoBusca
}

function rotuloEtapa(etapa: EstadoBusca["etapa"]): string | null {
  if (etapa === "scraping") return "Capturando no Google Maps…"
  if (etapa === "verificando_sites") return "Analisando sites…"
  return null
}

export function BuscaProgress({ estado }: BuscaProgressProps) {
  const temContagem = estado.empresas_encontradas > 0
  const indeterminado = estado.rodando && !temContagem
  const percentual = temContagem
    ? Math.min(
        100,
        Math.round(
          (estado.empresas_processadas / estado.empresas_encontradas) * 100
        )
      )
    : 0
  const etapaLabel = rotuloEtapa(estado.etapa)

  return (
    <div className="space-y-2 rounded-lg border border-border bg-muted/40 p-3">
      <div className="flex items-center gap-2 text-sm">
        <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
        <div className="min-w-0 flex-1">
          {etapaLabel && (
            <p className="font-medium text-foreground">{etapaLabel}</p>
          )}
          <p className={etapaLabel ? "text-xs text-muted-foreground" : undefined}>
            {estado.mensagem}
          </p>
        </div>
        {estado.total_areas > 0 && estado.area_atual > 0 && (
          <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium tabular-nums text-primary">
            Área {estado.area_atual}/{estado.total_areas}
          </span>
        )}
      </div>

      {temContagem && (
        <p className="text-xs text-muted-foreground tabular-nums">
          {estado.etapa === "verificando_sites"
            ? `Analisadas ${estado.empresas_processadas} de ${estado.empresas_encontradas}`
            : `Capturadas ${estado.empresas_encontradas} empresa(s)`}
        </p>
      )}

      <div className="h-2 overflow-hidden rounded-full bg-border">
        {indeterminado ? (
          <div className="h-full w-[30%] animate-[deslizar_1.2s_ease-in-out_infinite] rounded-full bg-primary" />
        ) : (
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${percentual}%` }}
          />
        )}
      </div>
    </div>
  )
}
