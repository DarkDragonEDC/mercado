$ErrorActionPreference = "Stop"

$envPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.env"))
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "Arquivo .env nao encontrado. Execute bootstrap_env.py primeiro."
}

$token = (Get-Clipboard -Raw).Trim()
if ($token.Length -lt 50 -or $token.Length -gt 200 -or $token -notmatch '^[A-Za-z0-9._-]+$') {
    throw "O clipboard nao parece conter um token valido do Discord."
}

$contents = [System.IO.File]::ReadAllText($envPath)
$replacement = "DISCORD_BOT_TOKEN=$token"
if ($contents -match '(?m)^DISCORD_BOT_TOKEN=.*$') {
    $contents = [regex]::Replace($contents, '(?m)^DISCORD_BOT_TOKEN=.*$', $replacement)
} else {
    if ($contents.Length -gt 0 -and -not $contents.EndsWith("`n")) {
        $contents += "`r`n"
    }
    $contents += "$replacement`r`n"
}

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($envPath, $contents, $utf8WithoutBom)
Set-Clipboard -Value " "

Write-Host "Token do novo bot salvo no .env local; clipboard limpo."
