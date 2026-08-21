# Claude Code CLI 2.1.235 技术文章总入口

这里是给人阅读的入口。机器清单、反汇编和 JSONL 用来证明结论，不应该挡在文章前面。

## 先读这三篇

1. [完整机制说明书](analysis/claude-code-2.1.235-complete-guide.md)：单卷 35 章，从发布物、请求装配、Agent Loop、上下文、权限、多 Agent、恢复、遥测一直讲到原生桥和版本变化。
2. [Agent Loop 专题](analysis/agent-loop.md)：解释 Claude Code 为什么能连续读文件、改代码、执行测试、吸收工具结果并继续决策。
3. [`/compact` 图文专题](analysis/compact-visual-guide.md)：用一个完整场景和三张图说明 Summary、近期消息、附件恢复、compact boundary 与失败恢复。

![Claude Code 任务在上下文、Agent Loop、工具控制、外部状态和恢复状态之间循环](analysis/visuals/system-lifecycle.svg)

## 按问题阅读

| 你想弄清楚什么 | 对应文章 |
| --- | --- |
| 一次请求从输入到工具执行、持久化和遥测经历什么 | [技术机制总图](analysis/technical-mechanism-atlas.md) |
| system prompt、messages、tools、provider 和请求体怎样装配 | [技术架构导读](analysis/technical-architecture.md) |
| Prompt Cache、Tool Search、microcompaction 和 auto-compact 有什么区别 | [上下文治理与多层缓存](analysis/context-governance-and-caching.md) |
| Resume、fork、rewind、checkpoint 和 Memory 分别恢复什么 | [会话、检查点与 Memory](analysis/sessions-checkpoints-memory.md) |
| 工具执行为什么还要经过 hook、permission、policy 和 sandbox | [工具、权限与 Hooks](analysis/tools-permissions-hooks.md) |
| MCP 工具何时刷新，子 Agent 和后台任务怎样回传结果 | [MCP、Agents 与后台协作](analysis/mcp-agents-background.md) |
| Retry、fallback、reactive compact 和 file rewind 分别恢复哪一层 | [韧性与恢复](analysis/resilience-and-recovery.md) |
| 模型别名、provider、凭据、base URL、beta 和 request body 怎样决定 | [模型、认证、Provider 与请求装配](analysis/models-auth-providers-request.md) |
| 为什么 settings 或 feature flag 写了却不生效 | [Settings、Feature Flags 与 Managed Policy](analysis/settings-feature-flags-policy.md) |
| TUI、IDE、Remote Control 和 Cloud Session 谁真正持有执行状态 | [TUI、IDE、Remote Control 与 Cloud Session](analysis/tui-ide-remote-cloud.md) |
| 安装、更新、Doctor 和版本回退怎样验证真实二进制 | [安装、更新、Doctor 与版本生命周期](analysis/install-update-doctor-lifecycle.md) |
| `.node` 模块怎样连接 JavaScript、N-API、Rust/Swift 和 macOS | [Native Bridge 与 JavaScript Runtime](analysis/native-bridge-runtime.md) |
| 一方事件、OTEL、Datadog、错误上报和本地诊断记录什么 | [遥测、日志与诊断](analysis/telemetry.md) |
| JSONL 中 `comparisonKey`、payload、schema 和 model 字段怎么读 | [机器清单字段阅读指南](analysis/inventory-field-guide.md) |
| bundle 到底还能提取出哪些产品能力和证据 | [全量可提取能力面](analysis/source-surface.md) |

## 每篇文章怎么读

核心专题都按三层组织：

1. **60 秒模型**：读者问题、单句结论、贯穿场景、状态表和机制图。
2. **完整机制**：调用顺序、状态字段、gate、优先级、阈值、并发、失败与恢复。
3. **证据层**：`2.1.235` 源码范围、精确二进制 Probe、literal output、exit status 和不可证明边界。

图是为了先把状态变化讲清楚，不会替代字段、阈值、失败路径或源码证据。
