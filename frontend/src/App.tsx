import { BrowserRouter, Route, Routes } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { queryClient } from "@/lib/queryClient"
import { PaletaComando } from "@/components/shared/PaletaComando"
import { DashboardPage } from "@/pages/DashboardPage"
import { TarefasPage } from "@/pages/TarefasPage"
import { SessaoProspeccaoPage } from "@/pages/SessaoProspeccaoPage"
import { LeadsMapsPage } from "@/pages/LeadsMapsPage"
import { ConversaPage } from "@/pages/ConversaPage"
import { AnalyticsPage } from "@/pages/AnalyticsPage"
import { InstagramPage } from "@/pages/InstagramPage"
import { InstagramAnalyticsPage } from "@/pages/InstagramAnalyticsPage"
import { InstagramArquivadosPage } from "@/pages/InstagramArquivadosPage"
import { ConfiguracoesPage } from "@/pages/ConfiguracoesPage"
import { DocumentacaoPage } from "@/pages/DocumentacaoPage"

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <PaletaComando />
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/tarefas" element={<TarefasPage />} />
            <Route path="/sessao" element={<SessaoProspeccaoPage />} />
            <Route path="/leads" element={<LeadsMapsPage />} />
            <Route path="/conversas/:placeId" element={<ConversaPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/instagram" element={<InstagramPage />} />
            <Route path="/instagram/analytics" element={<InstagramAnalyticsPage />} />
            <Route path="/instagram/arquivados" element={<InstagramArquivadosPage />} />
            <Route path="/configuracoes" element={<ConfiguracoesPage />} />
            <Route path="/documentacao" element={<DocumentacaoPage />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="bottom-right" richColors />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
