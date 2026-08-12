@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Frontend Launcher
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "FRONTEND_ROOT=%PROJECT_ROOT%\frontend"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "PID_FILE=%RUN_DIR%\frontend.pid"
set "OUT_LOG=%RUN_DIR%\frontend.out.log"
set "ERR_LOG=%RUN_DIR%\frontend.err.log"
set "NO_PAUSE=0"
if /I "%~1"=="--worker" goto worker
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

echo ============================================================
echo Resume Assistant - Frontend
echo ============================================================

where.exe npm.cmd >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm.cmd was not found. Install Node.js first.
  goto failed
)
where.exe curl.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] curl.exe was not found. Windows 10 or newer is required.
  goto failed
)
where.exe powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows PowerShell was not found.
  goto failed
)
if not exist "%FRONTEND_ROOT%\node_modules" (
  echo [ERROR] frontend\node_modules is missing.
  echo Run npm install in the frontend directory first.
  goto failed
)
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

call :frontend_ready
if not errorlevel 1 (
  call :record_pid
  echo [OK] Frontend is already running.
  goto ready
)
call :port_in_use
if not errorlevel 1 (
  echo [ERROR] Port 5173 is occupied by another process.
  echo Stop that process, then run this script again.
  goto failed
)

echo [INFO] Starting Vite...
call :start_worker
if errorlevel 1 (
  echo [ERROR] Windows could not create the hidden frontend process.
  goto failed
)

set /a WAIT_COUNT=0
:wait_frontend
call :frontend_ready
if not errorlevel 1 goto frontend_started
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ 45 (
  echo [ERROR] Frontend did not become ready within 45 seconds.
  echo Review: %ERR_LOG%
  goto failed
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_frontend

:frontend_started
call :record_pid
echo [OK] Frontend started successfully.

:ready
echo URL:  http://127.0.0.1:5173
if defined SERVICE_PID echo PID:  !SERVICE_PID!
echo Logs: %RUN_DIR%
echo.
echo The frontend keeps running after this launcher closes.
call :maybe_pause
exit /b 0

:failed
echo.
echo [FAILED] Frontend was not started.
call :maybe_pause
exit /b 1

:frontend_ready
curl.exe --silent --fail --max-time 2 http://127.0.0.1:5173/ >nul 2>&1
exit /b %errorlevel%

:port_in_use
netstat.exe -ano -p tcp | findstr /R /C:":5173 .*LISTENING" >nul 2>&1
exit /b %errorlevel%

:record_pid
set "SERVICE_PID="
for /f "tokens=5" %%P in ('netstat.exe -ano -p tcp ^| findstr /R /C:":5173 .*LISTENING"') do if not defined SERVICE_PID set "SERVICE_PID=%%P"
if defined SERVICE_PID >"%PID_FILE%" echo !SERVICE_PID!
exit /b 0

:maybe_pause
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this launcher window...
  pause >nul
)
exit /b 0

:start_worker
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/c','\"%~f0\" --worker' -WindowStyle Hidden -PassThru; if ($p) { exit 0 } else { exit 1 }"
exit /b %errorlevel%

:worker
cd /d "%FRONTEND_ROOT%"
npm.cmd run dev -- --host 127.0.0.1 0<nul 1>"%OUT_LOG%" 2>"%ERR_LOG%"
exit /b %errorlevel%
