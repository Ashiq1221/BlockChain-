#!/data/data/com.termux/files/usr/bin/bash
# ── Solana Meme Trading Bot — Termux launcher ─────────────────────────────────
# One command to set up and run the bot 24/7 on your Android phone.
#
#   bash solbot_termux.sh          # setup (first run) + start in background
#   bash solbot_termux.sh status   # portfolio + PnL
#   bash solbot_termux.sh log      # follow the live log
#   bash solbot_termux.sh scan     # one-off market scan
#   bash solbot_termux.sh stop     # stop the bot
#
# Paper trading by default. For live trading, edit ~/BlockChain-/.env
# (SOLBOT_LIVE=true + SOLBOT_PRIVATE_KEY) — see README "Going live".

set -e
REPO_DIR="$HOME/BlockChain-"
BRANCH="claude/sol-meme-trading-bot-k7bufm"
LOG="$REPO_DIR/solbot.log"
PIDFILE="$REPO_DIR/solbot.pid"

case "${1:-start}" in
  stop)
    if [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; then
        rm -f "$PIDFILE"; termux-wake-unlock 2>/dev/null || true
        echo "🛑 solbot stopped."
    else
        pkill -f "sol_meme_bot.py run" 2>/dev/null && echo "🛑 solbot stopped." \
            || echo "solbot is not running."
        rm -f "$PIDFILE"
    fi
    exit 0 ;;
  status)  cd "$REPO_DIR" && exec python3 sol_meme_bot.py status ;;
  scan)    cd "$REPO_DIR" && exec python3 sol_meme_bot.py scan ;;
  log)     exec tail -f "$LOG" ;;
esac

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   🤖 Solana Meme Trading Bot — Termux Setup          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "📦 Checking system packages..."
command -v python3 > /dev/null || pkg install -y -q python
command -v git     > /dev/null || pkg install -y -q git
pkg install -y -q libffi openssl termux-api 2>/dev/null || true

# ── 2. Clone / update repo ────────────────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Updating repo..."
    git -C "$REPO_DIR" fetch origin "$BRANCH" --quiet
    git -C "$REPO_DIR" checkout "$BRANCH" --quiet
    git -C "$REPO_DIR" pull origin "$BRANCH" --quiet
else
    echo "📥 Cloning repository..."
    git clone --branch "$BRANCH" --quiet https://github.com/ashiq1221/blockchain- "$REPO_DIR"
fi
cd "$REPO_DIR"

# ── 3. Python deps (solbot needs only these — skips the heavy repo-wide list) ─
echo "🐍 Checking Python packages..."
python3 -c "import httpx"  2>/dev/null || pip install -q httpx
python3 -c "import dotenv" 2>/dev/null || pip install -q python-dotenv
python3 -c "import rich"   2>/dev/null || pip install -q rich
python3 -c "import anthropic" 2>/dev/null || pip install -q anthropic

# solders (transaction signing) is only needed for LIVE trading. It's a Rust
# package with no Android wheels — building it needs the rust toolchain.
if grep -q "^SOLBOT_LIVE=true" .env 2>/dev/null; then
    if ! python3 -c "import solders" 2>/dev/null; then
        echo "🦀 Live mode: building solders (one-time, can take 15-30 min)..."
        pkg install -y -q rust binutils
        pip install solders
    fi
fi

# ── 4. Create .env on first run ───────────────────────────────────────────────
if [ ! -f .env ]; then
    echo ""
    echo "⚙️  First-time setup (paper trading — no wallet needed):"
    echo ""
    read -p "  Anthropic API key (Enter to skip AI analyst): " ANTHROPIC_KEY
    read -p "  Telegram bot token (Enter to skip alerts)   : " TG_TOKEN
    TG_CHAT=""
    [ -n "$TG_TOKEN" ] && read -p "  Telegram chat ID                            : " TG_CHAT

    cat > .env << EOF
# ── Solana meme trading bot ──────────────────────────────
# Paper trading. To go LIVE: set SOLBOT_LIVE=true, add your
# burner wallet key below, and use a paid RPC (Helius free tier works).
SOLBOT_LIVE=false
SOLBOT_PRIVATE_KEY=
SOLBOT_RPC_URL=https://api.mainnet-beta.solana.com
SOLBOT_BUY_AMOUNT_SOL=0.05
SOLBOT_MAX_POSITIONS=5
SOLBOT_MAX_DAILY_BUYS=20

# AI analyst (Claude reviews every trade)
ANTHROPIC_API_KEY=$ANTHROPIC_KEY

# Telegram trade alerts
SOLBOT_TG_BOT_TOKEN=$TG_TOKEN
SOLBOT_TG_CHAT_ID=$TG_CHAT
EOF
    chmod 600 .env
    echo ""
    echo "✅ .env created (permissions locked to you)."
fi

# ── 5. Start in background with a wake lock ───────────────────────────────────
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "✅ solbot is already running (pid $(cat "$PIDFILE"))."
else
    termux-wake-lock 2>/dev/null || true
    nohup python3 -u sol_meme_bot.py run >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "🚀 solbot started (pid $(cat "$PIDFILE"))."
    else
        echo "❌ solbot failed to start — last log lines:"; tail -5 "$LOG"; exit 1
    fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Useful commands:                                    ║"
echo "║    bash solbot_termux.sh status   portfolio + PnL    ║"
echo "║    bash solbot_termux.sh log      follow live log    ║"
echo "║    bash solbot_termux.sh stop     stop the bot       ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  📱 IMPORTANT: disable battery optimization for      ║"
echo "║  Termux (Android Settings → Apps → Termux → Battery  ║"
echo "║  → Unrestricted) or Android will kill the bot.       ║"
echo "╚══════════════════════════════════════════════════════╝"
