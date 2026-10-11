@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" helper\check.py
pause
exit /b
:missing
echo Run Install.cmd first.
pause
exit /b 1
