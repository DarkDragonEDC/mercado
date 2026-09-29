# Distribuição comercial do MKT

## O que entregar ao cliente

Entregue somente `release/MKT_Setup_<versão>.exe`. Não envie a pasta do
projeto, a `.venv`, o ZIP de atualização ou o repositório privado.

O instalador:

- instala o MKT em `%LOCALAPPDATA%\Programs\MKT`;
- instala o runtime x64 oficial do Microsoft Visual C++;
- cria atalhos no menu Iniciar e na área de trabalho;
- instala o atualizador externo em `%LOCALAPPDATA%\AlbionMKT\updater`;
- preserva calibragens, ajustes, logs e cache em `%LOCALAPPDATA%\AlbionMKT`.

## Como publicar um patch

1. Altere `APP_VERSION` em `app_version.py`.
2. Execute `build_release.ps1` pelo PowerShell com política temporária:

   `powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1`

3. Teste `release/MKT_Setup_<versão>.exe` em uma máquina limpa.
4. No repositório público `luizphotoshop25-prog/AlbionMKT-Releases`, crie uma
   release em modo rascunho com a tag `v<versão>`.
5. Anexe `release/MKT_Update_<versão>.zip`,
   `release/MKT_Setup_<versão>.exe` e `release/latest.json`.
6. Publique a release somente depois que todos os arquivos terminarem de subir.
7. Mantenha as releases anteriores disponíveis para rollback.

O formato do endpoint está detalhado em `UPDATE_API_CONTRACT.md`.

## Assinatura de código

Os binários compilados ocultam o código proprietário, mas não substituem uma
assinatura digital. Sem certificado Authenticode, o Windows pode exibir
“Editor desconhecido”. Antes da venda em escala, adquira um certificado de
assinatura de código e assine `MKT.exe`, `MKTUpdater.exe` e o instalador final.

