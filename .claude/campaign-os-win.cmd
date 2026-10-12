@echo off
rem Windows twin of the "campaign-os" launch config, which needs bash.
cd /d "%~dp0..\campaign-os"
set "DATA_DIR=%CD%\data"
set "PORT=8010"
set "PYTHONUTF8=1"
python app.py
