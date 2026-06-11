@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
  goto :end
)

echo Environnement .venv absent.
echo Lancement de l'installation initiale...
set "BOTCREAPIC_FROM_RUN=1"
call install.bat
set "BOTCREAPIC_FROM_RUN="
if errorlevel 1 goto :install_failed

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
  goto :end
)

:install_failed
echo Installation incomplete. Corrige l'erreur affichee puis relance run.bat.
goto :end

:end
pause
