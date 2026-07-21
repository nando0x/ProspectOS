# Contribuindo com o ProspectOS

Obrigado pelo interesse! Este é um projeto mantido nas horas vagas, então o
processo é leve — só bom senso.

## Antes de abrir um PR

1. **Abra uma [issue](../../issues)** descrevendo o bug ou a ideia antes de codar
   algo grande. Evita retrabalho e alinha a direção.
2. Para PRs pequenos (fix de bug, melhoria de doc), pode mandar direto.
3. Leia os avisos de risco no [README](README.md#️-antes-de-usar) — o projeto faz
   scraping e automação de conta pessoal, e isso tem implicações.

## Ambiente de desenvolvimento

Pré-requisitos: Python 3.11+, Node.js 20+, Windows, Linux ou macOS.

```powershell
# Backend
cd backend
py -m pip install -r requirements.txt
copy .env.example .env        # preencha ao menos uma chave de IA

# Frontend
cd ../frontend
npm install
```

Suba os dois de uma vez com o `iniciar.bat` (Windows) ou `./iniciar.sh` (Linux/macOS)
na raiz. Backend em `:5000`, frontend em `:5173`.

## Rodando os testes

```powershell
# Backend (pytest) - sempre rode antes de mandar o PR
cd backend
py -m pytest

# Frontend (build + lint)
cd frontend
npm run build
npm run lint
```

Os testes do backend não dependem de rede, scraper ou banco real (usam SQLite
temporário e mocks dos provedores). Toda mudança de comportamento deve vir com
teste.

## Convenções de código

- **Nomes do domínio em português** (`leads`, `nichos`, `avaliar_site`,
  `gerar_mensagem`) — o vocabulário do negócio é pt-BR. Termos técnicos e libs
  ficam na forma original.
- **Backend**: Flask organizado em blueprints por domínio (`rotas_*.py`) + módulos
  dedicados (`ia.py`, `jobs.py`, `db.py`, `diagnostico.py`). Acesso ao banco sempre
  via `db.conectar()` com queries parametrizadas.
- **Frontend**: React + TypeScript. Server state com TanStack React Query; a camada
  é `services` (HTTP) → `hooks` (React Query) → `components`. Sem `any`.
- **Nunca** commite `.env`, `leads.db`, sessões do Instagram, CSVs de saída ou o
  binário do scraper — o `.gitignore` já cobre, mas confira com `git status` antes.

## Estilo de commit

Mensagens em português, no imperativo, com prefixo de tipo quando fizer sentido
(`feat:`, `fix:`, `refactor:`, `docs:`). Corpo explicando o *porquê* quando a
mudança não é óbvia.

Seja respeitoso nas discussões. É isso. 🙂
