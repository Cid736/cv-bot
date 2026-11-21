"""
Anonymous usage stats and answer feedback, stored in SQLite.

What is stored: the question, the answer, language, mode (chat / job offer),
whether it came from cache or the static fallback, a 👍/👎 rating, and a salted
hash of the session id (to count conversations). No IP addresses, no raw session
ids, no user agent.

On Render's free plan the filesystem is wiped on every deploy/restart, so point
STATS_DB at a persistent disk if you want the history to survive.
"""

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.getenv("STATS_DB", "data/stats.db"))
_SALT = os.getenv("STATS_SALT") or secrets.token_hex(16)
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

# Phrases the assistant uses when the profile doesn't cover a question.
# Used to surface "questions it couldn't answer" in the dashboard.
_NOT_COVERED = (
    "no se especifica", "no especifica", "no figura", "no aparece", "no consta",
    "no se menciona", "no está en el perfil", "no esta en el perfil",
    "not specified", "not mentioned", "not in the profile", "doesn't mention",
    "does not mention", "no information", "not listed", "isn't listed",
    "no s'especifica", "no hi consta",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    ts          REAL NOT NULL,
    conv        TEXT NOT NULL,
    lang        TEXT,
    mode        TEXT,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    source      TEXT,          -- llm | cache | fallback
    not_covered INTEGER DEFAULT 0,
    rating      INTEGER        -- 1 = 👍, -1 = 👎, NULL = no feedback
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def _conv_hash(session_id: str) -> str:
    return hashlib.sha256((_SALT + session_id).encode()).hexdigest()[:16]


def _not_covered(answer: str) -> bool:
    a = answer.lower()
    return any(p in a for p in _NOT_COVERED)


def record(session_id: str, question: str, answer: str, *, lang: str,
           mode: str, source: str) -> str | None:
    """Store one exchange; returns the message id used for feedback."""
    msg_id = secrets.token_hex(8)
    try:
        with _lock:
            db = _db()
            db.execute(
                "INSERT INTO messages (id, ts, conv, lang, mode, question, answer, source, not_covered)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (msg_id, time.time(), _conv_hash(session_id), lang, mode,
                 question[:4000], answer[:6000], source,
                 # job-offer analyses list gaps on purpose; only chat answers count here
                 int(mode == 'chat' and _not_covered(answer))),
            )
            db.commit()
        return msg_id
    except Exception:  # stats must never break the chat (disk full, read-only FS...)
        return None  # stats must never break the chat


def rate(msg_id: str, rating: int) -> bool:
    if rating not in (1, -1, 0):
        return False
    try:
        with _lock:
            db = _db()
            cur = db.execute("UPDATE messages SET rating = ? WHERE id = ?",
                             (rating or None, msg_id))
            db.commit()
            return cur.rowcount == 1
    except Exception:  # stats must never break the chat (disk full, read-only FS...)
        return False


def summary(days: int = 14) -> dict:
    try:
        return _summary(days)
    except Exception:
        return _EMPTY | {"days": days, "error": "Estadísticas no disponibles (no se puede escribir en STATS_DB)"}


_EMPTY = {
    "total_questions": 0, "total_conversations": 0, "recent_questions": 0,
    "recent_conversations": 0, "per_day": [], "languages": [], "modes": [],
    "feedback": {"up": 0, "down": 0}, "top_questions": [], "not_covered": [],
    "disliked": [], "job_offers": [], "recent": [],
}


def _summary(days: int) -> dict:
    since = time.time() - days * 86400
    with _lock:
        db = _db()
        q = lambda sql, *a: db.execute(sql, a).fetchall()
        total = q("SELECT COUNT(*) n, COUNT(DISTINCT conv) c FROM messages")[0]
        recent = q("SELECT COUNT(*) n, COUNT(DISTINCT conv) c FROM messages WHERE ts >= ?", since)[0]
        return {
            "days": days,
            "total_questions": total["n"],
            "total_conversations": total["c"],
            "recent_questions": recent["n"],
            "recent_conversations": recent["c"],
            "per_day": [dict(r) for r in q(
                "SELECT date(ts, 'unixepoch') day, COUNT(*) questions, COUNT(DISTINCT conv) conversations"
                " FROM messages WHERE ts >= ? GROUP BY day ORDER BY day", since)],
            "languages": [dict(r) for r in q(
                "SELECT lang, COUNT(*) n FROM messages WHERE ts >= ? GROUP BY lang ORDER BY n DESC", since)],
            "modes": [dict(r) for r in q(
                "SELECT mode, COUNT(*) n FROM messages WHERE ts >= ? GROUP BY mode ORDER BY n DESC", since)],
            "feedback": dict(q(
                "SELECT SUM(rating = 1) up, SUM(rating = -1) down FROM messages WHERE ts >= ?", since)[0]),
            "top_questions": [dict(r) for r in q(
                "SELECT lower(trim(question)) question, COUNT(*) n FROM messages"
                " WHERE ts >= ? AND mode = 'chat' GROUP BY lower(trim(question))"
                " ORDER BY n DESC LIMIT 15", since)],
            "not_covered": [dict(r) for r in q(
                "SELECT datetime(ts, 'unixepoch') ts, question, answer FROM messages"
                " WHERE not_covered = 1 ORDER BY ts DESC LIMIT 20")],
            "disliked": [dict(r) for r in q(
                "SELECT datetime(ts, 'unixepoch') ts, question, answer FROM messages"
                " WHERE rating = -1 ORDER BY ts DESC LIMIT 20")],
            "job_offers": [dict(r) for r in q(
                "SELECT datetime(ts, 'unixepoch') ts, question, answer FROM messages"
                " WHERE mode = 'job' ORDER BY ts DESC LIMIT 10")],
            "recent": [dict(r) for r in q(
                "SELECT datetime(ts, 'unixepoch') ts, lang, mode, source, rating, question"
                " FROM messages ORDER BY ts DESC LIMIT 30")],
        }
