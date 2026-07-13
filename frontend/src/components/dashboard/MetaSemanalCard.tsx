import { useState } from "react"
import { Pencil, Target } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { useMetaSemanal, useSalvarMetaSemanal } from "@/hooks/useCombinado"
import { cn } from "@/lib/utils"

export function MetaSemanalCard() {
  const { data: meta, isLoading } = useMetaSemanal()
  const salvar = useSalvarMetaSemanal()
  const [editando, setEditando] = useState(false)
  const [valor, setValor] = useState("")

  if (isLoading || !meta) return null

  const handleSalvar = () => {
    const numero = Number(valor)
    if (!Number.isFinite(numero) || numero < 0) return
    salvar.mutate(numero, { onSuccess: () => setEditando(false) })
  }

  if (meta.meta === 0 && !editando) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-border bg-muted/20 p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Target className="size-4" />
          Configure uma meta semanal de leads contatados para acompanhar seu
          progresso aqui.
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setValor("")
            setEditando(true)
          }}
        >
          Configurar meta
        </Button>
      </div>
    )
  }

  if (editando) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-4">
        <Target className="size-4 shrink-0 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">
          Meta semanal de leads contatados:
        </span>
        <Input
          type="number"
          min={0}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSalvar()}
          placeholder={String(meta.meta || 100)}
          className="h-8 w-24 [appearance:textfield] focus-visible:border-input focus-visible:ring-1 focus-visible:ring-border [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          autoFocus
        />
        <Button
          size="sm"
          variant="outline"
          disabled={salvar.isPending}
          onClick={handleSalvar}
        >
          {salvar.isPending ? "Salvando..." : "Salvar"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setEditando(false)}>
          Cancelar
        </Button>
      </div>
    )
  }

  const atingiu = meta.progresso >= meta.meta

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Target className="size-4 text-muted-foreground" />
          Meta semanal: {meta.progresso}/{meta.meta} contatados
          {atingiu && " 🎉"}
        </div>
        <button
          type="button"
          onClick={() => {
            setValor(String(meta.meta))
            setEditando(true)
          }}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <Pencil className="size-3" />
          Editar
        </button>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            atingiu ? "bg-success" : "bg-primary"
          )}
          style={{ width: `${Math.min(meta.porcentagem, 100)}%` }}
        />
      </div>

      <p className="mt-1.5 text-xs text-muted-foreground">
        {atingiu
          ? "Meta batida essa semana!"
          : `Faltam ${meta.faltam} para bater a meta desta semana.`}
      </p>
    </div>
  )
}
