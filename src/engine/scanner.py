"""Starter scanner: simple momentum crossover with macro regime adjustment.

This file was extended to support intraday signals and an adjustable threshold calibration
so the scanner can produce a configurable minimum average signals per day (e.g., >N).

You asked to "send even at 60 confidence": to support this, the calibration minimum
threshold default has been adjusted and you can directly pass threshold=0.6 to emit
signals at z-score >= 0.6.
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, window: int):
    return series.rolling(window).mean()


def compute_macro_regime(macro_df: pd.DataFrame):
    """Very simple regime detector based on yield curve (10y - 2y) and VIX.
    Returns a Series of 1 (risk-on) or 0 (risk-off).
    """
    if macro_df is None or macro_df.empty:
        return None

    if '10y' not in macro_df.columns or '2y' not in macro_df.columns:
        # Fallback: if yields not available, assume risk-on
        return pd.Series(1, index=macro_df.index)

    yc = macro_df['10y'] - macro_df['2y']
    vix = macro_df.get('VIX', pd.Series(0, index=macro_df.index))
    regime = ((yc > yc.shift(1)) & (vix < 20)).astype(int)
    return regime


def _zscore(series: pd.Series, window: int = 252):
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    return (series - mean) / std


def _signals_from_z(z: pd.DataFrame, threshold: float = 1.0):
    """Produce signals in {-1,0,1} based on z-score threshold per column."""
    sig = z.copy().astype(float)
    sig[:] = 0.0
    sig[z > threshold] = 1.0
    sig[z < -threshold] = -1.0
    return sig


def _avg_signals_per_day(signals: pd.DataFrame):
    if signals.empty:
        return 0.0
    # group by date
    idx = signals.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.to_datetime(idx)
    daily_counts = signals.abs().sum(axis=1).groupby(idx.date).sum()
    return daily_counts.mean()


def calibrate_threshold(momentum_z: pd.DataFrame, target_min_signals_per_day: int, initial_threshold: float = 1.0, min_threshold: float = 0.6, step: float = 0.05):
    """Lower the threshold until the average signals/day >= target or min_threshold reached.

    NOTE: min_threshold default changed to 0.6 to allow "send at 60 confidence" behavior.
    """
    thr = initial_threshold
    while thr >= min_threshold:
        s = _signals_from_z(momentum_z, thr)
        avg = _avg_signals_per_day(s)
        if avg >= target_min_signals_per_day:
            return thr, s
        thr -= step
    # return last attempt
    return max(thr, min_threshold), _signals_from_z(momentum_z, max(thr, min_threshold))


def scan_universe(price_df: pd.DataFrame, macro_df: pd.DataFrame = None, window_short: int = 3, window_long: int = 12,
                  zscore_window: int = 252, threshold: float = 1.0, target_min_signals_per_day: int = None, min_threshold: float = 0.6):
    """
    price_df: DataFrame with columns = tickers, index = datetime (close prices), can be intraday
    macro_df: DataFrame with macro series aligned to same index (or resampled)
    window_short/window_long: integers (number of periods). For intraday use small windows (e.g., 3, 12 for 5m bars)
    zscore_window: window for z-score normalization (in periods). If intraday, pick shorter window (e.g., 1000)
    threshold: initial zscore threshold for signals
    target_min_signals_per_day: if set, the scanner will lower `threshold` until average signals/day >= target
    min_threshold: the lower bound of threshold reduction. Default 0.6 (60% confidence)

    returns: signals DataFrame with floats in {-1,0,1}
    """
    # compute short and long moving averages
    short = price_df.rolling(window_short).mean()
    long = price_df.rolling(window_long).mean()

    # momentum: relative difference
    momentum = (short - long) / long

    # convert to z-score per column
    momentum_z = momentum.apply(lambda col: _zscore(col.dropna(), window=zscore_window)).reindex(momentum.index)

    # If calibration requested, find threshold
    if target_min_signals_per_day is not None:
        chosen_threshold, signals = calibrate_threshold(momentum_z, target_min_signals_per_day, initial_threshold=threshold, min_threshold=min_threshold)
    else:
        chosen_threshold = threshold
        signals = _signals_from_z(momentum_z.fillna(0.0), threshold=chosen_threshold)

    # Apply macro regime: if regime==0 (risk-off) reduce signals toward 0 (half size)
    if macro_df is not None and not macro_df.empty:
        regime = compute_macro_regime(macro_df).reindex(signals.index).fillna(1)
        # multiply signals by regime factor (1 or 0.5)
        factor = pd.Series(1.0, index=signals.index)
        factor[regime == 0] = 0.5
        signals = signals.mul(factor, axis=0)

    # final: fill NaN with 0
    signals = signals.fillna(0.0)
    return signals


if __name__ == '__main__':
    # Example: fetch 5-minute SPY data for the last 7 days and generate signals aiming for 10 signals/day
    try:
        from src.data.fetchers import fetch_prices
    except Exception:
        fetch_prices = None

    if fetch_prices is not None:
        prices = fetch_prices('SPY', interval='5m', period='7d')  # 5-minute bars
        # synthetic macro: assume risk-on
        macro = None
        # Aim for 10 signals/day but allow lowering threshold down to 0.6 (60% confidence)
        sig = scan_universe(prices, macro, window_short=3, window_long=12, zscore_window=200, threshold=1.0, target_min_signals_per_day=10, min_threshold=0.6)
        print('Average signals/day:', _avg_signals_per_day(sig))
        print(sig.tail(20))
    else:
        print('Install dependencies and run this file to see a sample intraday scan.')
