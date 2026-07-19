import { ArrowLeft, Check, Copy, Flame, ListTodo, MapPin, MessageCircle, PartyPopper } from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Header } from "@/components/layout/Header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { InstagramIcon } from "@/components/icons/InstagramIcon"
import { SiteStatusBadge } from "@/components/leads/SiteStatusBadge"
import { EmptyStateCard } from "@/components/shared/EmptyStateCard"
import { PageHero } from "@/components/shared/PageHero"
import { useTarefasHoje } from "@/hooks/useTarefasHoje"
import { tocarSom } from "@/hooks/useSom"
import { ajustarSaudacao } from "@/lib/saudacao"
import { linkWhatsappComMensagem } from "@/services/tarefasService"
import { formatarNota } from "@/lib/formatters"
import type { LeadQuente, TarefaFollowup } from "@/types/tarefas"

function diasDeAtraso(proximoFollowup: string): string {
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const data = new Date(`${proximoFollowup}T00:00:00`)
  const dias = Math.round((hoje.getTime() - data.getTime()) / 86_400_000)
  if (dias <= 0) return "para hoje"
  return dias === 1 ? "1 dia atrasado" : `${dias} dias atrasado`
}

async function copiarMensagem(mensagem: string) {
  await navigator.clipboard.writeText(ajustarSaudacao(mensagem))
  tocarSom("copiado")
  toast.success("Mensagem copiada - é só colar na DM.")
}

function LinhaFollowup({
  tarefa,
  onFollowupEnviado,
  desabilitado,
}: {
  tarefa: TarefaFollowup
  onFollowupEnviado: () => void
  desabilitado: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3 shadow-sm">
      {tarefa.canal === "instagram" ? (
        <InstagramIcon className="size-4 shrink-0 text-instagram-mid" />
      ) : (
        <MessageCircle className="size-4 shrink-0 text-success" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{tarefa.titulo}</p>
        <p className="text-xs text-muted-foreground">
          Follow-up nº {tarefa.follow_ups_enviados + 1} · {diasDeAtraso(tarefa.proximo_followup)}
        </p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tarefa.canal === "maps" && tarefa.whatsapp_link && (
          <Button size="sm" variant="outline" className="h-8 text-xs" asChild>
            <a
              href={linkWhatsappComMensagem(tarefa.whatsapp_link, tarefa.mensagem)}
              target="_blank"
              rel="noreferrer"
            >
              <MessageCircle className="size-3.5" />
              Abrir WhatsApp
            </a>
          </Button>
        )}
        {tarefa.canal === "instagram" && tarefa.username && (
          <>
            {tarefa.mensagem && (
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => copiarMensagem(tarefa.mensagem!)}
              >
                <Copy className="size-3.5" />
                Copiar DM
              </Button>
            )}
            <Button size="sm" variant="outline" className="h-8 text-xs" asChild>
              <a
                href={`https://www.instagram.com/${tarefa.username}/`}
                target="_blank"
                rel="noreferrer"
              >
                <InstagramIcon className="size-3.5" />
                Abrir perfil
              </a>
            </Button>
          </>
        )}
        <Button
          size="sm"
          className="h-8 text-xs"
          onClick={onFollowupEnviado}
          disabled={desabilitado}
        >
          <Check className="size-3.5" />
          Follow-up enviado
        </Button>
      </div>
    </div>
  )
}

function LinhaLeadQuente({
  lead,
  onContatado,
  desabilitado,
}: {
  lead: LeadQuente
  onContatado: () => void
  desabilitado: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3 shadow-sm">
      <span
        className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary"
        title="Score de prioridade"
      >
        <Flame className="size-3" />
        {lead.score}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{lead.titulo}</p>
        <p className="truncate text-xs text-muted-foreground">
          {lead.categoria || "Sem categoria"} · nota {formatarNota(lead.nota)} (
          {lead.num_avaliacoes ?? 0})
        </p>
      </div>
      <SiteStatusBadge siteStatus={lead.site_status} siteProblemas={lead.site_problemas} />
      <div className="flex flex-wrap gap-1.5">
        {lead.whatsapp_link && (
          <Button size="sm" variant="outline" className="h-8 text-xs" asChild>
            <a
              href={linkWhatsappComMensagem(lead.whatsapp_link, lead.mensagem)}
              target="_blank"
              rel="noreferrer"
              title={
                lead.mensagem
                  ? "Abre o WhatsApp com a mensagem gerada já preenchida"
                  : "Abre o WhatsApp (gere a mensagem na tela de leads pra levá-la preenchida)"
              }
            >
              <MessageCircle className="size-3.5" />
              Abrir WhatsApp
            </a>
          </Button>
        )}
        <Button size="sm" className="h-8 text-xs" onClick={onContatado} disabled={desabilitado}>
          <Check className="size-3.5" />
          Marcar contatado
        </Button>
      </div>
    </div>
  )
}

export function TarefasPage() {
  const { tarefas, marcarFollowupEnviado, marcarContatado } = useTarefasHoje()

  if (tarefas.isLoading) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <Header />
        <main className="mx-auto w-full max-w-4xl space-y-3 px-4 py-6 sm:px-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[64px]" />
          ))}
        </main>
      </div>
    )
  }

  const followups = tarefas.data?.followups ?? []
  const novosQuentes = tarefas.data?.novos_quentes ?? []

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <main className="mx-auto w-full max-w-4xl space-y-6 px-4 py-6 sm:px-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar para o dashboard
        </Link>

        <PageHero
          icone={<ListTodo className="size-6" />}
          titulo="Tarefas de hoje"
          descricao="Sua mesa de trabalho: follow-ups vencidos e os leads mais quentes, cada um com a abordagem a 1 clique de distância."
          gradiente="from-google-maps-start/85 via-primary/85 to-google-maps-end/85"
        />

        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Follow-ups para hoje
            </h2>
            {followups.length > 0 && <Badge variant="outline">{followups.length}</Badge>}
          </div>
          {followups.length === 0 ? (
            <EmptyStateCard
              icone={<PartyPopper className="size-5" />}
              titulo="Nenhum follow-up pendente"
              descricao="Nada vencido nem para hoje - caixa limpa."
            />
          ) : (
            followups.map((tarefa) => (
              <LinhaFollowup
                key={`${tarefa.canal}-${tarefa.id}`}
                tarefa={tarefa}
                onFollowupEnviado={() => marcarFollowupEnviado.mutate(tarefa)}
                desabilitado={marcarFollowupEnviado.isPending}
              />
            ))
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Leads novos mais quentes
            </h2>
            {novosQuentes.length > 0 && <Badge variant="outline">{novosQuentes.length}</Badge>}
          </div>
          {novosQuentes.length === 0 ? (
            <EmptyStateCard
              icone={<MapPin className="size-5" />}
              titulo="Nenhum lead novo esperando abordagem"
              descricao="Rode uma busca no Google Maps para encher esta fila com leads priorizados por score."
              acao={
                <Button size="sm" variant="outline" asChild>
                  <Link to="/leads">
                    <MapPin className="size-4" />
                    Ir para leads do Maps
                  </Link>
                </Button>
              }
            />
          ) : (
            novosQuentes.map((lead) => (
              <LinhaLeadQuente
                key={lead.id}
                lead={lead}
                onContatado={() => marcarContatado.mutate(lead.id)}
                desabilitado={marcarContatado.isPending}
              />
            ))
          )}
        </section>
      </main>
    </div>
  )
}
