[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$workRoot = Join-Path $projectRoot ".local-run\packaging"
$stageRoot = Join-Path $workRoot "stage"
$extractRoot = Join-Path $workRoot "extract"
$assetRoot = Join-Path $workRoot "assets"
$launcherPublish = Join-Path $workRoot "launcher"
$outputRoot = Join-Path $projectRoot "output\installer"
$cacheRoot = Join-Path $env:LOCALAPPDATA "ResumeBranchPackager\cache"
$toolRoot = Join-Path $env:LOCALAPPDATA "ResumeBranchPackager\tools"

$downloads = @(
    @{
        Name = "python-3.11.9-embed-amd64.zip"
        Url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
        Sha256 = "009D6BF7E3B2DDCA3D784FA09F90FE54336D5B60F0E0F305C37F400BF83CFD3B"
    },
    @{
        Name = "nginx-1.30.4.zip"
        Url = "https://nginx.org/download/nginx-1.30.4.zip"
        Sha256 = "159294214D403F34F0BB4AE598801AB1F6A0D8C8DA707F8F08748E294A222A01"
    },
    @{
        Name = "chrome-headless-shell-win64-151.0.7922.138.zip"
        Url = "https://storage.googleapis.com/chrome-for-testing-public/151.0.7922.138/win64/chrome-headless-shell-win64.zip"
        Sha256 = "714F4B9D17CB82A41EE10734DDE15FD8C27C08B3229CE799C0C6A7DCC7730E1E"
    },
    @{
        Name = "poppler-26.02.0-0.zip"
        Url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v26.02.0-0/Release-26.02.0-0.zip"
        Sha256 = "993E4A94376ED712FAFC7058D724EA0B943D118BBD2305CD9ED55174EB85CDA5"
    },
    @{
        Name = "innosetup-6.7.3.exe"
        Url = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
        Sha256 = "9C73C3BAE7ED48D44112A0F48E66742C00090BDB5BEF71D9D3C056C66E97B732"
    },
    @{
        Name = "ChineseSimplified.isl"
        Url = "https://raw.githubusercontent.com/jrsoftware/issrc/refs/heads/main/Files/Languages/ChineseSimplified.isl"
        Sha256 = "E0B0B350E2245F3C5E65586DFE43D574F6E7F06F2261149ABA284954B3FC9A8D"
    }
)

function Assert-UnderBuildRoot {
    param([Parameter(Mandatory)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $allowedRoot = [IO.Path]::GetFullPath($workRoot) + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to reset a path outside the packaging work directory: $fullPath"
    }
}

function Reset-BuildDirectory {
    param([Parameter(Mandatory)][string]$Path)
    Assert-UnderBuildRoot -Path $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Get-VerifiedDownload {
    param([Parameter(Mandatory)][hashtable]$Asset)
    New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
    $destination = Join-Path $cacheRoot $Asset.Name
    if (-not (Test-Path -LiteralPath $destination)) {
        Write-Host "Downloading $($Asset.Name)..."
        Invoke-WebRequest -UseBasicParsing -Uri $Asset.Url -OutFile $destination
    }
    $actual = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    if ($actual -ne $Asset.Sha256) {
        throw "SHA-256 mismatch for $($Asset.Name). Expected $($Asset.Sha256), got $actual."
    }
    return $destination
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination
    )
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | Copy-Item -Destination $Destination -Recurse -Force
}

function New-BrandIcon {
    param([Parameter(Mandatory)][string]$Destination)
    Add-Type -AssemblyName System.Drawing
    $bitmap = [Drawing.Bitmap]::new(256, 256)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([Drawing.Color]::FromArgb(48, 48, 48))
    $pale = [Drawing.Pen]::new([Drawing.Color]::FromArgb(238, 241, 245), 12)
    $blue = [Drawing.Pen]::new([Drawing.Color]::FromArgb(77, 156, 255), 12)
    $pale.StartCap = $pale.EndCap = [Drawing.Drawing2D.LineCap]::Round
    $blue.StartCap = $blue.EndCap = [Drawing.Drawing2D.LineCap]::Round
    $graphics.DrawRectangle($pale, 52, 28, 142, 126)
    $graphics.DrawLine($pale, 85, 79, 160, 79)
    $graphics.DrawLine($pale, 85, 106, 153, 106)
    $graphics.DrawLine($blue, 128, 148, 128, 194)
    $graphics.DrawLine($blue, 128, 178, 74, 218)
    $graphics.DrawLine($pale, 128, 178, 182, 218)
    $graphics.DrawEllipse($blue, 111, 164, 34, 34)
    $graphics.DrawEllipse($pale, 59, 203, 30, 30)
    $graphics.DrawEllipse($pale, 167, 203, 30, 30)
    $graphics.Dispose()
    $pale.Dispose()
    $blue.Dispose()

    $pngPath = [IO.Path]::ChangeExtension($Destination, ".png")
    $bitmap.Save($pngPath, [Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    $png = [IO.File]::ReadAllBytes($pngPath)
    $stream = [IO.File]::Create($Destination)
    $writer = [IO.BinaryWriter]::new($stream)
    $writer.Write([UInt16]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]1)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]32)
    $writer.Write([UInt32]$png.Length)
    $writer.Write([UInt32]22)
    $writer.Write($png)
    $writer.Dispose()
    Remove-Item -LiteralPath $pngPath -Force
}

Set-Location $projectRoot
New-Item -ItemType Directory -Force -Path $workRoot, $outputRoot, $toolRoot | Out-Null
Reset-BuildDirectory -Path $stageRoot
Reset-BuildDirectory -Path $extractRoot
Reset-BuildDirectory -Path $assetRoot
Reset-BuildDirectory -Path $launcherPublish

$trackedChangesBefore = @(git status --porcelain --untracked-files=no)
if ($trackedChangesBefore.Count -gt 0) {
    throw "Tracked files already contain changes. Commit or stash them before creating a release package."
}

$resolved = @{}
foreach ($asset in $downloads) {
    $resolved[$asset.Name] = Get-VerifiedDownload -Asset $asset
}

if (-not $SkipTests) {
    $testPython = Join-Path $projectRoot ".venv-win\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $testPython)) {
        throw "The build-time test environment .venv-win is missing."
    }
    & $testPython -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

    Push-Location (Join-Path $projectRoot "frontend")
    try {
        & npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
    }
    finally {
        Pop-Location
    }
}

Push-Location (Join-Path $projectRoot "frontend")
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
}
finally {
    Pop-Location
}

$appStage = Join-Path $stageRoot "app"
$runtimeStage = Join-Path $stageRoot "runtime"
$resourceStage = Join-Path $stageRoot "resources"
$licenseStage = Join-Path $stageRoot "licenses"
New-Item -ItemType Directory -Force -Path $appStage, $runtimeStage, $resourceStage, $licenseStage | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot "backend") -Destination $appStage -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appStage "scripts"), (Join-Path $appStage "packaging") | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\run_local_backend.py") -Destination (Join-Path $appStage "scripts\run_local_backend.py") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\run_installed_backend.py") -Destination (Join-Path $appStage "packaging\run_installed_backend.py") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appStage "frontend") | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "frontend\dist") -Destination (Join-Path $appStage "frontend") -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appStage "data\source_documents"), (Join-Path $appStage "output\resumes"), (Join-Path $appStage ".local-run") | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\nginx.local.conf.template") -Destination (Join-Path $resourceStage "nginx.local.conf.template") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination (Join-Path $licenseStage "ResumeBranch-LICENSE.txt") -Force

Get-ChildItem -LiteralPath $appStage -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $appStage -File -Recurse -Include "*.pyc", "*.pyo" | Remove-Item -Force

$pythonExtract = Join-Path $extractRoot "python"
Expand-Archive -LiteralPath $resolved["python-3.11.9-embed-amd64.zip"] -DestinationPath $pythonExtract -Force
$pythonStage = Join-Path $runtimeStage "python"
Copy-DirectoryContents -Source $pythonExtract -Destination $pythonStage
New-Item -ItemType Directory -Force -Path (Join-Path $pythonStage "Lib\site-packages") | Out-Null
$pthFile = Get-ChildItem -LiteralPath $pythonStage -Filter "python*._pth" | Select-Object -First 1
if (-not $pthFile) { throw "Embedded Python path configuration was not found." }
[IO.File]::WriteAllText($pthFile.FullName, "python311.zip`r`n.`r`nLib\site-packages`r`nimport site`r`n", [Text.Encoding]::ASCII)

$buildPython = Join-Path $projectRoot ".venv-win\Scripts\python.exe"
& $buildPython -m pip install --disable-pip-version-check --no-compile --no-warn-script-location --requirement (Join-Path $projectRoot "backend\requirements.lock.txt") --target (Join-Path $pythonStage "Lib\site-packages")
if ($LASTEXITCODE -ne 0) { throw "Private Python dependency assembly failed." }

$nginxExtract = Join-Path $extractRoot "nginx"
Expand-Archive -LiteralPath $resolved["nginx-1.30.4.zip"] -DestinationPath $nginxExtract -Force
$nginxSource = Get-ChildItem -LiteralPath $nginxExtract -Directory | Select-Object -First 1
if (-not $nginxSource) { throw "Nginx archive layout was not recognized." }
Copy-DirectoryContents -Source $nginxSource.FullName -Destination (Join-Path $runtimeStage "nginx")

$chromeExtract = Join-Path $extractRoot "chrome"
Expand-Archive -LiteralPath $resolved["chrome-headless-shell-win64-151.0.7922.138.zip"] -DestinationPath $chromeExtract -Force
$chromeSource = Get-ChildItem -LiteralPath $chromeExtract -Directory | Where-Object Name -eq "chrome-headless-shell-win64" | Select-Object -First 1
if (-not $chromeSource) { throw "Chromium archive layout was not recognized." }
Copy-DirectoryContents -Source $chromeSource.FullName -Destination (Join-Path $runtimeStage "chromium")

$popplerExtract = Join-Path $extractRoot "poppler"
Expand-Archive -LiteralPath $resolved["poppler-26.02.0-0.zip"] -DestinationPath $popplerExtract -Force
$pdfInfo = Get-ChildItem -LiteralPath $popplerExtract -File -Recurse -Filter "pdfinfo.exe" | Select-Object -First 1
if (-not $pdfInfo) { throw "Poppler archive layout was not recognized." }
$popplerSource = $pdfInfo.Directory.Parent.Parent.FullName
Copy-DirectoryContents -Source $popplerSource -Destination (Join-Path $runtimeStage "poppler")

New-BrandIcon -Destination (Join-Path $assetRoot "ResumeBranch.ico")
& dotnet publish (Join-Path $projectRoot "launcher\ResumeBranch.Launcher.csproj") -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:DebugType=None -p:DebugSymbols=false -p:ApplicationIcon="$(Join-Path $assetRoot 'ResumeBranch.ico')" -o $launcherPublish
if ($LASTEXITCODE -ne 0) { throw "Launcher build failed." }
Copy-Item -LiteralPath (Join-Path $launcherPublish "ResumeBranch.exe") -Destination (Join-Path $stageRoot "ResumeBranch.exe") -Force

& (Join-Path $pythonStage "python.exe") -B -c "import fastapi, sqlalchemy, langgraph, docx, PIL; print('private runtime ok')"
if ($LASTEXITCODE -ne 0) { throw "Private Python runtime verification failed." }
Get-ChildItem -LiteralPath $pythonStage -File -Recurse -Filter "*.pyc" | Remove-Item -Force

$innoRoot = Join-Path $toolRoot "InnoSetup-6.7.3"
$iscc = Join-Path $innoRoot "ISCC.exe"
if (-not (Test-Path -LiteralPath $iscc)) {
    New-Item -ItemType Directory -Force -Path $innoRoot | Out-Null
    $arguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CURRENTUSER",
        "/DIR=$innoRoot"
    )
    $process = Start-Process -FilePath $resolved["innosetup-6.7.3.exe"] -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $iscc)) {
        throw "Inno Setup compiler installation failed with exit code $($process.ExitCode)."
    }
}

& $iscc "/Qp" "/DSourceDir=$stageRoot" "/DOutputDir=$outputRoot" "/DSetupIcon=$(Join-Path $assetRoot 'ResumeBranch.ico')" "/DLanguageFile=$($resolved['ChineseSimplified.isl'])" (Join-Path $projectRoot "installer\ResumeBranch.iss")
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed." }

$trackedChangesAfter = @(git diff --name-only -- backend frontend/src scripts)
if ($trackedChangesAfter.Count -gt 0) {
    throw "Frozen application files changed during packaging: $($trackedChangesAfter -join ', ')"
}

$installerPath = Join-Path $outputRoot "ResumeBranch-Setup-v1.1.2-x64.exe"
$installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Installer ready: $installerPath"
Write-Host "SHA-256: $installerHash"
