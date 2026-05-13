# Memory OS — Claude Code Integration

## Auto Memory Context

回复用户消息前，先检查记忆上下文文件：

```
~/my-memory/_meta/last-context.md
```

1. 读取该文件（如果存在）
2. 检查 `Retrieved:` 时间戳是否在最近 5 分钟内
3. 如果在有效期内，将记忆上下文作为参考知识融入回复，自然引用而不逐字复述
4. 如果文件不存在或时间戳过期，正常回复即可

示例:
```
用户: "上次讨论的那个 agent 通信方案是什么？"
  → ~/my-memory/_meta/last-context.md 存在且新鲜
  → 包含: "Agent 间通过 Obsidian vault 文件系统异步通信"
  → 回复时自然引用这一信息
```
