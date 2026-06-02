import os
import threading

from dotenv import load_dotenv

load_dotenv()

JSON_LOCK = threading.Lock()

HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
}

DCF_MAX_WORKERS = int(os.getenv("DCF_MAX_WORKERS", "16"))
MARKETSCREENER_MAX_WORKERS = int(os.getenv("MARKETSCREENER_MAX_WORKERS", "8"))
YAHOO_INFO_MAX_WORKERS = int(os.getenv("YAHOO_INFO_MAX_WORKERS", "25"))
YAHOOQUERY_BATCH_SIZE = int(os.getenv("YAHOOQUERY_BATCH_SIZE", "10"))
YAHOOQUERY_MAX_WORKERS = int(os.getenv("YAHOOQUERY_MAX_WORKERS", "4"))
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT") or f"Val financial scraper {os.getenv('SEC_CONTACT_EMAIL', 'contact@example.com')}"
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
