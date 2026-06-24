# CV Bot

Asistente web conversacional que responde preguntas sobre el perfil profesional de Eric C. — habilidades, proyectos y experiencia. Impulsado por Groq LLM con el perfil completo como contexto.

Live: [cv-bot-hxku.onrender.com](https://cv-bot-hxku.onrender.com)

## Stack
Python · Flask · LangChain · Groq API (llama-3.3-70b, gratuito)

## Cómo funciona
1. Carga `docs/perfil.txt` al arrancar (~6KB de perfil profesional)
2. En cada pregunta: envía el perfil completo + historial de conversación al LLM
3. Detecta el idioma de cada mensaje — responde en español o inglés automáticamente
4. Si Groq devuelve 429 (límite de uso): muestra respuestas estáticas del perfil con el tiempo de reset exacto

Sin embeddings, sin base de datos vectorial, sin GPU. El perfil cabe en la ventana de contexto de 128K tokens.

## Instalación
```bash
pip install -r requirements.txt
cp .env.example .env
# Añade tu key de Groq gratuita: https://console.groq.com
python app.py
# Abre http://localhost:5001
```

## Docker
```bash
docker build -t cv-bot .
docker run -p 5001:5001 -e GROQ_API_KEY=gsk_... cv-bot
```

## Personalización
Edita `docs/perfil.txt` con tu propio perfil y reinicia. El LLM recibe el documento completo en cada petición.

## Historial de versiones

**v0.3.0** — 2026-06-24
- Seguridad: rate limiting propio en el servidor — 20 peticiones/min por IP (ventana deslizante), devuelve 429 antes de llegar al LLM
- Seguridad: longitud de pregunta limitada a 500 caracteres; respuesta en `/suggest` limitada a 1 000 caracteres
- Seguridad: el parámetro `lang` en `/suggest` se valida contra una lista blanca (`Spanish` / `English`)
- Seguridad: SYSTEM_PROMPT y SUGGEST_PROMPT construidos con `.replace()` en vez de `.format()` — evita KeyError cuando el input contiene `{}`
- Seguridad: cabeceras HTTP de seguridad añadidas (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
- Seguridad: banner XSS-safe — reemplazado `innerHTML` por DOM API (`textContent` + `createElement`)
- Seguridad: toda salida de `marked.parse()` envuelta con DOMPurify antes de renderizar
- Seguridad: los detalles de excepción internos ya no se filtran al cliente (mensaje genérico 500)
- Seguridad: diccionario de sesiones en memoria limitado a 500 entradas con desalojo LRU

**v0.2.0** — 2026-06-24
- Fix: variable no utilizada eliminada del manejador de sugerencias en frontend
- Novedades: fallback al límite de uso de Groq con respuestas estáticas y banner con tiempo de reset exacto
- Novedades: banner de versión alfa

**v0.1.0** — 2026-06-01
- Publicación inicial: Flask + Groq LLM, historial de conversación, detección automática de idioma, preguntas de seguimiento sugeridas
