@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Start All
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "NO_PAUSE=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

echo ============================================================
echo Resume Assistant - Start Database, Backend and Frontend
echo ============================================================
echo.

call "%~dp0start_db_local.cmd" --no-pause
if errorlevel 1 goto failed
echo.
call "%~dp0start_backend_local.cmd" --no-pause
if errorlevel 1 goto failed
echo.
call "%~dp0start_frontend_local.cmd" --no-pause
if errorlevel 1 goto failed

call :database_ready
if errorlevel 1 goto failed
call :backend_ready
if errorlevel 1 goto failed
call :frontend_ready
if errorlevel 1 goto failed

echo.
echo ============================================================
echo [OK] The complete project is running.
echo ============================================================
echo Database: 127.0.0.1:3306
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Logs:     %RUN_DIR%
echo.
echo Use scripts\stop_local.cmd to stop all three services.
call :maybe_pause
exit /b 0

:failed
echo.
echo ============================================================
echo [FAILED] The complete project was not started.
echo ============================================================
echo Review the messages above and logs in:
echo %RUN_DIR%
echo.
echo Any service that did start can be stopped with scripts\stop_local.cmd.
call :maybe_pause
exit /b 1

:database_ready
netstat.exe -ano -p tcp | findstr /R /C:":3306 .*LISTENING" >nul 2>&1
exit /b %errorlevel%

:backend_ready
curl.exe --silent --fail --max-time 2 -X POST http://127.0.0.1:8000/health >nul 2>&1
exit /b %errorlevel%

:frontend_ready
curl.exe --silent --fail --max-time 2 http://127.0.0.1:5173/ >nul 2>&1
exit /b %errorlevel%

:maybe_pause
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this launcher window...
  pause >nul
)
exit /b 0
