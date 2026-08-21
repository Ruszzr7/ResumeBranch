@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - MySQL Launcher
cd /d "%~dp0.."

set "PROJECT_ROOT=%CD%"
set "RUN_DIR=%PROJECT_ROOT%\.local-run"
set "SERVICE_FILE=%RUN_DIR%\database.service"
set "DB_PORT=3306"
set "NO_PAUSE=0"
set "ELEVATED=0"
call :parse_args %*
if defined MYSQL_SERVICE_NAME (
  set "DB_SERVICE=%MYSQL_SERVICE_NAME%"
) else (
  set "DB_SERVICE=MySQL84"
)

echo ============================================================
echo Resume Assistant - MySQL Windows Service
echo ============================================================

if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

call :port_ready
if not errorlevel 1 (
  sc.exe query "%DB_SERVICE%" >nul 2>&1
  if not errorlevel 1 >"%SERVICE_FILE%" echo %DB_SERVICE%
  echo [OK] MySQL is already accepting connections.
  goto ready
)

sc.exe query "%DB_SERVICE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] MySQL service "%DB_SERVICE%" was not found.
  echo If it has another name, set MYSQL_SERVICE_NAME before running this script.
  goto failed
)

echo [INFO] Starting Windows service "%DB_SERVICE%"...
net.exe start "%DB_SERVICE%" >nul 2>&1
if errorlevel 1 (
  sc.exe query "%DB_SERVICE%" | findstr /I "RUNNING" >nul 2>&1
  if errorlevel 1 (
    if "%ELEVATED%"=="0" (
      echo [INFO] Administrator approval is required to start MySQL.
      call :run_elevated
      if errorlevel 1 (
        echo [ERROR] Administrator approval was cancelled or MySQL could not start.
        goto failed
      )
      goto wait_database
    ) else (
      echo [ERROR] Windows could not start "%DB_SERVICE%" with administrator rights.
      goto failed
    )
  )
)

set /a WAIT_COUNT=0
:wait_database
call :port_ready
if not errorlevel 1 goto database_started
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ 30 (
  echo [ERROR] MySQL started, but port %DB_PORT% was not ready within 30 seconds.
  goto failed
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_database

:database_started
>"%SERVICE_FILE%" echo %DB_SERVICE%
echo [OK] Database started successfully.

:ready
echo Service: %DB_SERVICE%
echo Address: 127.0.0.1:%DB_PORT%
echo.
call :maybe_pause
exit /b 0

:failed
echo.
echo [FAILED] Database was not started.
call :maybe_pause
exit /b 1

:port_ready
netstat.exe -ano -p tcp | findstr /R /C:":%DB_PORT% .*LISTENING" >nul 2>&1
exit /b %errorlevel%

:maybe_pause
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this launcher window...
  pause >nul
)
exit /b 0

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--elevated" set "ELEVATED=1"
shift
goto parse_args

:run_elevated
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/c','\"%~f0\" --elevated --no-pause' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
exit /b %errorlevel%
