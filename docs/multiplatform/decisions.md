# Architecture Decision Records — ProspectOS Multiplataforma

## ADR-001 — Manter Electron como runtime desktop

**Status:** ACEITA

**Contexto:** O ProspectOS original usava Electron para Windows. Para
multiplataforma, considerar alternativas como Tauri (Rust), reescrita web
pura, ou framework nativo (SwiftUI + Python).

**Decisão:** Manter Electron. O investimento em Electron já existe (código,
configuração, auto-update), a migração de usuários Windows existentes seria
custosa, e Electron suporta arm64 nativamente.

**Alternativas rejeitadas:**
- Tauri: exigiria reescrever o main.js e adaptar o sidecar Python
- SwiftUI + Python: stack split, sem reuso dos módulos Python existentes

**Consequências:** Bundle maior (~200MB), mas sem custo de reescrita. Auto-update
via `electron-updater` funciona em todas as plataformas.

**Evidências:** `desktop/package.json` (Electron 38.2.0), `desktop/main.js`
(já adaptado para macOS lifecycle).

---

## ADR-002 — Mac M4 (darwin-arm64) como primeiro target

**Status:** ACEITA

**Contexto:** Três plataformas possíveis, recursos limitados. Escolher ordem.

**Decisão:** Implementar darwin-arm64 primeiro. O desenvolvedor possui hardware
M4, e o Apple Silicon representa o maior mercado de desktop não-Windows.

**Alternativas rejeitadas:**
- Windows primeiro: já funciona, sem necessidade de refatoração
- Linux primeiro: menor participação no mercado do app (windows-only até então)

**Consequências:** Código é testado e comprovado em arm64 antes de x64. Linux
e Mac Intel terão suporte depois.

**Evidências:** Commits PR 5 (c2e1e12) e PR 6 (c254a83) focados em arm64.

---

## ADR-003 — Builds nativos por plataforma, sem cross-compile

**Status:** ACEITA

**Contexto:** PyInstaller e electron-builder suportam cross-compile limitado.

**Decisão:** Cada plataforma gera seu próprio build nativamente. PyInstaller
gera Mach-O arm64 no macOS, PE32+ no Windows, ELF no Linux. electron-builder
builda o `.app` no macOS, NSIS no Windows.

**Consequências:** CI/CD precisará de runners nativos para cada plataforma.
Sem risco de cross-compile silencioso quebrado.

**Evidências:** `scripts/build_desktop.py` valida `arm64` antes de buildar.

---

## ADR-004 — RuntimeManifest compartilhado (JSON) entre Electron e backend

**Status:** ACEITA

**Contexto:** Tanto Electron (main.js) quanto backend Python (jobs.py) precisam
resolver nomes de binários por plataforma. Sem manifesto, cada lado resolve
independentemente.

**Decisão:** Criar `shared/runtime-targets.json` como fonte única da verdade.
Electron usa `runtime-target.js` para ler; backend usa `runtime_targets.py`.
Ambos validam schema, rejeitam targets desconhecidos, previnem path traversal.

**Consequências:** Nomes de binário mudam em um só lugar. Electron e backend
sempre veem o mesmo mapping.

**Evidências:** `shared/runtime-targets.json`, `desktop/runtime-target.js:204-221`,
`backend/runtime_targets.py:206`.

---

## ADR-005 — Paths fornecidos pelo Electron via env vars

**Status:** ACEITA

**Contexto:** Backend precisa saber onde estão dados, logs, cache e recursos.
Originalmente usava `%APPDATA%` no Windows e fallback `Path.home()` no
macOS/Linux — inconsistente.

**Decisão:** Electron resolve paths nativamente (`app.getPath('userData')`,
`app.getPath('logs')`, etc) e passa ao backend via `PROSPECTOS_*` env vars.
Backend usa fallback nativo por plataforma se executado standalone.

**Precedência:**
1. `PROSPECTOS_DATA_DIR` (env var)
2. `app.getPath('userData')` → `~/Library/Application Support/ProspectOS`
3. `Path.home() / "Library" / "Application Support" / "ProspectOS"` (fallback)

**Consequências:** Backend funciona sem Electron (modo fonte/dev). Dados do
usuário seguem convenções da plataforma.

**Evidências:** `backend/paths.py:97-101`, `desktop/main.js:88-106`.

---

## ADR-006 — Scraper Go compilado pelo ProspectOS (build próprio)

**Status:** ACEITA

**Contexto:** Upstream `gosom/google-maps-scraper` não fornece binário
`darwin-arm64` oficial (só Windows e Linux). Duas opções: aguardar upstream
ou compilar.

**Decisão:** Compilar o scraber a partir do source tag `v1.16.3` (commit
`25751bf`), fixando a versão e verificando o commit. Script de build em
`scripts/build_desktop.py` automatiza o processo.

**Alternativas rejeitadas:**
- Aguardar upstream: sem previsão, bloca a iniciativa
- Usar emulação Rosetta (darwin-amd64): viola regra de não usar emulação
- Substituir scraper: reescrita cara, sem ganho claro

**Consequências:** Build reproduzível e auditável. Licença MIT permite
redistribuição. Custo: manutenção do script de build + CI com Go instalado.

**Evidências:** `scripts/native-artifact-sources.json`, `scripts/build_desktop.py:171-252`.

---

## ADR-007 — Node do sistema não é requisito

**Status:** ACEITA

**Contexto:** O scraper Go usa Playwright-go, que baixa seu próprio Node
embutido (driver) na primeira execução. O ProspectOS original referenciava
`node.exe` e fallback `C:\Program Files\nodejs\`.

**Decisão:** Eliminar a dependência de Node externo. O `PlaywrightRuntimeManager`
baixa e gerencia Node + playwright-core no cache isolado. O manifesto
`runtime-targets.json` não referencia mais `node` como binário separado.

**Consequências:** Usuário não precisa instalar Node. Runtime é versionado e
reproduzível. Primeira execução do scraper faz download (~316MB).

**Evidências:** Gate 1B (scraper executado sem Node no PATH), Gate 1C (bootstrap
reproduzível).

---

## ADR-008 — Runtime Playwright controlado e versionado

**Status:** ACEITA

**Contexto:** Playwright baixa Chromium automaticamente, mas a versão do driver
(1.60.0) não está mais disponível no CDN da Microsoft (404).

**Decisão:** Implementar `PlaywrightRuntimeManager` com:
- Download de playwright-core do npm registry (única fonte funcional)
- Download de Node.js do nodejs.org
- SHA-256 verificados
- Instalação atômica (staging → mv)
- Locking para concorrência
- Validação de integridade
- Reparo de instalações corrompidas

**Especificação versionada em:** `shared/playwright-runtime-targets.json`

**Consequências:** ~938MB de runtime em disco (Node 128MB + Chromium 356MB +
Headless Shell 190MB + FFmpeg 2.5MB + scraper 65MB). Primeira instalação
demora ~20s (download + extração + instalação do browser).

**Evidências:** Gate 1C (3 bootstraps reproduzíveis), `playwright_runtime/`
(22 arquivos, 4058 linhas).

---

## ADR-009 — Download sob demanda no primeiro build

**Status:** ACEITA

**Contexto:** Incluir Chromium + Node + playwright-core no bundle do Electron
aumentaria o .app em ~938MB. A maioria dos usuários não usa o scraper Maps.

**Decisão:** Runtime Playwright baixado sob demanda na primeira execução do
scraper. O .app contém apenas o scraper Go (80MB) + backend (95MB).

**Consequências:** Download único, não por execução. Cache é reutilizado.
Usuário sem internet para busca Maps não paga o custo do download.

**Evidências:** `scraper_runtime.py:82-133` (ensure_ready chamado no início
da busca).

---

## ADR-010 — PyInstaller `--onedir` (não `--onefile`)

**Status:** ACEITA

**Contexto:** PyInstaller suporta `--onedir` (pasta com executável + libs)
e `--onefile` (arquivo único que se extrai em runtime).

**Decisão:** Usar `--onedir`. Startup mais rápido, debug mais fácil, Electron
pode referenciar `_internal/` diretamente sem esperar extração.

**Consequências:** Bundle de 262 arquivos (~95MB) em vez de um único executável
(~70MB comprimido). Distribuição exige que a pasta completa seja incluída.

**Evidências:** `backend/prospectos.spec:135-157` (COLLECT), commit c2e1e12.

---

## ADR-011 — Sidecars fora do `app.asar`

**Status:** ACEITA

**Contexto:** Electron empacota arquivos JavaScript em `app.asar`. Binários
não devem ficar dentro do asar (leitura é suportada, mas execução é problemática).

**Decisão:** Backend, scraper e manifests são `extraResources` no
`electron-builder.yml`, copiados para `Resources/` ao lado do `app.asar`.
Resolução usa `process.resourcesPath`.

**Consequências:** Sidecars visíveis no .app (não ofuscados). Assinatura
individual possível. Atualização de sidecars sem trocar app.asar inteiro.

**Evidências:** `electron-builder.yml:14-20`, `desktop/runtime-target.js:123-146`.

---

## ADR-012 — Distribuição pública exige assinatura e notarização

**Status:** ACEITA (decisão de engenharia, implementação pendente)

**Contexto:** macOS bloqueia aplicativos não assinados via Gatekeeper.
Distribuição fora da App Store exige Developer ID + notarização.

**Decisão:** Build local não exige assinatura (`CSC_IDENTITY_AUTO_DISCOVERY=false`).
Distribuição pública exige:
1. Apple Developer Program ($99/ano)
2. Developer ID Application certificate
3. Hardened Runtime + entitlements
4. Assinatura de todos os executáveis internos
5. Notarização + stapling
6. DMG

**Consequências:** Builds locais funcionam sem custo. Distribuição pública tem
custo anual e processo burocrático.

**Evidências:** `scripts/build_desktop.py:345` usa `CSC_IDENTITY_AUTO_DISCOVERY=false`,
documentado na auditoria original.

---

## ADR-013 — Leitura de progresso do scraper via stderr

**Status:** ACEITA

**Contexto:** O scraper v1.16.3 emite progresso JSON (`"places found"`,
`"job finished"`) no **stderr**, não no stdout. O wrapper original
(`rodar_scraper_com_progresso`) lia de stdout.

**Decisão:** O `ScraperProcessRunner` lê ambos os streams concorrentemente e
categoriza por stream de origem. Parse funciona para ambos os pipes.

**Consequências:** Código do job lida com progresso de stderr corretamente.
Fluxo legado (stdout) também é suportado para Windows.

**Evidências:** Gate 1B (validou stderr), `scraper_process.py:141-153`,
`scraper_process.py:254-269` (callback dispara para stdout e stderr).

---

## Decisões abertas (PROPOSTA)

### ADR-014 — ProcessSupervisor centralizado

**Status:** PROPOSTA

Necessidade de um supervisor de processos que gerencie backend, scraper e
jobs com:
- PID tracking
- Health check periódico
- Crash recovery automático
- Shutdown coordenado
- Diagnóstico exportável

Atualmente, backend é gerenciado pelo Electron (`main.js`), scraper pelo
`ScraperProcessRunner`, e threads Python são daemon. Sem coordenação central.

### ADR-015 — CI/CD multiplataforma

**Status:** PROPOSTA

Necessidade de workflows GitHub Actions para:
- Build matrix (macOS arm64 + x64, Windows, Linux)
- Testes Python + Electron
- Smoke test pós-build
- Assinatura + notarização automática
- Publicação de release

Atualmente: zero workflows. Build manual via scripts Python.

### ADR-016 — Tratamento de erros do runtime

**Status:** PROPOSTA

Decidir se o Playwright Runtime deve ser:
- Obrigatório (app não abre sem runtime válido)
- Opcional (app abre, scraper desativado)
- Lazy (baixado na primeira busca)

Atualmente é lazy via `scraper_runtime.py`. Decisão explícita documentada
como ADR pendente.

### ADR-017 — Node.js portátil no bundle

**Status:** PROPOSTA

O Node do runtime Playwright (driver, 115MB) poderia ser incluído no .app
para eliminar o download na primeira execução. Trade-off: .app maior vs
primeira execução mais rápida.

### ADR-018 — Suporte a darwin-x64 e linux-x64

**Status:** PROPOSTA

Targets existem no manifesto mas nunca foram testados. Decisões pendentes:
- Scraper arm64 vs x64 (mesmo source, cross-compile ou runner nativo)
- Keychain no Linux (Secret Service vs fallback)
- Chromium x64 no Linux
- Build em CI vs máquina local
