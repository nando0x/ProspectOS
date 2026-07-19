import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  BarChart3,
  Building2,
  ListTodo,
  MapPin,
  Search,
  Settings,
  Zap,
} from "lucide-react"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { InstagramIcon } from "@/components/icons/InstagramIcon"
import { StatusBadge } from "@/components/leads/StatusBadge"
import { leadsService } from "@/services/leadsService"
import { normalizarParaBusca } from "@/lib/nichos"
import { cn } from "@/lib/utils"
import { FILTROS_VAZIOS } from "@/types/lead"

const PAGINAS = [
  { rotulo: "Sessão de prospecção", rota: "/sessao", icone: <Zap className="size-4" /> },
  { rotulo: "Tarefas de hoje", rota: "/tarefas", icone: <ListTodo className="size-4" /> },
  { rotulo: "Leads do Maps", rota: "/leads", icone: <MapPin className="size-4" /> },
  { rotulo: "Leads do Instagram", rota: "/instagram", icone: <InstagramIcon className="size-4" /> },
  { rotulo: "Analytics", rota: "/analytics", icone: <BarChart3 className="size-4" /> },
  { rotulo: "Configurações", rota: "/configuracoes", icone: <Settings className="size-4" /> },
]

interface ItemPaleta {
  chave: string
  icone: React.ReactNode
  rotulo: string
  detalhe?: React.ReactNode
  aoSelecionar: () => void
}

/** Busca global (Ctrl+K / Cmd+K): pula pra qualquer página ou acha um lead do
 * Maps pelo nome/endereço e abre a lista já filtrada nele. */
export function PaletaComando() {
  const [aberta, setAberta] = useState(false)
  const [consulta, setConsulta] = useState("")
  const [indice, setIndice] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    const aoTeclar = (evento: KeyboardEvent) => {
      if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "k") {
        evento.preventDefault()
        setAberta((atual) => !atual)
        setConsulta("")
        setIndice(0)
      }
    }
    window.addEventListener("keydown", aoTeclar)
    return () => window.removeEventListener("keydown", aoTeclar)
  }, [])

  const { data: paginaLeads } = useQuery({
    queryKey: ["paleta-leads", consulta],
    queryFn: () => leadsService.listar({ ...FILTROS_VAZIOS, busca: consulta }, 0),
    enabled: aberta && consulta.trim().length >= 2,
    staleTime: 10_000,
  })

  const itens = useMemo<ItemPaleta[]>(() => {
    const termo = normalizarParaBusca(consulta.trim())
    const fechar = () => setAberta(false)

    const paginas: ItemPaleta[] = PAGINAS.filter(
      (p) => !termo || normalizarParaBusca(p.rotulo).includes(termo)
    ).map((p) => ({
      chave: `pagina-${p.rota}`,
      icone: p.icone,
      rotulo: p.rotulo,
      aoSelecionar: () => {
        fechar()
        navigate(p.rota)
      },
    }))

    const leads: ItemPaleta[] = (termo.length >= 2 ? (paginaLeads?.leads ?? []) : [])
      .slice(0, 8)
      .map((lead) => ({
        chave: `lead-${lead.place_id}`,
        icone: <Building2 className="size-4 text-muted-foreground" />,
        rotulo: lead.nome,
        detalhe: (
          <span className="flex items-center gap-2">
            <span className="truncate text-xs text-muted-foreground">
              {lead.categoria || "sem categoria"}
              {lead.cidade ? ` · ${lead.cidade}` : ""}
            </span>
            <StatusBadge status={lead.status} />
          </span>
        ),
        aoSelecionar: () => {
          fechar()
          navigate(`/leads?busca=${encodeURIComponent(lead.nome)}`)
        },
      }))

    return [...leads, ...paginas]
  }, [consulta, paginaLeads, navigate])

  useEffect(() => {
    setIndice(0)
  }, [consulta])

  const selecionar = (item: ItemPaleta | undefined) => item?.aoSelecionar()

  return (
    <Dialog open={aberta} onOpenChange={setAberta}>
      <DialogContent className="top-[20%] translate-y-0 gap-0 p-0 sm:max-w-lg">
        <DialogTitle className="sr-only">Busca global</DialogTitle>
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={consulta}
            onChange={(e) => setConsulta(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault()
                setIndice((i) => Math.min(i + 1, itens.length - 1))
              } else if (e.key === "ArrowUp") {
                e.preventDefault()
                setIndice((i) => Math.max(i - 1, 0))
              } else if (e.key === "Enter") {
                e.preventDefault()
                selecionar(itens[indice])
              }
            }}
            placeholder="Buscar lead pelo nome, ou ir para uma página..."
            className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            Esc
          </kbd>
        </div>
        <div className="max-h-72 overflow-y-auto p-2">
          {itens.length === 0 ? (
            <p className="px-2 py-4 text-center text-sm text-muted-foreground">
              Nada encontrado para "{consulta}".
            </p>
          ) : (
            itens.map((item, i) => (
              <button
                key={item.chave}
                type="button"
                onClick={() => selecionar(item)}
                onMouseEnter={() => setIndice(i)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm",
                  i === indice ? "bg-accent" : "hover:bg-accent/60"
                )}
              >
                <span className="shrink-0">{item.icone}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{item.rotulo}</span>
                {item.detalhe}
              </button>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
