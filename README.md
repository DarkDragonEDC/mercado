# MKT — versão de teste em código-fonte

Esta pasta executa o programa diretamente pelo Python e não contém o aplicativo
compilado em `.exe`.

Esta edição inclui o novo HUD moderno inspirado em Albion, o título **MKT**,
o rodapé **produzido por: S e M** e o assistente de calibragem. A rotina principal
do bot foi preservada para não acrescentar atrasos ao ciclo de compras.

A identidade visual usa a paleta oficial do projeto: azul-marinho profundo,
azul aço, dourado lunar e creme. Verde e vermelho ficam reservados para estados
de sucesso e interrupção/erro.

## Requisitos

- Windows 10 ou 11 de 64 bits.
- O instalador tenta localizar ou instalar automaticamente o Python 3.11 de
  64 bits pelo Windows Package Manager (`winget`).
- Internet apenas durante a primeira instalação das bibliotecas.

Os modelos do EasyOCR já estão na pasta `ocr_models`, evitando downloads de
modelos durante a primeira execução.

## Primeira execução

1. Execute `INICIAR_BOT.bat`.
2. Se o Python estiver ausente, confirme a instalação automática e aguarde.
3. Depois da primeira preparação, o MKT será iniciado.
4. Faça a calibragem neste computador.

Depois disso, use somente `INICIAR_BOT.bat`. Caso o computador não possua o
`winget`, o instalador abre a página oficial do Python e informa o que deve ser
instalado.

Em instalações novas com Albion em 1920×1080, DPI 96 e interface PT-BR, o
assistente pode aplicar o preset certificado de Compra, Venda e Ciclo. O pacote
inclui as referências visuais e coordenadas homologadas, inclusive número da
página e **Pegar todos**. Configurações pessoais e financeiras não fazem parte
do preset.

## Calibragem guiada

Na aba de configuração, abra a **Central de Calibragem** e escolha o guia de
compras. O assistente mostra uma etapa por vez, informa o que deve estar aberto
no Albion e marca automaticamente cada campo concluído. A configuração de
categorias e a área de fechamento possuem guias separados.

Durante a marcação, a janela principal é escondida para não cobrir o jogo. Uma
lupa amplia a região do cursor e permite selecionar o centro dos botões com
mais precisão. Ao terminar, use **Validar sem cliques** para conferir todos os
pontos e testar o reconhecimento do botão Pedido.

Esses recursos funcionam antes de iniciar o bot e não adicionam OCR, esperas ou
cliques ao ciclo de compra.

## Modos de automação

- **Compra:** cria ordens continuamente e não abre a rotina de venda.
- **Venda:** percorre os itens da mochila e cria os pedidos de venda.
- **Ciclo:** compra até o limite configurado, coleta os produtos, vende e volta
  automaticamente para as compras.

O limite do Ciclo é configurado na própria aba **CICLO**. O valor antigo de 48
compras continua sendo usado como padrão para configurações existentes.

## Arquivos principais

- `interface.py`: interface gráfica e inicialização.
- `bot.py`: OCR, análise da loja e automação de cliques.
- `coordinate_system.py`: calibragem normalizada entre resoluções e escalas.
- `assets/`: imagens usadas pelo reconhecimento visual.
- `ocr_models/`: modelos locais necessários pelo EasyOCR.
- `requirements.txt`: versões validadas das bibliotecas Python.

## Diagnóstico do OCR

Com o ambiente instalado, execute:

```bat
.venv\Scripts\python.exe interface.py --diagnose-ocr
```

O resultado será salvo em `diagnostico_ocr.txt`.

## Testes do código

Execute `TESTAR_CODIGO.bat` ou use o comando abaixo:

```bat
.venv\Scripts\python.exe -m unittest discover -v
```

Arquivos pessoais como calibragens, relatórios e caches não são incluídos na
distribuição limpa.

## Antes de uma futura compilação

Teste principalmente **Iniciar bot**, a troca de categorias, a calibragem guiada
e **Validar sem cliques**. O `.exe` só deve ser gerado depois que esta versão em
código-fonte for aprovada.
