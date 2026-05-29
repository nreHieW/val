import random
import threading
import time
from contextlib import contextmanager

from yfinance.exceptions import YFRateLimitError

from scrape.core.config import (
    YAHOO_CALL_MAX_CONCURRENCY,
    YAHOO_CALL_MIN_INTERVAL_SECONDS,
    YAHOO_COOLDOWN_SECONDS,
    YAHOO_INFO_RETRIES,
    YAHOO_INFO_RETRY_SLEEP_SECONDS,
)


class YahooRateLimiter:
    def __init__(self, max_concurrency: int, min_interval_seconds: float, cooldown_seconds: float):
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrency))
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._cooldown_seconds = max(0.0, cooldown_seconds)
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    @contextmanager
    def slot(self):
        self._semaphore.acquire()
        try:
            self._wait_for_turn()
            yield
        except YFRateLimitError:
            self.cooldown()
            raise
        finally:
            self._semaphore.release()

    def _wait_for_turn(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_at:
                time.sleep(self._next_allowed_at - now)
                now = time.monotonic()
            self._next_allowed_at = now + self._min_interval_seconds

    def cooldown(self):
        if self._cooldown_seconds <= 0:
            return
        with self._lock:
            self._next_allowed_at = max(self._next_allowed_at, time.monotonic() + self._cooldown_seconds)


YAHOO_RATE_LIMITER = YahooRateLimiter(
    max_concurrency=YAHOO_CALL_MAX_CONCURRENCY,
    min_interval_seconds=YAHOO_CALL_MIN_INTERVAL_SECONDS,
    cooldown_seconds=YAHOO_COOLDOWN_SECONDS,
)


def yahoo_call(fn, *, retries: int | None = None, retry_sleep_seconds: float | None = None):
    retries = YAHOO_INFO_RETRIES if retries is None else retries
    retry_sleep_seconds = YAHOO_INFO_RETRY_SLEEP_SECONDS if retry_sleep_seconds is None else retry_sleep_seconds
    last_error = None
    for attempt in range(retries):
        try:
            with YAHOO_RATE_LIMITER.slot():
                return fn()
        except YFRateLimitError as e:
            last_error = e
            if attempt == retries - 1:
                raise
            sleep_for = retry_sleep_seconds * (attempt + 1) + random.uniform(0, 1)
            time.sleep(sleep_for)
    if last_error:
        raise last_error
    return None
