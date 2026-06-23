"""
CV Bot — asistente web sobre el perfil profesional de Eric C.
RAG: Flask + LangChain + Groq (gratis) + embeddings locales
"""

import os
import sys
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
MODEL         = "llama-3.1-8b-instant"
EMBED_MODEL   = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE    = 600
CHUNK_OVERLAP = 60
TOP_K         = 4

PROMPT_TEMPLATE = """Eres el asistente de CV de Eric C., un profesional de Cloud, DevOps e IA.
Responde en el mismo idioma que use la pregunta (español o inglés).
Usa únicamente la información del perfil que se te proporciona como contexto.
Si la información no está disponible, responde: "No tengo esa información en el perfil."
Sé conciso y directo.

Perfil:
{context}

Pregunta: {question}
Respuesta:"""

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Eric C. — CV Assistant</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0d0d0d;
      color: #e0e0e0;
      height: 100dvh;
      display: flex;
      flex-direction: column;
      align-items: center;
    }

    header {
      width: 100%;
      max-width: 720px;
      padding: 24px 20px 12px;
      text-align: center;
    }
    header h1 { font-size: 1.4rem; color: #fff; }
    header p  { font-size: 0.85rem; color: #777; margin-top: 4px; }

    #chat {
      flex: 1;
      width: 100%;
      max-width: 720px;
      overflow-y: auto;
      padding: 12px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 0.9rem;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .msg.user {
      align-self: flex-end;
      background: #7c5cbf;
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .msg.bot {
      align-self: flex-start;
      background: #1e1e2e;
      border: 1px solid #2a2a3a;
      border-bottom-left-radius: 4px;
    }
    .msg.typing { color: #555; font-style: italic; }

    #form {
      width: 100%;
      max-width: 720px;
      padding: 12px 20px 20px;
      display: flex;
      gap: 8px;
    }
    #input {
      flex: 1;
      padding: 10px 14px;
      background: #1a1a2e;
      border: 1px solid #333;
      border-radius: 8px;
      color: #e0e0e0;
      font-size: 0.9rem;
      outline: none;
    }
    #input:focus { border-color: #7c5cbf; }
    #input::placeholder { color: #555; }

    button {
      padding: 10px 18px;
      background: #7c5cbf;
      border: none;
      border-radius: 8px;
      color: #fff;
      font-size: 0.9rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    button:hover { background: #9b7fe0; }
    button:disabled { background: #444; cursor: default; }

    .suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 0 20px 12px;
      width: 100%;
      max-width: 720px;
    }
    .chip {
      padding: 6px 12px;
      background: #1a1a2e;
      border: 1px solid #333;
      border-radius: 20px;
      font-size: 0.78rem;
      color: #aaa;
      cursor: pointer;
      transition: border-color 0.15s, color 0.15s;
    }
    .chip:hover { border-color: #7c5cbf; color: #c9a8ff; }
  </style>
</head>
<body>
  <header>
    <h1>Eric C. — CV Assistant</h1>
    <p>Pregúntame sobre habilidades, proyectos o experiencia · Ask me about skills, projects or experience</p>
  </header>

  <div id="chat"></div>

  <div class="suggestions">
    <span class="chip" onclick="ask(this.textContent)">¿Qué proyectos has hecho?</span>
    <span class="chip" onclick="ask(this.textContent)">¿Qué tecnologías de IA conoces?</span>
    <span class="chip" onclick="ask(this.textContent)">What Cloud experience do you have?</span>
    <span class="chip" onclick="ask(this.textContent)">¿Sabes Kubernetes?</span>
    <span class="chip" onclick="ask(this.textContent)">Tell me about your networking skills</span>
  </div>

  <form id="form" onsubmit="send(event)">
    <input id="input" type="text" placeholder="Escribe tu pregunta..." autocomplete="off">
    <button id="btn" type="submit">Enviar</button>
  </form>

  <script>
    const chat = document.getElementById('chat');
    const input = document.getElementById('input');
    const btn = document.getElementById('btn');

    function addMsg(text, role) {
      const div = document.createElement('div');
      div.className = `msg ${role}`;
      div.textContent = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      return div;
    }

    async function ask(q) {
      input.value = q;
      await send(new Event('submit'));
    }

    async function send(e) {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;

      addMsg(q, 'user');
      input.value = '';
      btn.disabled = true;

      const typing = addMsg('Pensando...', 'bot typing');

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q })
        });
        const data = await res.json();
        typing.className = 'msg bot';
        typing.textContent = data.answer || data.error || 'Error al procesar la pregunta.';
      } catch {
        typing.className = 'msg bot';
        typing.textContent = 'Error de conexión.';
      } finally {
        btn.disabled = false;
        input.focus();
      }
    }
  </script>
</body>
</html>"""


def build_pipeline():
    if not os.getenv("GROQ_API_KEY"):
        print("[!] Falta GROQ_API_KEY en el archivo .env")
        sys.exit(1)

    print("[~] Cargando documentos...")
    loader = DirectoryLoader(DOCS_DIR, glob="**/*.txt", loader_cls=TextLoader,
                             loader_kwargs={"encoding": "utf-8"})
    docs = loader.load()
    if not docs:
        print(f"[!] No se encontraron documentos en '{DOCS_DIR}'")
        sys.exit(1)
    print(f"[✓] {len(docs)} documento(s) cargado(s)")

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(docs)
    print(f"[✓] {len(chunks)} chunks generados")

    print("[~] Cargando embeddings (primera vez puede tardar)...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectorstore = Chroma.from_documents(chunks, embeddings)
    print("[✓] Vector store listo")

    llm = ChatGroq(model=MODEL, temperature=0)
    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    prompt = PromptTemplate(input_variables=["context", "question"], template=PROMPT_TEMPLATE)

    def format_docs(docs):
        return "\n\n".join(d.page_content for d in docs)

    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain


print("\nCV Bot — iniciando pipeline RAG...")
chain = build_pipeline()
print("[✓] Listo en http://localhost:5000\n")

app = Flask(__name__)

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'Pregunta vacía'}), 400
    try:
        answer = chain.invoke(question)
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
