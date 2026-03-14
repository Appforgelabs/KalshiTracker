"""
generate_dashboard.py — KalshiTracker data pipeline
Reads trade_log.json + queries Kalshi API → writes dashboard_data.json
"""

import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# ── Config ────────────────────────────────────────────────────────────────────
KEY_ID = "15c58475-10f1-4a58-92e1-70820a1adb34"
BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Key loading: GitHub Actions passes KALSHI_PRIVATE_KEY env var; local uses PEM file
_env_key = os.environ.get("KALSHI_PRIVATE_KEY", "")
if _env_key:
    pem_data = _env_key.encode("utf-8")
    # Normalize: ensure proper PEM headers if env var is raw base64
    if not pem_data.strip().startswith(b"-----"):
        inner = _env_key.strip().replace(" ", "\n")
        pem_data = f"-----BEGIN RSA PRIVATE KEY-----\n{inner}\n-----END RSA PRIVATE KEY-----\n".encode()
else:
    _pem_path = os.environ.get(
        "KALSHI_PEM_PATH",
        "/Users/sgtclaw/.openclaw/workspace/data/kalshi-private.pem"
    )
    with open(_pem_path, "rb") as f:
        pem_data = f.read()

privkey = serialization.load_pem_private_key(pem_data, password=None)

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
KALSHI_DATA_DIR = os.path.join(REPO_DIR, "..", "kalshi", "data")
OUTPUT_FILE = os.path.join(KALSHI_DATA_DIR, "dashboard_data.json")
TRADE_LOG = os.path.join(KALSHI_DATA_DIR, "trade_log.json")


# ── Auth ──────────────────────────────────────────────────────────────────────
def _sign(text: str) -> str:
    sig = privkey.sign(
        text.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("utf-8")


def _auth_headers(method: str, path: str) -> dict:
    ts = str(int(time.time() * 1000))
    full_path = path if path.startswith("/trade-api/") else "/trade-api/v2" + path
    msg = ts + method.upper() + full_path
    sig = _sign(msg)
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
        "User-Agent": "KalshiTracker/1.0",
    }


def kalshi_get(path: str, params: str = "") -> dict:
    url = BASE + path
    if params:
        url += "?" + params
    headers = _auth_headers("GET", path)
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP {e.code} on {path}: {body}")


# ── API helpers ───────────────────────────────────────────────────────────────
def get_balance() -> float:
    resp = kalshi_get("/portfolio/balance")
    return resp.get("balance", 0) / 100.0


def get_positions() -> list:
    """Fetch open positions from Kalshi."""
    try:
        resp = kalshi_get("/portfolio/positions", "limit=100&settlement_status=unsettled")
        return resp.get("market_positions", [])
    except Exception as e:
        print(f"  ⚠️  Positions fetch failed: {e}")
        return []


def get_fills() -> list:
    """Fetch recent fills (completed trades)."""
    try:
        resp = kalshi_get("/portfolio/fills", "limit=200")
        return resp.get("fills", [])
    except Exception as e:
        print(f"  ⚠️  Fills fetch failed: {e}")
        return []


def get_market_info(ticker: str) -> dict:
    """Fetch market details for a ticker."""
    try:
        resp = kalshi_get(f"/markets/{ticker}")
        return resp.get("market", {})
    except Exception:
        return {}


# ── Trade log helpers ─────────────────────────────────────────────────────────
def load_trade_log() -> dict:
    if not os.path.exists(TRADE_LOG):
        return {"trades": [], "starting_balance": 100.74}
    with open(TRADE_LOG) as f:
        return json.load(f)


def compute_stats(trades: list, balance: float, starting_balance: float) -> dict:
    """Compute P&L stats from trade list."""
    wins = [t for t in trades if t.get("result") == "win"]
    losses = [t for t in trades if t.get("result") == "loss"]
    open_trades = [t for t in trades if t.get("result") == "open"]

    total_pnl = sum(t.get("pnl", 0) for t in trades)
    total_trades = len(wins) + len(losses)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
    total_return_pct = ((balance - starting_balance) / starting_balance * 100) if starting_balance > 0 else 0.0

    return {
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "open_positions": len(open_trades),
        "total_return_pct": round(total_return_pct, 2),
    }


def build_equity_curve(trades: list, starting_balance: float) -> list:
    """Build equity curve from trade history."""
    curve = []
    balance = starting_balance

    # Group by date
    from collections import defaultdict
    daily_pnl = defaultdict(float)
    for t in sorted(trades, key=lambda x: x.get("date", "")):
        date = t.get("date", "")[:10]
        pnl = t.get("pnl", 0)
        if date:
            daily_pnl[date] += pnl

    running = starting_balance
    if not daily_pnl:
        # Just show today
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return [{"date": today, "balance": round(starting_balance, 2)}]

    for date in sorted(daily_pnl.keys()):
        running += daily_pnl[date]
        curve.append({"date": date, "balance": round(running, 2)})

    return curve


def merge_fills_to_trades(fills: list, positions: list, log_trades: list) -> list:
    """
    Merge API fills with local trade log.
    Returns unified trade list for dashboard.
    """
    all_trades = []
    seen_ids = set()

    # From API fills
    for fill in fills:
        fill_id = fill.get("id", "")
        ticker = fill.get("market_ticker", "")
        side = fill.get("side", "")
        price_cents = fill.get("yes_price", fill.get("no_price", 50))
        count = fill.get("count", 0)
        created_time = fill.get("created_time", "")
        date = created_time[:10] if created_time else ""

        # Get market title
        market_title = fill.get("market_title", ticker)

        cost = round(price_cents / 100.0 * count, 2)
        trade_id = fill_id or f"{ticker}-{created_time}"

        if trade_id not in seen_ids:
            seen_ids.add(trade_id)
            all_trades.append({
                "id": trade_id,
                "date": date,
                "ticker": ticker,
                "title": market_title,
                "side": side,
                "price": round(price_cents / 100.0, 2),
                "contracts": count,
                "cost": cost,
                "result": "open",  # Will be updated when position resolves
                "pnl": 0.0,
                "source": "api",
            })

    # From local trade log
    for t in log_trades:
        trade_id = t.get("id", t.get("ticker", "") + t.get("date", ""))
        if trade_id not in seen_ids:
            seen_ids.add(trade_id)
            all_trades.append({
                "id": trade_id,
                "date": t.get("date", ""),
                "ticker": t.get("ticker", ""),
                "title": t.get("title", t.get("ticker", "")),
                "side": t.get("side", ""),
                "price": t.get("price", 0.0),
                "contracts": t.get("contracts", 0),
                "cost": t.get("cost", 0.0),
                "result": t.get("result", "open"),
                "pnl": t.get("pnl", 0.0),
                "source": "log",
            })

    # Sort by date desc
    all_trades.sort(key=lambda x: x.get("date", ""), reverse=True)
    return all_trades


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("🎯 KalshiTracker Dashboard Generator")
    print("=" * 50)

    # Fetch balance
    print("\n📊 Fetching account data...")
    try:
        balance = get_balance()
        print(f"  ✅ Balance: ${balance:.2f}")
    except Exception as e:
        print(f"  ❌ Balance error: {e}")
        balance = 0.0

    # Fetch positions and fills
    print("  Fetching positions...")
    positions = get_positions()
    print(f"  ✅ Open positions: {len(positions)}")

    print("  Fetching fills...")
    fills = get_fills()
    print(f"  ✅ Fills: {len(fills)}")

    # Load local trade log
    print("\n📂 Loading trade log...")
    log = load_trade_log()
    log_trades = log.get("trades", [])
    starting_balance = log.get("starting_balance", balance or 100.74)
    print(f"  ✅ Local trades: {len(log_trades)}, starting balance: ${starting_balance:.2f}")

    # Merge
    print("\n🔀 Merging data sources...")
    all_trades = merge_fills_to_trades(fills, positions, log_trades)
    print(f"  ✅ Total trades: {len(all_trades)}")

    # Stats
    stats = compute_stats(all_trades, balance, starting_balance)
    equity_curve = build_equity_curve(all_trades, starting_balance)

    # Add current balance point to equity curve
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if equity_curve and equity_curve[-1]["date"] != today:
        equity_curve.append({"date": today, "balance": round(balance, 2)})
    elif not equity_curve:
        equity_curve = [{"date": today, "balance": round(balance, 2)}]

    # Build output
    dashboard_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "balance": round(balance, 2),
        "starting_balance": round(starting_balance, 2),
        "total_return_pct": stats["total_return_pct"],
        "total_pnl": stats["total_pnl"],
        "win_rate": stats["win_rate"],
        "total_trades": stats["total_trades"],
        "wins": stats["wins"],
        "losses": stats["losses"],
        "open_positions": len(positions),
        "trades": all_trades,
        "equity_curve": equity_curve,
    }

    # Write output — two locations:
    # 1) kalshi/data/dashboard_data.json (canonical, for local dev)
    # 2) repo root dashboard_data.json (for GitHub Pages fetch fallback)
    os.makedirs(KALSHI_DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(dashboard_data, f, indent=2, default=str)

    # Also write to repo root for GitHub Pages
    root_output = os.path.join(REPO_DIR, "dashboard_data.json")
    with open(root_output, "w") as f:
        json.dump(dashboard_data, f, indent=2, default=str)

    print(f"\n✅ Dashboard data written:")
    print(f"   → {OUTPUT_FILE}")
    print(f"   → {root_output}")
    print(f"   Balance: ${balance:.2f} | P&L: ${stats['total_pnl']:+.2f} | Win rate: {stats['win_rate']:.1f}%")


if __name__ == "__main__":
    main()
