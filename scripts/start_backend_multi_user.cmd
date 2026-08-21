@echo off
setlocal EnableExtensions
set "BACKEND_PROFILE=multi_user"
call "%~dp0start_backend_local.cmd" %*
exit /b %errorlevel%
