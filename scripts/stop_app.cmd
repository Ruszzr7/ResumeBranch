@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Stop Application
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "NO_PAUSE=0"
set "STOP_FAILED=0"
call :parse_args %*

echo ============================================================
echo Resume Assistant - Stop Frontend and Backend
echo ============================================================
echo.

call :stop_port 5173 frontend
call :stop_port 8000 backend

del /q "%RUN_DIR%\frontend.pid" "%RUN_DIR%\backend.pid" >nul 2>&1

echo.
if "%STOP_FAILED%"=="0" (
  echo ============================================================
  echo [OK] Frontend and backend are stopped.
  echo [OK] Application services are stopped; database data was not removed.
  echo ============================================================
) else (
  echo ============================================================
  echo [FAILED] One or more services could not be stopped.
  echo ============================================================
  echo Read the error above for details.
)
if "%NO_PAUSE%"=="0" pause
if "%STOP_FAILED%"=="0" exit /b 0
exit /b 1

:stop_port
set "TARGET_PORT=%~1"
set "SERVICE_LABEL=%~2"
set "FOUND_PROCESS=0"
for /f "tokens=5" %%P in ('netstat.exe -ano -p tcp ^| findstr /R /C:":!TARGET_PORT! .*LISTENING"') do (
  set "FOUND_PROCESS=1"
  echo [INFO] Stopping !SERVICE_LABEL! process %%P...
  taskkill.exe /PID %%P /T /F >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Unable to stop !SERVICE_LABEL! process %%P.
    set "STOP_FAILED=1"
  ) else (
    echo [OK] Stopped !SERVICE_LABEL! process tree %%P.
  )
)
if "!FOUND_PROCESS!"=="0" echo [OK] !SERVICE_LABEL! is already stopped.
call :wait_for_port !TARGET_PORT!
exit /b 0

:wait_for_port
set "WAIT_PORT=%~1"
set /a WAIT_COUNT=0
:wait_port_loop
netstat.exe -ano -p tcp | findstr /R /C:":!WAIT_PORT! .*LISTENING" >nul 2>&1
if errorlevel 1 exit /b 0
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ 10 (
  echo [ERROR] Port !WAIT_PORT! is still listening after 10 seconds.
  set "STOP_FAILED=1"
  exit /b 1
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_port_loop

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
shift
goto parse_args
