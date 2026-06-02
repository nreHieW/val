import random
import threading
import time
from contextlib import contextmanager

from yfinance.exceptions import YFRateLimitError

from scrape.core.cancellation import sleep_with_cancel
from scrape.core.policies import YAHOO


class RateLimiter:
    def __init__(self, min_interval_seconds: float, jitter_seconds: float = 0.0):
        if min_interval_seconds < 0 or jitter_seconds < 0:
            raise ValueError("Rate limiter intervals must be non-negative")
        self.min_interval_seconds = min_interval_seconds
        self.jitter_seconds = jitter_seconds
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def wait(self, cancel_event=None) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_seconds = max(0.0, self._next_allowed_at - now)
            interval = self.min_interval_seconds
            if self.jitter_seconds:
                interval += random.uniform(0.0, self.jitter_seconds)
            self._next_allowed_at = max(now, self._next_allowed_at) + interval

        if sleep_seconds:
            sleep_with_cancel(sleep_seconds, cancel_event, "Rate-limited request cancelled")


class YahooRateLimiter:
    def __init__(self, max_concurrency: int, min_interval_seconds: float, cooldown_seconds: float):
        if max_concurrency < 1:
            raise ValueError("Yahoo max concurrency must be positive")
        if min_interval_seconds < 0 or cooldown_seconds < 0:
            raise ValueError("Yahoo rate limiter intervals must be non-negative")
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._min_interval_seconds = min_interval_seconds
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    @contextmanager
    def slot(self):
        self._semaphore.acquire()
        try:
            with self._lock:
                now = time.monotonic()
                if now < self._next_allowed_at:
                    time.sleep(self._next_allowed_at - now)
                    now = time.monotonic()
                self._next_allowed_at = now + self._min_interval_seconds
            yield
        except YFRateLimitError:
            if self._cooldown_seconds > 0:
                with self._lock:
                    self._next_allowed_at = max(self._next_allowed_at, time.monotonic() + self._cooldown_seconds)
            raise
        finally:
            self._semaphore.release()


YAHOO_RATE_LIMITER = YahooRateLimiter(
    max_concurrency=YAHOO.max_concurrency,
    min_interval_seconds=YAHOO.call_rate_limit.min_interval_seconds,
    cooldown_seconds=YAHOO.cooldown_seconds,
)


def yahoo_call(fn, *, retries: int | None = None, retry_sleep_seconds: float | None = None):
    retries = YAHOO.retry.attempts if retries is None else retries
    retry_sleep_seconds = YAHOO.retry.backoff_seconds if retry_sleep_seconds is None else retry_sleep_seconds
    if retries < 1:
        raise ValueError("Yahoo retries must be positive")
    for attempt in range(retries):
        try:
            with YAHOO_RATE_LIMITER.slot():
                return fn()
        except YFRateLimitError:
            if attempt == retries - 1:
                raise
            sleep_for = retry_sleep_seconds * (attempt + 1) + random.uniform(0, 1)
            time.sleep(sleep_for)
