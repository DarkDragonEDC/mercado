# AlbionMKT Development Rules

## Architecture

O aplicativo utiliza Python e executa o backend/domínio localmente, no mesmo
processo da interface desktop. A arquitetura deve evoluir progressivamente para:

```text
backend/domain existente
        ↓
application/adapters
        ↓
UI PySide6
```

A UI não deve duplicar regras de negócio que já pertencem ao backend. A migração
deve ser aditiva e incremental, sem reescrever o núcleo operacional como efeito
colateral de trabalho visual.

## Protected Backend

Tratar como áreas protegidas:

- `bot.py`;
- `category_config.py`;
- `coordinate_system.py`;
- lógica funcional de Compra, Venda e Ciclo;
- `app_paths.py` e contratos do atualizador.

Esses arquivos não devem ser alterados durante o redesign visual sem justificativa
técnica explícita, escopo isolado e validação proporcional ao risco.

## Protected Contracts

Preservar os contratos atuais:

- `offsets.json`;
- `bot_control.json`;
- marcadores `[DATA]`;
- marcadores `[BUY]`;
- callback de compra;
- templates utilizados pela visão computacional.

Não alterar formatos existentes apenas para facilitar a nova UI. Mudanças de
contrato exigem decisão própria, compatibilidade explícita e testes de migração.

## UI Migration

A nova UI será implementada com:

- PySide6;
- Qt Widgets;
- QSS;
- SVG;
- `QTableView`;
- `QAbstractTableModel`;
- `QStyledItemDelegate` quando necessário.

A interface Tkinter antiga deve permanecer funcional durante a migração. Não
realizar substituição destrutiva de `interface.py`. A nova apresentação deve
existir paralelamente à interface antiga até alcançar paridade funcional.

## Adapter Layer

A nova UI deve consumir uma camada intermediária. Evitar que widgets:

- escrevam diretamente `offsets.json`;
- escrevam diretamente `bot_control.json`;
- interpretem diretamente logs de `bot.py`;
- dependam diretamente de callbacks globais;
- conheçam detalhes internos da automação;
- implementem regras econômicas;
- implementem regras de OCR;
- implementem regras de compra.

Encapsular essas responsabilidades em adapters, services e controllers. Os
adapters devem preservar inicialmente os contratos legados, não redesenhá-los.

## Thread Safety

PySide6 possui event loop próprio. Toda integração com threads existentes deve
respeitar thread safety.

Widgets Qt não podem ser atualizados diretamente por threads de automação. Usar,
quando apropriado:

- Signals;
- Slots;
- `QObject`;
- conexões enfileiradas;
- filas ou bridges thread-safe.

Não transportar padrões inseguros existentes do Tkinter diretamente para Qt.
Operações bloqueantes, OCR, rede, leitura contínua e automação devem permanecer
fora da thread da interface.

## Visual Reference

A referência visual oficial é:

`ChatGPT Image 10 de ago. de 2026, 20_54_37.png`

Essa imagem substitui quaisquer referências visuais anteriores. O novo frontend
deve reproduzir sua linguagem visual com alta fidelidade:

- dark;
- premium;
- Albion Online;
- trading;
- dourado;
- alta densidade de informação;
- sidebar;
- hero;
- cards;
- painéis;
- filtros;
- tabela densa;
- badges compactos.

Evitar:

- visual SaaS genérico;
- glassmorphism exagerado;
- neon exagerado;
- grandes gradientes sem correspondência com a referência;
- border radius exagerado;
- excesso de whitespace;
- tipografia grande demais;
- componentes genéricos que descaracterizem o design.

## Window Architecture

A nova aplicação deve prever conceitualmente dois modos.

### Main Window

Janela ampla e redimensionável.

- tamanho padrão aproximado: `1600x900`;
- tamanho mínimo aproximado: `1180x720`.

Comportamento adaptativo previsto:

- `>=1600`: sidebar + hero + dashboard;
- `1200–1599`: sidebar compacta + hero reduzido + dashboard;
- `<1200`: hero ocultável/reduzido e prioridade para o dashboard.

### Compact Mode

Modo independente para acompanhamento durante gameplay. Quando implementado,
deve preservar funcionalidades equivalentes ao comportamento compacto atual e
pode usar always-on-top, dimensões reduzidas, status e comandos essenciais.

Não confundir o modo compacto com a janela principal.

## Design System

Todos os componentes futuros devem utilizar um Design System centralizado.

Evitar:

- cores duplicadas;
- QSS copiado entre widgets;
- números mágicos espalhados;
- fontes definidas arbitrariamente em cada componente;
- estilos inline repetidos.

## Components

Criar componentes reutilizáveis quando houver repetição real. Evitar tanto
widgets monolíticos gigantes quanto abstração excessiva de elementos triviais.
Modelos de tabela, delegates, cards, filtros e navegação devem ter
responsabilidades claras.

## Data Integrity

Dados mostrados pela nova UI devem possuir origem real. A screenshot é referência
visual, não contrato de dados.

Não apresentar permanentemente como dados reais funcionalidades que o backend
ainda não possui, incluindo:

- histórico de preço;
- volume de 7 dias;
- volume de 30 dias;
- favoritos;
- oscilação histórica;
- métricas mensais.

Mocks temporários, quando estritamente necessários para prototipação visual,
devem ser identificados, isolados e impossíveis de confundir com produção.

## Existing Functionality

O aplicativo não possui mais licenciamento, ativação por key nem HWID: o
programa abre direto na janela principal. Não reintroduzir esse fluxo sem
pedido explícito.

Preservar integralmente:

- identificação da janela do Albion;
- hotkey Insert;
- proteção da área de clique;
- OCR;
- leitura de preço;
- cálculo de custo;
- cálculo de lucro;
- identificação de oportunidades;
- sequência de categorias;
- rolagem;
- paginação;
- criação de ordens;
- fechamento de ordens;
- calibração;
- persistência;
- logs;
- notificações;
- separação dos módulos Compra, Venda e Ciclo;
- filtros de categorias, subtipos e tiers;
- perfis de compra;
- persistência em `%LOCALAPPDATA%\AlbionMKT`;
- build PyInstaller.

## Scope Discipline

Não misturar nesta migração:

- correção geral de backend;
- limpeza indiscriminada de código morto;
- mudança de banco;
- mudança de protocolos;
- mudança de OCR;
- mudança de regras econômicas.

Problemas encontrados nessas áreas devem ser documentados e tratados em escopo
separado.

## Testing

Após cada etapa relevante:

- executar testes existentes;
- verificar imports;
- verificar erros de sintaxe;
- verificar regressões;
- verificar inicialização;
- quando PySide6 estiver instalado, verificar lifecycle Qt;
- verificar encerramento limpo das threads;
- verificar comportamento do bot.

Adicionar testes de caracterização antes de alterar integrações legadas sem
cobertura.

## Git Discipline

Manter mudanças pequenas e rastreáveis. Não fazer alterações não relacionadas ao
objetivo da etapa atual. Não incluir limpeza oportunista no mesmo commit do
redesign. Nunca descartar trabalho existente sem autorização e não fazer commit,
push ou merge quando a etapa não autorizar explicitamente.
