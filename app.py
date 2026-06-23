"""
CV Bot - conversational assistant about Eric C.'s professional profile
Flask + LangChain + Groq llama-3.3-70b + HuggingFace embeddings (local)
"""

import os, sys, json, re, secrets
from operator import itemgetter
from flask import Flask, request, jsonify, render_template_string
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR      = "./docs"
MODEL         = "llama-3.3-70b-versatile"
EMBED_MODEL   = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 80
TOP_K         = 5
MAX_HISTORY   = 6

sessions = {}   # session_id -> [{"q": str, "a": str}]

MAIN_PROMPT = (
    "You are the CV assistant for Eric C., a Cloud & DevOps / AI professional.\n"
    "Your job: answer questions about Eric as if you were him speaking in first person, "
    "or as his representative when the recruiter asks in third person.\n\n"
    "Rules:\n"
    "- Detect the language of the question and respond in THAT same language (Spanish or English)\n"
    "- ALWAYS give a useful answer. Never say 'I don't have that information' — instead, "
    "reason from what you know: infer experience level from projects, depth from tech stack, "
    "seniority from the breadth of domains covered\n"
    "- Be specific: mention real project names, technologies, and concrete details from the profile\n"
    "- If asked about something not in the profile (like exact years), give a reasonable, "
    "honest estimate based on the evidence you have, and say it's an estimate\n"
    "- For HR questions (strengths, weaknesses, salary, teamwork), give a confident, "
    "well-structured answer — these are already prepared in the profile\n"
    "- Be concise and punchy — think recruiter reading a strong candidate's profile\n"
    "- Use conversation history to answer follow-ups correctly\n\n"
    "Conversation so far:\n{history}\n\n"
    "Relevant profile sections:\n{context}\n\n"
    "Question: {question}\n"
    "Answer:"
)

SUGGEST_PROMPT = (
    "A recruiter is reading about a software professional named Eric C. "
    "and just received this answer:\n\n"
    "Q: {question}\n"
    "A: {answer}\n\n"
    "Generate exactly 3 short follow-up questions a recruiter might naturally ask next.\n"
    "Respond in {lang}.\n"
    "Return ONLY a valid JSON array of 3 strings - no explanation, no markdown, just the array.\n"
    'Example: ["Question 1?", "Question 2?", "Question 3?"]'
)

# ── RAG pipeline ──────────────────────────────────────────────────────────────

def build_pipeline():
    if not os.getenv("GROQ_API_KEY"):
        print("[!] Missing GROQ_API_KEY in .env")
        sys.exit(1)

    print("[~] Loading documents...")
    loader = DirectoryLoader(DOCS_DIR, glob="**/*.txt", loader_cls=TextLoader,
                             loader_kwargs={"encoding": "utf-8"})
    docs = loader.load()
    if not docs:
        print(f"[!] No .txt files found in '{DOCS_DIR}'")
        sys.exit(1)
    print(f"[ok] {len(docs)} doc(s) loaded")

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    ).split_documents(docs)
    print(f"[ok] {len(chunks)} chunks")

    print("[~] Loading embeddings (first run may take a minute)...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectorstore = Chroma.from_documents(chunks, embeddings)
    print("[ok] Vector store ready")

    llm       = ChatGroq(model=MODEL, temperature=0.15)
    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    prompt    = PromptTemplate(
        input_variables=["history", "context", "question"],
        template=MAIN_PROMPT,
    )

    def fmt(docs):
        return "\n\n".join(d.page_content for d in docs)

    chain = (
        {
            "context":  itemgetter("question") | retriever | fmt,
            "question": itemgetter("question"),
            "history":  itemgetter("history"),
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain, ChatGroq(model=MODEL, temperature=0.7)


print("\nCV Bot - building RAG pipeline...")
chain, llm_suggest = build_pipeline()
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
  </style>
</head>
<body>
  <header>
    <div class="avatar">EC</div>
    <div class="htext">
      <h1>Eric C. &mdash; CV Assistant</h1>
      <p>Cloud &amp; DevOps &middot; IA &middot; Sistemas &amp; Redes &middot; Ask in any language</p>
    </div>
    <span class="badge">&#9679; online</span>
  </header>

  <div id="chat"></div>
  <div id="chips"></div>

  <form id="form" onsubmit="send(event)">
    <textarea id="input" placeholder="Pregunta en cualquier idioma / Ask in any language..." rows="1"
      oninput="resize(this)" onkeydown="onKey(event)"></textarea>
    <button id="btn" type="submit">&#9658;</button>
  </form>

  <script>
    const chat  = document.getElementById('chat');
    const input = document.getElementById('input');
    const btn   = document.getElementById('btn');
    const chips = document.getElementById('chips');
    let sid  = null;
    let busy = false;

    const DEFAULTS = [
      "Que proyectos has hecho?",
      "Que tecnologias de IA conoces?",
      "What Cloud & DevOps experience do you have?",
      "Sabes Kubernetes?",
      "Tell me about your networking skills"
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
          getSuggestions(q, data.answer);
        }
      } catch { t.remove(); addMsg('Error de conexion.', 'bot', false); }
      finally { busy = false; btn.disabled = false; input.focus(); }
    }

    async function getSuggestions(q, a) {
      try {
        const lang = /[a-z]/i.test(q) && !/[aeiou]{2}/i.test(q) ? 'English' : 'Spanish';
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

# ── Flask routes ──────────────────────────────────────────────────────────────

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

    hist = sessions.get(sid, [])
    history_text = "\n\n".join(
        f"Human: {h['q']}\nAssistant: {h['a']}" for h in hist[-MAX_HISTORY:]
    ) or "(No previous conversation)"

    try:
        answer = chain.invoke({"question": question, "history": history_text})
        hist.append({"q": question, "a": answer})
        sessions[sid] = hist[-MAX_HISTORY:]
        return jsonify({"answer": answer, "session_id": sid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/suggest', methods=['POST'])
def suggest():
    data = request.get_json(silent=True) or {}
    q, a, lang = data.get('question',''), data.get('answer',''), data.get('lang','Spanish')
    try:
        raw = llm_suggest.invoke(SUGGEST_PROMPT.format(question=q, answer=a, lang=lang)).content
        m   = re.search(r'\[.*?\]', raw, re.DOTALL)
        return jsonify({"suggestions": json.loads(m.group())[:3] if m else []})
    except Exception:
        return jsonify({"suggestions": []})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
