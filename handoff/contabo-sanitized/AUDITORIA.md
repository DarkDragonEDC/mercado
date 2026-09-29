# Auditoria do pacote recebido

Data da análise: 2026-08-24.

## Origem e integridade

- Arquivo analisado: `albionmkt-bot-contabo-2026-08-24.zip`
- SHA-256: `BD951947B616186D3BFEC18680D173C3CB015CDD7D1B069ADE3FE8EF78ACFB67`
- Tamanho: 650.280.642 bytes
- Conteúdo total: 8.630 entradas, sendo 7.695 arquivos
- A análise foi estática; nenhum código do pacote foi executado.

## O que foi preservado nesta cópia

- Código principal em `src/`
- Testes e verificadores
- Imagens usadas pelo bot
- `package.json` e `package-lock.json`
- README original

## O que foi deliberadamente excluído

- Todos os arquivos `.env` e credenciais reais
- Dados operacionais em `data/`
- `node_modules/` e cache do npm
- Backups e cópias de deploy repetidas
- Instalador executável em `product/`

O pacote original contém dados de licenças, assinaturas, vendas, lembretes e aceite de onboarding. Esses arquivos devem permanecer privados e só devem ser migrados depois de definir retenção, backup e destino seguro.

## Arquitetura encontrada

- Node.js 20 ou superior, módulos ES
- Discord.js 14
- Express 5 para health check, ativação/validação de licenças, download e webhook
- Integração com Mercado Pago
- Armazenamento operacional em arquivos JSON locais
- Registro e configuração de comandos do Discord por scripts próprios
- Rotinas periódicas de pagamento, licenças e lembretes

## Pontos de atenção

- O pacote recebido possuía credenciais reais em `.env` e também em backups. Elas não foram copiadas.
- A configuração original continha IDs fixos do servidor Discord atual. Nesta cópia eles foram substituídos por variáveis de ambiente.
- Foi encontrada uma chave aparentemente digitada incorretamente no `.env` original: `nLICENSE_PEPPER`. A chave correta usada pelo código é `LICENSE_PEPPER`.
- O servidor HTTP escuta apenas em `127.0.0.1`; em produção será necessário um proxy reverso ou uma alteração consciente da interface de escuta.
- O armazenamento JSON exige estratégia de backup e impede executar duas instâncias gravando os mesmos arquivos simultaneamente.

## Verificações da cópia higienizada

- 29 arquivos do pacote principal foram preservados antes da documentação e do modelo de ambiente serem adicionados.
- Todos os arquivos JavaScript passaram na verificação estática de sintaxe.
- A suíte `npm test` passou integralmente: 8 testes aprovados e nenhuma falha.
- A busca por tokens Discord, tokens Mercado Pago, chaves privadas e tokens GitHub não encontrou ocorrências.
- Nenhum dos IDs fixos do servidor Discord original permaneceu na cópia.
- O hash do ZIP original continuou idêntico após a análise.
