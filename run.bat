@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
  goto :end
)

where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3.10 run.py
  goto :end
)

python run.py

:end
pause

