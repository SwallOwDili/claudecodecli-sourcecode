---
title: 状态边界、恢复与数据流
description: 用 owner 模型解释 compact、resume、fallback、rewind、遥测和远端动作分别能恢复或删除什么。
section: 核心机制
order: 6
---

# 状态边界、恢复与数据流

Claude Code 的恢复机制看起来很多：retry、fallback、compact、resume、rewind、MCP reconnect、后台任务恢复。它们不是一份万能快照的不同按钮，而是各自向状态 owner 请求恢复。

## 先问：状态归谁所有

![模型提议、客户端因果账本和外部副作用分属不同 owner](assets/visuals/runtime-authority-lifecycle.svg)

| 状态 | 主要 owner | 能恢复什么 | 不能自动恢复什么 |
| --- | --- | --- | --- |
| 有效消息与模型 attempt | Agent Loop / message graph | 丢弃临时 attempt、重建下一次请求 | 已完成工具副作用 |
| Transcript 与 compact boundary | 本地 session storage | 选择消息链、修复 compact 后的逻辑历史 | 旧进程内存与远端服务状态 |
| 文件 checkpoint | 本地 checkpoint store | 被跟踪文件的有限快照 | 数据库、Git remote、第三方 API |
| MCP connection | MCP client 与远端 server | 重连、刷新工具 generation、重新认证 | 已提交的远端业务动作 |
| 后台 task / remote session | task registry、runner、remote owner | 查询仍在运行的任务、继续收取结果 | 把启动 ACK 变成已完成结果 |
| 原生安装 | version path、launcher、当前进程 | 发布新版本文件、切换下次启动入口 | 热替换当前进程 bytes |

只要先定位 owner，很多“为什么恢复失败”的问题就会变成明确边界，而不是神秘的不稳定。

## 七类“再来一次”并不相同

![请求、流、模型、输出、上下文、工具和会话分别有本地恢复环](assets/visuals/recovery-layers.svg)

**HTTP retry** 重做同一网络 attempt，保留逻辑请求身份；是否重试取决于 status、错误类和预算。**Stream fallback** 处理部分响应与 transport 切换。**Model fallback** 改变后续模型 attempt，但不能重做已经完成的工具。

**Output repair** 处理 `max_tokens`、malformed tool use 或 thinking-only 等模型输出问题。**Context recovery** 通过 compact 缩小 wire view。**Tool error feedback** 把失败变成配对结果，让模型决定下一步。**Session resume** 恢复持久消息图，并重新计算当前动态上下文。

它们的计数器、保留消息和副作用风险都不同。故障后看到第二次 API 请求，不能直接断言 Agent “重新做了一遍任务”。

## 三个看似矛盾但正确的结果

### 对话变短，文件仍保持修改

compact 改变后续请求使用的历史表示。文件系统是另一个 owner，所以已完成 Edit 不会随旧 tool result 的压缩而消失。

### Fallback 丢掉失败消息，外部调用仍存在

模型 attempt 的临时 assistant block 可以被 tombstone；如果工具已经成功调用远端服务，fallback 只会在新消息视图中继续，不能证明远端零副作用。

### Rewind 恢复代码，remote push 没有撤销

File checkpoint 只覆盖被追踪文件。它不是 Git、数据库和第三方服务的分布式事务管理器。

## “失败”也不等于“什么都没发生”

一个 API POST、原子 rename、Hook command 或子进程可能在客户端确认完整结果之前已经执行。之后出现 timeout、stream close 或解析错误，只能说明**最终结果未被完整确认**，不能自动升级成“动作没有发生”。

排障应分别记录：调用是否开始、外部系统是否收到、副作用是否可观察、客户端是否拿到完成确认、结果是否进入 transcript。把这五步压成 success/failed 会丢失最重要的恢复信息。

## 数据不是沿一根“遥测管道”流动

![模型推理、本地记录、一方事件、OTEL 与诊断拥有不同门控和目的地](assets/visuals/telemetry-pipeline.svg)

`2.1.235` 至少要分开这些数据线：

- **模型请求**发送编译后的 system、messages、active tools/results 和必要 metadata；关闭 telemetry 不会关闭推理流量。
- **本地 transcript**默认保存会话事件；它不是 provider cache，也不代表内容没有进入下一轮模型请求。
- **一方 analytics / Datadog / error reporting**有各自资格、采样、队列、字段处理和远端门控。
- **用户或管理员 OTEL**默认关闭，启用后由独立 exporter 发送；事件门和 prompt 正文内容门是两回事。
- **Feedback、Remote Control、Artifact、附件和 Voice**由显式产品动作产生，各有自己的确认和目的地。
- **MCP、WebFetch、Hooks、IDE 与 Chrome**把数据交给相应外部系统或本机集成，不受一个全局 telemetry switch 统一管理。

`compact`、`/clear`、tombstone、rewind 或删除本地 transcript 只改变客户端持有的表示。它们不是 provider、MCP、OTEL collector 或远端服务的删除 API。

## 遥测字段怎样读才不误判

静态 callsite 只能证明代码在某个分支准备记录事件；还要经过 enable gate、采样、队列、batch、exporter 和网络结果。Datadog allowlist 只提供转发资格，不证明事件已发送；OTEL 中 event、metric 和 span 也不是同一信号。

正文隐私还要分 gate：默认脱敏、显式 inline、写入文件或完全关闭可能走不同分支。一个通道隐藏 prompt，不代表模型请求、Feedback 或另一个 exporter 同样隐藏。

## 本地、远端与 Native 的最后边界

Remote Control 的 Agent Loop 和工具执行 owner 可以仍在本机，但 transcript 与控制活动会同步到远端；“代码本地执行”不等于“内容只留本地”。MCP 的 schema 在客户端注册，真正业务动作由 MCP server 拥有。

Native `.node` 模块通过 N-API 把 JavaScript 请求交给图像、音频、URL event 和 Computer Use 能力。仓库能恢复导出、参数、错误、依赖、object lifetime 和可观察副作用，也能构建兼容实现；构建时已经消失的内部源码结构不能从二进制中诚实复原。

![JavaScript、N-API 与原生平台能力之间的合同边界](assets/visuals/native-bridge-lifecycle.svg)

## 推荐阅读顺序

1. [韧性与恢复](articles/resilience-and-recovery.html)：按七个 owner 跟完一次失败链。
2. [全局数据流与隐私](articles/client-data-flow-and-privacy.html)：逐目的地解释内容门、删除边界与用户确认。
3. [遥测、日志与诊断](articles/telemetry.html)：一方、Datadog、OTEL、error 和本地诊断的独立管线。
4. [会话、Checkpoint 与 Memory](articles/sessions-checkpoints-memory.html)：resume、fork、rewind 和 transcript 的精确恢复对象。
5. [Native Bridge](articles/native-bridge-runtime.html)：JavaScript 到 `.node`、N-API 和平台副作用的边界。

站内继续：[2.1.235 版本变化](version.html) · [证据与复核](evidence.html) · [返回首页](index.html)
