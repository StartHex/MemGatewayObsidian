#!/usr/bin/env python3
"""SessionStart hook: inject hot.md context at the start of each Claude Code session.

Flow:
  1. GET /api/v1/system/hot → fetch hot.md content
  2. Print to stdout so Claude Code injects it into the session context
  3. If no hot.md exists, print a minimal initialization message
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
    result = _api("GET", "/api/v1/system/hot")

    if result and result.get("content"):
        print("[MEMORY OS CONTEXT]")
        print(result["content"])
    elif result and result.get("generated"):
        # Initial generation succeeded
        print("[MEMORY OS CONTEXT]")
        print(result["content"])
    else:
        # No hot.md available — print minimal context
        vault = os.environ.get("MEMORY_OS_VAULT", os.path.expanduser("~/memory-vault"))
        print("[MEMORY OS CONTEXT]")
        print(f"Memory OS vault: {vault}")
        print("No memories indexed yet. Start a conversation to build your memory vault.")


if __name__ == "__main__":
    main()
