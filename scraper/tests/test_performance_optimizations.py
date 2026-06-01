import concurrent.futures
import json
import logging
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, call, patch

import numpy as np

import main
from scrape.core import http_utils
from scrape.core.rate_limit import RateLimiter
from scrape.core.tickers import _is_common_operating_stock
from scrape.sources import marketscreener, yahoo_profiles, yahoo_snapshot
from scrape.valuation import dcf_inputs, string_mapper


class _Collection:
    def bulk_write(self, *args, **kwargs):
        pass

    def update_one(self, *args, **kwargs):
        pass


class _Database:
    def __getitem__(self, key):
        return _Collection()


class _Client:
    def __getitem__(self, key):
        return _Database()


class _Mapper:
    def __init__(self, values):
        pass


class _Response:
    status_code = 200
    text = "ok"

    def raise_for_status(self):
        pass


class _HtmlResponse(_Response):
    def __init__(self, content, url):
        self.content = content.encode()
        self.text = content
        self.url = url


class PerformanceOptimizationTests(unittest.TestCase):
    def test_dcf_scrape_refills_worker_slots_without_waiting_for_batch_straggler(self):
        started = {}
        finished = {}
        lock = threading.Lock()
        durations = {0: 0.15, 1: 0.01, 2: 0.01}

        def process_ticker(ticker, *args, **kwargs):
            with lock:
                started[ticker] = time.monotonic()
            time.sleep(durations[ticker])
            with lock:
                finished[ticker] = time.monotonic()
            return True, {"ticker": ticker}, None, None, None

        with (
            patch.object(main, "DCF_MAX_WORKERS", 2),
            patch.object(main, "StringMapper", _Mapper),
            patch.object(main, "get_country_erp", return_value={"Global": 0.0}),
            patch.object(main, "get_industry_avgs", return_value={"Unlevered Beta": {}}),
            patch.object(main, "get_10year_tbill", return_value=0.0),
            patch.object(main, "get_mature_erp", return_value=0.0),
            patch.object(main, "get_exchange_rates", return_value={}),
            patch.object(main, "process_ticker", process_ticker),
        ):
            main.run_dcf_scrape([0, 1, 2], _Client())

        self.assertCountEqual(started, [0, 1, 2])
        self.assertLess(started[2], finished[0])

    def test_ticker_chunks_cover_the_full_list_without_overlap(self):
        tickers = list(range(4206))
        chunks = []
        for chunk_index in range(5):
            with patch.dict(
                os.environ,
                {"SCRAPE_CHUNK_COUNT": "5", "SCRAPE_CHUNK_INDEX": str(chunk_index)},
            ):
                chunks.append(main._get_ticker_chunk(tickers))

        self.assertEqual([len(chunk) for chunk in chunks], [842, 842, 842, 842, 838])
        self.assertEqual([ticker for chunk in chunks for ticker in chunk], tickers)

    def test_fixed_size_ticker_chunks_keep_overflow_partition_small(self):
        tickers = list(range(4643))
        chunks = []
        for chunk_index in range(6):
            with patch.dict(
                os.environ,
                {
                    "SCRAPE_CHUNK_COUNT": "6",
                    "SCRAPE_CHUNK_INDEX": str(chunk_index),
                    "SCRAPE_CHUNK_SIZE": "900",
                },
            ):
                chunks.append(main._get_ticker_chunk(tickers))

        self.assertEqual([len(chunk) for chunk in chunks], [900, 900, 900, 900, 900, 143])
        self.assertEqual([ticker for chunk in chunks for ticker in chunk], tickers)

    def test_fixed_size_ticker_chunks_fail_when_capacity_is_exceeded(self):
        with patch.dict(
            os.environ,
            {
                "SCRAPE_CHUNK_COUNT": "6",
                "SCRAPE_CHUNK_INDEX": "0",
                "SCRAPE_CHUNK_SIZE": "900",
            },
        ):
            with self.assertRaisesRegex(ValueError, "exceeds configured scrape chunk capacity"):
                main._get_ticker_chunk(list(range(5401)))

    def test_common_stock_filter_does_not_exclude_valid_symbol_suffixes(self):
        for ticker in ["MU", "ACMR", "ACIW"]:
            with self.subTest(ticker=ticker):
                self.assertTrue(_is_common_operating_stock(ticker, f"{ticker} Inc. - Common Stock", "N", "N"))

    def test_common_stock_filter_excludes_derivatives_by_security_name(self):
        for ticker, name in [
            ("AACBU", "Artius II Acquisition Inc. - Units"),
            ("AACBR", "Artius II Acquisition Inc. - Rights"),
            ("AACIW", "Armada Acquisition Corp. III - Warrant"),
        ]:
            with self.subTest(ticker=ticker):
                self.assertFalse(_is_common_operating_stock(ticker, name, "N", "N"))

    def test_sector_industry_scrape_can_be_deferred_to_the_final_chunk(self):
        with patch.object(main, "get_sector_industries") as get_sector_industries:
            main.run_market_discovery_scrape([], _Client(), include_sector_industries=False)

        get_sector_industries.assert_not_called()

    def test_marketscreener_requests_are_paced_and_reuse_sessions(self):
        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait") as wait,
            patch.object(marketscreener, "browser_get", return_value=_Response()) as browser_get,
        ):
            marketscreener._marketscreener_get("https://example.com")

        wait.assert_called_once_with(None)
        browser_get.assert_called_once_with("https://example.com", impersonate="chrome124")

    def test_marketscreener_retry_resets_reused_session(self):
        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait"),
            patch.object(marketscreener, "browser_get", side_effect=[RuntimeError("failed"), _Response()]),
            patch.object(marketscreener, "reset_browser_session") as reset_browser_session,
            patch.object(marketscreener.time, "sleep"),
        ):
            marketscreener._marketscreener_get("https://example.com")

        reset_browser_session.assert_called_once_with()

    def test_marketscreener_invalid_forecast_page_is_retried(self):
        url = "https://example.com/quote/A/finances/"
        valid_html = """
            <div class="card extra card--collapsible mb-15">
                <div class="card-header extra">Projected Income Statement</div>
                <table><tr><th>Metric</th><th>2025</th></tr></table>
            </div>
        """
        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait"),
            patch.object(
                marketscreener,
                "browser_get",
                side_effect=[_HtmlResponse("<html></html>", url), _HtmlResponse(valid_html, url)],
            ) as browser_get,
            patch.object(marketscreener, "reset_browser_session") as reset_browser_session,
            patch.object(marketscreener.time, "sleep"),
        ):
            response = marketscreener._marketscreener_get(
                url,
                validator=marketscreener._validate_revenue_forecast_page,
            )

        self.assertEqual(response.text, valid_html)
        self.assertEqual(browser_get.call_count, 2)
        reset_browser_session.assert_called_once_with()

    def test_marketscreener_forecast_section_allows_additional_card_classes(self):
        soup = marketscreener.BeautifulSoup(
            """
            <div class="extra mb-15 card card--collapsible">
                <div class="extra card-header">Projected Income Statement</div>
                <table><tr><th>Metric</th><th>2025</th></tr></table>
            </div>
            """,
            "lxml",
        )

        card, table = marketscreener._forecast_income_statement_section(soup)

        self.assertIsNotNone(card)
        self.assertIsNotNone(table)

    def test_marketscreener_historical_only_redirect_is_retried_and_not_used_as_forecast(self):
        url = "https://example.com/quote/A/"
        response = _HtmlResponse(
            "<html></html>",
            "https://example.com/quote/A/finances-income-statement/",
        )
        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait"),
            patch.object(marketscreener, "browser_get", return_value=response) as browser_get,
            patch.object(marketscreener, "reset_browser_session") as reset_browser_session,
            patch.object(marketscreener.time, "sleep"),
        ):
            with self.assertRaisesRegex(
                marketscreener.MarketScreenerForecastUnavailable,
                "no analyst forecast page",
            ):
                marketscreener.get_revenue_forecasts(url)

        self.assertEqual(browser_get.call_count, marketscreener.MARKETSCREENER_RETRIES)
        self.assertEqual(reset_browser_session.call_count, marketscreener.MARKETSCREENER_RETRIES - 1)

    def test_marketscreener_forecast_redirect_can_recover_after_session_reset(self):
        url = "https://example.com/quote/A/finances/"
        redirected = _HtmlResponse("<html></html>", "https://example.com/quote/A/")
        valid_html = """
            <div class="card">
                <div class="card-header">Projected Income Statement</div>
                <table><tr><th>Metric</th><th>2025</th></tr></table>
            </div>
        """
        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait"),
            patch.object(
                marketscreener,
                "browser_get",
                side_effect=[redirected, _HtmlResponse(valid_html, url)],
            ) as browser_get,
            patch.object(marketscreener, "reset_browser_session") as reset_browser_session,
            patch.object(marketscreener.time, "sleep"),
        ):
            response = marketscreener._marketscreener_get(
                url,
                validator=marketscreener._validate_revenue_forecast_page,
            )

        self.assertEqual(response.text, valid_html)
        self.assertEqual(browser_get.call_count, 2)
        reset_browser_session.assert_called_once_with()

    def test_marketscreener_restored_url_cache_avoids_search_request(self):
        with (
            patch.object(marketscreener, "_MARKETSCREENER_CACHE", {"A": "https://example.com/quote/A/"}),
            patch.object(marketscreener, "_MARKETSCREENER_CACHE_LOADED", True),
            patch.object(marketscreener, "_marketscreener_search") as search,
        ):
            self.assertEqual(marketscreener.get_marketscreener_url("A"), "https://example.com/quote/A/")

        search.assert_not_called()

    def test_marketscreener_url_cache_is_checkpointed_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = os.path.join(temp_dir, "marketscreener_links.json")
            with (
                patch.object(marketscreener, "_MARKETSCREENER_CACHE_FILE", cache_file),
                patch.object(marketscreener, "_MARKETSCREENER_CACHE", {}),
                patch.object(marketscreener, "_MARKETSCREENER_CACHE_LOADED", True),
                patch.object(marketscreener, "_MARKETSCREENER_CACHE_DIRTY", False),
                patch.object(marketscreener, "_MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE", 0),
                patch.object(marketscreener, "_MARKETSCREENER_CACHE_SAVE_INTERVAL", 2),
                patch.object(marketscreener, "_marketscreener_search", side_effect=lambda ticker, _query, _cancel_event: f"https://example.com/{ticker}/"),
            ):
                marketscreener.get_marketscreener_url("A")
                self.assertFalse(os.path.exists(cache_file))
                marketscreener.get_marketscreener_url("B")

            with open(cache_file) as f:
                self.assertEqual(json.load(f), {"A": "https://example.com/A/", "B": "https://example.com/B/"})
            self.assertFalse(os.path.exists(cache_file + ".tmp"))

    def test_proxy_list_is_loaded_only_when_proxy_mode_is_used(self):
        with (
            patch.object(http_utils, "setup_proxies", return_value=[]) as setup_proxies,
            patch.object(http_utils, "PROXIES", None),
        ):
            self.assertIsNone(http_utils.get_proxy())
            self.assertIsNone(http_utils.get_proxy())

        setup_proxies.assert_called_once_with()

    def test_browser_get_uses_impersonated_browser_headers_by_default(self):
        session = Mock()
        with patch.object(http_utils, "_browser_session", return_value=session):
            http_utils.browser_get("https://example.com")

        session.get.assert_called_once_with(
            "https://example.com",
            impersonate="chrome124",
            timeout=http_utils.REQUEST_TIMEOUT_SECONDS,
        )

    def test_ttm_financials_reuses_prefetched_sec_data(self):
        prefetched = {"Ticker": "A", "Revenue TTM": 123}
        with (
            patch.object(yahoo_profiles, "_get_sec_ttm_financials_with_fallback") as get_sec_financials,
            patch.object(yahoo_profiles, "YAHOO_INFO_MAX_WORKERS", 1),
        ):
            result = yahoo_profiles.compute_ttm_financials(
                ["A"],
                yahoo_snapshots={"A": Mock(quarterly_income_stmt=yahoo_profiles.pd.DataFrame())},
                sec_financials_by_ticker={"A": prefetched},
            )

        get_sec_financials.assert_not_called()
        self.assertEqual(result.loc["A", "Revenue TTM"], 123)

    def test_ttm_financials_does_not_pause_between_snapshot_only_batches(self):
        snapshots = {
            ticker: Mock(quarterly_income_stmt=yahoo_profiles.pd.DataFrame())
            for ticker in ["A", "B"]
        }
        with (
            patch.object(yahoo_profiles, "YAHOO_INFO_MAX_WORKERS", 1),
            patch.object(yahoo_profiles.time, "sleep") as sleep,
        ):
            yahoo_profiles.compute_ttm_financials(
                ["A", "B"],
                yahoo_snapshots=snapshots,
                sec_financials_by_ticker={"A": {"Ticker": "A"}, "B": {"Ticker": "B"}},
            )

        sleep.assert_not_called()

    def test_sec_ttm_prefetch_stops_before_next_batch_when_cancelled(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch.object(yahoo_profiles, "_get_sec_ttm_financials_with_fallback") as get_sec_financials:
            result = yahoo_profiles.prefetch_sec_ttm_financials(["A"], cancelled)

        get_sec_financials.assert_not_called()
        self.assertEqual(result, {})

    def test_yahoo_snapshots_are_chunked_and_paced(self):
        with (
            patch.object(yahoo_snapshot, "YAHOOQUERY_BATCH_SIZE", 2),
            patch.object(yahoo_snapshot, "YAHOOQUERY_BATCH_SLEEP_SECONDS", 1),
            patch.object(
                yahoo_snapshot,
                "_get_yahoo_snapshot_batch",
                side_effect=lambda batch: {ticker: ticker for ticker in batch},
            ) as get_batch,
            patch.object(yahoo_snapshot.time, "sleep") as sleep,
        ):
            snapshots = yahoo_snapshot.get_yahoo_snapshots(["A", "B", "C", "D", "E"])

        self.assertEqual(snapshots, {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"})
        self.assertEqual(get_batch.call_args_list, [call(["A", "B"]), call(["C", "D"]), call(["E"])])
        self.assertEqual(sleep.call_args_list, [call(1), call(1)])

    def test_yahoo_snapshot_batch_limits_internal_workers(self):
        with (
            patch.object(yahoo_snapshot, "YAHOOQUERY_MAX_WORKERS", 4),
            patch.object(yahoo_snapshot, "Ticker", side_effect=RuntimeError("stop")) as ticker,
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                yahoo_snapshot._get_yahoo_snapshot_batch(["BRK.B"])

        ticker.assert_called_once_with(["BRK-B"], asynchronous=True, max_workers=4)

    def test_yahoo_snapshot_partial_batch_is_reported(self):
        with (
            patch.object(yahoo_snapshot, "YAHOOQUERY_BATCH_SIZE", 2),
            patch.object(yahoo_snapshot, "_get_yahoo_snapshot_batch", return_value={"A": "A"}),
        ):
            with self.assertLogs(yahoo_snapshot.logger, level="WARNING") as logs:
                yahoo_snapshot.get_yahoo_snapshots(["A", "B"])

        self.assertIn("1 of 2 snapshots collected", logs.output[0])
        self.assertIn("Yahoo snapshots missing for 1 out of 2 tickers", logs.output[1])

    def test_yahoo_snapshot_empty_batch_cools_down_and_retries_once(self):
        with (
            patch.object(yahoo_snapshot, "YAHOOQUERY_BATCH_SIZE", 2),
            patch.object(yahoo_snapshot, "YAHOOQUERY_FAILURE_COOLDOWN_SECONDS", 30),
            patch.object(yahoo_snapshot, "_get_yahoo_snapshot_batch", side_effect=[{}, {"A": "A", "B": "B"}]) as get_batch,
            patch.object(yahoo_snapshot.time, "sleep") as sleep,
        ):
            snapshots = yahoo_snapshot.get_yahoo_snapshots(["A", "B"])

        self.assertEqual(snapshots, {"A": "A", "B": "B"})
        self.assertEqual(get_batch.call_args_list, [call(["A", "B"]), call(["A", "B"])])
        sleep.assert_called_once_with(30)

    def test_yahoo_snapshot_repeated_empty_batches_abort_before_fallback(self):
        with (
            patch.object(yahoo_snapshot, "YAHOOQUERY_BATCH_SIZE", 2),
            patch.object(yahoo_snapshot, "YAHOOQUERY_BATCH_SLEEP_SECONDS", 1),
            patch.object(yahoo_snapshot, "YAHOOQUERY_FAILURE_COOLDOWN_SECONDS", 30),
            patch.object(yahoo_snapshot, "YAHOOQUERY_MAX_CONSECUTIVE_EMPTY_BATCHES", 2),
            patch.object(yahoo_snapshot, "_get_yahoo_snapshot_batch", return_value={}) as get_batch,
            patch.object(yahoo_snapshot.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(yahoo_snapshot.YahooSnapshotRejected, "stopping before database writes"):
                yahoo_snapshot.get_yahoo_snapshots(["A", "B", "C", "D", "E"])

        self.assertEqual(
            get_batch.call_args_list,
            [call(["A", "B"]), call(["A", "B"]), call(["C", "D"]), call(["C", "D"])],
        )
        self.assertEqual(sleep.call_args_list, [call(30), call(1), call(30)])

    def test_timeout_signals_cooperative_cancellation(self):
        cancelled = threading.Event()

        def wait_for_cancel(cancel_event):
            cancel_event.wait()
            cancelled.set()

        with self.assertRaises(TimeoutError):
            http_utils.run_with_timeout(wait_for_cancel, 0.01, cancel_event_kwarg="cancel_event")

        self.assertTrue(cancelled.wait(0.2))

    def test_completed_future_is_read_after_polling_timeout_race(self):
        future = Mock()
        future.result.side_effect = [concurrent.futures.TimeoutError(), "result"]
        future.done.return_value = True

        self.assertEqual(dcf_inputs._future_result(future, threading.Event()), "result")

    def test_cancelled_rate_limiter_wait_does_not_start_request(self):
        cancel_event = threading.Event()
        limiter = RateLimiter(10)
        limiter.wait()
        cancel_event.set()

        with self.assertRaises(TimeoutError):
            limiter.wait(cancel_event)

    def test_cancelled_marketscreener_request_does_not_call_remote(self):
        cancel_event = threading.Event()
        cancel_event.set()

        with patch.object(marketscreener, "browser_get") as browser_get:
            with self.assertRaises(TimeoutError):
                marketscreener._marketscreener_get("https://example.com", cancel_event)

        browser_get.assert_not_called()

    def test_marketscreener_response_returned_after_cancel_is_discarded(self):
        cancel_event = threading.Event()

        def cancel_during_request(*args, **kwargs):
            cancel_event.set()
            return _Response()

        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait"),
            patch.object(marketscreener, "browser_get", side_effect=cancel_during_request),
        ):
            with self.assertRaises(TimeoutError):
                marketscreener._marketscreener_get("https://example.com", cancel_event)

    def test_timed_out_ticker_signals_dcf_cancellation(self):
        cancelled = threading.Event()

        def wait_for_cancel(*args, cancel_event):
            cancel_event.wait()
            cancelled.set()

        with (
            patch.object(main, "TICKER_TIMEOUT_SECONDS", 0.01),
            patch.object(main, "get_dcf_inputs", side_effect=wait_for_cancel),
        ):
            success, dcf_inputs, yahoo_profile, yahoo_overview, failure_reason = main.process_ticker(
                "A", {}, None, {}, None, 0, 0, {}
            )

        self.assertFalse(success)
        self.assertIsNone(dcf_inputs)
        self.assertIsNone(yahoo_profile)
        self.assertIsNone(yahoo_overview)
        self.assertEqual(failure_reason, "timeout")
        self.assertTrue(cancelled.wait(0.2))

    def test_string_mappers_reuse_the_same_transformer_model(self):
        model = Mock()
        model.encode.side_effect = lambda values, **kwargs: np.ones((len(values), 2))
        string_mapper._get_model.cache_clear()

        try:
            with patch.object(string_mapper, "SentenceTransformer", return_value=model) as sentence_transformer:
                first = string_mapper.StringMapper(["Global"])
                second = string_mapper.StringMapper(["Technology"])

            self.assertIs(first.model, second.model)
            sentence_transformer.assert_called_once_with("Alibaba-NLP/gte-base-en-v1.5", trust_remote_code=True)
        finally:
            string_mapper._get_model.cache_clear()

    def test_string_mapper_caches_duplicate_embedding_lookups(self):
        model = Mock()
        model.encode.side_effect = [
            np.array([[1.0, 0.0], [0.0, 1.0]]),
            np.array([1.0, 0.0]),
            np.array([0.0, 1.0]),
        ]
        string_mapper._get_model.cache_clear()

        try:
            with patch.object(string_mapper, "SentenceTransformer", return_value=model):
                mapper = string_mapper.StringMapper(["Alpha", "Beta"])
                first = mapper.get_closest("Gamma")
                second = mapper.get_closest("Gamma")
                first_scores = mapper.get_closest_with_scores("Delta", indices_to_adjust=[1])
                second_scores = mapper.get_closest_with_scores("Delta", indices_to_adjust=[1])

            self.assertEqual(first, second)
            self.assertIsNot(first, second)
            self.assertEqual(first_scores, second_scores)
            self.assertIsNot(first_scores, second_scores)
            self.assertEqual(model.encode.call_count, 3)
        finally:
            string_mapper._get_model.cache_clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
