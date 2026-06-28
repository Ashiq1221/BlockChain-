"""Persistent memory — single connection, own DB file, serialised writes."""
import asyncio
import aiosqlite
import os


class Memory:
    def __init__(self, db_path: str = "tg_memory.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self):
        # Remove stale lock files
        for ext in ("-shm", "-wal", "-journal"):
            try:
                os.remove(self.db_path + ext)
            except FileNotFoundError:
                pass
        self._db = await aiosqlite.connect(self.db_path, timeout=30)
        await self._db.execute("PRAGMA journal_mode=DELETE")
        await self._db.execute("PRAGMA busy_timeout=10000")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                type  TEXT,
                key   TEXT UNIQUE,
                value TEXT,
                score REAL DEFAULT 0,
                hits  INTEGER DEFAULT 1,
                ts    TEXT DEFAULT (datetime('now'))
            )""")
        await self._db.commit()

    async def _ensure(self):
        if self._db is None:
            await self.connect()

    async def remember(self, key: str, value: str,
                       memory_type: str = "insight", score: float = 0):
        await self._ensure()
        async with self._lock:
            try:
                await self._db.execute("""
                    INSERT INTO memory (type, key, value, score)
                    VALUES (?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value, score=excluded.score,
                        hits=hits+1, ts=datetime('now')
                """, [memory_type, key, value, score])
                await self._db.commit()
            except Exception:
                pass

    async def recall(self, memory_type: str = None, limit: int = 20) -> list[dict]:
        await self._ensure()
        try:
            if memory_type:
                cur = await self._db.execute(
                    "SELECT * FROM memory WHERE type=? ORDER BY score DESC, hits DESC LIMIT ?",
                    [memory_type, limit])
            else:
                cur = await self._db.execute(
                    "SELECT * FROM memory ORDER BY score DESC, hits DESC LIMIT ?",
                    [limit])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
        except Exception:
            return []

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
        await self._ensure()
        async with self._lock:
            try:
                await self._db.execute(
                    "UPDATE memory SET score=score+? WHERE key=?", [delta, key])
                await self._db.commit()
            except Exception:
                pass

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
