# CV Bot

Asistente web conversacional que responde preguntas sobre el perfil profesional de Eric C. — habilidades, proyectos y experiencia. Construido con RAG: los documentos entran, las preguntas salen, sin alucinaciones.

## Stack
Python · Flask · LangChain · ChromaDB · Groq API (gratuito) · Embeddings HuggingFace (local)

## Cómo funciona
1. Carga `docs/perfil.txt` (documento con el perfil profesional)
2. Lo divide en chunks y genera embeddings locales (sin GPU necesaria)
3. En cada pregunta: recupera los chunks más relevantes y los envía junto a la pregunta al LLM de Groq
4. El modelo solo puede responder con la información del documento — no inventa

## Instalación
```bash
pip install -r requirements.txt
cp .env.example .env
# Añade tu key de Groq gratuita: https://console.groq.com
python app.py
# Abre http://localhost:5000
```

## Docker
```bash
docker build -t cv-bot .
docker run -p 5000:5000 -e GROQ_API_KEY=gsk_... cv-bot
```

## Personalización
Edita `docs/perfil.txt` con tu propio perfil y reinicia el servidor. El pipeline RAG se reconstruye automáticamente al arrancar.
