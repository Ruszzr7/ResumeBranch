@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Start All
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
rem The all-in-one launcher is an orchestrator, not an interactive service shell.
rem It must run backend -> frontend -> health checks without waiting
rem for keyboard input. Use --pause only when the final summary should stay open.
set "NO_PAUSE=1"
set "RESTART=0"
call :parse_args %*

echo ============================================================
echo Resume Assistant - Start Local SQLite Profile
echo ============================================================
echo.

if "%RESTART%"=="1" (
  call "%~dp0start_backend_local.cmd" --restart --no-pause
) else (
  call "%~dp0start_backend_local.cmd" --no-pause
)
if errorlevel 1 goto failed
echo.
call "%~dp0start_frontend.cmd" --no-pause
if errorlevel 1 goto failed

call :backend_ready
if errorlevel 1 goto failed
call :frontend_ready
if errorlevel 1 goto failed

echo.
echo ============================================================
echo [OK] The complete project is running.
echo ============================================================
echo Database: %PROJECT_ROOT%\data\resumebranch.db
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Logs:     %RUN_DIR%
echo.
echo Exports:  %PROJECT_ROOT%\output\resumes
echo The shared frontend remains running for Vite hot updates.
echo Backend code changes require running this script again.
echo Use scripts\stop_app.cmd to stop both services.
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
echo Any service that did start can be stopped with scripts\stop_app.cmd.
call :maybe_pause
exit /b 1

:backend_ready
curl.exe --silent --fail --max-time 2 -X POST http://127.0.0.1:8000/health >nul 2>&1
exit /b %errorlevel%

:frontend_ready
curl.exe --silent --fail --max-time 2 http://127.0.0.1:5173/ >nul 2>&1
exit /b %errorlevel%

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--pause" set "NO_PAUSE=0"
if /I "%~1"=="--restart" set "RESTART=1"
shift
goto parse_args

:maybe_pause
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this launcher window...
  pause >nul
)
exit /b 0
