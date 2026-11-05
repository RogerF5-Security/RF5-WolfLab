# Aceptación física pendiente

Usar únicamente datos ficticios. Registrar modelo/flash reales, fecha y resultado;
no marcar aprobado sin ejecutar. Ver el estado exacto en `VALIDACION.json`.

1. Identificar chip y flash; instalar con respaldo completo y SHA-256.
2. Abrir el panel y comprobar firmware `RF5-WolfLab-C3` y versión 1.0.1.
3. Conectar Android/iOS/Windows disponibles; comprobar portal automático o manual.
4. Enviar `Demo` / `TEST-001`; ver explicación. Recargar la misma sesión no debe duplicar el envío.
5. Abrir mural: mostrar alias sin nombre ni `TEST-001`; comprobar CSV/JSON privados.
6. Cambiar SSID y ubicación; comprobar AP anterior desconectado y nuevo SSID visible.
7. Reiniciar: configuración persistente y formularios RAM vacíos. Archivo de PC conservado.
8. Alimentar solo con cargador/power bank; enviar datos ficticios y recuperar por
   USB sin cortar energía. Comprobar si el host/placa se reinician al reconectar.
9. Probar duración de 1 minuto, pausa/activación y BOOT durante 3 segundos.
10. Probar cuatro estaciones simultáneas y el límite de 128 registros, con datos
    sintéticos. Comprobar reemplazos, memoria y estabilidad bajo la carga prevista.
11. Probar SSID con acentos, formulario inválido y sesión vencida.
12. Desde otra PC, mural con clave válida y rechazo de configuración/exportaciones.
13. Borrar con `BORRAR` y comprobar archivo lógico y RAM vacíos.

La hora de PC es primera lectura, no hora exacta de envío. Las identidades son
declaradas y las asociaciones Wi-Fi pueden ser automáticas o reconexiones.
