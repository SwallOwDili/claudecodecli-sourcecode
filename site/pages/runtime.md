---
title: Agent Loop 与运行时
description: 解释 Claude Code 2.1.235 的核心循环、流式工具启动、并发屏障、停止条件与子 Agent 隔离。
section: 核心机制
order: 3
---

# Agent Loop 与运行时

Agent Loop 不是“反复调用模型”六个字。它是一套客户端状态机：每次迭代都重新吸收外部输入、构造有效消息视图、调用模型、调度工具、合并结果，然后根据停止条件决定继续方式。

## 循环拥有的状态

运行时至少要同时维护：

- 当前有效消息图，以及 compact、tombstone 和 attachment 形成的发送视图；
- 当前模型、provider、effort、fallback 与 API attempt 状态；
- 本 iteration 的工具集合、执行队列、并发屏障与 abort signal；
- 用户中途输入、后台通知、Stop hook 反馈和 terminal reason；
- `maxTurns`、fallback sweep、连续异常等预算与计数器。

这些对象不属于模型。模型只看到客户端最后编译出的请求，并以流式 content block 返回提议。

## 一次 iteration 的实际顺序

![Agent Loop 生命周期](assets/visuals/agent-loop-lifecycle.svg)

1. **吸收外部状态。** 客户端先处理排队用户输入、passive command、后台任务通知和停止信号。
2. **重建发送视图。** 它从消息图、compact boundary、动态附件和缓存状态生成这一次请求真正使用的 messages。
3. **治理上下文。** Context hint、microcompaction、precompute 或 reactive compact 可能在模型调用前后改变 active view。
4. **冻结本轮执行器。** 当前可用工具、permission context、Hook 和 abort 状态成为本 iteration 的执行环境。
5. **解析模型流。** 文本、thinking 和 `tool_use` block 被逐块消费；一个工具块完整后即可开始执行。
6. **形成工具批次。** scheduler 根据工具及其输入是否 concurrency-safe 决定重叠执行或建立屏障。
7. **回灌观察。** 每个结果按 ID 映射成 `tool_result`，与 PostToolBatch、用户新消息一起进入消息图。
8. **决定终态。** 无工具回复、Stop hook、`maxTurns`、fallback、malformed tool use 和异常类型共同决定结束、重试或继续。

## 工具可以早于模型流结束启动

模型返回的一个 `tool_use` 在 `content_block_stop` 时已经具备完整名称和 input。客户端不必等待整条 assistant message 的 `message_stop`，就可以把这个块送入执行器。

这降低了工具密集任务的等待时间，但也带来两个约束：

- 后续还可能出现更多工具块，scheduler 必须保持确定的结果配对和屏障顺序；
- 一旦工具已经产生外部副作用，后续流错误或模型 fallback 只能修复消息表示，不能把现实状态回滚。

## 并发不是无条件 `Promise.all`

读操作、独立搜索等可能被判定为并发安全；写文件、Shell 或输入相关动作通常需要更严格的屏障。判定既看工具类型，也可能看具体 input。运行时允许一段安全操作重叠，但在遇到非并发安全项时等待前面的工作收束，再继续后续队列。

这保证了两个目标：减少无依赖工具的串行等待，同时避免多个有顺序依赖的副作用互相穿插。用户中途输入也不是永远立即打断：客户端会根据当前工具阶段和 abort 能力决定中止、排队或在批次后吸收。

## “没有工具调用”也不一定结束

普通文本回复可以结束任务，但以下分支可能继续：

- `max_tokens` 截断触发 continuation；
- malformed tool use 生成修复反馈；
- thinking-only 响应收到继续提示；
- Stop hook 阻止结束并把反馈送回循环；
- prompt-too-long 被暂时扣住，客户端尝试 compact；
- 当前模型失败后进入受控 fallback sweep。

终止时客户端保存的是有类型的 terminal reason，而不是只看进程 exit code。`success`、预算耗尽、用户中止、Hook 阻断、API 错误和工具失败属于不同的恢复合同。

## Stop hook 为什么会重新打开循环

模型已经没有工具调用时，客户端仍可执行 Stop hook。Hook 若允许，任务结束；若返回阻止和反馈，反馈会成为新的上下文，Agent Loop 再运行一次。本版对连续阻止有上限，避免一个 Hook 永久占住循环。

所以 Stop hook 不是完成后的日志回调，而是能改变控制流的裁决点。它同样需要超时、错误处理和熔断语义。

## 主 Agent、子 Agent 与后台 Agent

子 Agent 复用核心循环机制，但不共享父 Agent 的消息数组：它拥有独立 messages、工具集合、`maxTurns`、abort controller 和上下文预算。`model: inherit` 表示默认继承模型选择，不等于共享同一次推理；`permissionMode: bubble` 表示关键审批可以上浮，不等于绕过权限。

后台任务还多一层 owner：启动 ACK 只说明任务已经交给后台系统，最终结果要通过任务 registry、通知或 mailbox 回来。把“已启动”写成“已完成”会直接破坏因果账本。

![子 Agent、Team 与 Task 的状态和消息边界](assets/visuals/subagent-team-task-lifecycle.svg)

## 出错时先找 owner

同样是“又执行了一次”，可能分别由 HTTP retry、stream fallback、model fallback、output repair、context compact、tool error feedback 或 Hook re-entry 触发。它们拥有不同计数器，保留不同消息，也承担不同的重复副作用风险。

排障时先问三件事：当前失败属于哪个 owner；临时消息是否已进入有效图；外部动作是否已经完成。只看终端最后一行，很容易把网络重试、Agent 继续和工具重做混为一谈。

## 推荐阅读顺序

1. [Agent Loop 完整专题](articles/agent-loop.html)：主调用链、状态字段、探针和每个终止分支。
2. [技术机制总图](articles/technical-mechanism-atlas.html)：把 loop 放回请求、工具和恢复的全链路。
3. [Runtime Supervision](articles/runtime-supervision-and-processes.html)：区分 Claude worker、PTY host、daemon 与持久任务 owner。
4. [子 Agent、Team 与 Task Runtime](articles/subagent-team-task-runtime.html)：独立上下文、task claim、mailbox 与后台持久性。
5. [韧性与恢复](articles/resilience-and-recovery.html)：七类恢复怎样与 Agent Loop 交接。

站内继续：[上下文、缓存与压缩](context.html) · [工具、权限与扩展](tools.html) · [返回首页](index.html)
