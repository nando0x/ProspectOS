import { AlertTriangle, MessageCircle, Radio } from "lucide-react"
import type { EstadoCaptura } from "@/types/conversa"

interface StatusCapturaProps {
  estado: EstadoCaptura | undefined
  onAbrirWhatsapp: () => void
}

/**
 * Três estados possíveis, e nenhum deles é silencioso:
 * lendo (verde) · leitura quebrada (vermelho) · modo manual (neutro).
 *
 * A pergunta que decide não é "estou no Electron?", e sim "existe leitura
 * viva?" - isso cobre também o caso de estar no app com a janela do WhatsApp
 * fechada.
 */
export function StatusCaptura({ estado, onAbrirWhatsapp }: StatusCapturaProps) {
  if (estado?.ativa && estado.seletores_ok) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-success/15 px-2.5 py-1 text-xs font-medium text-success">
        <Radio className="size-3.5 animate-pulse" />
        Lendo a conversa do WhatsApp
      </span>
    )
  }

  if (estado?.ativa && !estado.seletores_ok) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-2.5 text-xs">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
        <p className="text-muted-foreground">
          <span className="font-medium text-destructive">
            Não consegui ler as mensagens do WhatsApp.
          </span>{" "}
          O layout do site deve ter mudado. Registre as mensagens à mão abaixo
          enquanto isso, que a análise continua funcionando igual.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
        <MessageCircle className="size-3.5" />
        Modo manual
      </span>
      <button
        type="button"
        onClick={onAbrirWhatsapp}
        className="text-xs font-medium text-success hover:underline"
      >
        Abrir WhatsApp para conversar
      </button>
    </div>
  )
}
