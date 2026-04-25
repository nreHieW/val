import yfinance as yf


def yahoo_ticker(symbol: str) -> yf.Ticker:
    """Use yfinance's default session (curl_cffi / TLS impersonation in 1.3+). Do not pass requests.Session."""
    return yf.Ticker(symbol)
