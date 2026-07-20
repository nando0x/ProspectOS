import { useEffect, useState } from "react"
import { Copy, MessageCircle, MessageCircleReply, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { TemplateSelector } from "@/components/shared/TemplateSelector"
import { useClipboard } from "@/hooks/useClipboard"
import { ajustarSaudacao } from "@/lib/saudacao"
import { formatarTempoRelativo } from "@/lib/formatters"
import { linkWhatsappComMensagem } from "@/services/tarefasService"
import type { UseMutationResult } from "@tanstack/react-query"
import type { GerarMensagemResposta, Lead } from "@/types/lead"

interface LeadMessageGeneratorProps {
  lead: Lead
  gerarMensagem: UseMutationResult<
    GerarMensagemResposta,
    Error,
    { forcarNova: boolean; tipo?: "contato" | "followup" },
    unknown
  >
  marcarFollowupEnviado: UseMutationResult<
    unknown,
    Error,
    {
      followUpsEnviadosAnterior: number
      ultimoFollowupEmAnterior: string | null
      proximoFollowupAnterior: string | null
    },
    unknown
  >
}

export function LeadMessageGenerator({
  lead,
  gerarMensagem,
  marcarFollowupEnviado,
}: LeadMessageGeneratorProps) {
  const [mensagem, setMensagem] = useState(lead.mensagem_gerada ?? "")

  useEffect(() => {
    setMensagem(lead.mensagem_gerada ?? "")
  }, [lead.place_id, lead.mensagem_gerada])

  const { copiado, copiar } = useClipboard()
  const {
    copiado: numeroCopiado,
    copiar: copiarNumero,
  } = useClipboard()

  const handleGerar = (tipo: "contato" | "followup") => {
    const jaTinhaMensagem = mensagem.trim().length > 0
    gerarMensagem.mutate(
      { forcarNova: jaTinhaMensagem, tipo },
      {
        onSuccess: (resposta) => {
          setMensagem(resposta.mensagem)
          if (resposta.avisos?.length) {
            toast.warning(
              `${resposta.avisos.join(" ")} (usado: ${resposta.provedor ?? "?"})`
            )
          } else {
            toast.success("Mensagem gerada com sucesso.")
          }
        },
      }
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-2">
      <Label>Mensagem de abordagem (gerada por IA)</Label>
      <Textarea
        value={mensagem}
        onChange={(e) => setMensagem(e.target.value)}
        placeholder="Clique em 'Gerar copy de contato' para criar uma sugestão"
        className="min-h-[220px] flex-1 resize-none"
      />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() => handleGerar("contato")}
          disabled={gerarMensagem.isPending}
        >
          <Sparkles className="size-4" />
          {gerarMensagem.isPending ? "Gerando..." : "Gerar copy de contato"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => handleGerar("followup")}
          disabled={gerarMensagem.isPending}
        >
          <MessageCircleReply className="size-4" />
          Gerar copy de follow-up
        </Button>
        <Button size="sm" variant="outline" onClick={() => copiar(ajustarSaudacao(mensagem))}>
          <Copy className="size-4" />
          {copiado ? "Copiado!" : "Copiar"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="border-success/40 text-success hover:bg-success/10"
          onClick={() => copiarNumero(lead.telefone ?? "")}
        >
          {numeroCopiado ? "Copiado!" : "Copiar número"}
        </Button>
        {lead.whatsapp_link && (
          <Button
            size="sm"
            className="bg-success text-white hover:bg-success/90"
            onClick={() =>
              window.open(
                linkWhatsappComMensagem(lead.whatsapp_link!, mensagem || null),
                "_blank"
              )
            }
          >
            <MessageCircle className="size-4" />
            Abrir WhatsApp
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/40 p-2.5">
        <Button
          size="sm"
          variant="secondary"
          onClick={() =>
            marcarFollowupEnviado.mutate({
              followUpsEnviadosAnterior: lead.follow_ups_enviados,
              ultimoFollowupEmAnterior: lead.ultimo_followup_em,
              proximoFollowupAnterior: lead.proximo_followup,
            })
          }
          disabled={marcarFollowupEnviado.isPending}
        >
          Marquei follow-up
        </Button>
        {lead.follow_ups_enviados > 0 && (
          <p className="text-xs text-muted-foreground">
            {lead.follow_ups_enviados} follow-up(s) enviado(s)
            {lead.ultimo_followup_em &&
              ` · último em ${formatarTempoRelativo(lead.ultimo_followup_em)}`}
          </p>
        )}
      </div>

      <TemplateSelector
        textoAtual={mensagem}
        onUsarTemplate={setMensagem}
        nichoSugerido={lead.nicho}
      />
    </div>
  )
}
