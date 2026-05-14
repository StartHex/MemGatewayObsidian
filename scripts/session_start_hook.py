#!/usr/bin/env python3
"""SessionStart hook: inject hot.md context + alert notifications at session start.

Flow:
  1. GET /api/v1/system/hot → fetch hot.md content
  2. GET /api/v1/system/alerts → fetch system alerts
  3. Print combined context to stdout for Claude Code injection
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request

API = os.environ.get("MEMORY_OS_API", "http://127.0.0.1:9090")


def _api(method: str, path: str) -> dict | None:
    url = f"{API}{path}"
    try:
        req = urllib.request.Request(url, method=method)
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[session-start-hook] API call failed: {method} {path}: {e}", file=sys.stderr)
        return None


def main():
    # Fetch hot.md for context
    hot = _api("GET", "/api/v1/system/hot")
    # Fetch system alerts
    alerts = _api("GET", "/api/v1/system/alerts")
    # Fetch latest review
    review = _api("GET", "/api/v1/system/review/latest")

    parts = ["[MEMORY OS CONTEXT]"]

    # 1. Alerts first if they need attention
    if alerts and alerts.get("file_exists") and alerts.get("level") != "OK":
        parts.append("\n## ⚠️ System Alerts")
        parts.append(alerts.get("content", "").strip())

    # 2. Latest review summary if available
    if review and review.get("found"):
        review_content = review.get("content", "")
        # Extract first 10 lines as summary
        lines = review_content.strip().split("\n")
        summary_lines = [l for l in lines if l.strip() and not l.startswith(">")][:10]
        parts.append(f"\n## 📝 最新复盘 ({review.get('date', 'unknown')})")
        parts.append("\n".join(summary_lines))

    # 3. Hot context
    if hot and hot.get("content"):
        parts.append(hot["content"])
    elif hot and hot.get("generated"):
        parts.append(hot["content"])
    else:
        vault = os.environ.get("MEMORY_OS_VAULT", os.path.expanduser("~/memory-vault"))
        parts.append(f"Memory OS vault: {vault}")
        parts.append("No memories indexed yet. Start a conversation to build your memory vault.")

    print("\n".join(parts))


if __name__ == "__main__":
    main()
