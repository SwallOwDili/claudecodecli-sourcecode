---
title: 上下文、缓存与压缩
description: 分清 Prompt Assembly、Prompt Cache、Tool Search、microcompaction、compact、transcript、resume 与 Memory。
section: 核心机制
order: 4
---

# 上下文、缓存与压缩

“上下文太长”只是表象。Claude Code 实际管理的是一组用途不同的对象：system 指令、动态机器状态、消息图、工具 schema、旧工具结果、compact summary、transcript 和持久 Memory。它们不能用一个“自动总结”概括。

## 模型看到的不是磁盘 transcript

![请求装配把运行合同、上下文、消息图、附件和工具定义编译成 wire view](assets/visuals/request-assembly-lifecycle.svg)

一次请求大致经历以下编译顺序：

1. 先确定运行合同：模式、model/provider、权限、工具能力与 feature gate。
2. 编译 top-level system sections，而不是拼一整段永不变化的字符串。
3. 独立构造 user context 与 system context，包括 cwd、Git、环境和受信任配置。
4. 从 transcript 事件恢复当前有效消息图，处理 fork、tombstone 与 compact boundary。
5. 在提交点计算文件、Plan、Skill、MCP 等 typed attachment。
6. 按目标 API 能力把 attachment 渲染成合法消息或 mid-conversation system block。
7. 加入 reminder、工具定义和 cache breakpoint，才形成最终 wire view。

因此，磁盘 JSONL 是持久事件账本，wire view 是当前请求的编译产物。两者相似，但不保证逐条相同。

## 六种机制分别改变什么

| 机制 | 直接治理的对象 | 不负责什么 |
| --- | --- | --- |
| Prompt Cache | 稳定 system/message 前缀和 breakpoint 的复用资格 | 不缩短逻辑历史，不恢复会话 |
| Tool Search | 完整工具 schema 何时进入 active context | 不延迟安装工具，也不是零 token 声明 |
| Context Hint | 客户端与服务端协作的上下文提示协议 | 不等于本地删除旧结果 |
| microcompaction | active view 中较旧、较大的 tool result | 不删除物理 transcript 或工具 ID 因果链 |
| compact | 用语义 Summary 和合法保留组重建历史表示 | 不撤销文件、进程或远端副作用 |
| Memory / CLAUDE.md | 跨轮或跨会话重新注入的持久知识 | 不等于 prompt cache，也不是模型内部记忆 |

这张表是阅读边界，不是实现细节的替代。下面按一次长会话的自然顺序解释它们怎样接力。

## 稳定前缀决定缓存是否有价值

Prompt Cache 的关键不是“开了缓存”，而是稳定内容能否停留在稳定边界。Claude Code 把 system prompt 分段，对消息设置 breakpoint，并根据模型与配置选择 5 分钟或 1 小时 TTL 资格。普通追加消息不必破坏旧前缀；system section、活跃工具集合、模型身份或缓存 TTL 变化则可能产生新写入或 miss。

本版修复的 LSP reconnect 问题正属于 cache identity：普通断线重连不应让整个 prompt cache 失效。但这不意味着所有后续请求永久命中。真正判断 cache break，要结合请求 fingerprint 与响应中的 cache-read 变化，而不是只看“发生了重连”。

## Tool Search 延迟的是 schema

当内置工具、MCP 和插件提供大量工具时，完整 description 与 input schema 会占据稳定前缀。Tool Search 可以让部分工具以 deferred declaration 出现在请求中，模型在需要时再发现完整 schema。

deferred 工具不是“完全不在请求里”，也不是“运行时才安装”。节省的是初始 active context 中的完整定义；代价是多一步发现、generation 刷新和缓存失效处理。工具目录不大或服务端能力不满足时，客户端会回退到普通声明。

## 旧结果先做局部治理

长会话中，体积最大的内容常是早期 `Read`、`Grep` 或命令输出。Context Hint 与 microcompaction 处理这类局部压力：前者属于客户端与服务端的协作协议，后者在本地重写 active view，把满足条件的旧工具结果替换为更小的表示，同时保留 `tool_use`/`tool_result` 因果关系。

这一步不产生一份完整会话总结，也不删除物理 transcript。它的目标是在不切换整段历史表示的情况下，回收低价值 token。

## `/compact` 的普通路径

![compact 先生成 Summary，再以合法消息组和精确附件重建上下文](assets/visuals/compact-lifecycle.svg)

手工 `/compact` 的 normal miss 路径不是“保留末尾 N 条”：

1. 客户端选择合法切点，避免拆开 `tool_use` 与配对的 `tool_result`。
2. 它插入专用总结请求，要求纯文本输出 `<analysis>` 后跟 `<summary>`，并反复禁止工具调用。
3. 返回后客户端删除 `<analysis>`，提取 `<summary>`，形成 `Summary: ...` 文本。
4. 较早历史由 Summary 承接；切点后的合法消息组按该路径规则保留。
5. 客户端重新装入近期文件、Plan、Skills、MCP 和 Hook 等精确附件，并写 compact boundary。
6. 下一次请求从这份新表示继续；磁盘 transcript 仍保留可供 resume 修链的事件。

预计算 compact 只是提前生成候选 Summary，命中时还要校验 anchor、分支和有效期；reactive compact 是 prompt-too-long 后的恢复；部分 SDK/full 路径又有不同的保留规则。不能把某一路径的 `messagesToKeep` 套到所有 compact。

![compact 后的请求由 Summary、合法近期因果和重新计算的附件组成](assets/visuals/compact-rebuilt-context.svg)

## Resume、Checkpoint 与 Memory 是不同恢复对象

Transcript 保存消息事件与父子 UUID 关系；compact boundary 标记一次表示切换；resume 选择 leaf、修复合法链，再重新计算当前动态附件。它不会复活上一次进程，也不是把旧 wire request 原封不动重放。

File checkpoint 保存受管文件的有限快照，rewind 能恢复它覆盖的文件和会话位置，但不能补偿数据库、remote push 或第三方 API。Memory、`CLAUDE.md`、Rules 与 Skills 则是在新请求中重新注入的持久文本；它们有自己的发现、截断和预算，不与 prompt cache 共用生命周期。

![Session、compact boundary、checkpoint 与外部状态各自有恢复 owner](assets/visuals/session-recovery-lifecycle.svg)

## 四个常见症状怎样定位

**每轮都贵，但 context 看起来不大。** 先检查稳定前缀是否反复改动、工具集合是否抖动、TTL 是否过期，以及 cache-read 是否真正下降。

**会话不长，窗口却接近满。** 检查完整工具 schema、动态附件、大型工具结果和 system context，不要只数聊天轮数。

**Resume 后 token 突然上升。** Resume 会修复消息图并重算动态附件；旧 cache 身份未必继续有效，Memory/Skill/MCP 状态也可能重新注入。

**Auto-compact 没触发。** 有效窗口、输出预留、blocked threshold、用户开关和当前路径共同决定阈值；它不是一个对所有模型固定的百分比。

## 推荐阅读顺序

1. [Prompt Assembly](articles/prompt-assembly-and-system-reminders.html)：先理解一次请求究竟装了什么。
2. [上下文治理与多层缓存](articles/context-governance-and-caching.html)：缓存、Tool Search、Hint、microcompaction 与四条 compact 路径。
3. [`/compact` 可视化专题](articles/compact-visual-guide.html)：用 Claude Code 自身的 Grep/Read 会话对照压缩前后。
4. [会话、Checkpoint 与 Memory](articles/sessions-checkpoints-memory.html)：消息图、boundary、resume、fork 和 rewind。
5. [Memory、CLAUDE.md、Rules 与 Skills](articles/memory-claude-md-skills-lifecycle.html)：持久知识怎样进入有限上下文。

站内继续：[工具、权限与扩展](tools.html) · [状态边界、恢复与数据流](boundaries.html) · [返回首页](index.html)
