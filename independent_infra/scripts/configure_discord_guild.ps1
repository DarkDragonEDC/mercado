param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]{17,20}$')]
    [string]$GuildId,

    [ValidatePattern('^[0-9]{17,20}(,[0-9]{17,20})*$')]
    [string]$AdminRoleIds = ""
)

$ErrorActionPreference = "Stop"

$envPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.env"))
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "Arquivo .env nao encontrado. Execute bootstrap_env.py primeiro."
}

$contents = [System.IO.File]::ReadAllText($envPath)
$replacement = "DISCORD_GUILD_ID=$GuildId"
if ($contents -match '(?m)^DISCORD_GUILD_ID=.*$') {
    $contents = [regex]::Replace($contents, '(?m)^DISCORD_GUILD_ID=.*$', $replacement)
} else {
    if ($contents.Length -gt 0 -and -not $contents.EndsWith("`n")) {
        $contents += "`r`n"
    }
    $contents += "$replacement`r`n"
}

if ($AdminRoleIds) {
    $adminReplacement = "DISCORD_ADMIN_ROLE_IDS=$AdminRoleIds"
    if ($contents -match '(?m)^DISCORD_ADMIN_ROLE_IDS=.*$') {
        $contents = [regex]::Replace(
            $contents,
            '(?m)^DISCORD_ADMIN_ROLE_IDS=.*$',
            $adminReplacement
        )
    } else {
        if ($contents.Length -gt 0 -and -not $contents.EndsWith("`n")) {
            $contents += "`r`n"
        }
        $contents += "$adminReplacement`r`n"
    }
}

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($envPath, $contents, $utf8WithoutBom)

Write-Host "Servidor privado configurado no .env local."
