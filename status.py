#!/usr/bin/env python3
"""
Status Dashboard
----------------
Shows balance, all order statuses, and support ticket status in one run.

Usage:
  python status.py
  python status.py --refill    # also attempt refills on eligible completed orders
"""

from __future__ import annotations
import argparse, sys, json, re
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

API_KEY = "882fa9a6e54b39ffa8c7e2bf4fcc1f46"
API_URL = "https://smmfollows.com/api/v2"
PANEL   = "https://smmfollows.com"

# Old orders needing service-level refill via support
OLD_ORDERS = ["61218148", "61218147", "61218151", "61218154"]

# New orders placed for the 3 posts
NEW_ORDERS = [
    {"id": "61450840", "type": "likes",    "post": "2065705610163941467", "refillable": True},
    {"id": "61450841", "type": "retweets", "post": "2065705610163941467", "refillable": True},
    {"id": "61450842", "type": "comments", "post": "2065705610163941467", "refillable": False},
    {"id": "61450843", "type": "likes",    "post": "2064879295843983840", "refillable": True},
    {"id": "61450844", "type": "retweets", "post": "2064879295843983840", "refillable": True},
    {"id": "61450845", "type": "comments", "post": "2064879295843983840", "refillable": False},
    {"id": "61450846", "type": "likes",    "post": "2064283340849738045", "refillable": True},
    {"id": "61450847", "type": "retweets", "post": "2064283340849738045", "refillable": True},
    {"id": "61450848", "type": "comments", "post": "2064283340849738045", "refillable": False},
]

TICKET_ID = "1136178"


def api(payload: dict) -> dict:
    payload["key"] = API_KEY
    r = requests.post(API_URL, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def web_login() -> requests.Session | None:
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    try:
        r = sess.get(PANEL + "/", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf_inp = soup.find("input", {"name": "_csrf"})
        if not csrf_inp:
            return None
        csrf_val = csrf_inp["value"]
        login_data = urlencode([
            ("LoginForm[username]", "hhrh197"),
            ("LoginForm[password]", "Yawer@123"),
            ("LoginForm[remember]", "1"),
            ("_csrf", csrf_val),
        ])
        r2 = sess.post(PANEL + "/", data=login_data,
                       headers={"Content-Type": "application/x-www-form-urlencoded",
                                "Referer": PANEL + "/"},
                       allow_redirects=False, timeout=20)
        if "_identity_user" not in sess.cookies:
            return None
        loc = r2.headers.get("Location", "/")
        if not loc.startswith("http"):
            loc = PANEL + loc
        sess.get(loc, timeout=20)
        return sess
    except Exception as exc:
        print(f"  [warn] Web login failed: {exc}")
        return None


def check_ticket(sess: requests.Session) -> list[dict]:
    """Return list of ticket messages, de-duplicated."""
    try:
        r = sess.get(f"{PANEL}/viewticket/{TICKET_ID}", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        msgs = []
        seen = set()
        # Each message block: div.row.ticket-message-block
        # class ticket-message-right = user, ticket-message-left = staff
        for blk in soup.find_all("div", class_="ticket-message-block"):
            inner = blk.find("div", class_="message")
            if not inner:
                continue
            txt = inner.get_text(separator=" ", strip=True)
            if not txt or txt in seen:
                continue
            seen.add(txt)
            classes = blk.get("class", [])
            is_staff = "ticket-message-left" in classes
            msgs.append({"text": txt[:400], "staff": is_staff})
        return msgs
    except Exception as exc:
        return [{"text": f"[error checking ticket: {exc}]", "staff": False}]


def attempt_refill(order_id: str) -> str:
    res = api({"action": "refill", "order": order_id})
    if "error" in res:
        return res["error"]
    return f"REFILL SENT — refill_id={res.get('refill')}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refill", action="store_true", help="Attempt refills on eligible orders")
    args = parser.parse_args()

    sep = "─" * 70

    # ── Balance ────────────────────────────────────────────────────────────
    try:
        bal = api({"action": "balance"})
        print(f"\n💰  Balance: ${bal.get('balance')} {bal.get('currency','USD')}")
    except Exception as exc:
        print(f"\n[error] Balance check failed: {exc}")

    # ── Old orders ─────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("OLD ORDERS (service 8140 — refill via support ticket)")
    print(sep)
    try:
        st = api({"action": "status", "orders": ",".join(OLD_ORDERS)})
        for oid in OLD_ORDERS:
            info = st.get(oid, {})
            status  = info.get("status", "unknown")
            remains = info.get("remains", "?")
            print(f"  #{oid}  status={status:<12} remains={remains}")
    except Exception as exc:
        print(f"  [error] {exc}")

    # ── New orders ─────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("NEW ORDERS (3 posts — likes/retweets/comments)")
    print(sep)
    try:
        all_new_ids = [o["id"] for o in NEW_ORDERS]
        st2 = api({"action": "status", "orders": ",".join(all_new_ids)})
        for o in NEW_ORDERS:
            info    = st2.get(o["id"], {})
            status  = info.get("status", "unknown")
            remains = info.get("remains", "?")
            refill_note = ""
            if args.refill and o["refillable"] and status == "Completed":
                refill_note = "  →  " + attempt_refill(o["id"])
            elif o["refillable"] and status == "Completed":
                refill_note = "  [refillable — run with --refill]"
            print(f"  #{o['id']} {o['type']:<10} status={status:<14} remains={remains:<5}{refill_note}")
    except Exception as exc:
        print(f"  [error] {exc}")

    # ── Support ticket ─────────────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"SUPPORT TICKET #{TICKET_ID}")
    print(sep)
    sess = web_login()
    if sess:
        msgs = check_ticket(sess)
        if msgs:
            for i, m in enumerate(msgs, 1):
                who = "SUPPORT" if m["staff"] else "You"
                print(f"\n  [{i}] {who}:")
                print(f"  {m['text'][:300]}")
        else:
            print("  No messages found (or not logged in).")
    else:
        print("  [warn] Could not log in to check ticket.")

    print(f"\n{sep}")
    print(f"Ticket URL: {PANEL}/viewticket/{TICKET_ID}")
    print(sep + "\n")


if __name__ == "__main__":
    main()
