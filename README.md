<div align="center">

<img src="frontend/public/logo-icon.svg" width="96" alt="ProspectOS logo" />

# ProspectOS

### Prospecção de leads no piloto automático: do Google Maps e Instagram direto pro seu CRM

Encontre pequenos negócios locais **sem site ou com site ruim**, receba a estratégia
de abordagem e a mensagem prontas por IA, gere um diagnóstico em PDF e acompanhe tudo
num CRM visual — do primeiro contato ao fechamento.

![Version](https://img.shields.io/badge/version-2.0.0-107a4a)
![Tests](https://img.shields.io/badge/tests-230%20passing-22c55e)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows_%7C_Linux_%7C_macOS-0078D6)
![License](https://img.shields.io/badge/license-MIT-green)

[![GitHub stars](https://img.shields.io/github/stars/nando0x/ProspectOS?style=social)](https://github.com/nando0x/ProspectOS)

<img src="https://res.cloudinary.com/doqqbpc2u/image/upload/v1783540529/ProspecOS_Print_pfnrc9.png" alt="Dashboard do ProspectOS" width="800" />

<!-- 🎬 Placeholder: GIF de demo (buscar, filtrar, gerar mensagem, mover no Kanban) -->
<!-- <img src="docs/demo.gif" alt="Demo do ProspectOS" width="800" /> -->

</div>

---

## 📋 Índice

- [O que é](#-o-que-é)
- [⚠️ Antes de usar](#️-antes-de-usar)
- [Features](#-features)
- [Quickstart](#-quickstart)
- [Uso no dia a dia](#-uso-no-dia-a-dia)
- [Stack](#-stack)
- [Estrutura do projeto](#-estrutura-do-projeto)
- [Filosofia do projeto](#-filosofia-do-projeto)
- [Perguntas comuns](#-perguntas-comuns)
- [Contribuindo](#-contribuindo)
- [Licença](#-licença)
- [Agradecimentos](#-agradecimentos)

---

## 🎯 O que é

**ProspectOS** é uma ferramenta de prospecção de leads para quem vende sites, landing pages ou serviços digitais para pequenos negócios locais.

Ela resolve um problema específico de ponta a ponta: encontrar empresas que **precisam de um site** e transformá-las em conversas de venda. O ProspectOS varre o **Google Maps** (por nicho + cidade, ou por pino e raio num mapa) e os **comentários de posts do Instagram**, **analisa o site de cada empresa** para separar quem não tem site de quem tem um site ruim/lento/inseguro, prioriza por um score, e para cada lead entrega a **estratégia de abordagem**, a **mensagem pronta por IA** e um **diagnóstico em PDF** para mandar no WhatsApp — tudo num CRM visual com funil, follow-up e analytics.

**Para quem é:**
- Freelancers e agências de web design/landing pages que fazem a própria prospecção
- Devs e estudantes que querem estudar scraping, integração com IA e um CRM full-stack na prática
- Qualquer pessoa curiosa sobre como automatizar geração de leads locais

**Por que foi criado:** nasceu como ferramenta pessoal para simplificar um processo manual e repetitivo (abrir o Maps, checar site por site, anotar em planilha) e cresceu até virar uma ferramenta de prospecção completa. É uma base de código real e funcional, aberta para você aprender, adaptar e usar por sua conta.

> 💡 Continua sendo software que você roda localmente, na sua máquina, por sua conta e risco — não um SaaS pronto. Leia os avisos abaixo antes de usar.

---

## ⚠️ Antes de usar

Leia isto com atenção antes de rodar qualquer coisa:

- 🕷️ **Isto é uma ferramenta de scraping.** Raspar o Google Maps e o Instagram pode violar os Termos de Uso dessas plataformas. Use por sua conta e risco.
- 📸 **O módulo do Instagram usa sua conta pessoal** (via [instagrapi](https://github.com/subzeroid/instagrapi)) para logar e consultar dados. Isso pode resultar em **checkpoint de segurança ou banimento temporário/permanente da conta**. Recomendado: use uma conta secundária, rode com moderação, e nunca compartilhe o arquivo de sessão gerado.
- 🔧 **Sem garantia de funcionamento contínuo.** Instagram e Google mudam suas proteções com frequência. Se algo parar de funcionar, é provavelmente por isso.
- 🚫 **Sem afiliação** com Google, Meta/Instagram, nem com os projetos de terceiros usados (`gosom/google-maps-scraper`, `instagrapi`).
- 📄 Fornecido **"como está"**, sem garantias. Veja [`LICENSE`](LICENSE) (MIT).
- 💻 **Windows, Linux e macOS.** Cada plataforma tem seu script de conveniência (`iniciar.bat` / `iniciar.sh`) e sua própria build do scraper de Maps. No Linux/macOS, rode `backend/preparar_driver_playwright.sh` uma vez para o scraper conseguir subir o navegador interno.

---

## ✨ Features

| Área | O que faz |
|---|---|
| 🗺️ **Canal Google Maps** | Busca por nicho + cidade **ou por pino e raio num mapa** (estilo segmentação do Facebook Ads), com catálogo de 170+ nichos clicáveis |
| 🔎 **Análise de site real** | Abre o site de cada empresa e detecta **sem site, site fora do ar, sem HTTPS, SSL inválido, não-mobile, lento ou feito em construtor pronto** (Wix, Canva...) — site ruim também é lead |
| 🩻 **Raio-X do site** | Extrai do HTML o que o site **tem e o que falta** (WhatsApp, telefone, e-mail, mapa, fotos, meta description, favicon) — dado real, não chute |
| 📄 **Diagnóstico em PDF** | Relatório de uma página pronto pra mandar no WhatsApp: reputação, problemas em linguagem leiga, raio-X e **nota oficial do Google PageSpeed** |
| 📸 **Canal Instagram** | Extrai comentários de um post, enriquece o perfil de cada autor e classifica prioridade com IA, com retomada de análises interrompidas |
| 🧠 **Mensagens com IA** | Copy de abordagem e follow-up **na sua voz** (perfil do vendedor), citando detalhes reais do site, com fallback entre 3 provedores gratuitos (Gemini, Groq, NVIDIA) |
| 🎯 **Estratégia por lead** | Cada lead vem com cenário detectado, ângulo de venda, ganchos concretos e objeções com respostas prontas |
| 🔥 **Score de priorização** | Nota + volume de avaliações + situação do site num score 0-100 para ordenar a fila de abordagem |
| ⚡ **Sessão de prospecção** | Modo foco: um lead por vez do mais quente ao mais frio (follow-ups primeiro), abordagem em um clique com atalhos de teclado |
| 📋 **Tarefas de hoje** | Follow-ups vencidos + leads quentes, cada um com o WhatsApp já preenchido |
| 📊 **CRM visual + Kanban** | Funil de status com histórico, drag-and-drop, tags, observações e follow-up com cadência crescente (+3/+5/+7 dias) |
| 📈 **Analytics** | Funil de conversão e desempenho por nicho, para os dois canais separados e combinados |
| 🧰 **Produtividade** | Filtros (inclusive por situação do site), histórico de buscas, busca global (Ctrl+K), exportação CSV, ações em lote, tema claro/escuro |
| 🔐 **Segurança** | Chaves de API guardadas no cofre de credenciais do sistema via `keyring` (DPAPI no Windows, Secret Service no Linux, Keychain no macOS), nunca em texto puro |

---

## 🚀 Quickstart

### Pré-requisitos

- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 20+](https://nodejs.org/)
- Windows, Linux ou macOS

### 1. Clone o repositório

```powershell
git clone https://github.com/nando0x/ProspectOS.git
cd ProspectOS
```

### 2. Configure o backend

```powershell
cd backend
py -m pip install -r requirements.txt
copy .env.example .env
```

Você vai precisar de **ao menos uma** chave de IA gratuita (usada para gerar as mensagens de abordagem e classificar leads do Instagram):

| Provedor | Onde pegar a chave |
|---|---|
| Gemini | https://aistudio.google.com/apikey |
| Groq | https://console.groq.com/keys |
| NVIDIA Build | https://build.nvidia.com |

Tem duas formas de configurar, escolha a que for mais fácil pra você:

- **Pela interface do sistema (mais fácil):** depois de rodar o projeto (veja o passo 6), acesse **Configurações** no menu e cole a chave direto lá. Fica guardada com segurança no cofre de credenciais do sistema (nunca em texto puro), sem precisar mexer em nenhum arquivo nem reiniciar o servidor.
- **Editando o `.env` manualmente:** abra o arquivo `backend/.env` num editor de texto e preencha o valor da chave correspondente (`GEMINI_API_KEY`, `GROQ_API_KEY` ou `NVIDIA_API_KEY`).

> Se você configurar dos dois jeitos, o que estiver salvo pela interface tem prioridade sobre o `.env`.

> 💡 **Opcional — Google PageSpeed:** para incluir a nota oficial de desempenho do Google no diagnóstico em PDF, adicione uma chave do [PageSpeed Insights](https://developers.google.com/speed/docs/insights/v5/get-started) em Configurações. É gratuita e funciona sem chave para uso leve.

> 💡 **Recomendado — Seu perfil:** ainda em Configurações, preencha "Seu perfil" (nome e o que você faz). As mensagens geradas por IA saem assinadas e na sua voz, em vez de genéricas.

### 3. Baixe a dependência externa do scraper

O binário do `google-maps-scraper` **não vem no repositório** (é um binário de terceiros, ~60MB, de outro projeto open source, então não faz sentido versionar binário compilado dentro de um repo git). Passo a passo completo, sem pular nada:

1. Acesse **[a página de releases mais recente](https://github.com/gosom/google-maps-scraper/releases/latest)**.
2. Role até a seção **"Assets"** (fica perto do final da página, às vezes precisa clicar para expandir).
3. Baixe o asset da **sua plataforma** (o nome muda a cada versão, mas o padrão é fixo — ex.: `google_maps_scraper-1.16.1-...`):
   - **Windows:** `google_maps_scraper-<versão>-windows-amd64.exe`
   - **Linux:** `google_maps_scraper-<versão>-linux-amd64`
   - **macOS:** `google_maps_scraper-<versão>-darwin-amd64` (ou `darwin-arm64` no Apple Silicon)
4. Renomeie o arquivo para o nome exato que o projeto espera (tudo minúsculo, com hífens):
   - **Windows:** `google-maps-scraper.exe`
   - **Linux/macOS:** `google-maps-scraper` (sem extensão) e dê permissão de execução: `chmod +x google-maps-scraper`
   - No Windows, se você não estiver vendo a extensão `.exe` no nome do arquivo, isso é normal (o Windows esconde extensões conhecidas por padrão). Só renomeie a parte visível do nome.
5. Mova esse arquivo para dentro da pasta `backend/` deste projeto, **no mesmo nível** do arquivo `app.py` (não dentro de nenhuma subpasta).
6. Para conferir se deu certo, a pasta `backend/` deve conter, lado a lado: `app.py`, `processar.py` e o binário do scraper.

> 🐧 **Linux/macOS — um passo extra do navegador:** o scraper embute o Playwright, que tenta baixar o driver de um CDN antigo já desativado. Rode uma vez, dentro da pasta `backend/`:
> ```bash
> ./preparar_driver_playwright.sh
> ```
> Sem isso a busca falha com "não conseguiu iniciar o navegador interno". No Windows esse passo não é necessário.

> ✅ **Como saber se funcionou:** ao clicar em "Nova busca" no canal Google Maps do ProspectOS, a busca deve iniciar normalmente. Se aparecer um erro dizendo que o programa não foi encontrado, revise o nome do arquivo (passo 4) e o local onde ele está (passo 5). São os dois erros mais comuns.
>
> Sem esse arquivo, **só o canal Google Maps fica indisponível**. O canal Instagram funciona normalmente sem ele.

### 4. Faça login no Instagram (só se for usar esse canal)

O canal Instagram não usa a API oficial: ele automatiza sua **própria conta pessoal** (via `instagrapi`) para ler comentários e perfis, exatamente como se você estivesse navegando manualmente. Por isso, antes de usar esse canal pela primeira vez, é preciso logar uma única vez pelo terminal:

```powershell
cd backend
py instagram\login.py SEU_USUARIO
```

O que acontece ao rodar isso:

1. O terminal pede sua **senha do Instagram** (a digitação fica invisível na tela, isso é normal, é assim que o `getpass` funciona).
2. Se sua conta tiver **verificação em duas etapas (2FA)** ativada, o terminal vai pausar e pedir o código que chegar no seu celular ou app autenticador.
3. Se o login der certo, aparece a mensagem `Login feito com sucesso` e é criado um arquivo em `backend/instagram/sessao/session-SEU_USUARIO.json`. Esse arquivo guarda sua sessão logada, então você **não precisa repetir esse passo toda vez**, só quando a sessão expirar.

> ⚠️ **Este é o passo de maior risco do projeto.** Como é sua conta pessoal fazendo essa automação, o Instagram pode detectar o comportamento como suspeito e aplicar um checkpoint de segurança ou banimento temporário/permanente. Recomendado: use uma **conta secundária**, criada só para isso, nunca a sua conta principal. Veja `backend/instagram/LEIA-ME.md` para mais contexto.
>
> Não existe forma de "testar" ou simular esse login sem uma conta real do Instagram. Não pule este passo se você não pretende usar o canal Instagram, ele é totalmente independente do canal Google Maps.

### 5. Configure o frontend

```powershell
cd ../frontend
npm install
```

### 6. Rode tudo

Use o atalho que sobe backend + frontend juntos e abre o navegador automaticamente:

```powershell
cd ..
iniciar.bat
```

No Linux/macOS, use o equivalente:

```bash
cd ..
chmod +x iniciar.sh   # só na primeira vez
./iniciar.sh
```

Ou manualmente, em dois terminais:

```powershell
# Terminal 1: backend
cd backend
py app.py

# Terminal 2: frontend
cd frontend
npm run dev
```

Acesse **http://localhost:5173** 🎉

---

## 🛠️ Uso no dia a dia

**Canal Google Maps:**
```
Clique em "Nova busca" e escolha o modo:
- Por texto: nicho + cidade, um por linha (ex: corretor de imóveis em Curitiba)
- Por mapa: solte pinos, ajuste o raio de cada um e selecione os nichos no catálogo
```
A ferramenta analisa o site de cada empresa e mantém no CRM quem **não tem site ou tem site ruim** (fora do ar, inseguro, lento, não-mobile, construtor pronto...), descartando quem já tem um site decente.

**Canal Instagram:**
```
Cole o link de um post. A ferramenta extrai os comentários,
enriquece o perfil de cada autor e classifica a prioridade com IA
```

**Prospecção em ritmo:** abra a **Sessão de prospecção** — um lead por vez, do mais quente ao mais frio (follow-ups vencidos primeiro), com a estratégia e a mensagem prontas e abordagem em um clique. Ou a tela **Tarefas de hoje** para os follow-ups do dia.

**Em cada lead**, você tem:
- A **estratégia de abordagem** (cenário, ângulo, ganchos e objeções)
- O **raio-X do site** (o que tem e o que falta)
- A **mensagem por IA** na sua voz, e o **diagnóstico em PDF** para mandar no WhatsApp
- Funil de status (Kanban ou lista), tags, observações, follow-up com data e exportação CSV

> 💡 Aperte **Ctrl+K** de qualquer lugar para achar um lead pelo nome ou pular para uma tela.

**Quer usar sem interface visual?** O fluxo antigo de linha de comando continua funcionando:
```powershell
cd backend
.\buscar.ps1
py processar.py
```

---

## 🧱 Stack

**Backend**
- Python 3.11+ · Flask 3.1 (blueprints) · SQLite
- [instagrapi](https://github.com/subzeroid/instagrapi) (Instagram) · [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper) (Maps, via Playwright)
- Gemini / Groq / NVIDIA Build (geração de texto e classificação por IA, com fallback automático)
- fpdf2 (diagnóstico em PDF) · keyring (cofre de credenciais) · PageSpeed Insights (opcional)

**Frontend**
- React 19 · TypeScript · Vite 8 · Tailwind CSS 4
- shadcn/ui (Radix primitives) · TanStack React Query · React Router 7
- Recharts (analytics) · Leaflet + OpenStreetMap (busca por mapa) · Framer Motion (animações) · Sonner (toasts) · dnd-kit (Kanban)

---

## 📁 Estrutura do projeto

```
ProspectOS/
├── iniciar.bat / iniciar.sh # sobe backend + frontend juntos (Windows / Linux-macOS)
├── backend/
│   ├── app.py                # monta o Flask e registra os blueprints
│   ├── rotas_*.py            # rotas por domínio (leads, instagram, analytics, config)
│   ├── ia.py                 # provedores de IA, prompts e fallback
│   ├── jobs.py               # jobs de background (scraper e análise do Instagram)
│   ├── processar.py          # análise de site + filtro/dedupe + schema do banco
│   ├── diagnostico.py        # geração do diagnóstico em PDF
│   ├── db.py                 # conexão, cofre de credenciais e backup
│   ├── instagram/            # login, raspagem e enriquecimento de perfis
│   └── tests/                # suíte de testes (pytest, 230 testes)
└── frontend/
    ├── src/
    │   ├── pages/            # telas (dashboard, leads, sessão, tarefas, analytics...)
    │   ├── components/       # UI por domínio (leads/, instagram/, dashboard/, search-modal/...)
    │   ├── hooks/            # data-fetching e mutations (React Query)
    │   ├── services/         # chamadas HTTP para a API do backend
    │   ├── lib/              # estratégia, catálogo de nichos, utilitários
    │   └── types/            # tipos TypeScript espelhando o schema do backend
    └── public/
```

---

## 💭 Filosofia do projeto

- **Dois canais, uma experiência.** Google Maps e Instagram têm fluxos de dados bem diferentes, mas o produto final (funil, tags, follow-up, IA) é espelhado nos dois. O que funciona num canal deveria funcionar igual no outro.
- **IA com fallback, nunca bloqueante.** Toda geração de texto por IA tenta múltiplos provedores gratuitos em sequência antes de desistir, porque depender de uma única API gratuita é assumir que ela vai falhar (cota, instabilidade) em algum momento.
- **Honestidade sobre os riscos.** Scraping e automação de contas pessoais têm risco real de banimento/bloqueio. O projeto não esconde isso em letra miúda: os avisos ficam no topo do README, não no rodapé.
- **Simples de rodar localmente.** Sem Docker, sem infraestrutura complexa, só Python, Node e SQLite. A barreira de entrada pra testar o projeto deveria ser a menor possível.

---

## ❓ Perguntas comuns

**Quero apagar tudo e começar do zero.**
Feche o backend, apague `backend/leads.db` e rode de novo (recria o banco vazio). Há backup automático em `backend/backups/`.

**Quero rodar os testes automatizados.**
```powershell
cd backend
py -m pytest
```

**O canal Instagram não depende do `google-maps-scraper.exe`?**
Não. Os dois canais são independentes. Falta de um não trava o outro.

**Minha conta do Instagram foi bloqueada, e agora?**
Rode `py instagram\login.py SEU_USUARIO` de novo. Veja `backend/instagram/LEIA-ME.md` para mais contexto sobre esse risco.

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Este é um projeto mantido nas horas vagas, então o processo é leve. Veja o guia completo em **[CONTRIBUTING.md](CONTRIBUTING.md)** — setup de dev, como rodar os testes e as convenções de código.

Resumo:

1. Abra uma [issue](../../issues) descrevendo o bug ou a ideia antes de codar algo grande. Isso evita retrabalho.
2. Para PRs pequenos (fix de bug, melhoria de doc), pode mandar direto.
3. Mantenha o padrão de código existente (nomes em português no domínio do negócio, testes com `pytest` no backend).
4. Seja respeitoso nas discussões. Sem necessidade de um processo formal, só bom senso.

---

## 📄 Licença

[MIT](LICENSE). Use, modifique e redistribua livremente, mas por sua conta e risco (veja os avisos no topo deste README).

---

## 🙏 Agradecimentos

- [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper): scraper de Google Maps usado como dependência externa
- [subzeroid/instagrapi](https://github.com/subzeroid/instagrapi): biblioteca usada para o canal Instagram
- [shadcn/ui](https://ui.shadcn.com/): componentes base do frontend
- Google Gemini, Groq e NVIDIA Build: provedores de IA gratuitos usados na geração de texto

<div align="center">

Feito com foco em resolver um problema real de prospecção. Se ajudou você, considere deixar uma ⭐.

</div>
