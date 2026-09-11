# Roadmap ProspectOS

Prioridades de produto para os próximos ciclos. Foco em entregar valor rápido no Linux/Docker e depois estabilizar o core de prospecção.

---

## 1. Release Linux one-click ✅

- [x] Docker Compose com volume persistente (`prospectos-data`)
- [x] Launcher no menu de aplicativos (`scripts/prospectos-launch.sh`)
- [x] Instalador one-click (`scripts/install-linux.sh`) + imagem GHCR
- [x] Release automatizada via GitHub Actions (`linux-v*`)

**Objetivo:** qualquer usuário Linux com Docker instala com um comando e abre pelo menu. Ver [INSTALAR-LINUX.md](INSTALAR-LINUX.md).

---

## 2. Estabilidade do scraper Maps / fallback Places API

- Melhorar mensagens quando o scraper local falha (rede, bloqueio, timeout)
- UX clara para alternar em **Configurações → Fonte de dados** (scraper vs Places API)
- Documentar pré-requisitos e limites de cada modo

**Objetivo:** menos abandono na primeira busca por erro opaco.

---

## 3. Kanban e funil (UX)

- Filtros persistentes entre sessões (status, nicho, situação do site)
- Lembrar modo de visualização (lista vs Kanban)
- Pequenos ajustes de drag-and-drop e feedback visual

**Objetivo:** quem prospecta todo dia não reconfigura a tela a cada abertura.

---

## 4. Onboarding wizard

- Primeira execução: chave de IA, perfil do vendedor, escolha de canal (Maps / Instagram)
- Checklist de “pronto para prospectar” no dashboard

**Objetivo:** reduzir tempo até a primeira busca útil.

---

## 5. Observabilidade de jobs

- Status visível de buscas em andamento (progresso, ETA, erros)
- Histórico de jobs com link para logs
- Notificação quando uma busca longa termina

**Objetivo:** confiança em buscas que levam minutos, não “travou ou está rodando?”.

---

## 6. Depois (backlog)

| Item | Notas |
|------|-------|
| API + worker separados | Escalar buscas pesadas sem travar a UI |
| AppImage / Flatpak | Distribuição sem Docker, opcional |
| Sync multi-máquina | Fora do escopo local-first atual |

---

## Como contribuir

Abra uma issue ou PR no [repositório](https://github.com/Teolfeu/ProspectOS) descrevendo qual prioridade você quer atacar. PRs pequenos e focados são mais fáceis de revisar.
