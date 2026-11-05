@echo off
setlocal
cd /d "%~dp0"
python -c "import serial" >nul 2>&1
if errorlevel 1 (
  python -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
python host\wolflab.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo No se pudo abrir el panel. Comprueba Python y el mensaje anterior.
pause
exit /b 1
