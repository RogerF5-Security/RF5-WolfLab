@echo off
setlocal
cd /d "%~dp0"
python host\wolflab.py --demo %*
if errorlevel 1 pause
