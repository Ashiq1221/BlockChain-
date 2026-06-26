"""SMMFollows v2 API client — all endpoints, full error handling."""

from __future__ import annotations

import logging
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
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "SMMAgent/2.0"})

    # ── internal ──────────────────────────────────────────────────────────────

    def _post(self, payload: dict[str, Any]) -> Any:
        payload["key"] = self.api_key
        try:
            resp = self._session.post(self.api_url, data=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise SMMError(f"HTTP error: {exc}") from exc
        except ValueError as exc:
            raise SMMError(f"Bad JSON: {resp.text[:300]}") from exc

        if isinstance(data, dict) and "error" in data:
            raise SMMError(data["error"])
        return data

    # ── account ───────────────────────────────────────────────────────────────

    def balance(self) -> dict:
        """Return {'balance': '...', 'currency': '...'}."""
        return self._post({"action": "balance"})

    # ── services ──────────────────────────────────────────────────────────────

    def services(self) -> list[dict]:
        """Full service catalogue with IDs, rates, min/max, refill flag."""
        return self._post({"action": "services"})

    # ── orders ────────────────────────────────────────────────────────────────

    def add_order(
        self,
        service: int,
        link: str,
        quantity: int,
        *,
        comments: str | None = None,
        keywords: str | None = None,
        hashtags: str | None = None,
        username: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "action":   "add",
            "service":  service,
            "link":     link,
            "quantity": quantity,
        }
        for key, val in [
            ("comments",  comments),
            ("keywords",  keywords),
            ("hashtags",  hashtags),
            ("username",  username),
        ]:
            if val is not None:
                payload[key] = val
        return self._post(payload)

    def order_status(self, order_id: int) -> dict:
        return self._post({"action": "status", "order": order_id})

    def order_status_bulk(self, order_ids: list[int]) -> dict[str, dict]:
        """Check up to 100 orders at once. Returns {str_id: {...}}."""
        ids = ",".join(str(i) for i in order_ids[:100])
        return self._post({"action": "status", "orders": ids})

    def cancel_orders(self, order_ids: list[int]) -> Any:
        ids = ",".join(str(i) for i in order_ids[:100])
        return self._post({"action": "cancel", "orders": ids})

    # ── refill ────────────────────────────────────────────────────────────────

    def refill(self, order_id: int) -> dict:
        """Request refill. Returns {'refill': refill_id}."""
        return self._post({"action": "refill", "order": order_id})

    def refill_bulk(self, order_ids: list[int]) -> Any:
        ids = ",".join(str(i) for i in order_ids[:100])
        return self._post({"action": "refill", "orders": ids})

    def refill_status(self, refill_id: int) -> dict:
        return self._post({"action": "refill_status", "refill": refill_id})

    def refill_status_bulk(self, refill_ids: list[int]) -> Any:
        ids = ",".join(str(i) for i in refill_ids[:100])
        return self._post({"action": "refill_status", "refills": ids})
