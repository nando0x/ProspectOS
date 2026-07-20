import { ArrowLeft } from "lucide-react"
import { Link } from "react-router-dom"
import { Header } from "@/components/layout/Header"
import { Skeleton } from "@/components/ui/skeleton"
import { FonteMapsCard } from "@/components/configuracoes/FonteMapsCard"
import { InstagramContaCard } from "@/components/configuracoes/InstagramContaCard"
import { PerfilVendedorCard } from "@/components/configuracoes/PerfilVendedorCard"
import { ProvedorApiCard } from "@/components/configuracoes/ProvedorApiCard"
import { ScraperProxyCard } from "@/components/configuracoes/ScraperProxyCard"
import { SomConfigCard } from "@/components/configuracoes/SomConfigCard"
import { useConfiguracoes } from "@/hooks/useConfiguracoes"

const TITULOS: Record<"gemini" | "groq" | "nvidia" | "pagespeed", string> = {
  gemini: "Google Gemini",
  groq: "Groq",
  nvidia: "NVIDIA",
  pagespeed: "Google PageSpeed (opcional)",
}

export function ConfiguracoesPage() {
  const { data, isLoading } = useConfiguracoes()

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <main className="mx-auto w-full max-w-2xl space-y-6 px-4 py-6 sm:px-6">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar para o dashboard
        </Link>

        <div>
          <h2 className="text-xl font-semibold tracking-tight">Seu perfil</h2>
          <p className="text-sm text-muted-foreground">
            Quem envia as mensagens de prospecção - as copies geradas por IA
            saem assinadas e na sua voz.
          </p>
        </div>

        <PerfilVendedorCard />

        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            Configurações de API
          </h2>
          <p className="text-sm text-muted-foreground">
            As chaves abaixo são usadas para gerar mensagens por IA. O sistema
            tenta cada provedor na ordem Gemini → Groq → NVIDIA, e passa para
            o próximo automaticamente se algum falhar ou ficar sem cota.
          </p>
        </div>

        {isLoading || !data ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-[140px]" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {(["gemini", "groq", "nvidia", "pagespeed"] as const).map((provedor) => (
              <ProvedorApiCard
                key={provedor}
                provedor={provedor}
                titulo={TITULOS[provedor]}
                config={data[provedor]}
              />
            ))}
            <p className="text-xs text-muted-foreground">
              A chave do PageSpeed é opcional: adiciona a nota oficial de
              desempenho do Google no diagnóstico em PDF (funciona sem chave
              para uso leve, mas com limites).
            </p>
          </div>
        )}

        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            Fonte de dados do Google Maps
          </h2>
          <p className="text-sm text-muted-foreground">
            Escolha entre o coletor local e a integração oficial do Google
            Places.
          </p>
        </div>

        <FonteMapsCard />

        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            Conta do Instagram
          </h2>
          <p className="text-sm text-muted-foreground">
            Conecte sua conta para analisar posts e enriquecer perfis. O login
            substitui o antigo script de linha de comando.
          </p>
        </div>

        <InstagramContaCard />

        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            Busca no Google Maps
          </h2>
          <p className="text-sm text-muted-foreground">
            Configurações avançadas do scraper de leads.
          </p>
        </div>

        <ScraperProxyCard />

        <div>
          <h2 className="text-xl font-semibold tracking-tight">Sons</h2>
          <p className="text-sm text-muted-foreground">
            Controle os sons de feedback do sistema.
          </p>
        </div>

        <SomConfigCard />
      </main>
    </div>
  )
}
