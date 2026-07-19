import { useEffect, useMemo, useState } from "react"
import {
  Archive,
  ArrowLeft,
  Check,
  ExternalLink,
  Flame,
  MessageCircle,
  PartyPopper,
  SkipForward,
  Sparkles,
  Star,
  Zap,
} from "lucide-react"
import { Link } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Header } from "@/components/layout/Header"
import { PageHero } from "@/components/shared/PageHero"
import { EmptyStateCard } from "@/components/shared/EmptyStateCard"
import { SiteStatusBadge } from "@/components/leads/SiteStatusBadge"
import { InstagramIcon } from "@/components/icons/InstagramIcon"
import { useLeads } from "@/hooks/useLeads"
import { useLeadMutations } from "@/hooks/useLeadMutations"
import { tocarSom } from "@/hooks/useSom"
import { montarEstrategia } from "@/lib/estrategia"
import { formatarNota } from "@/lib/formatters"
import { linkWhatsappComMensagem } from "@/services/tarefasService"
import { FILTROS_VAZIOS, type Lead } from "@/types/lead"

const FILTROS_NOVOS = { ...FILTROS_VAZIOS, status: "novo" as const, ordenar: "score" as const }
const FILTROS_FOLLOWUPS = { ...FILTROS_VAZIOS, followup: "vencido" as const }

function CartaoDaSessao({
  lead,
  modo,
  onContatado,
  onPular,
  onIgnorar,
}: {
  lead: Lead
  modo: "novo" | "followup"
  onContatado: () => void
  onPular: () => void
  onIgnorar: () => void
}) {
  const mutations = useLeadMutations(lead.place_id)
  // no modo follow-up a copy de contato salva não serve - gera uma nova
  const [mensagem, setMensagem] = useState(modo === "novo" ? (lead.mensagem_gerada ?? "") : "")
  const estrategia = useMemo(() => montarEstrategia(lead), [lead])

  useEffect(() => {
    setMensagem(modo === "novo" ? (lead.mensagem_gerada ?? "") : "")
  }, [lead.place_id, lead.mensagem_gerada, modo])

  const abrirWhatsappEContatar = () => {
    if (lead.whatsapp_link) {
      window.open(linkWhatsappComMensagem(lead.whatsapp_link, mensagem || null), "_blank")
    }
    onContatado()
  }

  // Atalhos: Enter = WhatsApp + contatado · → = pular · Backspace = ignorar
  useEffect(() => {
    const aoTeclar = (evento: KeyboardEvent) => {
      const alvo = evento.target as HTMLElement
      if (alvo.tagName === "TEXTAREA" || alvo.tagName === "INPUT") return
      if (evento.key === "Enter") {
        evento.preventDefault()
        abrirWhatsappEContatar()
      } else if (evento.key === "ArrowRight") {
        evento.preventDefault()
        onPular()
      } else if (evento.key === "Backspace") {
        evento.preventDefault()
        onIgnorar()
      }
    }
    window.addEventListener("keydown", aoTeclar)
    return () => window.removeEventListener("keydown", aoTeclar)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lead.place_id, mensagem])

  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight">{lead.nome}</h2>
            {modo === "followup" && (
              <Badge variant="outline" className="border-warning/40 bg-warning/15 text-warning">
                Follow-up {lead.proximo_followup ? `venceu ${lead.proximo_followup}` : "pendente"}
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {lead.categoria || "Sem categoria"}
            {lead.cidade ? ` · ${lead.cidade}` : ""}
            {modo === "followup" && ` · ${lead.follow_ups_enviados} follow-up(s) já enviado(s)`}
          </p>
        </div>
        <span
          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-sm font-semibold tabular-nums text-primary"
          title="Score de prioridade"
        >
          <Flame className="size-4" />
          {lead.score}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <Star className="size-4 fill-warning text-warning" />
          <span className="font-medium text-foreground">{formatarNota(lead.nota)}</span>
          ({lead.num_avaliacoes ?? 0} avaliações)
        </span>
        <SiteStatusBadge siteStatus={lead.site_status} siteProblemas={lead.site_problemas} />
        {lead.site_url && (
          <a
            href={lead.site_url.startsWith("http") ? lead.site_url : `https://${lead.site_url}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            <ExternalLink className="size-3" />
            site atual
          </a>
        )}
        {lead.instagram_url && (
          <a
            href={lead.instagram_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-instagram-mid hover:underline"
          >
            <InstagramIcon className="size-3" />
            Instagram
          </a>
        )}
      </div>

      <div className="rounded-xl border border-primary/25 bg-primary/[0.04] p-3">
        <div className="mb-1 flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">Estratégia</p>
          <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary">
            {estrategia.cenario}
          </Badge>
        </div>
        <p className="text-sm leading-relaxed">{estrategia.angulo}</p>
      </div>

      <div className="space-y-2">
        {mensagem ? (
          <textarea
            value={mensagem}
            onChange={(e) => setMensagem(e.target.value)}
            rows={5}
            className="w-full resize-none rounded-lg border border-border bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Mensagem de abordagem"
          />
        ) : (
          <Button
            variant="outline"
            className="w-full"
            onClick={() =>
              mutations.gerarMensagem.mutate(
                { forcarNova: modo === "followup", tipo: modo === "followup" ? "followup" : "contato" },
                { onSuccess: (r) => setMensagem(r.mensagem) }
              )
            }
            disabled={mutations.gerarMensagem.isPending}
          >
            <Sparkles className="size-4" />
            {mutations.gerarMensagem.isPending
              ? "Gerando copy com a estratégia acima..."
              : modo === "followup"
                ? "Gerar copy de follow-up"
                : "Gerar copy de contato"}
          </Button>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <Button size="lg" onClick={abrirWhatsappEContatar} disabled={!lead.whatsapp_link}>
          <MessageCircle className="size-4" />
          {modo === "followup"
            ? "Abrir WhatsApp + follow-up feito"
            : "Abrir WhatsApp + marcar contatado"}
          <kbd className="ml-1 hidden rounded bg-primary-foreground/20 px-1.5 text-[10px] sm:inline">Enter</kbd>
        </Button>
        <Button size="lg" variant="outline" onClick={onPular}>
          <SkipForward className="size-4" />
          Pular
          <kbd className="ml-1 hidden rounded bg-muted px-1.5 text-[10px] sm:inline">→</kbd>
        </Button>
        <Button
          size="lg"
          variant="outline"
          className="text-muted-foreground hover:text-destructive"
          onClick={onIgnorar}
        >
          <Archive className="size-4" />
          Ignorar
        </Button>
      </div>
    </div>
  )
}

export function SessaoProspeccaoPage() {
  // a sessão começa pelos compromissos (follow-ups vencidos) e só depois vai
  // pros leads novos, do mais quente ao mais frio
  const filaFollowups = useLeads(FILTROS_FOLLOWUPS)
  const filaNovos = useLeads(FILTROS_NOVOS)
  const [processados, setProcessados] = useState<Set<string>>(new Set())
  const [contatados, setContatados] = useState(0)

  const followupsPendentes = filaFollowups.leads.filter((l) => !processados.has(l.place_id))
  const idsFollowups = new Set(filaFollowups.leads.map((l) => l.place_id))
  const novosPendentes = filaNovos.leads.filter(
    (l) => !processados.has(l.place_id) && !idsFollowups.has(l.place_id)
  )
  const fila = [...followupsPendentes, ...novosPendentes]
  const leadAtual = fila[0] ?? null
  const modoAtual: "novo" | "followup" = followupsPendentes.length > 0 ? "followup" : "novo"
  const isLoading = filaFollowups.isLoading || filaNovos.isLoading
  const mutations = useLeadMutations(leadAtual?.place_id ?? "")

  // busca a próxima página antes da fila local secar
  useEffect(() => {
    if (fila.length < 5 && filaNovos.hasNextPage) filaNovos.fetchNextPage()
    if (followupsPendentes.length < 3 && filaFollowups.hasNextPage) filaFollowups.fetchNextPage()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fila.length, followupsPendentes.length, filaNovos.hasNextPage, filaFollowups.hasNextPage])

  const avancar = (placeId: string) => {
    setProcessados((atual) => new Set(atual).add(placeId))
  }

  const handleContatado = () => {
    if (!leadAtual) return
    const id = leadAtual.place_id
    if (modoAtual === "followup") {
      mutations.marcarFollowupEnviado.mutate({
        followUpsEnviadosAnterior: leadAtual.follow_ups_enviados,
        ultimoFollowupEmAnterior: leadAtual.ultimo_followup_em,
        proximoFollowupAnterior: leadAtual.proximo_followup,
      })
    } else {
      mutations.atualizarStatus.mutate("contatado")
      tocarSom("card-movido")
    }
    setContatados((c) => c + 1)
    avancar(id)
  }

  const handleIgnorar = () => {
    if (!leadAtual) return
    const id = leadAtual.place_id
    mutations.ignorar.mutate(leadAtual.status)
    avancar(id)
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <main className="mx-auto w-full max-w-2xl space-y-5 px-4 py-6 sm:px-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar para o dashboard
        </Link>

        <PageHero
          icone={<Zap className="size-6" />}
          titulo="Sessão de prospecção"
          descricao="Um lead por vez, do mais quente pro mais frio - estratégia e copy prontas, abordagem em um clique."
          gradiente="from-google-maps-start/85 via-primary/85 to-google-maps-end/85"
        />

        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            <span className="font-semibold tabular-nums text-success">{contatados}</span> contatado(s)
            nesta sessão
          </span>
          <span className="tabular-nums">
            {followupsPendentes.length > 0 && (
              <span className="mr-2 text-warning">
                {followupsPendentes.length} follow-up(s) primeiro
              </span>
            )}
            {fila.length} na fila
          </span>
        </div>

        {isLoading ? (
          <Skeleton className="h-[420px] rounded-2xl" />
        ) : leadAtual ? (
          <CartaoDaSessao
            key={`${modoAtual}-${leadAtual.place_id}`}
            lead={leadAtual}
            modo={modoAtual}
            onContatado={handleContatado}
            onPular={() => avancar(leadAtual.place_id)}
            onIgnorar={handleIgnorar}
          />
        ) : (
          <EmptyStateCard
            icone={<PartyPopper className="size-5" />}
            titulo={
              contatados > 0
                ? `Fila zerada - ${contatados} lead(s) contatado(s) nesta sessão!`
                : "Nenhum lead novo na fila"
            }
            descricao="Rode uma busca no Google Maps para encher a fila de novo."
            acao={
              <Button size="sm" variant="outline" asChild>
                <Link to="/leads">
                  <Check className="size-4" />
                  Ir para leads do Maps
                </Link>
              </Button>
            }
          />
        )}
      </main>
    </div>
  )
}
