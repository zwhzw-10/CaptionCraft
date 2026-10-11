@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
if errorlevel 1 goto failed
echo Installation complete. Follow README.md to load the extension.
pause
exit /b 0
:failed
echo Installation failed. See the error above and README.md.
pause
exit /b 1
