<p align="center">
  <a href="#english">🇬🇧 English</a> &nbsp;·&nbsp; <a href="#español">🇪🇸 Español</a>
</p>

---

<a name="english"></a>

# CV Bot

Conversational web assistant that answers questions about Eric C.'s professional profile — skills, projects, and experience. Powered by Groq LLM with the full profile passed as context.

Live: [cv-bot-hxku.onrender.com](https://cv-bot-hxku.onrender.com)

## Stack
Python · Flask · Groq API — `openai/gpt-oss-120b` (chat) · `openai/gpt-oss-20b` (suggestions)

## How it works
1. Loads `docs/perfil.txt` at startup (~15KB profile, compacted at load)
2. On each question: sends the full profile + conversation history to the LLM
3. The assistant answers from profile evidence, labels reasonable inferences, and avoids inventing experience
4. Language is detected consistently for answers and recruiter follow-up suggestions in Spanish or English
5. When Groq rate limit is hit (429): falls back to static answers from the profile, shows reset time

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
**v0.6.0** — 2026-10-01
- Profile: synced with the current CV — 2+ years of experience (was wrongly 3+), FCT internships no longer listed as jobs, role responsibilities, Active Directory/DNS/DHCP/ServiceNow, Cisco *Introduction to Cybersecurity* credential
- AI: rewritten system prompt — evidence-first answers, job-description fit analysis (requirement by requirement), follow-up resolution, clear split between jobs, internships and projects
- AI: adaptive reasoning — `reasoning_effort` low by default, medium for role-fit / job-description questions
- Tokens: stable prompt prefix (profile before the per-turn language) for Groq prompt caching; profile compacted at load; only the last 4 exchanges are resent, older answers trimmed; `max_completion_tokens` caps
- Tokens: follow-up suggestions moved to `openai/gpt-oss-20b` (separate rate-limit bucket); in-memory cache for first-turn answers and suggestions
- UI: app version and AI model shown on the page; `/health` returns version and model
- Question length raised to 1 500 chars so recruiters can paste a job description

**v0.5.0** — 2026-09-28
- Model: updated runtime documentation to `openai/gpt-oss-120b` on Groq
- AI: grounded answer and follow-up prompts in profile evidence; prevent invented facts, repeated suggestions, and unsupported logistics answers
- Fix: use server-side language detection for follow-up suggestions; replace misleading default questions with specific bilingual recruiter prompts
- Fix: malformed JSON payloads now return 400; correct rate-limit IP-store and session-store eviction behavior
- Tests: add regression coverage for rate limiting, sessions, JSON validation, and suggestion language


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
- Question length capped at 1 500 chars; `/suggest` answer input capped at 1 000 chars
- `session_id` validated against `[0-9a-fA-F]{1,48}` — arbitrary values replaced with a server-generated token
- CSP with per-request cryptographic nonces — no `unsafe-inline` anywhere
- `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `HSTS`
- All Markdown output sanitized with DOMPurify before DOM insertion
- Rate-limit banner built with DOM API — no `innerHTML` assignment
- Internal error details never sent to client (generic 500 message + server-side `logging.exception`)
- In-memory session store capped at 500 entries (LRU eviction)
- Phone number removed from LLM context; system prompt explicitly forbids revealing private contact details
- System prompt instructs the LLM to ignore prompt-injection attempts
- Rate-limit client IP depends on the reverse proxy overwriting forwarded-IP headers; see [`BUGLOG.md`](BUGLOG.md) for this deployment caveat

Found a vulnerability? Open an issue or contact directly.

---

<a name="español"></a>

# CV Bot

Asistente conversacional web que responde preguntas sobre el perfil profesional de Eric C. — habilidades, proyectos y experiencia. Impulsado por Groq LLM con el perfil completo como contexto.

En producción: [cv-bot-hxku.onrender.com](https://cv-bot-hxku.onrender.com)

## Stack
Python · Flask · Groq API — `openai/gpt-oss-120b` (chat) · `openai/gpt-oss-20b` (suggestions)

## Cómo funciona
1. Carga `docs/perfil.txt` al arrancar (~15KB de perfil, compactado al cargar)
2. En cada pregunta: envía el perfil completo + historial de conversación al LLM
3. La respuesta se basa en el perfil; las inferencias se identifican y no se inventa experiencia
4. Detecta el idioma de forma coherente para las respuestas y preguntas de seguimiento, en español o inglés
5. Si Groq alcanza el límite de peticiones (429): responde con datos estáticos del perfil y muestra el tiempo de espera

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
- Longitud de pregunta limitada a 1 500 chars; respuesta en `/suggest` limitada a 1 000 chars
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
