# CV Bot

Asistente web conversacional que responde preguntas sobre el perfil profesional de Eric C. — habilidades, proyectos y experiencia. Impulsado por Groq LLM con el perfil completo como contexto.

Live: [cv-bot-hxku.onrender.com](https://cv-bot-hxku.onrender.com)

## Stack
Python · Flask · Groq API — `openai/gpt-oss-120b` (chat) · `openai/gpt-oss-20b` (sugerencias)

## Cómo funciona
1. Carga `docs/perfil.txt` al arrancar (~15KB de perfil, compactado al cargar)
2. En cada pregunta: envía el perfil completo + historial de conversación al LLM
3. Basa las respuestas en el perfil, identifica las inferencias y evita inventar experiencia
4. Detecta el idioma de forma coherente para respuestas y sugerencias en español o inglés
5. Si Groq devuelve 429 (límite de uso): muestra respuestas estáticas del perfil con el tiempo de reset exacto

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
**v0.6.0** — 2026-10-01
- Perfil: sincronizado con el CV actual — más de 2 años de experiencia (antes decía 3 por error), prácticas FCT separadas de los empleos, funciones de cada puesto, Active Directory/DNS/DHCP/ServiceNow, credencial Cisco *Introduction to Cybersecurity*
- IA: prompt de sistema reescrito — respuestas basadas en evidencia, análisis de encaje con ofertas requisito a requisito, resolución de preguntas de seguimiento y separación clara entre empleos, prácticas y proyectos
- IA: razonamiento adaptativo — `reasoning_effort` bajo por defecto, medio para preguntas de encaje u ofertas de empleo
- Tokens: prefijo del prompt estable (el perfil antes del idioma de cada turno) para aprovechar el prompt caching de Groq; perfil compactado al cargar; solo se reenvían los últimos 4 intercambios y los antiguos se recortan; límite `max_completion_tokens`
- Tokens: las sugerencias de seguimiento pasan a `openai/gpt-oss-20b` (cupo de rate limit propio); caché en memoria para respuestas del primer turno y sugerencias
- Web: versión de la app y modelo de IA visibles en la página; `/health` devuelve versión y modelo
- Longitud máxima de pregunta ampliada a 1 500 caracteres para poder pegar una oferta de empleo

**v0.5.0** — 2026-09-28
- Modelo: documentación actualizada a `openai/gpt-oss-120b` en Groq
- IA: prompts basados en evidencia del perfil; evita inventar datos, repetir sugerencias o responder sobre logística no confirmada
- Fix: idioma de sugerencias coherente con el chat; preguntas iniciales bilingües, concretas y orientadas a selección
- Fix: JSON mal formado devuelve 400; corregida la evicción de IPs y sesiones
- Tests: cobertura de rate limiting, sesiones, validación JSON e idioma de sugerencias

**v0.4.0** — 2026-06-28
- Seguridad: CSP con nonce por petición, cabeceras HTTP y salida Markdown sanitizada
- Seguridad: teléfono eliminado del contexto del LLM y prompt protegido frente a instrucciones de override
- Fix: rate limits con almacenes separados y límite de memoria para IPs


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

## Seguridad

El rate limit por IP depende de que el proxy inverso elimine y sobrescriba `X-Real-IP` y `X-Forwarded-For`. Configura esa confianza en el proxy de producción; el detalle está en [`BUGLOG.md`](BUGLOG.md).
