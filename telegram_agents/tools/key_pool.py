"""
Per-provider key pool with round-robin rotation and rate-limit cooldown.

Each provider (OpenAI, Claude, DeepSeek, Groq) has up to 5 API keys.
On a 429 the key is cooled for `cooldown_secs`; the pool automatically
skips cooling keys and moves to the next available one.
"""
import time
import threading


class KeyPool:
    def __init__(self, keys: list[str], cooldown_secs: int = 60):
        self._keys     = [k for k in keys if k]
        self._cooldown = cooldown_secs
        self._cooling: dict[str, float] = {}   # key → unblock_at timestamp
        self._idx      = 0
        self._lock     = threading.Lock()

    def __bool__(self) -> bool:
        return bool(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def next(self) -> str | None:
        """Return the next available key (round-robin), or None if all cooling."""
        with self._lock:
            now = time.time()
            available = [k for k in self._keys if self._cooling.get(k, 0) <= now]
            if not available:
                return None
            self._idx  = self._idx % len(available)
            key        = available[self._idx]
            self._idx  = (self._idx + 1) % len(available)
            return key

    def mark_rate_limited(self, key: str):
        """Put a key in cooldown after a 429."""
        with self._lock:
            self._cooling[key] = time.time() + self._cooldown

    def available_count(self) -> int:
        now = time.time()
        return sum(1 for k in self._keys if self._cooling.get(k, 0) <= now)

    def status(self) -> dict:
        now     = time.time()
        cooling = sum(1 for v in self._cooling.values() if v > now)
        return {
            "total":     len(self._keys),
            "available": self.available_count(),
            "cooling":   cooling,
        }
