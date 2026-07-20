import { useMemo } from "react"
import { ChevronDown, Lightbulb, MessageSquareQuote, Target } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { montarEstrategia } from "@/lib/estrategia"
import type { Lead } from "@/types/lead"

interface EstrategiaCardProps {
  lead: Lead
}

/** Playbook de venda do lead: cenário, ângulo, ganchos e objeções - calculado
 * na hora a partir da situação do site, reputação e histórico de contato. */
export function EstrategiaCard({ lead }: EstrategiaCardProps) {
  // memoiza: sem isso, recalcula todo o playbook (regex + arrays) a cada render
  // do modal, inclusive enquanto o usuário digita observações/tags
  const estrategia = useMemo(() => montarEstrategia(lead), [lead])

  return (
    <div className="space-y-3 rounded-xl border border-primary/25 bg-primary/[0.04] p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <Target className="size-4 text-primary" />
          Estratégia de abordagem
        </h3>
        <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary">
          {estrategia.cenario}
        </Badge>
      </div>

      <p className="text-sm leading-relaxed">{estrategia.angulo}</p>

      <div>
        <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Lightbulb className="size-3.5" />
          Ganchos para usar
        </p>
        <ul className="space-y-1.5">
          {estrategia.ganchos.map((gancho) => (
            <li key={gancho} className="flex gap-2 text-sm text-muted-foreground">
              <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-primary/60" />
              <span>{gancho}</span>
            </li>
          ))}
        </ul>
      </div>

      <details className="group rounded-lg border border-border bg-card">
        <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-xs font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-1.5">
            <MessageSquareQuote className="size-3.5" />
            Objeções prováveis e como responder
          </span>
          <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <div className="space-y-3 border-t border-border px-3 py-3">
          {estrategia.objecoes.map((item) => (
            <div key={item.objecao} className="space-y-0.5">
              <p className="text-xs font-medium">{item.objecao}</p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {item.resposta}
              </p>
            </div>
          ))}
        </div>
      </details>

      <p className="rounded-lg bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
        <span className="font-semibold text-foreground">Próximo passo: </span>
        {estrategia.proximoPasso}
      </p>
    </div>
  )
}
