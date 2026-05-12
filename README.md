# Memory OS

> 一个仿人脑记忆系统的多 Agent 个人知识引擎。以 Obsidian vault 为存储基座，LanceDB 为向量索引，6 个独立 Agent 协同完成输入→巩固→检索→遗忘→自监控的完整记忆生命周期。

## 这是什么

Memory OS 不是笔记工具，也不是传统 RAG。它是一套**后台常驻的 AI Agent 集群**，将你所有的对话、代码、文档、想法自动整理成一个"第二大脑"——有输入门控、有工作记忆槽位、有长期巩固、有遗忘曲线、有六路径检索，以及定期的自我健康检查。

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
| 检索失败（舌尖现象） | 6 条互补路径：精确ID → 关键词 → 向量 → 图谱 → 时间线 → 上下文 |

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
                        ┌──────────────────┼──────────────────┐
                        │                  │                  │
                        ▼                  ▼                  ▼
                 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                 │ A5 Forgetting│  │ A6 Meta-     │  │ 4x Canvas    │
                 │ 遗忘管理      │  │ Cognition    │  │ 可视化面板    │
                 │              │  │ 元认知监控    │  │              │
                 └──────────────┘  └──────────────┘  └──────────────┘
```

**六个 Agent 各自独立运行，通过 Obsidian vault 文件系统异步通信。**

| Agent | 对应脑区 | 触发方式 | 做什么 |
|-------|---------|---------|--------|
| **Sensory Gateway** | 丘脑+感觉皮层 | 实时 | 接收所有输入→去重→分类→写 `_inbox/` |
| **Working Memory Manager** | 前额叶 | 实时 | 维护 ≤7 个活跃槽位，满时按 LRU+重要性踢出 |
| **Consolidation Agent** | 海马体→新皮层 | 每4h / inbox≥20 | 摘要化+链接化+向量化+间隔重复调度 |
| **Retrieval Agent** | 前额叶+颞叶 | 按需 | 6 条检索路径，向量语义为默认主路径 |
| **Forgetting Agent** | 前额叶抑制 | 每日凌晨3点 | 计算强度衰减→分级归档→向量关联清理 |
| **Meta-Cognition Agent** | 前扣带皮层 | 每周一早9点 | 健康报告+缺口发现+向量一致性校验+调参建议 |

## 记忆生命周期

```
_inbox/ (status: raw)              ← Sensory Gateway 写入，不可变
    │
    ▼ Consolidation Agent 处理
_inbox/ (status: processing)       ← 锁定中
    │
    ▼ 摘要 + 链接 + 向量化
_memory/semantic/ (status: active)  ← 长期记忆
_vectors/semantic.lance              ← 向量索引（派生数据）
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

支持三种部署模式，在 `_meta/system-config.yaml` 中配置：

**全 Anthropic 栈：**
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

**混和部署（推荐）：**
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

### 日常使用流程

```
你说的话 / 写的代码 / 发的文件
    │
    ▼  自动
Sensory Gateway 收进来 → 打标签 → 写入 _inbox/
    │
    ▼  每4小时自动
Consolidation Agent 摘要 + 链接 + 向量化 → _memory/
    │
    ▼  随时
你搜索 "上个月讨论过的那个 agent 通信方案"
    │
    ▼  Retrieval Agent 向量语义搜索
返回 top-K 记忆 → 打开 Obsidian 笔记看到完整上下文
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
memory-os capture "Rust 的所有权系统用栈上分配避免了 GC"

# 搜索
memory-os search "agent 通信方案"              # 自动选择路径
memory-os search "vector database" --mode vector  # 纯语义搜索
memory-os search "mem-sem-20260512-001" --mode exact  # 精确 ID

# 查看状态
memory-os status                               # 记忆统计概览
memory-os health                               # 最新健康报告

# 手动触发 Agent
memory-os agent run consolidation              # 立即巩固所有 pending 输入
memory-os agent run forgetting                 # 立即运行遗忘扫描

# Canvas 数据导出
memory-os canvas graph --output graph.json     # 记忆图谱数据
memory-os canvas heatmap --output heatmap.json # 强度热力图数据
```

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
│   ├── episodic/                  # 情景记忆（按日期的日志）
│   ├── procedural/                # 程序记忆（流程/模板/技能）
│   └── archive/                   # 归档（保留文件，不在活跃索引）
├── _vectors/                      # LanceDB 向量索引
│   ├── semantic.lance/
│   ├── episodic.lance/
│   └── procedural.lance/
├── _canvas/                       # Canvas 缓存数据
├── _meta/                         # 系统元数据
│   ├── index.md                   # 全局记忆索引
│   ├── strength-matrix.md         # 强度评分表
│   ├── gaps.md                    # 知识缺口记录
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
| Embedding | BGE-M3（默认） | 本地运行、中英双语、1024 维、零成本 |
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
| 运行方式 | 后台常驻 Agent 集群 | 手动打开 | 请求驱动 |

## 相关文档

- [系统设计文档](../memory-system-design.md) — 人脑记忆分析 + 完整架构设计（九章）
- [详细实现规格](../memory-system-detail-design.md) — 15 个模块的接口、数据模型、测试清单
