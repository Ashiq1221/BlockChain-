#!/data/data/com.termux/files/usr/bin/bash
# Quick launcher for Termux — kills old instances, installs deps, starts bot.py
cd "$(dirname "$0")"

# Kill any previous bot instances (exclude self)
echo "🔄 Stopping any previous bot instances..."
pgrep -f "python.*bot.py" | grep -v $$ | xargs kill -15 2>/dev/null; sleep 1

# Remove ALL stale SQLite lock files (DB recreates itself on start)
rm -f telegram_agents.db-shm telegram_agents.db-wal telegram_agents.db-journal
rm -f tg_memory.db-shm tg_memory.db-wal tg_memory.db-journal
rm -f aos_memory.db-shm aos_memory.db-wal aos_memory.db-journal
# If DB is stuck locked, wipe it — data recreates automatically
python3 -c "
import sqlite3, os
for db in ['telegram_agents.db', 'aos_memory.db']:
    if os.path.exists(db):
        try:
            sqlite3.connect(db, timeout=2).execute('SELECT 1').fetchone()
        except:
            os.remove(db)
            print(f'Removed stuck DB: {db}')
" 2>/dev/null

python3 -c "import pyrogram" 2>/dev/null || pip install -q pyrogram==2.0.106 TgCrypto
python3 -c "import aiohttp" 2>/dev/null   || pip install -q aiohttp
python3 -c "import aiosqlite" 2>/dev/null || pip install -q aiosqlite
python3 -c "import dotenv" 2>/dev/null    || pip install -q python-dotenv
python3 -c "import rich" 2>/dev/null      || pip install -q rich
python3 -c "import httpx" 2>/dev/null     || pip install -q httpx
python3 -c "import bs4" 2>/dev/null       || pip install -q beautifulsoup4

echo "🧠 Starting AOS Autonomous Bot..."
python3 bot.py
