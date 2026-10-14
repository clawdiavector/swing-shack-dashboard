@echo off
rem Windows twin of the "campaign-os" launch config, which needs bash.
cd /d "%~dp0..\campaign-os"
set "DATA_DIR=%CD%\data"
rem The app may assign a free port through PORT; 8010 is only the fallback.
if not defined PORT set "PORT=8010"
set "PYTHONUTF8=1"
python app.py
