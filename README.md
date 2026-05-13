# Memory OS

> 一个仿人脑记忆系统的多 Agent 个人知识引擎。以 Obsidian vault 为存储基座，LanceDB 为向量索引，7 个独立 Agent 协同完成输入→巩固→检索→遗忘→复盘→自监控的完整记忆生命周期。

## 这是什么

Memory OS 不是笔记工具，也不是传统 RAG。它是一套**后台常驻的 AI Agent 集群**，将你所有的对话、代码、文档、想法自动整理成一个"第二大脑"——有输入门控、有工作记忆槽位、有长期巩固、有遗忘曲线、有每日复盘、有六路径检索，以及定期的自我健康检查。

你不需要手动整理。Agent 在你睡觉的时候干活。

## 核心理念：复制人脑的优点，修补人脑的缺陷

人脑记忆系统经过亿年进化，有七个精妙之处（语义联想、自动模式识别、遗忘即特征、情绪加权、上下文检索、间隔重复、睡眠巩固），也有七个致命缺陷（指数遗忘、虚假记忆、新旧干扰、容量瓶颈、舌尖效应、回忆偏差、缺乏元数据）。

Memory OS 用工程手段逐个映射：

| 人脑特征 | 工程实现 |
|---------|---------|
| 联想索引（一个线索激活一串记忆） | Obsidian `[[wikilinks]]` + 图谱扩散检索 |
| 分布式表征（知道意思但想不起原话） | LanceDB 向量语义搜索，默认主检索路径 |
| 遗忘即特征（不重要信息自然消退） | Forgetting Agent 强度衰减 + 归档（不删文件） |
| 间隔重复（分散复习远超集中复习） | SM-2 衍生调度，自动设定下次复习时间 |
| 工作记忆容量 4-7 组块 | 持久化槽位，可踢出可恢复 |
| 睡眠巩固（离线期重组记忆） | Consolidation Agent 定时批量摘要+链接+向量化 |
| 错误记忆（脑补缺失信息） | `_inbox/` 原始输入不可变，全链路 provenance |
| 认知失调（新旧知识矛盾） | Consolidation Agent 向量相似度+LLM 冲突检测，标记 `conflict: true`，写入 `cognitive-conflicts.md` |
| 检索失败（舌尖现象） | 7 条互补路径：精确ID → 关键词 → 向量 → 图谱 → 时间线 → 上下文 → 推理回溯 |

## 系统架构

```
                       ┌─────────────────────────────┐
                       │     GUI / TUI / WebUI        │  三种客户端可选
                       │  (Tauri / Textual / React)   │  共享同一 Core SDK
                       └─────────────┬───────────────┘
                                     │
                       ┌─────────────▼───────────────┐
                       │      Core SDK (API)          │  统一入口，UI/Agent 互不感知
                       └─────────────┬───────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
       ▼                             ▼                             ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ A1 Sensory   │  │ A2 Working   │  │ A3 Consoli-  │  │ A4 Retrieval     │
│ Gateway      │─▶│ Memory       │─▶│ dation       │  │ (6 路径检索)     │
│ 感官门控      │  │ 工作记忆管理  │  │ 巩固代理      │  │                  │
└──────────────┘  └──────────────┘  └──────┬───────┘  └──────────────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │ Obsidian Vault   │
                                  │ + LanceDB 向量库 │
                                  └──────────────────┘
                                           │
                        ┌──────────────────┼──────────────────────┐
                        │                  │                      │
                        ▼                  ▼                      ▼
                 ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
                 │ A5 Forgetting│  │ A6 Review    │  │ A7 Meta-         │
                 │ 遗忘管理      │  │ 每日复盘      │  │ Cognition        │
                 │              │  │              │  │ 元认知监控        │
                 └──────────────┘  └──────────────┘  └──────────────────┘
                        │                  │                      │
                        └──────────────────┼──────────────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ 4x Canvas    │
                                    │ 可视化面板    │
                                    └──────────────┘
```

**七个 Agent 各自独立运行，通过 Obsidian vault 文件系统异步通信。**

| Agent | 对应脑区 | 触发方式 | 做什么 |
|-------|---------|---------|--------|
| **Sensory Gateway** | 丘脑+感觉皮层 | 实时 | 接收所有输入（支持 input+output 对）→去重→分类→写 `_inbox/` |
| **Working Memory Manager** | 前额叶 | 实时 | 维护 ≤7 个活跃槽位，记录操作日志，LLM 检测推理链→保存为程序记忆 trace |
| **Consolidation Agent** | 海马体→新皮层 | 每4h / inbox≥20 | 从 Q&A 对提炼语义+程序记忆+情景日志；检测新旧记忆矛盾→标记冲突 |
| **Retrieval Agent** | 前额叶+颞叶 | 按需 | 7 条检索路径（含推理回溯），向量语义为默认主路径，支持列表+按ID相似搜索 |
| **Review Agent** | 前额叶+默认模式网络 | 每日上午 8:57 | 回顾昨日记忆活动，LLM 生成复盘报告（话题/决策/缺口/连接/行动建议+Token 消耗） |
| **Forgetting Agent** | 前额叶抑制 | 每日凌晨3点 | 计算强度衰减→分级归档→向量关联清理 |
| **Meta-Cognition Agent** | 前扣带皮层 | 每周一早9点 | 健康报告+缺口发现+认知冲突统计+向量一致性校验+调参建议 |

## 记忆生命周期

```
_inbox/ (status: raw)              ← Sensory Gateway 写入（含 input+output 对），不可变
    │
    ▼ Consolidation Agent 处理
_inbox/ (status: processing)       ← 锁定中
    │
    ▼ 提炼 3 种记忆：Episodic（情景日志）+ Semantic（知识点）+ Procedural（步骤流程）
_memory/semantic/ (status: active)
_memory/episodic/ (status: active)
_memory/procedural/ (status: active)
_vectors/*.lance                     ← 向量索引（派生数据）
    │
    ▼ 认知冲突检测（Consolidation Agent）
_meta/cognitive-conflicts.md         ← 矛盾记忆记录
    │
    ▼ 每日复盘（Review Agent）
_memory/episodic/review-YYYY-MM-DD.md  ← 复盘报告
    │
    ▼ 时间衰减
(status: fading)                     ← Forgetting Agent 标记
    │
    ▼ 持续衰减
_memory/archive/ (status: archived) ← 归档保留文件，删除向量
```

**核心原则：归档不删除 Obsidian 文件。** Markdown 是 source of truth，LanceDB 向量是派生索引，丢失可一键重建。

## 安装

### 环境要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)（推荐，也可用 pip）
- [Obsidian](https://obsidian.md/)（可选，用于浏览 vault 中的笔记）
- LLM API key（支持 Anthropic、OpenAI、以及任何 OpenAI 兼容接口如 Ollama）

### 快速开始

```bash
# 1. 克隆仓库
git clone git@github.com:StartHex/MemGatewayObsidian.git
cd MemGatewayObsidian

# 2. 安装（可编辑模式，方便后续更新 git pull 即可）
uv sync
# 或者用 pip: pip install -e .

# 3. 初始化 vault（在 Obsidian 中打开此目录即可浏览笔记）
memory-os init --vault ~/my-memory

# 4. 配置 LLM
memory-os config set llm.chat.provider anthropic
memory-os config set llm.chat.model claude-sonnet-4-6
memory-os config set llm.chat.api_key $ANTHROPIC_API_KEY

# 5. 启动服务
memory-os serve          # 后台常驻，Agent 开始工作
```

> **提示**：项目尚未发布到 PyPI。执行 `uv sync` 或 `pip install -e .` 即可将 `memory-os` 命令注册到系统 PATH。

### LLM 配置示例

在 `_meta/system-config.yaml` 中配置。**embedding 是可选的**——不配置时系统自动回退到关键词搜索，向量存储和语义匹配功能跳过。

**最小配置（仅聊天，无 embedding）：**
```yaml
llm:
  chat:
    provider: anthropic
    model: claude-sonnet-4-6
    api_key: ${ANTHROPIC_API_KEY}
```

**带 embedding（推荐，启用语义搜索）：**
```yaml
llm:
  chat:
    provider: anthropic
    model: claude-sonnet-4-6
    api_key: ${ANTHROPIC_API_KEY}
  embedding:
    provider: local
    model: bge-m3
    base_url: http://localhost:8080
    dimension: 1024
```

**全本地 Ollama（零成本，离线）：**
```yaml
llm:
  chat:
    provider: openai-compatible
    model: qwen2.5:14b
    base_url: http://localhost:11434/v1
    api_key: ollama
  embedding:
    provider: openai-compatible
    model: nomic-embed-text
    base_url: http://localhost:11434/v1
    dimension: 768
```

**混和部署：**
```yaml
llm:
  chat:
    provider: anthropic
    model: claude-sonnet-4-6
    api_key: ${ANTHROPIC_API_KEY}
    fallback:
      provider: openai-compatible
      model: qwen2.5:14b
      base_url: http://localhost:11434/v1
  embedding:
    provider: openai
    model: text-embedding-3-large
    api_key: ${OPENAI_API_KEY}
```

## 使用方式

### 三种客户端

| | GUI (Tauri) | TUI (Textual) | WebUI (localhost) |
|---|---|---|---|
| 安装 | 克隆仓库后 `uv sync --extra gui` | 克隆仓库后 `uv sync --extra tui` | 内置 |
| 启动 | 桌面应用（Tauri 构建） | `memory-os tui` | `memory-os web` |
| 适用场景 | 桌面常驻 / 全局快捷键 | SSH 远程 / vim 用户 | 可视化 / 跨设备 |
| Canvas | 内嵌 WebView（完整） | ASCII 降级 | 完整 D3.js / ECharts |

三种客户端可同时运行，连接同一个 vault。

### 自动记忆注入（Auto-Inject）

Memory OS 可在每次对话时**自动检索相关记忆并注入到 Claude Code 上下文**中，无需手动搜索。

**工作原理：**

```
用户输入消息
    │
    ▼
Claude Code hook (UserPromptSubmit)
    │
    ├─ 1. POST /api/v1/search/inject-and-save
    │     检索相关记忆 → 写入 _meta/last-context.md
    │
    └─ 2. POST /api/v1/memories
          捕获当前消息到 inbox
```

**CLAUDE.md 指令**告诉 Claude Code 在回复前检查 `last-context.md`，将相关记忆融入回答。

**配置方式（在 settings.json 中）：**
```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "command": "/path/to/scripts/capture_hook.py"
    }]
  },
  "env": {
    "MEMORY_OS_API": "http://127.0.0.1:9090"
  }
}
```

有相关记忆时自动创建 `_meta/last-context.md`，无相关记忆时自动删除，避免过期上下文干扰。

### 五 Hook 生命周期

Memory OS 通过 5 个 Claude Code Hook 覆盖会话全流程，实现跨会话记忆无缝衔接：

```
🚀 SessionStart  → 注入 hot.md 摘要 + 激活记忆统计
     │
💬 UserPromptSubmit → 分类路由 + 检索注入 (capture_hook.py)
     │
✍️ PostToolUse → 验证写入的 .md 文件 (frontmatter + wikilinks)
     │
💾 PreCompact → 备份 session transcript 到 _agent-logs/
     │
🏁 Stop → 更新 hot.md + 打印会话摘要统计
```

| Hook | 脚本 | 触发时机 | 功能 |
|------|------|---------|------|
| **SessionStart** | `scripts/session_start_hook.py` | 会话启动 | 注入 `hot.md` 摘要，让新对话自动获得上次会话的上下文 |
| **UserPromptSubmit** | `scripts/capture_hook.py` | 每次输入 | 检索相关记忆 → 写入 `last-context.md` + 捕获消息到 inbox |
| **PostToolUse** | `scripts/post_tool_hook.py` | 工具调用后 | 验证写入 vault 的 .md 文件：检查 frontmatter 字段完整性 + wikilinks 有效性 |
| **PreCompact** | `scripts/pre_compact_hook.py` | 上下文压缩前 | 保存对话转录到 `_agent-logs/session-{timestamp}.md`，防止信息丢失 |
| **Stop** | `scripts/stop_hook.py` | 会话结束 | 重新生成 `hot.md` + 打印会话统计摘要 |

**配置方式（在 `~/.claude/settings.json` 中）：**
```json
{
  "hooks": {
    "SessionStart": [{"matcher": "", "command": "/path/to/scripts/session_start_hook.py"}],
    "UserPromptSubmit": [{"matcher": "", "command": "/path/to/scripts/capture_hook.py"}],
    "PostToolUse": [{"matcher": "*.md", "command": "/path/to/scripts/post_tool_hook.py"}],
    "PreCompact": [{"matcher": "", "command": "/path/to/scripts/pre_compact_hook.py"}],
    "Stop": [{"matcher": "", "command": "/path/to/scripts/stop_hook.py"}]
  }
}
```

### Hot Cache 热缓存机制

`hot.md` 是跨会话的"记忆快照"，由 Stop Hook 在每次会话结束时更新，SessionStart Hook 在新会话启动时注入。

**hot.md 内容结构：**
```markdown
# Hot Context
> Updated: 2026-05-13T14:30:00 | Session #5 | Vault: ~/my-memory

## Active Memories (10)
- [[mem-sem-xxx|Memory OS 架构]] (strength: 90, last_retrieved: 2h ago)
- [[mem-sem-yyy|项目比较分析]] (strength: 75)

## Recent Activity (5 days)
- 2026-05-13: 5 episodic entries
- 2026-05-12: 2 episodic entries

## Pending (6)
- 3 inbox items waiting for consolidation
- 1 conflict unresolved
- 2 fading memories below threshold

## Top Decisions
- Memory OS 三端架构已完成 (2026-05-13)
- Embedding 模型改为可选配置 (2026-05-13)
```

**相关 API：**

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/system/hot` | 获取 hot.md 内容（自动生成如果缺失） |
| POST | `/api/v1/system/hot/update` | 重新生成 hot.md |
| POST | `/api/v1/system/transcript/save` | 保存会话转录 |
| POST | `/api/v1/system/validate` | 验证 .md 文件的 frontmatter + wikilinks |

### 分级 Token 加载策略

为避免每次对话注入过多无关上下文，采用四级 token 预算控制：

| 层级 | 内容 | Token 预算 | 触发时机 |
|------|------|-----------|---------|
| **Always** | hot.md 摘要 | ~200 | SessionStart |
| **On-demand** | search_and_inject 检索结果 | ~500 | UserPromptSubmit |
| **Triggered** | Agent 运行报告 | ~300 | 特定命令触发 |
| **Rare** | 完整记忆文件 | 不限 | 用户明确请求 |

`search_and_inject` 支持 `max_tokens` 参数控制输出长度，`min_score` 参数过滤低相关度结果（默认 0.40）。

### 日常使用流程

```
你说的话 / 写的代码 / 发的文件（支持 input+output 问答对）
    │
    ▼  自动
Sensory Gateway 收进来 → 打标签 → 写入 _inbox/（保存完整的 Q&A 对）
    │
    ▼  每4小时自动
Consolidation Agent 提炼 3 种记忆：
  - Episodic: "什么时候讨论了什么"（情景日志）
  - Semantic: "学到了什么知识点"（知识卡片）
  - Procedural: "怎么做"（步骤流程）
  + 冲突检测：发现与高置信度旧记忆矛盾时标记 conflict
    │
    ▼  随时
你搜索 "上个月讨论过的那个 agent 通信方案"
    │
    ▼  Retrieval Agent 向量语义搜索
返回 top-K 记忆 → 打开 Obsidian 笔记看到完整上下文
    │
    ▼  每天上午 8:57 自动
Review Agent 回顾昨日所有记忆活动 → 生成复盘报告
（话题总结 / 关键决策 / 知识缺口 / 连接建议 / 行动建议 / Token 消耗分模型统计）
    │
    ▼  每天凌晨自动
Forgetting Agent 清理不再需要的记忆 → 归档
    │
    ▼  每周一自动
Meta-Cognition 发你一份健康报告
```

### CLI 常用命令

```bash
# 快速记录一条想法
memory-os ingest "Rust 的所有权系统用栈上分配避免了 GC"

# 记录问答对（Q + A → 自动提炼知识点和操作步骤）
memory-os ingest "Docker 多阶段构建怎么做" --output "使用 builder stage 编译，再复制到 runtime stage"

# 搜索
memory-os search "agent 通信方案"              # 自动选择路径
memory-os search "vector database" --mode vector  # 纯语义搜索
memory-os search "mem-sem-20260512-001" --mode exact  # 精确 ID
memory-os search "推理链" --mode traceback       # 推理回溯搜索

# 工作记忆管理
memory-os wm list                                # 列出所有槽位
memory-os wm promote --memory-id mem-xxx --name "分析任务"  # 提升到工作记忆
memory-os wm update --slot-id 1 --content "新内容"           # 更新槽位
memory-os wm conclude --slot-id 1                            # 结束槽位（检测推理链）
memory-os wm evict --slot-id 1                               # 踢出槽位

# 全量记忆列表（分页/过滤）
memory-os list                                 # 列出所有记忆
memory-os list --type semantic --limit 20      # 只列语义记忆
memory-os list --sort importance               # 按重要性排序

# 搜索并拼接为 Context（手动注入）
memory-os search-inject "agent 通信方案"         # 检索+加载全文+格式化 Context
memory-os search-inject "vector database" -k 3  # 最多 3 条
# 注: Claude Code hook 已实现自动注入，CLI 仅为手动使用场景

# 按记忆 ID 找相似
memory-os similar mem-sem-xxx --top-k 10       # 语义相似记忆

# 每日记忆复盘
memory-os review                               # 复盘昨日
memory-os review --date 2026-05-10             # 复盘指定日期

# 查看状态
memory-os status                               # 记忆统计概览
memory-os health                               # 最新健康报告

# 手动触发 Agent
memory-os agent run consolidation              # 立即巩固所有 pending 输入
memory-os agent run forgetting                 # 立即运行遗忘扫描
memory-os agent run review                     # 立即触发记忆复盘

# Canvas 数据导出
memory-os canvas graph --output graph.json     # 记忆图谱数据
memory-os canvas heatmap --output heatmap.json # 强度热力图数据
```

### MCP 工具（Claude Code 集成）

通过 `memory-os mcp` 启动 MCP Server，Claude Code 等 MCP 客户端可直接调用以下工具：

| 工具 | 用途 | 关键参数 |
|------|------|---------|
| `capture_memory` | 记录新记忆（支持 Q&A 对） | content, tags, output |
| `search_memory` | 多策略检索 | query, strategy, top_k |
| `search_and_inject` | 检索+加载全文+拼接为 Context（自动注入链路的检索端） | query, top_k |
| `list_memories` | 分页列出全量记忆 | type, status, limit, offset, sort_by |
| `find_similar` | 按记忆 ID 找语义相似记忆 | memory_id, top_k |
| `review_memory` | 手动触发复盘 | date (可选，默认昨日) |
| `get_memory_stats` | 记忆库统计 | — |
| `get_vault_health` | 系统健康检查 | — |
| `trigger_agent` | 手动触发 Agent | agent (consolidation/forgetting/meta_cognition/review) |
| `working_memory` | 工作记忆槽位管理 | action (list/promote/update/evict/conclude), slot_id, memory_id, name, content |
| `get_canvas_graph` | 记忆图谱数据 | status |
| `get_canvas_heatmap` | 强度热力图数据 | — |
| `get_hot_context` | 获取 hot.md 上下文 | — |
| `update_hot_context` | 刷新 hot.md | — |
| `validate_memory_file` | 验证 .md 文件 | file_path |

### 四张可视化 Canvas

在 WebUI 或 GUI 中打开：

1. **记忆图谱（Memory Graph）** — 力导向图展示记忆节点和 wikilinks 关联，节点越大表示记忆越强
2. **强度热力图（Strength Heatmap）** — treemap 显示所有记忆的健康状况，绿→黄→红随衰减变化
3. **时间线（Episodic Timeline）** — 按天/周/月浏览情景记忆，支持情绪标记过滤
4. **向量投影（Vector Projection）** — UMAP 降维到 2D，直观看到知识簇的分布和漂移

## Vault 目录结构

```
~/my-memory/                       # Obsidian vault 根目录
├── _inbox/                        # 感官输入暂存区（原始不可变）
├── _working/                      # 工作记忆槽位（≤9 个 .md）
├── _memory/
│   ├── semantic/                  # 语义记忆（知识/概念）
│   ├── episodic/                  # 情景记忆（按日期的日志+每日复盘 review-*.md）
│   ├── procedural/                # 程序记忆（流程/模板/技能 + 推理链 trace-*.md）
│   └── archive/                   # 归档（保留文件，不在活跃索引）
├── _vectors/                      # LanceDB 向量索引
│   ├── semantic.lance/
│   ├── episodic.lance/
│   └── procedural.lance/
├── _canvas/                       # Canvas 缓存数据
├── _meta/                         # 系统元数据
│   ├── index.md                   # 全局记忆索引
│   ├── hot.md                     # 会话热缓存（跨会话记忆快照）
│   ├── last-context.md            # 当前对话上下文（自动注入）
│   ├── validation-log.md          # 文件验证日志
│   ├── strength-matrix.md         # 强度评分表
│   ├── gaps.md                    # 知识缺口记录
│   ├── cognitive-conflicts.md     # 认知冲突日志
│   ├── token-usage.jsonl          # Token 消耗记录
│   ├── health-report.md           # 最新健康报告
│   └── system-config.yaml         # 系统配置
├── _agent-logs/                   # Agent 操作审计日志
└── _templates/                    # Obsidian 模板
```

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 主存储 | Obsidian vault (Markdown) | 人类可读、git 可版控、wikilinks 建模语义网络 |
| 向量库 | LanceDB | 嵌入式、文件级持久化、ANN 毫秒级、随 vault 一起备份 |
| LLM 接入 | Provider Adapter 双层 | OpenAI + Anthropic 双协议，换 provider 只改一行配置 |
| Embedding | BGE-M3 / OpenAI / 无 | 可选——不配置时自动回退到关键词搜索 |
| GUI | Tauri 2.x | ~5MB 包体、系统托盘、全局快捷键、原生通知 |
| TUI | Python Textual | SSH 可用、vim 键位、tmux 长驻 |
| WebUI | React + FastAPI | PWA 支持、跨设备、完整图表生态 |

## 与传统方案的区别

| | Memory OS | 传统笔记 (Obsidian/Notion) | RAG (LangChain/LlamaIndex) |
|---|---|---|---|
| 整理方式 | Agent 自动分类+链接 | 手动整理 | chunk 切片，无语义结构 |
| 遗忘 | 主动衰减+归档 | 只增不减 | 无遗忘机制 |
| 检索 | 6 条互补路径 | 全文搜索 | 仅向量相似度 |
| 元认知 | 健康报告+缺口检测+调参建议 | 无 | 无 |
| 原始追溯 | `_inbox/` 不可变 | 修改即覆盖 | 无 provenance |
| 每日复盘 | 自动回顾+LLM 生成报告 | 无 | 无 |
| 运行方式 | 后台常驻 7 Agent 集群 | 手动打开 | 请求驱动 |

## 相关文档

- [系统设计文档](../memory-system-design.md) — 人脑记忆分析 + 完整架构设计（九章）
- [详细实现规格](../memory-system-detail-design.md) — 15 个模块的接口、数据模型、测试清单
