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

MAX_WORKERS = 120
YAHOO_INFO_MAX_WORKERS = int(os.getenv("YAHOO_INFO_MAX_WORKERS", "8"))
YAHOO_INFO_RETRIES = int(os.getenv("YAHOO_INFO_RETRIES", "4"))
YAHOO_INFO_RETRY_SLEEP_SECONDS = float(os.getenv("YAHOO_INFO_RETRY_SLEEP_SECONDS", "5"))
REQUEST_TIMEOUT_SECONDS = 30
TICKER_TIMEOUT_SECONDS = int(os.getenv("TICKER_TIMEOUT_SECONDS", "300"))
FINVIZ_RETRIES = int(os.getenv("FINVIZ_RETRIES", "3"))
FINVIZ_RETRY_SLEEP_SECONDS = float(os.getenv("FINVIZ_RETRY_SLEEP_SECONDS", "2"))
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
