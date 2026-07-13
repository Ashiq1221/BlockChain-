import aiosqlite
import asyncio
import json
import os
from datetime import datetime
from telegram_agents.config import Config


class Database:
    def __init__(self):
        self.path = Config.DB_PATH
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()   # serialise all writes

    async def connect(self):
        await self._open_with_retry()
        await self._create_tables()

    async def _open_with_retry(self):
        """Open SQLite — wait up to 15 s, then nuke and recreate."""
        for attempt in range(2):
            try:
                self._db = await aiosqlite.connect(self.path, timeout=15)
                self._db.row_factory = aiosqlite.Row
                await self._db.execute("PRAGMA busy_timeout=30000")
                await self._db.execute("PRAGMA synchronous=NORMAL")
                await self._db.commit()
                return
            except Exception:
                if self._db:
                    try:
                        await self._db.close()
                    except Exception:
                        pass
                    self._db = None
                # Nuke everything and start fresh
                for ext in ("", "-journal", "-wal", "-shm"):
                    try:
                        os.remove(self.path + ext)
                    except FileNotFoundError:
                        pass
                await asyncio.sleep(1)

    async def close(self):
        if self._db:
            await self._db.close()

    async def _create_tables(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE,
                username TEXT, title TEXT, members INTEGER DEFAULT 0,
                category TEXT, joined INTEGER DEFAULT 0, last_post TEXT,
                discovered TEXT DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE,
                username TEXT, first_name TEXT, last_name TEXT, bio TEXT,
                tags TEXT, dm_sent INTEGER DEFAULT 0, last_dm TEXT,
                added TEXT DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, title TEXT,
                company TEXT, description TEXT, url TEXT,
                applied INTEGER DEFAULT 0, applied_at TEXT, response TEXT,
                found_at TEXT DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, direction TEXT,
                peer_id INTEGER, peer_type TEXT, text TEXT, msg_id INTEGER,
                sent_at TEXT DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, goal TEXT,
                status TEXT DEFAULT 'pending', result TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')))""",
            """CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT, data TEXT,
                ts TEXT DEFAULT (datetime('now')))""",
        ]
        for sql in tables:
            await self._db.execute(sql)
        await self._db.commit()

    # ── Groups ────────────────────────────────────────────────────────

    async def _exec(self, sql: str, params=None, retries: int = 5):
        """Serialised write with retry — only one write at a time."""
        async with self._lock:
            for i in range(retries):
                try:
                    if params is None:
                        await self._db.execute(sql)
                    else:
                        await self._db.execute(sql, params)
                    await self._db.commit()
                    return
                except Exception as e:
                    if "locked" in str(e).lower() and i < retries - 1:
                        await asyncio.sleep(0.4 * (i + 1))
                    else:
                        return  # swallow — don't crash the brain over a log entry

    async def upsert_group(self, tg_id: int, **kwargs):
        cols = ", ".join(["tg_id"] + list(kwargs.keys()))
        placeholders = ", ".join(["?"] * (1 + len(kwargs)))
        updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs)
        await self._exec(
            f"INSERT INTO groups ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(tg_id) DO UPDATE SET {updates}",
            [tg_id, *kwargs.values()],
        )

    async def _query(self, sql: str, params=None) -> list:
        """Serialised read — shares the same lock as writes."""
        async with self._lock:
            async with self._db.execute(sql, params or []) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def _query_one(self, sql: str, params=None):
        async with self._lock:
            async with self._db.execute(sql, params or []) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def get_groups(self, category: str | None = None, joined: bool | None = None):
        q, params = "SELECT * FROM groups WHERE 1=1", []
        if category:
            q += " AND category=?"; params.append(category)
        if joined is not None:
            q += " AND joined=?"; params.append(1 if joined else 0)
        return await self._query(q, params)

    # ── Contacts ──────────────────────────────────────────────────────

    async def upsert_contact(self, tg_id: int, **kwargs):
        cols = ", ".join(["tg_id"] + list(kwargs.keys()))
        placeholders = ", ".join(["?"] * (1 + len(kwargs)))
        updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs)
        await self._exec(
            f"INSERT INTO contacts ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(tg_id) DO UPDATE SET {updates}",
            [tg_id, *kwargs.values()],
        )

    async def get_contacts(self, tags: str | None = None):
        q, params = "SELECT * FROM contacts WHERE 1=1", []
        if tags:
            q += " AND tags LIKE ?"; params.append(f"%{tags}%")
        return await self._query(q, params)

    # ── Jobs ──────────────────────────────────────────────────────────

    async def save_job(self, **kwargs):
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        await self._exec(
            f"INSERT OR IGNORE INTO jobs ({cols}) VALUES ({placeholders})",
            list(kwargs.values()),
        )

    async def get_jobs(self, applied: bool | None = None):
        q, params = "SELECT * FROM jobs WHERE 1=1", []
        if applied is not None:
            q += " AND applied=?"; params.append(1 if applied else 0)
        return await self._query(q, params)

    async def mark_job_applied(self, job_id: int, response: str = ""):
        await self._exec(
            "UPDATE jobs SET applied=1, applied_at=datetime('now'), response=? WHERE id=?",
            [response, job_id],
        )

    # ── Messages ──────────────────────────────────────────────────────

    async def log_message(self, direction: str, peer_id: int, peer_type: str, text: str, msg_id: int = 0):
        await self._exec(
            "INSERT INTO messages (direction, peer_id, peer_type, text, msg_id) VALUES (?,?,?,?,?)",
            [direction, peer_id, peer_type, text, msg_id],
        )

    # ── Tasks ─────────────────────────────────────────────────────────

    async def create_task(self, agent: str, goal: str) -> int:
        async with self._lock:
            for i in range(5):
                try:
                    cur = await self._db.execute(
                        "INSERT INTO tasks (agent, goal) VALUES (?,?)", [agent, goal]
                    )
                    await self._db.commit()
                    return cur.lastrowid
                except Exception as e:
                    if "locked" in str(e).lower() and i < 4:
                        await asyncio.sleep(0.4 * (i + 1))
                    else:
                        return 0
        return 0

    async def update_task(self, task_id: int, status: str, result: str = ""):
        await self._exec(
            "UPDATE tasks SET status=?, result=?, updated_at=datetime('now') WHERE id=?",
            [status, result, task_id],
        )

    async def get_tasks(self, status: str | None = None):
        q, params = "SELECT * FROM tasks WHERE 1=1", []
        if status:
            q += " AND status=?"; params.append(status)
        return await self._query(q, params)

    # ── Analytics ─────────────────────────────────────────────────────

    async def log_event(self, event: str, data: dict):
        await self._exec(
            "INSERT INTO analytics (event, data) VALUES (?,?)",
            [event, json.dumps(data)],
        )

    async def get_stats(self) -> dict:
        stats = {}
        for table in ("groups", "contacts", "jobs", "messages"):
            stats[table] = await self._query_one(f"SELECT COUNT(id) FROM {table}") or 0
        stats["jobs_applied"]  = await self._query_one("SELECT COUNT(id) FROM jobs WHERE applied=1") or 0
        stats["messages_sent"] = await self._query_one("SELECT COUNT(id) FROM messages WHERE direction='out'") or 0
        return stats
