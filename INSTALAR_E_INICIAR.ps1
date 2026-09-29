param(
    [switch]$DetectOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonInstaller = Join-Path $env:TEMP ("python-3.11.9-amd64-{0}.exe" -f $PID)

function Test-CompatiblePython {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    try {
        $detected = & $Path -c "import struct,sys; print(sys.executable if sys.version_info[:2] >= (3, 11) and struct.calcsize('P') * 8 == 64 else '')" 2>$null | Select-Object -First 1
        if (-not [string]::IsNullOrWhiteSpace($detected)) {
            return [System.IO.Path]::GetFullPath($detected.Trim())
        }
    } catch {
        return $null
    }
    return $null
}

function Find-CompatiblePython {
    $candidates = New-Object System.Collections.Generic.List[string]

    try {
        foreach ($launcherSelector in @('-3', '-3.11-64')) {
            $launcherPath = & py $launcherSelector -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1
            if ($launcherPath) {
                $candidates.Add($launcherPath.Trim())
            }
        }
    } catch {}

    foreach ($commandName in @('python.exe', 'python3.exe')) {
        $command = Get-Command $commandName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            $candidates.Add($command.Source)
        }
    }

    foreach ($root in @($env:LOCALAPPDATA, $env:ProgramFiles)) {
        if ($root) {
            foreach ($pythonRoot in @((Join-Path $root 'Programs\Python'), $root)) {
                if (Test-Path -LiteralPath $pythonRoot -PathType Container) {
                    Get-ChildItem -LiteralPath $pythonRoot -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
                        Sort-Object Name -Descending |
                        ForEach-Object { $candidates.Add((Join-Path $_.FullName 'python.exe')) }
                }
            }
        }
    }

    $usersRoot = Join-Path $env:SystemDrive 'Users'
    if (Test-Path -LiteralPath $usersRoot -PathType Container) {
        Get-ChildItem -LiteralPath $usersRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $pythonRoot = Join-Path $_.FullName 'AppData\Local\Programs\Python'
            if (Test-Path -LiteralPath $pythonRoot -PathType Container) {
                Get-ChildItem -LiteralPath $pythonRoot -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending |
                    ForEach-Object { $candidates.Add((Join-Path $_.FullName 'python.exe')) }
            }
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $key = $candidate.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true

        $valid = Test-CompatiblePython -Path $candidate
        if ($valid) { return $valid }
    }
    return $null
}

Write-Host 'Verificando o Python 3.11 ou mais recente, de 64 bits...'
$pythonExe = Find-CompatiblePython

if ($pythonExe) {
    Write-Host "Python encontrado: $pythonExe"
} else {
    if ($DetectOnly) {
        throw 'Python 3.11 ou mais recente, de 64 bits, nao encontrado.'
    }
    Write-Host 'Python 3.11 de 64 bits nao encontrado. Baixando o instalador oficial...'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $pythonInstaller

    Write-Host 'Instalando o Python somente para o usuario atual...'
    $installer = Start-Process -FilePath $pythonInstaller -ArgumentList @(
        '/quiet',
        'InstallAllUsers=0',
        'PrependPath=1',
        'Include_launcher=1',
        'Include_test=0'
    ) -Wait -PassThru

    if ($installer.ExitCode -eq 1603) {
        Write-Host 'O Windows encontrou uma instalacao incompleta do Python. Tentando reparar...'
        $repair = Start-Process -FilePath $pythonInstaller -ArgumentList @('/quiet', '/repair') -Wait -PassThru
        Write-Host "Reparo concluido com codigo $($repair.ExitCode)."
    } elseif ($installer.ExitCode -notin @(0, 3010)) {
        throw "O instalador do Python retornou o codigo $($installer.ExitCode)."
    }
    Remove-Item -LiteralPath $pythonInstaller -Force -ErrorAction SilentlyContinue

    $pythonExe = Find-CompatiblePython
    if (-not $pythonExe) {
        throw 'O Python nao foi localizado apos a instalacao ou reparo. Remova a instalacao incompleta do Python em Aplicativos Instalados e execute novamente.'
    }
    Write-Host "Python instalado: $pythonExe"
}

if ($DetectOnly) {
    Write-Host 'DETECCAO_PYTHON=OK'
    exit 0
}

Write-Host 'Preparando o instalador de pacotes...'
& $pythonExe -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel preparar o pip.' }

& $pythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel atualizar o pip.' }

$requirements = Join-Path $appDir 'requirements.txt'
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Arquivo nao encontrado: $requirements"
}

Write-Host 'Instalando as dependencias do AlbionElite...'
& $pythonExe -m pip install --requirement $requirements
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar as dependencias.' }

$entryPoint = Join-Path $appDir 'interface.py'
if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) {
    throw "Arquivo nao encontrado: $entryPoint"
}

Write-Host 'Instalacao concluida. Iniciando o AlbionElite...'
Start-Process -FilePath $pythonExe -ArgumentList @("`"$entryPoint`"") -WorkingDirectory $appDir
