# Orquestração da aplicação

## Papel

`ApplicationOrchestrator` é a última camada independente de interface antes da
bridge Qt. Ele recebe dados e intenções, delega aos adapters existentes, atualiza
`ApplicationState` e somente então publica eventos para consumidores.

Ele não importa Tkinter, PySide6, Qt, `bot.py` ou `interface.py`. Também não
abre arquivos diretamente: controle e configurações são acessados
exclusivamente pelos ports injetados.

```text
bot stdout ----> LegacyBotLogParser ------+
                                         |
buy_callback --> PurchaseNormalizer ------+--> ApplicationOrchestrator
                                         |             |
bot_control ---> BotControlAdapter -------+             v
                                         |      ApplicationState
offsets -------> SettingsAdapter ---------+             |
                                                       v
                                              ApplicationEvents
                                                       |
                                                       v
                                                future Qt bridge
```

## Entradas e comandos

- `handle_bot_log_line(line)`: processa exclusivamente os resultados tipados do
  parser legado;
- `handle_purchase_callback(item_name, estimated_profit)`: normaliza o callback
  opcional sem transformá-lo em uma segunda compra contabilizada;
- `start_bot(mode)`, `stop_bot()`, `change_bot_mode(mode)` e
  `refresh_bot_state()`: delegam ao `BotControlPort`;
- `load_settings()` e `save_settings(snapshot)`: delegam ao `SettingsPort`;
- `reset_session_metrics()`: inicia explicitamente uma nova sessão de métricas;
- `update_license_state(state)`: aceita estado produzido externamente, sem
  conectar a rede ou o gerenciador legado.

Não existe CommandBus ou framework de commands. Os métodos são a API de intents
para a futura apresentação.

## Fluxo de logs e observações

Uma linha `[DATA]` válida torna-se `MarketItemObservation`. O orquestrador cria
`MarketObservationReceived`, aplica o evento ao estado e o publica. O contador de
oportunidades usa somente `observation.opportunity`, calculado pelo backend; não
há repetição das regras econômicas.

Linhas comuns ou inválidas retornam `None` e não alteram estado ou métricas.

## Estratégia `[BUY]` versus `buy_callback`

O código real confirma a seguinte ordem dentro de um único bloco de oportunidade:

1. imprime `[BUY] LUCRO_ESTIMADO`;
2. se houver callback registrado, chama `buy_callback(nome, lucro_estimado)`;
3. executa os cliques de compra.

`[BUY]` sempre é produzido nesse fluxo. O callback é opcional, pode lançar erro e
possui mais contexto, mas não contém identificador correlacionável com a linha.
Nenhuma das fontes confirma o sucesso final dos cliques.

A decisão determinística é:

- `[BUY]` é a fonte canônica de `purchases_count`, `estimated_profit` e
  `last_purchase`;
- `buy_callback` publica `PurchaseCallbackReceived` como informação adicional e
  não altera métricas;
- não existe correlação por tempo, nome, lucro, ordem, contador ou hash.

Assim, receber ambos no fluxo normal contabiliza uma única compra. Caso apenas um
callback seja inserido artificialmente, ele continua informativo e não cria uma
compra canônica. Essa limitação é preferível a inventar uma regra de correlação.

## Estado e sessão

`ApplicationState` mantém em memória somente dados reais da sessão. O snapshot é
imutável e o mapa de categorias é copiado para uma view read-only.

`reset_session_metrics()` zera:

- itens analisados;
- oportunidades;
- compras contabilizadas;
- lucro estimado;
- última observação;
- última compra;
- último erro.

Status, modo, configurações e licença são preservados. O reset nunca é associado
automaticamente a start/stop; a futura UI ou um caso de uso deverá solicitá-lo
explicitamente.

## Ordem de atualização e eventos

Para eventos que alteram estado, a ordem é sempre:

```text
input
  -> parser/adapter
  -> state.apply(event)
  -> snapshot
  -> event publication
```

Um listener pode consultar o estado e observar os dados do evento que acabou de
receber. Entradas concorrentes podem fazer com que o snapshot já contenha também
uma atualização posterior; não é prometida ordenação global entre threads.

O callback informativo não altera estado e é publicado diretamente.

## Thread safety

O estado possui seu próprio `RLock`. O orquestrador usa outro `RLock` para
serializar mutação e captura do snapshot. O lock do orquestrador é liberado antes
da publicação, portanto listeners lentos não bloqueiam a região crítica dos
contadores.

O dispatcher copia a lista de listeners sob lock e executa os callbacks fora do
lock interno. Ele continua síncrono nesta fase.

Listeners não devem executar:

- OCR;
- requests ou I/O lento;
- `sleep`;
- processamento pesado;
- automação ou cliques.

A futura bridge Qt deverá ser um listener leve que apenas encaminha os dados para
Signals enfileirados na thread principal.

## Settings e erros

Leituras e gravações bem-sucedidas aplicam e publicam `SettingsChanged`. Um erro
estruturado do adapter não substitui as configurações atuais; ele se transforma
em `BotErrorReceived` com código `settings.<tipo>`.

## Licença

`update_license_state()` permite receber futuramente o resultado do bootstrap ou
de um adapter de licença. Não há conexão com API, HWID ou periodicidade nesta
camada.

## Limitações atuais

- ainda não existe conexão concreta com stdout ou `buy_callback` do processo;
- o evento informativo de callback não enriquece `last_purchase`, pois não há
  correlação determinística;
- `[BUY]` representa o início do fluxo, não a confirmação dos cliques;
- listeners são síncronos;
- não existe fila, worker ou bridge Qt;
- não existe pacote `presentation/`.

## Integração futura com Qt

A próxima camada poderá criar uma bridge que assina eventos, consulta snapshots
e emite Signals. Widgets deverão enviar intents ao orquestrador e nunca escrever
JSON, interpretar logs ou modificar `ApplicationState` diretamente.
