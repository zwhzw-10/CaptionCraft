@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Enable-Preload.ps1"
if errorlevel 1 goto failed
echo Preload enabled. Restart Start.cmd, reload extension, refresh YouTube.
pause
exit /b 0
:failed
echo Setup failed. Check error above; local audio import remains available.
pause
exit /b 1
