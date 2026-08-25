---
title: 工具、权限与扩展
description: 从一个 Edit 调用追踪工具解析、输入校验、Hooks、权限、sandbox、MCP 与外部副作用。
section: 核心机制
order: 5
---

# 工具、权限与扩展

模型生成 `Edit`、`Bash` 或 MCP `tool_use`，并不意味着动作已经发生。Claude Code 客户端把模型提议编译成一次受控执行；每一层都可能拒绝、改写、延迟或生成带同一 ID 的错误结果。

## 一个 Edit 怎样真正写到磁盘

假设模型提出：

```text
tool_use id=toolu_edit_port_01
name=Edit
file_path=/workspace/project/config.json
old_string='"port": 8080'
new_string='"port": 9090'
```

![工具调用从解析、校验、Hook 和权限进入真实执行，再把结果回灌 Agent Loop](assets/visuals/tool-control-lifecycle.svg)

客户端按顺序处理：

1. **名称解析。** 当前工具 registry 将 `Edit` 或 alias 解析到可执行对象；找不到就直接生成 error result。
2. **结构校验。** JSON 与 input schema 必须可解析，默认值在这里确定。
3. **工具自定义校验。** Edit 检查绝对路径、已完整读取、磁盘未漂移、旧字符串匹配数和大小限制。
4. **PreToolUse。** Hook 可以补充上下文、拒绝、defer、给出权限决定或返回 `updatedInput`。
5. **Permission / policy。** 当前模式、allow/deny/ask rule、managed setting、workspace trust 和必要 classifier 合并成决定。
6. **改写输入复验。** Hook 或 permission 返回的新 input 会重跑通用 schema 与 permission 语义检查。
7. **适用的执行隔离。** Bash 等路径进入 filesystem/network/credential sandbox；Edit 走自己的文件保护，不会凭空启动一层 Shell wrapper。
8. **真实 `tool.call`。** 这一刻才产生文件、进程或网络副作用。
9. **PostToolUse 与结果合同。** 后置 Hook 观察结果，客户端验证输出并生成配对的 `tool_result`。

一个需要保留的微小但重要的细节：PreToolUse 把原始 Edit 路径改成另一个文件后，通用管线会复验 schema 与 permission 语义，但不会自动重跑 Edit 自己的 custom `validateInput`。后续真实实现仍会遇到当前磁盘状态，但不能把这写成“所有前置校验完整重跑”。

## 权限不是一个危险分类器

确定性控制先于 Auto Mode：

- managed policy、显式 deny/ask、工具约束和 workspace trust 构成不可被普通分类结果越过的下限；
- permission mode 决定交互方式与默认策略，不会关闭工具自己的输入校验；
- 一次性批准、session 范围批准和持久规则是不同状态，UI 必须准确显示 scope；
- Auto Mode 只裁决前面仍未决定的普通询问；无有效 verdict、解析失败或不可用时走 fail-closed；
- `bypassPermissions` 仍不等于关闭 OS/TCC、sandbox、远端服务权限或工具内部约束。

这也是 `2.1.235` 修复 Shift+Tab permission bug 的实质：原本一个输入导航动作可能被误解释为批准 Edit 并授予 session-wide 权限。修复的是“界面动作、授权说明和实际 scope”之间的状态一致性，不只是键盘体验。

## Hooks 能改变控制流，也需要边界

PreToolUse 在副作用前，可以阻止或改写；PostToolUse 在副作用后，只能影响后续消息和观察；PostToolBatch 的时机又与单工具后置处理不同。Stop hook 能在模型准备结束时阻止退出，让反馈重新进入 Agent Loop。

因此 Hook 不是一组日志回调。它需要 timeout、错误处理、连续阻断上限和清晰的 updated input 合同。Hook 自己执行的外部命令也属于真实副作用，compact 或 resume 不会替它回滚。

## Sandbox 是另一层控制面

![Sandbox 的安装、策略编译与每次命令执行属于不同阶段](assets/visuals/sandbox-install-runtime.svg)

Sandbox 要分成两件事：宿主上是否安装并支持对应能力，以及某一次 Bash/进程调用是否实际进入 filesystem、network 与 credential enforcement。一个工具获得 permission allow，不代表子进程拥有无限文件或网络能力；反过来，CLI 进程 exit 0 也不能单独证明目标副作用成功。

网络控制还会涉及 proxy、`NO_PROXY`、CA、mTLS、proxy auth 与不同 transport。验证一条 HTTP 路径不能自动覆盖 MCP、Git、WebSocket、SSE 或 CONNECT relay。

## MCP 怎样变成 Agent 可用工具

![MCP 从受信任配置、连接与认证进入工具 generation，再参与 Agent Loop](assets/visuals/mcp-runtime-lifecycle.svg)

MCP 工具进入循环前要经过配置来源与 trust、连接、认证、`tools/list`、名称映射和 generation 管理。服务端发出 `tools/list_changed` 后，客户端刷新列表并使相关 schema/cache 身份失效；精确探针显示新工具会在后续请求中出现，不应描述成“当前正在发送的请求即时热替换”。

当目录很大时，Tool Search 可以 defer 完整 schema；当 MCP 断线、认证失败或工具消失时，错误会沿动态工具恢复路径回到 Agent Loop。远端 MCP 服务执行成功后产生的副作用由远端 owner 持有，客户端只能记录已观察到的结果。

## 子 Agent 与权限上浮

子 Agent 有独立上下文和工具集合。默认 `permissionMode: bubble` 允许关键审批交给父会话，不是自动批准；worktree 隔离只覆盖相应文件范围，也不是数据库或远端 API 的事务隔离。Team/task/mailbox 解决任务身份与消息投递，不能自动消除共享文件写冲突。

## 推荐阅读顺序

1. [工具、权限与 Hooks](articles/tools-permissions-hooks.html)：完整 Edit trace、权限模式、Hook 时序与失败矩阵。
2. [Auto Mode 两阶段分类器](articles/auto-mode-classifier.html)：确定性下限之后的分类预算、XML 解析与 fail-closed。
3. [Sandbox 安装与运行 Enforcement](articles/sandbox-install-and-runtime-enforcement.html)：宿主安装和每次命令约束分层验证。
4. [MCP Runtime 生命周期](articles/mcp-runtime-lifecycle.html)：连接、认证、generation、动态刷新与错误恢复。
5. [Onboarding 与 Workspace Trust](articles/onboarding-workspace-trust-and-safe-startup.html)：项目内容何时有资格影响工具、Hook 和扩展。

站内继续：[状态边界、恢复与数据流](boundaries.html) · [参考手册](reference.html) · [返回首页](index.html)
