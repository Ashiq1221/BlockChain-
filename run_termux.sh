#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")"

echo "🛑 Stopping old agent..."
if [ -f .bot.pid ]; then
    kill -9 $(cat .bot.pid) 2>/dev/null
    rm -f .bot.pid
fi
pkill -9 -f "job_agent.py" 2>/dev/null
pkill -9 -f "bot.py"       2>/dev/null
pkill -9 -f "python3"      2>/dev/null
pkill -9 -f "python"       2>/dev/null
sleep 3

rm -f *.session-shm *.session-wal *.session-journal

echo "📦 Checking deps..."
python3 -c "import httpx"     2>/dev/null || pip install -q httpx
python3 -c "import dotenv"    2>/dev/null || pip install -q python-dotenv
python3 -c "import rich"      2>/dev/null || pip install -q rich
python3 -c "import aiosqlite" 2>/dev/null || pip install -q aiosqlite
python3 -c "import bs4"       2>/dev/null || pip install -q beautifulsoup4
python3 -c "import pyrogram"  2>/dev/null || pip install -q pyrogram==2.0.106 TgCrypto

echo "🤖 Starting Job Agent..."
python3 job_agent.py &
echo $! > .bot.pid
wait
rm -f .bot.pid
