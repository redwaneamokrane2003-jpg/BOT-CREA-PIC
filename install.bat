@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3.10 run.py --setup --download-models
  goto :end
)

python run.py --setup --download-models

:end
pause

