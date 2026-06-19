"""Extended scanner that uses momentum zscore, ATR breakout, and RSI flip signals and combines them.

Exports:
- scan_with_extra_signals(...): returns dict of signals and combined signal

The combined logic uses weights and a vote threshold; tune weights to preference.
"""

import pandas as pd
from .scanner import scan_universe as base_scan
from src.features.indicators import rsi, atr, atr_breakout_signal, rsi_signal, combine_signals


def scan_with_extra_signals(price_df: pd.DataFrame, high: pd.Series = None, low: pd.Series = None, macro_df: pd.DataFrame = None,
                            window_short: int = 3, window_long: int = 12, zscore_window: int = 200, threshold: float = 1.0,
                            target_min_signals_per_day: int = None, min_threshold: float = 0.6,
                            atr_window: int = 14, atr_lookback: int = 20, atr_mult: float = 1.0,
                            rsi_window: int = 8, rsi_low: float = 30, rsi_high: float = 70,
                            weights: dict = None, vote_threshold: float = 0.5):
    """
    Generate momentum (zscore) signals via base_scan, plus ATR breakout and fast RSI signals, then combine.

    Returns dict:
    - 'momentum': DataFrame
    - 'atr': DataFrame
    - 'rsi': DataFrame
    - 'combined': DataFrame
    """
    # momentum signals (zscore-based)
    momentum = base_scan(price_df, macro_df=macro_df, window_short=window_short, window_long=window_long,
                         zscore_window=zscore_window, threshold=threshold, target_min_signals_per_day=target_min_signals_per_day, min_threshold=min_threshold)

    # For ATR and RSI computations we need high/low/close. If high/low not provided, approximate using close
    if high is None or low is None:
        high = price_df
        low = price_df

    # compute ATR per column (works with DataFrame)
    atr_df = atr(high, low, price_df, window=atr_window)

    # ATR breakout signals per ticker
    atr_signals = pd.DataFrame(0.0, index=price_df.index, columns=price_df.columns)
    rsi_signals = pd.DataFrame(0.0, index=price_df.index, columns=price_df.columns)

    for col in price_df.columns:
        atr_s = atr_df[col]
        atr_sig = atr_breakout_signal(price_df[col], high[col], low[col], atr_s, lookback=atr_lookback, mult=atr_mult)
        atr_signals[col] = atr_sig

        r = rsi(price_df[col], window=rsi_window)
        rsi_sig = rsi_signal(r, low=rsi_low, high=rsi_high)
        rsi_signals[col] = rsi_sig

    signals = {'momentum': momentum, 'atr': atr_signals, 'rsi': rsi_signals}

    if weights is None:
        weights = {'momentum': 1.0, 'atr': 1.0, 'rsi': 1.0}

    combined = combine_signals(signals, weights=weights, vote_threshold=vote_threshold)
    signals['combined'] = combined
    return signals

if __name__ == '__main__':
    # simple demo when the module is run directly
    try:
        from src.data.fetchers import fetch_prices
    except Exception:
        fetch_prices = None

    if fetch_prices is not None:
        prices = fetch_prices(['SPY', 'QQQ', 'IWM'], interval='5m', period='7d')
        # Use same price series for high/low (approx)
        s = scan_with_extra_signals(prices, high=prices, low=prices, window_short=3, window_long=12, zscore_window=200,
                                    atr_window=14, atr_lookback=20, atr_mult=1.0, rsi_window=8, weights={'momentum':1.0,'atr':1.0,'rsi':1.0}, vote_threshold=0.4)
        print('Avg signals/day (combined):', s['combined'].abs().sum(axis=1).groupby(s['combined'].index.date).sum().mean())
    else:
        print('Install dependencies and run this module to demo combined signals.')
