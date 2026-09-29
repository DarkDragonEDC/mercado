param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [string]$DownloadBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TestPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = Join-Path $RepoRoot ".venv-build\Scripts\python.exe"
$BuildRoot = Join-Path $RepoRoot "build"
$ReleaseRoot = Join-Path $RepoRoot "release"
$PrerequisiteRoot = Join-Path $RepoRoot "build\prerequisites"
$VcRedist = Join-Path $PrerequisiteRoot "VC_redist.x64.exe"
$VcRedistUrl = "https://aka.ms/vc14/vc_redist.x64.exe"

function Remove-SafeDirectory([string]$Path) {
    $resolvedRepo = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\') + '\'
    $resolvedTarget = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    if (-not $resolvedTarget.StartsWith($resolvedRepo, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Recusa ao remover caminho fora do projeto: $resolvedTarget"
    }
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $TestPython)) {
    throw "Ambiente Python de testes do projeto nao encontrado."
}
if (-not (Test-Path -LiteralPath $Python)) {
    & py -3.11 -m venv (Join-Path $RepoRoot ".venv-build")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente Python de build." }
}

$versionSource = Get-Content -LiteralPath (Join-Path $RepoRoot "app_version.py") -Raw
$versionMatch = [regex]::Match($versionSource, 'APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"')
if (-not $versionMatch.Success) {
    throw "APP_VERSION invalida."
}
$Version = $versionMatch.Groups[1].Value
if ([string]::IsNullOrWhiteSpace($DownloadBaseUrl)) {
    $DownloadBaseUrl = "https://github.com/luizphotoshop25-prog/AlbionMKT-Releases/releases/download/v$Version"
}
$IconPath = Join-Path $RepoRoot "assets\icon.ico"
$OcrModels = Join-Path $RepoRoot "ocr_models"
$CalibrationPresets = Join-Path $RepoRoot "presets"

if (-not $SkipTests) {
    & $TestPython -m unittest discover -q
    if ($LASTEXITCODE -ne 0) { throw "Os testes falharam." }
}

& $Python -m pip install --disable-pip-version-check -r (Join-Path $RepoRoot "build-runtime-requirements.txt") -r (Join-Path $RepoRoot "build-requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar ferramentas de build." }

Remove-SafeDirectory $BuildRoot
Remove-SafeDirectory $ReleaseRoot
New-Item -ItemType Directory -Path $BuildRoot, $ReleaseRoot | Out-Null

# O runtime oficial e necessario apenas para o instalador de primeira
# instalacao. Atualizacoes por patch trocam somente a pasta do aplicativo,
# portanto nao devem depender desse download nem de um instalador aberto.
if (-not $SkipInstaller) {
    New-Item -ItemType Directory -Path $PrerequisiteRoot -Force | Out-Null
    Invoke-WebRequest -Uri $VcRedistUrl -OutFile $VcRedist -UseBasicParsing
    try {
        $VcSignature = Get-AuthenticodeSignature -FilePath $VcRedist -ErrorAction Stop
        $VcSignatureStatus = [string]$VcSignature.Status
        $VcSignerSubject = [string]$VcSignature.SignerCertificate.Subject
    }
    catch {
        # Algumas distribuicoes recentes do PowerShell 7 nao carregam o modulo
        # Microsoft.PowerShell.Security. O host nativo do Windows continua
        # disponivel e e usado apenas para manter a mesma validacao de assinatura.
        $LegacyPowerShell = Join-Path ([Environment]::SystemDirectory) "WindowsPowerShell\v1.0\powershell.exe"
        if (-not (Test-Path -LiteralPath $LegacyPowerShell)) {
            throw "Nao foi possivel carregar a verificacao de assinatura do Windows."
        }
        $escapedVcRedist = $VcRedist.Replace("'", "''")
        $signatureCommand = '$ProgressPreference = ''SilentlyContinue''; $signature = Get-AuthenticodeSignature -FilePath ''' + $escapedVcRedist + '''; [Console]::Write(([string]$signature.Status + [char]124 + [string]$signature.SignerCertificate.Subject))'
        $encodedSignatureCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($signatureCommand))
        $signatureResult = & $LegacyPowerShell -NoProfile -EncodedCommand $encodedSignatureCommand
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($signatureResult)) {
            throw "Nao foi possivel verificar a assinatura do Microsoft Visual C++ Redistributable."
        }
        $signatureParts = ([string]$signatureResult).Trim() -split '\|', 2
        $VcSignatureStatus = $signatureParts[0]
        $VcSignerSubject = if ($signatureParts.Count -gt 1) { $signatureParts[1] } else { "" }
    }
    if ($VcSignatureStatus -ne "Valid" -or $VcSignerSubject -notmatch "Microsoft") {
        throw "O Microsoft Visual C++ Redistributable nao possui assinatura valida da Microsoft."
    }
}

# Recursos distribuidos: mantem os PNGs oficiais e exclui capturas locais.
$ResourceRoot = Join-Path $BuildRoot "resources"
$PackagedAssets = Join-Path $ResourceRoot "assets"
New-Item -ItemType Directory -Path $PackagedAssets | Out-Null
Get-ChildItem -LiteralPath (Join-Path $RepoRoot "assets") -File | ForEach-Object {
    if ($_.Name -notin @("pedido_usuario.png", "vender_usuario.png")) {
        Copy-Item -LiteralPath $_.FullName -Destination $PackagedAssets
    }
}
$PackagedItemCache = Join-Path $PackagedAssets "item_cache"
New-Item -ItemType Directory -Path $PackagedItemCache | Out-Null
Get-ChildItem -LiteralPath (Join-Path $RepoRoot "assets\item_cache") -File -Filter "*_render.png" | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $PackagedItemCache
}

# Copia por lista segura somente as referencias declaradas nos presets. O
# proprio utilitario valida caminhos, hashes e a arvore final antes da build.
& $TestPython (Join-Path $RepoRoot "release_packaging.py") stage `
    --repo-root $RepoRoot `
    --presets-dir $CalibrationPresets `
    --packaged-assets $PackagedAssets
if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar os assets certificados dos presets." }

$MainOutput = Join-Path $BuildRoot "main"
& $Python -m nuitka `
    --mode=standalone `
    --assume-yes-for-downloads `
    --mingw64 `
    --enable-plugin=tk-inter `
    --windows-console-mode=disable `
    --nofollow-import-to=torch `
    --nofollow-import-to=torchvision `
    --no-deployment-flag=excluded-module-usage `
    --include-module=PIL.ImageEnhance `
    --include-module=PIL.ImageOps `
    "--windows-icon-from-ico=$IconPath" `
    --output-filename=MKT.exe `
    --output-dir=$MainOutput `
    "--include-data-dir=$PackagedAssets=assets" `
    "--include-data-dir=$CalibrationPresets=presets" `
    "--include-data-dir=$OcrModels=ocr_models" `
    --include-package-data=easyocr `
    --nofollow-import-to=unittest `
    (Join-Path $RepoRoot "interface.py")
if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar o MKT." }

$CompiledApp = Join-Path $MainOutput "interface.dist"
if (-not (Test-Path -LiteralPath (Join-Path $CompiledApp "MKT.exe"))) {
    throw "Build do MKT nao encontrado."
}
& $TestPython (Join-Path $RepoRoot "release_packaging.py") validate `
    --presets-dir (Join-Path $CompiledApp "presets") `
    --asset-root $CompiledApp
if ($LASTEXITCODE -ne 0) { throw "A build compilada perdeu arquivos de preset." }

# Torch e torchvision precisam permanecer como bibliotecas oficiais em Python.
# O codigo proprietario do MKT continua totalmente compilado pelo Nuitka.
$SitePackages = Join-Path (Split-Path -Parent $Python) "..\Lib\site-packages"
$SitePackages = [IO.Path]::GetFullPath($SitePackages)
foreach ($package in @("torch", "torchgen", "torchvision", "sympy", "mpmath", "networkx", "filelock", "fsspec", "jinja2", "markupsafe")) {
    $sourcePackage = Join-Path $SitePackages $package
    if (-not (Test-Path -LiteralPath $sourcePackage)) { throw "Dependencia de runtime ausente: $package" }
    Copy-Item -LiteralPath $sourcePackage -Destination $CompiledApp -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $SitePackages "typing_extensions.py") -Destination $CompiledApp -Force
Get-ChildItem -LiteralPath $SitePackages -Directory | Where-Object {
    $_.Name -match '^(torch|torchvision)-.*\.dist-info$'
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $CompiledApp -Recurse -Force
}

$StandardLibrary = (& $Python -c "import sysconfig; print(sysconfig.get_path('stdlib'))").Trim()
if (-not (Test-Path -LiteralPath $StandardLibrary)) { throw "Biblioteca padrao do Python nao encontrada." }
foreach ($module in @("pdb.py", "bdb.py", "cmd.py", "code.py", "codeop.py", "cProfile.py", "profile.py", "pstats.py")) {
    Copy-Item -LiteralPath (Join-Path $StandardLibrary $module) -Destination $CompiledApp -Force
}
Copy-Item -LiteralPath (Join-Path $StandardLibrary "unittest") -Destination $CompiledApp -Recurse -Force

$ReleaseApp = Join-Path $ReleaseRoot "app"
Copy-Item -LiteralPath $CompiledApp -Destination $ReleaseApp -Recurse

$UpdaterOutput = Join-Path $BuildRoot "updater"
& $Python -m nuitka `
    --mode=onefile `
    --assume-yes-for-downloads `
    --mingw64 `
    --windows-console-mode=disable `
    "--windows-icon-from-ico=$IconPath" `
    --output-filename=MKTUpdater.exe `
    --output-dir=$UpdaterOutput `
    (Join-Path $RepoRoot "updater.py")
if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar o atualizador." }
Copy-Item -LiteralPath (Join-Path $UpdaterOutput "MKTUpdater.exe") -Destination $ReleaseRoot
# O patch tambem leva o atualizador para que, depois de aplicado, o MKT possa
# renovar de forma segura o executavel externo que mostra o progresso visual.
$BundledUpdaterDir = Join-Path $ReleaseApp "updater"
New-Item -ItemType Directory -Path $BundledUpdaterDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $UpdaterOutput "MKTUpdater.exe") -Destination $BundledUpdaterDir

$UpdatePackage = Join-Path $ReleaseRoot "MKT_Update_$Version.zip"
Compress-Archive -LiteralPath $ReleaseApp -DestinationPath $UpdatePackage -CompressionLevel Optimal
$PackageInfo = Get-Item -LiteralPath $UpdatePackage
$PackageHash = (Get-FileHash -LiteralPath $UpdatePackage -Algorithm SHA256).Hash.ToLowerInvariant()
$Manifest = [ordered]@{
    version = $Version
    channel = "stable"
    downloadUrl = "$($DownloadBaseUrl.TrimEnd('/'))/MKT_Update_$Version.zip"
    sha256 = $PackageHash
    size = $PackageInfo.Length
    mandatory = $false
    minimumVersion = $Version
    signature = $null
    releaseNotes = @(
        "Painel de novidades exibido antes da tela principal.",
        "Atualizacoes automaticas continuam protegidas e preservam suas configuracoes.",
        "Nas proximas versoes, as melhorias e orientacoes aparecerao neste painel."
    )
}
$Manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReleaseRoot "latest.json") -Encoding utf8

if (-not $SkipInstaller) {
    $IsccCandidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $Iscc) { throw "Inno Setup nao encontrado. Instale-o ou use -SkipInstaller." }
    & $Iscc "/DMyAppVersion=$Version" "/DVcRedistPath=$VcRedist" (Join-Path $RepoRoot "installer\MKT.iss")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
}

Write-Output "RELEASE_OK version=$Version path=$ReleaseRoot"
