"""Basic data fetchers: price (yfinance) and macro (FRED).

These are minimal helpers to fetch historical data for prototyping.

Improvements:
- Added `interval` support for intraday yfinance downloads.
- When intraday intervals are used, `period` can be provided instead of `start`/`end` (yfinance requirement for sub-daily data).
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


def fetch_prices(tickers, start: str = None, end: str = None, interval: str = '1d', period: str = None):
    """Fetch adjusted close prices for tickers using yfinance.

    Parameters:
    - tickers: str or list of tickers
    - start, end: date strings (YYYY-MM-DD) for daily data
    - interval: '1d', '1h', '30m', '15m', '5m', '1m' etc. (yfinance supported)
    - period: for intraday data, use period (e.g., '7d','30d') instead of start/end

    Returns DataFrame indexed by datetime with 'Adj Close' columns per ticker.
    """
    if yf is None:
        raise RuntimeError("yfinance not installed")

    # yfinance requires period for intraday intervals; for daily interval start/end work
    kwargs = { 'interval': interval, 'progress': False }
    if interval != '1d':
        if period is not None:
            kwargs['period'] = period
        else:
            # default to 30 days for intraday if no period provided
            kwargs['period'] = '30d'
    else:
        # daily: use start/end if provided
        if start is not None:
            kwargs['start'] = start
        if end is not None:
            kwargs['end'] = end

    data = yf.download(tickers, **kwargs, group_by='ticker')

    # yfinance returns different shapes for single vs multi tickers
    if isinstance(tickers, str) or (hasattr(tickers, '__len__') and len(tickers) == 1):
        # single ticker: data['Adj Close'] is a Series or DataFrame
        adj = data['Adj Close']
        if isinstance(adj, pd.Series):
            adj = adj.to_frame(name=tickers if isinstance(tickers, str) else tickers[0])
        return adj
    else:
        # multiple tickers: data['Adj Close'] is a DataFrame with columns per ticker
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
