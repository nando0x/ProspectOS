import { motion } from "framer-motion"
import { Archive, Clock, RotateCcw, Users } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { InstagramIcon } from "@/components/icons/InstagramIcon"
import { DeleteLeadButton } from "@/components/lead-detail/DeleteLeadButton"
import { cn } from "@/lib/utils"
import { formatarTempoRelativo } from "@/lib/formatters"
import type { PostInstagram } from "@/types/instagram"

interface PostCardProps {
  post: PostInstagram
  onClick: () => void
  selecionado: boolean
  onArquivar?: () => void
  onDesarquivar?: () => void
  onExcluirDefinitivamente?: () => void
}

const LABEL_ETAPA: Record<PostInstagram["etapa"], string> = {
  pendente: "Pendente",
  raspando: "Extraindo comentários...",
  enriquecendo: "Enriquecendo perfis...",
  concluido: "Concluído",
  erro: "Erro",
}

function codigoDoPost(postUrl: string): string {
  const partes = postUrl.replace(/\/$/, "").split("/")
  return partes[partes.length - 1] || postUrl
}

export function PostCard({
  post,
  onClick,
  selecionado,
  onArquivar,
  onDesarquivar,
  onExcluirDefinitivamente,
}: PostCardProps) {
  const { contagem_leads: contagem } = post
  const totalPerfis = contagem.total ?? 0

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick()
      }}
      aria-label={`Abrir leads do post ${post.post_url}`}
      className={cn(
        "flex cursor-pointer flex-col gap-3 rounded-xl border border-border bg-gradient-to-br from-instagram-start/[0.06] via-card to-instagram-end/[0.06] p-4 text-left shadow-sm transition-colors hover:from-instagram-start/[0.1] hover:to-instagram-end/[0.1]",
        selecionado && "ring-2 ring-primary"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <InstagramIcon className="size-4 shrink-0 text-instagram-mid" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              Post {codigoDoPost(post.post_url)}
            </p>
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="size-3" />
              {formatarTempoRelativo(post.criado_em)}
            </p>
          </div>
        </div>
        {post.etapa === "concluido" && totalPerfis > 0 && (
          <span className="flex shrink-0 items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            <Users className="size-3" />
            {totalPerfis}
          </span>
        )}
      </div>

      {post.etapa !== "concluido" ? (
        <Badge variant="outline" className="w-fit">
          {LABEL_ETAPA[post.etapa]}
        </Badge>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {(contagem.alta ?? 0) > 0 && (
            <Badge variant="outline" className="bg-success/15 text-success border-success/30">
              {contagem.alta} alta
            </Badge>
          )}
          {(contagem.media ?? 0) > 0 && (
            <Badge variant="outline" className="bg-warning/15 text-warning border-warning/30">
              {contagem.media} média
            </Badge>
          )}
          {(contagem.baixa ?? 0) > 0 && (
            <Badge variant="outline" className="bg-muted text-muted-foreground">
              {contagem.baixa} baixa
            </Badge>
          )}
          {(contagem.pendente ?? 0) > 0 && (
            <Badge variant="outline">{contagem.pendente} pendente</Badge>
          )}
          {(contagem.ignorado ?? 0) > 0 && (
            <Badge variant="outline" className="bg-muted text-muted-foreground">
              {contagem.ignorado} ignorado
            </Badge>
          )}
        </div>
      )}

      {(onArquivar || onDesarquivar || onExcluirDefinitivamente) && (
        <div
          className="flex flex-wrap gap-1.5 border-t border-border pt-2"
          onClick={(e) => e.stopPropagation()}
        >
          {onArquivar && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={onArquivar}
            >
              <Archive className="size-3.5" />
              Arquivar
            </Button>
          )}
          {onDesarquivar && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={onDesarquivar}
            >
              <RotateCcw className="size-3.5" />
              Restaurar
            </Button>
          )}
          {onExcluirDefinitivamente && (
            <DeleteLeadButton
              nomeLead={`o post ${codigoDoPost(post.post_url)}`}
              definitivo
              onConfirmar={onExcluirDefinitivamente}
            />
          )}
        </div>
      )}
    </motion.div>
  )
}
