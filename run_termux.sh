#!/data/data/com.termux/files/usr/bin/bash
# Quick launcher for Termux — kills old instances, installs deps, starts bot.py
cd "$(dirname "$0")"

# Kill ALL python3 processes (the only way to release Pyrogram's session lock)
echo "🔄 Stopping all Python processes..."
killall -9 python3 python 2>/dev/null; sleep 2

# Wipe DB files (recreate automatically)
rm -f telegram_agents.db telegram_agents.db-shm telegram_agents.db-wal telegram_agents.db-journal
rm -f tg_memory.db tg_memory.db-shm tg_memory.db-wal tg_memory.db-journal
rm -f aos_memory.db-shm aos_memory.db-wal aos_memory.db-journal
# Clean Pyrogram session WAL/lock files (NOT the session file itself)
rm -f *.session-shm *.session-wal *.session-journal

python3 -c "import pyrogram" 2>/dev/null || pip install -q pyrogram==2.0.106 TgCrypto
python3 -c "import aiohttp" 2>/dev/null   || pip install -q aiohttp
python3 -c "import aiosqlite" 2>/dev/null || pip install -q aiosqlite
python3 -c "import dotenv" 2>/dev/null    || pip install -q python-dotenv
python3 -c "import rich" 2>/dev/null      || pip install -q rich
python3 -c "import httpx" 2>/dev/null     || pip install -q httpx
python3 -c "import bs4" 2>/dev/null       || pip install -q beautifulsoup4

echo "🧠 Starting AOS Autonomous Bot..."
python3 bot.py
