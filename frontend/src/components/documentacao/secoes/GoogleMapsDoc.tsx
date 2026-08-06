import {
  DocSection,
  DocH2,
  DocP,
  DocList,
  DocCallout,
  DocCode,
} from "@/components/documentacao/DocSection"

export function GoogleMapsDoc() {
  return (
    <DocSection titulo="Google Maps">
      <DocP>
        O canal do Google Maps busca empresas por nicho + cidade e filtra
        automaticamente as que valem a pena abordar: nota alta (≥ 4.0) e sem
        site cadastrado em lugar nenhum da web.
      </DocP>

      <DocH2>Como buscar leads</DocH2>
      <DocP>
        No botão "Nova busca", você digita uma ou mais linhas no formato{" "}
        <DocCode>nicho em cidade</DocCode> (ex.: "clínica de estética em
        Londrina"). Cada linha vira uma busca separada. O sistema roda em
        background e mostra o progresso ao vivo.
      </DocP>
      <DocCallout variante="warning">
        A busca depende do scraper externo <DocCode>gosom/google-maps-scraper</DocCode>,
        instalado na pasta do backend como <DocCode>google-maps-scraper.exe</DocCode>
        no Windows ou <DocCode>google-maps-scraper</DocCode> no macOS/Linux. Veja
        a seção "Instalação" para os detalhes.
      </DocCallout>

      <DocH2>Dupla checagem de "sem site"</DocH2>
      <DocP>
        Depois de listar as empresas do Maps, o sistema faz uma segunda busca
        na web (DuckDuckGo/Bing/Yahoo) pelo nome de cada empresa, pra
        confirmar que ela realmente não tem site em lugar nenhum — não só no
        cadastro do Maps. Isso evita levar leads que já têm site em outro
        lugar.
      </DocP>

      <DocH2>Lista e Kanban</DocH2>
      <DocP>
        Você pode alternar entre visualização em <strong>Lista</strong>{" "}
        (cards com todos os detalhes) e <strong>Kanban</strong> (colunas por
        estágio do funil, arrastando o card entre colunas para mudar o
        status).
      </DocP>

      <DocH2>Follow-up inteligente</DocH2>
      <DocList>
        <li>
          <strong>Gerar copy por IA</strong>: dois tipos — "contato" (primeira
          abordagem) e "follow-up" (retomar contato), com tom e argumento
          adaptados automaticamente.
        </li>
        <li>
          <strong>Marcar follow-up enviado</strong>: registra que você mandou
          mensagem e sugere a próxima data (cadência crescente: 3, depois 5,
          depois 7 dias, pra não parecer insistente).
        </li>
        <li>
          <strong>Lead difícil</strong>: aparece um selo de aviso quando o
          lead já recebeu follow-up e ficou parado por mais de 5 dias, com um
          atalho pra arquivar.
        </li>
      </DocList>

      <DocH2>Outras ações</DocH2>
      <DocList>
        <li>
          <strong>Tags e observações</strong>: texto livre pra organizar como
          quiser.
        </li>
        <li>
          <strong>Templates de mensagem</strong>: salve mensagens que
          funcionam bem e reutilize depois em outros leads.
        </li>
        <li>
          <strong>Exportar CSV</strong>: baixa todos os leads filtrados numa
          planilha.
        </li>
        <li>
          <strong>Ignorar</strong>: some da lista principal (reversível).{" "}
          <strong>Excluir definitivamente</strong>: apaga do banco de vez, só
          permitido em leads já ignorados.
        </li>
      </DocList>
    </DocSection>
  )
}
