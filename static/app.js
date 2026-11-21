'use strict';

const $ = id => document.getElementById(id);
const chat = $('chat'), input = $('input'), btn = $('btn'), btnLabel = $('btn-label'), chips = $('chips');
const banner = $('rate-banner'), micBtn = $('mic'), speakBtn = $('speak-toggle');
const tabChat = $('tab-chat'), tabJob = $('tab-job');
const formNote = $('form-note'), hint = $('hint');
const PHOTO = document.querySelector('.as-photo')?.getAttribute('src') || '';

let sid = null;          // server session id
let lang = null;         // language of the last answer (Spanish, English, ...)
let busy = false;
let turn = 0;            // bumped on every question/reset so late suggestions are discarded
let jobMode = false;
const transcript = [];   // [{role, text, mode}] for export

// Same SVG set as icons.py / the Figma file, delivered as JSON in the page.
let ICONS = {};
try { ICONS = JSON.parse($('icons').textContent); } catch {}
function svgIcon(name, size = 16) {
  const span = document.createElement('span');
  span.innerHTML = `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" `
    + `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
  return span.firstChild;
}

// Questions recruiters typically ask first.
const SUGGESTED = [
  '¿Qué experiencia tiene en soporte IT y sistemas?',
  '¿Qué hace en su puesto actual en Infinity Neural?',
  '¿Qué herramientas corporativas ha usado (Intune, ServiceNow, Active Directory)?',
  '¿Qué formación y certificaciones tiene?',
  'What is his level of English?',
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
// The model marks job-offer requirements with ✅ 🟡 ❌; show them as labels.
const FIT = [['✅', 'fit-yes', 'Cumple'], ['🟡', 'fit-mid', 'Parcial'], ['❌', 'fit-no', 'No consta']];
function fitBadges(el) {
  for (const td of el.querySelectorAll('td')) {
    const t = td.textContent.trim();
    const hit = FIT.find(([e]) => t.startsWith(e));
    if (!hit) continue;
    const rest = t.slice(hit[0].length).replace(/^[\s:—-]+/, '');
    const badge = document.createElement('span');
    badge.className = 'fit ' + hit[1]; badge.textContent = hit[2];
    td.replaceChildren(badge);
    if (rest && !/^(direct|directa|relacionad|related|transfer|no )/i.test(rest)) td.append(' ', rest);
  }
}
function renderInto(el, text) {
  if (canRender) { el.innerHTML = DOMPurify.sanitize(marked.parse(text)); fitBadges(el); }
  else el.textContent = text;
}
const narrowLayout = window.matchMedia('(max-width: 980px)');
// Phones/tablets: focusing the textarea pops up the on-screen keyboard and hides the
// answer, so only focus it automatically on devices with a mouse/trackpad.
const touchDevice = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
function focusInput() { if (!touchDevice) input.focus(); }
function scrollDown() {
  if (!narrowLayout.matches) { chat.scrollTop = chat.scrollHeight; return; }
  // Narrow screens scroll the page: keep the newest message just above the pinned composer.
  const last = chat.lastElementChild;
  if (last) last.scrollIntoView({ block: 'end' });
}

function addUserMsg(text, mode) {
  const d = document.createElement('div');
  d.className = 'msg user';
  if (mode === 'job') {
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    sum.textContent = `Oferta de empleo (${text.length} caracteres)`;
    det.append(sum, document.createTextNode(text));
    d.appendChild(det);
  } else {
    d.textContent = text;
  }
  chat.appendChild(d);
  scrollDown();
}

function addBotMsg() {
  const row = document.createElement('div');
  row.className = 'bot-row';
  const av = document.createElement('img');
  av.className = 'bot-avatar'; av.src = PHOTO; av.alt = ''; av.width = 28; av.height = 28;
  const d = document.createElement('div');
  d.className = 'msg bot';
  d.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
  row.append(av, d);
  chat.appendChild(row);
  scrollDown();
  return d;
}

function setChips(list) {
  chips.innerHTML = '';
  list.forEach(q => {
    const el = document.createElement('button');
    el.type = 'button'; el.className = 'chip'; el.textContent = q;
    el.addEventListener('click', () => ask(q));
    chips.appendChild(el);
  });
}

// ── Empty states ─────────────────────────────────────────────────────────────

function showIntro() {
  chat.innerHTML = ''; chips.innerHTML = '';
  const box = document.createElement('div');
  box.className = 'intro';
  if (!jobMode) {
    box.innerHTML = '<h2>¿Qué quieres saber sobre Eric?</h2>'
      + '<p>Pregunta por su experiencia, sus funciones, las herramientas que domina o su formación, en cualquier idioma. '
      + 'Las respuestas salen únicamente de su CV.</p><p class="label">Preguntas frecuentes de reclutadores</p>';
    const grid = document.createElement('div'); grid.className = 'suggestions';
    for (const q of SUGGESTED) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'suggestion';
      const t = document.createElement('span'); t.textContent = q;
      const a = document.createElement('span'); a.className = 'arrow'; a.textContent = '→';
      b.append(t, a);
      b.addEventListener('click', () => ask(q));
      grid.appendChild(b);
    }
    box.appendChild(grid);
    const job = document.createElement('button');
    job.type = 'button'; job.className = 'job-card';
    const ico = document.createElement('span'); ico.className = 'ico'; ico.appendChild(svgIcon('clipboard', 18));
    const txt = document.createElement('span');
    txt.innerHTML = '<strong>¿Tienes una oferta? Comprueba si Eric encaja</strong>'
      + '<small>Pega la descripción del puesto y obtén un análisis requisito a requisito</small>';
    job.append(ico, txt);
    job.addEventListener('click', () => setMode('job'));
    box.appendChild(job);
  } else {
    box.classList.add('job-help');
    box.innerHTML = '<h2>Comprueba el encaje con tu oferta</h2>'
      + '<p>Pega la descripción del puesto y el asistente revisará cada requisito frente al CV de Eric, '
      + 'con sus puntos fuertes, las carencias y una valoración general.</p>'
      + '<ol><li>Copia el texto de la oferta (requisitos, funciones, nivel).</li>'
      + '<li>Pégalo en el cuadro de abajo.</li><li>Pulsa «Analizar encaje».</li></ol>'
      + '<p class="legend"><span class="fit fit-yes">Cumple</span> experiencia directa '
      + '<span class="fit fit-mid">Parcial</span> relacionada <span class="fit fit-no">No consta</span> no figura en el CV</p>';
  }
  chat.appendChild(box);
}
function hideIntro() { const i = chat.querySelector('.intro'); if (i) i.remove(); }

// ── Modes (tabs) ─────────────────────────────────────────────────────────────

function setMode(mode) {
  if (busy) return;
  const toJob = mode === 'job';
  // A pasted offer is longer than a chat question allows: don't silently break the next send.
  if (!toJob && input.value.length > Number(input.dataset.chatMax)) {
    formNote.textContent = 'Este texto es demasiado largo para una pregunta. Analízalo como oferta o acórtalo.';
    formNote.hidden = false;
    return;
  }
  formNote.hidden = true;
  jobMode = toJob;
  tabChat.setAttribute('aria-selected', String(!jobMode));
  tabJob.setAttribute('aria-selected', String(jobMode));
  input.classList.toggle('job', jobMode);
  input.maxLength = Number(jobMode ? input.dataset.jobMax : input.dataset.chatMax);
  input.placeholder = jobMode ? 'Pega aquí la descripción de la oferta…' : 'Escribe tu pregunta sobre Eric…';
  btnLabel.textContent = jobMode ? 'Analizar encaje' : 'Enviar';
  hint.textContent = jobMode ? 'Ctrl+Enter para analizar' : 'Enter para enviar · cualquier idioma';
  if (!transcript.length) showIntro();
  resize(input);
  focusInput();
}

// ── Feedback 👍 / 👎 and copy ────────────────────────────────────────────────

function addFeedback(bubble, messageId, answer) {
  const bar = document.createElement('div');
  bar.className = 'feedback';
  const thanks = document.createElement('span');
  thanks.className = 'thanks';
  let current = 0;
  const mk = (iconName, value, title) => {
    const b = document.createElement('button');
    b.type = 'button'; b.title = title; b.setAttribute('aria-label', title);
    b.appendChild(svgIcon(iconName, 14));
    b.addEventListener('click', async () => {
      current = current === value ? 0 : value;
      bar.querySelectorAll('button[data-rate]').forEach(x => x.classList.remove('on'));
      if (current) b.classList.add('on');
      thanks.textContent = current ? '¡Gracias!' : '';
      try {
        await fetch('/feedback', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message_id: messageId, rating: current }),
        });
      } catch {}
    });
    b.dataset.rate = String(value);
    return b;
  };
  const copy = document.createElement('button');
  copy.type = 'button'; copy.title = 'Copiar respuesta'; copy.setAttribute('aria-label', 'Copiar respuesta');
  copy.appendChild(svgIcon('copy', 14));
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(answer);
      copy.replaceChildren(svgIcon('check', 14)); thanks.textContent = '¡Copiado!';
      setTimeout(() => { copy.replaceChildren(svgIcon('copy', 14)); if (thanks.textContent === '¡Copiado!') thanks.textContent = ''; }, 1500);
    } catch { thanks.textContent = 'No se pudo copiar'; }
  });
  if (messageId) bar.append(mk('thumbs-up', 1, 'Respuesta útil'), mk('thumbs-down', -1, 'Respuesta mejorable'));
  bar.append(copy, thanks);
  bubble.appendChild(bar);
}

// ── Sending & streaming ──────────────────────────────────────────────────────

function resize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, jobMode ? 260 : 140) + 'px';
}

async function ask(q) {
  if (busy) return;
  if (jobMode) setMode('chat');
  input.value = q; resize(input);
  await send();
}

function showRateBanner(resetMsg) {
  banner.textContent = 'El asistente no está disponible en este momento; se muestran respuestas resumidas del perfil. '
    + (resetMsg ? `(${resetMsg})` : '');
  banner.classList.add('visible');
}

async function readStream(res, bubble, onMeta) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', text = '';
  const result = { text: '', messageId: null, error: null };
  let frame = 0;  // pending requestAnimationFrame id (0 = none)
  const paint = () => { frame = 0; renderInto(bubble, text); bubble.classList.add('cursor'); scrollDown(); };
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
      else if (ev.type === 'delta') { text += ev.text; if (!frame) frame = requestAnimationFrame(paint); }
      else if (ev.type === 'done') result.messageId = ev.message_id;
      else if (ev.type === 'error') result.error = ev.message;
    }
  }
  // A repaint still queued from the last delta would overwrite the final render
  // (and the 👍/👎 buttons added right after), so cancel it first.
  if (frame) cancelAnimationFrame(frame);
  bubble.classList.remove('cursor');
  result.text = text.trim();
  if (result.text) renderInto(bubble, result.text);
  return result;
}

async function send(e) {
  if (e) e.preventDefault();
  const q = input.value.trim();
  if (!q || busy) return;
  const mode = jobMode ? 'job' : 'chat';
  busy = true; btn.disabled = true;
  const myTurn = ++turn;
  const viaVoice = askedByVoice; askedByVoice = false;
  stopSpeaking();

  hideIntro(); chips.innerHTML = '';
  if (touchDevice) input.blur();   // close the keyboard so the answer is visible
  addUserMsg(q, mode);
  transcript.push({ role: 'user', text: q, mode });
  input.value = '';
  const bubble = addBotMsg();

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
        if (!answer) { bubble.textContent = r.error; transcript.pop(); }
        else { const p = document.createElement('p'); p.textContent = '⚠ ' + r.error; bubble.appendChild(p); }
      }
    } else {
      const data = await res.json();
      if (data.error) { bubble.textContent = data.error; transcript.pop(); return; }
      sid = data.session_id; lang = data.lang || lang;
      answer = data.answer; messageId = data.message_id; rateLimited = !!data.rate_limited;
      renderInto(bubble, answer);
      if (rateLimited) showRateBanner(data.reset_msg);
    }
    if (!answer) return;
    transcript.push({ role: 'bot', text: answer });
    addFeedback(bubble, messageId, answer);
    scrollDown();
    if (!rateLimited) {
      banner.classList.remove('visible');
      getSuggestions(mode === 'job' ? 'Análisis de encaje con una oferta de empleo' : q, answer, lang, myTurn);
    }
    if (speakEnabled || viaVoice) speak(answer, lang);
  } catch {
    bubble.textContent = 'No se ha podido conectar. Inténtalo de nuevo.';
    if (transcript.length && transcript[transcript.length - 1].role === 'user') transcript.pop();
  } finally {
    busy = false; btn.disabled = false;
    formNote.hidden = true;
    if (mode === 'job') setMode('chat');   // follow-up questions about the offer
    resize(input); focusInput();
  }
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
  banner.classList.remove('visible');
  stopSpeaking();
  input.value = '';
  setMode('chat');
  showIntro();
}

// ── Export ───────────────────────────────────────────────────────────────────

function exportConversation() {
  if (!transcript.length) { alert('Todavía no hay conversación que exportar.'); return; }
  const date = new Date();
  const lines = ['# Conversación sobre el perfil de Eric Cid López', '', `_${date.toLocaleString()} · ${location.origin}_`, ''];
  for (const m of transcript) {
    if (m.role === 'user') lines.push(m.mode === 'job' ? '## Oferta de empleo' : '## Pregunta', '', m.text, '');
    else lines.push('**Respuesta:**', '', m.text, '', '---', '');
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `conversacion-perfil-eric-cid-${date.toISOString().slice(0, 10)}.md`;
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
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s*\|?\s*:?-{3,}.*$/gm, '')
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
      speakBtn.replaceChildren(svgIcon(speakEnabled ? 'volume' : 'volume-off'));
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
    let finalText = '';
    recognizer.onresult = ev => {
      let interim = '';
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript;
      }
      input.value = (finalText + interim).trim(); resize(input);
    };
    recognizer.onerror = ev => { if (ev.error === 'not-allowed') alert('Permite el acceso al micrófono para preguntar por voz.'); };
    recognizer.onend = () => {
      micBtn.classList.remove('listening'); recognizer = null;
      if (finalText.trim()) { askedByVoice = true; send(); }
    };
    micBtn.classList.add('listening');
    recognizer.start();
  });
}

// ── Full profile dialog ──────────────────────────────────────────────────────

function setupProfileDialog() {
  const dlg = $('profile-dialog');
  if (!dlg || typeof dlg.showModal !== 'function') return;
  $('open-profile').addEventListener('click', () => dlg.showModal());
  $('close-profile').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });  // click on the backdrop
}

// ── Light / dark theme ───────────────────────────────────────────────────────

function setupTheme() {
  const btnTheme = $('theme-toggle');
  if (!btnTheme) return;
  const dark = () => document.documentElement.dataset.theme === 'dark'
    || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  btnTheme.addEventListener('click', () => {
    const next = dark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    storageSet('cvbot-theme', next);
  });
}

// ── Wiring ───────────────────────────────────────────────────────────────────

$('form').addEventListener('submit', send);
input.addEventListener('input', () => resize(input));
input.addEventListener('keydown', e => {
  // In job mode Enter adds lines (pasted offers); Ctrl/Cmd+Enter sends.
  if (e.key === 'Enter' && !e.shiftKey && (!jobMode || e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
});
tabChat.addEventListener('click', () => setMode('chat'));
tabJob.addEventListener('click', () => setMode('job'));
$('reset').addEventListener('click', resetChat);
$('export').addEventListener('click', exportConversation);
$('print').addEventListener('click', () => window.print());

setupVoice();
setupProfileDialog();
setupTheme();
showIntro();
