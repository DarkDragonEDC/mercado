$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Ambiente Python ausente.'
}
if (-not (Test-Path -LiteralPath (Join-Path $root '.env'))) {
    throw 'Arquivo .env ausente.'
}

Get-Content -LiteralPath (Join-Path $root '.env') | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
& $python -m bot.discord_bot

