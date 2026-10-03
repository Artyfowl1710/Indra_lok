@echo off
setlocal
set "INDRA_ROOT=%~dp0"
set "HERMES_HOME=%INDRA_ROOT%SIH-26"
set "DOCKER_CONFIG=%INDRA_ROOT%SIH-26\docker-config"
set "HERMES_NODE=%INDRA_ROOT%.indra-runtime\node-v24.11.0-win-x64\node.exe"
set "PATH=%INDRA_ROOT%.indra-runtime\node-v24.11.0-win-x64;%PATH%"

if /I "%~1"=="set-server" (
  shift
  "%INDRA_ROOT%venv\Scripts\python.exe" "%INDRA_ROOT%configure_remote_server.py" %*
  exit /b %errorlevel%
)
if /I "%~1"=="set-context" (
  shift
  "%INDRA_ROOT%venv\Scripts\python.exe" "%INDRA_ROOT%configure_remote_server.py" --set-context %*
  exit /b %errorlevel%
)
if /I "%~1"=="" goto ensure_backend
if /I "%~1"=="chat" goto ensure_backend
if /I "%~1"=="dashboard" if /I not "%~2"=="--status" if /I not "%~2"=="--stop" goto ensure_backend
if /I "%~1"=="--tui" goto ensure_backend
if /I "%~1"=="--cli" goto ensure_backend
if /I "%~1"=="--oneshot" goto ensure_backend
if /I "%~1"=="-z" goto ensure_backend
goto run_cli

:ensure_backend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INDRA_ROOT%ensure-indra-backend.ps1"
if errorlevel 1 (
  echo INDRA backend startup failed. See SIH-26\hermes-agent\backend\data for logs.
  exit /b 1
)

:run_cli
"%INDRA_ROOT%venv\Scripts\indra.exe" %*
endlocal
