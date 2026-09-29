$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Ambiente Python ausente. Execute: python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements.txt'
}
if (-not (Test-Path -LiteralPath (Join-Path $root '.env'))) {
    throw 'Arquivo .env ausente. Execute: .\.venv\Scripts\python scripts\bootstrap_env.py'
}

& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env

