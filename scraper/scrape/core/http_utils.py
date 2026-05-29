import concurrent.futures
import threading
import time

import numpy as np
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrape.core.config import MAX_WORKERS, REQUEST_TIMEOUT_SECONDS, headers

_THREAD_LOCAL = threading.local()


def request_get(url, **kwargs):
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _THREAD_LOCAL.session = session
    return session.get(url, **kwargs)


def curl_request_get(url, **kwargs):
    session = getattr(_THREAD_LOCAL, "curl_session", None)
    if session is None:
        session = curl_requests.Session(impersonate="chrome")
        _THREAD_LOCAL.curl_session = session
    kwargs.setdefault("impersonate", "chrome")
    return session.get(url, **kwargs)


def setup_proxies():
    response = request_get(
        "https://www.sslproxies.org/",
        headers={
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    proxies = []
    soup = BeautifulSoup(response.text, "html.parser")
    for row in soup.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) == 0:
            continue
        proxies.append({"ip": tds[0].string, "port": tds[1].string})
    proxies = [f"{x['ip']}:{x['port']}" for x in proxies if x["ip"] and x["port"]]
    proxies = [x for x in proxies if "-" not in x]  # remove date
    proxies = [x for x in proxies if len(x.split(":")) == 2 and len(x.split(".")) == 4]
    return proxies


PROXIES = setup_proxies()


def get_proxy():
    if len(PROXIES) == 0:
        return None
    idx = np.random.randint(0, len(PROXIES))
    return {"http": PROXIES[idx], "https": PROXIES[idx]}


def fetch_html(url, retries=2, sleep_seconds=10, use_proxy=False, use_curl=False):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            proxies = get_proxy() if use_proxy else None
            getter = curl_request_get if use_curl else request_get
            return getter(url, headers=headers, proxies=proxies, timeout=REQUEST_TIMEOUT_SECONDS).text
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("fetch_html exhausted retries with no exception")


def get_htmls(urls, use_proxy=False, workers=MAX_WORKERS, use_curl=False):
    html_responses = []
    for i in range(0, len(urls), workers):
        batch = urls[i : i + workers]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(batch))) as executor:
            batch_htmls = list(executor.map(lambda u: fetch_html(u, use_proxy=use_proxy, use_curl=use_curl), batch))
            html_responses.extend(batch_htmls)
        time.sleep(1)
    return html_responses


def run_with_timeout(func, timeout_seconds, *args, **kwargs):
    result = {}
    error = {}

    def target():
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as e:
            error["value"] = e

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive():
        raise TimeoutError(f"Timed out after {timeout_seconds} seconds")
    if "value" in error:
        raise error["value"]
    return result.get("value")
