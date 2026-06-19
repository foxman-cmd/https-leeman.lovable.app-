# https-leeman.lovable.app-

A starter macro-engine scanner for trading — scaffold created by GitHub Copilot.

Contents
- src/: Python source
- requirements.txt: minimal dependencies

Quick start
1. Create a virtualenv: python -m venv .venv
2. pip install -r requirements.txt
3. Run small example (see src/engine/scanner.py)

Notes
- This is a minimal scaffold: implement secure credentials and paper/live execution adapters before any live trading.
- For higher-frequency signals (multiple per day), fetch intraday data using `fetch_prices(..., interval='5m'|'15m'|'1m')` and pick shorter rolling windows in `scan_universe`.

Send at 60% confidence
- To emit signals at a lower confidence (e.g., 60%), set the z-score threshold to 0.6. You can pass `threshold=0.6` to `scan_universe` or set `min_threshold=0.6` when using `target_min_signals_per_day` calibration.
