@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Resume Assistant - Stop MySQL
cd /d "%~dp0.."

set "NO_PAUSE=0"
set "ELEVATED=0"
call :parse_args %*
if defined MYSQL_SERVICE_NAME (
  set "DB_SERVICE=%MYSQL_SERVICE_NAME%"
) else (
  set "DB_SERVICE=MySQL84"
)

echo ============================================================
echo Resume Assistant - Stop MySQL Windows Service
echo ============================================================
echo.
echo [INFO] Service: %DB_SERVICE%
echo [INFO] Stopping this service may affect other applications that use it.

sc.exe query "%DB_SERVICE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] MySQL service "%DB_SERVICE%" was not found.
  echo If it has another name, set MYSQL_SERVICE_NAME before running this script.
  goto failed
)

call :service_stopped
if not errorlevel 1 (
  echo [OK] MySQL service is already stopped.
  goto ready
)

echo [INFO] Stopping Windows service "%DB_SERVICE%"...
net.exe stop "%DB_SERVICE%" >nul 2>&1
if errorlevel 1 (
  call :service_stopped
  if errorlevel 1 (
    if "%ELEVATED%"=="0" (
      echo [INFO] Administrator approval is required to stop MySQL.
      call :run_elevated
      if errorlevel 1 (
        echo [ERROR] Administrator approval was cancelled or MySQL could not stop.
        goto failed
      )
      goto ready
    ) else (
      echo [ERROR] Windows could not stop "%DB_SERVICE%" with administrator rights.
      goto failed
    )
  )
)

set /a WAIT_COUNT=0
:wait_service
call :service_stopped
if not errorlevel 1 goto service_stopped_ok
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ 30 (
  echo [ERROR] MySQL did not stop within 30 seconds.
  goto failed
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_service

:service_stopped_ok
echo [OK] MySQL stopped successfully.

:ready
echo [OK] No database files or application data were deleted.
if "%NO_PAUSE%"=="0" pause
exit /b 0

:failed
echo.
echo [FAILED] MySQL was not stopped.
if "%NO_PAUSE%"=="0" pause
exit /b 1

:service_stopped
sc.exe query "%DB_SERVICE%" | findstr /I "STOPPED" >nul 2>&1
exit /b %errorlevel%

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--elevated" set "ELEVATED=1"
shift
goto parse_args

:run_elevated
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/c','\"%~f0\" --elevated --no-pause' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
exit /b %errorlevel%
