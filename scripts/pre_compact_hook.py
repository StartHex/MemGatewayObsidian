#!/usr/bin/env python3
"""PreCompact hook: save session transcript before context compression.

Flow:
  1. Read conversation summary from stdin
  2. POST /api/v1/system/transcript/save → save to _agent-logs/
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request

API = os.environ.get("MEMORY_OS_API", "http://127.0.0.1:9090")


def _api(method: str, path: str, body: dict) -> dict | None:
    url = f"{API}{path}"
    data = json.dumps(body).encode()
    try:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[pre-compact-hook] API call failed: {method} {path}: {e}", file=sys.stderr)
        return None


def main():
    stdin_data = sys.stdin.read().strip()
    if not stdin_data:
        print("[pre-compact-hook] No stdin data, skipping", file=sys.stderr)
        return

    # Claude Code passes conversation summary in the hook data
    try:
        data = json.loads(stdin_data)
    except json.JSONDecodeError:
        data = {"raw": stdin_data[:5000]}

    payload = {
        "content": json.dumps(data, ensure_ascii=False)[:50000],
        "metadata": {
            "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            "message_count": data.get("message_count", 0) if isinstance(data, dict) else 0,
        },
    }

    result = _api("POST", "/api/v1/system/transcript/save", payload)
    if result and result.get("saved"):
        print(f"[pre-compact-hook] Transcript saved: {result.get('file')}", file=sys.stderr)


if __name__ == "__main__":
    main()
