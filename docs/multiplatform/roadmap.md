# Roadmap — ProspectOS Multiplataforma

**Última atualização:** 2026-07-20

Cada item segue a taxonomia:
- **COMPLETO** — código implementado, testado, artefato existe
- **PARCIAL** — implementado mas incompleto ou sem smoke real
- **PENDENTE** — não implementado
- **BLOQUEADO** — depende de item anterior
- **FORA DE ESCOPO** — postergado

## Fase 1 — Fundação multiplataforma

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| CORE-001 | P0 | **REVERTIDO** | Dependências Python reproduzíveis | Nenhuma | `pip install -r requirements.txt` exit 0, `pip check` sem quebras | Baixo | todas |
| CORE-002 | P0 | **COMPLETO** | PlatformPaths (paths por plataforma) | Nenhuma | Env vars `PROSPECTOS_*` funcionam, fallbacks macOS/Windows/Linux | Baixo | todas |
| CORE-003 | P0 | **COMPLETO** | RuntimeManifest compartilhado | CORE-002 | Electron e backend resolvem binários sem `.exe` hardcoded | Baixo | todas |
| CORE-004 | P0 | **COMPLETO** | PlaywrightRuntimeManager | CORE-003 | Install, validate, repair, remove funcionam em darwin-arm64 | Médio | darwin-arm64 |
| CORE-005 | P0 | **COMPLETO** | Scraper arm64 nativo | Nenhuma | Binário Mach-O arm64, SHA-256 verificado, compilado de tag fixa | Baixo | darwin-arm64 |
| CORE-006 | P0 | **COMPLETO** | Integração scraper + runtime | CORE-004, CORE-005 | Busca Maps executa com runtime controlado, progresso via stderr | Médio | darwin-arm64 |

## Fase 2 — Aplicativo Mac M4 funcional

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| MAC-001 | P0 | **COMPLETO** | PyInstaller arm64 | CORE-001, CORE-002 | Bundle Mach-O arm64, 95MB, 262 arquivos, sem Homebrew | Médio | darwin-arm64 |
| MAC-002 | P0 | **COMPLETO** | Electron `.app` arm64 | MAC-001, CORE-005 | `.app` com todos sidecars, todos Mach-O arm64 | Médio | darwin-arm64 |
| MAC-003 | P1 | **PENDENTE** | Smoke real do `.app` | MAC-002, CORE-001 | Checklist de QA macOS completo | Médio | darwin-arm64 |
| MAC-004 | P1 | **PENDENTE** | Keychain macOS no bundle assinado | MAC-002 | `keyring` salva/lê via Keychain dentro do `.app` | Médio | darwin-arm64 |
| MAC-005 | P2 | **PARCIAL** | Lifecycle macOS | MAC-002 | Command+Q, Dock, segunda instância, crash recovery (código existe, smoke pendente) | Baixo | darwin-arm64 |

## Fase 3 — Distribuição pública macOS

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| MAC-010 | P0 | **PENDENTE** | Apple Developer Program | Nenhuma | Conta ativa $99/ano | Médio | macOS |
| MAC-011 | P0 | **PENDENTE** | Developer ID Application certificate | MAC-010 | Certificado válido no Keychain | Médio | macOS |
| MAC-012 | P0 | **PENDENTE** | Assinar todos executáveis internos | MAC-011 | `codesign -dv` em backend, scraper, Node, Chromium | Alto | macOS |
| MAC-013 | P0 | **PENDENTE** | Hardened Runtime + entitlements | MAC-012 | App executa sem exceções de segurança | Alto | macOS |
| MAC-014 | P0 | **PENDENTE** | Notarização + stapling | MAC-013 | `spctl --assess --verbose --type execute` passa | Alto | macOS |
| MAC-015 | P1 | **PENDENTE** | DMG | MAC-014 | DMG montável com .app arrastável | Médio | macOS |
| MAC-016 | P1 | **PENDENTE** | Auto-update macOS | MAC-015 | `electron-updater` baixa e instala atualização | Médio | macOS |

## Fase 4 — Regressão Windows

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| WIN-001 | P1 | **PENDENTE** | Build real Windows | CORE-001 | electron-builder gera instalador NSIS | Médio | Windows |
| WIN-002 | P1 | **PENDENTE** | Smoke test Windows | WIN-001 | App abre, backend sobe, scraper executa, leads persistem | Alto | Windows |
| WIN-003 | P2 | **PENDENTE** | Migração de dados Windows | WIN-002 | `%APPDATA%\ProspectOS\leads.db` existente é lido corretamente | Alto | Windows |

## Fase 5 — Linux

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| LNX-001 | P2 | **PENDENTE** | Build Linux (AppImage) | CORE-001 | electron-builder gera AppImage | Médio | Linux |
| LNX-002 | P2 | **PENDENTE** | Secret Service keyring | LNX-001 | `keyring.backends.SecretService` salva/lê | Médio | Linux |
| LNX-003 | P2 | **PENDENTE** | Chromium headless Linux | LNX-001 | Scraper executa em Linux sem X11 | Alto | Linux |

## Fase 6 — Mac Intel (darwin-x64)

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| INT-001 | P2 | **PENDENTE** | Scraper darwin-x64 | Nenhuma | Compilar scraper Go para amd64 | Baixo | darwin-x64 |
| INT-002 | P2 | **PENDENTE** | Playwright Runtime x64 | Nenhuma | Node + Chromium x64 baixados | Baixo | darwin-x64 |
| INT-003 | P2 | **PENDENTE** | Build + smoke x64 | INT-001, INT-002 | `.app` funcional em Intel Mac | Médio | darwin-x64 |

## Fase 7 — Robustez

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| ROB-001 | P1 | **PENDENTE** | ProcessSupervisor central | CORE-006 | Supervisor gerencia backend + scraper + jobs | Alto | todas |
| ROB-002 | P1 | **PENDENTE** | Health endpoint | CORE-002 | `GET /health` retorna status de todos subsistemas | Baixo | todas |
| ROB-003 | P2 | **PENDENTE** | Jobs persistentes com recovery | CORE-006 | Jobs sobrevivem a restart do backend | Médio | todas |
| ROB-004 | P2 | **PENDENTE** | Logs estruturados | CORE-002 | Correlation IDs, formato JSON, rotação | Baixo | todas |
| ROB-005 | P2 | **PENDENTE** | Diagnóstico exportável | CORE-004 | Botão "Exportar diagnóstico" gera zip com logs + config + runtime state | Baixo | todas |

## Fase 8 — Performance e produto

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| PERF-001 | P3 | **PENDENTE** | Lazy loading frontend | Nenhuma | Bundle React dividido por rota | Baixo | todas |
| PERF-002 | P3 | **PENDENTE** | Redução do runtime Playwright | CORE-004 | Apenas Headless Shell (sem Chromium completo) se possível | Médio | todas |
| PERF-003 | P3 | **PENDENTE** | UX do download inicial | CORE-004 | Barra de progresso, tempo estimado, botão cancelar | Médio | todas |
| PERF-004 | P3 | **PENDENTE** | Cache do runtime pré-preenchido | MAC-015 | Runtime incluso no DMG (app maior, sem download) | Baixo | macOS |
| PERF-005 | P3 | **PENDENTE** | Atualizações do scraper | CORE-005 | Script de bump de tag + rebuild + hash verification | Baixo | todas |

---

## Release checklist macOS

### Build

- [x] Frontend React buildado (`frontend/dist/`)
- [x] Backend arm64 compilado (`backend/dist/ProspectOS/`, Mach-O arm64)
- [x] Scraper arm64 compilado (`google-maps-scraper`, Mach-O arm64)
- [x] Electron arm64 buildado (`desktop/saida/mac-arm64/ProspectOS.app/`)
- [x] Manifests inclusos (runtime-targets.json, playwright-runtime-targets.json)
- [x] Licenças inclusas (MIT, Apache 2.0, BSD, LGPL 2.1)
- [ ] DMG gerado (atualmente só `.app` dir)
- [ ] Código de versão correto (`package.json` version)
- [ ] CHANGELOG atualizado

### Runtime

- [ ] Paths macOS corretos (`~/Library/Application Support/ProspectOS/`)
- [ ] Banco SQLite criado e migrado
- [ ] Logs em `~/Library/Logs/ProspectOS/`
- [ ] Keychain macOS funcional (keyring)
- [ ] Playwright Runtime baixado na primeira execução
- [ ] Chromium arm64 executa
- [ ] Scraper executa (texto + mapa)
- [ ] Cancelamento da busca funciona
- [ ] PDF gerado sem erros
- [ ] Instagram: login + raspagem + enriquecimento

### Lifecycle

- [ ] App abre sem erros
- [ ] Fechar janela não encerra app (macOS behavior)
- [ ] Dock icon aparece
- [ ] Segunda instância foca a existente
- [ ] Command+Q encerra completamente
- [ ] Backend morre quando app encerra (sem órfãos)
- [ ] Crash do backend fecha app com mensagem

### Signing

- [ ] Developer ID certificate instalado
- [ ] Electron assinado (codesign -dv)
- [ ] Helpers assinados
- [ ] Backend PyInstaller assinado
- [ ] Scraper Go assinado
- [ ] Node (driver) assinado
- [ ] Chromium assinado
- [ ] Todas libraries dinâmicas assinadas

### Notarização

- [ ] Hardened Runtime configurado
- [ ] Entitlements corretas
- [ ] Upload para notarização
- [ ] Status: Approved
- [ ] Stapling aplicado
- [ ] Gatekeeper: app abre sem aviso

### Distribuição

- [ ] DMG montável
- [ ] Versão semântica
- [ ] Release notes no GitHub
- [ ] Checksums SHA-256 publicados
- [ ] Auto-update funcional
- [ ] Rollback testado

### QA

- [ ] Mac limpo (sem ferramentas de desenvolvimento)
- [ ] Primeira execução sem Node, Python, Go
- [ ] Rede lenta (runtime Playwright)
- [ ] Sem rede (erro amigável)
- [ ] Pouco espaço em disco
- [ ] Reinstalação (dados preservados)
- [ ] Atualização de versão anterior

---

## Melhorias além da portabilidade

Itens não obrigatórios para o primeiro release multiplataforma, mas desejáveis.

### Necessário antes de release público
- ProcessSupervisor: sem ele, subprocessos órfãos em crash são risco de suporte
- Health endpoint: permite diagnósticos remotos e auto-recuperação
- Logs estruturados: correlação de erros entre Electron + backend + scraper
- Diagnóstico exportável: resolve 80% dos chamados de suporte

### Recomendado depois de release
- E2E Electron: Spectron ou Playwright para Electron
- Smoke test CI por plataforma
- Backup seguro com compactação
- Migrações de schema versionadas
- CSP e validação de origem local na API Flask
- Página de status do runtime (diagnóstico visual)

### Otimização futura
- Lazy loading do frontend (divisão de bundle Vite)
- Apenas Headless Shell (sem Chromium completo, economia de ~350MB)
- Cache de runtime pré-preenchido no instalador
- Bump automatizado do scraper com verificação de contrato CSV
- Tempo de inicialização do Electron (app.getPath caching)
