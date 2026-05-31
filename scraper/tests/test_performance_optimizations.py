import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

import main
from scrape.core import http_utils
from scrape.sources import marketscreener
from scrape.valuation import string_mapper


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

    def test_proxy_list_is_loaded_only_when_proxy_mode_is_used(self):
        with (
            patch.object(http_utils, "setup_proxies", return_value=[]) as setup_proxies,
            patch.object(http_utils, "PROXIES", None),
        ):
            self.assertIsNone(http_utils.get_proxy())
            self.assertIsNone(http_utils.get_proxy())

        setup_proxies.assert_called_once_with()

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

    def test_marketscreener_requests_are_paced(self):
        with (
            patch.object(marketscreener._MARKETSCREENER_LIMITER, "wait") as wait,
            patch.object(marketscreener, "browser_get", return_value=_Response()),
        ):
            marketscreener._marketscreener_get("https://example.com")

        wait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
