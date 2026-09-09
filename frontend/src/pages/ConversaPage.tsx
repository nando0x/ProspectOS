import { useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, Copy, MessageCircle, Send } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { Header } from "@/components/layout/Header"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { AnaliseConversaCard } from "@/components/conversa/AnaliseConversaCard"
import { StatusCaptura } from "@/components/conversa/StatusCaptura"
import { ThreadConversa } from "@/components/conversa/ThreadConversa"
import { httpClient } from "@/services/httpClient"
import { conversaService } from "@/services/conversaService"
import { linkWhatsappComMensagem } from "@/services/tarefasService"
import { useClipboard } from "@/hooks/useClipboard"
import {
  useConversa,
  useConversaMutations,
  useEstadoCaptura,
  useEventosDoCockpit,
} from "@/hooks/useConversa"
import { cn } from "@/lib/utils"
import type { Lead } from "@/types/lead"

const CANAL = "maps"

export function ConversaPage() {
  const { placeId = "" } = useParams()
  const [rascunho, setRascunho] = useState("")
  const [autorManual, setAutorManual] = useState<"lead" | "vendedor">("lead")
  const composerRef = useRef<HTMLTextAreaElement>(null)

  const { data: lead } = useQuery({
    queryKey: ["lead", placeId],
    queryFn: () => httpClient.get<Lead>(`/api/leads/${encodeURIComponent(placeId)}`),
    enabled: Boolean(placeId),
  })

  const { data: captura } = useEstadoCaptura()
  const capturaAtiva = Boolean(captura?.ativa)
  const { data, isLoading } = useConversa(CANAL, placeId, capturaAtiva)
  const { adicionarMensagem, removerMensagem, analisar } = useConversaMutations(CANAL, placeId)
  useEventosDoCockpit(CANAL, placeId)

  const { copiado, copiar } = useClipboard()
  const mensagens = useMemo(() => data?.mensagens ?? [], [data])

  // registra de quem é a conversa antes de qualquer captura chegar
  useEffect(() => {
    if (placeId) conversaService.registrarLeadAtivo(CANAL, placeId).catch(() => {})
  }, [placeId])

  const abrirWhatsapp = () => {
    if (!lead?.whatsapp_link) {
      toast.error("Este lead não tem WhatsApp cadastrado.")
      return
    }
    conversaService.registrarLeadAtivo(CANAL, placeId).catch(() => {})
    window.open(linkWhatsappComMensagem(lead.whatsapp_link, rascunho || null), "_blank")
  }

  const registrarNoHistorico = () => {
    const texto = rascunho.trim()
    if (!texto) return
    adicionarMensagem.mutate(
      { autor: autorManual, texto },
      { onSuccess: () => setRascunho("") }
    )
  }

  const usarResposta = (texto: string) => {
    setRascunho(texto)
    setAutorManual("vendedor")
    composerRef.current?.focus()
  }

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <Header />

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-3 overflow-hidden px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <Link
              to="/leads"
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-4" />
              Voltar para os leads
            </Link>
            <h1 className="truncate text-xl font-semibold tracking-tight">
              {lead?.nome ?? "Conversa"}
            </h1>
            {lead?.telefone && (
              <p className="text-sm text-muted-foreground">
                {lead.categoria} · {lead.telefone}
              </p>
            )}
          </div>
          <StatusCaptura estado={captura} onAbrirWhatsapp={abrirWhatsapp} />
        </div>

        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
          {/* Conversa */}
          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
            <div className="min-h-0 flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="space-y-3 p-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-16" />
                  ))}
                </div>
              ) : (
                <ThreadConversa
                  mensagens={mensagens}
                  onRemover={(id) => removerMensagem.mutate(id)}
                />
              )}
            </div>

            {/* Composer: nada sai daqui sem você mandar. */}
            <div className="border-t border-border p-3">
              <div className="mb-2 flex items-center gap-1 text-xs">
                <span className="text-muted-foreground">Registrar como:</span>
                {(["lead", "vendedor"] as const).map((autor) => (
                  <button
                    key={autor}
                    type="button"
                    onClick={() => setAutorManual(autor)}
                    className={cn(
                      "rounded-full px-2.5 py-0.5 font-medium transition-colors",
                      autorManual === autor
                        ? "bg-primary/15 text-primary"
                        : "text-muted-foreground hover:bg-muted"
                    )}
                  >
                    {autor === "lead" ? "Resposta do lead" : "Minha mensagem"}
                  </button>
                ))}
              </div>

              <Textarea
                ref={composerRef}
                value={rascunho}
                onChange={(e) => setRascunho(e.target.value)}
                placeholder="Escreva ou cole a mensagem aqui..."
                className="min-h-[76px] resize-none"
              />

              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={abrirWhatsapp}
                  disabled={!lead?.whatsapp_link}
                  className="bg-success text-white hover:bg-success/90"
                >
                  <MessageCircle className="size-4" />
                  Abrir no WhatsApp
                </Button>
                <Button size="sm" variant="outline" onClick={() => copiar(rascunho)} disabled={!rascunho.trim()}>
                  <Copy className="size-4" />
                  {copiado ? "Copiado!" : "Copiar"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={registrarNoHistorico}
                  disabled={!rascunho.trim() || adicionarMensagem.isPending}
                >
                  <Send className="size-4" />
                  Registrar no histórico
                </Button>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                O ProspectOS nunca envia mensagem sozinho: você revisa e envia pelo
                WhatsApp.
              </p>
            </div>
          </section>

          {/* Análise */}
          <aside className="min-h-0 overflow-hidden rounded-xl border border-border bg-card">
            <AnaliseConversaCard
              analise={data?.analise ?? null}
              analisando={analisar.isPending}
              temMensagens={mensagens.length > 0}
              onAnalisar={() => analisar.mutate()}
              onUsarResposta={usarResposta}
            />
          </aside>
        </div>
      </main>
    </div>
  )
}
