'use strict';

const $ = id => document.getElementById(id);
const chat = $('chat'), input = $('input'), btn = $('btn'), chips = $('chips');
const banner = $('rate-banner'), usagePanel = $('usage-panel');
const jobBtn = $('job'), jobPill = $('job-pill');
const micBtn = $('mic'), speakBtn = $('speak-toggle');

let sid = null;          // server session id
let lang = null;         // language of the last answer (Spanish, English, ...)
let busy = false;
let turn = 0;            // bumped on every question/reset so late suggestions are discarded
let jobMode = false;
const transcript = [];   // [{role, text, mode}] for export

const DEFAULTS = [
  "¿Qué proyectos has desarrollado y cuál demuestra mejor tu perfil?",
  "¿Qué hace en su puesto actual en Infinity Neural?",
  "What did he do as IT Support Technician at AMC Networks?",
  "¿Qué certificaciones tiene?",
  "Why is he a strong fit for an IT support or sysadmin role?",
];

// ── Rendering ────────────────────────────────────────────────────────────────
// If the CDN is unreachable the chat still works, falling back to plain text.
const canRender = !!(window.marked && window.DOMPurify);
if (canRender) {
  DOMPurify.addHook('afterSanitizeAttributes', node => {
    if (node.tagName === 'A') {   // links in answers open in a new tab, safely
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer');
    }
  });
}

function renderInto(el, text) {
  if (canRender) el.innerHTML = DOMPurify.sanitize(marked.parse(text));
  else el.textContent = text;
}

function scrollDown() { chat.scrollTop = chat.scrollHeight; }

function addUserMsg(text, mode) {
  const d = document.createElement('div');
  d.className = 'msg user';
  if (mode === 'job') {
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    sum.textContent = `📋 Oferta de empleo (${text.length} caracteres)`;
    det.append(sum, document.createTextNode(text));
    d.appendChild(det);
  } else {
    d.textContent = text;
  }
  chat.appendChild(d);
  scrollDown();
}

function addBotMsg() {
  const d = document.createElement('div');
  d.className = 'msg bot';
  d.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
  chat.appendChild(d);
  scrollDown();
  return d;
}

function setChips(list) {
  [...chips.children].forEach(c => c.classList.add('out'));
  setTimeout(() => {
    chips.innerHTML = '';
    list.forEach(q => {
      const el = document.createElement('span');
      el.className = 'chip in';
      el.textContent = q;
      el.addEventListener('click', () => ask(q));
      chips.appendChild(el);
    });
    const job = document.createElement('span');
    job.className = 'chip in job';
    job.textContent = '📋 Analizar una oferta de empleo';
    job.addEventListener('click', () => setJobMode(true));
    chips.appendChild(job);
  }, 220);
}

// ── Feedback 👍 / 👎 ──────────────────────────────────────────────────────────

function addFeedback(bubble, messageId) {
  if (!messageId) return;
  const bar = document.createElement('div');
  bar.className = 'feedback';
  const thanks = document.createElement('span');
  thanks.className = 'thanks';
  let current = 0;
  const mk = (emoji, value, title) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = emoji; b.title = title;
    b.addEventListener('click', async () => {
      current = current === value ? 0 : value;
      bar.querySelectorAll('button').forEach(x => x.classList.remove('on'));
      if (current) b.classList.add('on');
      thanks.textContent = current ? '¡Gracias!' : '';
      try {
        await fetch('/feedback', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ message_id: messageId, rating: current }),
        });
      } catch {}
    });
    return b;
  };
  bar.append(mk('👍', 1, 'Respuesta útil'), mk('👎', -1, 'Respuesta mejorable'), thanks);
  bubble.appendChild(bar);
}

// ── Job-offer mode ───────────────────────────────────────────────────────────

function setJobMode(on) {
  if (busy) return;
  jobMode = on;
  jobPill.hidden = !on;
  jobBtn.classList.toggle('active', on);
  input.classList.toggle('job', on);
  input.maxLength = Number(on ? input.dataset.jobMax : input.dataset.chatMax);
  input.placeholder = on
    ? 'Pega la oferta de empleo / Paste the job description'
    : 'Pregunta sobre Eric / Ask about Eric';
  input.focus();
}

// ── Sending & streaming ──────────────────────────────────────────────────────

function resize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, jobMode ? 240 : 120) + 'px';
}

async function ask(q) {
  if (busy) return;
  input.value = q; resize(input);
  await send();
}

function showRateBanner(resetMsg) {
  banner.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = resetMsg || 'consulta la consola de Groq';
  const link = document.createElement('a');
  link.href = 'https://github.com/Cid736'; link.target = '_blank'; link.rel = 'noopener';
  link.textContent = 'github.com/Cid736';
  banner.append('⚠ Asistente IA pausado (Groq). Respuestas estáticas. ', strong, '. Perfil completo: ', link);
  banner.classList.add('visible');
}

async function readStream(res, bubble, onMeta) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', text = '', result = { text: '', messageId: null, error: null };
  let pending = false;
  const paint = () => {
    pending = false;
    renderInto(bubble, text);
    bubble.classList.add('cursor');
    scrollDown();
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx); buffer = buffer.slice(idx + 2);
      if (!raw.startsWith('data: ')) continue;
      let ev; try { ev = JSON.parse(raw.slice(6)); } catch { continue; }
      if (ev.type === 'meta') onMeta(ev);
      else if (ev.type === 'delta') {
        text += ev.text;
        if (!pending) { pending = true; requestAnimationFrame(paint); }
      }
      else if (ev.type === 'done') result.messageId = ev.message_id;
      else if (ev.type === 'error') result.error = ev.message;
    }
  }
  bubble.classList.remove('cursor');
  result.text = text.trim();
  if (result.text) renderInto(bubble, result.text);
  return result;
}

async function send(e) {
  if (e) e.preventDefault();
  const q = input.value.trim();
  if (!q || busy) return;
  busy = true; btn.disabled = true;
  const mode = jobMode ? 'job' : 'chat';
  const myTurn = ++turn;
  const viaVoice = askedByVoice; askedByVoice = false;
  stopSpeaking();

  addUserMsg(q, mode);
  transcript.push({ role: 'user', text: q, mode });
  input.value = ''; resize(input);
  if (jobMode) setJobModeAfterSend();
  const bubble = addBotMsg();
  if (mode === 'job') bubble.classList.add('wide');

  try {
    const res = await fetch('/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, session_id: sid, mode, stream: true }),
    });
    let answer = '', messageId = null, rateLimited = false;
    if ((res.headers.get('content-type') || '').includes('text/event-stream')) {
      const r = await readStream(res, bubble, ev => { sid = ev.session_id; lang = ev.lang; });
      answer = r.text; messageId = r.messageId;
      if (r.error) {
        if (!answer) bubble.textContent = r.error;
        else { const p = document.createElement('p'); p.textContent = '⚠ ' + r.error; bubble.appendChild(p); }
      }
    } else {
      const data = await res.json();
      if (data.error) { bubble.textContent = data.error; return; }
      sid = data.session_id; lang = data.lang || lang;
      answer = data.answer; messageId = data.message_id; rateLimited = !!data.rate_limited;
      renderInto(bubble, answer);
      if (rateLimited) showRateBanner(data.reset_msg);
    }
    if (!answer) return;
    transcript.push({ role: 'bot', text: answer });
    addFeedback(bubble, messageId);
    scrollDown();
    if (!rateLimited) {
      banner.classList.remove('visible');
      getSuggestions(mode === 'job' ? 'Análisis de oferta de empleo' : q, answer, lang, myTurn);
      pollUsage();
    }
    if (speakEnabled || viaVoice) speak(answer, lang);
  } catch {
    bubble.textContent = 'Error de conexión.';
  } finally {
    busy = false; btn.disabled = false; input.focus();
  }
}

function setJobModeAfterSend() {
  jobMode = false; jobPill.hidden = true; jobBtn.classList.remove('active');
  input.classList.remove('job'); input.maxLength = Number(input.dataset.chatMax);
  input.placeholder = 'Pregunta sobre Eric / Ask about Eric';
}

async function getSuggestions(q, a, answerLang, myTurn) {
  try {
    const res = await fetch('/suggest', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, answer: a, lang: answerLang }),
    });
    const data = await res.json();
    if (myTurn === turn && Array.isArray(data.suggestions) && data.suggestions.length)
      setChips(data.suggestions);
  } catch {}
}

function resetChat() {
  if (busy) return;
  sid = null; lang = null; turn++;
  transcript.length = 0;
  chat.innerHTML = '';
  banner.classList.remove('visible');
  stopSpeaking();
  if (jobMode) setJobMode(false);
  setChips(DEFAULTS);
  input.value = ''; resize(input); input.focus();
}

// ── Export ───────────────────────────────────────────────────────────────────

function exportConversation() {
  if (!transcript.length) { alert('Todavía no hay conversación que exportar.'); return; }
  const date = new Date();
  const lines = [
    '# Conversación con el asistente de CV de Eric C.',
    '',
    `_${date.toLocaleString()} · ${location.origin}_`,
    '',
  ];
  for (const m of transcript) {
    if (m.role === 'user') {
      lines.push(m.mode === 'job' ? '## 📋 Oferta de empleo' : '## Pregunta', '', m.text, '');
    } else {
      lines.push('**Respuesta:**', '', m.text, '', '---', '');
    }
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `conversacion-cv-eric-${date.toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ── Voice (Web Speech API, runs in the browser, no server cost) ──────────────

const BCP47 = { Spanish: 'es-ES', English: 'en-US', Catalan: 'ca-ES', French: 'fr-FR',
                Portuguese: 'pt-PT', Italian: 'it-IT', German: 'de-DE' };
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;
let speakEnabled = false, askedByVoice = false, recognizer = null;

function storageGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function storageSet(k, v) { try { localStorage.setItem(k, v); } catch {} }

function plainText(md) {
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')       // links → text
    .replace(/^\s*\|?\s*:?-{3,}.*$/gm, '')          // table separators
    .replace(/\|/g, ', ')
    .replace(/[*_#>`~]/g, '')
    .replace(/✅/g, 'sí').replace(/❌/g, 'no').replace(/🟡/g, 'parcial')
    .replace(/\s+/g, ' ').trim();
}

function speak(text, answerLang) {
  if (!synth) return;
  stopSpeaking();
  const u = new SpeechSynthesisUtterance(plainText(text));
  u.lang = BCP47[answerLang] || navigator.language || 'es-ES';
  const voice = synth.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith(u.lang.slice(0, 2).toLowerCase()));
  if (voice) u.voice = voice;
  u.rate = 1.05;
  synth.speak(u);
}

function stopSpeaking() { if (synth && (synth.speaking || synth.pending)) synth.cancel(); }

function setupVoice() {
  if (synth) {
    speakBtn.hidden = false;
    speakEnabled = storageGet('cvbot-speak') === '1';
    const paint = () => {
      speakBtn.setAttribute('aria-pressed', String(speakEnabled));
      speakBtn.innerHTML = speakEnabled ? '&#128266;' : '&#128264;';
    };
    paint();
    speakBtn.addEventListener('click', () => {
      speakEnabled = !speakEnabled;
      storageSet('cvbot-speak', speakEnabled ? '1' : '0');
      if (!speakEnabled) stopSpeaking();
      paint();
    });
  }
  if (!Recognition) return;
  micBtn.hidden = false;
  micBtn.addEventListener('click', () => {
    if (recognizer) { recognizer.stop(); return; }
    if (busy) return;
    stopSpeaking();
    recognizer = new Recognition();
    recognizer.lang = BCP47[lang] || navigator.language || 'es-ES';
    recognizer.interimResults = true;
    recognizer.maxAlternatives = 1;
    let finalText = '';
    recognizer.onresult = ev => {
      let interim = '';
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript;
      }
      input.value = (finalText + interim).trim(); resize(input);
    };
    recognizer.onerror = ev => {
      if (ev.error === 'not-allowed') alert('Permite el acceso al micrófono para preguntar por voz.');
    };
    recognizer.onend = () => {
      micBtn.classList.remove('listening');
      recognizer = null;
      if (finalText.trim()) { askedByVoice = true; send(); }
    };
    micBtn.classList.add('listening');
    recognizer.start();
  });
}

// ── Groq usage bar ───────────────────────────────────────────────────────────

function paintUsageBar(barEl, pctEl, entry) {
  if (entry.pct === null || entry.pct === undefined) {
    pctEl.textContent = '–'; barEl.style.width = '0%'; return;
  }
  barEl.style.width = entry.pct + '%';
  barEl.style.background = entry.pct > 85 ? '#c0392b' : entry.pct > 60 ? '#e09a3a' : 'var(--accent)';
  pctEl.textContent = Math.round(entry.pct) + '%';
}

async function pollUsage() {
  if (document.hidden) return;  // no point polling a background tab
  try {
    const data = await (await fetch('/usage')).json();
    paintUsageBar($('usage-bar-req'), $('usage-pct-req'), data.requests);
    paintUsageBar($('usage-bar-tok'), $('usage-pct-tok'), data.tokens);
    const reqTxt = data.requests.remaining !== null
      ? `${data.requests.remaining}/${data.requests.limit} requests restantes hoy` : 'sin datos aún';
    const tokTxt = data.tokens.remaining !== null
      ? `${data.tokens.remaining}/${data.tokens.limit} tokens restantes este minuto` : 'sin datos aún';
    usagePanel.title = `${reqTxt} · ${tokTxt}`;
  } catch {}
}

// ── Wiring ───────────────────────────────────────────────────────────────────

$('form').addEventListener('submit', send);
input.addEventListener('input', () => resize(input));
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
$('reset').addEventListener('click', resetChat);
$('export').addEventListener('click', exportConversation);
$('print').addEventListener('click', () => window.print());
jobBtn.addEventListener('click', () => setJobMode(!jobMode));
$('job-cancel').addEventListener('click', () => setJobMode(false));
document.addEventListener('visibilitychange', () => { if (!document.hidden) pollUsage(); });

setupVoice();
pollUsage();
setInterval(pollUsage, 5000);
setChips(DEFAULTS);
input.focus();
