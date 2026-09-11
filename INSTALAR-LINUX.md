# Instalar ProspectOS no Linux (one-click)

Requisitos: **Docker Engine** + **Docker Compose v2** instalados e o daemon em execução.

## Instalação rápida

```bash
curl -fsSL https://raw.githubusercontent.com/Teolfeu/ProspectOS/linux-docker/scripts/install-linux.sh -o install-prospectos.sh
chmod +x install-prospectos.sh
./install-prospectos.sh
```

O script:

1. Clona o repositório em `~/ProspectOS` (ou `PROSPECTOS_HOME` customizado)
2. Cria `.env` a partir de `backend/.env.example`
3. Sobe o container Docker (imagem GHCR ou build local)
4. Instala atalho no menu de aplicativos
5. Abre **http://127.0.0.1:5000** no navegador

## Depois de instalar

1. Edite `~/ProspectOS/.env` e cole **ao menos uma** chave de IA (Gemini, Groq ou NVIDIA).
2. Abra o ProspectOS pelo menu de aplicativos ou pela URL acima.

## Atualizar

```bash
~/ProspectOS/scripts/install-linux.sh
```

Ou manualmente:

```bash
cd ~/ProspectOS
git pull
docker compose up -d --build
```

## Remover atalho do menu

```bash
~/ProspectOS/scripts/install-linux.sh --uninstall-launcher
```

## Variáveis opcionais

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PROSPECTOS_HOME` | `~/ProspectOS` | Pasta de instalação |
| `PROSPECTOS_BRANCH` | `linux-docker` | Branch do repositório |
| `PROSPECTOS_IMAGE` | `ghcr.io/teolfeu/prospectos:latest` | Imagem Docker pré-construída |

## Instagram no Docker

Login interativo (uma vez):

```bash
cd ~/ProspectOS
docker compose exec -w /app/backend app python3 instagram/login.py SEU_USUARIO
```

A sessão fica no volume `prospectos-data`.

## Problemas?

```bash
cd ~/ProspectOS
docker compose logs -f
```

Documentação completa: [README.md](README.md#-linux--docker)
