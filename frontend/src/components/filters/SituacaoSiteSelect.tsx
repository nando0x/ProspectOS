import { SelectComVazio } from "@/components/filters/SelectComVazio"
import type { FiltrosLeads } from "@/types/lead"

interface SituacaoSiteSelectProps {
  valor: FiltrosLeads["site_status"]
  onChange: (valor: FiltrosLeads["site_status"]) => void
}

export function SituacaoSiteSelect({ valor, onChange }: SituacaoSiteSelectProps) {
  return (
    <SelectComVazio
      valor={valor}
      onChange={(v) => onChange(v as FiltrosLeads["site_status"])}
      opcoes={[
        { valor: "sem_site", label: "Sem site" },
        { valor: "site_ruim", label: "Site ruim" },
        { valor: "site_ok", label: "Site ok" },
      ]}
      labelVazio="Qualquer situação"
      placeholder="Situação do site"
      className="w-[170px]"
    />
  )
}
