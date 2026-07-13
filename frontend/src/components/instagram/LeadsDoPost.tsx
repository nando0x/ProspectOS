import { AnimatePresence } from "framer-motion"
import { useState } from "react"
import { Trash2, Users } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { useLeadsInstagram } from "@/hooks/useLeadsInstagram"
import { useSelecaoLeadsInstagram } from "@/hooks/useSelecaoLeadsInstagram"
import { useBulkMutationsInstagram } from "@/hooks/useBulkMutationsInstagram"
import { InstagramLeadCard } from "@/components/instagram/InstagramLeadCard"
import { InstagramBulkActionsBar } from "@/components/instagram/InstagramBulkActionsBar"
import { InstagramLeadDetailModal } from "@/components/instagram/InstagramLeadDetailModal"
import type { StatusLead } from "@/types/lead"
import type { OrdenacaoPrioridade } from "@/lib/constants"
import { ordenarPorPrioridade } from "@/lib/constants"

interface LeadsDoPostProps {
  postId: number
  filtroStatus: StatusLead | ""
  filtroNicho: string
  busca: string
  ordenacaoPrioridade: OrdenacaoPrioridade
}

export function LeadsDoPost({
  postId,
  filtroStatus,
  filtroNicho,
  busca,
  ordenacaoPrioridade,
}: LeadsDoPostProps) {
  const { leads: leadsSemOrdenar, isLoading } = useLeadsInstagram(postId, {
    status: filtroStatus,
    nicho: filtroNicho,
    busca,
  })
  const leads = ordenarPorPrioridade(leadsSemOrdenar, ordenacaoPrioridade)
  const { selecionados, alternar, limpar, quantidade } =
    useSelecaoLeadsInstagram()
  const [leadIdSelecionado, setLeadIdSelecionado] = useState<number | null>(
    null
  )
  const leadDetalhe = leads.find((l) => l.id === leadIdSelecionado) ?? null
  const { excluirEmLoteDefinitivamente } = useBulkMutationsInstagram(postId)
  const modoIgnorados = filtroStatus === "ignorado"

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[160px]" />
        ))}
      </div>
    )
  }

  if (leads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-12 text-center">
        <Users className="size-7 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Nenhum perfil corresponde aos filtros selecionados.
        </p>
      </div>
    )
  }

  return (
    <div>
      {modoIgnorados && (
        <div className="mb-3 flex justify-end">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="size-4" />
                Esvaziar ignorados
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  Excluir todos os {leads.length} lead(s) ignorado(s)?
                </AlertDialogTitle>
                <AlertDialogDescription>
                  Isso apaga de vez todos os leads ignorados carregados nesta
                  lista. Não tem como desfazer.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() =>
                    excluirEmLoteDefinitivamente.mutate(leads.map((l) => l.id))
                  }
                >
                  Excluir todos
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {leads.map((lead) => (
          <InstagramLeadCard
            key={lead.id}
            lead={lead}
            selecionado={selecionados.has(lead.id)}
            onAlternarSelecao={() => alternar(lead.id)}
            onAbrirDetalhe={() => setLeadIdSelecionado(lead.id)}
          />
        ))}
      </div>

      <InstagramLeadDetailModal
        lead={leadDetalhe}
        onClose={() => setLeadIdSelecionado(null)}
      />

      <AnimatePresence>
        {quantidade > 0 && (
          <InstagramBulkActionsBar
            postId={postId}
            leadIdsSelecionados={Array.from(selecionados)}
            onLimparSelecao={limpar}
            modoIgnorados={modoIgnorados}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
