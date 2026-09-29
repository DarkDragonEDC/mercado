# Camada adapter do AlbionMKT

## Finalidade

Esta camada cria uma fronteira tipada entre o backend legado e a futura
apresentação PySide6. Ela é aditiva: `bot.py`, `interface.py` e
`category_config.py` continuam funcionando sem conhecer o novo pacote.

```text
LEGACY BACKEND
      ↓
ADAPTERS
      ↓
APPLICATION
      ↓
future Qt bridge
      ↓
PySide6 UI
```

O pacote não importa PySide6, não inicia threads, não abre janelas e não lê
arquivos durante import.

## Tipos de aplicação

`albionmkt_app.application.types` representa somente dados confirmados:

- `MarketItemObservation`: nome, venda, compra, percentual de custo e flag de
  oportunidade provenientes de `[DATA]`;
- `PurchaseEvent`: lucro estimado, origem e nome opcional;
- `BotControlState`, `BotStatus` e `BotMode`: estado derivado do contrato de
  controle;
- `SettingsSnapshot`: limites, delays e categorias existentes em `offsets.json`;
- `LicenseState`: estado read-only que a futura integração poderá publicar;
- resultados e erros estruturados de leitura/gravação das configurações.

Não existem tipos para histórico de preço, volume, cidade, favoritos ou outras
métricas presentes apenas na referência visual.

## Adapters

### `LegacyBotLogParser`

Reconhece exclusivamente `[DATA]` e `[BUY]`. Converte campos válidos para tipos
de aplicação e retorna `None` para linhas comuns ou malformadas. Diferentemente
do consumidor Tkinter atual, uma linha arbitrária com pipes não é tratada como
dado de mercado. Essa diferença existe apenas na nova camada; o legado não foi
alterado.

### `BotControlAdapter`

Lê e grava `bot_control.json` por um caminho injetável. Expõe operações para
iniciar, parar e mudar o modo. Mantém os campos `run` e `mode`, defaults
conservadores e preserva o modo ao solicitar parada. A gravação troca
atomicamente um arquivo temporário no mesmo diretório.

### `LegacySettingsAdapter`

Lê o subconjunto financeiro e de categorias confirmado em `offsets.json`.
Atualiza somente essas chaves e preserva coordenadas, calibrações e campos
desconhecidos. Arquivos inexistentes resultam nos defaults atuais da interface.
JSON inválido não é sobrescrito: a nova camada devolve um erro estruturado para
que a futura UI possa informar o problema. A interface antiga mantém seu
comportamento silencioso atual.

### `PurchaseEventNormalizer`

Modela os dois caminhos existentes de compra:

- `[BUY]`: possui lucro, mas não possui nome do item;
- `buy_callback`: possui nome e lucro.

Os eventos carregam uma origem explícita. Não existe identificador real de
compra no protocolo, portanto nenhuma chave ou deduplicação artificial foi
criada.

## Eventos

`ApplicationEventDispatcher` oferece registro, remoção e publicação síncrona de
listeners usando um snapshot protegido por `RLock`. Os eventos atuais são:

- `MarketObservationReceived`;
- `PurchaseRecorded`;
- `BotStatusChanged`;
- `SettingsChanged`;
- `LicenseStateChanged`;
- `BotErrorReceived`.

O dispatcher não conhece Tkinter ou Qt. Uma bridge futura converterá esses
eventos em Signals enfileirados na thread principal do Qt.

## Estado em memória

`ApplicationState` deriva somente informações disponíveis na sessão:

- status e modo do bot;
- itens analisados;
- oportunidades;
- compras recebidas;
- soma do lucro estimado;
- última observação e compra;
- configurações, licença e último erro.

Não há persistência adicional. Se `[BUY]` e `buy_callback` forem publicados para
a mesma compra, ambos serão contabilizados; a regra de correlação precisa ser
definida em uma etapa de orquestração porque o backend não fornece identificador.

## Ports

Somente duas fronteiras foram justificadas nesta fase:

- `BotControlPort`;
- `SettingsPort`.

Gateways de licença e mapa serão criados quando existirem casos de uso concretos
da nova apresentação. Isso evita abstrações cerimoniais e acoplamento prematuro
ao backend protegido.

## Limitações e etapas futuras

- o pacote ainda não registra `buy_callback` em `bot.py`;
- ainda não existe leitor de stdout/fila conectando logs ao parser;
- não existe deduplicação segura de compras;
- o aplicativo não possui mais licenciamento; `LicenseState` é apenas um
  tipo read-only sem produtor real;
- Compra, Venda, Ciclo e calibrações continuam integralmente no legado;
- não existe bridge de thread/evento para Qt;
- não existe camada `presentation`.

O próximo passo deve criar um orquestrador pequeno que conecte adapters, eventos
e estado sem importar Qt. A bridge Qt deve vir somente depois dessa integração
estar coberta por testes.
