@echo off
setlocal EnableExtensions
cd /d "%~dp0"
goto :main

:validar_python
if not exist "%~1" exit /b 0
echo %~1 | find /I "\WindowsApps\" >nul
if not errorlevel 1 exit /b 0
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0

:localizar_python
set "PYTHON_EXE="

for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys; print(sys.executable)" 2^>nul`) do call :validar_python "%%P"
if defined PYTHON_EXE exit /b 0

call :validar_python "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined PYTHON_EXE exit /b 0
call :validar_python "%ProgramFiles%\Python311\python.exe"
if defined PYTHON_EXE exit /b 0
call :validar_python "C:\Python311\python.exe"
if defined PYTHON_EXE exit /b 0

for /f "delims=" %%P in ('where python 2^>nul') do call :validar_python "%%P"
exit /b 0

:main
echo Verificando o Python 3.11 de 64 bits...
call :localizar_python

if /I "%MKT_CHECK_PYTHON_ONLY%"=="1" (
    if defined PYTHON_EXE (
        echo PYTHON_OK=%PYTHON_EXE%
        exit /b 0
    )
    echo PYTHON_MISSING
    exit /b 1
)

if not defined PYTHON_EXE (
    echo.
    echo Python 3.11 nao encontrado.
    where winget >nul 2>nul
    if errorlevel 1 goto :instalacao_manual

    echo Instalando automaticamente o Python 3.11 para este usuario...
    winget install --exact --id Python.Python.3.11 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
    echo.
    echo Conferindo a instalacao do Python...
    call :localizar_python
)

if not defined PYTHON_EXE goto :instalacao_manual

echo Python encontrado:
echo %PYTHON_EXE%

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Criando o ambiente isolado do MKT...
    "%PYTHON_EXE%" -m venv ".venv"
    if errorlevel 1 goto :erro
)

echo.
echo Atualizando o instalador de pacotes...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :erro

echo.
echo Instalando as dependencias do MKT...
echo Esta etapa pode demorar na primeira execucao.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :erro

echo.
echo Validando a instalacao uma unica vez...
".venv\Scripts\python.exe" "%~dp0dependency_manager.py" --verify-and-mark
if errorlevel 1 goto :erro

echo.
echo Instalacao concluida. O MKT ja pode ser iniciado.
pause
exit /b 0

:instalacao_manual
echo.
echo Nao foi possivel instalar o Python automaticamente.
echo A pagina oficial sera aberta. Instale o Python 3.11 de 64 bits,
echo marque a opcao para adicionar o Python ao PATH e execute este arquivo novamente.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:erro
echo.
echo Nao foi possivel concluir a instalacao.
echo Confira a conexao com a internet e tente novamente.
pause
exit /b 1
