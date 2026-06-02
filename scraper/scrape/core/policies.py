from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    backoff_seconds: float


@dataclass(frozen=True)
class RateLimitPolicy:
    min_interval_seconds: float
    jitter_seconds: float = 0.0


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


@dataclass(frozen=True)
class YahooSnapshotPolicy:
    batch_sleep_seconds: float
    failure_cooldown_seconds: float
    max_consecutive_empty_batches: int


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
