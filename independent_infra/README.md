# AlbionMKT — infraestrutura independente

> A implantação recomendada está em `cloudflare_worker/`: ela usa Worker + D1
> sem VPS, inclui comandos serverless do Discord e não depende de um processo
> ligado continuamente. A versão FastAPI/Docker descrita abaixo permanece como
> alternativa compatível para uma VPS própria.

Este diretório contém uma contingência isolada para o licenciamento e a
administração pelo Discord. Ele não usa o domínio, o banco, o token nem a
aplicação do Discord atuais.

## Componentes

- API compatível com `POST /api/licenses/activate` e
  `POST /api/licenses/validate`.
- Banco SQLite local com transações atômicas para vincular computadores.
- Keys armazenadas somente como HMAC-SHA-256; a key completa aparece uma única
  vez, no momento da criação.
- HWIDs recebidos do programa são novamente protegidos com HMAC antes de serem
  armazenados.
- Endpoints administrativos autenticados por Bearer token.
- Bot separado do Discord com comandos de criar, listar, prorrogar, revogar,
  resetar computadores e consultar totais.
- Docker Compose para executar backend e bot sem depender da máquina atual.

## Teste local

1. Crie automaticamente um `.env` com dois segredos diferentes e longos:

   ```powershell
   python scripts\bootstrap_env.py
   ```

2. Para testar somente a API:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python -m pip install -r requirements.txt
   .\.venv\Scripts\python -m pytest -q
   .\INICIAR_BACKEND.ps1
   ```

3. Para testar a cópia do AlbionMKT contra a API local, inicie o programa com:

   ```powershell
   $env:ALBIONMKT_API_BASE_URL = "http://127.0.0.1:8000"
   python ..\interface.py
   ```

A variável acima existe apenas na cópia local. Sem ela, o programa continua
usando `https://botmkt.dkgestao.online`.

## Bot separado do Discord

Crie uma nova aplicação no Discord Developer Portal e nunca reutilize ou
redefina o token do bot atual. Configure no `.env`:

- `DISCORD_BOT_TOKEN`: token da aplicação nova.
- `DISCORD_GUILD_ID`: servidor privado de testes, ou o servidor definitivo na
  hora da troca.
- `DISCORD_ADMIN_ROLE_IDS`: IDs de cargos autorizados, separados por vírgula.
- `ALBIONMKT_BACKEND_URL`: endereço interno ou público da API nova.

Para registrar o servidor privado sem editar os demais segredos do arquivo:

```powershell
.\scripts\configure_discord_guild.ps1 -GuildId SEU_ID_DO_SERVIDOR
```

No Windows, depois de copiar o token da aplicação nova, ele pode ser salvo sem
aparecer no terminal ou no histórico de comandos:

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass `
  -File .\scripts\store_discord_token_from_clipboard.ps1
```

O script valida o formato, atualiza apenas o `.env` ignorado pelo Git e limpa o
clipboard em seguida.

O bot responde de forma efêmera aos comandos administrativos, evitando que a
key completa fique registrada em canais. Quando `DISCORD_GUILD_ID` está
configurado, ele também recusa toda administração originada de qualquer outro
servidor e sai automaticamente de instalações não autorizadas, mesmo que a
aplicação seja adicionada fora do ambiente permitido.

## Configuração do servidor Discord

O configurador idempotente reproduz a organização do AlbionMKT sem copiar
mensagens, membros ou dados do servidor atual. Ele valida o nome e o ID do
servidor independente antes de qualquer alteração, reaproveita os canais
padrão e não contém operações de exclusão.

Por padrão, o comando apenas simula e lista o que seria configurado:

```powershell
.\.venv\Scripts\python scripts\provision_discord_server.py
```

Para aplicar, conceda temporariamente ao bot novo `Gerenciar canais` e
`Gerenciar cargos`, execute e depois restaure as permissões mínimas:

```powershell
.\.venv\Scripts\python scripts\provision_discord_server.py --apply
```

A estrutura possui áreas públicas, de clientes e de administração. As duas
últimas negam visualização ao cargo `@everyone` e liberam somente os cargos
autorizados e o bot independente.

Para iniciar o bot fora do Docker, use `INICIAR_DISCORD.ps1`. Para criar um
backup consistente do SQLite enquanto a API está ativa, execute:

```powershell
.\.venv\Scripts\python scripts\backup_database.py
```

## Publicação futura

1. Suba o `docker-compose.yml` em um servidor controlado pelo proprietário do
   AlbionMKT.
2. Coloque um proxy HTTPS na frente da porta local `8000`.
3. Faça backup diário do volume `albionmkt_data`.
4. Teste a API e o bot com keys descartáveis.
5. Somente quando for necessário trocar, altere o valor padrão de
   `DEFAULT_API_BASE_URL` no programa e gere uma nova versão.

Enquanto o novo domínio não for escolhido, nenhuma alteração deve ser feita no
DNS ou na infraestrutura atual.
