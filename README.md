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

**v0.2.0** — 2026-06-24
- Fix: remove unused variable in frontend suggest handler
- Feat: Groq rate-limit fallback with static answers and dynamic reset time banner
- Feat: alpha version banner

**v0.1.0** — 2026-06-01
- Initial release: Flask + Groq LLM, conversation history, language auto-detection, suggested follow-up questions
