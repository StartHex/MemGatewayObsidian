#!/usr/bin/env python3
"""PostToolUse hook: validate .md files written to the vault.

Flow:
  1. Read tool call info from stdin (Claude Code passes hook data as JSON)
  2. If a .md file was written in the vault, call POST /api/v1/system/validate
  3. Log validation results to _meta/validation-log.md
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request

API = os.environ.get("MEMORY_OS_API", "http://127.0.0.1:9090")
VAULT = os.environ.get("MEMORY_OS_VAULT", os.path.expanduser("~/memory-vault"))


def _api(method: str, path: str, body: dict | None = None) -> dict | None:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[post-tool-hook] API call failed: {method} {path}: {e}", file=sys.stderr)
        return None


def extract_written_md_files(stdin_data: str) -> list[str]:
    """Extract paths of .md files written by the tool from hook data."""
    if not stdin_data.strip():
        return []
    paths = []
    try:
        data = json.loads(stdin_data)
    except json.JSONDecodeError:
        return []

    # Claude Code hook format: {"tool_name": "...", "tool_input": {...}, "tool_output": "..."}
    tool_input = data.get("tool_input", {})
    tool_output = data.get("tool_output", "")

    # Check common file-writing params
    for key in ("file_path", "path", "notebook_path", "to"):
        if key in tool_input:
            p = str(tool_input[key])
            if p.endswith(".md") and VAULT in p:
                paths.append(os.path.relpath(p, VAULT))

    # Also check Write/Edit tool output for file path
    if isinstance(tool_output, str) and VAULT in tool_output:
        for line in tool_output.split("\n"):
            if ".md" in line and VAULT in line:
                # Try to extract path
                import re
                match = re.search(rf"{re.escape(VAULT)}/\S+\.md", line)
                if match:
                    paths.append(os.path.relpath(match.group(), VAULT))

    return paths


def main():
    stdin_data = sys.stdin.read().strip()
    if not stdin_data:
        return

    md_files = extract_written_md_files(stdin_data)
    if not md_files:
        return

    for file_path in md_files:
        result = _api("POST", "/api/v1/system/validate", {"file_path": file_path})
        if result:
            status = "PASS" if result.get("valid") else "FAIL"
            issues = "; ".join(result.get("issues", [])) if not result.get("valid") else "none"
            print(f"[post-tool-hook] Validate {file_path}: {status} (issues: {issues})", file=sys.stderr)


if __name__ == "__main__":
    main()
