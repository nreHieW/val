from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    backoff_seconds: float

    def __post_init__(self):
        if self.attempts < 1 or self.backoff_seconds < 0:
            raise ValueError("Retry attempts must be positive and backoff must be non-negative")

    def backoff(self, attempt):
        return self.backoff_seconds * (attempt + 1)


@dataclass(frozen=True)
class RateLimitPolicy:
    min_interval_seconds: float
    jitter_seconds: float = 0.0

    def __post_init__(self):
        if self.min_interval_seconds < 0 or self.jitter_seconds < 0:
            raise ValueError("Rate limit policy intervals must be non-negative")


@dataclass(frozen=True)
class SourcePolicy:
    retry: RetryPolicy
    rate_limit: RateLimitPolicy


@dataclass(frozen=True)
class YahooPolicy:
    retry: RetryPolicy
    call_rate_limit: RateLimitPolicy
    financial_rate_limit: RateLimitPolicy
    max_concurrency: int
    cooldown_seconds: float

    def __post_init__(self):
        if self.max_concurrency < 1 or self.cooldown_seconds < 0:
            raise ValueError("Yahoo concurrency must be positive and cooldown must be non-negative")


@dataclass(frozen=True)
class YahooSnapshotPolicy:
    batch_sleep_seconds: float
    failure_cooldown_seconds: float
    max_consecutive_empty_batches: int

    def __post_init__(self):
        if (
            self.batch_sleep_seconds < 0
            or self.failure_cooldown_seconds < 0
            or self.max_consecutive_empty_batches < 1
        ):
            raise ValueError("Yahoo snapshot sleeps must be non-negative and empty batch limit must be positive")


MARKETSCREENER = SourcePolicy(RetryPolicy(3, 2), RateLimitPolicy(0.25, 0.1))
SEC = SourcePolicy(RetryPolicy(6, 30), RateLimitPolicy(1, 0.25))
YAHOO = YahooPolicy(
    retry=RetryPolicy(3, 5),
    call_rate_limit=RateLimitPolicy(0.35),
    financial_rate_limit=RateLimitPolicy(1.5, 0.5),
    max_concurrency=2,
    cooldown_seconds=30,
)
YAHOO_SNAPSHOT = YahooSnapshotPolicy(
    batch_sleep_seconds=1,
    failure_cooldown_seconds=30,
    max_consecutive_empty_batches=2,
)
