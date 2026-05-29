# DCF Scrape Optimization Plan

Goal: drastically reduce total pipeline runtime without changing scraper functionality, outputs, data requirements, or failure semantics. No new modes. No silent fallbacks.

## Optimization Areas

### 1. Reuse Yahoo data across the whole pipeline

The biggest opportunity is duplicate Yahoo work across DCF, comps, TTM financials, overview, and market discovery paths.

Plan:

- Fetch Yahoo data once per ticker for the full run.
- Reuse the fetched objects/data in every stage that needs them.
- Preserve the same fields and behavior; only remove duplicate calls.

Target files:

- `scraper/main.py`
- `scraper/scrape/sources/yahoo_snapshot.py`
- `scraper/scrape/valuation/dcf_inputs.py`
- `scraper/scrape/sources/yahoo_profiles.py`
- `scraper/scrape/sources/yahoo_overview.py`

### 2. Memoize Yahoo data within each ticker

Inside one ticker's DCF path, the code repeatedly touches the same Yahoo ticker/data.

Plan:

- Construct each `yf.Ticker(...)` once per ticker.
- Cache `get_info()` result.
- Cache statement DataFrames.
- Pass cached values into helper functions instead of refetching.

This keeps identical functionality while reducing network calls and object churn.

### 3. Bulk Mongo writes

The scraper currently writes records one at a time from worker paths.

Plan:

- Collect successful batch results in memory.
- Write DCF inputs, profiles, overviews, and financials with Mongo `bulk_write(UpdateOne(..., upsert=True))`.
- Preserve the same document shapes and upsert behavior.

Target files:

- `scraper/main.py`

### 4. Load MarketScreener cache once

`get_marketscreener_url()` currently reads/writes `marketscreener_links.json` repeatedly under a lock.

Plan:

- Load `marketscreener_links.json` once at startup.
- Use an in-memory cache during the run.
- Write changed links back once at the end or periodically.
- Keep the same URL lookup behavior and same cache file format.

Target files:

- `scraper/scrape/sources/marketscreener.py`

### 5. Reuse HTTP sessions

Many requests are one-off HTTP calls.

Plan:

- Use shared `requests.Session` for normal requests.
- Use shared `curl_cffi` session for browser-like requests if supported cleanly.
- Preserve existing headers, timeouts, impersonation, and retry behavior.

Target files:

- `scraper/scrape/core/http_utils.py`
- `scraper/scrape/sources/marketscreener.py`

### 6. Reduce nested thread-pool churn

DCF already runs tickers in a thread pool, and each ticker creates another small thread pool for MarketScreener region/forecast work.

Plan:

- Avoid creating thousands of short-lived nested executors.
- Reuse a shared small executor for those independent MarketScreener fetches, or run them through the existing batch executor safely.
- Keep the same two MarketScreener fetches and same failure behavior.

Target files:

- `scraper/scrape/valuation/dcf_inputs.py`

### 7. Cache run-level expensive setup

Some data should only be fetched or computed once per run.

Plan:

- Ensure Damodaran/CNBC macro data is fetched once.
- Ensure `StringMapper` objects are created once.
- Avoid recomputing embeddings/mappers inside ticker loops.

Most of this is already partially done; verify and tighten if needed.

Target files:

- `scraper/main.py`
- `scraper/scrape/valuation/market_metrics.py`
- `scraper/scrape/valuation/string_mapper.py`

### 8. Tune concurrency last

Only tune concurrency after duplicate work has been removed.

Plan:

- Benchmark current values.
- Tune:
  - `DCF_MAX_WORKERS`
  - `YAHOO_CALL_MAX_CONCURRENCY`
  - `YAHOO_FINANCIAL_MIN_INTERVAL_SECONDS`
  - `YAHOO_INFO_MAX_WORKERS`
- Watch for Yahoo rate-limit failures.

Do not start here; raising concurrency before deduping can make rate limits worse.

## Recommended Implementation Order

1. Add lightweight timing around major stages so before/after runtime is measurable.
2. Reuse Yahoo snapshots across DCF, comps, TTM, overview, and discovery.
3. Memoize Yahoo data inside each ticker path.
4. Convert Mongo per-record writes to bulk writes.
5. Load and write MarketScreener cache once per run.
6. Reuse HTTP sessions.
7. Reduce nested executor churn.
8. Tune concurrency based on measured bottlenecks.

## Non-Goals

- Do not remove existing output fields.
- Do not add new scrape modes.
- Do not silently replace missing data with fabricated defaults.
- Do not weaken existing failure visibility.
- Do not optimize by skipping required sources.
