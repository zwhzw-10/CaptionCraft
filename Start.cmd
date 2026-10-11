@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
set HF_HUB_OFFLINE=1
set HF_HUB_DISABLE_TELEMETRY=1
".venv\Scripts\python.exe" helper\server.py %*
if errorlevel 1 echo Failed. Check README.md: model download, VC++ runtime, or port in use.
pause
exit /b
:missing
echo Run Install.cmd first.
pause
exit /b 1
