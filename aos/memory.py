"""
Layer 10 — Memory System
Short-term: conversation context (last N turns)
Long-term:  user profile, past Q&A, feedback, projects — SQLite FTS5
"""
import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from .config import AOSConfig as C


@dataclass
class MemoryItem:
    id:         int
    category:   str   # "qa", "profile", "project", "feedback", "insight"
    key:        str
    value:      str
    score:      float = 0.0
    timestamp:  float = 0.0


class Memory:
    def __init__(self):
        self._db: sqlite3.Connection | None = None
        self._short_term: list[dict] = []  # [{role, content}]
        self._max_short   = 20

    def connect(self):
        self._db = sqlite3.connect(C.DB_PATH, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA cache_size=10000")
        self._init_schema()

    def _init_schema(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memory (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                category  TEXT    NOT NULL,
                key       TEXT    NOT NULL,
                value     TEXT    NOT NULL,
                score     REAL    DEFAULT 0,
                ts        REAL    DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_memory_cat ON memory(category);
            CREATE INDEX IF NOT EXISTS idx_memory_ts  ON memory(ts);

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                key, value, content=memory, content_rowid=id
            );

            CREATE TABLE IF NOT EXISTS responses (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                question   TEXT,
                answer     TEXT,
                confidence INTEGER,
                ts         REAL DEFAULT (strftime('%s','now')),
                feedback   INTEGER DEFAULT 0  -- 0=none, 1=useful, -1=not useful
            );
        """)
        self._db.commit()

    # ── Short-term (in-memory conversation) ───────────────────────────────────

    def add_turn(self, role: str, content: str):
        self._short_term.append({"role": role, "content": content})
        if len(self._short_term) > self._max_short:
            self._short_term = self._short_term[-self._max_short:]

    def get_context(self, max_turns: int = 6) -> str:
        turns = self._short_term[-max_turns:]
        return "\n".join(f"{t['role'].upper()}: {t['content'][:300]}" for t in turns)

    def clear_short_term(self):
        self._short_term = []

    # ── Long-term (SQLite) ────────────────────────────────────────────────────

    def _commit_with_retry(self, retries: int = 5):
        for i in range(retries):
            try:
                self._db.commit()
                return
            except sqlite3.OperationalError:
                time.sleep(0.2 * (i + 1))
        self._db.rollback()

    def store(self, category: str, key: str, value: str, score: float = 0.0):
        try:
            self._db.execute(
                "INSERT INTO memory (category, key, value, score) VALUES (?,?,?,?)",
                (category, key, value[:2000], score)
            )
            try:
                self._db.execute(
                    "INSERT INTO memory_fts (rowid, key, value) "
                    "VALUES (last_insert_rowid(), ?, ?)", (key, value[:2000])
                )
            except Exception:
                pass
            self._commit_with_retry()
        except Exception:
            pass

    def retrieve(self, query: str, limit: int = 5, category: str = "") -> list[MemoryItem]:
        try:
            if category:
                rows = self._db.execute(
                    "SELECT m.* FROM memory_fts f JOIN memory m ON m.id=f.rowid "
                    "WHERE memory_fts MATCH ? AND m.category=? "
                    "ORDER BY rank LIMIT ?",
                    (query, category, limit)
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT m.* FROM memory_fts f JOIN memory m ON m.id=f.rowid "
                    "WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                    (query, limit)
                ).fetchall()
        except Exception:
            # Fallback: LIKE search
            pat = f"%{query[:50]}%"
            rows = self._db.execute(
                "SELECT * FROM memory WHERE key LIKE ? OR value LIKE ? LIMIT ?",
                (pat, pat, limit)
            ).fetchall()

        return [
            MemoryItem(id=r["id"], category=r["category"], key=r["key"],
                       value=r["value"], score=r["score"], timestamp=r["ts"])
            for r in rows
        ]

    def store_response(self, question: str, answer: str, confidence: int) -> int:
        try:
            cur = self._db.execute(
                "INSERT INTO responses (question, answer, confidence) VALUES (?,?,?)",
                (question[:500], answer[:3000], confidence)
            )
            self._commit_with_retry()
            return cur.lastrowid
        except Exception:
            return 0

    def record_feedback(self, response_id: int, useful: bool):
        try:
            self._db.execute(
                "UPDATE responses SET feedback=? WHERE id=?",
                (1 if useful else -1, response_id)
            )
            self._commit_with_retry()
        except Exception:
            pass
        # Store insight for learning
        val = "positive" if useful else "negative"
        self.store("feedback", f"response_{response_id}", val, 1.0 if useful else -1.0)

    def get_recent_qa(self, limit: int = 3) -> str:
        rows = self._db.execute(
            "SELECT question, answer, confidence FROM responses "
            "ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in rows:
            lines.append(f"Q: {r['question'][:100]}\nA: {r['answer'][:200]}\n({r['confidence']}% confidence)")
        return "\n---\n".join(lines)

    def close(self):
        if self._db:
            self._db.close()
