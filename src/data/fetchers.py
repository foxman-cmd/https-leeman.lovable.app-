"""Basic data fetchers: price (yfinance) and macro (FRED).

These are minimal helpers to fetch historical data for prototyping.
"""

from datetime import datetime
import pandas as pd

try:
    import yfinance as yf
except Exception:
    yf = None

try:
    from fredapi import Fred
except Exception:
    Fred = None


def fetch_prices(tickers, start: str = "2000-01-01", end: str = None):
    """Fetch adjusted close prices for tickers using yfinance. Returns DataFrame indexed by date."""
    if yf is None:
        raise RuntimeError("yfinance not installed")
    end = end or datetime.today().strftime("%Y-%m-%d")
    data = yf.download(tickers, start=start, end=end, progress=False, group_by='ticker')
    if len(tickers) == 1 or isinstance(tickers, str):
        return data['Adj Close'].to_frame(tickers)
    else:
        return data['Adj Close']


def fetch_fred_series(series_id, api_key=None, start: str = "2000-01-01", end: str = None):
    """Fetch a FRED series by id. Requires FRED api key via fredapi or environment.
    Returns a Series indexed by date.
    """
    if Fred is None:
        raise RuntimeError("fredapi not installed")
    fred = Fred(api_key=api_key)
    end = end or datetime.today().strftime("%Y-%m-%d")
    s = fred.get_series(series_id, observation_start=start, observation_end=end)
    s.index = pd.to_datetime(s.index)
    return s
