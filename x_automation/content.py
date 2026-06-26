import random
from datetime import datetime
from . import config

HASHTAGS = "#Blockchain #Crypto #Web3 #DeFi #CryptoNews"

SCHEDULED_TEMPLATES = [
    "🔗 {name} — a blockchain with a fixed supply of {supply:,} tokens.\n\nScarcity is built in. No inflation. No surprises.\n\n{tags}",
    "💎 Why fixed supply matters:\n\n✅ {supply:,} {name} tokens. That's it. Forever.\n✅ Deflationary by design\n✅ True digital scarcity\n\n{tags}",
    "📊 {name} Token Stats\n\n• Total Supply: {supply:,}\n• Inflation Rate: 0%\n• Supply Cap: Hard\n\nBuilt for the long game. 🚀\n\n{tags}",
    "🌐 The future of finance is decentralized.\n\n{name} with {supply:,} fixed supply tokens is here to prove it.\n\n{tags}",
    "🔒 {supply:,} tokens. Hard cap. Immutable.\n\nThat's the promise of {name} — a blockchain built on scarcity and trust.\n\n{tags}",
    "⛓️ Did you know? {name} has a total supply of only {supply:,} tokens.\n\nCompare that to fiat currency being printed endlessly...\n\n{tags}",
]

ALERT_TEMPLATES = {
    "new_transaction": "🔔 New transaction detected on {name}!\n\n📤 From: {sender}\n📥 To: {receiver}\n💰 Amount: {amount} tokens\n🕐 {time}\n\n{tags}",
    "milestone": "🎉 {name} just hit a new milestone!\n\n{milestone_text}\n\n{tags}",
    "supply_update": "📈 {name} Supply Update\n\nCirculating: {circulating:,} / {supply:,} tokens\nRemaining: {remaining:,} tokens\n\n{tags}",
}

THREAD_INTRO = [
    "🧵 A thread on why {name} with {supply:,} tokens is different from everything else in crypto 👇",
    "🧵 Let me break down {name} for you — a blockchain with hard-capped supply of {supply:,} tokens 👇",
    "🧵 Everything you need to know about {name} (1/{total})",
]

THREAD_POSTS = [
    "1/ What is {name}?\n\nIt's a blockchain with a maximum supply of {supply:,} tokens — hardcoded, immutable, and non-negotiable.",
    "2/ Why does the supply cap matter?\n\nWith only {supply:,} tokens ever in existence, {name} cannot be inflated away. Every token holds its relative share of the network.",
    "3/ Scarcity = Value\n\nBasic economics: when supply is fixed and demand grows, value increases. {name} bets on this principle.",
    "4/ Decentralization first\n\nNo central authority controls {name}. The rules are enforced by code, not by committees or governments.",
    "5/ The long-term vision\n\nAs the world moves toward trustless systems, a fixed-supply blockchain like {name} becomes a foundation — not just a token.",
    "6/ TL;DR — {name}\n\n✅ {supply:,} total supply\n✅ Hard cap, no inflation\n✅ Decentralized\n✅ Built for the future\n\nFollow for updates 🔔\n\n{tags}",
]


def get_scheduled_tweet() -> str:
    template = random.choice(SCHEDULED_TEMPLATES)
    return template.format(
        name=config.BLOCKCHAIN_NAME,
        supply=config.TOTAL_SUPPLY,
        tags=HASHTAGS,
    )


def get_alert_tweet(alert_type: str, **kwargs) -> str:
    template = ALERT_TEMPLATES.get(alert_type, "")
    if not template:
        return ""
    kwargs.setdefault("name", config.BLOCKCHAIN_NAME)
    kwargs.setdefault("supply", config.TOTAL_SUPPLY)
    kwargs.setdefault("tags", HASHTAGS)
    kwargs.setdefault("time", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    return template.format(**kwargs)


def get_thread() -> list[str]:
    posts = []
    intro_template = random.choice(THREAD_INTRO)
    intro = intro_template.format(
        name=config.BLOCKCHAIN_NAME,
        supply=config.TOTAL_SUPPLY,
        total=len(THREAD_POSTS),
    )
    posts.append(intro)
    for post in THREAD_POSTS:
        posts.append(post.format(
            name=config.BLOCKCHAIN_NAME,
            supply=config.TOTAL_SUPPLY,
            tags=HASHTAGS,
        ))
    return posts
