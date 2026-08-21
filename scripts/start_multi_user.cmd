@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Start Multi-user Profile
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "NO_PAUSE=1"
call :parse_args %*

echo ============================================================
echo Resume Assistant - Start Multi-user MySQL Profile
echo ============================================================
echo.

call "%~dp0start_mysql.cmd" --no-pause
if errorlevel 1 goto failed
echo.
rem Always restart the backend so Python code changes are loaded. The shared
rem Vite frontend is reused when it is already running and continues hot reload.
call "%~dp0start_backend_multi_user.cmd" --restart --no-pause
if errorlevel 1 goto failed
echo.
call "%~dp0start_frontend.cmd" --no-pause
if errorlevel 1 goto failed

call :profile_ready
if errorlevel 1 goto failed
call :frontend_ready
if errorlevel 1 goto failed

echo.
echo ============================================================
echo [OK] The multi-user project is running.
echo ============================================================
echo Database: MySQL on 127.0.0.1:3306
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Logs:     %RUN_DIR%
echo.
echo The shared frontend remains running for Vite hot updates.
echo Backend code changes require running this script again.
echo Use scripts\stop_app.cmd to stop frontend and backend.
if "%NO_PAUSE%"=="0" pause
exit /b 0

:failed
echo.
echo ============================================================
echo [FAILED] The multi-user project was not started.
echo ============================================================
echo Review the messages above and logs in:
echo %RUN_DIR%
echo.
echo MySQL is not stopped automatically because other applications may use it.
if "%NO_PAUSE%"=="0" pause
exit /b 1

:profile_ready
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $c = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/app/config' -TimeoutSec 3; if ($c.app_mode -eq 'multi_user' -and $c.database_backend -eq 'mysql' -and $c.authentication_required -eq $true) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:frontend_ready
curl.exe --silent --fail --max-time 2 http://127.0.0.1:5173/ >nul 2>&1
exit /b %errorlevel%

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--pause" set "NO_PAUSE=0"
shift
goto parse_args
