# Assinaturas Discord + Mercado Pago

Bot para vender o **Plano Mensal** por **R$ 30,00/mês** e liberar automaticamente um cargo no Discord.

## Fluxo

1. O membro entra no servidor e usa `/assinar email:cliente@exemplo.com`.
2. O bot cria uma assinatura recorrente e envia o checkout somente para o membro.
3. O Mercado Pago notifica o servidor por webhook.
4. O bot consulta a API do Mercado Pago e concede o cargo configurado.
5. Cancelamento ou pausa remove o cargo.

## Requisitos

- Node.js 20 ou superior;
- uma aplicação/bot no Discord Developer Portal;
- uma aplicação no painel **Suas integrações** do Mercado Pago;
- hospedagem com URL HTTPS pública e funcionamento contínuo.

## Discord

1. Crie um cargo chamado `Assinante`.
2. Nas categorias privadas, negue `Ver canal` para `@everyone` e permita para `Assinante`.
3. Crie uma aplicação e um bot no Discord Developer Portal.
4. Autorize o bot no servidor com os escopos `bot` e `applications.commands` e a permissão `Gerenciar Cargos`.
5. Em **Configurações do servidor > Cargos**, coloque o cargo do bot acima de `Assinante`.
6. Ative o modo desenvolvedor do Discord e copie os IDs da aplicação, servidor e cargo.

Não conceda `Administrador` ao bot.

## Mercado Pago

1. Acesse o painel de desenvolvedores e crie uma aplicação.
2. Obtenha o Access Token de teste ou produção.
3. Configure a URL pública usada pelo bot. A assinatura é criada com:

   `https://seu-dominio.com/webhooks/mercadopago`

4. Defina a assinatura secreta do webhook em `MERCADO_PAGO_WEBHOOK_SECRET`.

Nunca publique o Access Token, a assinatura secreta ou o token do Discord.

## Instalação

```bash
npm install
copy .env.example .env
```

Preencha `.env`. Depois registre os comandos uma vez:

```bash
npm run register
```

Inicie o serviço:

```bash
npm start
```

Teste `https://seu-dominio.com/health`, que deverá responder `{"ok":true}`.

## Variáveis

| Nome | Uso |
|---|---|
| `DISCORD_TOKEN` | Token secreto do bot |
| `DISCORD_CLIENT_ID` | ID da aplicação Discord |
| `DISCORD_GUILD_ID` | ID do servidor |
| `SUBSCRIBER_ROLE_ID` | ID do cargo Assinante |
| `MERCADO_PAGO_ACCESS_TOKEN` | Credencial da API Mercado Pago |
| `MERCADO_PAGO_WEBHOOK_SECRET` | Assinatura secreta para validar notificações |
| `PUBLIC_BASE_URL` | URL HTTPS pública, sem barra final |

## Observação sobre o programa

Este projeto controla o cargo e os canais do Discord. Se o programa tiver login ou licença própria, será necessário integrar a ativação e expiração ao sistema do programa; disponibilizar apenas o arquivo em um canal não impede que ele continue funcionando depois do cancelamento.
# Licenciamento AlbionMKT

O bot gera e administra as licencas sem depender de Gist. Pagamentos aprovados recebem uma key exclusiva com vencimento e limite de computadores.

O aplicativo usa:

- `POST /api/licenses/activate` para vincular o primeiro computador.
- `POST /api/licenses/validate` nas demais inicializacoes e periodicamente durante o uso.
- Corpo JSON: `{ "key": "ALBIONMKT-...", "hwid": "identificador-estavel", "appVersion": "1.0.0" }`.

Administradores com a permissao Gerenciar Servidor podem usar `/licencas`, `/licenca-criar`, `/licenca-info`, `/licenca-entregar`, `/licenca-estender`, `/licenca-revogar`, `/licenca-reativar` e `/licenca-resetar-pc`. As respostas administrativas sao privadas.

As variaveis `LICENSE_PEPPER` e `LICENSE_ENCRYPTION_KEY` sao obrigatorias e devem permanecer apenas no servidor.
