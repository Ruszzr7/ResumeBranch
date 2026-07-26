param(
    [ValidateSet("", "local", "multi_user")]
    [string]$AppMode = "",
    [string]$LocalUserEmail = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $projectRoot ".local-run"
$python = Join-Path $projectRoot ".venv-win\Scripts\python.exe"
$frontendRoot = Join-Path $projectRoot "frontend"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv-win. Complete the local setup first."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Missing frontend/node_modules. Run npm ci in frontend first."
}

if ($AppMode) {
    $env:APP_MODE = $AppMode
}
if ($LocalUserEmail) {
    $env:LOCAL_USER_EMAIL = $LocalUserEmail
}

New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null

function Test-LocalUrl([string]$url, [string]$method = "Get") {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Method $method -Uri $url -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

if (-not (Test-LocalUrl "http://127.0.0.1:8000/health" "Post")) {
    $backendOptions = @{
        FilePath = $python
        ArgumentList = @("-m", "backend.main")
        WorkingDirectory = $projectRoot
        WindowStyle = "Hidden"
        PassThru = $true
        RedirectStandardOutput = Join-Path $runDirectory "backend.out.log"
        RedirectStandardError = Join-Path $runDirectory "backend.err.log"
    }
    $backend = Start-Process @backendOptions
    Set-Content -LiteralPath (Join-Path $runDirectory "backend.pid") -Value $backend.Id -Encoding ascii
}

if (-not (Test-LocalUrl "http://127.0.0.1:5173")) {
    $npm = (Get-Command npm.cmd).Source
    $frontendOptions = @{
        FilePath = $npm
        ArgumentList = @("run", "dev", "--", "--host", "127.0.0.1")
        WorkingDirectory = $frontendRoot
        WindowStyle = "Hidden"
        PassThru = $true
        RedirectStandardOutput = Join-Path $runDirectory "frontend.out.log"
        RedirectStandardError = Join-Path $runDirectory "frontend.err.log"
    }
    $frontend = Start-Process @frontendOptions
    Set-Content -LiteralPath (Join-Path $runDirectory "frontend.pid") -Value $frontend.Id -Encoding ascii
}

$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    $backendReady = Test-LocalUrl "http://127.0.0.1:8000/health" "Post"
    $frontendReady = Test-LocalUrl "http://127.0.0.1:5173"
} until (($backendReady -and $frontendReady) -or (Get-Date) -gt $deadline)

if (-not $backendReady -or -not $frontendReady) {
    throw "Local services did not become ready. Check .local-run/*.log."
}

Write-Output "Backend:  http://127.0.0.1:8000"
Write-Output "Frontend: http://127.0.0.1:5173"
$displayMode = if ($env:APP_MODE) { $env:APP_MODE } else { "from .env" }
Write-Output "App mode: $displayMode"
