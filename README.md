# Telegram Autonomous AI Agent System

10 specialized AI agents, all powered by Claude, that autonomously manage your Telegram account — finding groups, hunting jobs, sending DMs, posting content, building your network, and more.

---

## Agent Roster

| # | Agent | Mission |
|---|-------|---------|
| 1 | **Commander** | Master orchestrator — interprets your natural-language goals and delegates to other agents |
| 2 | **GroupDiscovery** | Searches the web + Telegram to find and join relevant groups |
| 3 | **JobHunter** | Scans groups for job posts, crafts personalized applications, sends them |
| 4 | **DMAgent** | Runs targeted DM campaigns with AI-personalized messages |
| 5 | **ContentAgent** | Generates and posts content in groups, adapts tone per group category |
| 6 | **NetworkAgent** | Harvests contacts from groups, tags by relevance |
| 7 | **MonitorAgent** | Watches groups in real-time for keywords, opportunities, mentions |
| 8 | **ResponderAgent** | Auto-replies to incoming DMs and group mentions intelligently |
| 9 | **AnalyticsAgent** | Tracks all metrics, prints dashboards, generates AI insights |
| 10 | **StrategyAgent** | Plans multi-week campaigns, generates daily briefings |

---

## Setup

### 1. Get Telegram API credentials

Go to [my.telegram.org/apps](https://my.telegram.org/apps), create an app, and copy your `api_id` and `api_hash`.

### 2. Get Anthropic API key

Sign up at [console.anthropic.com](https://console.anthropic.com) and create an API key.

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. First run (authenticate Telegram session)

```bash
python main.py --agent analytics
```

On first run, Pyrogram will ask for your phone number and verification code. After that, a `.session` file is saved and you never need to authenticate again.

---

## Usage

### Natural language (Commander handles everything)

```bash
python main.py --goal "find blockchain developer jobs and apply to them"
python main.py --goal "join Python communities and post about my freelance services"
python main.py --goal "find hiring managers and DM them my portfolio"
```

### Individual agents

```bash
# Discover and join relevant groups
python main.py --agent group_discovery --topics "python,blockchain,remote jobs"

# Hunt jobs and apply
python main.py --agent job_hunter --goal "find remote backend developer jobs"

# DM campaign
python main.py --agent dm --goal "introduce myself as a blockchain developer" --max-send 20

# Post content in joined groups
python main.py --agent content --topic "Available for freelance blockchain development"

# Build contact database from groups
python main.py --agent network

# Monitor for keywords (10 minutes)
python main.py --agent monitor --keywords "hiring,looking for developer,remote" --duration 600

# Auto-respond to all incoming DMs (1 hour)
python main.py --agent responder --duration 3600

# Analytics dashboard + AI insights
python main.py --agent analytics

# Generate 2-week strategy
python main.py --agent strategy --goal "land a remote Python job"

# Morning briefing
python main.py --agent brief

# Full pipeline (discover → network → hunt jobs → analytics)
python main.py --agent full --goal "find and apply to remote blockchain jobs"
```

### Dry run (no messages sent)

```bash
python main.py --agent job_hunter --dry-run
```

---

## Configuration (`.env`)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_API_ID` | From my.telegram.org/apps |
| `TELEGRAM_API_HASH` | From my.telegram.org/apps |
| `TELEGRAM_PHONE` | Your phone with country code (+1234567890) |
| `TELEGRAM_SESSION_NAME` | Session file name (default: tg_agent_session) |
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `AGENT_PERSONA` | How agents should sound (default: professional) |
| `MAX_DM_PER_HOUR` | Rate limit for DMs (default: 10) |
| `MAX_GROUP_POSTS_PER_HOUR` | Rate limit for posts (default: 5) |
| `RATE_LIMIT_SLEEP` | Seconds between Telegram actions (default: 3) |
| `AUTO_RESPOND` | Enable auto-DM responses (default: true) |
| `JOB_KEYWORDS` | Comma-separated job keywords |
| `SERPAPI_KEY` | Optional: SerpAPI key for enhanced web search |

---

## Architecture

```
telegram_agents/
├── config.py           — All configuration from .env
├── database.py         — SQLite persistence (groups, contacts, jobs, messages, tasks)
├── base_agent.py       — Abstract base shared by all agents
├── agents/
│   ├── commander.py        — Agent 1: Orchestrator
│   ├── group_discovery.py  — Agent 2: Group finder
│   ├── job_hunter.py       — Agent 3: Job applicant
│   ├── dm_agent.py         — Agent 4: DM campaigner
│   ├── content_agent.py    — Agent 5: Content publisher
│   ├── network_agent.py    — Agent 6: Contact harvester
│   ├── monitor_agent.py    — Agent 7: Real-time watcher
│   ├── responder_agent.py  — Agent 8: Auto-responder
│   ├── analytics_agent.py  — Agent 9: Metrics + insights
│   └── strategy_agent.py   — Agent 10: Long-term planner
└── tools/
    ├── telegram_tools.py   — Pyrogram API wrappers
    ├── web_tools.py        — Web search + scraping
    └── ai_tools.py         — Claude AI integration
```

All state persists in `telegram_agents.db` (SQLite) — survives restarts.

---

## Important Notes

- **Rate limiting**: The system respects Telegram's limits. Default: 3s between actions, max 10 DMs/hour.
- **Anti-spam**: Never spam. The AI personalizes every message. Use responsibly.
- **Session file**: Keep your `.session` file private — it grants full account access.
- **Flood protection**: Pyrogram auto-handles `FloodWait` errors with backoff.

## 🎼 Apply Pilot — Job-Application Agent Orchestra

Share a job link, get hired. A self-learning multi-agent pipeline built on the
AOS debate engine + Cloudflare Workers AI (runs even with only CF credentials).

**Pipeline:** fetch posting → 3-agent structured debate (Recruiter / skeptical
Hiring Manager / Career Strategist) → Moderator decision (APPLY/SKIP + fit
score + ATS keywords) → tailored cover letter & screener answers → Playwright
form autofill with resume upload → screenshot review → optional submit →
outcome logged to SQLite + CF Vectorize episodic memory (each application
teaches the next one).

```bash
python apply.py <job_url>              # evaluate + dry-run fill (screenshots)
python apply.py <job_url> --submit     # actually submit
python apply.py --report               # application history
python apply.py --status <url> interview   # record outcomes → self-learning
```

**Telegram:** send `/apply <link>` to the AOS bot — or just paste a job link.
**CI:** add links to `job_links.txt` → Actions → "Submit Applications".

Safety: dry-run by default (`APPLY_AUTO_SUBMIT=false`), never bypasses
CAPTCHAs, and the AI is forbidden from inventing facts — unknown fields are
left blank. Personal defaults (name, phone, salary) live in `.env`
(`APPLY_*` vars); the resume ships in `apply_agent/data/`.

---

## Solana Meme-Coin Trading Bot (`sol_meme_bot.py`)

Autonomous meme-coin trader for Solana: discovers fresh tokens via
DexScreener, runs rug-safety checks on-chain, buys through the Jupiter
aggregator, and manages exits with take-profit / stop-loss / trailing-stop
rules. **Paper trading by default** — no wallet needed to try it.

```
DexScreener (profiles + boosts)          Solana RPC                 Claude AI          Jupiter
   └─ candidate mints ──▶ market filters ──▶ mint/holder checks ──▶ AI analyst ──▶ swap
        liquidity, volume,      mint & freeze authority renounced,   structured buy/skip
        txns, momentum, age     top-10 holder concentration          verdict + sizing
```

### Quick start

```bash
pip install -r requirements.txt
python sol_meme_bot.py scan      # one-off: see which tokens pass filters right now
python sol_meme_bot.py run      # start the loop (paper mode — simulated fills)
python sol_meme_bot.py status   # portfolio + realized PnL
```

### Going live

1. Create a **dedicated burner wallet** and fund it with only what you can
   afford to lose entirely.
2. In `.env`: set `SOLBOT_LIVE=true` and `SOLBOT_PRIVATE_KEY=<base58 key>`
   (Phantom → Settings → Export Private Key).
3. Use a paid RPC (Helius/QuickNode/Triton) via `SOLBOT_RPC_URL` — the public
   mainnet endpoint rate-limits aggressively.
4. `python sol_meme_bot.py run`

Manual controls: `python sol_meme_bot.py sell <mint>` and
`python sol_meme_bot.py close-all`.

### Strategy knobs (`.env`, all `SOLBOT_*`)

| Setting | Default | Meaning |
|---|---|---|
| `BUY_AMOUNT_SOL` | 0.05 | SOL per entry |
| `MAX_POSITIONS` / `MAX_DAILY_BUYS` | 5 / 20 | exposure caps |
| `TAKE_PROFIT_PCT` / `STOP_LOSS_PCT` | 60 / 25 | hard exits vs entry |
| `TRAILING_STOP_PCT` | 20 | from peak, arms at +TP/2 |
| `MAX_HOLD_MINUTES` | 240 | timeout exit |
| `MIN_LIQUIDITY_USD` / `MIN_VOLUME_H1_USD` | 20k / 10k | entry filters |
| `MIN_PAIR_AGE_MINUTES` / `MAX_PAIR_AGE_HOURS` | 30 / 48 | freshness window |
| `MAX_TOP10_HOLDER_PCT` | 40 | holder-concentration rug filter |
| `SLIPPAGE_BPS` | 300 | swap slippage (3%) |

Safety checks before every buy: mint authority renounced, freeze authority
renounced, top-10 holder concentration, minimum liquidity/volume/txns,
buy/sell ratio, momentum band (skips vertical pumps), and a minimum pair age
to dodge instant rugs. Positions whose pair disappears from DexScreener are
marked closed as suspected rugs.

### AI analyst (Claude)

When `ANTHROPIC_API_KEY` is set, every candidate that passes the mechanical
filters is also reviewed by Claude before the bot buys. The model receives
the full market picture (liquidity, volume, buy/sell dynamics, momentum,
pair age, holder concentration) and returns a structured verdict:
`buy`/`skip`, a 0-100 conviction score, a 0.5-1.5x position-size multiplier,
and risk flags. The bot only enters at `SOLBOT_AI_MIN_CONVICTION` (default
60) or above, scales the position by the AI's sizing, and records the
reasoning on each position (visible in Telegram alerts and `scan` output).
Any AI error fails safe — the candidate is skipped, not bought. Without an
API key the bot runs on the mechanical filters alone.

| Setting | Default | Meaning |
|---|---|---|
| `SOLBOT_AI_ENABLED` | auto | on when `ANTHROPIC_API_KEY` is set |
| `SOLBOT_AI_MODEL` | `claude-opus-4-8` | Claude model for analysis |
| `SOLBOT_AI_MIN_CONVICTION` | 60 | minimum conviction to enter |

Optional Telegram alerts on every buy/sell: set `SOLBOT_TG_BOT_TOKEN` +
`SOLBOT_TG_CHAT_ID`.

> ⚠️ **Risk warning:** meme coins are extreme-risk assets; most go to zero
> and filters cannot catch every rug or honeypot. Nothing here is financial
> advice — paper-trade first, size small, and never use your main wallet.
