---
title: 参考手册
description: 按实际问题选择 Claude Code 2.1.235 的命令、设置、工具、Hook、协议、遥测和错误参考。
section: 查阅
order: 7
---

# 参考手册

参考手册适合查字段、入口和枚举，不负责从头教授架构。先明确你在查什么，再进入对应文档；直接打开最大的 JSONL 或事件目录，通常只会得到一个没有 owner 的字符串。

## 查命令：先分本地动作还是 Agent prompt

[`CLI 命令树`](articles/cli-command-reference.html) 解释进程入口、flags 和子命令；[`Slash Command 参考`](articles/slash-command-reference.html) 区分 `local`、`local-jsx` 与 `prompt` 三种 command type，以及 interactive、print、SDK、thin client 的实现 twin。

当一个命令“看起来执行了却没产生结果”时，先确认它只是打开 UI、写本地设置、展开成 Agent prompt，还是向宿主发 RPC。命令 handler 返回成功，不等于后续模型已经完成业务目标。

**推荐顺序：** [CLI 命令树](articles/cli-command-reference.html) -> [复杂 Slash Command 生命周期](articles/complex-slash-command-lifecycles.html) -> [CLI、SDK 与输出协议](articles/cli-sdk-output-protocol.html)。

## 查工具：从 registry 回到执行合同

[`核心工具参考`](articles/builtin-tools-reference.html) 记录内置工具的 schema、输入约束、权限与副作用；[`工具注册与宿主表面`](articles/tool-registration-and-host-surfaces.html) 解释 canonical name、alias、deferred 工具和不同 host 的可用集合。

看到一个工具名时，不要直接推断它在当前 session 可用。还要看 provider capability、workspace trust、feature/policy gate、工具 generation 与 host surface。

**推荐顺序：** [核心工具参考](articles/builtin-tools-reference.html) -> [工具、权限与 Hooks](articles/tools-permissions-hooks.html) -> [Hook 事件参考](articles/hooks-event-reference.html)。

## 查设置：字段存在不等于当前生效

[`Settings 全字段参考`](articles/settings-reference.html) 适合查类型、默认和来源；[`Settings Resolution 与 Reload`](articles/settings-resolution-and-reload.html) 解释 user/project/local/managed/CLI/environment 的逐字段合并、限制和 live reload；[`Feature Flags 与 Remote Config`](articles/feature-flags-remote-config.html) 处理远端求值、缓存和 Boundary。

同一个 setting 的值可能受来源限制、managed lock、当前运行模式与二次 gate 影响。只在 schema 里找到字段，最多证明声明存在。

**推荐顺序：** [Settings 全字段参考](articles/settings-reference.html) -> [Settings Resolution 与 Reload](articles/settings-resolution-and-reload.html) -> [Settings、Feature Flags 与 Managed Policy](articles/settings-feature-flags-policy.html)。

## 查扩展：先确定谁提供能力

[`Plugins、Skills、Commands 与 LSP`](articles/plugins-skills-commands-lsp.html) 解释本地扩展发现与缓存；[`MCP Runtime 生命周期`](articles/mcp-runtime-lifecycle.html) 解释远端 server 的连接、认证、工具 generation 和动态刷新；[`Connectors、Catalog 与 MCP Operators`](articles/connectors-catalog-and-mcp-operators.html) 处理更高层的目录与操作入口。

Skill 是上下文与工作流材料，MCP 是运行时协议，Plugin 可以同时贡献命令、Hook 或工具。名称相近不代表状态 owner 相同。

**推荐顺序：** [Plugins、Skills、Commands 与 LSP](articles/plugins-skills-commands-lsp.html) -> [MCP Runtime 生命周期](articles/mcp-runtime-lifecycle.html) -> [子 Agent、Team 与 Task Runtime](articles/subagent-team-task-runtime.html)。

## 查会话和存储：先确认恢复对象

[`Storage v5 参考`](articles/storage-v5-reference.html) 用于查本地持久结构；[`会话、Checkpoint 与 Memory`](articles/sessions-checkpoints-memory.html) 解释消息图、compact boundary、fork 和 rewind；[`项目 Purge、Import 与数据生命周期`](articles/project-purge-import-and-data-lifecycle.html) 解释预览、digest、archive guard 与部分完成。

删除本地文件、清理 transcript、rewind 代码和撤销远端动作是四类不同操作，不要因为都叫“恢复/清理”就混用。

**推荐顺序：** [会话、Checkpoint 与 Memory](articles/sessions-checkpoints-memory.html) -> [Storage v5 参考](articles/storage-v5-reference.html) -> [Project Purge、Import 与数据生命周期](articles/project-purge-import-and-data-lifecycle.html)。

## 查遥测、错误和 API：先找状态机，再找事件名

[`遥测事件目录`](articles/telemetry-event-catalog.html) 适合按场景查事件、payload 和出口资格；[`错误与诊断图谱`](articles/error-diagnostic-atlas.html) 把异常连接到分类、恢复、用户结果和观察面；[`API、Beta 与路由所有权`](articles/api-beta-route-ownership.html) 区分真实 consumer、SDK 依赖、embedded reference 与远端 Boundary。

事件名、错误文案、URL 或 beta 字符串本身不证明调用发生。优先找到 owning mechanism，再用目录定位字段和源码位置。

**推荐顺序：** [遥测、日志与诊断](articles/telemetry.html) -> [遥测事件目录](articles/telemetry-event-catalog.html) -> [错误与诊断图谱](articles/error-diagnostic-atlas.html)。

## 查机器清单：用稳定字段做版本对比

[`机器清单字段阅读指南`](articles/inventory-field-guide.html) 解释 `comparisonKey`、`comparisonValue`、lexical function、immediate consumer 和证据等级。跨版本时先用稳定语义字段配对，再回到 reachable consumer；行号、minified symbol、bytecode hash 或整块反汇编变化不能单独升级成功能变化。

环境变量和 Feature key 的全量参考用于防漏，不是按名称猜功能的词典。它们记录 `Static immediate consumer` 时，只证明值接下来流向哪里；完整 fallback、状态变化、失败和用户影响仍要回到机制专题。

三个超大参考页不会把整页正文塞进浏览器搜索索引。需要按精确名称查找时，使用轻量的 [Environment 标识符索引](search/environment-identifiers.html)、[Feature Key 标识符索引](search/feature-identifiers.html) 和 [Telemetry Event 标识符索引](search/telemetry-identifiers.html)；定位名称后再进入完整参考阅读 consumer、字段和 Boundary。

**推荐顺序：** [机器清单字段阅读指南](articles/inventory-field-guide.html) -> [Environment 全量参考](articles/environment-variable-reference.html) -> [Feature key 全量参考](articles/feature-flag-reference.html)。

## 需要全部入口时

[完整文章索引](articles.html) 保留全部教程、参考手册和证据入口；[2.1.235 深度技术指南](articles/claude-code-2.1.235-complete-guide.html) 适合已经建立运行模型后做系统查漏。不要把深度指南当第一篇，它的作用是覆盖，不是替代渐进解释。

## 推荐阅读顺序

先从本页与你的问题对应的小节进入一篇机制文章，再打开相邻参考手册查字段，最后用 [机器清单字段阅读指南](articles/inventory-field-guide.html) 回到稳定语义和源码位置。需要全局查漏时，再读 [完整深度技术指南](articles/claude-code-2.1.235-complete-guide.html) 与 [完整文章索引](articles.html)。

站内关联：[证据与复核](evidence.html) · [2.1.235 版本变化](version.html) · [返回首页](index.html)
