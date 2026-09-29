@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python nao encontrado.
    echo Execute primeiro INSTALAR_DEPENDENCIAS.bat.
    pause
    exit /b 1
)

echo Executando os testes automatizados do MKT...
"%~dp0.venv\Scripts\python.exe" -B -m unittest discover -v
if errorlevel 1 (
    echo.
    echo Um ou mais testes falharam.
    pause
    exit /b 1
)

echo.
echo Todos os testes foram aprovados.
pause
