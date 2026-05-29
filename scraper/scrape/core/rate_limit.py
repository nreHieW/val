import random
import threading
import time


class RateLimiter:
    """Thread-safe minimum-interval limiter for fragile remote endpoints."""

    def __init__(self, min_interval_seconds: float, jitter_seconds: float = 0.0):
        self.min_interval_seconds = min_interval_seconds
        self.jitter_seconds = jitter_seconds
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_seconds = max(0.0, self._next_allowed_at - now)
            interval = self.min_interval_seconds
            if self.jitter_seconds:
                interval += random.uniform(0.0, self.jitter_seconds)
            self._next_allowed_at = max(now, self._next_allowed_at) + interval

        if sleep_seconds:
            time.sleep(sleep_seconds)
