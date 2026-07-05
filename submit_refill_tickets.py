#!/usr/bin/env python3
"""
Direct refill ticket submission for all dropped orders.
Groups by post link, one ticket per post. Bypasses AI council per user request.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests

# ── Load .env ──────────────────────────────────────────────────────────────────────────────
def _load_env() -> None:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

PANEL = "https://smmfollows.com"
USER  = os.environ.get("SMM_USER", "")
PASSWD = os.environ.get("SMM_PASS", "")
STATE_FILE = Path(__file__).parent / "automation_state.json"

# ── Login ──────────────────────────────────────────────────────────────────────────────
def _panel_session() -> requests.Session | None:
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    try:
        r = sess.get(f"{PANEL}/", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            print("ERROR: CSRF token not found on login page")
            return None
        sess.post(f"{PANEL}/", data={
            "_csrf": m.group(1),
            "LoginForm[username]": USER,
            "LoginForm[password]": PASSWD,
            "LoginForm[remember]": "1",
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{PANEL}/",
            "Origin": PANEL,
        }, allow_redirects=True, timeout=20)
        if "_identity_user" in sess.cookies:
            print(f"Logged in to {PANEL} as {USER}")
            return sess
        print("ERROR: Login failed — cookie not set")
        return None
    except Exception as exc:
        print(f"ERROR: Login exception: {exc}")
        return None

# ── Submit single ticket ──────────────────────────────────────────────────────────────────
def _submit_ticket(sess: requests.Session, order_ids: list[str], post_link: str, message: str) -> bool:
    try:
        r = sess.get(f"{PANEL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            print(f"  ERROR: CSRF token not found for ticket page")
            return False
        csrf = m.group(1)

        r2 = sess.post(f"{PANEL}/ticket-create", data={
            "_csrf": csrf,
            "TicketForm[subject]": f"Junior - Orders [ Refill ]",
            "TicketForm[message]": message,
            "subject": "Orders",
            "request": "Refill",
            "cancel-reason": "",
            "ordernumbers": ",".join(order_ids),
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{PANEL}/tickets",
            "Origin": PANEL,
            "Accept": "application/json, */*",
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=20)

        if r2.status_code == 200:
            try:
                resp = r2.json()
                if resp.get("status") == "success":
                    return True
                print(f"  WARN: API response: {resp}")
                return False
            except Exception:
                if "success" in r2.text.lower() or r2.status_code == 200:
                    return True
        print(f"  ERROR: HTTP {r2.status_code}: {r2.text[:200]}")
        return False
    except Exception as exc:
        print(f"  ERROR: Exception: {exc}")
        return False

# ── Main ──────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    with open(STATE_FILE) as f:
        state = json.load(f)
    orders = state.get("orders", {})

    eligible_statuses = {"Completed", "Partial", "Canceled"}
    smmwiz_ids = set()
    groups: dict[str, list] = {}

    for oid, o in orders.items():
        status = (o.get("status") or "").strip()
        panel  = (o.get("panel")  or "").strip().lower()
        link   = (o.get("link")   or "").strip()

        if status not in eligible_statuses:
            print(f"  SKIP #{oid}: status={status!r}")
            continue

        if panel == "smmwiz":
            smmwiz_ids.add(oid)
            print(f"  SKIP #{oid}: smmwiz panel (ticket not supported here)")
            continue

        if not link:
            print(f"  SKIP #{oid}: no post link")
            continue

        groups.setdefault(link, []).append({
            "id": oid,
            "kind": o.get("kind", ""),
            "quantity": o.get("quantity", 0),
            "status": status,
            "remains": o.get("remains", 0),
        })

    print(f"\nFound {sum(len(v) for v in groups.values())} eligible orders across {len(groups)} posts\n")
    if not groups:
        print("Nothing to ticket. Exiting.")
        return

    sess = _panel_session()
    if not sess:
        print("Cannot continue without panel session.")
        sys.exit(1)

    submitted = 0
    failed    = 0
    for link, orders_list in groups.items():
        ids  = [o["id"] for o in orders_list]
        message = (
            f"Hello,\n\n"
            f"All orders for the following post have dropped back to 0 after completion. "
            f"Please refill them immediately.\n\n"
            f"Post: {link}\n\n"
            f"Orders:\n" +
            "\n".join(f"  - #{o['id']}: {o['quantity']}x {o['kind']} — {o['status']}"
                      for o in orders_list) +
            "\n\nKindly process the refills as soon as possible. Thank you."
        )

        print(f"Submitting ticket for {link}")
        print(f"  Orders: {', '.join(ids)}")
        ok = _submit_ticket(sess, ids, link, message)
        if ok:
            print(f"  SUCCESS — ticket submitted for {len(ids)} orders")
            submitted += 1
        else:
            print(f"  FAILED")
            failed += 1
        print()

    print(f"Done. Submitted: {submitted}  Failed: {failed}")
    if smmwiz_ids:
        print(f"\nNote: {len(smmwiz_ids)} smmwiz orders skipped (— log in to smmwiz.com manually to ticket those.)")

if __name__ == "__main__":
    main()
