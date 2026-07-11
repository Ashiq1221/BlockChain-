"""Position tracking with JSON persistence (paper and live share one book)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field


@dataclass
class Position:
    mint: str
    symbol: str
    pair_address: str
    entry_price_native: float        # token price in SOL at entry
    entry_price_usd: float
    sol_spent: float
    tokens_raw: int                  # raw base units held (live) / simulated (paper)
    opened_at: float
    peak_price_native: float
    live: bool
    buy_signature: str = ""
    ai_conviction: int = -1          # -1 = AI analyst not used for this entry
    ai_reasoning: str = ""
    status: str = "open"             # open | closed
    closed_at: float = 0.0
    exit_price_native: float = 0.0
    sol_received: float = 0.0
    exit_reason: str = ""
    sell_signature: str = ""

    @property
    def pnl_pct(self) -> float:
        ref = self.exit_price_native if self.status == "closed" else self.peak_price_native
        if self.entry_price_native <= 0:
            return 0.0
        return (ref / self.entry_price_native - 1) * 100

    def pnl_pct_at(self, price_native: float) -> float:
        if self.entry_price_native <= 0:
            return 0.0
        return (price_native / self.entry_price_native - 1) * 100

    @property
    def pnl_sol(self) -> float:
        if self.status != "closed":
            return 0.0
        return self.sol_received - self.sol_spent

    @property
    def hold_minutes(self) -> float:
        end = self.closed_at if self.status == "closed" else time.time()
        return (end - self.opened_at) / 60


@dataclass
class Portfolio:
    path: str
    positions: list[Position] = field(default_factory=list)
    daily_buys: dict[str, int] = field(default_factory=dict)  # "YYYY-MM-DD" -> count

    @classmethod
    def load(cls, path: str) -> "Portfolio":
        if not os.path.exists(path):
            return cls(path=path)
        with open(path) as fh:
            data = json.load(fh)
        return cls(
            path=path,
            positions=[Position(**p) for p in data.get("positions", [])],
            daily_buys=data.get("daily_buys", {}),
        )

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(
                {
                    "positions": [asdict(p) for p in self.positions],
                    "daily_buys": self.daily_buys,
                },
                fh,
                indent=2,
            )
        os.replace(tmp, self.path)

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "open"]

    @property
    def closed_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "closed"]

    def holds(self, mint: str) -> bool:
        return any(p.mint == mint for p in self.open_positions)

    def has_traded(self, mint: str) -> bool:
        """True if the mint was ever bought — avoids re-entering rugs."""
        return any(p.mint == mint for p in self.positions)

    def buys_today(self) -> int:
        return self.daily_buys.get(time.strftime("%Y-%m-%d", time.gmtime()), 0)

    def record_buy_today(self) -> None:
        key = time.strftime("%Y-%m-%d", time.gmtime())
        self.daily_buys = {key: self.daily_buys.get(key, 0) + 1}  # keep only today

    def open(self, position: Position) -> None:
        self.positions.append(position)
        self.record_buy_today()
        self.save()

    def close(
        self,
        position: Position,
        exit_price_native: float,
        sol_received: float,
        reason: str,
        sell_signature: str = "",
    ) -> None:
        position.status = "closed"
        position.closed_at = time.time()
        position.exit_price_native = exit_price_native
        position.sol_received = sol_received
        position.exit_reason = reason
        position.sell_signature = sell_signature
        self.save()

    def realized_pnl_sol(self) -> float:
        return sum(p.pnl_sol for p in self.closed_positions)
