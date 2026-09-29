# Presets de calibragem

## Garantias do fluxo

- O tamanho considerado e a area cliente real da janela do Albion, nao apenas a
  resolucao declarada do monitor.
- Geometria, DPI e idioma precisam corresponder exatamente.
- Nenhum clique e executado durante a validacao do preset.
- A lista de pedidos e uma referencia visual obrigatoria. Outras tres provas
  precisam passar entre ancora, nome, venda e compra.
- O `offsets.json` anterior e copiado para `offsets.pre-preset.json`.
- Somente campos espaciais sao substituidos. Key, banca, perfil financeiro,
  delays, categorias e tiers permanecem locais.
- Templates ativos ficam em
  `%LOCALAPPDATA%\AlbionMKT\calibration_assets`, separados dos recursos
  imutaveis do instalador.
- Falha de gravacao ou validacao restaura configuracoes e templates anteriores.
- Preset incompativel nunca e aproximado; o usuario recebe a calibragem manual.

## Fluxo do cliente

Ao abrir o aplicativo, uma calibragem existente e validada e reutilizada. Em uma
instalacao nova, o assistente localiza o Albion, seleciona um unico preset
compativel e pede que o usuario abra o mercado e selecione um item. A validacao
e passiva e a aplicacao permanece transacional.

O preset certificado de 1920x1080 inclui Compra, Venda e Ciclo. Ele contem a
area do numero da pagina e o ponto de `Pegar todos` homologado no teste real de
Ciclo. Presets futuros podem declarar apenas os modos efetivamente testados; um
preset que declara somente `buy` nao desbloqueia os demais modulos.

## Exportacao para homologacao

O colaborador deve calibrar a versao atual e fechar o MKT. No repositorio:

```powershell
python scripts\export_calibration_preset.py `
  --id albion-2560x1440-dpi96-ptbr-full-v1 `
  --label "Albion 2560x1440 - Compra, Venda e Ciclo - PT-BR" `
  --modes buy sell cycle `
  --output "C:\Preset-Albion-2K"
```

O pacote gerado contem apenas coordenadas normalizadas, metadados tecnicos e
amostras visuais. O exportador recusa modos cuja calibragem esteja incompleta.
Cada preset possui uma pasta visual propria para evitar colisao entre 1080p,
2K e futuras variantes.

Antes de distribuir um novo pacote, mover seu JSON para `presets`, manter os
caminhos relativos dos assets, executar `python -m unittest discover -q` e
realizar a prova passiva e uma sessao real controlada na maquina de origem.
