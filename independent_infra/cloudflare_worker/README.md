# Licenciamento serverless do AlbionMKT

Esta é a infraestrutura principal recomendada para as novas licenças. Um
Cloudflare Worker atende a API do aplicativo, as interações do Discord e o
fluxo comercial; o D1 armazena pedidos e licenças de forma persistente. Nenhum
computador ou VPS precisa ficar ligado.

## Fluxo comercial independente

- `/planos` apresenta os três acessos de 30 dias: Venda (R$ 39,90), Compra
  (R$ 49,90) e Completo (R$ 99,90).
- `/comprar` cria um Checkout Pro do Mercado Pago. É pagamento único, sem
  assinatura ou renovação automática.
- O webhook é autenticado por HMAC e o Worker consulta o pagamento diretamente
  no Mercado Pago antes de conferir referência, status, moeda e valor.
- Uma aprovação é processada de forma idempotente: gera somente uma licença,
  concede o cargo do plano e envia key, validade e download por mensagem direta.
- `/meu_acesso` permite recuperar a key em resposta efêmera. A cópia persistida
  para recuperação é cifrada com AES-GCM; a tabela de licenças continua contendo
  apenas HMAC da key.
- Um cron diário remove o cargo quando o acesso termina, exceto se já existir
  outro acesso válido para o mesmo plano.

## Segurança e propriedade

- A conta Cloudflare deve pertencer exclusivamente ao proprietário do
  AlbionMKT e usar autenticação em dois fatores.
- A tabela de licenças contém apenas HMAC das keys e dos HWIDs. Nos pedidos
  aprovados, a key de recuperação é persistida cifrada com AES-GCM.
- `ALBIONMKT_ADMIN_TOKEN` e `ALBIONMKT_KEY_PEPPER` são secrets do Worker e
  nunca entram no Git, no instalador ou no Discord.
- Os comandos administrativos do Discord são efêmeros e aceitos somente no
  servidor configurado e por um administrador ou usuário autorizado. Os três
  comandos comerciais são públicos para os membros desse servidor.
- O bot usa Interactions HTTP; não existe processo conectado 24 horas. O token
  do Discord fica em um secret do Worker para entrega e cargos, e também é usado
  localmente para registrar os comandos.

## Validação local

```powershell
npm install
npm run check
npm test
```

Os testes usam o runtime oficial local do Cloudflare e um banco D1 isolado.

## Implantação

1. Crie o banco D1 `albionmkt-licenses` na conta Cloudflare do proprietário.
2. Copie `wrangler.jsonc` para `wrangler.deploy.jsonc` e substitua somente o
   `database_id` pelo ID real. O arquivo de implantação é ignorado pelo Git.
3. Cadastre os secrets com o Wrangler, sem digitá-los em linha de comando:

   ```powershell
   npx wrangler secret put ALBIONMKT_ADMIN_TOKEN --config wrangler.deploy.jsonc
   npx wrangler secret put ALBIONMKT_KEY_PEPPER --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_PUBLIC_KEY --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_GUILD_ID --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_ADMIN_USER_IDS --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_BOT_TOKEN --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_ROLE_COMPRA_ID --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_ROLE_VENDA_ID --config wrangler.deploy.jsonc
   npx wrangler secret put DISCORD_ROLE_COMPLETO_ID --config wrangler.deploy.jsonc
   npx wrangler secret put MERCADOPAGO_ACCESS_TOKEN --config wrangler.deploy.jsonc
   npx wrangler secret put MERCADOPAGO_WEBHOOK_SECRET --config wrangler.deploy.jsonc
   npx wrangler secret put PUBLIC_BASE_URL --config wrangler.deploy.jsonc
   npx wrangler secret put ALBIONMKT_DOWNLOAD_URL --config wrangler.deploy.jsonc
   ```

4. Aplique o schema e publique:

   ```powershell
   npm run db:migrate:remote
   npm run deploy
   ```

5. Teste `https://albionmkt-license.<subdominio>.workers.dev/health`.
6. No Discord Developer Portal, defina o endereço de interações como
   `https://albionmkt-license.<subdominio>.workers.dev/discord/interactions`.
7. Registre os comandos usando o token do bot apenas no processo local:

   ```powershell
   $env:DISCORD_APPLICATION_ID = "ID_DA_APLICACAO"
   $env:DISCORD_GUILD_ID = "ID_DO_SERVIDOR"
   $env:DISCORD_BOT_TOKEN = Read-Host "Token do bot"
   npm run discord:register
   Remove-Item Env:DISCORD_BOT_TOKEN
   ```

8. No portal do Mercado Pago, cadastre o evento de pagamentos em
   `https://<worker>/webhooks/mercadopago` e use como
   `MERCADOPAGO_WEBHOOK_SECRET` a assinatura secreta exibida ali.
9. No Discord, mantenha o cargo do bot acima dos três cargos comerciais e dê ao
   bot a permissão **Gerenciar cargos**. Sem isso, a licença ainda pode ser
   recuperada com `/meu_acesso`, mas o cargo não será concedido automaticamente.

## Troca no programa

Somente depois de o ciclo completo ser testado com uma key descartável, altere
`DEFAULT_API_BASE_URL` em `license_manager.py` para o endereço HTTPS definitivo
do Worker e gere a nova versão do instalador.

O repositório público de releases serve apenas binários e manifestos. Ele não é
o banco de licenças e jamais recebe secrets, keys ou dados de clientes.
