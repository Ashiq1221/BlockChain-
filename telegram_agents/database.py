import aiosqlite
import json
from datetime import datetime
from telegram_agents.config import Config


class Database:
    def __init__(self):
        self.path = Config.DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.path, timeout=30)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=10000")
        await self._db.commit()
        await self._create_tables()

    async def close(self):
        if self._db:
            await self._db.close()

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id       INTEGER UNIQUE,
                username    TEXT,
                title       TEXT,
                members     INTEGER DEFAULT 0,
                category    TEXT,
                joined      INTEGER DEFAULT 0,
                last_post   TEXT,
                discovered  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id       INTEGER UNIQUE,
                username    TEXT,
                first_name  TEXT,
                last_name   TEXT,
                bio         TEXT,
                tags        TEXT,
                dm_sent     INTEGER DEFAULT 0,
                last_dm     TEXT,
                added       TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT,
                title       TEXT,
                company     TEXT,
                description TEXT,
                url         TEXT,
                applied     INTEGER DEFAULT 0,
                applied_at  TEXT,
                response    TEXT,
                found_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                direction   TEXT,
                peer_id     INTEGER,
                peer_type   TEXT,
                text        TEXT,
                msg_id      INTEGER,
                sent_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent       TEXT,
                goal        TEXT,
                status      TEXT DEFAULT 'pending',
                result      TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS analytics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event       TEXT,
                data        TEXT,
                ts          TEXT DEFAULT (datetime('now'))
            );
        """)
        await self._db.commit()

    # ── Groups ────────────────────────────────────────────────────────

    async def upsert_group(self, tg_id: int, **kwargs):
        cols = ", ".join(["tg_id"] + list(kwargs.keys()))
        placeholders = ", ".join(["?"] * (1 + len(kwargs)))
        updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs)
        await self._db.execute(
            f"INSERT INTO groups ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(tg_id) DO UPDATE SET {updates}",
            [tg_id, *kwargs.values()],
        )
        await self._db.commit()

    async def get_groups(self, category: str | None = None, joined: bool | None = None):
        q, params = "SELECT * FROM groups WHERE 1=1", []
        if category:
            q += " AND category=?"; params.append(category)
        if joined is not None:
            q += " AND joined=?"; params.append(1 if joined else 0)
        async with self._db.execute(q, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ── Contacts ──────────────────────────────────────────────────────

    async def upsert_contact(self, tg_id: int, **kwargs):
        cols = ", ".join(["tg_id"] + list(kwargs.keys()))
        placeholders = ", ".join(["?"] * (1 + len(kwargs)))
        updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs)
        await self._db.execute(
            f"INSERT INTO contacts ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(tg_id) DO UPDATE SET {updates}",
            [tg_id, *kwargs.values()],
        )
        await self._db.commit()

    async def get_contacts(self, tags: str | None = None):
        q, params = "SELECT * FROM contacts WHERE 1=1", []
        if tags:
            q += " AND tags LIKE ?"; params.append(f"%{tags}%")
        async with self._db.execute(q, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ── Jobs ──────────────────────────────────────────────────────────

    async def save_job(self, **kwargs):
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        await self._db.execute(
            f"INSERT OR IGNORE INTO jobs ({cols}) VALUES ({placeholders})",
            list(kwargs.values()),
        )
        await self._db.commit()

    async def get_jobs(self, applied: bool | None = None):
        q, params = "SELECT * FROM jobs WHERE 1=1", []
        if applied is not None:
            q += " AND applied=?"; params.append(1 if applied else 0)
        async with self._db.execute(q, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def mark_job_applied(self, job_id: int, response: str = ""):
        await self._db.execute(
            "UPDATE jobs SET applied=1, applied_at=datetime('now'), response=? WHERE id=?",
            [response, job_id],
        )
        await self._db.commit()

    # ── Messages ──────────────────────────────────────────────────────

    async def log_message(self, direction: str, peer_id: int, peer_type: str, text: str, msg_id: int = 0):
        await self._db.execute(
            "INSERT INTO messages (direction, peer_id, peer_type, text, msg_id) VALUES (?,?,?,?,?)",
            [direction, peer_id, peer_type, text, msg_id],
        )
        await self._db.commit()

    # ── Tasks ─────────────────────────────────────────────────────────

    async def create_task(self, agent: str, goal: str) -> int:
        cur = await self._db.execute(
            "INSERT INTO tasks (agent, goal) VALUES (?,?)", [agent, goal]
        )
        await self._db.commit()
        return cur.lastrowid

    async def update_task(self, task_id: int, status: str, result: str = ""):
        await self._db.execute(
            "UPDATE tasks SET status=?, result=?, updated_at=datetime('now') WHERE id=?",
            [status, result, task_id],
        )
        await self._db.commit()

    async def get_tasks(self, status: str | None = None):
        q, params = "SELECT * FROM tasks WHERE 1=1", []
        if status:
            q += " AND status=?"; params.append(status)
        async with self._db.execute(q, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ── Analytics ─────────────────────────────────────────────────────

    async def log_event(self, event: str, data: dict):
        await self._db.execute(
            "INSERT INTO analytics (event, data) VALUES (?,?)",
            [event, json.dumps(data)],
        )
        await self._db.commit()

    async def get_stats(self) -> dict:
        stats = {}
        for table, col in [("groups", "id"), ("contacts", "id"), ("jobs", "id"), ("messages", "id")]:
            async with self._db.execute(f"SELECT COUNT({col}) FROM {table}") as cur:
                stats[table] = (await cur.fetchone())[0]
        async with self._db.execute("SELECT COUNT(id) FROM jobs WHERE applied=1") as cur:
            stats["jobs_applied"] = (await cur.fetchone())[0]
        async with self._db.execute("SELECT COUNT(id) FROM messages WHERE direction='out'") as cur:
            stats["messages_sent"] = (await cur.fetchone())[0]
        return stats
