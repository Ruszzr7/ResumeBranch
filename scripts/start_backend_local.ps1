param(
    [ValidateSet("", "local", "multi_user")]
    [string]$AppMode = "",
    [string]$LocalUserEmail = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv-win\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv-win. Run the local setup first."
}

if ($AppMode) {
    $env:APP_MODE = $AppMode
}
if ($LocalUserEmail) {
    $env:LOCAL_USER_EMAIL = $LocalUserEmail
}

Set-Location $projectRoot
& $python -m backend.main
