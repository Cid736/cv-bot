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
