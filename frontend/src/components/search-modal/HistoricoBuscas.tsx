import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, ChevronDown, CircleAlert, CircleSlash, History, Loader2 } from "lucide-react"
import { buscaService } from "@/services/buscaService"
import { formatarTempoRelativo } from "@/lib/formatters"
import type { BuscaHistorico } from "@/types/busca"

const ICONE_STATUS: Record<BuscaHistorico["status"], React.ReactNode> = {
  concluido: <CheckCircle2 className="size-3.5 text-success" />,
  erro: <CircleAlert className="size-3.5 text-destructive" />,
  interrompido: <CircleSlash className="size-3.5 text-warning" />,
  rodando: <Loader2 className="size-3.5 animate-spin text-primary" />,
}

/** Últimas buscas do Maps: quando rodou, como terminou e quantos leads saíram -
 * responde "onde eu já busquei?" sem precisar repetir busca. */
export function HistoricoBuscas() {
  const { data } = useQuery({
    queryKey: ["busca-historico"],
    queryFn: buscaService.historico,
  })

  const buscas = data?.buscas ?? []
  if (buscas.length === 0) return null

  return (
    <details className="group rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer items-center justify-between gap-2 px-4 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          <History className="size-4" />
          Histórico de buscas ({buscas.length})
        </span>
        <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <ul className="space-y-1 border-t border-border px-4 py-3">
        {buscas.map((busca) => (
          <li key={busca.id} className="flex items-start gap-2 text-xs">
            <span className="mt-0.5 shrink-0">{ICONE_STATUS[busca.status]}</span>
            <span className="text-muted-foreground">
              <span className="font-medium text-foreground">
                {formatarTempoRelativo(busca.iniciado_em)}
              </span>
              {busca.progresso_total > 0 && ` · ${busca.progresso_total} área(s)`}
              {busca.mensagem ? ` - ${busca.mensagem}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}
