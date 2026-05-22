# KalshiTracker

Kalshi command center for Jigar's bot stack.

## What it does

- **Grok** scores live Kalshi candidates from X/news before trades fire.
- **GPT** reviews the trade ledger, flags what’s working, and suggests tighter guardrails.
- **Dashboard** shows balance, win/loss, expectancy, open positions, recent opportunities, and strategy advice.

## Live site

<https://appforgelabs.github.io/KalshiTracker/>

## Data flow

```text
kalshi/run_scanner.py
  -> kalshi/place_trade.py logs trades
  -> kalshi/analytics.py builds performance_summary.json + strategy_advice.json
  -> KalshiTracker/scripts/generate_dashboard.py builds dashboard_data.json
  -> KalshiTracker/scripts/publish_dashboard.py commits/pushes the site
```

## Local refresh

```bash
cd /Users/sgtclaw/.openclaw/workspace/KalshiTracker
python3 scripts/publish_dashboard.py
```

Skip the GPT review pass if you just want a fast dashboard refresh:

```bash
python3 scripts/publish_dashboard.py --no-gpt
```

## Notes

- Local data from `../kalshi/data/` is the source of truth.
- GitHub Pages is the viewing layer, not the trading brain.
- The adaptive config is advisory for now. That’s intentional — tiny samples are where dumb overfitting is born.
