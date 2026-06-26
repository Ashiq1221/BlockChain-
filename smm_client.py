"""Thin wrapper around the SMMFollows v2 REST API."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)


class SMMError(Exception):
    pass


class SMMClient:
    def __init__(self, api_key: str, api_url: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.api_url = api_url
        self.timeout = timeout
        self.session = requests.Session()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _post(self, payload: dict) -> Any:
        payload["key"] = self.api_key
        try:
            resp = self.session.post(self.api_url, data=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise SMMError(f"HTTP error: {exc}") from exc
        except ValueError as exc:
            raise SMMError(f"Invalid JSON response: {resp.text[:200]}") from exc

        if isinstance(data, dict) and "error" in data:
            raise SMMError(data["error"])
        return data

    # ── public API ───────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        return self._post({"action": "balance"})

    def get_services(self) -> list[dict]:
        return self._post({"action": "services"})

    def add_order(
        self,
        service: int,
        link: str,
        quantity: int,
        *,
        comments: str | None = None,
    ) -> dict:
        payload: dict = {
            "action": "add",
            "service": service,
            "link": link,
            "quantity": quantity,
        }
        if comments:
            payload["comments"] = comments
        return self._post(payload)

    def get_order_status(self, order_id: int) -> dict:
        return self._post({"action": "status", "order": order_id})

    def get_order_statuses(self, order_ids: list[int]) -> dict:
        """Batch check – up to 100 IDs."""
        ids = ",".join(str(i) for i in order_ids[:100])
        return self._post({"action": "status", "orders": ids})

    def request_refill(self, order_id: int) -> dict:
        return self._post({"action": "refill", "order": order_id})

    def get_refill_status(self, refill_id: int) -> dict:
        return self._post({"action": "refill_status", "refill": refill_id})

    def cancel_orders(self, order_ids: list[int]) -> dict:
        ids = ",".join(str(i) for i in order_ids[:100])
        return self._post({"action": "cancel", "orders": ids})
