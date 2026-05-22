"""Refresh analytics, rebuild dashboard payload, and optionally push to GitHub."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE_DIR = os.path.abspath(os.path.join(REPO_DIR, ".."))
KALSHI_DIR = os.path.join(WORKSPACE_DIR, "kalshi")


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-gpt", action="store_true", help="Skip the GPT strategy review refresh")
    parser.add_argument("--no-push", action="store_true", help="Do not commit/push repo changes")
    args = parser.parse_args()

    analytics = os.path.join(KALSHI_DIR, "analytics.py")
    generator = os.path.join(REPO_DIR, "scripts", "generate_dashboard.py")

    if os.path.exists(analytics):
        cmd = [sys.executable, analytics]
        if args.no_gpt:
            cmd = [sys.executable, "-c", "from analytics import refresh_analytics; refresh_analytics(run_gpt=False)"]
            run(cmd, cwd=KALSHI_DIR)
        else:
            run(cmd, cwd=KALSHI_DIR)

    run([sys.executable, generator], cwd=REPO_DIR)

    if args.no_push:
        return 0

    run(["git", "config", "user.email", "luka@appforgelabs.com"], cwd=REPO_DIR)
    run(["git", "config", "user.name", "Luka (KalshiTracker Bot)"], cwd=REPO_DIR)
    run(["git", "add", "dashboard_data.json", "performance_summary.json", "strategy_advice.json", "index.html", "scripts/generate_dashboard.py", "scripts/publish_dashboard.py", "README.md", ".github/workflows/pipeline.yml"], cwd=REPO_DIR)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR)
    if diff.returncode == 0:
        return 0

    run(["git", "commit", "-m", "📊 Update Kalshi tracker command center"], cwd=REPO_DIR)
    run(["git", "push"], cwd=REPO_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
