"""Persistent memory system — the agent remembers what works."""
import json
import aiosqlite
from telegram_agents.config import Config


class Memory:
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path

    async def _db(self):
        db = await aiosqlite.connect(self.db_path)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                type      TEXT,
                key       TEXT UNIQUE,
                value     TEXT,
                score     REAL DEFAULT 0,
                hits      INTEGER DEFAULT 1,
                ts        TEXT DEFAULT (datetime('now'))
            )""")
        await db.commit()
        return db

    async def remember(self, key: str, value: str, memory_type: str = "insight", score: float = 0):
        db = await self._db()
        await db.execute("""
            INSERT INTO memory (type, key, value, score)
            VALUES (?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                score=excluded.score,
                hits=hits+1,
                ts=datetime('now')
        """, [memory_type, key, value, score])
        await db.commit()
        await db.close()

    async def recall(self, memory_type: str = None, limit: int = 20) -> list[dict]:
        db = await self._db()
        if memory_type:
            cur = await db.execute(
                "SELECT * FROM memory WHERE type=? ORDER BY score DESC, hits DESC LIMIT ?",
                [memory_type, limit])
        else:
            cur = await db.execute(
                "SELECT * FROM memory ORDER BY score DESC, hits DESC LIMIT ?", [limit])
        rows = [dict(zip([d[0] for d in cur.description], r)) for r in await cur.fetchall()]
        await db.close()
        return rows

    async def best_strategies(self) -> str:
        rows = await self.recall("strategy", limit=10)
        if not rows:
            return "No strategies learned yet."
        return "\n".join(f"- [{r['score']:+.1f}] {r['key']}: {r['value']}" for r in rows)

    async def best_messages(self) -> str:
        rows = await self.recall("message", limit=5)
        if not rows:
            return "No message templates learned yet."
        return "\n".join(f"- [{r['score']:+.1f}] {r['value']}" for r in rows)

    async def update_score(self, key: str, delta: float):
        db = await self._db()
        await db.execute("UPDATE memory SET score=score+? WHERE key=?", [delta, key])
        await db.commit()
        await db.close()
