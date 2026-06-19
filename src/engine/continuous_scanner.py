"""Continuous scanner with confidence-based signal generation.

Runs the scanner in an infinite loop and emits signals when confidence reaches 60%.
Maintains all original scanner functionality.

Functions:
- calculate_signal_confidence
- emit_signal
- run_continuous_scanner
"""

import pandas as pd
import numpy as np
import time
from datetime import datetime
from src.engine.scanner import scan_universe, compute_macro_regime


def calculate_signal_confidence(signals: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Calculate confidence (C) for signals based on consistency over a rolling window.
    Confidence = percentage of time signal direction stays consistent.
    
    Args:
        signals: DataFrame with signal values
        window: rolling window size for confidence calculation
    
    Returns:
        DataFrame with confidence values (0.0 to 1.0)
    """
    confidence = pd.DataFrame(index=signals.index, columns=signals.columns, dtype=float)
    
    for col in signals.columns:
        signal_series = signals[col]
        rolling_signals = signal_series.rolling(window=window)
        
        # Calculate consistency: count direction matches in window
        consistent_count = rolling_signals.apply(
            lambda x: (np.sign(x) == np.sign(x.iloc[-1])).sum() if len(x) > 0 else 0
        )
        confidence[col] = consistent_count / window
    
    return confidence


def emit_signal(ticker: str, signal: float, confidence: float, timestamp: str):
    """
    Emit a trading signal when confidence >= 60%.
    
    Args:
        ticker: Asset ticker
        signal: Signal value (-1, 0, or 1)
        confidence: Confidence level (0.0 to 1.0)
        timestamp: Timestamp of signal
    """
    signal_dir = "BUY" if signal > 0 else "SELL" if signal < 0 else "NEUTRAL"
    confidence_pct = confidence * 100
    
    print(f"[SIGNAL] {timestamp} | {ticker} | {signal_dir} | Confidence: {confidence_pct:.2f}%")
    
    # Optional: Write to signal log file
    try:
        with open('signals_log.txt', 'a') as f:
            f.write(f"{timestamp} | {ticker} | {signal_dir} | Confidence: {confidence_pct:.2f}%\n")
    except Exception as e:
        print(f"[WARNING] Could not write to log: {e}")


def run_continuous_scanner(price_df: pd.DataFrame, macro_df: pd.DataFrame, 
                           confidence_threshold: float = 0.60, 
                           scan_interval: float = 60, 
                           window: int = 5):
    """
    Run the scanner continuously in an infinite loop.
    Emits signals when signal confidence reaches the threshold.
    
    Args:
        price_df: Historical price data (DataFrame)
        macro_df: Historical macro data (DataFrame)
        confidence_threshold: Confidence level required to emit signal (default 0.60 = 60%)
        scan_interval: Seconds to wait between scans (default 60)
        window: Rolling window for confidence calculation (default 5)
    """
    print(f"[INFO] Starting continuous scanner with {confidence_threshold*100:.0f}% confidence threshold")
    print(f"[INFO] Scan interval: {scan_interval}s | Confidence window: {window}")
    print("-" * 80)
    
    scan_count = 0
    signal_count = 0
    
    try:
        while True:
            scan_count += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"\n[SCAN #{scan_count}] {timestamp} - Running scanner...")
            
            # Run the scanner (keeps original functionality)
            signals = scan_universe(price_df, macro_df)
            
            # Calculate confidence for each asset
            confidence = calculate_signal_confidence(signals, window=window)
            
            # Get the latest signals and confidence values
            latest_signals = signals.iloc[-1]
            latest_confidence = confidence.iloc[-1]
            
            # Check each asset for signals at 60%+ confidence
            for ticker in latest_signals.index:
                sig_val = latest_signals[ticker]
                conf_val = latest_confidence[ticker]
                
                # Emit signal if confidence >= threshold
                if conf_val >= confidence_threshold and sig_val != 0:
                    signal_count += 1
                    emit_signal(ticker, sig_val, conf_val, timestamp)
            
            # Print summary
            print(f"[INFO] Scan complete: {len(latest_signals)} assets scanned")
            print(f"[INFO] Total signals emitted: {signal_count}")
            
            # Wait before next scan
            print(f"[INFO] Next scan in {scan_interval}s...")
            time.sleep(scan_interval)
    
    except KeyboardInterrupt:
        print(f"\n[STOP] Scanner stopped by user after {scan_count} scans and {signal_count} signals")
    except Exception as e:
        print(f"[ERROR] Scanner encountered error: {e}")
        raise


if __name__ == '__main__':
    try:
        from src.data.fetchers import fetch_prices
    except Exception:
        fetch_prices = None

    if fetch_prices is not None:
        print("Fetching price data...")
        prices = fetch_prices(['SPY', 'QQQ', 'IWM'], start='2020-01-01')
        
        # Create synthetic macro data
        macro = pd.DataFrame({
            '10y': np.random.uniform(1.0, 3.0, len(prices)),
            '2y': np.random.uniform(0.5, 2.5, len(prices)),
            'VIX': np.random.uniform(10, 30, len(prices))
        }, index=prices.index)
        
        # Run continuous scanner with 60% confidence threshold
        run_continuous_scanner(
            prices, 
            macro,
            confidence_threshold=0.60,
            scan_interval=10,  # 10 seconds between scans for testing
            window=5
        )
    else:
        print('Install dependencies and ensure fetchers.py exists to run this scanner.')
