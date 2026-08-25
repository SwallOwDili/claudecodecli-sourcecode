---
title: 从一条真实工具链开始
description: 用 2.1.235 精确二进制的 Read 探针，理解模型、客户端、工具结果和下一轮请求之间的关系。
section: 入门
order: 2
---

# 从一条真实工具链开始

理解 Claude Code 最快的方法，不是先记几十个组件名，而是跟完一个真实闭环：**模型请求读取文件，客户端读取文件，结果进入下一次模型请求。**

这条链来自 `2.1.235` 精确二进制的受控运行探针。模型端返回固定内容，会话只开放内置 `Read`，因此观察到的状态变化来自客户端，而不是一次偶然的模型发挥。

## 0. 文件还只在本地

测试目录有一个文件：

```text
$WORKSPACE/probe-fixture.txt
AGENT_LOOP_FILE_MARKER
```

用户消息是 `AGENT_LOOP_INITIAL_MARKER`。客户端构造第一次 `POST /v1/messages` 时，消息里只有这条用户输入；请求的 `tools` 中声明了 `Read`。**文件正文此时还没有发给模型。**

## 1. 模型提出结构化动作

第一次模型流返回：

```text
content_block_start:
  type: tool_use
  id: toolu_agent_loop_probe
  name: Read

input_json_delta:
  {"file_path":"$WORKSPACE/probe-fixture.txt"}

content_block_stop
message_delta.stop_reason: tool_use
```

`content_block_stop` 表示这个工具块已经完整。`toolu_agent_loop_probe` 不是展示用标签，而是后续因果配对的 ID。模型表达了“希望读取这个路径”，但尚未读取文件。

## 2. 客户端才是真正的执行者

Claude Code 将完整工具块交给当前 iteration 的工具执行器。执行器解析名称、验证输入，并按当前权限配置调用内置 `Read`。本地结果包含：

```text
AGENT_LOOP_FILE_MARKER
```

这里发生的是客户端文件访问。模型只有在客户端把结果装入后续请求后，才会看见这一行。

## 3. 同一个 ID 把动作和观察接起来

第二次 `POST /v1/messages` 新增两段内容：

```text
assistant:
  tool_use:
    id: toolu_agent_loop_probe
    name: Read
    input:
      file_path: $WORKSPACE/probe-fixture.txt

user:
  tool_result:
    tool_use_id: toolu_agent_loop_probe
    content: ...AGENT_LOOP_FILE_MARKER...
```

`tool_result.tool_use_id` 与 `tool_use.id` 相同。模型因此知道“这段文本是哪个动作的结果”，而不是收到一条没有来源的新用户消息。工具失败也会沿同一个协议回到下一轮，成为模型可以修正策略的新观察。

## 4. 第二次模型请求才完成任务

模型在第二次请求里看见文件内容，返回固定文本 `TOOL_EXECUTION_OK`。客户端最终给出 `subtype=success`，进程退出状态为 `0`。

![Agent Loop 从模型流启动工具，经受控执行和结果回灌后决定继续或结束](assets/visuals/agent-loop-lifecycle.svg)

完整时序是：

```text
用户消息
  -> request 1
  -> assistant tool_use
  -> 客户端执行 Read
  -> tool_result
  -> request 2
  -> assistant 最终文本
  -> success
```

这条链建立了三个后续不会改变的事实：

- 模型没有直接访问本地文件；
- 客户端拥有工具执行、权限裁决和因果配对；
- 真实结果只有进入下一次请求，才成为模型的新上下文。

## 不要把四种“轮次”混在一起

| 节奏 | 从哪里开始，到哪里结束 | 为什么要分开 |
| --- | --- | --- |
| 用户任务 | 一次用户提交到客户端给出终态 | 可能跨很多模型和工具步骤 |
| Agent iteration | 一次消息视图装配、模型流、工具批次和继续判断 | `maxTurns` 与 Stop hook 在这一层有意义 |
| API attempt | 一次具体网络请求 | 重试或 fallback 不必等于新 iteration |
| 工具执行 | 一个 `tool_use` 从完整输入到 `tool_result` | 可能与同批工具并发，也可能形成屏障 |

因此，“请求重试了三次”不等于“Agent 已经消耗三轮”，“模型输出结束”也不一定等于用户任务结束。Stop hook、排队输入、malformed tool use、`max_tokens` continuation 和 fallback 都可能重新打开同一个任务的控制流。

## 从 Read 换成 Edit，会多出什么

`Read` 例子刻意压缩了控制面。一次真实 `Edit` 至少还要经过：工具名称解析、JSON/schema、Edit 自己的内容校验、`PreToolUse`、permission/policy、改写输入复验、真实 `tool.call`、`PostToolUse`、输出合同和 `tool_result` 映射。

关键边界是：**执行前的层可以阻止副作用；真实 `tool.call` 成功以后，后置 Hook、compact、resume 和 fallback 都不能自动把文件写回去。**

## 推荐阅读顺序

1. [Agent Loop 专题](articles/agent-loop.html)：继续追并发调度、队列、Stop hook、maxTurns、fallback 和终止状态。
2. [Prompt Assembly](articles/prompt-assembly-and-system-reminders.html)：解释第一次请求中的 system、动态上下文、附件和工具 schema 怎样组装。
3. [工具、权限与 Hooks](articles/tools-permissions-hooks.html)：把 `Edit` 的完整控制管线走到底。
4. [韧性与恢复](articles/resilience-and-recovery.html)：理解失败 attempt、消息 tombstone 与外部副作用的边界。

站内下一页：[Agent Loop 与运行时](runtime.html) · [返回首页](index.html)
