@echo off
setlocal
cd /d "%~dp0"

echo Repo: https://github.com/redwaneamokrane2003-jpg/BOT-CREA-PIC
echo.
echo Si GitHub demande une connexion, suis les instructions affichees.
echo.

"C:\Users\redwa\Documents\New\cmd\git.exe" remote set-url origin https://github.com/redwaneamokrane2003-jpg/BOT-CREA-PIC.git
"C:\Users\redwa\Documents\New\cmd\git.exe" push -u origin main

echo.
pause

