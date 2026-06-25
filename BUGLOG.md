# Bug Log — cv-bot

## 2026-06-25

### [MEDIUM] Rate limiter bypaseable detrás de reverse proxy
- **Archivo:** `app.py`
- **Fix:** La IP del cliente ahora se obtiene de `X-Real-IP` o `X-Forwarded-For` antes de caer a `remote_addr`, garantizando que el rate limiter funcione correctamente detrás de Nginx/Gunicorn.

### [LOW] `except Exception` sin logging en `/chat`
- **Archivo:** `app.py`
- **Fix:** Añadido `logging.exception()` antes de devolver el 500, para que los errores de producción queden registrados.

---

## 2026-06-25 — Revisión 3

### [LOW] `/suggest` sin rate limiting
- **Archivo:** `app.py` línea 662
- **Fix:** Reutilizado el rate limiter `_rate_ok()` existente (20 req/min por IP) en el endpoint `/suggest`. IP obtenida de `X-Forwarded-For`, `X-Real-IP` o `remote_addr`.

---

### [CRITICAL — Acción manual requerida] Groq API key en `.env`
- La misma clave está también en `rag-chatbot/.env`.
- **Acción:** Revocar y regenear en console.groq.com. Actualizar ambos proyectos. Añadir `.env` al `.gitignore`.

---

## 2026-06-25 — Revisión 4 (Auditoría profesional completa)

### [HIGH] `session_id` controlado por el cliente sin validación
- **Archivo:** `app.py` línea 615
- **Descripción:** Un atacante podía enviar un `session_id` arbitrario para inyectar o leer el historial de conversación de otro usuario.
- **Fix:** `session_id` debe coincidir con regex `[0-9a-fA-F]{1,48}`. Cualquier valor fuera de ese patrón genera un nuevo ID aleatorio.

### [MEDIUM] Sin cabeceras CSP ni HSTS
- **Archivo:** `app.py` línea 596
- **Descripción:** La aplicación carecía de Content-Security-Policy y Strict-Transport-Security.
- **Fix:** Añadidas `Content-Security-Policy` (con directivas `default-src 'self'`) y `Strict-Transport-Security` (max-age=31536000) al `after_request` handler.

### [MEDIUM] `/suggest` compartía budget de rate limiting con `/chat`
- **Archivo:** `app.py`
- **Descripción:** El endpoint `/suggest` (llamado automáticamente por el frontend) consumía el mismo contador de 20 req/min que `/chat`, bloqueando la conversación principal.
- **Fix:** Añadido `_suggest_rate_log` independiente con límite de 40 req/min. Ambos endpoints usan stores separados.

### [LOW] Sin `.dockerignore`
- **Archivo:** raíz del proyecto
- **Descripción:** La imagen Docker podía incluir `venv/`, `__pycache__/`, `.env` y archivos de log.
- **Fix:** Añadido `.dockerignore` con exclusiones para `.env`, `venv/`, `__pycache__/`, `*.pyc`, `*.db`, `*.log`, `.git`.
