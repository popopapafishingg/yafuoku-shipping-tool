@echo off
cd /d "%~dp0"
python tools\verify_sagawa_alignment.py --fix --preview-png --check-preview-pdf
if errorlevel 1 (
  echo.
  echo [NG] ずれあり。output\alignment_debug.png を確認してください。
  pause
  exit /b 1
)
echo.
echo [OK] レイアウトはスキャン検出と一致しています。
pause
