# Contratos protegidos do backend atual

## Controle

`bot_control.json` contém os campos `run` e `mode`. A escrita deve ser atômica e
preservar um modo válido ao parar a automação.

## Configuração

`offsets.json` reúne regiões calibradas, coordenadas, filtros, sequência de
categorias e parâmetros financeiros. Adapters devem preservar campos que não
conhecem e nunca sobrescrever JSON inválido.

## Eventos por log

O backend publica observações em `[DATA]` e compras confirmadas em `[BUY]`. A
ordem dos campos e o separador fazem parte do contrato legado. `[BUY]` permanece
a fonte canônica dos contadores; o callback serve como informação complementar.

## Persistência

Arquivos mutáveis pertencem a `%LOCALAPPDATA%\AlbionMKT`, com suporte ao override
`MKT_DATA_DIR`. A pasta da instalação deve ser tratada como somente leitura.

## Segurança operacional

Continuam protegidos: hotkeys de emergência, limites financeiros, confirmação
visual de botões, área segura de clique, filtros de tiers, prevenção de cliques
ambíguos e transições de Compra, Venda e Ciclo.

