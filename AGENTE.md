# Configuração do agente + contexto de negócio

Documento de trabalho. Explica **como configurar o comportamento do Claude Code neste
projeto**, **que contexto de negócio precisa ser capturado**, e **por que os dois não
são a mesma coisa**. Ao final, um plano priorizado e a lista do que ainda depende de você.

Escrito em 2026-08-07, depois de instalar e validar o ambiente.

---

## 0. A distinção que organiza tudo

Você pediu "configurar como o agente vai agir **e** o contexto do nosso negócio".
Na prática são **dois destinos diferentes**, e misturá-los é o erro mais comum:

| | Contexto do **produto** | Contexto do **agente** |
|---|---|---|
| **Quem consome** | O ProspectOS em runtime | O Claude Code enquanto programa |
| **Onde mora** | Banco (`configuracoes`) + cofre do Windows | `CLAUDE.md` + `.claude/` |
| **Como se configura** | Tela de Configurações do app | Arquivos versionados no repo |
| **Exemplo** | "Sou o Gabriel, faço sites para clínicas" | "Nunca dê push no origin" |
| **Efeito de errar** | Mensagem genérica para o cliente | Agente toma decisão errada no código |

Seu perfil de vendedor **não** vai no `CLAUDE.md`. Ele vira texto dentro do *system
prompt* que o [ia.py](backend/ia.py) monta para gerar as copies — código, não contexto
de desenvolvimento. Colocá-lo no `CLAUDE.md` não faria a IA do produto assinar nada.

O resto do documento trata das duas metades separadamente.

---

## 1. Fato que condiciona todas as decisões: o código-base é de terceiro

O projeto original é de outra pessoa — os 15 commits mais recentes são todos de
`nandostrong <contato.fernandofagnerr@gmail.com>`. Você trabalha sobre um **fork**:

```
origin    https://github.com/GabrielBottan/ProspectOSGB.git   (seu fork, público)
upstream  https://github.com/nando0x/ProspectOS.git           (original)
branch    main → origin/main
```

Em 2026-08-07, local, `origin/main` e `upstream/main` estavam todos em `6e176d9` —
partida limpa, sem divergência.

Quatro consequências práticas:

1. **Push só no `origin`.** `upstream` é repositório de terceiro; escrever nele por
   acidente é o pior erro possível aqui. Como os dois remotes existem lado a lado,
   um `git push upstream` distraído é plausível — por isso isto vira regra de
   permissão, não recomendação escrita.
2. **Seu fork é público.** Tudo que for commitado fica visível: `CLAUDE.md`, este
   documento, qualquer nota de negócio. Segredos seguem protegidos pelo `.gitignore`
   (`.env`, `leads.db`, sessões do Instagram), mas contexto comercial commitado é
   contexto comercial publicado. Se algo for sensível, não versione.
3. **Configuração pessoal não deveria sujar o repo.** Se um dia sair um PR upstream,
   um `.claude/settings.json` com suas preferências vai junto. Pessoal vai em
   `settings.local.json`; só o que é do projeto vai versionado.
4. **Suas mudanças têm dois destinos.** O fix do `requirements.txt` (pin quebrado do
   `requests`) conserta um bug que atinge **qualquer pessoa** que clona o original — é
   candidato natural a PR no `upstream`. Já customizações de negócio nunca são: ficam
   só no fork.

---

## 2. Como o Claude Code se configura — o mapa

Existem seis mecanismos. A escolha errada é a diferença entre uma regra que funciona
sempre e uma que funciona quando o modelo lembra.

| Mecanismo | Arquivo | O que faz | Escopo |
|---|---|---|---|
| **Contexto** | `CLAUDE.md` | Texto carregado em toda sessão. O agente lê e decide. | Projeto (versionado) |
| **Permissões** | `.claude/settings.json` | Que comandos rodam sem perguntar, quais são proibidos. | Projeto ou local |
| **Hooks** | `.claude/settings.json` | Comandos que o **harness** executa em eventos. Não dependem do modelo. | Projeto ou local |
| **Slash commands** | `.claude/commands/*.md` | Fluxos repetíveis que você dispara com `/nome`. | Projeto |
| **Subagentes** | `.claude/agents/*.md` | Agentes especializados, contexto isolado. | Projeto |
| **MCP** | `.mcp.json` | Ferramentas externas (bancos, APIs, serviços). | Projeto |

Além desses, o nível **usuário** (`~/.claude/`) vale para todos os seus projetos — é
onde já vive sua regra de declarar uso de skills e agentes.

### A regra de ouro: contexto ≠ garantia

Esta é a parte que mais gera frustração, então vale explicitar:

- **`CLAUDE.md` é contexto.** Eu leio e levo em conta. Numa sessão longa, com muita
  coisa competindo por atenção, uma instrução pode pesar menos do que você gostaria.
  É orientação, não trilho.
- **Hook é garantia.** Quem executa é o harness, antes ou depois da ferramenta,
  independentemente do que eu "decidi". Um hook que roda `oxlint` depois de cada
  edição de `.tsx` roda **sempre**.

Tradução prática: *"prefira nomes em português"* é `CLAUDE.md`. *"todo commit tem que
passar no pytest"* é hook. Se você quer que algo aconteça **toda vez, sem exceção**,
não escreva no `CLAUDE.md` — configure um hook.

### O que já existe aqui

- ✅ `CLAUDE.md` — criado nesta sessão: arquitetura, comandos, convenções, armadilhas
  (`paths.py`, `db.CAMINHO_BANCO`, cofre de chaves, WhatsApp passivo).
- ✅ `~/.claude/CLAUDE.md` — sua regra global de transparência sobre skills/agentes.
- ❌ `.claude/` — **não existe**. Nenhuma permissão, nenhum hook, nenhum comando.

Ou seja: hoje o agente tem bom contexto e **zero** garantias e zero automação.

---

## 3. Contexto do produto: o que falta no app

Isto **não** é configuração de agente. É configuração do ProspectOS, feita pela
interface, e é o que separa uma mensagem genérica de uma que parece sua.

### 3.1 Perfil do vendedor — o buraco mais caro

Estado atual, verificado via API: `{"nome":"", "apresentacao":"", "diferencial":""}`.

O [ia.py:265-281](backend/ia.py#L265-L281) injeta este bloco no *system prompt*:

```
Quem envia as mensagens (escreva na voz dessa pessoa):
- Nome: <nome> (apresente-se pelo nome quando soar natural)
- O que faz: <apresentacao>
- Diferencial a destacar quando couber: <diferencial>
```

Vazio, a função retorna string vazia e o modelo cai numa persona neutra. Foi
exatamente o que aconteceu no teste: *"Eu crio sites profissionais para comércios
locais"* — plausível e completamente intercambiável com qualquer concorrente.

| Campo | O que é | Cuidado |
|---|---|---|
| `nome` | Como você assina | Primeiro nome costuma soar melhor que nome completo |
| `apresentacao` | O que você faz, uma frase | Específico vence genérico: "sites para clínicas e consultórios" > "soluções digitais" |
| `diferencial` | Por que você e não outro | Concreto e verificável. O prompt proíbe inventar números, então dado falso vira mensagem fraca |

### 3.2 Os outros ajustes de negócio

| Onde | O quê | Por que importa |
|---|---|---|
| Configurações → Templates | Mensagens-modelo reutilizáveis (`/api/templates`) | Alternativa determinística à IA, útil para abordagens que você já sabe que funcionam |
| Dashboard → Meta semanal | Alvo de leads/contatos por semana | Alimenta o acompanhamento; sem isso o painel fica sem régua |
| Configurações → PageSpeed | Chave opcional do Google | Põe a nota oficial de desempenho no PDF. Gratuita |
| Busca → catálogo de nichos | 170+ nichos em [nichos.ts](frontend/src/lib/nichos.ts) | Vale mapear os **seus** nichos-alvo e cidades antes da primeira busca real |

### 3.3 O que o agente precisa saber sobre o negócio

Nem todo contexto de negócio é do produto. Estes fatos mudam **decisões de código** e
por isso pertencem ao `CLAUDE.md`:

- Qual canal importa mais (Maps ou Instagram)? Define onde vale investir esforço.
- Você usa isto em produção, com clientes reais, ou é estudo? Define o apetite a risco.
- Quais features você de fato usa? Não faz sentido eu otimizar o Kanban se você vive
  na Sessão de prospecção.
- O que é "pronto" para você: passa nos testes? Você testou na tela? Está no ar?

---

## 4. Plano recomendado, em ordem de retorno

### Fase 1 — Fundação (agora, ~15 min)

**1.1 Barreira de segurança no git.** Com `origin` (seu fork) e `upstream` (de terceiro)
convivendo, o alvo do push passa a importar. Vai como regra de permissão, não como texto
no `CLAUDE.md` — tem que ser trilho, não sugestão:

```
deny:  Bash(git push upstream:*)   ← nunca escrever no repo do nando0x
deny:  Bash(git push --force:*)    ← nem reescrever histórico
allow: Bash(git push origin:*)     ← seu fork, liberado
```

**1.2 Allowlist do dia a dia.** Hoje cada `pytest`, `npm run build`, `git status` pede
aprovação. Um allowlist dos comandos read-only e dos scripts do projeto elimina a maior
parte dos prompts sem abrir mão de controle sobre o que é destrutivo.

**1.3 Preencher o perfil do vendedor.** Três campos, efeito imediato em toda copy gerada.

**1.4 Decidir a relação com o upstream.** Fork, branch local, ou acesso direto.

### Fase 2 — Garantias (quando a Fase 1 estiver de pé)

**2.1 Hook de qualidade pós-edição.** Depois de editar `.py`, rodar o `pytest` do módulo
afetado; depois de `.tsx`, rodar `oxlint`. Pega regressão no ato, em vez de no fim.

**2.2 Hook de proteção de segredos.** Um `PreToolUse` que barra escrita em `.env`,
`leads.db` e `instagram/sessao/`. O `.gitignore` protege o repositório; isto protege os
arquivos de mim.

> Vale calibrar: hook em excesso deixa o ciclo lento. Comece pelos dois e meça.

**2.3 Slash command para o fluxo recorrente.** Se existe uma sequência que você repete
("rodar os testes, buildar o front, resumir o que quebrou"), ela vira `/verificar`.

### Fase 3 — Só se a dor aparecer

Subagentes e MCP resolvem problemas que você **ainda não tem**. Subagente faz sentido
quando uma tarefa polui o contexto principal (varrer o repo inteiro atrás de um padrão).
MCP faz sentido quando o agente precisa alcançar um sistema externo — seu CRM real, um
banco de produção. Configurar antes da necessidade é complexidade sem retorno.

---

## 5. Como aplicar (e por que não editando JSON na mão)

O `settings.json` tem esquema específico e erro de sintaxe falha em silêncio — a
configuração simplesmente não vale, sem aviso. Nesta sessão existem duas skills feitas
para isso:

- **`update-config`** — escreve permissões, hooks e variáveis de ambiente com o esquema
  correto, no escopo certo (projeto vs. local vs. usuário).
- **`fewer-permission-prompts`** — varre o histórico real desta sessão, vê quais
  comandos eu de fato rodei, e propõe um allowlist priorizado. Empírico, não chute.

Recomendação: usar as duas na Fase 1. Quando eu invocar qualquer uma, eu aviso, conforme
sua regra global de transparência.

---

## 6. O que depende de você

**Bloqueiam a Fase 1:**

1. **Perfil do vendedor** — nome, o que faz (uma frase), diferencial.
2. ~~Relação com o upstream~~ — ✅ resolvido: fork em `GabrielBottan/ProspectOSGB`,
   remotes configurados como `origin`/`upstream`.
3. **O fix do `requirements.txt`** — commit só no seu fork, ou também um PR no upstream?
   É um bug que quebra a instalação para qualquer um que clone o projeto original.

**Ajudam a calibrar, sem bloquear:**

4. Uso real ou estudo? Qual canal é prioridade?
5. Seus nichos-alvo e cidades.
6. Quer os hooks da Fase 2 desde já, ou prefere ver o atrito antes de automatizar?

---

## 7. Estado atual, para referência

| Item | Estado |
|---|---|
| Deps Python / Node | Instaladas. 375 testes passando, build e lint OK |
| Chaves de IA | Gemini, Groq e NVIDIA no `.env`, as três validadas com chamada real |
| Geração de mensagem | OK ponta a ponta (respondida pelo Gemini) |
| Diagnóstico PDF | OK, PDF válido de 1 página |
| Scraper do Maps | v1.17.3 + driver Playwright 1.61.1 + Chromium instalados e verificados |
| Busca real no Maps | **Não exercitada** — pipeline query → CSV → CRM segue não comprovado |
| Canal Instagram | Não configurado, por decisão |
| Perfil do vendedor | **Vazio** |
| `.claude/` | **Não existe** |
| Banco | Limpo, 0 leads |

Pendências no repo: `M backend/requirements.txt`, `?? CLAUDE.md`, `?? AGENTE.md`.
