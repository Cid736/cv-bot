"""
CV Bot - conversational assistant about Eric C.'s professional profile
Flask + Groq llama-3.3-70b  (no embeddings, no torch, full profile in context)
"""

import os, sys, json, re, secrets
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from groq import RateLimitError
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR    = Path("./docs")
MODEL       = "llama-3.3-70b-versatile"
MAX_HISTORY = 8   # exchanges kept per session

sessions: dict[str, list] = {}  # session_id -> [{"role":"user"|"assistant","content":str}]
MAX_SESSIONS = 500

def load_profile() -> str:
    txts = list(DOCS_DIR.glob("**/*.txt"))
    if not txts:
        print(f"[!] No .txt files found in '{DOCS_DIR}'")
        sys.exit(1)
    profile = "\n\n".join(p.read_text(encoding="utf-8") for p in txts)
    print(f"[ok] Profile loaded ({len(profile)} chars from {len(txts)} file(s))")
    return profile

SYSTEM_PROMPT = """\
You are the CV assistant for Eric C., a Cloud & DevOps / AI professional.
Answer questions about Eric's skills, projects, experience, and career.

Rules:
- You MUST reply in {lang}. This is mandatory — do not reply in any other language.
- ALWAYS give a useful, concrete answer — never say "I don't have that information"
- When something isn't explicit, reason from the evidence: infer from projects, stack depth, domains covered
- Mention real project names, technologies, and concrete details from the profile
- For HR questions (strengths, motivation, salary, teamwork) give a confident, structured answer
- Be concise and punchy — a recruiter is reading this

Eric's complete profile:
{profile}"""

SUGGEST_PROMPT = """\
A recruiter just received this answer about a software professional named Eric C.:

Q: {question}
A: {answer}

Generate exactly 3 short follow-up questions a recruiter would naturally ask next.
Respond in {lang}.
Return ONLY a valid JSON array of 3 strings, no extra text.
Example: ["Question 1?", "Question 2?", "Question 3?"]"""


if not os.getenv("GROQ_API_KEY"):
    print("[!] Missing GROQ_API_KEY")
    sys.exit(1)

print("[~] Loading profile...")
PROFILE = load_profile()

SPANISH_RE = re.compile(r'[áéíóúüñ¿¡]|(\bque\b|\bcomo\b|\bcuanto\b|\btienes\b|\beres\b|\bhas\b|\bpuedes\b|\btus\b)', re.I)

def detect_lang(text: str) -> str:
    return "Spanish" if SPANISH_RE.search(text) else "English"

# ── Static fallbacks (shown when Groq rate limit is hit) ─────────────────────

FALLBACKS_ES = [
    (r'sobre ti|cuentame|quien eres|presentat', (
        "Soy Eric C., técnico de sistemas con ~3 años de experiencia. Mi base es "
        "infraestructura: Linux, Windows Server, redes (TCP/IP, VPN, Pi-hole, Tailscale) "
        "y gestión de endpoints con MS Intune. Sobre esa base tengo Cloud & DevOps "
        "(GCP, Docker, Kubernetes, CI/CD) y automatización con Python y Bash. "
        "La IA la uso como complemento, no como núcleo."
    )),
    (r'proyecto|has hecho|portfolio|trabajo', (
        "Proyectos destacados:\n"
        "- **Medical Bot** — SaaS chatbot para clínicas médicas (Python · FastAPI · Docker)\n"
        "- **Task API** — REST API con JWT, 18 tests automáticos y CI/CD completo (Node.js · GitHub Actions)\n"
        "- **Price Tracker** — CLI de rastreo de precios web con historial SQLite (Python)\n"
        "- **RAG Chatbot** — chatbot con embeddings locales, sin GPU (Python · LangChain)\n"
        "- **Smart Notes** — app tipo Obsidian con WikiLinks y grafo de conexiones (Node.js)\n"
        "Todos están en github.com/Cid736"
    )),
    (r'sistema|linux|windows server|red|tcp|vpn|tailscale|pihole|pi-hole|intune', (
        "Mi núcleo es sistemas y redes:\n"
        "- **Linux/Ubuntu** — administración de servidores, servicios, permisos\n"
        "- **Windows Server** — entornos corporativos, Active Directory\n"
        "- **TCP/IP, VPN** — configuración y gestión de redes\n"
        "- **Tailscale** — red mesh VPN sobre WireGuard para acceso remoto seguro\n"
        "- **Pi-hole** — servidor DNS con bloqueo de publicidad a nivel de red\n"
        "- **MS Intune** — gestión de dispositivos y endpoints corporativos"
    )),
    (r'cloud|gcp|google cloud|kubernetes|docker|devops|ci.?cd', (
        "En Cloud & DevOps manejo:\n"
        "- **Google Cloud Platform (GCP)** — despliegue de servicios, Cloud Run\n"
        "- **Docker y Docker Compose** — contenedores y entornos reproducibles\n"
        "- **Kubernetes** — orquestación de contenedores\n"
        "- **GitHub Actions** — CI/CD: pipelines de test, build y despliegue automático"
    )),
    (r'ia|inteligencia artificial|llm|langchain|rag|vertex|automatizacion', (
        "La IA la uso como complemento a mis habilidades de sistemas:\n"
        "- LLMs y Prompt Engineering — uso práctico de modelos de lenguaje\n"
        "- RAG (Retrieval-Augmented Generation) — chatbots con contexto de documentos\n"
        "- Vertex AI — plataforma de IA de Google Cloud\n"
        "- LangChain — pipelines de IA\n"
        "Tengo proyectos en producción: RAG Chatbot, CV Bot y Medical Bot."
    )),
    (r'python|bash|script|programacion|javascript|node', (
        "Programo principalmente para automatizar tareas de sistemas:\n"
        "- **Python** — scripting, CLIs, automatización, herramientas de sistemas\n"
        "- **Bash** — scripts de administración y automatización\n"
        "- **SQL/SQLite** — bases de datos relacionales\n"
        "- **JavaScript/Node.js** — APIs REST como complemento"
    )),
    (r'fuerte|habilidad|punto fuerte|strength|skill', (
        "Mis puntos fuertes:\n"
        "1. **Visión de extremo a extremo** — de la red al despliegue en cloud\n"
        "2. **Autonomía** — configuro, despliego y mantengo sistemas sin depender de nadie\n"
        "3. **Automatización** — si algo se repite, lo scripto en Python o Bash\n"
        "4. **Aprendizaje rápido** — en 3 años: sistemas → DevOps → Cloud → IA"
    )),
    (r'debil|mejora|weakness|mejorar', (
        "Quiero profundizar en seguridad de sistemas y redes — hardening de servidores, "
        "firewalls avanzados, posiblemente CompTIA Security+. Tengo base pero quiero más "
        "profundidad. También estoy mejorando la comunicación técnica hacia perfiles no técnicos."
    )),
    (r'contratar|hire|por que|why.*hire|deberiamos', (
        "Porque tengo base sólida en sistemas y redes con exposición real a entornos "
        "corporativos (Intune, Windows Server, VPN), y encima sé automatizar, contenerizar "
        "y desplegar en cloud. No soy solo un administrador clásico: puedo montar un servidor "
        "Linux, configurar la red, dockerizarlo, subirlo a GCP y poner CI/CD — todo yo. "
        "Eso da mucha autonomía a cualquier equipo."
    )),
    (r'5 años|cinco años|futuro|donde.*ves|5 years|future', (
        "En un rol de administrador de sistemas senior o arquitecto de infraestructura, "
        "gestionando entornos complejos que combinen on-premise y cloud. Me interesa "
        "especializarme en seguridad de sistemas e infraestructura como código "
        "(Terraform, Ansible)."
    )),
    (r'año|experiencia|tiempo|how long|years|experience', (
        "Tengo aproximadamente 3 años de experiencia en el sector tecnológico. "
        "Perfil junior-mid con stack amplio: sistemas, redes, Cloud, DevOps y nociones de IA. "
        "La evolución ha sido rápida — de infraestructura básica a CI/CD, Kubernetes y "
        "pipelines de IA en ese tiempo."
    )),
    (r'salario|salary|sueldo|expectativa|pay', (
        "Estoy abierto a discutirlo según el rol y las responsabilidades. "
        "Me interesa un salario competitivo acorde al mercado para perfiles de "
        "sistemas junior-mid con conocimientos en cloud y automatización."
    )),
]

FALLBACKS_EN = [
    (r'about you|yourself|who are you|introduce', (
        "I'm Eric C., a systems technician with ~3 years of experience. My core is "
        "infrastructure: Linux, Windows Server, networking (TCP/IP, VPN, Pi-hole, Tailscale) "
        "and endpoint management with MS Intune. On top of that I have Cloud & DevOps "
        "(GCP, Docker, Kubernetes, CI/CD) and automation with Python and Bash. "
        "I use AI as a complement, not as my core identity."
    )),
    (r'project|portfolio|built|work', (
        "Key projects:\n"
        "- **Medical Bot** — SaaS chatbot for medical clinics (Python · FastAPI · Docker)\n"
        "- **Task API** — REST API with JWT auth, 18 automated tests and full CI/CD (Node.js · GitHub Actions)\n"
        "- **Price Tracker** — web price tracking CLI with SQLite history (Python)\n"
        "- **RAG Chatbot** — chatbot with local embeddings, no GPU needed (Python · LangChain)\n"
        "- **Smart Notes** — Obsidian-like app with WikiLinks and graph view (Node.js)\n"
        "All on github.com/Cid736"
    )),
    (r'system|linux|windows server|network|tcp|vpn|tailscale|pihole|intune', (
        "My core is systems & networking:\n"
        "- **Linux/Ubuntu** — server admin, services, permissions\n"
        "- **Windows Server** — corporate environments, Active Directory\n"
        "- **TCP/IP, VPN** — network configuration and management\n"
        "- **Tailscale** — mesh VPN over WireGuard for secure remote access\n"
        "- **Pi-hole** — DNS server with network-level ad blocking\n"
        "- **MS Intune** — corporate device and endpoint management"
    )),
    (r'cloud|gcp|google cloud|kubernetes|docker|devops|ci.?cd', (
        "In Cloud & DevOps:\n"
        "- **Google Cloud Platform (GCP)** — service deployment, Cloud Run\n"
        "- **Docker & Docker Compose** — containers and reproducible environments\n"
        "- **Kubernetes** — container orchestration\n"
        "- **GitHub Actions** — CI/CD pipelines: test, build and deploy"
    )),
    (r'strength|skill|good at|best', (
        "My strengths:\n"
        "1. **End-to-end visibility** — from network config to cloud deployment\n"
        "2. **Autonomy** — I set up, deploy and maintain systems independently\n"
        "3. **Automation mindset** — if something repeats, I script it in Python or Bash\n"
        "4. **Fast learner** — in 3 years: sysadmin → DevOps → Cloud → AI"
    )),
    (r'weakness|improve|area', (
        "I want to go deeper into systems security — server hardening, advanced firewalls, "
        "possibly CompTIA Security+. I have the foundation but want more depth. "
        "I'm also improving how I communicate technical concepts to non-technical stakeholders."
    )),
    (r'hire|why.*you|should we', (
        "Because I have a solid foundation in systems and networking with real corporate "
        "exposure (Intune, Windows Server, VPN), and on top of that I can automate, "
        "containerize and deploy to the cloud. I'm not just a classic sysadmin: "
        "I can set up a Linux server, configure the network, dockerize the service, "
        "push it to GCP and add CI/CD — all by myself. That gives a team a lot of autonomy."
    )),
    (r'year|experience|how long|how many', (
        "About 3 years of experience in the tech sector. "
        "Junior-mid profile with a broad stack: systems, networking, Cloud, DevOps and AI. "
        "The progression has been fast — from basic infrastructure to CI/CD, Kubernetes "
        "and AI pipelines in that time."
    )),
    (r'salary|pay|compensation|expect', (
        "Open to discussing based on the role and responsibilities. "
        "I'm looking for a competitive salary in line with the market for "
        "junior-mid systems profiles with cloud and automation skills."
    )),
]

def static_answer(question: str, lang: str) -> str:
    q = question.lower()
    table = FALLBACKS_ES if lang == "Spanish" else FALLBACKS_EN
    for pattern, answer in table:
        if re.search(pattern, q):
            return answer
    if lang == "Spanish":
        return (
            "El asistente IA está temporalmente pausado por límite de uso de la API. "
            "Puedes ver el perfil completo de Eric en **github.com/Cid736** o escribirle directamente. "
            "Prueba con una pregunta más específica sobre proyectos, tecnologías o experiencia."
        )
    return (
        "The AI assistant is temporarily paused due to API rate limits. "
        "You can view Eric's full profile at **github.com/Cid736** or reach out directly. "
        "Try a more specific question about projects, technologies or experience."
    )


llm         = ChatGroq(model=MODEL, temperature=0.2)
llm_suggest = ChatGroq(model=MODEL, temperature=0.7)
print("[ok] Ready\n")

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Eric C. - CV Assistant</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0d0d0d; --surface: #141420; --border: #252535;
      --accent: #7c5cbf; --accent-h: #9b7fe0;
      --text: #e2e2e2; --muted: #666;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: var(--bg); color: var(--text);
      height: 100dvh; display: flex; flex-direction: column; align-items: center;
    }
    header {
      width: 100%; max-width: 760px;
      padding: 20px 20px 8px;
      display: flex; align-items: center; gap: 14px;
    }
    .avatar {
      width: 44px; height: 44px; border-radius: 50%;
      background: linear-gradient(135deg, #7c5cbf, #3a2a6e);
      display: flex; align-items: center; justify-content: center;
      font-size: 1.1rem; font-weight: 700; color: #fff; flex-shrink: 0;
    }
    .htext h1 { font-size: 1rem; color: #fff; font-weight: 600; }
    .htext p  { font-size: 0.76rem; color: var(--muted); margin-top: 2px; }
    .badge {
      margin-left: auto; padding: 4px 10px;
      background: #1a2e1a; border: 1px solid #2a4a2a;
      border-radius: 20px; font-size: 0.72rem; color: #5a9a5a;
    }
    #chat {
      flex: 1; width: 100%; max-width: 760px;
      overflow-y: auto; padding: 8px 20px 4px;
      display: flex; flex-direction: column; gap: 10px;
    }
    #chat::-webkit-scrollbar { width: 4px; }
    #chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
    .msg {
      max-width: 82%; padding: 11px 15px;
      border-radius: 14px; font-size: 0.88rem; line-height: 1.6;
    }
    .msg.user {
      align-self: flex-end; background: var(--accent); color: #fff;
      border-bottom-right-radius: 4px;
    }
    .msg.bot {
      align-self: flex-start; background: var(--surface);
      border: 1px solid var(--border); border-bottom-left-radius: 4px;
    }
    .msg.bot p { margin-bottom: 6px; }
    .msg.bot p:last-child { margin-bottom: 0; }
    .msg.bot ul, .msg.bot ol { padding-left: 18px; margin: 4px 0; }
    .msg.bot li { margin: 2px 0; }
    .msg.bot code {
      background: #1e1e2e; padding: 1px 5px; border-radius: 4px;
      font-size: 0.82em; font-family: monospace;
    }
    .msg.bot strong { color: #c9a8ff; }
    .dots span {
      display: inline-block; width: 6px; height: 6px;
      background: var(--muted); border-radius: 50%; margin: 0 2px;
      animation: bounce 1.2s infinite ease-in-out;
    }
    .dots span:nth-child(2) { animation-delay: .2s; }
    .dots span:nth-child(3) { animation-delay: .4s; }
    @keyframes bounce {
      0%,80%,100% { transform: translateY(0); opacity:.4; }
      40%          { transform: translateY(-5px); opacity:1; }
    }
    #chips {
      width: 100%; max-width: 760px;
      padding: 6px 20px 4px; display: flex; flex-wrap: wrap; gap: 7px; min-height: 38px;
    }
    .chip {
      padding: 6px 13px; background: var(--surface);
      border: 1px solid var(--border); border-radius: 20px;
      font-size: 0.75rem; color: #aaa; cursor: pointer;
      transition: border-color .15s, color .15s, opacity .2s, transform .2s;
    }
    .chip:hover { border-color: var(--accent); color: #c9a8ff; }
    .chip.out { opacity: 0; transform: translateY(-4px); }
    @keyframes chipIn {
      from { opacity: 0; transform: translateY(6px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .chip.in { animation: chipIn .25s ease forwards; }
    #form {
      width: 100%; max-width: 760px;
      padding: 8px 20px 18px; display: flex; gap: 8px; align-items: flex-end;
    }
    #input {
      flex: 1; padding: 11px 14px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; color: var(--text); font-size: 0.88rem;
      outline: none; resize: none; min-height: 44px; max-height: 120px;
      line-height: 1.5; font-family: inherit;
    }
    #input:focus { border-color: var(--accent); }
    #input::placeholder { color: var(--muted); }
    button {
      padding: 0 18px; background: var(--accent);
      border: none; border-radius: 10px; color: #fff;
      font-size: 1rem; cursor: pointer; transition: background .15s; height: 44px; flex-shrink: 0;
    }
    button:hover { background: var(--accent-h); }
    button:disabled { background: #333; cursor: default; }
    #rate-banner {
      display: none; width: 100%; max-width: 760px;
      margin: 4px 20px 0; padding: 9px 14px;
      background: #2a1a00; border: 1px solid #6b3f00;
      border-radius: 8px; font-size: 0.78rem; color: #e09a3a;
      gap: 8px; align-items: center;
    }
    #rate-banner.visible { display: flex; }
    #rate-banner a { color: #e09a3a; }
    #alpha-banner { background:#1a1200; border-bottom:1px solid #4a3500; padding:6px 20px; font-size:0.73rem; color:#d29922; display:flex; align-items:center; gap:8px; }
    #alpha-banner .ab { background:#4a3500; color:#d29922; font-size:0.62rem; font-weight:700; padding:1px 6px; border-radius:4px; letter-spacing:.5px; }
    #alpha-banner a { color:#d29922; }
  </style>
</head>
<body>
  <div id="alpha-banner">
    <span class="ab">ALPHA</span>
    Versi&oacute;n en desarrollo &mdash; pueden existir errores.
    Reporta en <a href="https://github.com/Cid736/cv-bot/issues" target="_blank">github.com/Cid736/cv-bot</a>
  </div>
  <header>
    <div class="avatar">EC</div>
    <div class="htext">
      <h1>Eric C. &mdash; CV Assistant</h1>
      <p>Cloud &amp; DevOps &middot; IA &middot; Sistemas &amp; Redes &middot; Ask in any language</p>
    </div>
    <span class="badge">&#9679; online</span>
  </header>

  <div id="chat"></div>
  <div id="rate-banner">
    &#9888; Asistente IA pausado por l&iacute;mite de uso (Groq free tier).
    Las respuestas son est&aacute;ticas hasta que se reinicie el contador (~1 min).
    Perfil completo: <a href="https://github.com/Cid736" target="_blank">github.com/Cid736</a>
  </div>
  <div id="chips"></div>

  <form id="form" onsubmit="send(event)">
    <textarea id="input" placeholder="Pregunta en cualquier idioma / Ask in any language..." rows="1"
      oninput="resize(this)" onkeydown="onKey(event)"></textarea>
    <button id="btn" type="submit">&#9658;</button>
  </form>

  <script>
    const chat   = document.getElementById('chat');
    const input  = document.getElementById('input');
    const btn    = document.getElementById('btn');
    const chips  = document.getElementById('chips');
    const banner = document.getElementById('rate-banner');
    let sid  = null;
    let busy = false;

    const DEFAULTS = [
      "Que proyectos has hecho?",
      "Que tecnologias de IA conoces?",
      "What Cloud & DevOps experience do you have?",
      "Sabes Kubernetes?",
      "Por que deberiamos contratarte?"
    ];

    function setChips(list) {
      [...chips.children].forEach(c => c.classList.add('out'));
      setTimeout(() => {
        chips.innerHTML = '';
        list.forEach(q => {
          const el = document.createElement('span');
          el.className = 'chip in';
          el.textContent = q;
          el.onclick = () => ask(q);
          chips.appendChild(el);
        });
      }, 220);
    }

    function addMsg(html, role, markdown) {
      const d = document.createElement('div');
      d.className = 'msg ' + role;
      if (markdown) d.innerHTML = marked.parse(html);
      else d.textContent = html;
      chat.appendChild(d);
      chat.scrollTop = chat.scrollHeight;
      return d;
    }

    function typing() {
      const d = document.createElement('div');
      d.className = 'msg bot';
      d.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
      chat.appendChild(d);
      chat.scrollTop = chat.scrollHeight;
      return d;
    }

    function resize(el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }

    function onKey(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e); }
    }

    async function ask(q) { input.value = q; resize(input); await send(new Event('submit')); }

    async function send(e) {
      e.preventDefault();
      const q = input.value.trim();
      if (!q || busy) return;
      busy = true; btn.disabled = true;

      addMsg(q, 'user', false);
      input.value = ''; resize(input);
      const t = typing();

      try {
        const res  = await fetch('/chat', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ question: q, session_id: sid })
        });
        const data = await res.json();
        t.remove();
        if (data.error) { addMsg(data.error, 'bot', false); }
        else {
          sid = data.session_id;
          addMsg(data.answer, 'bot', true);
          if (data.rate_limited) {
            const resetMsg = data.reset_msg || 'consulta la consola de Groq';
            banner.innerHTML = '&#9888; Asistente IA pausado por l&iacute;mite de uso (Groq free tier). '
              + '<strong>' + resetMsg + '</strong>. '
              + 'Perfil completo: <a href="https://github.com/Cid736" target="_blank">github.com/Cid736</a>';
            banner.classList.add('visible');
          } else {
            banner.classList.remove('visible');
            getSuggestions(q, data.answer);
          }
        }
      } catch { t.remove(); addMsg('Error de conexion.', 'bot', false); }
      finally { busy = false; btn.disabled = false; input.focus(); }
    }

    async function getSuggestions(q, a) {
      try {
        const lang = /[aeiou]{2,}|[nN][oO]|[qQ]ue|[cC]omo/i.test(q) ? 'Spanish' : 'English';
        const res  = await fetch('/suggest', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ question: q, answer: a, lang })
        });
        const data = await res.json();
        if (Array.isArray(data.suggestions) && data.suggestions.length)
          setChips(data.suggestions);
      } catch {}
    }

    setChips(DEFAULTS);
    input.focus();
  </script>
</body>
</html>"""

# ── Flask ─────────────────────────────────────────────────────────────────────

app = Flask(__name__)

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/chat', methods=['POST'])
def chat_route():
    data     = request.get_json(silent=True) or {}
    question = data.get('question', '').strip()
    sid      = data.get('session_id') or secrets.token_hex(12)

    if not question:
        return jsonify({'error': 'Empty question'}), 400

    history = sessions.get(sid, [])

    lang    = detect_lang(question)
    system  = SYSTEM_PROMPT.format(profile=PROFILE, lang=lang)
    messages = [SystemMessage(content=system)]
    for h in history[-(MAX_HISTORY):]:
        messages.append(HumanMessage(content=h['q']))
        messages.append(AIMessage(content=h['a']))
    messages.append(HumanMessage(content=question))

    try:
        answer = llm.invoke(messages).content
        history.append({"q": question, "a": answer})
        sessions[sid] = history[-MAX_HISTORY:]
        if len(sessions) >= MAX_SESSIONS:
            sessions.pop(next(iter(sessions)))
        return jsonify({"answer": answer, "session_id": sid})
    except RateLimitError as e:
        # Groq includes "Please try again in Xs" or "Xm Ys" in the message
        msg = str(e)
        retry_match = re.search(r'try again in ([\d\w\s\.]+?)\.', msg, re.I)
        if retry_match:
            retry_in = retry_match.group(1).strip()
            reset_msg = f"Reintentar en {retry_in}"
        elif 'per_day' in msg.lower() or 'rpd' in msg.lower() or 'tpd' in msg.lower():
            reset_msg = "Limite diario — se reinicia a medianoche UTC"
        else:
            reset_msg = "Reintentar en ~60 segundos (limite por minuto)"
        answer = static_answer(question, lang)
        return jsonify({"answer": answer, "session_id": sid, "rate_limited": True, "reset_msg": reset_msg})
    except Exception:
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/suggest', methods=['POST'])
def suggest():
    data = request.get_json(silent=True) or {}
    q, a, lang = data.get('question',''), data.get('answer',''), data.get('lang','Spanish')
    try:
        prompt = SUGGEST_PROMPT.format(question=q, answer=a, lang=lang)
        raw    = llm_suggest.invoke([HumanMessage(content=prompt)]).content
        m      = re.search(r'\[.*?\]', raw, re.DOTALL)
        return jsonify({"suggestions": json.loads(m.group())[:3] if m else []})
    except Exception:
        return jsonify({"suggestions": []})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
