import os
import threading
import warnings

from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings("ignore")

JSON_LOCK = threading.Lock()

headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
}

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))
DCF_MAX_WORKERS = int(os.getenv("DCF_MAX_WORKERS", "16"))
MARKETSCREENER_MAX_WORKERS = int(os.getenv("MARKETSCREENER_MAX_WORKERS", "4"))
MARKETSCREENER_RETRIES = int(os.getenv("MARKETSCREENER_RETRIES", "3"))
MARKETSCREENER_RETRY_SLEEP_SECONDS = float(os.getenv("MARKETSCREENER_RETRY_SLEEP_SECONDS", "2"))
MARKETSCREENER_MIN_INTERVAL_SECONDS = float(os.getenv("MARKETSCREENER_MIN_INTERVAL_SECONDS", "2.0"))
MARKETSCREENER_JITTER_SECONDS = float(os.getenv("MARKETSCREENER_JITTER_SECONDS", "0.75"))
YAHOO_INFO_MAX_WORKERS = int(os.getenv("YAHOO_INFO_MAX_WORKERS", "25"))
YAHOOQUERY_BATCH_SIZE = int(os.getenv("YAHOOQUERY_BATCH_SIZE", "500"))
YAHOO_INFO_RETRIES = int(os.getenv("YAHOO_INFO_RETRIES", "3"))
YAHOO_INFO_RETRY_SLEEP_SECONDS = float(os.getenv("YAHOO_INFO_RETRY_SLEEP_SECONDS", "5"))
YAHOO_CALL_MAX_CONCURRENCY = int(os.getenv("YAHOO_CALL_MAX_CONCURRENCY", "2"))
YAHOO_CALL_MIN_INTERVAL_SECONDS = float(os.getenv("YAHOO_CALL_MIN_INTERVAL_SECONDS", "0.35"))
YAHOO_COOLDOWN_SECONDS = float(os.getenv("YAHOO_COOLDOWN_SECONDS", "30"))
YAHOO_FINANCIAL_MIN_INTERVAL_SECONDS = float(os.getenv("YAHOO_FINANCIAL_MIN_INTERVAL_SECONDS", "1.5"))
YAHOO_FINANCIAL_JITTER_SECONDS = float(os.getenv("YAHOO_FINANCIAL_JITTER_SECONDS", "0.5"))
REQUEST_TIMEOUT_SECONDS = 30
TICKER_TIMEOUT_SECONDS = int(os.getenv("TICKER_TIMEOUT_SECONDS", "300"))
CURRENCIES = {
    "ARS",
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CLP",
    "CNY",
    "COP",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "IDR",
    "ILS",
    "INR",
    "JPY",
    "KRW",
    "KZT",
    "MXN",
    "MYR",
    "PEN",
    "PHP",
    "SEK",
    "SGD",
    "TRY",
    "TWD",
    "USD",
    "VND",
    "ZAR",
}
