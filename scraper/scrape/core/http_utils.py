import concurrent.futures
import threading
import time

import numpy as np
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from scrape.core.config import MAX_WORKERS, REQUEST_TIMEOUT_SECONDS, headers


_SESSION_LOCAL = threading.local()


def _requests_session():
    session = getattr(_SESSION_LOCAL, "requests_session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(headers)
        _SESSION_LOCAL.requests_session = session
    return session


def _browser_session():
    session = getattr(_SESSION_LOCAL, "browser_session", None)
    if session is None:
        session = curl_requests.Session()
        _SESSION_LOCAL.browser_session = session
    return session


def reset_browser_session():
    session = getattr(_SESSION_LOCAL, "browser_session", None)
    if session is not None:
        session.close()
        del _SESSION_LOCAL.browser_session


def setup_proxies():
    response = _requests_session().get(
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


PROXIES = None


def get_proxy():
    global PROXIES
    if PROXIES is None:
        PROXIES = setup_proxies()
    if len(PROXIES) == 0:
        return None
    idx = np.random.randint(0, len(PROXIES))
    return {"http": PROXIES[idx], "https": PROXIES[idx]}


def request_get(url, **kwargs):
    request_headers = kwargs.pop("headers", headers)
    return _requests_session().get(url, headers=request_headers, **kwargs)


def browser_get(url, **kwargs):
    """GET a page using a real browser TLS fingerprint.

    Use this for sites that reject plain requests with bot-protection 403s.
    """
    request_headers = kwargs.pop("headers", headers)
    session = curl_requests.Session() if kwargs.pop("fresh_session", False) else _browser_session()
    return session.get(
        url,
        headers=request_headers,
        impersonate=kwargs.pop("impersonate", "chrome124"),
        timeout=kwargs.pop("timeout", REQUEST_TIMEOUT_SECONDS),
        **kwargs,
    )


def fetch_html(url, retries=2, sleep_seconds=10, use_proxy=False, browser=False):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            proxies = get_proxy() if use_proxy else None
            if browser:
                return browser_get(url, proxies=proxies).text
            return _requests_session().get(url, proxies=proxies, timeout=REQUEST_TIMEOUT_SECONDS).text
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("fetch_html exhausted retries with no exception")


def get_htmls(urls, use_proxy=False, workers=MAX_WORKERS, browser=False):
    html_responses = []
    for i in range(0, len(urls), workers):
        batch = urls[i : i + workers]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(batch))) as executor:
            batch_htmls = list(executor.map(lambda u: fetch_html(u, use_proxy=use_proxy, browser=browser), batch))
            html_responses.extend(batch_htmls)
        time.sleep(1)
    return html_responses


def run_with_timeout(func, timeout_seconds, *args, cancel_event_kwarg=None, **kwargs):
    result = {}
    error = {}
    cancel_event = threading.Event() if cancel_event_kwarg else None
    if cancel_event_kwarg:
        kwargs[cancel_event_kwarg] = cancel_event

    def target():
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as e:
            error["value"] = e

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive():
        if cancel_event is not None:
            cancel_event.set()
        raise TimeoutError(f"Timed out after {timeout_seconds} seconds")
    if "value" in error:
        raise error["value"]
    return result.get("value")
