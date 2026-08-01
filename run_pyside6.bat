@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 pause & exit /b 1
python main.py
if errorlevel 1 pause
