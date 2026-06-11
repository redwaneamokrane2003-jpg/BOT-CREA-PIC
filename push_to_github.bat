@echo off
setlocal
cd /d "%~dp0"

echo.
echo Connexion GitHub si necessaire...
"C:\Users\redwa\Documents\New\cmd\git.exe" credential-manager github login

echo.
echo Push vers https://github.com/redwaneamokrane2003-jpg/BOT-CREA-PIC
"C:\Users\redwa\Documents\New\cmd\git.exe" push -u origin main

echo.
echo Si le push est termine sans erreur, le repo GitHub est pret.
pause

