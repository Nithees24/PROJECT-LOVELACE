"""In-memory rate limiting and login-failure lockout (SEC-12).

Single-process only by design: the app runs as one uvicorn process, so a
shared store (Redis) would be dead weight. If the deployment ever moves to
multiple workers, these counters must move to a shared backend or the
limits silently become per-worker.
"""
import threading
import time
from collections import defaultdict, deque

from backend.utils.logger import logger


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window counter keyed by an arbitrary string
    (e.g. "login-ip:1.2.3.4"). Sync FastAPI handlers run in a threadpool,
    so every mutation happens under a lock."""

    _PRUNE_INTERVAL = 300  # seconds between sweeps of dead keys
    _MAX_IDLE = 3600       # a key untouched this long is dropped

    def __init__(self):
        self._events = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def hit(self, key: str, limit: int, window_seconds: int):
        """Record one event against `key`. Returns (allowed, retry_after_s).
        When not allowed, the event is NOT recorded — a hammering client
        doesn't push its own window endlessly into the future."""
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            cutoff = now - window_seconds
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                retry_after = max(1, int(q[0] + window_seconds - now) + 1)
                return False, retry_after
            q.append(now)
            self._maybe_prune(now)
            return True, 0

    def _maybe_prune(self, now):
        if now - self._last_prune < self._PRUNE_INTERVAL:
            return
        self._last_prune = now
        stale = [k for k, q in self._events.items() if not q or q[-1] <= now - self._MAX_IDLE]
        for k in stale:
            del self._events[k]


class FailedLoginTracker:
    """Per-account lockout: `max_failures` failed attempts within
    `window_seconds` locks the key for `lockout_seconds`; a successful
    login clears it. Keyed by normalized email so the lock follows the
    targeted account, not the attacker's IP."""

    def __init__(self, max_failures=5, window_seconds=900, lockout_seconds=900):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._failures = defaultdict(deque)
        self._locked_until = {}
        self._lock = threading.Lock()

    def is_locked(self, key: str):
        """Returns (locked, retry_after_s)."""
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(key)
            if until and until > now:
                return True, max(1, int(until - now) + 1)
            if until:
                del self._locked_until[key]
        return False, 0

    def record_failure(self, key: str) -> bool:
        """Record a failed attempt; returns True when this failure engaged
        the lockout."""
        now = time.monotonic()
        with self._lock:
            q = self._failures[key]
            cutoff = now - self.window_seconds
            while q and q[0] <= cutoff:
                q.popleft()
            q.append(now)
            if len(q) >= self.max_failures:
                self._locked_until[key] = now + self.lockout_seconds
                q.clear()
                logger.warning(
                    f"[Auth] Account lockout engaged for '{key}' after "
                    f"{self.max_failures} failed logins within {self.window_seconds}s "
                    f"(locked for {self.lockout_seconds}s)"
                )
                return True
        return False

    def record_success(self, key: str):
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)
