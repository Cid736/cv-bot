# Bug Log — cv-bot

## 2026-06-25

### [MEDIUM] Rate limiter bypaseable detrás de reverse proxy
- **Archivo:** `app.py`
- **Fix:** La IP del cliente ahora se obtiene de `X-Real-IP` o `X-Forwarded-For` antes de caer a `remote_addr`, garantizando que el rate limiter funcione correctamente detrás de Nginx/Gunicorn.

### [LOW] `except Exception` sin logging en `/chat`
- **Archivo:** `app.py`
- **Fix:** Añadido `logging.exception()` antes de devolver el 500, para que los errores de producción queden registrados.

### [CRITICAL — Acción manual requerida] Groq API key en `.env`
- La misma clave está también en `rag-chatbot/.env`.
- **Acción:** Revocar y regenear en console.groq.com. Actualizar ambos proyectos. Añadir `.env` al `.gitignore`.
