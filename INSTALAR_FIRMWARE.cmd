@echo off
setlocal
cd /d "%~dp0"
echo RF5 WolfLab - ESP32-C3 - respaldo previo obligatorio
echo Cierra el panel y cualquier monitor serie antes de instalar.
python -c "import serial,esptool; assert tuple(map(int,esptool.__version__.split('.')[:2])) >= (5,3)" >nul 2>&1
if errorlevel 1 (
  python -m pip install -r requirements-device.txt
  if errorlevel 1 goto failed
)
python tools\device.py install %*
if errorlevel 1 goto failed
echo Escritura terminada. Abre ABRIR_PANEL.cmd para verificar el arranque.
pause
exit /b 0
:failed
echo Instalacion detenida. Revisa el mensaje anterior.
pause
exit /b 1
