param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$realProfile = Join-Path $env:LOCALAPPDATA 'AlbionMKT'
$testRoot = Join-Path $env:LOCALAPPDATA 'AlbionMKT-Testes'
$sessionName = 'Preset-1080-{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$testProfile = Join-Path $testRoot $sessionName

$resolvedRoot = [IO.Path]::GetFullPath($testRoot).TrimEnd('\') + '\'
$resolvedProfile = [IO.Path]::GetFullPath($testProfile).TrimEnd('\') + '\'
if (-not $resolvedProfile.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'O perfil de teste ficou fora da pasta segura permitida.'
}

New-Item -ItemType Directory -Path $testProfile -Force | Out-Null

# Nenhuma calibragem, preferencia financeira ou historico do perfil real e copiado.
if (Test-Path -LiteralPath (Join-Path $testProfile 'offsets.json')) {
    throw 'Recusa de seguranca: o novo perfil nao deveria conter offsets.json.'
}

$pythonCommand = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pythonCommand) {
    throw 'Python nao encontrado. Execute primeiro o iniciador normal do MKT.'
}
$pythonExe = $pythonCommand.Source
& $pythonExe -c "import cv2, numpy, PIL, pygetwindow, pyautogui" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'As dependencias do MKT ainda nao estao prontas neste Python.'
}

$entryPoint = Join-Path $repoRoot 'interface.py'
if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) {
    throw 'interface.py nao encontrado.'
}

$env:MKT_DATA_DIR = $testProfile
$profileNote = @(
    'PERFIL ISOLADO DE TESTE DO PRESET',
    "Criado em: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "Dados reais preservados em: $realProfile",
    'Este perfil iniciou sem offsets.json.'
)
$profileNote | Set-Content -LiteralPath (Join-Path $testProfile 'LEIA-ME.txt') -Encoding utf8

$pythonWindowed = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
$launcher = $pythonExe
if (Test-Path -LiteralPath $pythonWindowed -PathType Leaf) {
    $launcher = $pythonWindowed
}

Write-Host 'Perfil limpo criado com seguranca:'
Write-Host $testProfile
Write-Host ''
Write-Host 'O offsets.json real nao foi copiado nem alterado.'
Write-Host 'Abra o mercado no Albion, selecione um item e use VALIDAR PRESET.'

if ($ValidateOnly) {
    Write-Host 'VALIDACAO_LAUNCHER=OK'
    exit 0
}

Start-Process -FilePath $launcher -ArgumentList @("`"$entryPoint`"") -WorkingDirectory $repoRoot
