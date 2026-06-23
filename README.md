# CV Bot

Conversational web assistant that answers questions about Eric C.'s professional profile — skills, projects, and experience. Built with RAG: documents go in, questions come out, no hallucinations.

## Stack
Python · Flask · LangChain · ChromaDB · Groq API (free) · HuggingFace embeddings (local)

## How it works
1. Loads `docs/perfil.txt` (professional profile document)
2. Splits it into chunks and generates local embeddings (no GPU needed)
3. On each question: retrieves the most relevant chunks and sends them + the question to Groq LLM
4. The model can only answer from the document — it won't make things up

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Add your free Groq key: https://console.groq.com
python app.py
# Open http://localhost:5000
```

## Docker
```bash
docker build -t cv-bot .
docker run -p 5000:5000 -e GROQ_API_KEY=gsk_... cv-bot
```

## Customization
Edit `docs/perfil.txt` with your own profile and restart the server. The RAG pipeline rebuilds automatically on startup.
