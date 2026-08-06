import { DocSection, DocH2, DocP } from "@/components/documentacao/DocSection"

export function FaqDoc() {
  return (
    <DocSection titulo="Perguntas comuns">
      <DocH2>Rodei a mesma busca de novo, os leads antigos vão duplicar?</DocH2>
      <DocP>
        Não. Cada empresa é identificada pelo <code>place_id</code> do
        Google, então rodar a mesma busca depois só atualiza dados "vivos"
        (nome, nota, telefone) sem mexer no status, tags, observações ou
        follow-up que você já tinha preenchido.
      </DocP>

      <DocH2>A busca no Maps não retornou nenhum resultado, o que houve?</DocH2>
      <DocP>
        Confira se o scraper do Google Maps está na pasta correta do backend
        (<code>google-maps-scraper.exe</code> no Windows ou{" "}
        <code>google-maps-scraper</code> no macOS/Linux) e se o nicho/cidade
        está bem escrito. Nichos muito específicos ou cidades pequenas podem
        realmente não ter resultado qualificado (nota alta + sem site).
      </DocP>

      <DocH2>Posso usar sem chave de IA configurada?</DocH2>
      <DocP>
        Sim, para buscar e organizar leads. Só a geração de mensagem por IA
        (copy de contato/follow-up) e a classificação automática do Instagram
        precisam de pelo menos uma chave configurada em "Configurações".
      </DocP>

      <DocH2>Excluí um lead sem querer, dá pra recuperar?</DocH2>
      <DocP>
        Se foi "ignorar", sim — ele só fica escondido, procure pelo filtro de
        status "Ignorado". Se foi "excluir definitivamente", não — essa ação
        apaga do banco de vez, por isso só é permitida em leads já ignorados
        (uma proteção extra contra clique errado).
      </DocP>

      <DocH2>O Instagram está pedindo login de novo, é normal?</DocH2>
      <DocP>
        Sim, sessões expiram de tempos em tempos. Basta rodar o script de
        login novamente (veja a seção "Instalação").
      </DocP>
    </DocSection>
  )
}
