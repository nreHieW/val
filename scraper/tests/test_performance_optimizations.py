import concurrent.futures
import json
import logging
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

import main
from scrape.core import http_utils
from scrape.core.rate_limit import RateLimiter
from scrape.sources import marketscreener
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
