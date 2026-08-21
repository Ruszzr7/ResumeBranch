@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Backend Launcher
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "PYTHON=%PROJECT_ROOT%\.venv-win\Scripts\python.exe"
if not defined BACKEND_PROFILE set "BACKEND_PROFILE=local"
if /I "%BACKEND_PROFILE%"=="multi_user" (
  set "PROFILE_LABEL=Multi-user MySQL"
  set "ENV_FILE=%PROJECT_ROOT%\.env.multi_user"
  set "BACKEND_RUNNER=%PROJECT_ROOT%\scripts\run_multi_user_backend.py"
  set "EXPECTED_APP_MODE=multi_user"
  set "EXPECTED_DATABASE=mysql"
) else (
  set "BACKEND_PROFILE=local"
  set "PROFILE_LABEL=Local SQLite"
  set "ENV_FILE=%PROJECT_ROOT%\.env"
  set "BACKEND_RUNNER=%PROJECT_ROOT%\scripts\run_local_backend.py"
  set "EXPECTED_APP_MODE=local"
  set "EXPECTED_DATABASE=sqlite"
)
set "PID_FILE=%RUN_DIR%\backend.pid"
set "OUT_LOG=%RUN_DIR%\backend.out.log"
set "ERR_LOG=%RUN_DIR%\backend.err.log"
set "PREFLIGHT_LOG=%RUN_DIR%\backend-preflight.err.log"
set "NO_PAUSE=0"
set "RESTART=1"
if /I "%~1"=="--worker" goto worker
call :parse_args %*

echo ============================================================
echo Resume Assistant - Backend - %PROFILE_LABEL%
echo ============================================================

if not exist "%PYTHON%" (
  echo [ERROR] .venv-win is missing. Install backend dependencies first.
  goto failed
)
if not exist "%ENV_FILE%" (
  echo [ERROR] %ENV_FILE% is missing.
  goto failed
)
if not exist "%BACKEND_RUNNER%" (
  echo [ERROR] Backend runner is missing: %BACKEND_RUNNER%
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
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

if /I "%BACKEND_PROFILE%"=="multi_user" (
  echo [INFO] Checking MySQL application credentials before restarting the backend...
  "%PYTHON%" "%BACKEND_RUNNER%" --check >nul 2>"%PREFLIGHT_LOG%"
  if errorlevel 1 (
    echo [ERROR] MySQL connection check failed. The current backend was not stopped.
    echo Review: %PREFLIGHT_LOG%
    goto failed
  )
  del /q "%PREFLIGHT_LOG%" >nul 2>&1
  echo [OK] MySQL connection check passed.
)

if "%RESTART%"=="1" (
  call :backend_ready
  if not errorlevel 1 (
    call :stop_backend
    if errorlevel 1 goto failed
  ) else (
    echo [INFO] Backend is not running; starting it now.
  )
)

call :backend_ready
if not errorlevel 1 (
  call :record_pid
  echo [OK] Backend is already running.
  goto ready
)
netstat.exe -ano -p tcp | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [ERROR] Port 8000 is occupied by another process.
  echo Stop that process, then run this script again.
  goto failed
)

echo [INFO] Starting FastAPI...
call :start_worker
if errorlevel 1 (
  echo [ERROR] Windows could not create the hidden backend process.
  goto failed
)

set /a WAIT_COUNT=0
:wait_backend
call :backend_ready
if not errorlevel 1 goto backend_started
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ 45 (
  echo [ERROR] Backend did not become ready within 45 seconds.
  echo Review: %ERR_LOG%
  goto failed
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_backend

:backend_started
call :record_pid
call :profile_ready
if errorlevel 1 (
  echo [ERROR] Backend started, but the runtime profile is not %EXPECTED_APP_MODE% + %EXPECTED_DATABASE%.
  echo Review: %ERR_LOG%
  goto failed
)
echo [OK] Backend started successfully.

:ready
call :profile_ready
if errorlevel 1 (
  echo [ERROR] Backend is reachable, but it is not running the expected profile.
  goto failed
)
echo URL:  http://127.0.0.1:8000
echo Mode: %EXPECTED_APP_MODE% + %EXPECTED_DATABASE%
if defined SERVICE_PID echo PID:  !SERVICE_PID!
echo Logs: %RUN_DIR%
echo.
echo The backend keeps running after this launcher closes.
call :maybe_pause
exit /b 0

:failed
echo.
echo [FAILED] Backend was not started.
call :maybe_pause
exit /b 1

:backend_ready
curl.exe --silent --fail --max-time 2 -X POST http://127.0.0.1:8000/health >nul 2>&1
exit /b %errorlevel%

:profile_ready
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $c = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/app/config' -TimeoutSec 3; if ($c.app_mode -eq '%EXPECTED_APP_MODE%' -and $c.database_backend -eq '%EXPECTED_DATABASE%') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:record_pid
set "SERVICE_PID="
for /f "tokens=5" %%P in ('netstat.exe -ano -p tcp ^| findstr /R /C:":8000 .*LISTENING"') do if not defined SERVICE_PID set "SERVICE_PID=%%P"
if defined SERVICE_PID >"%PID_FILE%" echo !SERVICE_PID!
exit /b 0

:stop_backend
call :record_pid
if not defined SERVICE_PID (
  echo [ERROR] Backend responded on port 8000, but its process ID could not be determined.
  exit /b 1
)
echo [INFO] Restart requested. Stopping backend process !SERVICE_PID!...
taskkill.exe /PID !SERVICE_PID! /T /F >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Unable to stop backend process !SERVICE_PID!.
  exit /b 1
)
set /a STOP_WAIT_COUNT=0
:wait_backend_stop
netstat.exe -ano -p tcp | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if errorlevel 1 (
  del /q "%PID_FILE%" >nul 2>&1
  set "SERVICE_PID="
  echo [OK] Previous backend process stopped.
  exit /b 0
)
set /a STOP_WAIT_COUNT+=1
if !STOP_WAIT_COUNT! GEQ 15 (
  echo [ERROR] Port 8000 is still occupied after stopping the backend.
  exit /b 1
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_backend_stop

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--restart" set "RESTART=1"
if /I "%~1"=="--start-only" set "RESTART=0"
shift
goto parse_args

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
cd /d "%PROJECT_ROOT%"
"%PYTHON%" "%BACKEND_RUNNER%" 0<nul 1>"%OUT_LOG%" 2>"%ERR_LOG%"
exit /b %errorlevel%
