# CLAUDE.md

Orientações para o Claude Code trabalhar neste repositório.

## O que é

**ProspectOS** — ferramenta local (Windows) de prospecção de leads para quem vende sites/landing pages
para pequenos negócios. Dois canais de captação (**Google Maps** e **Instagram**) alimentam um CRM
único com funil, follow-up, mensagens geradas por IA, diagnóstico em PDF e analytics.

Não é SaaS: roda na máquina do usuário, com SQLite local. Existe também um shell Electron
(`desktop/`) que empacota tudo num app instalável com janela interna de WhatsApp Web.

## Comandos

```powershell
# Setup (uma vez)
cd backend;  py -m pip install -r requirements.txt;  copy .env.example .env
cd frontend; npm install

# Rodar em dev — sobe backend (:5000) + frontend (:5173) e abre o navegador
.\iniciar.bat

# Ou manualmente, em dois terminais
cd backend;  py app.py          # API em :5000 (waitress; PROSPECCAO_DEBUG=true usa o dev server do Flask)
cd frontend; npm run dev        # Vite em :5173, com proxy /api -> :5000

# Testes e checagens (rodar antes de qualquer entrega)
cd backend;  py -m pytest
cd frontend; npm run build      # tsc -b && vite build
cd frontend; npm run lint       # oxlint

# Um teste só
cd backend; py -m pytest tests/test_app.py::nome_do_teste -q

# App de desktop
cd desktop; npm start           # Electron apontando pro backend
cd desktop; npm run dist        # instalador Windows (electron-builder)
```

**Estado atual do ambiente nesta máquina:** dependências ainda **não instaladas**
(`frontend/node_modules` ausente, `pytest` não disponível), `backend/google-maps-scraper.exe`
ausente. `py` resolve para Python 3.14 e `node` para v24.

## Arquitetura

### Backend (`backend/`) — Flask 3.1 + SQLite, tudo em português no domínio

`app.py` só monta o Flask, registra os blueprints, prepara o schema e sobe o waitress.
A lógica mora nos módulos:

| Módulo | Responsabilidade |
|---|---|
| `rotas_leads.py` | CRM do canal Maps + disparo/status da busca + export CSV + PDF |
| `rotas_instagram.py` | CRM do canal Instagram + disparo/retomada da análise de posts |
| `rotas_analytics.py` | métricas, funis (por canal e combinado), meta semanal, tarefas de hoje |
| `rotas_config.py` | chaves de IA, fonte do Maps, perfil do vendedor, proxies, templates |
| `rotas_conversa.py` | cockpit de negociação: histórico de mensagens por lead + análise por IA |
| `ia.py` | provedores (Gemini → Groq → NVIDIA), prompts system/user, motor de fallback |
| `jobs.py` | jobs de background (scraper do Maps, análise do Instagram) + tabela `jobs` |
| `processar.py` | pipeline do CSV do scraper, análise/qualificação de site, schema e migrações |
| `fontes_maps.py` | fonte alternativa: Google Places API (New), gerando o mesmo CSV do scraper |
| `diagnostico.py` | diagnóstico em PDF (fpdf2) + PageSpeed Insights opcional |
| `db.py` | `conectar()`, configs, cofre de credenciais (keyring), backup do banco |
| `paths.py` | separação recursos read-only × dados graváveis |
| `constantes.py` / `validacao.py` | limites, enums de domínio, validação de entrada |
| `instagram/` | `login.py`, `raspar_comentarios.py`, `enriquecer_perfis.py` (instagrapi) |

Todas as rotas ficam sob `/api/*`. Rotas não-`/api` caem no fallback SPA que serve
`frontend/dist` (quando existe) — em dev quem serve a interface é o Vite.

### Frontend (`frontend/src/`) — React 19 + TS + Vite 8 + Tailwind 4

Camadas, sempre nesta direção: **`services/` (HTTP) → `hooks/` (React Query) → `components/`**.

- `pages/` — uma tela por rota (Dashboard, LeadsMaps, Instagram, Sessão, Tarefas, Analytics, Conversa, Configurações, Documentação)
- `components/` — agrupados por domínio (`leads/`, `lead-detail/`, `instagram/`, `dashboard/`, `conversa/`, `configuracoes/`, `filters/`, `shared/`, `ui/` = shadcn)
- `lib/` — `estrategia.ts` (estratégia de abordagem determinística, sem IA), `nichos.ts` (catálogo 170+), formatters, queryClient
- `types/` — espelham o schema do backend; **sem `any`**
- Alias `@/` → `frontend/src`

## Regras importantes

### Caminhos: recurso vs. dado (`paths.py`)
Há dois modos de execução — **fonte** (clone, `py app.py`) e **empacotado** (PyInstaller, `sys.frozen`).
Empacotado, o código vira bundle read-only e os dados do usuário vão para `%APPDATA%\ProspectOS`.
Por isso, nunca monte caminhos com `Path(__file__)`:

- arquivo que o app só **lê** e vem junto do código (scraper `.exe`, `.py` do instagram, build do frontend) → `paths.caminho_recurso(...)`
- arquivo que o app **escreve** (`leads.db`, `backups/`, `saidas/`, `logs/`, `queries.txt`, `instagram/sessao/`) → `paths.caminho_dados(...)`

### Banco
- Sempre `db.conectar()` (WAL, `busy_timeout`, `foreign_keys=ON`) e **queries parametrizadas**.
- Módulos devem ler o caminho como `db.CAMINHO_BANCO` (atributo do módulo, não `from db import CAMINHO_BANCO`)
  — é isso que deixa os testes redirecionarem o app inteiro para um banco temporário com um único
  `monkeypatch.setattr(db, "CAMINHO_BANCO", ...)`.
- Mudanças de schema entram em `processar.preparar_banco()` como migração idempotente
  (`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE` guardado). Tabelas: `leads`, `historico_status`,
  `instagram_posts`, `instagram_leads`, `historico_status_instagram`, `templates_mensagem`,
  `configuracoes`, `jobs`, `mensagens_conversa`, `analises_conversa`.

### Segredos
Chaves de API (`gemini`, `groq`, `nvidia`, `pagespeed`, `places`) vão para o **cofre do sistema**
(Windows Credential Manager via `keyring`), nunca em plaintext no `leads.db` — o banco entra nos
backups automáticos, o cofre não. Prioridade de leitura em `db.obter_config()`: cofre → tabela
`configuracoes` → variável de ambiente/`.env`. Nunca logue nem devolva o valor de uma chave numa resposta.

### IA
Toda geração passa por `ia.executar_com_fallback()`, que tenta os provedores em ordem
(`ORDEM_PROVEDORES_IA`) com cooldown de 5 min para quem estourou cota. Prompts sempre em par
**system** (persona + perfil do vendedor + regras) / **user** (dados do lead). Decisões que pedem
variação (fechamento, horário) são **sorteadas no servidor**, não delegadas ao modelo.
Nenhuma feature deve ficar bloqueante se a IA falhar.

### Scraping e WhatsApp
- O canal Instagram automatiza a **conta pessoal** do usuário via `instagrapi` — risco real de
  checkpoint/ban. Mudanças ali devem preservar o comportamento defensivo: backoff exponencial com
  jitter, parada limpa em checkpoint/rate limit, salvamento incremental para permitir retomada.
- A ingestão do WhatsApp (`rotas_conversa.py` + `desktop/preload-whatsapp.js`) é **passiva**: só lê o
  chat que o usuário já abriu, nunca navega nem varre conversas, e **nunca envia mensagem sozinha**.
  Não introduza envio automático nem navegação ativa.
- O vínculo mensagem→lead é feito por telefone; número que não casa é descartado em silêncio.

## Convenções

- **Domínio em português** (`leads`, `nichos`, `avaliar_site`, `gerar_mensagem`, `place_id`);
  termos técnicos e nomes de libs ficam na forma original. Vale para código, testes e commits.
- **Backend**: blueprints por domínio + módulos dedicados; erros não tratados viram 500 genérico com
  detalhe em `logs/prospeccao.log` (`HTTPException` passa direto, para 404/405 não virarem erro interno).
- **Frontend**: server state só via React Query; nada de `fetch` solto em componente.
- **Testes**: `pytest` no backend, sem rede, sem scraper e sem banco real (SQLite temporário + mocks
  dos provedores). Toda mudança de comportamento vem com teste.
- **Commits**: português, imperativo, com prefixo (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`),
  escopo entre parênteses quando ajudar (`feat(leads): ...`). Corpo explica o *porquê*.
- **Nunca commitar**: `.env`, `leads.db` (e `leads.db-*`), `backups/`, `saidas/`, `queries.txt`,
  `instagram/sessao/`, `instagram/comentarios/`, `google-maps-scraper.exe`, `logs/`, `porta.txt`.
  O `.gitignore` cobre, mas confira com `git status`.

## Dependências externas

- **`backend/google-maps-scraper.exe`** — binário de terceiros ([gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper/releases/latest)),
  não versionado. Baixar a release Windows, renomear para exatamente `google-maps-scraper.exe` e colocar
  ao lado de `app.py`. Sem ele **só** o canal Maps para (o Instagram é independente). Alternativa sem
  binário: *Configurações → Fonte de dados → Google Places API*.
- **Login do Instagram** — `cd backend; py instagram\login.py SEU_USUARIO` (uma vez; gera
  `instagram/sessao/session-<user>.json`). Use conta secundária.
- **Chave de IA** — ao menos uma entre Gemini / Groq / NVIDIA, via tela de Configurações
  (preferido, vai pro cofre) ou `backend/.env`.

## Plataforma

Windows apenas: os `.bat`/`.ps1`, o binário do scraper, o `keyring` via DPAPI e o empacotamento
(PyInstaller + electron-builder + Inno Setup em `instalador/prospectos.iss`) são específicos da plataforma.
