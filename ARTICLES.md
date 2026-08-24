# Claude Code CLI 2.1.235 阅读入口

这个仓库同时包含教程、参考手册和机器证据。三者用途不同：教程用来理解一次真实状态变化；参考手册用来查命令、字段和生命周期；机器证据用来复核结论。不要从大清单开始读。

## 先读这五篇

1. [`/compact` 到底压缩了什么](analysis/compact-visual-guide.md)：从一段 Claude Code 自身的 `Grep -> tool_result -> Read -> tool_result` 会话开始，展示压缩前后模型实际拿到什么。
2. [Agent Loop](analysis/agent-loop.md)：模型怎样提出 `tool_use`，客户端怎样执行并把配对结果送回下一轮。
3. [上下文治理](analysis/context-governance-and-caching.md)：Prompt Cache、Tool Search、microcompaction 和完整 compact 分别改变什么。
4. [会话、Checkpoint 与 Memory](analysis/sessions-checkpoints-memory.md)：Resume、fork、rewind 和长期 Memory 各自恢复什么对象。
5. [工具、权限与 Hooks](analysis/tools-permissions-hooks.md)：一个模型提议怎样经过校验、权限、sandbox 和 Hook 才产生真实副作用。

要先看整个系统，可读[一次请求的技术机制总图](analysis/technical-mechanism-atlas.md)。只关心本版变化，可读[2.1.235 状态边界修正](analysis/product-surface-evidence-map.md)。需要逐项查阅时，再进入下面的专题和参考手册。

## 机制教程

这些文档解释“用户做了什么、客户端按什么顺序改变状态、失败后留下什么”。

<details>
<summary>展开全部机制教程</summary>

### 请求、执行与上下文

- [技术机制总图](analysis/technical-mechanism-atlas.md)
- [技术架构](analysis/technical-architecture.md)
- [Agent Loop](analysis/agent-loop.md)
- [`/compact` 上下文压缩](analysis/compact-visual-guide.md)
- [上下文治理与多层缓存](analysis/context-governance-and-caching.md)
- [会话、Checkpoint 与 Memory](analysis/sessions-checkpoints-memory.md)
- [工具、权限与 Hooks](analysis/tools-permissions-hooks.md)
- [模型、认证、Provider 与请求装配](analysis/models-auth-providers-request.md)
- [韧性与恢复](analysis/resilience-and-recovery.md)

### 计划、输出与协作

- [Plan Mode 与人工审批](analysis/plan-mode-and-human-approval.md)
- [Structured Output 与 Schema 合同](analysis/structured-output-and-schema-contract.md)
- [Brief 与用户可见输出](analysis/brief-mode-and-user-visible-output.md)
- [REPL 程序化工具运行时](analysis/repl-programmatic-tool-runtime.md)
- [EndConversation 风控](analysis/end-conversation-risk-control.md)
- [MCP、Agents 与后台协作](analysis/mcp-agents-background.md)
- [Connectors、Catalog 与 MCP Operators](analysis/connectors-catalog-and-mcp-operators.md)
- [Remote Routines、Runner 与 Notifications](analysis/remote-routines-runner-and-notifications.md)
- [ClaudeDesign 与 Projects](analysis/claude-design-and-projects.md)
- [Workflow、Artifact 与 Design](analysis/workflow-artifact-design.md)

### CLI、宿主与远端状态

- [CLI 启动文件、URL 插件与 Deep Link](analysis/cli-startup-files-plugins-deeplinks.md)
- [复杂 Slash Command 生命周期](analysis/complex-slash-command-lifecycles.md)
- [TUI、媒体、IDE 与 Chrome](analysis/tui-input-accessibility-media-ide-chrome.md)
- [TUI、IDE、Remote Control 与 Cloud](analysis/tui-ide-remote-cloud.md)
- [后台执行、Channels 与 Cloud](analysis/cloud-background-channels.md)
- [Runtime Supervision](analysis/runtime-supervision-and-processes.md)
- [Enterprise Gateway Runtime](analysis/enterprise-gateway-runtime.md)
- [Artifact Watch 评论自动响应](analysis/artifact-watch-comment-autoreact.md)
- [`/insights` 历史分析管线](analysis/insights-history-analysis-pipeline.md)

### 配置、身份与安全边界

- [Settings、Feature Flags 与 Managed Policy](analysis/settings-feature-flags-policy.md)
- [Feature Flags 与 Remote Config](analysis/feature-flags-remote-config.md)
- [Auth、账号与订阅](analysis/auth-account-and-subscription-lifecycle.md)
- [Onboarding 与 Workspace Trust](analysis/onboarding-workspace-trust-and-safe-startup.md)
- [Auto Mode 两阶段分类器](analysis/auto-mode-classifier.md)
- [Sandbox 安装与运行 Enforcement](analysis/sandbox-install-and-runtime-enforcement.md)
- [Proxy、NO_PROXY、CA 与 mTLS](analysis/network-proxy-ca-and-mtls.md)
- [Project Purge、Import 与数据生命周期](analysis/project-purge-import-and-data-lifecycle.md)

### 模型任务、成本与发布运行时

- [Thinking、Effort 与 Fast Mode](analysis/thinking-effort-and-fast-mode.md)
- [Usage、成本、Credits 与 Limits](analysis/usage-cost-credits-and-limits.md)
- [Active Goal 与 Stop-loop](analysis/active-goal-and-stop-loop.md)
- [后台模型任务与 Memory Consolidation](analysis/background-model-tasks-and-memory-consolidation.md)
- [Advisor 双模型运行时](analysis/advisor-dual-model-runtime.md)
- [Ultrareview 云端审查](analysis/ultrareview-cloud-review.md)
- [Plugin Evaluation Harness](analysis/plugin-evaluation-harness.md)
- [Native 安装、自更新与 Doctor](analysis/install-update-doctor-lifecycle.md)
- [Native Bridge 与 JavaScript Runtime](analysis/native-bridge-runtime.md)
- [遥测、日志与诊断](analysis/telemetry.md)

</details>

## 参考手册

这些文档允许高密度表格。它们的目标是快速查找，不需要虚构贯穿场景。

<details>
<summary>展开全部参考手册</summary>

- [核心工具参考](analysis/builtin-tools-reference.md)
- [工具注册与宿主表面](analysis/tool-registration-and-host-surfaces.md)
- [Settings 全字段参考](analysis/settings-reference.md)
- [CLI 命令树](analysis/cli-command-reference.md)
- [CLI、SDK 与输出协议](analysis/cli-sdk-output-protocol.md)
- [Plugins、Skills、Commands 与 LSP](analysis/plugins-skills-commands-lsp.md)
- [Slash Command 参考](analysis/slash-command-reference.md)
- [Hook 事件参考](analysis/hooks-event-reference.md)
- [Storage v5 参考](analysis/storage-v5-reference.md)
- [遥测事件目录](analysis/telemetry-event-catalog.md)
- [API、Beta 与路由所有权](analysis/api-beta-route-ownership.md)
- [错误与诊断图谱](analysis/error-diagnostic-atlas.md)
- [机器清单字段阅读指南](analysis/inventory-field-guide.md)
- [可提取能力面](analysis/source-surface.md)

</details>

## 证据与完整性

这些文档回答“结论凭什么成立”，不承担教程职责。

- [完整机制说明书](analysis/claude-code-2.1.235-complete-guide.md)
- [全面性审计](analysis/completeness-audit.md)
- [公开主张与目标版证据](analysis/public-claims-validation.md)
- [精确二进制 Probe 索引](analysis/runtime-probe-index.md)
- [产品表面机器证据索引](analysis/product-surface-inventory-index.md)
- [错误与诊断精确 owner 索引](analysis/error-diagnostic-owner-index.md)
- [Environment 全量参考](analysis/environment-variable-reference.md)
- [Feature key 全量参考](analysis/feature-flag-reference.md)

教程中的阈值、失败分支和边界仍然必须保留；这里只是把证据清单从主阅读路径移开，而不是删掉技术深度。
