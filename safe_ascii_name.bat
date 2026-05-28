@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python -m pip install -r requirements.txt -q 2>nul
echo [YafuokuShipping] %cd%
python app.py
if errorlevel 1 pause
