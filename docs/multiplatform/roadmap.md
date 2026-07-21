# Roadmap — ProspectOS Multiplataforma

**Última atualização:** 2026-07-20

## Escopo oficial

A iniciativa multiplataforma tem como objetivo:

> Permitir que o ProspectOS seja compilado e executado localmente em macOS Apple Silicon, preservando a compatibilidade com Windows e preparando a arquitetura para Linux no futuro.

**Não faz parte do escopo atual:**

- Distribuir o aplicativo publicamente para usuários de macOS
- Publicar na Mac App Store
- Gerar instalador público
- Assinar com Developer ID
- Notarizar com a Apple
- Publicar DMG público
- Implementar auto-update para macOS
- Publicar releases macOS no GitHub
- Suportar instalação por usuários externos sem ambiente técnico
- Suportar Mac Intel neste momento

---

## Taxonomia

| Status | Significado |
|---|---|
| **COMPLETO** | Código implementado, testado, artefato existe |
| **PARCIAL** | Implementado, mas sem smoke real reproduzível a partir do HEAD |
| **PENDENTE** | Não implementado |
| **BLOQUEADO** | Depende de item anterior que não está completo |
| **FORA DE ESCOPO** | Não faz parte do objetivo atual |

---

## Fase 1 — Fundação multiplataforma

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| CORE-001 | P0 | **BLOQUEADO** | Dependências Python reproduzíveis | Nenhuma | `pip install -r requirements.txt` exit 0, `pip check` OK | Baixo | todas |
| CORE-002 | P0 | **COMPLETO** | PlatformPaths (paths por plataforma) | Nenhuma | Env vars `PROSPECTOS_*` funcionam, tests passam | Baixo | todas |
| CORE-003 | P0 | **COMPLETO** | RuntimeManifest compartilhado | CORE-002 | Electron + backend resolvem binários via mesmo JSON | Baixo | todas |
| CORE-004 | P0 | **COMPLETO** | PlaywrightRuntimeManager | CORE-003 | Install, validate, repair, remove, 160+ tests | Médio | darwin-arm64 |
| CORE-005 | P0 | **COMPLETO** | Scraper arm64 nativo | Nenhuma | Binário Mach-O arm64, tag fixa v1.16.3 | Baixo | darwin-arm64 |
| CORE-006 | P0 | **COMPLETO** | Integração scraper + runtime | CORE-004, CORE-005 | Scraper executa com runtime controlado, stderr parse | Médio | darwin-arm64 |

**CORE-001 validado em 2026-07-20:** `pip install` falha com `ResolutionImpossible`. Commit `42c9040` (que corrigia `requests==2.32.3` → `2.34.2`) não está no HEAD atual — foi revertido. `MAC-001` e `MAC-002` são `PARCIAL` porque seus artefatos existem mas não são reproduzíveis a partir do HEAD.

---

## Fase 2 — Aplicativo macOS local funcional

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| MAC-001 | P0 | **PARCIAL** | Backend PyInstaller arm64 | CORE-001 | Build reproduzível a partir do HEAD | Médio | darwin-arm64 |
| MAC-002 | P0 | **PARCIAL** | Electron `.app` arm64 | MAC-001, CORE-005 | `.app` produzido com backend + scraper arm64 | Médio | darwin-arm64 |
| MAC-003 | P0 | **PENDENTE** | Smoke completo do `.app` | MAC-002, CORE-001 | Checklist local executado em Mac M4 | Alto | darwin-arm64 |
| MAC-004 | P1 | **PENDENTE** | Keychain macOS no bundle | MAC-002 | `keyring` salva/lê via Keychain no `.app` local | Médio | darwin-arm64 |
| MAC-005 | P1 | **PARCIAL** | Lifecycle macOS | MAC-002 | Código existe, smoke pendente | Baixo | darwin-arm64 |
| MAC-006 | P0 | **PENDENTE** | Scraper dentro do `.app` | MAC-002 | Busca real de baixo volume concluída | Alto | darwin-arm64 |
| MAC-007 | P0 | **PENDENTE** | Runtime Playwright no `.app` | MAC-002 | Download, cache e reutilização validados | Alto | darwin-arm64 |
| MAC-008 | P1 | **PENDENTE** | Execução isolada | MAC-002 | App funciona sem Python, Node ou Go no `PATH` | Médio | darwin-arm64 |
| MAC-009 | P1 | **PENDENTE** | Reabertura e persistência | MAC-002 | Banco existente é reutilizado após reiniciar | Baixo | darwin-arm64 |

---

## Fase 3 — Regressão Windows

Mudanças em paths, manifests e resolução de sidecars podem afetar o produto existente.

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| WIN-001 | P0 | **PENDENTE** | Build real Windows | CORE-001 | Instalador ou `.exe` produzido em máquina Windows | Médio | Windows |
| WIN-002 | P0 | **PENDENTE** | Smoke funcional Windows | WIN-001 | Backend, frontend e scraper funcionam | Alto | Windows |
| WIN-003 | P0 | **PENDENTE** | Compatibilidade de dados | WIN-001 | Banco `%APPDATA%\ProspectOS\leads.db` é preservado | Alto | Windows |
| WIN-004 | P1 | **PENDENTE** | Keyring Windows | WIN-001 | Credenciais existentes continuam acessíveis | Médio | Windows |
| WIN-005 | P1 | **PENDENTE** | Lifecycle e encerramento | WIN-001 | Backend e scraper encerram sem órfãos no Windows | Médio | Windows |

---

## Fase 4 — Robustez operacional

Para uso estritamente local, ROB-001 é recomendado mas não precisa bloquear o primeiro smoke funcional.

| ID | Prioridade | Status | Objetivo | Dependências | Aceite | Risco | Plataforma |
|---|---|---|---|---|---|---|---|
| ROB-001 | P1 | **PENDENTE** | Supervisor de processos | CORE-006 | Backend e scraper encerram e recuperam corretamente | Alto | todas |
| ROB-002 | P1 | **PENDENTE** | Health endpoint | CORE-002 | Estado do backend e subsistemas disponível localmente | Baixo | todas |
| ROB-003 | P2 | **PENDENTE** | Jobs persistentes | CORE-006 | Jobs podem ser recuperados após restart | Médio | todas |
| ROB-004 | P2 | **PENDENTE** | Logs estruturados | CORE-002 | Eventos correlacionados entre Electron, backend e scraper | Baixo | todas |
| ROB-005 | P2 | **PENDENTE** | Diagnóstico exportável | CORE-004 | ZIP de diagnóstico sem dados sensíveis | Baixo | todas |

---

## Fase 5 — Linux

Linux permanece como evolução futura. Não declarar suporte enquanto houver apenas resolução de paths e targets no manifesto.

| ID | Prioridade | Status | Objetivo | Aceite | Risco |
|---|---|---|---|---|---|
| LNX-001 | P3 | **PENDENTE** | Build AppImage | electron-builder gera artefato Linux | Médio |
| LNX-002 | P3 | **PENDENTE** | Secret Service keyring | `keyring.backends.SecretService` salva/lê | Médio |
| LNX-003 | P3 | **PENDENTE** | Playwright Runtime Linux | Node + Chromium baixados e validados no Linux | Alto |
| LNX-004 | P3 | **PENDENTE** | Scraper Linux | Scraper Go compilado ou baixado para linux-x64 | Baixo |
| LNX-005 | P3 | **PENDENTE** | Smoke completo Linux | AppImage funcional, runtime, scraper, keyring | Alto |

---

## Fase 6 — Melhorias de produto e performance

| ID | Prioridade | Status | Objetivo | Notas |
|---|---|---|---|---|
| PERF-001 | P3 | **PENDENTE** | Lazy loading do frontend | Divisão de bundle Vite por rota |
| PERF-002 | P3 | **PENDENTE** | Avaliar uso apenas do Headless Shell | Economia de ~350MB de runtime |
| PERF-003 | P2 | **PENDENTE** | UX do primeiro download | Barra de progresso, tempo estimado, cancelar |
| PERF-004 | P3 | **FORA DE ESCOPO** | Runtime pré-preenchido no instalador | Só faria sentido com distribuição pública |
| PERF-005 | P2 | **PENDENTE** | Bump automatizado do scraper | Script de atualização de tag + rebuild + hash |

---

## Possível distribuição pública futura (histórico)

Itens da auditoria original que não fazem parte do escopo atual. Mantidos como registro histórico.

| ID | Prioridade | Status | Objetivo | Motivo da exclusão |
|---|---|---|---|---|
| MAC-010 | — | **FORA DE ESCOPO** | Apple Developer Program ($99/ano) | Não haverá distribuição pública agora |
| MAC-011 | — | **FORA DE ESCOPO** | Developer ID Application certificate | Mesmo |
| MAC-012 | — | **FORA DE ESCOPO** | Assinar todos executáveis internos | Mesmo |
| MAC-013 | — | **FORA DE ESCOPO** | Hardened Runtime + entitlements | Mesmo |
| MAC-014 | — | **FORA DE ESCOPO** | Notarização + stapling | Mesmo |
| MAC-015 | — | **FORA DE ESCOPO** | DMG público | Mesmo |
| MAC-016 | — | **FORA DE ESCOPO** | Auto-update macOS | Mesmo |

Esses itens não devem:
- Bloquear o uso local
- Aparecer como P0
- Fazer parte do release checklist atual
- Ser tratados como próximos passos
- Gerar trabalho de engenharia agora

---

## Release checklist macOS (escopo local)

### Build

- [x] Frontend React buildado
- [x] Backend PyInstaller arm64 produzido (histórico — ver MAC-001)
- [x] Scraper Go arm64 produzido
- [x] Electron `.app` arm64 produzido (histórico — ver MAC-002)
- [x] Runtime manifests incluídos
- [x] Licenças incluídas
- [ ] Build completo reproduzível a partir do HEAD
- [ ] Versão do aplicativo conferida

### Inicialização

- [ ] `.app` abre no Mac de desenvolvimento
- [ ] Backend inicia
- [ ] Frontend carrega
- [ ] Readiness identifica a porta correta
- [ ] Nenhum arquivo é gravado dentro do `.app`
- [ ] Erro de startup é apresentado de forma clara

### Paths

- [ ] Dados em `~/Library/Application Support/ProspectOS`
- [ ] Logs no diretório definido pelo Electron
- [ ] Cache em `~/Library/Caches/ProspectOS`
- [ ] Temporários no diretório temporário do macOS
- [ ] Resources apontam para `Contents/Resources`
- [ ] Banco é preservado após reiniciar

### Runtime

- [ ] Backend executa sem Python no `PATH`
- [ ] Scraper executa sem Go instalado
- [ ] Playwright não usa Node do sistema
- [ ] Chromium arm64 é instalado no cache controlado
- [ ] Segunda busca reutiliza o runtime
- [ ] Nenhum cache global do Playwright é usado
- [ ] Falha de rede não corrompe o runtime
- [ ] Pouco espaço em disco gera erro claro

### Funcionalidades

- [ ] Busca Google Maps de baixo volume
- [ ] Progresso recebido por `stderr`
- [ ] CSV processado
- [ ] Cancelamento funciona
- [ ] PDF é gerado
- [ ] Keychain salva e recupera credenciais
- [ ] Instagram importa e inicia sem erro
- [ ] Banco SQLite mantém WAL normalmente

### Lifecycle

- [ ] Fechar janela mantém aplicativo ativo no macOS
- [ ] Clicar no Dock recria a janela
- [ ] Segunda instância foca a existente
- [ ] `Command+Q` encerra o backend
- [ ] Scraper ativo é cancelado no quit
- [ ] Node e Chromium são encerrados
- [ ] Nenhum processo órfão permanece
- [ ] Crash do backend gera mensagem clara

### Isolamento

- [ ] App executa fora do repositório
- [ ] App executa sem venv
- [ ] App executa sem Python no `PATH`
- [ ] App executa sem Node no `PATH`
- [ ] App executa sem Go no `PATH`
- [ ] Nenhum path de Homebrew é necessário
- [ ] Nenhum path de build temporário é necessário

### Regressão

- [ ] Suíte Python completa (após CORE-001)
- [ ] Testes desktop completos
- [ ] Build executado duas vezes
- [ ] Estrutura dos dois builds comparada
- [ ] Regressão Windows executada em máquina Windows

---

## Definição de conclusão da iniciativa

A iniciativa de compatibilidade macOS estará concluída quando:

```
build local reproduzível
+ ProspectOS.app arm64
+ backend funcional
+ frontend funcional
+ scraper funcional
+ runtime Playwright controlado
+ Keychain funcional
+ paths corretos
+ lifecycle validado
+ nenhum processo órfão
+ regressão Windows aprovada
```

**Não são necessários:**

- Developer ID
- Notarização
- DMG público
- GitHub Release macOS
- Auto-update macOS
- Distribuição pública
- Mac Intel

---

## Melhorias além da portabilidade

### Necessário antes de release público (futuro)
- Supervisor de processos: sem ele, subprocessos órfãos em crash são risco
- Health endpoint: diagnósticos e auto-recuperação
- Logs estruturados: correlação de erros entre componentes
- Diagnóstico exportável: resolve suporte

### Recomendado depois de release
- E2E Electron (Spectron ou Playwright para Electron)
- Smoke test CI por plataforma
- Backup seguro com compactação
- Migrações de schema versionadas
- CSP e validação de origem local na API Flask
- Página de status do runtime

### Otimização futura
- Lazy loading do frontend
- Apenas Headless Shell (sem Chromium completo)
- Tempo de inicialização do Electron
