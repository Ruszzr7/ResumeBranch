@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Stop All
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "SERVICE_FILE=%RUN_DIR%\database.service"
set "NO_PAUSE=0"
set "STOP_FAILED=0"
set "ELEVATED=0"
set "KEEP_DB=0"
call :parse_args %*
if defined MYSQL_SERVICE_NAME (
  set "DB_SERVICE=%MYSQL_SERVICE_NAME%"
) else (
  set "DB_SERVICE=MySQL84"
)
if exist "%SERVICE_FILE%" set /p DB_SERVICE=<"%SERVICE_FILE%"

echo ============================================================
echo Resume Assistant - Stop Frontend, Backend and Database
echo ============================================================
echo.

call :stop_port 5173 frontend
call :stop_port 8000 backend
if "%KEEP_DB%"=="0" (
  call :stop_database
) else (
  echo [INFO] Database was left running because --keep-db was specified.
)

del /q "%RUN_DIR%\frontend.pid" "%RUN_DIR%\backend.pid" >nul 2>&1
if "%STOP_FAILED%"=="0" if "%KEEP_DB%"=="0" del /q "%SERVICE_FILE%" >nul 2>&1

echo.
if "%STOP_FAILED%"=="0" (
  echo ============================================================
  if "%KEEP_DB%"=="0" (
    echo [OK] Frontend, backend and database are stopped.
  ) else (
    echo [OK] Frontend and backend are stopped. Database is still running.
  )
  echo ============================================================
) else (
  echo ============================================================
  echo [FAILED] One or more services could not be stopped.
  echo ============================================================
  echo Read the error above for details.
)
call :maybe_pause
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

:stop_database
sc.exe query "%DB_SERVICE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Database service "%DB_SERVICE%" was not found.
  set "STOP_FAILED=1"
  exit /b 1
)
sc.exe query "%DB_SERVICE%" | findstr /I "RUNNING" >nul 2>&1
if errorlevel 1 (
  echo [OK] Database service "%DB_SERVICE%" is already stopped.
  exit /b 0
)
echo [INFO] Stopping database service "%DB_SERVICE%"...
net.exe stop "%DB_SERVICE%" >nul 2>&1
if errorlevel 1 (
  if "%ELEVATED%"=="0" (
    echo [INFO] Administrator approval is required to stop MySQL.
    call :run_elevated
    if errorlevel 1 (
      echo [ERROR] Administrator approval was cancelled or MySQL could not stop.
      set "STOP_FAILED=1"
      exit /b 1
    )
    echo [OK] Database service "%DB_SERVICE%" stopped.
    exit /b 0
  ) else (
    echo [ERROR] Windows could not stop "%DB_SERVICE%" with administrator rights.
    set "STOP_FAILED=1"
    exit /b 1
  )
)
set /a DB_WAIT=0
:wait_database_stop
sc.exe query "%DB_SERVICE%" | findstr /I "STOPPED" >nul 2>&1
if not errorlevel 1 (
  echo [OK] Database service "%DB_SERVICE%" stopped.
  exit /b 0
)
set /a DB_WAIT+=1
if !DB_WAIT! GEQ 30 (
  echo [ERROR] Database did not stop within 30 seconds.
  set "STOP_FAILED=1"
  exit /b 1
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_database_stop

:maybe_pause
if "%NO_PAUSE%"=="0" (
  echo.
  echo Press any key to close this window...
  pause >nul
)
exit /b 0

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--elevated" set "ELEVATED=1"
if /I "%~1"=="--keep-db" set "KEEP_DB=1"
shift
goto parse_args

:run_elevated
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/c','\"%~f0\" --elevated --no-pause' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
exit /b %errorlevel%
