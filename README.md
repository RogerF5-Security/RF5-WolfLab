# RF5 WolfLab

Portal de concientización Wi-Fi para **ESP32-C3 SuperMini**, con panel USB y mural de ovejas. Autor: Roger F5.

## Empezar en casa

Requiere Python 3.10 o posterior disponible como `python`.

```powershell
git clone https://github.com/RogerF5-Security/RF5-WolfLab.git
cd RF5-WolfLab
.\DEMO.cmd
```

Para la placa real: cierra la demo, conecta el ESP32-C3 y ejecuta **ABRIR_PANEL.cmd**. Si hay varias placas, usa `ABRIR_PANEL.cmd --port COM6` con el puerto correspondiente. Los lanzadores instalan las dependencias Python si faltan.

Panel: http://127.0.0.1:8765/ · Portal del teléfono: http://192.168.4.1/.

- Cambia SSID, campaña y ubicación desde el panel; se guardan en la placa.
- **Preparar otra demo** reinicia el AP y las sesiones para repetir desde el mismo teléfono. Conserva registros y escenario; desconecta momentáneamente las estaciones.
- **Abrir mural** muestra los alias; F11 permite presentarlo en pantalla completa.
- `DEMO.cmd` utiliza datos ficticios y no transmite Wi-Fi.

## Firmware

Se incluye el firmware **1.0.2 compilado y verificado** en `dist/`. No hace falta PlatformIO para instalarlo.

Para una placa nueva ejecuta `INSTALAR_FIRMWARE.cmd`: verifica ESP32-C3 y 4 MB, exige un respaldo completo con SHA-256 antes de escribir y comprueba los segmentos. Si ya tienes WolfLab 1.0.2, los cambios del panel no requieren reflashear.

## Estado de esta sincronización

Este repositorio recupera el **panel 1.0.3 y firmware 1.0.2** del paquete guardado y permite continuar el desarrollo. La integración más reciente del fondo del lobo y los STL generados en la PC todavía no se han sincronizado: la conexión con esa PC se interrumpió durante la publicación. No se presentan aquí como archivos ya subidos.

Se incluye la fuente paramétrica actualizada `case/wolf_case.scad` del diseño Wolf Vent. En OpenSCAD selecciona `part="print"`, renderiza y exporta a STL. El ajuste físico sigue pendiente; consulta `case/README.md`.

## Datos y límites

Se cuentan asociaciones (incluidas reconexiones), sesiones y formularios. Nombre e identificador son declarados, no verificados. El mural muestra alias. El firmware 1.0.2 no registra navegación externa, User-Agent, modelo exacto ni pantalla del teléfono.

El portal usa HTTP en una red abierta. No pide contraseñas ni MFA. Para presentaciones usa códigos ficticios o de campaña. Los registros privados se guardan en `private/` y los respaldos de flash en `backups/`; ambos quedan excluidos de Git.

## Desarrollo

```powershell
python -m unittest discover -s tests -v
```

Para compilar se requiere PlatformIO Core: `COMPILAR.cmd`. Para continuar después de la limpieza del historial, usa un clon nuevo y evita mezclar el historial antiguo.
