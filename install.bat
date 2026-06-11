@echo off
setlocal
cd /d "%~dp0"

echo.
echo === BOT-CREA-PIC / MoCha Local - installation Windows ===
echo.

set "PY310="
set "INSTALL_EXIT=1"
call :detect_py310

if not defined PY310 (
  echo Python 3.10 n'est pas installe.
  echo Tentative d'installation automatique avec winget...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo winget est introuvable. Installe Python 3.10 puis relance install.bat.
    echo https://www.python.org/downloads/release/python-31011/
    goto :end
  )

  winget install -e --id Python.Python.3.10 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo L'installation Python 3.10 via winget a echoue.
    goto :end
  )

  call :detect_py310
)

if not defined PY310 (
  echo Python 3.10 reste introuvable apres l'installation.
  echo Ferme puis rouvre PowerShell, ou installe Python 3.10 ici:
  echo https://www.python.org/downloads/release/python-31011/
  goto :end
)

echo.
echo Utilisation de %PY310%
%PY310% run.py --setup --download-models --no-launch
set "INSTALL_EXIT=%errorlevel%"
if not "%INSTALL_EXIT%"=="0" (
  echo.
  echo Installation arretee avec le code %INSTALL_EXIT%.
)

:end
pause
exit /b %INSTALL_EXIT%

:detect_py310
set "PY310="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.10 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PY310=py -3.10"
    exit /b 0
  )
)

if exist "%LocalAppData%\Programs\Python\Python310\python.exe" (
  "%LocalAppData%\Programs\Python\Python310\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PY310="%LocalAppData%\Programs\Python\Python310\python.exe""
    exit /b 0
  )
)

if exist "%ProgramFiles%\Python310\python.exe" (
  "%ProgramFiles%\Python310\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PY310="%ProgramFiles%\Python310\python.exe""
    exit /b 0
  )
)

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PY310=python"
    exit /b 0
  )
)

exit /b 0
