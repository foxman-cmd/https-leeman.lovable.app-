"""Starter scanner: simple momentum crossover with macro regime adjustment.

Functions:
- sma
- compute_macro_regime
- scan_universe
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, window: int):
    return series.rolling(window).mean()


def compute_macro_regime(macro_df: pd.DataFrame):
    """Very simple regime detector based on yield curve (10y - 2y) and VIX.
    Returns a Series of 1 (risk-on) or 0 (risk-off).
    """
    if '10y' not in macro_df.columns or '2y' not in macro_df.columns:
        # Fallback: if yields not available, assume risk-on
        return pd.Series(1, index=macro_df.index)

    yc = macro_df['10y'] - macro_df['2y']
    vix = macro_df.get('VIX', pd.Series(0, index=macro_df.index))
    regime = ((yc > yc.shift(1)) & (vix < 20)).astype(int)
    return regime


def scan_universe(price_df: pd.DataFrame, macro_df: pd.DataFrame):
    """
    price_df: DataFrame with columns = tickers, index = datetime (close prices)
    macro_df: DataFrame with macro series aligned to same index (or resampled)
    returns: signals DataFrame with floats in [-1, 1]
    """
    short = price_df.rolling(20).mean()
    long = price_df.rolling(100).mean()
    raw_signal = (short > long).astype(int) - (short < long).astype(int)  # 1 if short>long, -1 if short<long

    regime = compute_macro_regime(macro_df).reindex(price_df.index).fillna(1)
    # Apply regime: if regime==0 (risk-off) reduce signals toward 0
    signals = raw_signal.astype(float).copy()
    signals[regime == 0] = raw_signal[regime == 0] * 0.5  # de-risk: half size in risk-off
    return signals


if __name__ == '__main__':
    # tiny example: fetch prices for SPY and compute signals using synthetic macro
    import pandas as pd
    try:
        from src.data.fetchers import fetch_prices
    except Exception:
        fetch_prices = None

    if fetch_prices is not None:
        prices = fetch_prices(['SPY'], start='2020-01-01')
        # simple macro: synthetic flat yields
        macro = pd.DataFrame({'10y': 1.5, '2y': 0.5}, index=prices.index)
        sig = scan_universe(prices, macro)
        print(sig.tail())
    else:
        print('Install dependencies and run this file to see a sample scan.')
