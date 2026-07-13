import type { OrdenacaoPrioridade } from "@/lib/constants"
import { SelectComVazio } from "@/components/filters/SelectComVazio"

interface OrdenacaoPrioridadeSelectProps {
  valor: OrdenacaoPrioridade
  onChange: (valor: OrdenacaoPrioridade) => void
}

export function OrdenacaoPrioridadeSelect({
  valor,
  onChange,
}: OrdenacaoPrioridadeSelectProps) {
  return (
    <SelectComVazio
      valor={valor}
      onChange={(v) => onChange(v as OrdenacaoPrioridade)}
      opcoes={[
        { valor: "prioridade-desc", label: "Maior prioridade primeiro" },
        { valor: "prioridade-asc", label: "Menor prioridade primeiro" },
      ]}
      labelVazio="Ordem padrão"
      placeholder="Ordenar"
      className="w-[190px]"
    />
  )
}
