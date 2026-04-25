import requests


def get_all_tickers():
    url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
    response = requests.get(url, timeout=30)
    return [ticker for ticker in response.text.split("\n") if ticker]
