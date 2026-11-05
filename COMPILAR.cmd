@echo off
setlocal
set PLATFORMIO_SETTING_ENABLE_TELEMETRY=no
cd /d "%~dp0"
rem Reutiliza las dependencias locales si este proyecto esta en el workspace ESP32.
if exist "..\..\ESP32-Sentinel-Web\.venv\Lib\site-packages\platformio\__init__.py" (
  for %%I in ("..\..\ESP32-Sentinel-Web\.venv\Lib\site-packages") do set "PYTHONPATH=%%~fI"
)
if exist "..\..\.wolflab-build\packages\toolchain-riscv32-esp\package.json" (
  for %%I in ("..\..\.wolflab-build") do set "PLATFORMIO_CORE_DIR=%%~fI"
)
python -m platformio run -j 2
if errorlevel 1 (
  echo Instala PlatformIO Core o revisa los errores anteriores.
  pause
  exit /b 1
)
python tools\package_firmware.py
if errorlevel 1 (
  echo No se pudo preparar dist. No instales el firmware anterior.
  pause
  exit /b 1
)
echo Firmware 1.0.2 generado en dist. Ya puedes usar INSTALAR_FIRMWARE.cmd.
pause
