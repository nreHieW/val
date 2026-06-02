import threading

import requests
from curl_cffi import requests as curl_requests

from scrape.core.config import HEADERS, REQUEST_TIMEOUT_SECONDS


_SESSION_LOCAL = threading.local()


def _requests_session():
    session = getattr(_SESSION_LOCAL, "requests_session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
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


def request_get(url, **kwargs):
    return _requests_session().get(url, **kwargs)


def browser_get(url, **kwargs):
    return _browser_session().get(
        url,
        impersonate=kwargs.pop("impersonate", "chrome124"),
        timeout=kwargs.pop("timeout", REQUEST_TIMEOUT_SECONDS),
        **kwargs,
    )


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
    return result["value"]
