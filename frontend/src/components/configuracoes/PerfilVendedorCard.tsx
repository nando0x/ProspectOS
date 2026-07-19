import { useEffect, useState } from "react"
import { UserRound } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { usePerfilVendedor, useSalvarPerfilVendedor } from "@/hooks/useConfiguracoes"

/** Perfil de quem envia as mensagens - vira parte do system prompt da IA, então
 * as copies saem assinadas e na voz certa em vez de "vendedor genérico". */
export function PerfilVendedorCard() {
  const { data, isLoading } = usePerfilVendedor()
  const salvar = useSalvarPerfilVendedor()
  const [nome, setNome] = useState("")
  const [apresentacao, setApresentacao] = useState("")
  const [diferencial, setDiferencial] = useState("")

  useEffect(() => {
    if (data) {
      setNome(data.nome)
      setApresentacao(data.apresentacao)
      setDiferencial(data.diferencial)
    }
  }, [data])

  if (isLoading) {
    return <Skeleton className="h-[280px]" />
  }

  return (
    <div className="space-y-4 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <UserRound className="size-4" />
        </div>
        <div>
          <h3 className="text-sm font-medium">Seu perfil de vendedor</h3>
          <p className="text-xs text-muted-foreground">
            A IA usa isso para escrever as mensagens na sua voz, com o seu nome.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="vendedor-nome">Seu nome (como quer aparecer)</Label>
          <Input
            id="vendedor-nome"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Ex.: Fernando"
            maxLength={80}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="vendedor-apresentacao">O que você faz (1 frase)</Label>
          <Textarea
            id="vendedor-apresentacao"
            rows={2}
            value={apresentacao}
            onChange={(e) => setApresentacao(e.target.value)}
            placeholder="Ex.: crio sites profissionais para negócios locais"
            maxLength={300}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="vendedor-diferencial">
            Seu diferencial <span className="text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="vendedor-diferencial"
            rows={2}
            value={diferencial}
            onChange={(e) => setDiferencial(e.target.value)}
            placeholder="Ex.: entrego em até 7 dias, com tudo incluso (textos, fotos e publicação)"
            maxLength={300}
          />
        </div>
      </div>

      <Button
        size="sm"
        onClick={() => salvar.mutate({ nome, apresentacao, diferencial })}
        disabled={salvar.isPending}
      >
        {salvar.isPending ? "Salvando..." : "Salvar perfil"}
      </Button>
    </div>
  )
}
