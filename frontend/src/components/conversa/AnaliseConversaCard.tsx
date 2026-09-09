import { AlertTriangle, Sparkles, Target } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { COR_ESTAGIO, LABEL_ESTAGIO, type AnaliseConversa } from "@/types/conversa"

interface AnaliseConversaCardProps {
  analise: AnaliseConversa | null
  analisando: boolean
  temMensagens: boolean
  onAnalisar: () => void
  onUsarResposta: (texto: string) => void
}

export function AnaliseConversaCard({
  analise,
  analisando,
  temMensagens,
  onAnalisar,
  onUsarResposta,
}: AnaliseConversaCardProps) {
  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="flex items-center gap-2 font-semibold">
          <Sparkles className="size-4 text-success" />
          Sugestão da negociação
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          A IA lê a conversa e sugere o próximo passo. Você revisa e envia.
        </p>
      </div>

      <Button onClick={onAnalisar} disabled={analisando || !temMensagens} className="w-full">
        <Sparkles className="size-4" />
        {analisando ? "Analisando..." : "Analisar conversa"}
      </Button>

      {!temMensagens && (
        <p className="text-xs text-muted-foreground">
          Registre ao menos uma mensagem para a IA ter o que analisar.
        </p>
      )}

      {analise && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-medium",
                COR_ESTAGIO[analise.estagio]
              )}
            >
              {LABEL_ESTAGIO[analise.estagio]}
            </span>
            {analise.mensagens_consideradas ? (
              <span className="text-[11px] text-muted-foreground">
                com base em {analise.mensagens_consideradas} mensagem(ns)
              </span>
            ) : null}
          </div>

          {analise.leitura && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Leitura
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed">{analise.leitura}</p>
            </div>
          )}

          {analise.objetivo && (
            <div className="rounded-lg border-l-2 border-info bg-info/5 p-3">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-info">
                <Target className="size-3.5" />
                Próximo objetivo
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed">{analise.objetivo}</p>
            </div>
          )}

          {analise.resposta_sugerida && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Resposta sugerida
              </h3>
              <p className="mt-1.5 whitespace-pre-wrap rounded-lg bg-muted/50 p-3 text-sm leading-relaxed">
                {analise.resposta_sugerida}
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-2 w-full"
                onClick={() => onUsarResposta(analise.resposta_sugerida)}
              >
                Usar no campo de mensagem
              </Button>
            </div>
          )}

          {analise.evitar.length > 0 && (
            <div>
              <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-warning">
                <AlertTriangle className="size-3.5" />
                Evite agora
              </h3>
              <ul className="mt-1.5 space-y-1">
                {analise.evitar.map((item) => (
                  <li key={item} className="flex gap-2 text-sm text-muted-foreground">
                    <span className="text-warning">•</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
