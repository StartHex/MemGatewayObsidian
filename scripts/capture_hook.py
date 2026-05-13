#!/usr/bin/env python3
"""Claude Code hook: 每次对话前检索相关记忆 + 捕获当前消息到 Memory OS。

流程:
  1. POST /api/v1/search/inject-and-save → 有结果写入 last-context.md，无结果删除
  2. POST /api/v1/memories → 捕获消息到 inbox
"""
from __future__ import annotations

import os
import sys
import json
import urllib.request

API = os.environ.get("MEMORY_OS_API", "http://127.0.0.1:9090")
EVENT = os.environ.get("CLAUDE_HOOK_EVENT_TYPE", "unknown")


def _api(method: str, path: str, body: dict | None = None) -> dict | None:
    """Call the Memory OS API. Returns parsed JSON or None on failure."""
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[memory-hook] API call failed: {method} {path}: {e}", file=sys.stderr)
        return None


def search_and_inject(query: str, top_k: int = 3) -> dict | None:
    """检索相关记忆并写入 vault 的 last-context.md。"""
    result = _api("POST", "/api/v1/search/inject-and-save", {"query": query, "top_k": top_k})
    if result:
        if result.get("saved"):
            print(f"[memory-hook] Context saved: {result['result_count']} memories", file=sys.stderr)
        else:
            print("[memory-hook] No relevant memories found, context cleared", file=sys.stderr)
    return result


def capture(content: str, output: str | None = None, tags: list[str] | None = None) -> None:
    """将消息捕获到 Memory OS inbox。"""
    body = {
        "content": content,
        "type": "raw_input",
        "tags": tags or ["cc-connect"],
        "importance": 70,
        "source": "cc-connect-hook",
    }
    if output:
        body["output"] = output
    _api("POST", "/api/v1/memories", body)


def extract_prompt(stdin_data: str) -> str:
    """从 stdin JSON 中提取用户消息文本。"""
    if not stdin_data.strip():
        return ""
    try:
        data = json.loads(stdin_data)
    except json.JSONDecodeError:
        return stdin_data[:2000]

    prompt = data.get("prompt") or data.get("content") or ""
    return prompt.strip()[:2000]


def main():
    stdin_data = sys.stdin.read().strip()
    prompt = extract_prompt(stdin_data)

    if len(prompt) < 10:
        return  # 跳过过短消息

    # Step 1: 检索相关记忆并写入 last-context.md
    search_and_inject(prompt, top_k=3)

    # Step 2: 捕获当前消息到 inbox
    tags = ["cc-connect"]
    if EVENT and EVENT != "unknown":
        tags.append(EVENT)
    capture(prompt, tags=tags)


if __name__ == "__main__":
    main()
