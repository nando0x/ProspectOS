# Ferramenta de prospecção — Google Maps → WhatsApp (com CRM visual)

## Primeira configuração (só precisa fazer uma vez)

1. Instale as dependências do Python (uma única vez):
   ```powershell
   # Windows
   py -m pip install -r requirements.txt
   ```
   ```bash
   # macOS/Linux
   python3.11 -m pip install -r requirements.txt
   ```
2. Pegue sua chave gratuita do Google Gemini em https://aistudio.google.com/apikey
3. Copie o arquivo `.env.example` para um novo arquivo chamado `.env` (na mesma pasta) e cole sua chave:
   ```
   GEMINI_API_KEY=sua_chave_aqui
   ```
   O arquivo `.env` nunca é compartilhado nem enviado a lugar nenhum — fica só no seu computador.

## Como usar no dia a dia

1. Abra um terminal nesta pasta e rode:
   ```powershell
   # Windows
   py app.py
   ```
   ```bash
   # macOS/Linux
   python3.11 app.py
   ```
2. Abra o navegador em **http://localhost:5000**
3. No topo da tela aparece um **painel com números** (total de leads, quantos foram contatados/responderam/fecharam, sua taxa de conversão, e quantos follow-ups estão marcados para hoje).
4. Clique em **"+ Nova busca"**, escreva o nicho + cidade (um por linha, ex.: `corretor de imóveis em Curitiba`) e clique em Buscar. Leva alguns minutos (cada empresa sem site no Maps também é checada numa busca externa, pra confirmar que ela realmente não tem site em lugar nenhum) — acompanhe o andamento na própria tela.
5. Os leads novos aparecem automaticamente na lista, em forma de cartões, já filtrados (nota ≥ 4.0, sem site cadastrado no Maps **e** sem site encontrado numa busca externa).
6. Clique num cartão para abrir o lead: lá você pode
   - Mudar o **status** (novo → contatado → respondeu → fechou/recusou) — toda mudança fica registrada no **histórico** (visível no próprio card do lead, em "Histórico de status").
   - Adicionar **tags** (ex.: "urgente, zona sul") e marcar um **próximo follow-up** (uma data) — leads com follow-up vencido ou para hoje ganham um destaque amarelo no card e são contados no painel do topo.
   - Escrever **observações** (ex.: "liguei dia 10, disse que vai pensar").
   - Clicar em **"✨ Gerar mensagem"** para a IA (Google Gemini) escrever uma mensagem de abordagem personalizada com base no nome, categoria e nota da empresa. Você pode editar o texto antes de copiar.
   - Clicar em **"Copiar"** pra copiar a mensagem, e em **"Abrir WhatsApp"** pra já abrir a conversa com aquele número.
   - Clicar em **"🗑️ Excluir este lead"** pra tirar aquela empresa da sua lista de vez (não some do banco, só para de aparecer, inclusive em buscas futuras do mesmo nicho/cidade).
7. Use os filtros no topo (busca por nome, status, nicho, nota mínima) pra organizar sua lista — se um filtro não encontrar nada, aparece um botão de "Limpar filtros".
8. Clique em **"⬇ Exportar CSV"** a qualquer momento pra baixar uma planilha completa dos leads que estão sendo exibidos (respeitando os filtros ativos), com nome, status, tags, WhatsApp e observações.

Para fechar, é só fechar a aba do navegador e apertar `Ctrl+C` no terminal onde o backend está rodando.

## O que a ferramenta já filtra pra você

- Só aparecem empresas com **nota ≥ 4.0** no Google Maps.
- Só aparecem empresas que **não têm site cadastrado no Maps**.
- Além disso, cada uma dessas empresas passa por uma **segunda checagem**: o sistema busca o nome dela numa busca externa pra confirmar que ela não tem site em lugar nenhum da internet (às vezes uma empresa tem site de verdade, mas nunca preencheu esse campo no perfil do Google Meu Negócio — sem essa checagem, ela apareceria como lead por engano). Só quem passa nas duas checagens vira lead de verdade.
- Empresas que você já viu numa busca anterior **não aparecem de novo** (mesmo rodando o mesmo nicho/cidade semanas depois) — isso fica registrado em `leads.db`, que fica salvo nesta pasta.
- Mesmo assim, antes de mandar a primeira mensagem, vale uma conferida rápida no Google pelo nome da empresa — nenhuma checagem automática é 100% infalível.

## Se algo der errado

- **A busca falhou ou travou**: a tela agora mostra uma mensagem em português explicando o que pode ter acontecido (ex.: tempo esgotado, programa não encontrado). Se quiser mais detalhes técnicos, abra o arquivo `logs/prospeccao.log` (uma pasta chamada `logs` aparece automaticamente dentro do projeto) — lá fica registrado tudo o que a ferramenta fez, incluindo os erros completos.
- **Seus dados estão protegidos**: toda vez que você inicia uma nova busca, a ferramenta faz sozinha uma cópia de segurança do seu banco de leads na pasta `backups/` (guarda as últimas 20 cópias automaticamente). Se algo der muito errado, dá pra restaurar copiando um desses arquivos de volta como `leads.db`.
- **Uma mensagem de erro apareceu em vermelho no topo da tela**: é a própria ferramenta avisando que algo não funcionou (ex.: perdeu a conexão com o servidor, ou a IA não respondeu) — a mensagem já vem traduzida, sem "linguagem de programador".

## Perguntas comuns

**Rodei a mesma busca de novo e apareceram poucos leads novos — deu erro?**
Não. Significa que a ferramenta já tinha visto a maioria daquelas empresas antes (deduplicação funcionando). Se aparecer "nenhuma empresa foi encontrada", vale conferir se o nicho/cidade estão escritos corretamente.

**Quero apagar tudo e começar do zero?**
Feche o backend, apague o arquivo `leads.db` e rode o backend de novo (ele recria o banco vazio). Se der errado, tem uma cópia de segurança recente na pasta `backups/`.

**A geração de mensagem deu erro.**
A própria mensagem de erro já vem explicando o motivo (chave não configurada, cota da IA esgotada, etc.). Se for sobre a chave, confira se você criou o arquivo `.env` (não `.env.example`) na pasta do projeto, com sua chave colada corretamente, e reinicie o `py app.py`.

**Quero rodar os testes automatizados (só necessário se for mexer no código).**
```powershell
# Windows
py -m pytest
```
```bash
# macOS/Linux
python3.11 -m pytest
```

**Ainda quero usar do jeito antigo (sem interface), só linha de comando.**
Os arquivos `buscar.ps1` e `processar.py` continuam funcionando normalmente — a interface nova é um complemento, não substitui o fluxo antigo.
