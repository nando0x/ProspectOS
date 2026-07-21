# Arquitetura do ProspectOS Multiplataforma

## 1. Electron (desktop/)

### main.js

**Startup:**
1. `app.requestSingleInstanceLock()` — segunda instância é bloqueada e foca a existente
2. `resolverPaths()` — usa `app.getPath('userData/logs/temp/cache')` + fallbacks
3. `resolveRuntimeTarget()` — carrega `runtime-targets.json`, detecta target atual
4. `subirBackend()` — spawna backend com env vars `PROSPECTOS_*` completas
5. `aguardarReadiness()` — HTTP GET na porta até 200 OK ou timeout 15s
6. `criarJanela()` — `BrowserWindow` carregando `http://127.0.0.1:PORTA`

**Lifecycle macOS:**
- `window-all-closed` não encerra o app (comportamento macOS padrão)
- `activate` recria janela se backend ainda está vivo
- `before-quit` envia SIGTERM com grace period 10s, depois SIGKILL
- `will-quit` garante SIGKILL final

**Env vars passadas ao backend:**

```
PROSPECTOS_DATA_DIR
PROSPECTOS_LOG_DIR
PROSPECTOS_TEMP_DIR
PROSPECTOS_CACHE_DIR
PROSPECTOS_RESOURCE_DIR
PROSPECTOS_RUNTIME_MANIFEST
PROSPECTOS_PLAYWRIGHT_RUNTIME_MANIFEST
PROSPECTOS_RUNTIME_TARGET
PROSPECTOS_NO_BROWSER=1
```

### runtime-target.js

Resolução de binários:
1. Carrega `runtime-targets.json` (validate: schemaVersion, targets, backend/scraper name)
2. Detecta target via `process.platform` + `process.arch`
3. Em modo packaged: `safeJoin(resourcesPath, target.name)`
4. Em dev: `safeJoin(devRoot, 'backend/dist/ProspectOS/' + basename)`
5. `validateExecutable()` — existe, não é diretório, tem permissão de execução (POSIX)

### electron-builder.yml

- `extraResources`: backend, scraper, shared/ (manifests)
- `mac`: target `dir` + `arm64` (sem DMG)
- `win`: target `nsis`
- `afterPack.js` condicionado a `win32` (rcedit ignorado no macOS)
- `icon: build/icon.icns` (gerado de PNG no PR 6)

---

## 2. Backend (backend/)

### Flask + Waitress

- Flask montado em `backend/app.py`
- Blueprints: `rotas_leads`, `rotas_instagram`, `rotas_analytics`, `rotas_config`
- Waitress serve em porta dinâmica, escreve `LISTENING_ON=PORTA` no stdout
- Frontend React servido estaticamente via Flask quando empacotado
- Frontend em `localhost:5173` (Vite dev) quando em desenvolvimento

### paths.py

Precedência:
1. `PROSPECTOS_*` env var
2. Fallback nativo por plataforma (macOS: `~/Library/Application Support/...`,
   Windows: `%APPDATA%`, Linux: `$XDG_DATA_HOME`)
3. PyInstaller: `sys._MEIPASS` para resources

Diretórios criados no startup: `DIR_DADOS/backups`, `DIR_DADOS/saidas`,
`DIR_DADOS/instagram/sessao`, `DIR_DADOS/instagram/comentarios`.

### Database (db.py)

- SQLite WAL mode, `leads.db` em `DIR_DADOS`
- `fazer_backup_banco()` antes de operações em massa (mantém 20 backups)
- Keyring: macOS Keychain via `keyring.backends.macOS.Keyring`
- Migração automática de chaves plaintext → keyring no startup

### Runtime Targets (runtime_targets.py)

Mirror Python do `runtime-target.js`. Funções principais:
- `current_target()` — detecta `sys.platform` + `platform.machine()`
- `resolve_scraper()` — resolve path do scraber via manifesto
- `resolve_resource()` — resolve qualquer recurso por target + resource_root
- `validate_executable()` — existe, não é diretório, `os.X_OK`

### PlaywrightRuntimeManager (playwright_runtime/)

Gerenciador completo do runtime Playwright.

**Estrutura em disco** (dentro de `DIR_CACHE/playwright/`):

```
cache/playwright/
├── downloads/          # arquivos .tgz baixados (cache de download)
├── staging/            # extração e montagem atômica
├── installations/
│   └── darwin-arm64/
│       └── pw-1.60.0-chromium-1223/
│           ├── driver/
│           │   ├── node              (Node v24.18.0 arm64)
│           │   └── package/          (playwright-core 1.60.0)
│           ├── browsers/
│           │   ├── chromium-1223/    (Chromium arm64, 356 MB)
│           │   ├── chromium_headless_shell-1223/ (190 MB)
│           │   └── ffmpeg-1011/      (2.5 MB)
│           ├── licenses/
│           └── installation-manifest.json
├── locks/
└── diagnostics/
```

**Fluxo de instalação:**
1. Download playwright-core do npm registry (SHA-256 verificado)
2. Download Node.js do nodejs.org (SHA-256 verificado)
3. Extração para `staging/`
4. Montagem do driver (node + package/)
5. Validação do driver (`node --version`, `cli.js --version`)
6. Instalação do Chromium via `cli.js install chromium`
7. Validação dos browsers (diretórios por revision)
8. Cópia de licenças
9. Publicação atômica (mv staging → installations/)
10. Escrita do manifest de instalação

**API pública:**
- `ensure_ready()` — verifica estado, instala ou repara conforme necessário
- `inspect()` — estado atual, componentes, erros
- `validate()` — quick ou full validation
- `repair()` — reinstala mantendo backup da anterior
- `remove()` — remove instalação
- `get_environment()` — retorna `PLAYWRIGHT_DRIVER_PATH` e `PLAYWRIGHT_BROWSERS_PATH`
- `get_diagnostics()` — relatório completo para debug

**Limitações conhecidas:**
- Só implementado para `darwin-arm64` (spec só tem esse runtime)
- Cache do driver 1.60.0 no CDN da Microsoft está quebrado (404)
  - Solução: montagem manual via npm registry + nodejs.org (validada no Gate 1C)

### Scraper Process Runner (scraper_process.py)

Runner de processo com leitura concorrente de stdout/stderr via filas.

**Características:**
- Threads separadas para stdout e stderr (evita deadlock)
- Parse de linhas JSON com categorização (PROGRESS, LIFECYCLE, ERROR, DIAGNOSTIC)
- Deduplicação de mensagens por `(job_id, message, stream)`
- Tail dos últimos 50 eventos de cada stream
- Timeout configurável com `process.terminate()` → grace period → `process.kill()`
- Suporte a `cancel_event` via `threading.Event`

### Scraper Runtime Bridge (scraper_runtime.py)

Conexão entre `jobs.py` e `PlaywrightRuntimeManager`:
1. Detecta target
2. Resolve scraper via `runtime_targets.resolve_scraper()`
3. Se `darwin-arm64`: chama `manager.ensure_ready()`, obtém env vars
4. Se outros targets: retorna scraper path + env vazio (fluxo legado)
5. Valida paths do runtime (PLAYWRIGHT_DRIVER_PATH, PLAYWRIGHT_BROWSERS_PATH)

### Jobs (jobs.py)

Motor de background com persistência em tabela `jobs`:
- `_rodar_busca_em_background` — scraper + processamento
- `_executar_scraper` — decide entre runner novo (darwin-arm64) ou legado
- `_executar_scraper_com_runner` — usa ScraperProcessRunner
- Flag `use_new_runner = target == "darwin-arm64"` em `_executar_scraper`

### Scripts de build

**`scripts/build_backend.py`:**
- Valida ambiente (PyInstaller instalado, arm64, frontend/dist)
- Builda frontend (opcional)
- Executa PyInstaller com spec multiplataforma
- Valida output (Mach-O arm64, sem dependências externas)

**`scripts/build_desktop.py`:**
- Orquestrador completo (7 steps)
- Step 1: valida ambiente (Python, PyInstaller, Go, Node, Xcode)
- Step 2: build frontend
- Step 3: build backend (PyInstaller)
- Step 4: build scraper (Go, clona upstream tag v1.16.3, compila arm64)
- Step 5: stage resources (shared manifests, verifica backend/scraper)
- Step 6: valida staging
- Step 7: electron-builder (--mac dir --arm64)
- Step 8: valida .app (todos executáveis arm64, manifestos, permissões)

---

## 3. Melhorias futuras desejáveis (fora do escopo atual)

Melhorias que não são necessárias para o build local funcional, mas seriam
desejáveis em uma evolução futura:

- CI/CD matrix automatizando builds para 3 plataformas
- DMG, NSIS Installer e AppImage como artefatos de distribuição
- Smoke + E2E + regressão Windows como gates de qualidade automatizados
- Eliminar bifurcação de fluxo (todo target usando ScraperProcessRunner)
- Node.js do sistema completamente eliminado como dependência
- ProcessSupervisor centralizado
