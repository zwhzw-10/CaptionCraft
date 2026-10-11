@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" helper\server.py --model tiny --download
pause
