# Bootstrap Qt do AlbionMKT

## Estado da migração

- **Tkinter:** fallback operacional atual, executado pelo entrypoint legado;
- **Qt/PySide6:** frontend novo em desenvolvimento, ainda sem runtime do bot,
  licenciamento ou Design System final.

As duas interfaces coexistem. `interface.py` não foi substituído ou importado
pela apresentação Qt.

## Comandos

Interface Qt nova:

```powershell
py -3.11 -m albionmkt_app.presentation.qt.app
```

Interface Tkinter antiga:

```powershell
py -3.11 interface.py
```

## Entrypoint e lifecycle

O entrypoint está em `albionmkt_app.presentation.qt.app`. Importar o módulo não
cria `QApplication` nem mostra janela. `main()` executa o lifecycle:

1. chama `build_application()`;
2. mostra `MainWindow`;
3. inicia `QApplication.exec()`;
4. executa o cleanup da bridge ao encerrar.

`QApplication` só é criado pelo composition root ou injetado por testes. Não há
`processEvents()`, polling ou sleeps no aplicativo real.

## Composition root

`build_application()` é o único lugar que constrói a vertical slice:

- `BotControlAdapter`;
- `LegacySettingsAdapter`;
- `LegacyBotLogParser`;
- `PurchaseEventNormalizer`;
- `ApplicationEventDispatcher`;
- `ApplicationState`;
- `ApplicationOrchestrator`;
- `QtApplicationBridge`;
- `MainWindow`.

A janela recebe o orquestrador e a bridge prontos. Widgets não instanciam
adapters, não escrevem JSON e não conhecem o backend legado.

O diretório de dados padrão é o diretório de trabalho. Testes injetam diretórios
temporários, evitando `offsets.json` e `bot_control.json` reais.

## QtApplicationBridge

`QtApplicationBridge` é um `QObject` que assina eventos independentes de GUI e
expõe somente os sinais necessários nesta fase:

- `state_changed(object)`;
- `bot_status_changed(object)`;
- `market_observation_received(object)`;
- `purchase_recorded(object)`;
- `application_error(object)`.

Os sinais transportam snapshots ou objetos tipados da application layer. A
bridge não chama métodos de widgets.

## Fronteira de threads

Listeners do `ApplicationEventDispatcher` podem executar na thread produtora. A
bridge realiza apenas snapshot e emissão de Signal. A `MainWindow` conecta sinais
com `Qt.ConnectionType.QueuedConnection`, de modo que os slots que atualizam
widgets executam na thread da GUI.

```text
backend thread
    -> application event listener
    -> QtApplicationBridge.emit(...)
    -> queued Qt connection
    -> MainWindow slot na GUI thread
```

O teste Qt envia uma observação a partir de uma `threading.Thread` e confirma a
atualização da janela após a entrega enfileirada.

## MainWindow mínima

A janela atual é uma área temporária de diagnóstico, redimensionável, com barra
nativa do Windows, tamanho inicial `1200x720` e mínimo `800x520`.

Ela apresenta dados reais do `ApplicationState`:

- status e modo do bot;
- itens analisados;
- oportunidades;
- compras canônicas;
- lucro estimado da sessão;
- última observação ou compra;
- percentual máximo;
- valor máximo;
- último erro estruturado.

Estado inicial zero não é mock; representa uma sessão sem runtime conectado.

Controles disponíveis:

- seletor `buy`/`close` com rótulos amigáveis;
- botão `Iniciar`;
- botão `Parar`.

Esses controles chamam somente `ApplicationOrchestrator`. Nesta fase eles
persistem o contrato de controle, mas não iniciam `bot.py`.

## Configurações e erros

O composition root solicita `refresh_bot_state()` e `load_settings()` após montar
a janela. Campos ausentes usam defaults atuais. JSON inválido gera
`BotErrorReceived`, mostrado em uma linha discreta; não existe spam de dialogs.

## Encerramento

`MainWindow.closeEvent()` chama `QtApplicationBridge.cleanup()`, removendo todos
os listeners. O cleanup é idempotente e também é chamado no `finally` de
`main()`. A janela não inicia threads próprias, não mata o bot, não apaga arquivos
e não altera licença ao fechar.

## Testes

A suíte Qt define `QT_QPA_PLATFORM=offscreen` somente no módulo de teste. O
aplicativo normal usa a plataforma padrão do Windows.

Os testes cobrem criação do `QApplication`, imports sem side effects, composition
root, janela sem backend pesado, signals, crossing de thread, controles,
configurações válidas/inválidas e cleanup.

## Funcionalidades ainda não integradas

- execução de `bot.py`;
- redirecionamento de stdout e protocolos reais `[DATA]`/`[BUY]`;
- registro do `buy_callback` real;
- OCR, Torch, mouse, teclado e janela do Albion;
- gate, ativação e revalidação de licença;
- execução real de Compra, Venda e Ciclo;
- calibrações;
- Design System oficial;
- dashboard, sidebar, hero e tabela final;
- PyInstaller e arquivos `.spec`.

## Próxima etapa

Após aprovação deste bootstrap, o próximo trabalho deve integrar o runtime do bot
à application layer com lifecycle e stdout controlados, ainda sem iniciar o
redesign visual completo. O aplicativo não possui mais gate de licenciamento; o
Qt não precisa reproduzir esse fluxo.
