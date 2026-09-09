import { useEffect, useRef } from "react"
import { Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { MensagemConversa } from "@/types/conversa"

interface ThreadConversaProps {
  mensagens: MensagemConversa[]
  onRemover: (id: number) => void
}

function formatarDia(iso: string) {
  const data = new Date(iso)
  if (Number.isNaN(data.getTime())) return ""
  const hoje = new Date()
  const ehHoje = data.toDateString() === hoje.toDateString()
  return ehHoje
    ? "Hoje"
    : data.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" })
}

function formatarHora(iso: string) {
  const data = new Date(iso)
  return Number.isNaN(data.getTime())
    ? ""
    : data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
}

export function ThreadConversa({ mensagens, onRemover }: ThreadConversaProps) {
  const fimRef = useRef<HTMLDivElement>(null)

  // rola pro fim quando chega mensagem nova (comportamento esperado de chat)
  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [mensagens.length])

  if (!mensagens.length) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <p className="max-w-sm text-sm text-muted-foreground">
          Nenhuma mensagem ainda. Abra o WhatsApp para conversar (as mensagens
          aparecem aqui automaticamente) ou registre à mão o que já foi trocado.
        </p>
      </div>
    )
  }

  let diaAnterior = ""

  return (
    <div className="flex flex-col gap-3 p-4">
      {mensagens.map((mensagem) => {
        const dia = formatarDia(mensagem.enviada_em)
        const mostrarSeparador = dia !== diaAnterior
        diaAnterior = dia
        const souEu = mensagem.autor === "vendedor"

        return (
          <div key={mensagem.id}>
            {mostrarSeparador && dia && (
              <div className="my-3 flex items-center gap-3">
                <div className="h-px flex-1 bg-border" />
                <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {dia}
                </span>
                <div className="h-px flex-1 bg-border" />
              </div>
            )}

            <div className={cn("group flex", souEu ? "justify-end" : "justify-start")}>
              <div className={cn("flex max-w-[78%] items-end gap-1.5", souEu && "flex-row-reverse")}>
                <div
                  className={cn(
                    "rounded-2xl px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words",
                    souEu
                      ? "rounded-br-sm bg-primary text-primary-foreground"
                      : "rounded-bl-sm bg-muted text-foreground"
                  )}
                >
                  {mensagem.texto}
                  <span
                    className={cn(
                      "mt-1 block text-[10px] tabular-nums",
                      souEu ? "text-primary-foreground/70" : "text-muted-foreground"
                    )}
                  >
                    {formatarHora(mensagem.enviada_em)}
                    {mensagem.origem === "manual" && " · registrada à mão"}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => onRemover(mensagem.id)}
                  aria-label="Remover mensagem do histórico"
                  className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          </div>
        )
      })}
      <div ref={fimRef} />
    </div>
  )
}
