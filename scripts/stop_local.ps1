$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $projectRoot ".local-run"

foreach ($name in @("backend", "frontend")) {
    $pidFile = Join-Path $runDirectory "$name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) {
        continue
    }

    $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        & taskkill.exe /PID $processId /T /F | Out-Null
        Write-Output "Stopped $name process tree ($processId)."
    }
    Remove-Item -LiteralPath $pidFile -Force
}
