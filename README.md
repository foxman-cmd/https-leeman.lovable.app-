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
