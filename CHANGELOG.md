# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto adota versionamento semântico.

## [Não lançado]

### Adicionado
- Suporte a **Linux e macOS**: `iniciar.sh` (equivalente do `iniciar.bat`) e
  `backend/preparar_driver_playwright.sh`, que monta o driver do Playwright a partir
  do npm — o CDN antigo usado pelo scraper de Maps saiu do ar e o navegador interno
  não subia.

### Corrigido
- Scraper de Maps agora resolve o binário e o Node por plataforma (sem `.exe` nem
  caminho fixo do Windows) e lê o progresso ao vivo também do `stderr`, usado pelas
  builds de Linux — antes o contador ficava parado em zero.

## [2.0.0] - 2026-07-17

Salto grande: o ProspectOS deixou de ser "achador de leads sem site" e virou uma
ferramenta completa de prospecção — com análise real de sites, diagnóstico em PDF,
busca por mapa, estratégia por lead e um modo foco pra prospectar em ritmo.

### Adicionado

**Análise de sites (o coração da qualificação)**
- Detecção de **site ruim** além de "sem site": fora do ar, sem HTTPS/"não seguro",
  certificado SSL inválido, conteúdo misto, não adaptado para celular, página vazia,
  **site lento** (servidor demora a responder) e **feito em construtor pronto**
  (Wix, Canva, Google Sites, Webnode e afins). Site que existe mas afasta cliente
  também é lead — o pool de leads por busca aumenta bastante.
- **Raio-X do site**: extração do que a página realmente tem e o que falta
  (WhatsApp, telefone clicável, e-mail, redes, mapa, fotos, título, meta description,
  favicon) direto do HTML — dado real, nunca chute.
- Detecção de site **parado no tempo** pelo ano de copyright no rodapé.
- Checagem de disponibilidade mais inteligente: retry em falha transitória, e
  domínio que não resolve é diagnosticado como "pode ter expirado" (não "fora do ar").

**Diagnóstico em PDF**
- Relatório de presença digital de uma página, pronto pra mandar no WhatsApp:
  placar visual (reputação, desempenho, pontos a corrigir), problemas em linguagem
  leiga, raio-X em painéis e chamada final assinada com o nome do vendedor.
- Integração opcional com o **Google PageSpeed Insights** (nota oficial de
  desempenho e tempo de carregamento no celular).

**Busca por mapa (estilo segmentação do Facebook Ads)**
- Solte pinos num mapa (Leaflet + OpenStreetMap, sem chave de API), defina o raio
  de cada um e escolha nichos num catálogo clicável de 170+ opções por categoria.
  Cada pino roda uma busca geolocalizada; o rótulo do pino vira a cidade do lead.
- Busca de cidade/bairro e geocodificação reversa via Nominatim.

**Fluxo de prospecção**
- **Estratégia de abordagem por lead**: cenário detectado (sem site / fora do ar /
  inseguro / lento / construtor...), ângulo de venda, ganchos concretos e objeções
  com respostas prontas — determinístico, sem custo de IA.
- **Score de priorização** (0-100) combinando nota, volume de avaliações e situação
  do site, com ordenação da fila por score.
- **Sessão de prospecção**: modo foco, um lead por vez do mais quente ao mais frio,
  começando pelos follow-ups vencidos; abordagem em um clique (Enter/→/Backspace).
- **Tarefas de hoje**: follow-ups vencidos + leads quentes com WhatsApp preenchido.
- **Perfil do vendedor**: as copies de IA saem assinadas e na sua voz.

**Qualidade de vida**
- Filtro por situação do site na lista de leads.
- Botão "Reanalisar site" para atualizar status/problemas/raio-X na hora.
- Histórico de buscas do Maps.
- Busca global por atalho (Ctrl/Cmd + K): pula pra qualquer página ou acha um lead.
- Retomada de análise do Instagram interrompida.

### Alterado

- **Reengenharia dos prompts de IA**: arquitetura system + user, copy sempre em
  primeira pessoa do singular (voz de freelancer, não de agência), fechamento
  sorteado no servidor, follow-up que enxerga a mensagem anterior para variar de
  verdade, e classificação de perfis com JSON mode nativo.
- **Backend reorganizado**: o monólito `app.py` (~2.900 linhas) foi dividido em
  blueprints por domínio (`rotas_leads`, `rotas_instagram`, `rotas_analytics`,
  `rotas_config`) mais módulos dedicados (`ia`, `jobs`, `db`, `diagnostico`,
  `constantes`).
- **Instagram defensivo**: backoff exponencial com jitter, parada limpa em
  checkpoint/rate limit, e salvamento incremental que permite retomar a análise.
- **Redesign da interface**: heros e estados vazios padronizados, tiles de métrica
  com hierarquia, gráficos com paleta de marca, modais de lead mais largos e
  responsivos, tema claro/escuro consistente.

### Corrigido

- Race condition no disparo de buscas/análises simultâneas.
- 404/405 deixavam de ser tratados como erro interno.
- Leads do Instagram passam a ser deduplicados por username entre posts.
- Dados pessoais que estavam hardcoded no código foram removidos.

### Segurança

- Chaves de API salvas pela interface vão para o cofre de credenciais do sistema
  (Windows Credential Manager via `keyring`/DPAPI), não mais em texto puro no banco.
- Migração automática move chaves legadas do banco para o cofre no primeiro boot.
- `.gitignore` reforçado (arquivos temporários do SQLite, `.env` em qualquer nível).

## [1.x] - 2026-07

Versão inicial: CRM de prospecção com canais Google Maps e Instagram, geração de
mensagens por IA com fallback entre provedores, funil de status com Kanban,
follow-up com cadência, tags, analytics e exportação CSV.
