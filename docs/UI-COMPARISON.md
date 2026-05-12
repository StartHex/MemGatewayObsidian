# UI 技术栈对比评估

## TUI 方案

| 维度 | 方案 A: Textual | 方案 B: prompt_toolkit |
|------|----------------|----------------------|
| 包体积 | ~8MB (textual + rich) | ~2MB (prompt_toolkit) |
| 界面丰富度 | ★★★★☆ 完整 TUI 框架，布局/CSS/动画 | ★★☆☆☆ 纯 REPL 交互，无布局概念 |
| Canvas 降级 | ASCII 图表示意 | 无图形能力，仅文本输出 |
| 键盘效率 | ★★★★☆ vim 键位内置 | ★★★★★ 纯键盘流，管道友好 |
| SSH 适配 | ★★★☆☆ 需要 256 色终端 | ★★★★★ 任何终端可用 |
| 学习曲线 | 中（有自己的 CSS/布局系统） | 低（就是 REPL） |
| 适合场景 | 日常桌面终端重度用户 | SSH 远程管理、CI/CD 集成 |
| 启动命令 | `uv run python -m memory_os.tui.textual_app` | `uv run python -m memory_os.tui.prompt_app` |

**结论**：两者可共存。Textual 作为默认交互式 TUI，prompt_toolkit 作为 SSH/脚本场景的备选。

## WebUI 方案

| 维度 | 方案 A: React + Vite | 方案 B: HTMX + FastAPI |
|------|---------------------|----------------------|
| 包体积 | ~50MB (node_modules) | ~5MB (jinja2 + htmx 12KB) |
| 首屏加载 | ~2s (JS bundle) | ~200ms (SSR HTML) |
| Canvas 渲染 | ★★★★★ D3.js / ECharts / vis-network | ★★★☆☆ 服务端 SVG 降级 |
| 交互性 | ★★★★★ 全 SPA，无刷新 | ★★★☆☆ 局部刷新，无 SPA 体验 |
| PWA 支持 | ★★★★★ vite-plugin-pwa | ★★★☆☆ 手动 manifest |
| 开发体验 | TypeScript 类型安全 + HMR | 模板渲染，无类型检查 |
| 学习曲线 | 高（React + TS + Vite 生态） | 低（HTML 模板 + 少量 htmx 属性） |
| 移动端适配 | ★★★★☆ 响应式组件 | ★★★★☆ 原生 HTML 天然响应式 |
| 适合场景 | 日常高频使用、可视化需求高 | 低配设备、快速原型、内部工具 |
| 启动命令 | `cd webui-react && pnpm dev` | `uv run python webui-htmx/htmx_server.py` |

**结论**：React 方案做主力 WebUI（Canvas 必须用 D3.js 级别），HTMX 作为配置页/简单操作页的轻量入口。

## GUI 方案

| 维度 | 方案 A: Tauri 2.x | 方案 B: PySide6 |
|------|------------------|-----------------|
| 包体积 | ~5MB (.dmg) | ~15MB (PySide6 .app) |
| 语言 | Rust shell + React WebView | Pure Python |
| 系统集成 | ★★★★★ 托盘/通知/快捷键原生 | ★★★★☆ Qt 原生 widget |
| 开发速度 | 慢（Rust 编译 + 前端构建） | 快（Python 直接调 Core SDK） |
| Canvas | WebView 内嵌（完整） | QWebEngineView 内嵌 |
| 包分发 | .dmg / .msi / .AppImage | PyInstaller / Nuitka |
| 内存占用 | ~50MB | ~80MB |
| 团队要求 | Rust + TS 双技能 | 纯 Python |
| 适合场景 | 最终用户分发 | 开发期快速原型 |
| 启动命令 | `cd gui-tauri && cargo tauri dev` | `uv run python gui-pyside/pyside_app.py` |

**结论**：先用 PySide6 开发和验证所有 GUI 功能（开发速度优先），稳定后用 Tauri 重写为正式分发版本。

## 推荐组合

```
Phase 1: 开发和内部使用
  - TUI: Textual（本地交互）+ prompt_toolkit（SSH）
  - WebUI: React/Vite（完整功能）
  - GUI: PySide6（快速原型）

Phase 2: 生产发布
  - TUI: 保留两个方案
  - WebUI: 保留 React/Vite，HTMX 做轻量监控页
  - GUI: 迁移到 Tauri 做正式分发
```
