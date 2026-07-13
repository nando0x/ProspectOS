import { useState } from "react"
import { ArrowLeft, Download, Send } from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Header } from "@/components/layout/Header"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { SearchInput } from "@/components/filters/SearchInput"
import { StatusSelect } from "@/components/filters/StatusSelect"
import { NichoSelectInstagram } from "@/components/filters/NichoSelectInstagram"
import { OrdenacaoPrioridadeSelect } from "@/components/filters/OrdenacaoPrioridadeSelect"
import { InstagramProgress } from "@/components/instagram/InstagramProgress"
import { InstagramBanner } from "@/components/instagram/InstagramBanner"
import { PostList } from "@/components/instagram/PostList"
import { LeadsDoPost } from "@/components/instagram/LeadsDoPost"
import { useAnaliseInstagram } from "@/hooks/useAnaliseInstagram"
import { ApiError } from "@/services/httpClient"
import { urlExportarCsvInstagram } from "@/services/instagramService"
import type { StatusLead } from "@/types/lead"
import type { OrdenacaoPrioridade } from "@/lib/constants"

export function InstagramPage() {
  const [url, setUrl] = useState("")
  const [nichoAlvo, setNichoAlvo] = useState("")
  const [postSelecionadoId, setPostSelecionadoId] = useState<number | null>(null)
  const [filtroStatus, setFiltroStatus] = useState<StatusLead | "">("")
  const [filtroNicho, setFiltroNicho] = useState("")
  const [busca, setBusca] = useState("")
  const [ordenacaoPrioridade, setOrdenacaoPrioridade] =
    useState<OrdenacaoPrioridade>("")
  const { dispararAnalise, statusAnalise, pollingAtivo } = useAnaliseInstagram()

  const handleAnalisar = () => {
    const urlLimpa = url.trim()
    if (!urlLimpa) return

    dispararAnalise.mutate(
      { postUrl: urlLimpa, nichoAlvo: nichoAlvo.trim() },
      {
        onSuccess: (resposta) => {
          setUrl("")
          setNichoAlvo("")
          setPostSelecionadoId(resposta.post_id)
          toast.success("Análise iniciada.")
        },
        onError: (erro) => {
          toast.error(erro instanceof ApiError ? erro.message : "Erro ao iniciar análise.")
        },
      }
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar para o dashboard
        </Link>

        <InstagramBanner />

        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAnalisar()}
            placeholder="https://www.instagram.com/p/XXXXXXXXX/"
            disabled={pollingAtivo}
            className="sm:flex-[2]"
          />
          <Input
            value={nichoAlvo}
            onChange={(e) => setNichoAlvo(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAnalisar()}
            placeholder="Que tipo de cliente você procura? (opcional, ex: advogados)"
            disabled={pollingAtivo}
            className="sm:flex-[1]"
          />
          <Button onClick={handleAnalisar} disabled={pollingAtivo || !url.trim()}>
            <Send className="size-4" />
            Analisar
          </Button>
        </div>

        {pollingAtivo && statusAnalise.data && (
          <InstagramProgress estado={statusAnalise.data} />
        )}

        <PostList
          postSelecionadoId={postSelecionadoId}
          onSelecionarPost={setPostSelecionadoId}
        />

        {postSelecionadoId !== null && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-muted-foreground">
                Perfis encontrados neste post
              </h3>
              <div className="flex flex-wrap gap-2">
                <SearchInput valor={busca} onChange={setBusca} />
                <StatusSelect valor={filtroStatus} onChange={setFiltroStatus} />
                <NichoSelectInstagram
                  valor={filtroNicho}
                  onChange={setFiltroNicho}
                />
                <OrdenacaoPrioridadeSelect
                  valor={ordenacaoPrioridade}
                  onChange={setOrdenacaoPrioridade}
                />
                <Button variant="outline" size="sm" asChild>
                  <a href={urlExportarCsvInstagram(postSelecionadoId)}>
                    <Download className="size-4" />
                    <span className="hidden sm:inline">Exportar CSV</span>
                  </a>
                </Button>
              </div>
            </div>
            <LeadsDoPost
              postId={postSelecionadoId}
              filtroStatus={filtroStatus}
              filtroNicho={filtroNicho}
              busca={busca}
              ordenacaoPrioridade={ordenacaoPrioridade}
            />
          </div>
        )}
      </main>
    </div>
  )
}
