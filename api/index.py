from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf


app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/py/")
def read_root():
    return {"Status": "OK"}


@app.get("/api/py/history")
def get_history(ticker: str):
    ticker = yf.Ticker(ticker)
    out = ticker.history(period="6mo")["Close"].values
    return {"history": out.tolist()}
