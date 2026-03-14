# 🎯 KalshiTracker

**Kalshi Prediction Market Portfolio Dashboard** — GitHub Pages site tracking trades, P&L, and equity curve.

## 🔗 Live Dashboard

**[→ https://appforgelabs.github.io/KalshiTracker/](https://appforgelabs.github.io/KalshiTracker/)**

## Features

- 📊 Real-time balance & P&L from Kalshi API
- 📈 Equity curve (Lightweight Charts)
- 🗂️ Trade history table with win/loss tracking
- 💼 Open positions view
- 🤖 Auto-updates daily via GitHub Actions

## Setup

### Local dev
```bash
pip install cryptography
python3 scripts/generate_dashboard.py
# Open index.html in browser
```

### GitHub Actions
Set the `KALSHI_PRIVATE_KEY` repository secret (raw PEM content of your Kalshi private key).

The pipeline runs daily at 06:00 UTC and auto-deploys to GitHub Pages.

## Data

- `dashboard_data.json` — Generated data file (auto-updated)
- `scripts/generate_dashboard.py` — Data pipeline script
