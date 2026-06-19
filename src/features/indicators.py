"""Feature indicators: ATR, RSI, ATR breakout and RSI flip signals.

Provides:
- rsi(series, window)
- atr(high, low, close, window)
- atr_breakout_signal(close, high, low, atr, mult=1.0): 1 if price > prior_n_high + mult*ATR, -1 if price < prior_n_low - mult*ATR
- rsi_signal(rsi_series, low=30, high=70): 1 when RSI crosses above low, -1 when RSI crosses below high (fast mean-reversion/momentum variants)
- combine_signals: combine multiple signal DataFrames into a weighted final signal

These are designed for intraday usage with small windows.
"""

import pandas as pd
import numpy as np


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/window, adjust=False).mean()
    ma_down = down.ewm(alpha=1/window, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder's smoothing
    atr = tr.ewm(alpha=1/window, adjust=False).mean()
    return atr


def atr_breakout_signal(close: pd.Series, high: pd.Series, low: pd.Series, atr_series: pd.Series, lookback: int = 20, mult: float = 1.0) -> pd.Series:
    """Signal of 1 when close breaks above prior lookback high + mult*ATR, -1 for symmetric lower break.
    Uses prior lookback range (excluding current bar)."""
    prior_high = high.shift(1).rolling(lookback).max()
    prior_low = low.shift(1).rolling(lookback).min()
    upper = prior_high + mult * atr_series
    lower = prior_low - mult * atr_series
    s = pd.Series(0.0, index=close.index)
    s[close > upper] = 1.0
    s[close < lower] = -1.0
    return s


def rsi_signal(rsi_series: pd.Series, low: float = 30.0, high: float = 70.0) -> pd.Series:
    """Fast RSI flip signal: +1 when RSI crosses up above `low`, -1 when RSI crosses down below `high`.
    This emits short, fast signals appropriate to intraday use.
    """
    s = pd.Series(0.0, index=rsi_series.index)
    prev = rsi_series.shift(1)
    s[(prev <= low) & (rsi_series > low)] = 1.0
    s[(prev >= high) & (rsi_series < high)] = -1.0
    return s


def combine_signals(signals: dict, weights: dict = None, vote_threshold: float = 0.5) -> pd.DataFrame:
    """Combine multiple signal DataFrames (or Series) into a final signal per column.

    - signals: dict[name] = DataFrame or Series (index=DatetimeIndex, columns=tickers or scalar)
    - weights: dict[name] = weight (default 1.0)
    - vote_threshold: fraction of (sum weights) required to emit a signal (default 0.5)

    Returns DataFrame with combined signal in {-1,0,1} per ticker.
    """
    names = list(signals.keys())
    if weights is None:
        weights = {n: 1.0 for n in names}

    # Convert everything to DataFrame with same columns
    dfs = {}
    for n in names:
        v = signals[n]
        if isinstance(v, pd.Series):
            dfs[n] = v.to_frame(name=n)
        else:
            dfs[n] = v.copy()
            dfs[n].columns = [c for c in dfs[n].columns]

    # Reindex and align
    all_index = dfs[names[0]].index
    for d in dfs.values():
        all_index = all_index.union(d.index)
    aligned = {n: dfs[n].reindex(all_index).fillna(0.0) for n in names}

    # Sum weighted signals
    sum_weights = sum(weights.get(n, 1.0) for n in names)
    weighted = None
    for n in names:
        w = weights.get(n, 1.0)
        arr = aligned[n] * w
        if weighted is None:
            weighted = arr
        else:
            weighted = weighted.add(arr, fill_value=0.0)

    # Normalize by sum_weights and threshold
    normalized = weighted / max(sum_weights, 1e-9)
    final = pd.DataFrame(0.0, index=normalized.index, columns=normalized.columns)
    final[normalized > vote_threshold] = 1.0
    final[normalized < -vote_threshold] = -1.0
    return final
