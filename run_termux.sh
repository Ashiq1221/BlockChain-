#!/data/data/com.termux/files/usr/bin/bash
# Quick launcher for Termux — installs deps if missing, then starts bot.py
cd "$(dirname "$0")"

python3 -c "import pyrogram" 2>/dev/null || pip install -q pyrogram==2.0.106 TgCrypto
python3 -c "import aiohttp" 2>/dev/null   || pip install -q aiohttp
python3 -c "import aiosqlite" 2>/dev/null || pip install -q aiosqlite
python3 -c "import dotenv" 2>/dev/null    || pip install -q python-dotenv
python3 -c "import rich" 2>/dev/null      || pip install -q rich
python3 -c "import httpx" 2>/dev/null     || pip install -q httpx
python3 -c "import bs4" 2>/dev/null       || pip install -q beautifulsoup4

echo "🧠 Starting AOS Autonomous Bot..."
python3 bot.py
