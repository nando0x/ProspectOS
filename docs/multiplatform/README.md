# ProspectOS Multiplataforma

## Visão geral

ProspectOS é uma aplicação desktop de prospecção de leads com Electron + React 19
(frontend) + Flask 3.1 (backend) + SQLite. O backend utiliza sidecars externos:
um scraper Go (Google Maps via Playwright) e o runtime Playwright (Node + Chromium).

Originalmente Windows-only, esta iniciativa adapta o ProspectOS para executar
nativamente em **macOS Apple Silicon (darwin-arm64)**, preservando a compatibilidade
com Windows e preparando o terreno para Linux e Mac Intel.

**Validado em:** 2026-07-20 — MacBook Apple M4, macOS 26.4, Python 3.14.5,
Node 22.22.2, Electron 38.2.0.

---

## Estado original (branch `main` @ `bebc2f1`)

| Componente | Estado original | Limitação |
|---|---|---|
| Electron | Windows build | `electron-builder.yml` só target `win`, `main.js` hardcoded `.exe` |
| Backend | `ProspectOS.exe` nome hardcoded | `main.js:39,42` e `prospectos.spec:31,36` |
| Scraper | `google-maps-scraper.exe` hardcoded | `jobs.py:315` sem resolução por plataforma |
| Node | `node.exe` + fallback `C:\Program Files\` | `jobs.py:436,442` |
| Dados | `%APPDATA%` | `main.js:46`, `paths.py:33` |
| Credenciais | `keyring.backends.Windows` | `prospectos.spec:45` sem backend macOS |
| PyInstaller | spec Windows | só `.exe` references |
| Scripts | `.bat` e `.ps1` | dev workflow Windows-only |
| Ícone | `.ico` | sem `.icns` |

---

## Arquitetura atual (branch `develop` @ `b900821`)

```mermaid
flowchart TD
    Electron["Electron (main.js)"]
    RuntimeManifest["RuntimeManifest<br/>(runtime-target.js / runtime_targets.py)"]
    PlatformPaths["PlatformPaths<br/>(paths.py + main.js)"]
    Backend["Backend PyInstaller<br/>(Flask + Waitress + SQLite)"]
    PRM["PlaywrightRuntimeManager<br/>(8 módulos Python)"]
    ScraperRunner["ScraperProcessRunner<br/>(scraper_process.py)"]
    Scraper["google-maps-scraper<br/>(Go arm64)"]
    Playwright["Playwright Runtime<br/>(Node + Chromium + FFmpeg)"]
    Keyring["keyring (macOS Keychain)"]
    Frontend["Frontend React 19<br/>(servido pelo Flask)"]

    Electron --> PlatformPaths
    Electron --> RuntimeManifest
    Electron --> Backend
    Electron --> Frontend
    Backend --> PlatformPaths
    Backend --> RuntimeManifest
    Backend --> ScraperRunner
    Backend --> Keyring
    ScraperRunner --> Scraper
    ScraperRunner --> PRM
    PRM --> Playwright
    Scraper --> Playwright
```

### Fluxo de startup

1. Electron inicia, `main.js:56` resolve paths via `app.getPath()` e env vars
2. `runtime-target.js:180` carrega `runtime-targets.json` e resolve o target atual
3. Electron spawna o backend PyInstaller com env vars `PROSPECTOS_*`
4. Backend lê `paths.py`, configura diretórios, inicializa banco SQLite + keyring
5. Backend escreve `LISTENING_ON=PORTA` no stdout
6. Electron detecta porta, faz readiness check HTTP, carrega frontend
7. Na primeira busca Maps, `scraper_runtime.py` aciona `PlaywrightRuntimeManager`
8. PRM baixa Node + playwright-core + Chromium (download sob demanda, ~938MB)
9. `ScraperProcessRunner` executa scraper Go com ambiente controlado
10. Progresso lido de stderr, convertido em eventos, enviado ao frontend

---

## Estado da iniciativa

### PR/Fase 0 — Dependências Python

| Campo | Valor |
|---|---|
| **Status** | **REVERTIDO (quebrado)** |
| Commit | `42c9040` (original, requests 2.32.3 -> 2.34.2) |
| Arquivo | `backend/requirements.txt` |
| Evidência | `git diff 42c9040 HEAD -- backend/requirements.txt` confirma reversão |
| Risco | `instagrapi 2.18.3` exige `requests>=2.34.2`, pin atual `2.32.3` é impossível de resolver |
| Ação | Reaplicar bump para `requests==2.34.2` |

O PR 0 foi criado no commit `42c9040` e posteriormente revertido. O arquivo
atual em `HEAD` contém `requests==2.32.3`, que conflita com `instagrapi==2.18.3`
(requer `>=2.34.2`). `pip install -r requirements.txt` falha.

**Gate relacionado:** `docs/gates/GATE1_RUNTIME_M4.md` — blocante P1 confirmado.

### PR/Fase 1 — PlatformPaths

| Campo | Valor |
|---|---|
| **Status** | **COMPLETO** |
| Commit | `78badc4` |
| Arquivos | `backend/paths.py`, `backend/app.py`, `desktop/main.js`, `tests/test_paths.py` |
| Evidência | 516 linhas adicionadas, testes passando, env vars funcionais |

**Paths por plataforma:**

| Finalidade | macOS | Windows | Linux |
|---|---|---|---|
| Dados | `~/Library/Application Support/ProspectOS` | `%APPDATA%\ProspectOS` | `$XDG_DATA_HOME/ProspectOS` |
| Logs | `~/Library/Logs/ProspectOS` | `%APPDATA%\ProspectOS\logs` | `$XDG_DATA_HOME/ProspectOS/logs` |
| Cache | `~/Library/Caches/ProspectOS` | `%LOCALAPPDATA%\ProspectOS\cache` | `$XDG_CACHE_HOME/ProspectOS` |
| Temp | `$TMPDIR/ProspectOS` | `%TMP%\ProspectOS` | `/tmp/ProspectOS` |

**Precedência:**
1. `PROSPECTOS_DATA_DIR` / `PROSPECTOS_LOG_DIR` / `PROSPECTOS_CACHE_DIR` / `PROSPECTOS_TEMP_DIR` / `PROSPECTOS_RESOURCE_DIR` (env var)
2. Electron `app.getPath()` (modo empacotado)
3. Fallback nativo por plataforma

### PR/Fase 2 — RuntimeManifest

| Campo | Valor |
|---|---|
| **Status** | **COMPLETO** |
| Commit | `55f92b0` |
| Arquivos | `shared/runtime-targets.json`, `backend/runtime_targets.py`, `desktop/runtime-target.js`, testes |
| Evidência | 1407 linhas adicionadas, 9 arquivos, testes passando |

**Targets canônicos:**
- `darwin-arm64` (Apple Silicon)
- `darwin-x64` (Intel Mac)
- `win32-x64` (Windows)
- `linux-x64` (Linux)

**Schema manifesto:**
```json
{
  "schemaVersion": 1,
  "targets": {
    "darwin-arm64": {
      "backend": { "name": "backend/ProspectOS" },
      "scraper": { "name": "scraper/google-maps-scraper" }
    }
  }
}
```

### PR/Fase 3 — PlaywrightRuntimeManager

| Campo | Valor |
|---|---|
| **Status** | **COMPLETO** |
| Commit | `dc0a9ce` |
| Arquivos | 22 novos, 4058 linhas adicionadas |
| Evidência | 8 módulos Python, CLI técnica, 160+ testes unitários, smoke real |

**Componentes:**
- `download.py` — download com checksums e retry
- `errors.py` — 12+ tipos de erro específicos
- `extractor.py` — extração segura de `.tgz`
- `lock.py` — lock atômico via sistema de arquivos
- `manager.py` — orquestrador principal (893 linhas)
- `manifest.py` — manifesto de instalação
- `models.py` — dataclasses de estado
- `validator.py` — validação de integridade

**Licenças:** playwright-core (Apache 2.0), Node.js (MIT), Chromium (BSD),
FFmpeg (LGPL 2.1).

### PR/Fase 4 — Integração do scraper

| Campo | Valor |
|---|---|
| **Status** | **COMPLETO** |
| Commit | `35cde07` |
| Arquivos | `scraper_process.py`, `scraper_runtime.py`, `jobs.py`, testes |
| Evidência | 1195 linhas adicionadas, smoke real darwin-arm64 |

**Detalhes:**
- `ScraperProcessRunner`: lê stdout+stderr concorrentemente, progresso via
  callbacks, timeout, SIGTERM com grace period, SIGKILL como fallback
- `scraper_runtime.py`: bridge que resolve scraper + prepara runtime Playwright
- Leitura de progresso do **stderr** (compatível com scraper v1.16.3)
- Atualmente condicionado a `darwin-arm64`; outros targets usam fluxo legado
- Gate 1B (`docs/gates/GATE1B_REPORT.md`) validou scraper arm64 nativo

### PR/Fase 5 — Backend PyInstaller macOS

| Campo | Valor |
|---|---|
| **Status** | **COMPLETO** |
| Commit | `c2e1e12` |
| Artefato | `backend/dist/ProspectOS/` (95 MB, 262 arquivos) |
| Evidência | Mach-O 64-bit executable arm64, sem dependências Homebrew |

**Spec:** `--onedir`, platform-conditional hidden imports, frontend/dist incluído,
manifesto runtime incluído, keyring macOS incluso.

**Script:** `scripts/build_backend.py` com flags `--clean`, `--skip-frontend`,
`--dist-dir`, `--work-dir`.

### PR/Fase 6 — Electron macOS

| Campo | Valor |
|---|---|
| **Status** | **COMPLETO** (build local, sem assinatura) |
| Commit | `c254a83` |
| Artefato | `desktop/saida/mac-arm64/ProspectOS.app` |
| Evidência | Todos 3 executáveis são Mach-O arm64 |

**Artefato verificado:**
- `ProspectOS.app/Contents/MacOS/ProspectOS` — Mach-O 64-bit executable arm64
- `Resources/backend/ProspectOS` — Mach-O 64-bit executable arm64
- `Resources/scraper/google-maps-scraper` — Mach-O 64-bit executable arm64
- `Resources/shared/runtime-targets.json` — presente
- `Resources/shared/playwright-runtime-targets.json` — presente
- `Resources/icon.icns` — presente
- `Resources/app.asar` — presente

**Script:** `scripts/build_desktop.py` — orquestrador completo (7 passos).

### Notarização e assinatura

| Campo | Valor |
|---|---|
| **Status** | **PENDENTE** |
| Evidência | Build usa `CSC_IDENTITY_AUTO_DISCOVERY=false` |
| Necessário | Apple Developer Program ($99/ano), Developer ID, Hardened Runtime |

---

## Lacunas entre planejamento e implementação

| Item | Planejado | Implementado | Evidência | Ação |
|---|---|---|---|---|
| **PR 0** requests bump | `2.34.2` | `2.32.3` (revertido) | `git diff 42c9040 HEAD` | Reaplicar bump |
| **Scraper arm64** | Binário no bundle | Compilado e incluso | `file` no .app | OK |
| **Playwright Runtime** | Download gerenciado | `PlaywrightRuntimeManager` | 160+ testes | OK |
| **Windows build** | Preservado | Config estática, sem build real | `electron-builder.yml` win target | Testar no Windows |
| **Linux build** | Target no manifesto | Só contrato JSON | `runtime-targets.json` | Sem build, sem testes |
| **darwin-x64** | Target no manifesto | Só contrato JSON | Mesmo manifesto | Sem build, sem testes |
| **Notarização** | DMG distribuível | Nada implementado | Apenas plano na auditoria | Pendente |
| **CI/CD** | Workflows | Nenhum workflow | `find .github -name '*.yml'` vazio | Pendente |
| **Keyring macOS smoke** | Validado em /tmp | Validado em Gate 1 | GATE1_RUNTIME_M4.md | Repetir em .app assinado |
| **Frontend docs** | Texto dinâmico | Ainda cita `.exe` | `FaqDoc.tsx`, `GoogleMapsDoc.tsx` | Atualizar |

---

## Build e validação (comandos reais)

### Dependências

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt  # FALHA: requests 2.32.3 conflita com instagrapi

# Frontend
cd frontend && npm ci

# Desktop
cd desktop && npm ci
```

### Testes

```bash
# Backend (pytest)
cd backend && python -m pytest -v

# Desktop (Node test)
cd desktop && npm test  # testa runtime-target.js
```

### Build backend (PyInstaller)

```bash
python scripts/build_backend.py --clean
python scripts/build_backend.py --skip-frontend  # se frontend/dist já existe
```

### Build desktop (Electron .app)

```bash
python scripts/build_desktop.py  # orquestrador completo (7 passos)
python scripts/build_desktop.py --skip-scraper  # se scraper já foi compilado
python scripts/build_desktop.py --clean         # limpa tudo antes
```

### Diagnóstico

```bash
# CLI do Playwright Runtime
python -m backend.tools.playwright_runtime_cli --help
python -m backend.tools.playwright_runtime_cli inspect
python -m backend.tools.playwright_runtime_cli diagnostics
python -m backend.tools.playwright_runtime_cli validate --full
```

### Comandos ainda não implementados

- Testes E2E do Electron empacotado: **não implementado**
- Smoke test automatizado do `.app`: **não implementado**
- Build Windows CI: **não implementado**
- Build Linux: **não implementado**

---

## Riscos

### Arquitetura
- `requirements.txt` quebrado impede instalação limpa — P0
- Condicional `target == "darwin-arm64"` em `jobs.py` cria bifurcação de fluxo
- Node.js do sistema ainda referenciado em manifestos (não usado, mas confunde)

### macOS
- Build sem assinatura — não passa no Gatekeeper
- Apple Developer Program obrigatório ($99/ano)
- Hardened Runtime + entitlements precisam ser mapeados
- Chromium + Node + scraper precisam ser assinados ou exemptados
- Notarização nunca foi testada

### Windows
- Build Windows não foi executado desde as mudanças de paths/manifest
- `electron-builder.yml` ainda tem target NSIS
- Scripts `.bat` e `.ps1` obsoletos para o novo fluxo
- Dados existentes em `%APPDATA%\ProspectOS` precisam manter compatibilidade

### Linux
- Apenas contrato no manifesto (`linux-x64`)
- `keyring.backends.SecretService` no spec mas nunca testado
- Sem build, sem smoke, sem suporte real

### Distribuição
- `electron-updater` configurado para GitHub Releases, mas nunca testado no macOS
- DMG não gerado (build usa `--mac dir`)
- Sem SBOM, sem checksums públicos, sem canal de atualização

---

## Próximas ações imediatas

### 1. Reaplicar bump do requests (P0)

**Objetivo:** `pip install -r requirements.txt` funciona novamente.
**Por que agora:** Impede qualquer instalação limpa, desenvolvimento, testes e CI.
**Pré-condições:** Nenhuma.
**Entrega:** Commit alterando `requests==2.32.3` para `requests==2.34.2` em
`backend/requirements.txt`.
**Critério de aceite:** `pip install -r requirements.txt` exit 0, `pip check`
sem quebras, `python -m pytest` 293+ passando.

### 2. Validar smoke do .app (P1)

**Objetivo:** Confirmar que o `.app` existente abre, backend sobe, frontend carrega.
**Por que agora:** O build do Electron (.app) foi gerado mas nunca foi executado
como aplicativo — só validado estaticamente (file/lipo).
**Pré-condições:** requests corrigido (ação 1).
**Entrega:** Relatório de smoke test: app abre, frontend carrega, scraper executa,
Instagram loga, PDF gera, encerramento sem órfãos.
**Critério de aceite:** Checklist completo (ver `docs/multiplatform/roadmap.md`
seção Release macOS).

### 3. Assinar sidecars internos (P1)

**Objetivo:** Assinar backend PyInstaller, scraper Go, Node e Chromium com
Developer ID Application.
**Por que agora:** Sem assinatura individual, o Hardened Runtime bloqueia
subprocessos.
**Pré-condições:** Apple Developer Program ativo.
**Entrega:** Script de assinatura para todos os executáveis em
`Resources/backend/`, `Resources/scraper/` e runtime Playwright.
**Critério de aceite:** `codesign -dv` em cada executável mostra equipe
válida e permissões corretas.

### 4. Preparar notarização (P2)

**Objetivo:** Enviar .app para notarização da Apple e stapling.
**Por que agora:** Único caminho para distribuição pública sem aviso do Gatekeeper.
**Pré-condições:** Assinatura completa (ação 3), Developer ID Application,
App-specific password.
**Entrega:** `.app` notarizado + stapled + DMG.
**Critério de aceite:** `spctl --assess --verbose --type execute` passa.

### 5. Executar regressão Windows (P2)

**Objetivo:** Confirmar que mudanças multiplataforma não quebraram Windows.
**Por que agora:** Windows é a plataforma original de produção.
**Pré-condições:** Ação 1 concluída.
**Entrega:** Build Windows + smoke test + suite de testes passando.
**Critério de aceite:** Testes passam, scraper executa, leads persistem,
keyring funciona, upgrade de instalação existente preserva dados.

---

## Links

- [Arquitetura detalhada](architecture.md)
- [Decisões arquiteturais (ADRs)](decisions.md)
- [Roadmap e release checklist](roadmap.md)
- Auditoria original: `docs/gates/AUDITORIA_MULTIPLATAFORMA.md`
- Gate 1 — Runtime M4: `docs/gates/GATE1_RUNTIME_M4.md`
- Gate 1B — Scraper arm64: `docs/gates/GATE1B_REPORT.md`
- Gate 1C — Bootstrap Playwright: `docs/gates/GATE1C_REPORT.md`
- PR 0 — Dependências: `docs/PR0-resolucao-dependencias.md`
