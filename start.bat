@echo off
chcp 65001 >nul
cd /d %~dp0
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if "%PY%"=="" ( python --version >nul 2>nul && set PY=python )
if "%PY%"=="" (
  echo.
  echo Python ist auf diesem PC NICHT installiert ^(nur die Microsoft-Store-Verknuepfung ist da^).
  echo 1. Auf https://www.python.org/downloads/ "Download Python" klicken und installieren.
  echo 2. Im ersten Setup-Fenster UNTEN "Add python.exe to PATH" anhaken, dann "Install Now".
  echo 3. Dieses Fenster schliessen und start.bat erneut doppelklicken.
  pause & exit /b 1
)
if not exist .venv\Scripts\python.exe ( %PY% -m venv .venv )
call .venv\Scripts\activate
echo Installiere Pakete (beim ersten Mal einige Minuten) ...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 ( echo. & echo Paket-Installation fehlgeschlagen - Meldung oben kopieren. & pause & exit /b 1 )
if not exist .env copy .env.example .env >nul
echo Starte Programm ...
python app.py
echo.
echo Programm beendet. Falls ein Fehler auftrat, steht er in log.txt
pause
