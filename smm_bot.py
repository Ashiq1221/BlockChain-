#!/usr/bin/env python3
"""
SMMFollows Auto-Bot
-------------------
* Places Likes, Comments, and Retweets orders for every target link
* Monitors all active orders continuously
* Auto-requests refill on every completed/partial order that supports it
* Runs forever until interrupted with Ctrl-C
"""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import config
from smm_client import SMMClient, SMMError

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("smm_bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ── order tracking ────────────────────────────────────────────────────────────

REFILLABLE_STATUSES = {"Completed", "Partial"}
ACTIVE_STATUSES     = {"Pending", "In progress", "Processing"}
DONE_STATUSES       = {"Completed", "Partial", "Canceled", "Cancelled"}


@dataclass
class Order:
    order_id:    int
    service_id:  int
    order_type:  str       # "likes" | "comments" | "retweets"
    link:        str
    quantity:    int
    status:      str       = "Pending"
    refill_id:   Optional[int] = None
    refilled:    bool      = False


@dataclass
class BotState:
    orders:         dict[int, Order] = field(default_factory=dict)
    refill_ids:     dict[int, int]   = field(default_factory=dict)  # refill_id -> order_id
    comment_cycle:  itertools.cycle  = field(
        default_factory=lambda: itertools.cycle(config.COMMENT_TEXTS)
    )


# ── core bot ──────────────────────────────────────────────────────────────────

class SMMBot:
    def __init__(self, client: SMMClient) -> None:
        self.client = client
        self.state  = BotState()

    # ── order placement ───────────────────────────────────────────────────────

    def _place_order(
        self,
        order_type: str,
        service_id: int,
        link: str,
        quantity: int,
        comments: str | None = None,
    ) -> None:
        try:
            result = self.client.add_order(service_id, link, quantity, comments=comments)
            oid = int(result.get("order") or result.get("id", 0))
            if not oid:
                log.warning("Order placed but no ID returned: %s", result)
                return
            order = Order(
                order_id=oid,
                service_id=service_id,
                order_type=order_type,
                link=link,
                quantity=quantity,
            )
            self.state.orders[oid] = order
            log.info("Order placed | type=%-9s id=%-10d link=%s", order_type, oid, link)
        except SMMError as exc:
            log.error("Failed to place %s order for %s: %s", order_type, link, exc)

    def place_all_orders(self) -> None:
        """Place likes, comments, and retweets for every configured target link."""
        for link in config.TARGET_LINKS:
            log.info("Placing orders for: %s", link)

            self._place_order(
                "likes",
                config.LIKES_SERVICE_ID,
                link,
                config.DEFAULT_LIKES_QTY,
            )
            time.sleep(1)

            comment_text = "\n".join(
                next(self.state.comment_cycle)
                for _ in range(config.DEFAULT_COMMENTS_QTY)
            )
            self._place_order(
                "comments",
                config.COMMENTS_SERVICE_ID,
                link,
                config.DEFAULT_COMMENTS_QTY,
                comments=comment_text,
            )
            time.sleep(1)

            self._place_order(
                "retweets",
                config.RETWEETS_SERVICE_ID,
                link,
                config.DEFAULT_RETWEETS_QTY,
            )
            time.sleep(1)

    # ── status monitoring ─────────────────────────────────────────────────────

    def refresh_statuses(self) -> None:
        """Batch-check status of all tracked orders."""
        ids = list(self.state.orders.keys())
        if not ids:
            return

        # API allows up to 100 per request
        for chunk_start in range(0, len(ids), 100):
            chunk = ids[chunk_start : chunk_start + 100]
            try:
                if len(chunk) == 1:
                    raw = self.client.get_order_status(chunk[0])
                    statuses = {str(chunk[0]): raw}
                else:
                    statuses = self.client.get_order_statuses(chunk)
            except SMMError as exc:
                log.error("Status check failed: %s", exc)
                continue

            for str_id, info in statuses.items():
                oid = int(str_id)
                if oid not in self.state.orders:
                    continue
                order = self.state.orders[oid]
                old_status = order.status
                order.status = info.get("status", order.status)
                if order.status != old_status:
                    log.info(
                        "Order %d (%s) status changed: %s → %s",
                        oid, order.order_type, old_status, order.status,
                    )

    # ── auto-refill ───────────────────────────────────────────────────────────

    def request_refills(self) -> None:
        """Request refill for every completed/partial order not yet refilled."""
        for order in list(self.state.orders.values()):
            if order.refilled:
                continue
            if order.status not in REFILLABLE_STATUSES:
                continue
            try:
                result = self.client.request_refill(order.order_id)
                refill_id = int(result.get("refill", 0))
                if refill_id:
                    order.refill_id = refill_id
                    order.refilled  = True
                    self.state.refill_ids[refill_id] = order.order_id
                    log.info(
                        "Refill requested | order=%d type=%s refill_id=%d",
                        order.order_id, order.order_type, refill_id,
                    )
                else:
                    log.warning("Refill for order %d returned no refill ID: %s", order.order_id, result)
            except SMMError as exc:
                log.warning("Refill failed for order %d: %s", order.order_id, exc)

    def check_refill_statuses(self) -> None:
        """Log current status of pending refills."""
        for refill_id, order_id in list(self.state.refill_ids.items()):
            try:
                result = self.client.get_refill_status(refill_id)
                status = result.get("status", "unknown")
                log.info("Refill %d (order %d) status: %s", refill_id, order_id, status)
                if status in ("Completed", "Rejected"):
                    del self.state.refill_ids[refill_id]
            except SMMError as exc:
                log.warning("Refill status check failed for refill %d: %s", refill_id, exc)

    # ── main loop ─────────────────────────────────────────────────────────────

    def show_balance(self) -> None:
        try:
            bal = self.client.get_balance()
            log.info("Account balance: %s %s", bal.get("balance"), bal.get("currency", ""))
        except SMMError as exc:
            log.error("Could not fetch balance: %s", exc)

    def summary(self) -> None:
        total   = len(self.state.orders)
        active  = sum(1 for o in self.state.orders.values() if o.status in ACTIVE_STATUSES)
        done    = sum(1 for o in self.state.orders.values() if o.status in DONE_STATUSES)
        refills = sum(1 for o in self.state.orders.values() if o.refilled)
        log.info(
            "Summary | total_orders=%d  active=%d  done=%d  refills_sent=%d",
            total, active, done, refills,
        )

    def run(self) -> None:
        log.info("=== SMMFollows Auto-Bot starting ===")
        self.show_balance()

        log.info("Placing initial orders for %d target link(s)…", len(config.TARGET_LINKS))
        self.place_all_orders()

        last_refill_sweep = 0.0

        log.info(
            "Entering monitor loop (poll every %ds, refill sweep every %ds) — Ctrl-C to stop",
            config.POLL_INTERVAL, config.REFILL_INTERVAL,
        )

        while True:
            time.sleep(config.POLL_INTERVAL)

            self.refresh_statuses()

            now = time.time()
            if now - last_refill_sweep >= config.REFILL_INTERVAL:
                self.request_refills()
                self.check_refill_statuses()
                last_refill_sweep = now

            self.summary()


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_client() -> SMMClient:
    return SMMClient(api_key=config.API_KEY, api_url=config.API_URL)


def cmd_list_services(_args: argparse.Namespace) -> None:
    client = build_client()
    try:
        services = client.get_services()
    except SMMError as exc:
        log.error("Could not fetch services: %s", exc)
        sys.exit(1)

    print(f"\n{'ID':<8} {'Name':<50} {'Rate':<10} {'Min':<8} {'Max':<10} {'Refill'}")
    print("-" * 100)
    for svc in services:
        print(
            f"{svc.get('service',''):<8} "
            f"{str(svc.get('name',''))[:50]:<50} "
            f"{svc.get('rate',''):<10} "
            f"{svc.get('min',''):<8} "
            f"{svc.get('max',''):<10} "
            f"{svc.get('refill', False)}"
        )


def cmd_balance(_args: argparse.Namespace) -> None:
    client = build_client()
    try:
        bal = client.get_balance()
        print(f"Balance: {bal.get('balance')} {bal.get('currency','')}")
    except SMMError as exc:
        log.error("Error: %s", exc)
        sys.exit(1)


def cmd_run(_args: argparse.Namespace) -> None:
    client = build_client()
    bot = SMMBot(client)
    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
        bot.summary()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SMMFollows Auto-Bot – likes, comments, retweets & auto-refill"
    )
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("run",           help="Start the bot (default)")
    sub.add_parser("balance",       help="Print account balance and exit")
    sub.add_parser("list-services", help="List all available services and exit")

    args = parser.parse_args()

    if args.command == "balance":
        cmd_balance(args)
    elif args.command == "list-services":
        cmd_list_services(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
