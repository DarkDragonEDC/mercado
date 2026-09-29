# ADR 001 — Migração incremental do frontend para PySide6

## Estado

Aceita para implementação incremental.

## Contexto atual

O AlbionMKT é um aplicativo Windows em Python. `interface.py` fornece a interface
Tkinter e também coordena partes do ciclo de vida. `bot.py` contém OCR, regras
financeiras e as automações de Compra, Venda e Ciclo. A comunicação usa
`bot_control.json`, `offsets.json`, logs `[DATA]`/`[BUY]` e callback de compra.

A versão atual também possui filtros de categorias e tiers, perfis de compra,
dados persistentes em `%LOCALAPPDATA%\AlbionMKT` e um atualizador externo. O
aplicativo não exige mais licenciamento por key/HWID: ele abre direto na
janela principal.

## Decisão

Criar o novo frontend com PySide6 e Qt Widgets, em paralelo ao Tkinter. A
arquitetura alvo é:

```text
backend legado protegido
        ↓
adapters e application layer
        ↓
bridge de sinais Qt
        ↓
widgets PySide6
```

O entrypoint Tkinter permanece disponível durante toda a migração. O Qt não pode
duplicar OCR, regras financeiras ou automação.

## Escopo deste checkpoint

- adapters para os contratos JSON e logs existentes;
- estado e eventos tipados;
- orquestrador independente de toolkit;
- bridge thread-safe para sinais Qt;
- janela Qt mínima para validar o ciclo de vida;
- testes unitários e de caracterização.

Ainda não fazem parte deste checkpoint:

- substituir `interface.py`;
- executar o OCR ou clicar no jogo pelo frontend Qt;
- migrar calibrações completas;
- aplicar o Design System final;
- alterar regras econômicas ou protocolos existentes.

## Compatibilidade

Por padrão, a nova composição usa a mesma pasta persistente retornada por
`app_paths.user_data_dir()`. Testes podem injetar um diretório temporário. Toda
mudança de contrato deverá possuir migração e testes próprios.

