# Plano seguro de migração

Este roteiro mantém o bot atual funcionando até a troca final.

## 1. Preparação sem impacto

- Guardar o ZIP original offline e conferir o SHA-256 registrado em `AUDITORIA.md`.
- Obter acesso sob controle do proprietário às contas necessárias: hospedagem, domínio/DNS, Discord Developer Portal e Mercado Pago.
- Criar credenciais novas para o ambiente independente; não reutilizar segredos que outra pessoa ainda possa conhecer.
- Preencher uma cópia local de `.env.example` chamada `.env`.
- Instalar dependências com `npm ci` somente no ambiente isolado.

## 2. Configuração do Discord independente

- Informar IDs da aplicação, servidor, cargos, categorias e canais novos no `.env`.
- Registrar os comandos no servidor de testes.
- Testar permissões, onboarding, suporte, painéis e comandos administrativos sem clientes reais.
- Manter `SALES_ENABLED=false` e `PAYMENT_TEST_MODE=true` durante toda a homologação.

## 3. API e pagamentos em homologação

- Subir a API em endereço de testes com HTTPS.
- Validar `/health`, ativação e validação de licença com dados fictícios.
- Configurar webhook de teste do Mercado Pago e conferir assinatura/idempotência.
- Não apontar o webhook de produção para o novo ambiente ainda.

## 4. Migração dos dados

- Parar gravações por uma janela curta combinada.
- Fazer backup final dos JSON operacionais e registrar hash e horário.
- Copiar apenas os arquivos necessários para o novo armazenamento.
- Validar contagens e consistência sem publicar nomes, e-mails, chaves ou identificadores.

## 5. Troca final

- Confirmar que o novo bot, API, download e pagamentos passaram nos testes.
- Atualizar DNS/webhook somente na janela de troca.
- Iniciar a nova instância e impedir que duas instâncias processem os mesmos pagamentos.
- Monitorar logs, uma compra controlada e a entrega da licença.
- Só depois revogar tokens, chaves e acessos antigos.

## Critérios para voltar atrás

Se health check, Discord, webhook, licença ou download falhar, restaurar o apontamento anterior e manter o ambiente novo desligado até corrigir. Não apagar o servidor antigo durante a homologação.

