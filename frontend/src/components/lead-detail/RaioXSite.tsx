import { Check, ScanSearch, X } from "lucide-react"
import type { Lead } from "@/types/lead"

interface RaioXSiteProps {
  checklist: NonNullable<Lead["site_checklist"]>
}

/** Raio-X do site do lead: o que a página realmente tem e o que falta -
 * extraído do HTML na busca, nada é chute. São os ganchos concretos da venda. */
export function RaioXSite({ checklist }: RaioXSiteProps) {
  return (
    <div className="space-y-2 rounded-xl border border-border bg-card p-4">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <ScanSearch className="size-4 text-primary" />
        Raio-X do site atual
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-success">
            Já tem
          </p>
          {checklist.tem.length === 0 ? (
            <p className="text-xs text-muted-foreground">nada detectado</p>
          ) : (
            <ul className="space-y-1">
              {checklist.tem.map((item) => (
                <li key={item} className="flex items-start gap-1.5 text-xs">
                  <Check className="mt-0.5 size-3 shrink-0 text-success" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-warning">
            Está faltando
          </p>
          {checklist.falta.length === 0 ? (
            <p className="text-xs text-muted-foreground">nada - estrutura completa</p>
          ) : (
            <ul className="space-y-1">
              {checklist.falta.map((item) => (
                <li key={item} className="flex items-start gap-1.5 text-xs">
                  <X className="mt-0.5 size-3 shrink-0 text-warning" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
