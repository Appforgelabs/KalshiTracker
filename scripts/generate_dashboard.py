"""Generate the KalshiTracker dashboard payload.

Local-first behavior:
- Prefer sibling ../kalshi/data/* files created by the live Grok bot.
- Fall back to repo-root copies when running in GitHub Actions.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DASHBOARD = os.path.join(REPO_DIR, "dashboard_data.json")
ROOT_PERF = os.path.join(REPO_DIR, "performance_summary.json")
ROOT_ADVICE = os.path.join(REPO_DIR, "strategy_advice.json")

LOCAL_DATA_DIR = os.path.abspath(os.path.join(REPO_DIR, "..", "kalshi", "data"))
LOCAL_PERF = os.path.join(LOCAL_DATA_DIR, "performance_summary.json")
LOCAL_ADVICE = os.path.join(LOCAL_DATA_DIR, "strategy_advice.json")
LOCAL_TRADE_LOG = os.path.join(LOCAL_DATA_DIR, "trade_log.json")
LOCAL_OPPS = os.path.join(LOCAL_DATA_DIR, "opportunities.json")
LOCAL_CONFIG = os.path.join(LOCAL_DATA_DIR, "strategy_config.json")


def load_json(preferred: str, fallback: str | None = None, default=None):
    default = {} if default is None else default
    for path in [preferred, fallback]:
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return default


def trade_log() -> list[dict]:
    data = load_json(LOCAL_TRADE_LOG, default=[])
    if isinstance(data, dict):
        return data.get("trades", [])
    return data if isinstance(data, list) else []


def open_positions(trades: list[dict]) -> list[dict]:
    rows = []
    for t in trades:
        if t.get("status") == "placed" and t.get("result") not in {"win", "loss"}:
            rows.append({
                "ticker": t.get("ticker"),
                "title": t.get("title", t.get("ticker")),
                "side": t.get("side"),
                "cost_dollars": t.get("cost_dollars", t.get("cost", 0)),
                "price": t.get("price", 0),
                "confidence": t.get("confidence", 0),
                "edge_pct": t.get("edge_pct", 0),
                "opened_at": t.get("date"),
                "signal_source": t.get("signal_source"),
                "metadata": t.get("metadata", {}),
            })
    rows.sort(key=lambda x: x.get("opened_at") or "", reverse=True)
    return rows[:15]


def latest_opportunities() -> list[dict]:
    payload = load_json(LOCAL_OPPS, default={"opportunities": []})
    opps = payload.get("opportunities", []) if isinstance(payload, dict) else []
    opps.sort(key=lambda x: (x.get("edge", 0), x.get("confidence", 0)), reverse=True)
    return opps[:12]


def copy_root_json(data: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    perf = load_json(LOCAL_PERF, ROOT_PERF, default={})
    advice = load_json(LOCAL_ADVICE, ROOT_ADVICE, default={})
    config = load_json(LOCAL_CONFIG, default={})
    trades = trade_log()
    open_trades = open_positions(trades)

    dashboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": "KalshiTracker",
            "tagline": "Grok trades. GPT audits. Dashboard keeps score.",
        },
        "account": perf.get("account", {}),
        "config": config or perf.get("config", {}),
        "heuristic": advice.get("heuristic", {}),
        "gpt_review": advice.get("gpt_review", {}),
        "families": perf.get("families", []),
        "models": perf.get("models", []),
        "strategies": perf.get("strategies", []),
        "confidence_buckets": perf.get("confidence_buckets", []),
        "edge_buckets": perf.get("edge_buckets", []),
        "equity_curve": perf.get("equity_curve", []),
        "recent_settled": perf.get("recent_settled", []),
        "open_positions": open_trades,
        "latest_opportunities": advice.get("latest_opportunities") or latest_opportunities(),
    }

    copy_root_json(dashboard, ROOT_DASHBOARD)
    copy_root_json(perf, ROOT_PERF)
    copy_root_json(advice, ROOT_ADVICE)

    print(json.dumps({
        "generated_at": dashboard["generated_at"],
        "settled_trades": dashboard["account"].get("settled_trades", 0),
        "open_trades": dashboard["account"].get("open_trades", 0),
        "gpt_review_status": dashboard["gpt_review"].get("status", "missing"),
    }, indent=2))


if __name__ == "__main__":
    main()
