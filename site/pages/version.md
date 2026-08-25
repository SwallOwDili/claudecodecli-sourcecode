---
title: Claude Code 2.1.235 版本变化
description: 将 19 条 release note 还原为输入、权限、缓存、后台任务、失败和更新状态的具体修正。
section: 版本
order: 9
---

# Claude Code 2.1.235 版本变化

`2.1.235` 不是一次 Agent Loop、compact 或 MCP 架构重写。上游列出的 19 条变化集中在一个主题：**让界面展示的状态、客户端真正持有的状态和最终发生的动作重新一致。**

完整上游原文、固定 commit/响应 hash、逐条 Static/Probe/Boundary 证据在 [Release Notes 对照](articles/release-notes.html)。本页只解释这些修复为什么属于同一组工程问题。

## 1. 输入界面必须对应真正提交的状态

多行 prompt 的 slash command、keyword、mention 与 spellcheck decoration 曾可能因 raw/rendered offset 映射错误而偏移；深度 3+ Markdown 列表的 marker 和正文缩进 owner 也会分叉；Vim 详细 transcript 或 panel 重挂载可能丢失 NORMAL mode 与 cursor；快速 Arrow + Enter 可能提交上一帧高亮项。

本版分别修正逐行 segment、hanging indent、外部 composer state 和提交时读取最新 focused value。它们不是“视觉优化”这么简单：屏幕字符、光标、选项和最终提交动作必须指向同一个状态，否则用户无法可靠控制 Agent。

新增的 `spellcheck` 默认关闭，只在本地 prompt composer 工作。启用后按 `aspell -> hunspell -> ispell` 选择已安装程序，并带 batch、cache、timeout、一次重启和 session-disable；它不修改发送给模型的文本，也不是云端拼写服务。

**证据状态：** 多条有 Static；Shift+Tab 和快速选择还有精确二进制 PTY Probe。终端字体宽度、全部 Unicode 组合和真实 VS Code 多 panel 仍保留环境或外部边界。

## 2. 权限界面必须对应真正授权的 scope

最重要的修复是 permission comment 中的 Shift+Tab：旧路径可能把“关闭备注输入”误解释为批准 Edit，并扩大成 session-wide edit grant。`2.1.235` 让 comment input 先消费按键并退出输入，再允许 grant shortcut 处理。

Permission dialog 还统一了展示文本、实际 grant scope 和 `don't ask again`：内容无法完整展示时不再提供持久批准；Notebook delete/replace 无法读取旧 cell 时显示失败原因，而不是把未知内容伪装成空内容。

这组变化修的是风控正确性。审批者必须知道看到了什么、批准什么、批准持续多久。Probe 进一步验证 Shift+Tab 前后两个文件都未改变，显式批准后的第二次 Edit 仍需审批，排除了误授 session 权限。

![模型提议、客户端权限和真实副作用的状态边界](assets/visuals/product-surface-runtime-planes.svg)

## 3. 长会话要保留正确身份，而不是反复重做

LSP 断线/重连不再污染稳定 prompt cache identity，避免整段前缀被无意义重写；这不等于后续所有请求永久 cache hit，工具集合、system block、消息增长和 TTL 仍会改变 breakpoint。

Resume 或 relaunch 后，仍有 open tasks 的 expanded task list 会恢复展开态。后台 `/ultrareview`、`/autofix-pr` 等 cloud session 改为增量消费新 event，不再每次全量重扫和重渲染历史。这两条都在修“持久身份已经存在，但界面或 consumer 又从头开始”的问题。

当前证据能说明实现路径与状态变化，没有长时性能基准，因此不应给出节省 CPU 或内存的百分比。

## 4. 失败要早、明确，并能进入下一步处理

Agent tool 在默认 `general-purpose` 不可用时，不再广告一个不存在的默认值，而是列出当前可用 Agent。超大 `SendMessage` 在跨 session 投递前直接拒绝，不再静默丢失；模型因此能缩短、拆分或改用文件。

关闭 auto-compact 后触及 context limit，错误会明确说明开关状态并指向 `/config`。`claude rc` 与交互式 Remote Control 复用 enterprise-gateway availability gate，避免两个入口给出矛盾结果。

embedded grep 对病态 regex 快速失败，并修复 `-m N` 配合 `-A/-C` 的上下文边界。精确二进制 Probe 验证病态模式在 deadline 内以固定 size-limit error 和 exit 2 失败，`-m 1 -A 2` / `-m 1 -C 2` 保留正确两行 after-context。这里验证的是同一 binary 的 embedded `argv0=rg` 入口；模型的 Grep schema 本身不暴露 `-m`，不能写成模型发送了该参数。

这组修复共同把“静默丢失、很晚才失败、失败没有恢复入口”改成 Agent Loop 可以观察并处理的明确结果。

## 5. 安装完成不等于当前进程已经升级

后台更新完成后，footer 会持续显示 `Update installed` restart notice。这个状态只证明新版本文件已经落盘并被 UI 记录，不证明当前进程热切换了 bytes。

Native updater 会选择 channel/target、读取 manifest、下载并校验 SHA-256、发布到独立版本路径，再尝试切换 installer-owned launcher。版本文件落盘和 launcher 激活是两个 commit point；后者失败时，新文件仍可能存在，而当前进程始终继续运行旧版本。用户重启后才会沿新的 launcher 进入目标版本。

![Native 安装、自更新与下一次启动的分离状态](assets/visuals/release-lifecycle.svg)

## 哪些机制不是本版新增

Agent Loop、Prompt Cache、Tool Search、manual/reactive compact、MCP、子 Agent、Hooks、sandbox、telemetry 和 Native bridge 都是理解 `2.1.235` 必须掌握的基础架构，但不能因为本仓库首次把它们讲清楚，就归为本版新功能。

版本对比要分两层：先描述基线机制，再描述本版修改了哪个 gate、状态字段、失败分支或用户表面。否则一篇“版本分析”很容易把产品全貌和 release delta 混成同一张功能清单。

## 推荐阅读顺序

1. [Release Notes 19 条逐项对照](articles/release-notes.html)：先核对上游原文与每条证据等级。
2. [2.1.235 状态边界修正](articles/product-surface-evidence-map.html)：理解这些变化为什么落在三个状态世界的边界。
3. [输入、媒体、IDE 与 Chrome](articles/tui-input-accessibility-media-ide-chrome.html)：输入 offset、Vim、dialog、spellcheck 和 IDE surface。
4. [Native 安装、自更新与 Doctor](articles/install-update-doctor-lifecycle.html)：两个 commit point、launcher ownership 与 restart boundary。
5. [完整深度技术指南](articles/claude-code-2.1.235-complete-guide.html)：在机制和版本变化分开后做系统查漏。

站内关联：[从一条真实工具链开始](start.html) · [证据与复核](evidence.html) · [返回首页](index.html)
