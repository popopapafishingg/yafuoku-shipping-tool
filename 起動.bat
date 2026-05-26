@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt -q 2>nul
echo [YafuokuShipping] %cd%
python app.py
if errorlevel 1 pause
