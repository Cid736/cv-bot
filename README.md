<p align="center">
  <a href="#english">🇬🇧 English</a> &nbsp;·&nbsp; <a href="#español">🇪🇸 Español</a>
</p>

---

<a name="english"></a>

# CV Bot

Conversational web assistant that answers questions about Eric C.'s professional profile — skills, projects, and experience. Powered by Groq LLM with the full profile passed as context.

Live: [cv-bot-hxku.onrender.com](https://cv-bot-hxku.onrender.com)

## Stack
Python · Flask · LangChain · Groq API (llama-3.3-70b, free)

## How it works
1. Loads `docs/perfil.txt` at startup (~6KB profile document)
2. On each question: sends the full profile + conversation history to the LLM
3. Language auto-detected per message — responds in Spanish or English
4. When Groq rate limit is hit (429): falls back to static answers from the profile, shows reset time

No embeddings, no vector database, no GPU needed. The full profile fits comfortably in the 128K context window.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Add your free Groq key: https://console.groq.com
python app.py
# Open http://localhost:5001
```

## Docker
```bash
docker build -t cv-bot .
docker run -p 5001:5001 -e GROQ_API_KEY=gsk_... cv-bot
```

## Customization
Edit `docs/perfil.txt` with your own profile and restart. The LLM sees the full document on every request.

## Changelog

**v0.4.0** — 2026-06-28
- Security: CSP nonces per-request — replaced `unsafe-inline` with `nonce-{token}` in `script-src` and `style-src`
- Security: phone number removed from `docs/perfil.txt` — was accessible to any visitor via LLM
- Security: system prompt hardened against prompt injection — explicit rule to ignore override attempts
- Security: rate-limit IP stores capped at 10 000 entries — prevents unbounded memory growth under IP-rotation flood
- Fix: `detect_lang` false positives with English — removed ambiguous words ("has", "que", "como") from Spanish regex
- Fix: `groq` package now declared explicitly in `requirements.txt`; all deps have upper-bound version pins

**v0.3.0** — 2026-06-24
- Security: server-side rate limiting — 20 requests/min per IP (sliding window), returns 429 before reaching the LLM
- Security: question length capped at 500 chars; `/suggest` answer capped at 1 000 chars
- Security: `lang` parameter in `/suggest` validated against whitelist (`Spanish` / `English`)
- Security: SYSTEM_PROMPT and SUGGEST_PROMPT built with `.replace()` instead of `.format()` — prevents KeyError crash when user input contains `{}`
- Security: HTTP security headers added (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
- Security: XSS-safe banner — replaced `innerHTML` assignment with DOM API (`textContent` + `createElement`)
- Security: all `marked.parse()` output wrapped with DOMPurify before rendering
- Security: internal exception details no longer leak to the client (generic 500 message)
- Security: in-memory session dict capped at 500 entries with LRU eviction

**v0.2.0** — 2026-06-24
- Fix: remove unused variable in frontend suggest handler
- Feat: Groq rate-limit fallback with static answers and dynamic reset time banner
- Feat: alpha version banner

**v0.1.0** — 2026-06-01
- Initial release: Flask + Groq LLM, conversation history, language auto-detection, suggested follow-up questions

## Security

Automated security reviews are powered by [Claude](https://claude.ai) (Anthropic AI) and run on every significant change to detect vulnerabilities, insecure patterns and dependency risks. Findings are tracked in [`BUGLOG.md`](BUGLOG.md).

**Last review:** 2026-06-28 (rev 5) — 5 new issues found and patched (2 high, 2 medium, 1 low). See [`BUGLOG.md`](BUGLOG.md) for full history.

**Security controls in place:**
- Server-side rate limiting per IP — 20 req/min on `/chat`, 40 req/min on `/suggest` (independent sliding-window stores, capped at 10 000 IP entries to prevent memory exhaustion)
- Question length capped at 500 chars; `/suggest` answer input capped at 1 000 chars
- `session_id` validated against `[0-9a-fA-F]{1,48}` — arbitrary values replaced with a server-generated token
- CSP with per-request cryptographic nonces — no `unsafe-inline` anywhere
- `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `HSTS`
- All Markdown output sanitized with DOMPurify before DOM insertion
- Rate-limit banner built with DOM API — no `innerHTML` assignment
- Internal error details never sent to client (generic 500 message + server-side `logging.exception`)
- In-memory session store capped at 500 entries (LRU eviction)
- Phone number removed from LLM context; system prompt explicitly forbids revealing private contact details
- System prompt instructs the LLM to ignore prompt-injection attempts

Found a vulnerability? Open an issue or contact directly.

---

<a name="español"></a>

# CV Bot

Asistente conversacional web que responde preguntas sobre el perfil profesional de Eric C. — habilidades, proyectos y experiencia. Impulsado por Groq LLM con el perfil completo como contexto.

En producción: [cv-bot-hxku.onrender.com](https://cv-bot-hxku.onrender.com)

## Stack
Python · Flask · LangChain · Groq API (llama-3.3-70b, gratuito)

## Cómo funciona
1. Carga `docs/perfil.txt` al arrancar (~6KB de documento de perfil)
2. En cada pregunta: envía el perfil completo + historial de conversación al LLM
3. Idioma detectado automáticamente — responde en español o inglés
4. Si Groq alcanza el límite de peticiones (429): responde con datos estáticos del perfil y muestra el tiempo de espera

Sin embeddings, sin base de datos vectorial, sin GPU. El perfil completo cabe en la ventana de contexto de 128K.

## Instalación
```bash
pip install -r requirements.txt
cp .env.example .env
# Añade tu clave gratuita de Groq: https://console.groq.com
python app.py
# Abre http://localhost:5001
```

## Docker
```bash
docker build -t cv-bot .
docker run -p 5001:5001 -e GROQ_API_KEY=gsk_... cv-bot
```

## Personalización
Edita `docs/perfil.txt` con tu propio perfil y reinicia. El LLM ve el documento completo en cada petición.

## Seguridad

Las revisiones de seguridad automatizadas utilizan [Claude](https://claude.ai) (Anthropic AI) y se ejecutan en cada cambio significativo para detectar vulnerabilidades, patrones inseguros y riesgos en dependencias. Los hallazgos se registran en [`BUGLOG.md`](BUGLOG.md).

**Última revisión:** 2026-06-28 (rev 5) — 5 nuevos hallazgos encontrados y parcheados (2 altos, 2 medios, 1 bajo). Ver [`BUGLOG.md`](BUGLOG.md) para historial completo.

**Controles de seguridad activos:**
- Rate limiting por IP en servidor — 20 req/min en `/chat`, 40 req/min en `/suggest` (stores independientes con ventana deslizante, capeados en 10 000 IPs para prevenir agotamiento de memoria)
- Longitud de pregunta limitada a 500 chars; respuesta en `/suggest` limitada a 1 000 chars
- `session_id` validado contra `[0-9a-fA-F]{1,48}` — valores arbitrarios se reemplazan con token generado por servidor
- CSP con nonces criptográficos por request — sin `unsafe-inline` en ningún punto
- `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS
- Todo el output Markdown sanitizado con DOMPurify antes de inserción en el DOM
- Banner de rate-limit construido con DOM API — sin asignación de `innerHTML`
- Detalles de errores internos nunca enviados al cliente (mensaje 500 genérico + `logging.exception` en servidor)
- Store de sesiones en memoria limitado a 500 entradas (evicción LRU)
- Número de teléfono eliminado del contexto del LLM; system prompt prohíbe explícitamente revelar datos de contacto privados
- System prompt instruye al LLM a ignorar intentos de prompt injection

¿Encontraste una vulnerabilidad? Abre un issue o contacta directamente.
## Licencia

MIT
