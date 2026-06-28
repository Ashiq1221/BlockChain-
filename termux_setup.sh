#!/data/data/com.termux/files/usr/bin/bash
# ── AOS Termux Setup Script ────────────────────────────────────────────────────
# Run this once on your Android (Termux) to set up the full autonomous AI bot.
# Usage: bash termux_setup.sh

set -e

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   🧠 AOS Autonomous Bot — Termux Setup               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ─────────────────────────────────────────────────────────
echo "📦 Installing system packages..."
pkg update -y -q
pkg install -y -q python git libffi openssl

# ── 2. Python packages ─────────────────────────────────────────────────────────
echo "🐍 Installing Python packages..."
pip install --quiet --upgrade pip
pip install --quiet \
    pyrogram==2.0.106 \
    TgCrypto \
    aiohttp \
    aiosqlite \
    python-dotenv \
    rich \
    httpx \
    beautifulsoup4 \
    aiofiles

echo "✅ All packages installed."
echo ""

# ── 3. Clone / update repo ─────────────────────────────────────────────────────
REPO_DIR="$HOME/BlockChain-"

if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Repo already exists — pulling latest..."
    cd "$REPO_DIR"
    git pull origin claude/telegram-automation-agent-j755h9 --quiet
else
    echo "📥 Cloning repository..."
    git clone https://github.com/ashiq1221/blockchain- "$REPO_DIR" --branch claude/telegram-automation-agent-j755h9 --quiet
    cd "$REPO_DIR"
fi

# ── 4. Create .env if missing ──────────────────────────────────────────────────
ENV_FILE="$REPO_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "⚙️  Creating .env file — enter your credentials:"
    echo ""

    read -p "  Telegram API ID     : " API_ID
    read -p "  Telegram API Hash   : " API_HASH
    read -p "  Telegram Phone (+91): " PHONE
    read -p "  Bot Token (BotFather): " BOT_TOKEN
    read -p "  Your Telegram ID    : " OWNER_ID
    read -p "  Anthropic API Key   : " ANTHROPIC_KEY

    cat > "$ENV_FILE" << EOF
# Telegram API
TELEGRAM_API_ID=$API_ID
TELEGRAM_API_HASH=$API_HASH
TELEGRAM_PHONE=$PHONE
TELEGRAM_SESSION_NAME=my_session

# Telegram Bot
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_OWNER_ID=$OWNER_ID

# AI Providers
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
GROQ_API_KEY=
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
XAI_API_KEY=

# Agent settings
AGENT_LANGUAGE=en
MAX_DM_PER_HOUR=10
MAX_GROUP_POSTS_PER_HOUR=5
RATE_LIMIT_SLEEP=3
AUTO_RESPOND=true
EOF
    echo ""
    echo "✅ .env created."
else
    echo "✅ .env already exists."
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅ SETUP COMPLETE — Ready to launch!               ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
echo "║  To start the FULL autonomous bot:                   ║"
echo "║    cd ~/BlockChain-                                  ║"
echo "║    python bot.py                                     ║"
echo "║                                                      ║"
echo "║  (Enter OTP when prompted on first run)              ║"
echo "║                                                      ║"
echo "║  To start AOS-only bot (no user account needed):     ║"
echo "║    python aos_bot.py                                 ║"
echo "║                                                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
