#!/usr/bin/env python3
"""Stop hook: update hot.md and print session summary statistics.

Flow:
  1. POST /api/v1/system/hot/update → regenerate hot.md
  2. GET /api/v1/system/stats → print session summary
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request

API = os.environ.get("MEMORY_OS_API", "http://127.0.0.1:9090")


def _api(method: str, path: str, body: dict | None = None) -> dict | None:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[stop-hook] API call failed: {method} {path}: {e}", file=sys.stderr)
        return None


def main():
    # Read session context from stdin if available
    stdin_data = sys.stdin.read().strip()
    session_info = {}
    if stdin_data:
        try:
            session_info = json.loads(stdin_data)
        except json.JSONDecodeError:
            pass

    # Step 1: Update hot.md
    result = _api("POST", "/api/v1/system/hot/update")
    if result:
        print(f"[stop-hook] hot.md updated", file=sys.stderr)

    # Step 2: Print session summary from stats
    stats = _api("GET", "/api/v1/system/stats")
    if stats:
        print("\n[MEMORY OS SESSION SUMMARY]")
        print(f"  Active memories:  {stats.get('active', '?')}")
        print(f"  Fading memories:  {stats.get('fading', '?')}")
        print(f"  Total tracked:    {stats.get('total', '?')}")
        print(f"  Pending inbox:    {stats.get('inbox_pending', '?')}")


if __name__ == "__main__":
    main()
