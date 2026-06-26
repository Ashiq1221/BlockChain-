"""
Tool definitions for the Claude AI agent.
Each function maps 1-to-1 to a tool the agent can call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from smm_client import SMMClient, SMMError

log = logging.getLogger(__name__)

REFILLABLE = {"Completed", "Partial"}
ACTIVE     = {"Pending", "In progress", "Processing", "Active"}
TERMINAL   = {"Completed", "Partial", "Canceled", "Cancelled"}


# ── order registry ────────────────────────────────────────────────────────────

@dataclass
class TrackedOrder:
    order_id:   int
    kind:       str        # "likes" | "comments" | "retweets"
    link:       str
    quantity:   int
    status:     str        = "Pending"
    refilled:   bool       = False
    refill_id:  Optional[int] = None


@dataclass
class OrderRegistry:
    orders:   dict[int, TrackedOrder] = field(default_factory=dict)
    refills:  dict[int, int]          = field(default_factory=dict)  # refill_id → order_id


# ── tool implementations ──────────────────────────────────────────────────────

class AgentTools:
    def __init__(self, client: SMMClient, registry: OrderRegistry) -> None:
        self.client   = client
        self.registry = registry

    # ── account ───────────────────────────────────────────────────────────────

    def get_balance(self) -> str:
        try:
            data = self.client.balance()
            return json.dumps({"balance": data.get("balance"), "currency": data.get("currency")})
        except SMMError as e:
            return json.dumps({"error": str(e)})

    # ── services ──────────────────────────────────────────────────────────────

    def list_services(self) -> str:
        try:
            svcs = self.client.services()
            slim = [
                {
                    "id":     s.get("service"),
                    "name":   s.get("name"),
                    "type":   s.get("type"),
                    "rate":   s.get("rate"),
                    "min":    s.get("min"),
                    "max":    s.get("max"),
                    "refill": s.get("refill"),
                }
                for s in svcs
            ]
            return json.dumps(slim)
        except SMMError as e:
            return json.dumps({"error": str(e)})

    # ── order placement ───────────────────────────────────────────────────────

    def place_likes(self, link: str, quantity: int, service_id: int) -> str:
        try:
            res  = self.client.add_order(service_id, link, quantity)
            oid  = int(res.get("order") or res.get("id", 0))
            if oid:
                self.registry.orders[oid] = TrackedOrder(oid, "likes", link, quantity)
                log.info("Likes order placed | id=%d link=%s qty=%d", oid, link, quantity)
            return json.dumps({"order_id": oid, "result": res})
        except SMMError as e:
            return json.dumps({"error": str(e)})

    def place_retweets(self, link: str, quantity: int, service_id: int) -> str:
        try:
            res = self.client.add_order(service_id, link, quantity)
            oid = int(res.get("order") or res.get("id", 0))
            if oid:
                self.registry.orders[oid] = TrackedOrder(oid, "retweets", link, quantity)
                log.info("Retweets order placed | id=%d link=%s qty=%d", oid, link, quantity)
            return json.dumps({"order_id": oid, "result": res})
        except SMMError as e:
            return json.dumps({"error": str(e)})

    def place_comments(self, link: str, comments: list[str], service_id: int) -> str:
        try:
            comment_block = "\n".join(comments)
            res = self.client.add_order(
                service_id, link, len(comments), comments=comment_block
            )
            oid = int(res.get("order") or res.get("id", 0))
            if oid:
                self.registry.orders[oid] = TrackedOrder(
                    oid, "comments", link, len(comments)
                )
                log.info(
                    "Comments order placed | id=%d link=%s count=%d", oid, link, len(comments)
                )
            return json.dumps({"order_id": oid, "result": res})
        except SMMError as e:
            return json.dumps({"error": str(e)})

    # ── order monitoring ──────────────────────────────────────────────────────

    def check_all_orders(self) -> str:
        ids = list(self.registry.orders.keys())
        if not ids:
            return json.dumps({"message": "No orders tracked yet."})
        try:
            if len(ids) == 1:
                raw = self.client.order_status(ids[0])
                statuses = {str(ids[0]): raw}
            else:
                statuses = self.client.order_status_bulk(ids)

            updates = []
            for str_id, info in statuses.items():
                oid = int(str_id)
                order = self.registry.orders.get(oid)
                if not order:
                    continue
                old = order.status
                order.status = info.get("status", old)
                updates.append({
                    "order_id": oid,
                    "kind":     order.kind,
                    "link":     order.link,
                    "status":   order.status,
                    "remains":  info.get("remains"),
                    "charge":   info.get("charge"),
                })
            return json.dumps({"orders": updates})
        except SMMError as e:
            return json.dumps({"error": str(e)})

    def check_order(self, order_id: int) -> str:
        try:
            data = self.client.order_status(order_id)
            if order_id in self.registry.orders:
                self.registry.orders[order_id].status = data.get("status", "unknown")
            return json.dumps(data)
        except SMMError as e:
            return json.dumps({"error": str(e)})

    # ── refill ────────────────────────────────────────────────────────────────

    def refill_order(self, order_id: int) -> str:
        order = self.registry.orders.get(order_id)
        if order and order.refilled:
            return json.dumps({"message": f"Order {order_id} already refilled (refill_id={order.refill_id})."})
        try:
            res = self.client.refill(order_id)
            rid = int(res.get("refill", 0))
            if rid and order:
                order.refilled  = True
                order.refill_id = rid
                self.registry.refills[rid] = order_id
                log.info("Refill requested | order=%d refill_id=%d", order_id, rid)
            return json.dumps({"refill_id": rid, "result": res})
        except SMMError as e:
            return json.dumps({"error": str(e)})

    def auto_refill_all(self) -> str:
        """Refill every order whose status is Completed or Partial."""
        eligible = [
            o for o in self.registry.orders.values()
            if o.status in REFILLABLE and not o.refilled
        ]
        if not eligible:
            return json.dumps({"message": "No orders eligible for refill right now."})

        results = []
        for order in eligible:
            res = json.loads(self.refill_order(order.order_id))
            results.append({"order_id": order.order_id, "kind": order.kind, **res})
        return json.dumps({"refills": results})

    def check_refill_statuses(self) -> str:
        if not self.registry.refills:
            return json.dumps({"message": "No pending refills."})
        results = []
        done = []
        for rid, oid in self.registry.refills.items():
            try:
                data = self.client.refill_status(rid)
                status = data.get("status", "unknown")
                results.append({"refill_id": rid, "order_id": oid, "status": status})
                if status in ("Completed", "Rejected"):
                    done.append(rid)
            except SMMError as e:
                results.append({"refill_id": rid, "error": str(e)})
        for rid in done:
            del self.registry.refills[rid]
        return json.dumps({"refill_statuses": results})

    # ── summary ───────────────────────────────────────────────────────────────

    def get_summary(self) -> str:
        orders = list(self.registry.orders.values())
        return json.dumps({
            "total_orders":   len(orders),
            "active":         sum(1 for o in orders if o.status in ACTIVE),
            "completed":      sum(1 for o in orders if o.status == "Completed"),
            "partial":        sum(1 for o in orders if o.status == "Partial"),
            "refills_sent":   sum(1 for o in orders if o.refilled),
            "pending_refills": len(self.registry.refills),
            "by_kind": {
                "likes":    sum(1 for o in orders if o.kind == "likes"),
                "comments": sum(1 for o in orders if o.kind == "comments"),
                "retweets": sum(1 for o in orders if o.kind == "retweets"),
            },
        })


# ── Claude tool schema definitions ───────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_balance",
        "description": "Retrieve the current SMM panel account balance.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_services",
        "description": (
            "List all available SMM services with their IDs, names, types, rates, "
            "min/max quantities, and whether they support refill. "
            "Call this first to discover the correct service IDs."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "place_likes",
        "description": "Place a Likes order for a given post URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "link":       {"type": "string",  "description": "Full URL of the post to boost."},
                "quantity":   {"type": "integer", "description": "Number of likes to add."},
                "service_id": {"type": "integer", "description": "SMMFollows service ID for likes."},
            },
            "required": ["link", "quantity", "service_id"],
        },
    },
    {
        "name": "place_retweets",
        "description": "Place a Retweets order for a given post URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "link":       {"type": "string",  "description": "Full URL of the post to boost."},
                "quantity":   {"type": "integer", "description": "Number of retweets to add."},
                "service_id": {"type": "integer", "description": "SMMFollows service ID for retweets."},
            },
            "required": ["link", "quantity", "service_id"],
        },
    },
    {
        "name": "place_comments",
        "description": "Place a Comments order with AI-generated natural comment texts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "link": {"type": "string", "description": "Full URL of the post to comment on."},
                "comments": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "description": "List of comment texts (one per comment order).",
                },
                "service_id": {"type": "integer", "description": "SMMFollows service ID for comments."},
            },
            "required": ["link", "comments", "service_id"],
        },
    },
    {
        "name": "check_all_orders",
        "description": "Fetch the latest status of every tracked order in one batch call.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_order",
        "description": "Check the status of a single order by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "The order ID to check."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "refill_order",
        "description": "Request a refill for a single order that is Completed or Partial.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "The order ID to refill."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "auto_refill_all",
        "description": (
            "Automatically request refills for ALL orders that are Completed or Partial "
            "and have not yet been refilled. Use this in the monitoring loop."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_refill_statuses",
        "description": "Check the status of all pending refill requests.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_summary",
        "description": "Get a summary of all tracked orders and their statuses.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]
