"""Optional Telegram notifications for trade events."""

from __future__ import annotations

import logging

import httpx

from . import config

log = logging.getLogger("solbot.notify")


async def send(text: str) -> None:
    """Fire-and-forget Telegram message; silently no-op if unconfigured."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                url,
                json={
                    "chat_id": config.TELEGRAM_CHAT_ID,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
    except httpx.HTTPError as exc:
        log.warning("telegram notify failed: %s", exc)
