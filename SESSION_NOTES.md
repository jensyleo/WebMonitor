### Sesión WebMonitor - Notas rápidas (v1.0.0)

- Proyecto: EH/WebMonitor/WebMonitor.py

#### Cambios clave implementados
- Mensajería centralizada en `MESSAGES` y textos unificados (OK, 1xx, 3xx, 4xx, 5xx, DNS, SSL, Timeout, Servicio no disponible).
- Colores: "Servicio web no disponible" ahora usa `RGB_BLUE` (0,183,211).
- Lógica HTTP:
  - 2xx: OK (retorna True)
  - 1xx: “Sitio arriba con respuesta informacional”
  - 3xx: “Sitio arriba con redirección”
  - 4xx: “Sitio arriba con respuesta del cliente”
  - 5xx: “Sitio arriba con error del servidor”
  - Fuera 100–599: status no estándar
- normalizar_url:
  - Ahora resuelve DNS previamente (`socket.gethostbyname`); si no resuelve → None (clasifica como DNS en el flujo principal).
  - Usa HEAD (1.5s) para probes rápidas de esquema: primero HTTPS, si falla HTTP.
- Chequeo principal: GET con timeout 2.0s.
- Reintentos: se aplican para Timeout, errores de conexión y también cuando no se detecta servicio web; mensajes de reintento coherentes.
- Filtrado de `urls.txt`: ignora líneas vacías/espacios y comentarios (`#`).
- Import flexible eliminado (ya no hay archivo extra de mensajes; todo en un solo script).

#### Decisiones revertidas (para recordar)
- Se descartó el backoff de 0.3s entre reintentos.
- Se revirtió la versión que normalizaba sin requests y que alternaba esquema por intento.

#### Cómo ejecutar
- Dependencias: `pip install requests colorama`
- Ejecutar: `python3 WebMonitor.py`
- `urls.txt` debe estar en el mismo directorio que `WebMonitor.py`.

#### Pendientes opcionales (para futuras iteraciones)
- Considerar 1xx/3xx como éxito (True) si así se desea.
- Parametrizar timeouts/reintentos vía archivo/env.
- Logging a archivo/JSON y rotación.
- Concurrencia para listas grandes de URLs.

