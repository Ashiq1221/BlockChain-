#!/data/data/com.termux/files/usr/bin/bash
# Termux launcher — kills old instances, installs deps, starts full bot
cd "$(dirname "$0")"

echo "🔄 Stopping old Python processes..."
killall -9 python3 python 2>/dev/null; sleep 2

# Wipe stale DB/session lock files (they recreate instantly)
rm -f telegram_agents.db telegram_agents.db-shm telegram_agents.db-wal telegram_agents.db-journal
rm -f tg_memory.db tg_memory.db-shm tg_memory.db-wal tg_memory.db-journal
rm -f aos_memory.db-shm aos_memory.db-wal aos_memory.db-journal
rm -f *.session-shm *.session-wal *.session-journal

# Install deps silently if missing
python3 -c "import pyrogram"   2>/dev/null || pip install -q pyrogram==2.0.106 TgCrypto
python3 -c "import aiohttp"    2>/dev/null || pip install -q aiohttp
python3 -c "import aiosqlite"  2>/dev/null || pip install -q aiosqlite
python3 -c "import dotenv"     2>/dev/null || pip install -q python-dotenv
python3 -c "import rich"       2>/dev/null || pip install -q rich
python3 -c "import httpx"      2>/dev/null || pip install -q httpx
python3 -c "import bs4"        2>/dev/null || pip install -q beautifulsoup4

# If TELEGRAM_SESSION_STRING is missing, generate it now (one-time)
if ! grep -q "TELEGRAM_SESSION_STRING=" .env 2>/dev/null || grep -q "TELEGRAM_SESSION_STRING=$" .env 2>/dev/null; then
    echo ""
    echo "📱 No session string found — generating one now..."
    echo "   (You'll need to enter your OTP — only needed once)"
    echo ""
    python3 generate_session.py
    echo ""
    echo "✅ Session saved to .env — starting bot..."
    sleep 2
fi

echo ""
echo "🚀 Starting Full Autonomous Bot..."
echo "   Send /help to your Telegram bot for commands"
echo "   Send /execute to trigger full pipeline immediately"
echo ""
python3 -u cloud_main.py
