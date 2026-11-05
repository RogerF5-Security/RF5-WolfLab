# Panel USB 1.0.3 - repetir presentaciones

- Nuevo boton Preparar otra demo: reinicia las sesiones y el tiempo de campana mediante el comando start ya disponible en firmware 1.0.2.
- Conserva registros, contadores y escenario. El AP se reinicia y desconecta a todos los telefonos durante unos segundos.
- Reconecta el celular y abre http://192.168.4.1/ para ver un formulario nuevo.
- Actualizacion solo del panel. Con firmware 1.0.2 instalado no se necesita compilar ni flashear.
- Cierra la consola anterior, abre ABRIR_PANEL.cmd y recarga con Ctrl+F5.
- Verificado con 19 pruebas automatizadas y navegador en simulacion. Repeticion fisica pendiente de comprobar con el telefono.

# Panel USB 1.0.2

El panel puede comunicarse con firmware 1.0.1 o 1.0.2. Para corregir el fallo de arranque y la ausencia del SSID de 1.0.1, es necesario instalar el firmware 1.0.2 incluido en dist.

- Sincroniza la entrada al abrir el puerto y espera brevemente al endpoint USB.
- Reintenta solamente el saludo HELLO, manteniendo abierto el puerto y el mismo ID.
- Acepta una trama RF5 aunque tenga texto de arranque delante.
- No repite comandos que cambian configuración, activan o borran datos.
- Si no conecta, muestra bytes recibidos, tramas reconocidas e intentos; detecta
  mensajes de modo de descarga sin mostrar contenido de formularios.

Cerrá la consola del panel anterior, abrí `ABRIR_PANEL.cmd --port COM6` y recargá
el navegador. El proceso que ya estaba ejecutándose no carga automáticamente
los cambios del archivo Python. La causa física debe confirmarse si el problema persiste.

## Firmware 1.0.2: correccion de arranque

El firmware 1.0.1 abria el socket HTTP antes de inicializar Wi-Fi/esp_netif. Esto puede abortar el arranque en lwIP antes de publicar el SSID. En 1.0.2, se inicializa Wi-Fi, se configura el AP y solo despues se abren DNS y HTTP. Al pausar se cierra HTTP; al reactivar se vuelve a abrir. Esta correccion requiere instalar los binarios 1.0.2. La prueba fisica de la placa debe completarse despues de instalar.
