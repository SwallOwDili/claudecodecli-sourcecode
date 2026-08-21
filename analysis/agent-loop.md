# Agent Loop：Claude Code 如何从一次回答演化成持续执行

Claude Code 的核心不是“调用一次模型，再把文本打印出来”，而是一个由异步生成器驱动的状态机。模型输出工具调用后，CLI 会校验参数、判定权限、执行工具、把结果重新写进消息图，再决定是否发起下一轮模型请求。上下文压缩、模型 fallback、用户中途输入、Stop hook、最大轮数、子 Agent 和遥测都嵌在这条循环里。

本章只描述 2.1.235 发布 bundle 中可以直接追到的客户端行为。函数名是可读化 bundle 中保留下来的压缩符号；它们不是 Anthropic 原始 TypeScript 名称。

## 公开原理怎样变成本版结论

Anthropic 当前 Agent SDK 文档把 Agent Loop 概括为收集上下文、采取行动、验证结果并重复；Engineering 文章进一步把 Agent 描述为模型在反馈闭环中使用工具和从错误中恢复。这个公开模型解释“为什么需要循环”，但不证明 `2.1.235` 的流式工具启动点、计数器、hook cap 或 fallback 顺序。

本章采用三步验证：

1. 把公开主张拆成可观察假设，例如“工具结果会进入下一轮”“停止条件有界”“子 Agent 有独立上下文”。
2. 在 `2.1.235` canonical bundle 中连出从输入到状态变化再到输出的可达调用链，不用单个字符串命中代替实现证据。
3. 对工具回灌和 session resume 使用同哈希二进制的正向 probe；空列表与错误路径只证明对应 command/error surface，无法触发或依赖服务端的路径保留为边界。

逐项矩阵见 [公开主张与 2.1.235 验证](public-claims-validation.md)，完整系统位置见 [技术机制总图](technical-mechanism-atlas.md)。这一区分也适用于后续版本：当前官网文档可能已经描述更新实现，不能倒灌到旧分支。

## 先区分四个容易混淆的“轮次”

| 概念 | 本文定义 | 是否增加 `turnCount` |
| --- | --- | --- |
| 用户 turn | 用户提交一次任务，直到 CLI 返回一个 terminal reason | 整个过程只有一次外层用户 turn |
| Agent Loop 迭代 | 一次“整理消息 -> 请求模型 -> 处理工具/停止条件”的状态机迭代 | 正常工具回灌后加 1 |
| API attempt | 同一模型轮次中的网络重试、流转非流、模型 fallback 或拒绝 fallback | 不一定增加 |
| Tool batch | 同一模型响应中产生的一组 `tool_use` | 批次结束并准备再次请求模型时才增加 |

这一区分直接影响 `--max-turns` 的理解。它限制的是 Agent Loop 的模型轮次，不是 HTTP 请求次数，也不是工具数量。第一次模型请求的 `turnCount` 是 1；如果模型调用工具，工具执行完后准备第二次模型请求时计数变为 2。若 `maxTurns=1`，CLI 会保留第一轮工具执行结果并发出 `max_turns_reached`，但不会再请求模型生成工具后的总结。

证据：可读 JS 271560、272384-272424；SDK 最终结果把该状态映射为 `error_max_turns`，见 463093、463148。

### Agent Loop 不等于 `/loop` 命令

源码里的 `tengu_loop_command`、`tengu_loop_keepalive_fired`、`tengu_loop_dynamic_wakeup_*` 主要描述 `/loop` 定时提示和动态唤醒功能。本文的 Agent Loop 指 `tdf` 查询状态机，也就是每个主 Agent/子 Agent 都会经历的“模型 -> 工具 -> 结果 -> 再请求”执行引擎。

两者只在特定位置相交：如果本轮唯一工具是一个匹配已登记 loop prompt 的动态唤醒，主状态机会把它视为本轮结束条件，不再机械追加一次模型调用。不能因为看到 `tengu_loop_*` 事件，就把它们当成通用 Agent Loop 的完整遥测。

证据：事件名见 `first-party-events.txt` 636-642；动态唤醒结束分支见可读 JS 272337-272340。

## 主调用链

```text
USe                         外层 turn 生命周期
  -> HGS                    可选 observer tap，不改变核心执行语义
      -> tdf                真正的 Agent Loop 状态机
          while (true)
            -> 整理消息图、队列和上下文
            -> auto-compact / precompute 检查
            -> 创建本轮 streaming tool executor
            -> callModel
            -> 流式组装 assistant content blocks
            -> tool_use block 完成后立即排入执行器
            -> 判断无工具结束、错误恢复或工具回灌
            -> 执行完工具、hooks、队列吸收
            -> 写回 messages + toolUseContext
            -> 下一次 while 迭代
```

`USe` 是对外的异步生成器。它把核心状态机产生的 assistant、tool result、progress、system、tombstone、permission 和 SDK 状态事件逐个向上游转发；核心结束后，它收尾 active goal、command lifecycle 和 `tengu_turn_end`。

`HGS` 是 observer 包装层。启用时，它截获核心生成器发出的事件用于 observer/分类器，但真正执行仍由 `tdf` 完成。observer 初始化失败时，非交互路径会降级为 unobserved，而不是阻止主任务。

证据：可读 JS 271491-271548。

## 循环拥有的状态

`tdf` 没有依靠隐式递归维护进度，而是用一个状态对象在 `while (true)` 的每次迭代之间显式传递：

| 字段 | 含义 | 什么时候变化 |
| --- | --- | --- |
| `messages` | 下一次模型请求的逻辑消息集合 | compact、工具结果、hook 消息、队列消息或恢复提示加入后 |
| `toolUseContext` | 工具、权限、session、MCP、队列、abort controller、Agent 身份等运行上下文 | 工具产生 context layer、MCP/tool refresh 或 query tracking 更新后 |
| `compactTracking` | 上次 compact 的 turn ID、之后轮数、连续失败/快速回填计数 | compact 成功、失败或工具轮次完成后 |
| `turnCount` | 当前 Agent Loop 模型轮次，从 1 开始 | 工具批次回灌或 Stop hook 阻止结束后加 1 |
| `maxOutputTokensRecoveryCount` | 输出上限恢复尝试计数 | `max_tokens` 后重试时增加，新工具轮次归零 |
| `hasAttemptedReactiveCompact` | 本轮是否已经做过 prompt-too-long 响应式压缩 | reactive compact 后置真，进入正常下一轮后归零 |
| `thinkingOnlyNudged` | 是否已经对“只有 thinking、没有可见文本”的结束响应补过一次提示 | 补提示后置真，下一正常工具轮次归零 |
| `stopHookActive` | 当前是否是 Stop/SubagentStop hook 阻止结束后的重入 | blocking hook 后置真 |
| `stopHookBlockingCount` | Stop hook 连续阻止次数 | 每次 blocking 增加；正常继续时归零 |
| `pendingToolUseSummary` | 工具批次摘要的异步结果 | 工具完成后创建，后续迭代在模型流结束后等待并向上游发出；它不是下一轮模型 prompt 本身 |
| `transition` | 为什么重新进入循环 | `next_turn`、`reactive_compact_retry`、`max_output_tokens_recovery`、`malformed_tool_use_retry` 等 |

这组字段说明 Agent Loop 不是简单的 `while (response.tool_use)`。很多“再次请求模型”不是新工具轮次，而是同一轮的恢复分支，所以必须保留不同的计数器和 transition reason。

证据：可读 JS 271560、271640、272206、272219、272230、272241、272424。

## 一次迭代的完整路径

### 1. 在请求前吸收外部状态

主线程或 SDK 模式会先检查消息队列：

- turn 开始前吸收最高优先级的 `next` command 和 poll event；
- passive command 只有在完整转换成功且未 abort 时才从队列删除；
- 转换失败、部分生成或 abort 时保留原队列项，避免用户中途输入被静默丢弃；
- 后台模式可以通过 `shouldStopBeforeNextApiCall` 返回 `background_requested`，在下一次 API 请求前结束前台循环。

因此，用户在工具运行期间追加的提示通常不是直接修改正在传输的 HTTP body。它会进入 message queue，在工具批次后被转换成 attachment，再参与下一轮模型请求。

证据：可读 JS 271564-271623、272384-272410。

### 2. 重新建立发送给模型的消息视图

每轮从当前 `messages` 取最后一个 compact boundary 之后的有效表示，再处理内容替换、持久化工具结果引用、Agent 文件历史和当前工具集合。这里得到的 `Te` 是本次请求的工作消息集，不等于磁盘 JSONL 的全部原始记录。

请求前还会计算新的 `queryTracking`：第一轮生成 `chainId` 和 `depth=0`，同一链继续时 depth 加 1。模型请求、工具权限、工具成功/失败、compact 和终止事件都携带这两个字段，便于把一次用户 turn 内的多轮模型与工具行为串起来。

证据：可读 JS 271640-271652；工具事件见 316164、316297、316393、316476。

### 3. 每次模型调用前都检查上下文治理

Auto-compact 位于 Agent Loop 内部，不是会话结束后的清理任务。每次准备调用模型前都会执行：

```text
messages
  -> 内容替换/旧工具结果处理
  -> autocompact
  -> compact 成功则换成 summary + preserved messages
  -> compact 失败则记录连续失败
  -> blocked line 检查
  -> 预计算下一份 compact summary 的机会判断
```

如果 compact 之后很快再次填满，rapid-refill breaker 可以直接以 `rapid_refill_breaker` 结束，防止无限“总结 -> 立刻超限 -> 再总结”。如果在调用前已经达到 blocked line 且本轮没有成功 compact，则返回 `blocking_limit`，不会继续发送一个已知超限的请求。

更完整的阈值、precompute 和 cache 关系见 [上下文治理专题](context-governance-and-caching.md)。

证据：可读 JS 271653-271690、271763-271778。

### 4. 为本轮创建独立的工具执行器

每次模型轮次会新建一个 `h4a` streaming tool executor，并同时创建三个集合：

- `assistantMessages`：本轮已经完整产生的 assistant content block 消息；
- `toolUseBlocks`：本轮发现的全部 `tool_use`；
- `toolResults`：工具 progress、result、hook attachment 和其他回灌消息。

当模型 fallback、流式 fallback 或拒绝 fallback 需要丢弃当前响应时，这些集合会 reset，执行器会 abort 正在执行的工具并重建，防止旧响应的 tool result 被错误接到新模型响应上。

证据：可读 JS 270768-270775、271694-271708、271867-271892、271973-271980。

### 5. 构造并发送模型请求

Agent Loop 传给 `callModel` 的不只是 `messages`。同一调用还携带：

- system prompt、user context 和 thinking config；
- 当前完整工具集合和动态工具权限上下文；
- 当前模型、普通 fallback 链、拒绝 fallback 和 server fallback；
- query source、active skill、MCP server/tool、Agent 定义；
- max output override、effort、fast mode、task budget；
- cache 写入控制、fork point、sticky betas；
- abort signal、重试状态回调和 worker/client platform 信息。

这些字段让“换模型”“子 Agent”“print 模式”“工具权限”“上下文缓存”共享同一个循环，而不是各自复制一套执行器。

证据：可读 JS 271833-271842。

## 最关键的细节：模型仍在流式输出时，工具已经可以开始执行

模型流解析器在收到 `content_block_start` 后建立一个临时 block；`input_json_delta` 持续拼接工具 JSON；到 `content_block_stop` 时，CLI 才生成一个完整 assistant message。Agent Loop 收到这个 assistant message 后立即：

1. 把 message 放入 `assistantMessages`；
2. 找出其中的 `tool_use` block；
3. 标记 `needsFollowUp=true`；
4. 调用 `streamingToolExecutor.addTool()`。

这发生在整个 `message_stop` 到达之前。`Waf` 会同时等待“下一个模型流事件”和“工具执行器有新结果可排出”。如果工具先产生 progress 或 result，它返回 `tool_drain_tick`，主循环立即把工具事件向 UI/SDK 输出，然后继续消费模型流。

```text
模型：text block stop
  -> UI 已显示一段文本
模型：tool_use block stop
  -> addTool
  -> 权限允许后工具开始执行
模型：后续 content block 仍在到达
工具：progress/result 同时到达
  -> Waf 触发 tool_drain_tick
  -> UI/SDK 收到工具进度
模型：message_delta/message_stop
  -> 本轮响应最终完成
```

这能降低工具链总延迟，但带来一个重要边界：流式 fallback 发生时，CLI 可以 abort 尚未完成的工具、删除消息并清理 in-progress 状态，却不能自动撤销已经完成的外部副作用。例如一个写文件或远端变更工具已经成功后，后续流被判定无效，tombstone 只撤销对话表示，不等于业务回滚。

证据：流解析见可读 JS 409843-409933；立即加入执行器见 272032-272045；流与工具 drain 竞速见 267292-267310；fallback sweep 见 271867-271892、271973-271980。

## 工具并发不是“全部 Promise.all”

每个工具定义通过 `isConcurrencySafe(input)` 对具体调用判定是否可并发。执行器规则是：

```text
当前没有工具执行
  -> 任意工具可启动

当前已有工具执行
  -> 新工具自身 concurrency-safe
  -> 且全部正在执行的工具也 concurrency-safe
  -> 才能并发启动

遇到一个不能并发的排队工具
  -> 它形成顺序屏障
  -> 后面的工具不能越过它启动
```

这意味着多个只读、无共享状态的工具可以重叠；写文件、修改上下文或其他被判定不安全的工具会按响应顺序串行化。安全性由“工具类型 + 本次 input”共同决定，不是一个全局并发开关。若 `isConcurrencySafe` 自身抛错，客户端按 false 处理。

工具结果用 `tool_use_id` 配对，不依赖完成顺序。并发工具可以先后产生 progress；最终所有未完成工具会在本轮结束前由 `getRemainingResults()` drain 完。

证据：可读 JS 267124-267149、267204-267268。

## 单个工具调用的执行管线

`X1t -> Bpv -> jpv` 是单个 `tool_use` 的核心路径：

```text
1. 工具名/alias 查找
2. abort 与 isolation latch 检查
3. JSON parse / input coercion
4. Zod input schema 校验
5. 工具自定义 validateInput
6. PreToolUse hook
7. permission/canUseTool/policy/classifier 决策
8. permission 返回 updatedInput 时再次 schema 校验
9. 标记 in-progress
10. tool.call
11. 映射为标准 tool_result block
12. PostToolUse hook，可尝试改写 output
13. output schema 复验，失败则回退原输出
14. 写 progress/result/context layers
15. 清除 in-progress 状态
```

### 找不到工具

CLI 不会抛出一个让整个 Agent Loop 崩溃的裸异常。它生成带相同 `tool_use_id` 的 error `tool_result`，把“工具不存在”和相似工具提示反馈给模型。模型下一轮可以修正工具名。

### 输入 JSON 或 schema 错误

无法解析的 JSON、类型错误、缺失必填字段会变成 `InputValidationError` tool result。对于 deferred tool，如果该工具 schema 没有发给 API，错误还会明确要求先通过 Tool Search 加载，再重试，避免模型在未见 schema 时持续把数组、数字和布尔值写成字符串。

### PreToolUse 与 defer

PreToolUse 可以写进度消息、追加上下文、更新 input、停止继续、返回 permission decision，或在 print 模式 defer 单个工具。`defer` 在交互模式被忽略；同批有多个工具时也被忽略，因为只挂起其中一个会让 sibling tool 在 resume 时失去配对。

### 权限决策

hook 结果、permission mode、规则、managed policy、sandbox、安全分类器、用户对话框和 `canUseTool` 会汇合成 `allow`、`deny` 或未解决的 `ask`。拒绝不会调用工具，而是生成 error `tool_result`。如果 permission handler 改写了 input，CLI 会再次跑 input schema；无效改写被视为配置错误，不会把未经验证的数据交给工具。

### 工具成功与 PostToolUse

`tool.call` 成功后，工具自己的 mapper 把结果变成 Anthropic `tool_result` block。PostToolUse 可以返回附件或 `updatedToolOutput`；更新后的结果必须满足工具 output schema，复验失败时保留原始输出，并生成 hook error attachment。

### 工具异常

异常、MCP 鉴权错误、用户取消和 shutdown 都会转换成结构化 error `tool_result`，并携带 denial/cancel 类型。这样消息图仍保持每个 `tool_use` 都有对应结果，下一轮模型能看到失败原因，而不是收到破损历史。

证据：工具入口和隔离见可读 JS 316092-316131；输入校验见 316177-316211；PreToolUse/defer 见 316220-316267；权限见 316282-316327；调用、映射和 PostToolUse 见 316336-316457；异常路径见 316458-316487。

## 模型响应结束后，循环如何决定“结束还是继续”

### 没有工具调用

若本轮没有发现 `tool_use`，循环不会机械地继续。它依次处理：

1. prompt-too-long/image error 的 reactive compact；
2. `max_tokens` 的续写恢复；
3. `stop_reason=tool_use` 但没有可解析 block 的 malformed retry；
4. 只有 thinking、没有可见答案时的一次 nudge；
5. API error 终止；
6. Stop/SubagentStop hook；
7. 正常 `completed`。

### `max_tokens` 恢复

达到输出上限不一定立刻结束。CLI 会保留可用 assistant 内容，并加入一条隐藏提示，要求模型直接从中断处继续，不要道歉或复述。这个恢复有独立计数器，不增加正常工具轮次；次数耗尽后才把错误输出交给上层。

### malformed tool use

如果 API 的 stop reason 是 `tool_use`，但客户端没有得到任何完整可执行 block，CLI 会补一条隐藏纠错消息并重试一次。第二次仍失败才返回 `malformed_tool_use_exhausted`。这避免把半截 JSON 当成工具调用，也避免无限修复循环。

### thinking-only nudge

当模型以 `end_turn`/`stop_sequence` 结束、只有 thinking 而没有可见文本时，CLI 会补一次提示要求给出用户可见结果。只补一次，第二次仍如此就接受结束，避免无限 nudge。

证据：可读 JS 272171-272264。

## Stop hook 为什么会让模型再次运行

Stop/SubagentStop hook 不是只能做旁路通知。hook 返回 blocking error 时，CLI 会：

1. 把本轮 assistant 消息和 blocking error 都加入历史；
2. 设置 `stopHookActive=true`；
3. `turnCount + 1`；
4. 重新进入 Agent Loop，让模型根据 hook 反馈继续工作。

为了避免错误 hook 永久阻止结束，2.1.235 有两道上限：

- 用户设置的 `maxTurns` 先到时，以 `max_turns` 结束；
- `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` 默认是 8，连续超过时客户端覆盖 hook 并以 warning 结束。

hook 输入中的 `stop_hook_active` 用于告诉 hook“这已经是你阻止结束后的重入”。文档提示 hook 在该状态下应返回成功，否则会命中 cap。

证据：可读 JS 272253-272264；环境 schema 记录 `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`；事件 `tengu_stop_hook_block_count` 记录 `count`、`hit_max_turns`、`hit_cap` 和 `goal_active`。

## 有工具调用时的后半程

模型流结束后，执行器会 drain 全部剩余工具，再按顺序检查：

```text
abort?
  -> aborted_tools

PreToolUse defer?
  -> tool_deferred

hook stopped continuation?
  -> hook_stopped

工具结果声明 endsTurn / MCP meta end-turn?
  -> 运行 PostToolBatch 收尾
  -> 不再调用模型
  -> completed

PostToolBatch blocking?
  -> hook_stopped

MCP/tool 定义有刷新?
  -> 更新下一轮工具集合

用户中途命令/poll events?
  -> 转成 attachment 加入 toolResults

下一轮超过 maxTurns?
  -> max_turns

否则
  -> messages = 旧消息 + assistant + tool results
  -> transition = next_turn
  -> 再次请求模型
```

工具可以通过 `endsTurn` 明确结束本轮，不要求模型再总结。MCP meta 结束也走同类路径，但仍运行 PostToolBatch，让审计/清理 hook 有机会观察整个工具批次。

在进入下一轮前，客户端还会动态刷新 MCP tools 和 clients。远端 MCP 在本轮中途恢复连接后，下一轮可以拿到新工具集合，不必重启整个 Claude Code 进程。

证据：可读 JS 272295-272424；end-turn 收尾见 271439-271489。

## 模型 fallback 与工具副作用如何交互

Agent Loop 内部至少区分三类模型切换：

| 类型 | 触发 | 对当前 assistant/tool 状态的处理 |
| --- | --- | --- |
| 普通 fallback chain | overloaded、server error、model unavailable 等 | tombstone 当前 assistant/tool result，abort 执行中工具，换下一个模型重新请求 |
| refusal fallback | 模型返回 refusal，可能需要用户同意 | 可保留或拼接部分文本；拒绝切换时清理 provisional 状态 |
| server mid-stream fallback | 服务端在流中切换 serving model | 可丢弃拒绝 block、保留合法文本并标记 supersedes；allowlist 不允许目标模型时丢弃响应 |

所有路径都尽量清理对话层状态：

- assistant/tool result 通过 tombstone 撤销展示或 wire 参与；
- `set_in_progress_tool_use_ids` 移除 UI 中的运行标记；
- 正在执行的工具收到 abort；
- 新模型使用重建后的 streaming executor。

但这些是消息一致性措施，不是事务回滚。已经写入文件、提交 Git、发送网络请求或修改远端资源的工具副作用仍然存在。版本对比时，任何改变“工具何时开始”“fallback 何时触发”“哪些工具可并发”的代码，都应按高影响机制审查，而不能只记成一个事件名变化。

证据：可读 JS 271848-272104；执行器 abort 统计见 267075-267080、267108-267123。

## 主 Agent、子 Agent 和后台 Agent 是否共用同一个循环

共用核心 `USe/tdf`，但每个 Agent 实例有自己的：

- `querySource`；
- `agentId` / `agentContext`；
- model、effort 和 `maxTurns`；
- tools、allowed tools、permission layers；
- abort controller；
- transcript subdirectory、worktree 和文件历史；
- tool result 保留策略和 token usage。

custom/subagent wrapper `o8` 完成 Agent 定义、模型和工具继承后，再调用 `USe`。所以“子 Agent”不是主循环里的一个特殊 tool result parser，而是启动另一套隔离的 Agent Loop。主 Agent 可以等待它、后台运行它或通过任务/消息机制接收结果。

这也解释了为什么事件带 `is_subagent`、`agentContext`、`query_source_category` 和独立 `queryDepth`：同一用户任务可能同时存在多条 Agent Loop 链。

证据：可读 JS 276981-277145；`tengu_turn_end` 见 270840-270845。

## 终止状态字典

2.1.235 将 turn terminal reason 明确分组，而不是只返回 success/error：

| terminal reason | 含义 | 对上层是否按错误计 |
| --- | --- | --- |
| `completed` | 正常结束或 hook cap 覆盖后结束 | 否 |
| `background_requested` | 下一次 API 前切到后台 | 否 |
| `max_turns` | 再次调用模型会超过上限 | 内部 `p6n` 不计运行时错误；SDK 输出为 max-turns error variant |
| `tool_deferred` | print 模式挂起单个工具，等待恢复 | 否 |
| `hook_stopped` | Pre/PostToolBatch hook 阻止继续 | 否 |
| `stop_hook_prevented` | Stop hook 明确阻止 continuation | 否 |
| `aborted_streaming` | 模型流阶段被取消 | cancelled |
| `aborted_tools` | 工具阶段被取消 | cancelled |
| `blocking_limit` | 请求前已超过上下文 blocked line | 是 |
| `rapid_refill_breaker` | compact 后连续快速回填 | 是 |
| `prompt_too_long` | reactive compact 无法恢复 | 是 |
| `image_error` | 图片请求/尺寸等错误无法恢复 | 是 |
| `model_error` | 模型调用或循环 invariant 失败 | 是 |
| `api_error` | 结构化 API 错误消息 | 是 |
| `malformed_tool_use_exhausted` | tool-use 纠错重试仍失败 | 是 |
| `budget_exhausted` | task budget 用尽 | 是 |
| `structured_output_retry_exhausted` | 结构化输出修复耗尽 | 是 |
| `tool_deferred_unavailable` | deferred tool 无法恢复 | 是 |
| `turn_setup_failed` | turn 初始化失败 | 是 |

注意：内部分类把 `max_turns`、hook stop 和 defer 视为受控终止，不等同于运行时异常；SDK 最终协议仍可把 max turns 表示为用户可见 error subtype。这两个层级不冲突。

证据：可读 JS 270799-270845、463148。

## 可观测性：如何判断循环卡在哪一层

### 查询级关联字段

| 字段 | 读法 |
| --- | --- |
| `queryChainId` / `query_chain_id` | 一次用户 turn 内同一执行链的关联 ID，通常哈希/规范化后记录 |
| `queryDepth` / `query_depth` | 该链已经进入第几次模型迭代 |
| `querySource` | main、sdk、compact、agent:custom、hook_agent 等入口 |
| `terminal_reason` | 外层 USe 最终为什么退出 |
| `turn_count` | 只在 max-turns 等需要时记录的 Agent Loop 轮次 |

### 阶段 timing mark

客户端在关键阶段打点：

```text
query_fn_entry
query_autocompact_start / end
query_setup_start / end
query_api_loop_start
query_api_streaming_start / end
query_tool_execution_start / end
query_recursive_call
query_first_chunk_received
```

这些本地 profile mark 可以区分“请求前装配慢、首 token 慢、流式 stall、权限慢、工具慢、compact 慢”。开启 query profiling 才会生成报告；存在 mark 名称不代表默认上传完整 profile。

### 工具事件字段

`tengu_tool_use_success` 记录 duration、PreToolUse hook 时间、permission 时间、输入/结果大小、内存变化、MCP 类型、file extension/command 长度等。`tengu_tool_use_can_use_tool_rejected` 记录拒绝来源和 decision reason。`tengu_tool_use_error` 记录错误类、阶段和 request/query 关联。

内容字段是否进入一方、OTEL 或本地记录受各自独立的内容开关控制，不能因为事件 schema 有 `tool_input`/`error` 就断言默认上传原文。详见 [遥测专题](telemetry.md)。

## 精确版本正向探针：闭环不是纸面调用链

静态调用链能证明路径存在，但用户真正关心的是发布二进制是否按这个顺序运行。本仓库新增 [probe_agent_loop.mjs](../skill/claude-code-version-diff/scripts/probe_agent_loop.mjs)，在隔离 HOME/config/workspace 中启动本地 Messages API，并驱动 SHA-256 为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748` 的 2.1.235：

```text
request 1:
  user = AGENT_LOOP_INITIAL_MARKER
  tools includes Read schema

mock response:
  tool_use id=toolu_agent_loop_probe name=Read
  input.file_path=$WORKSPACE/probe-fixture.txt

CLI action:
  真实执行 Read，读取 AGENT_LOOP_FILE_MARKER

request 2:
  保留同 ID tool_use
  新增 tool_result.tool_use_id=toolu_agent_loop_probe
  tool_result content 包含 AGENT_LOOP_FILE_MARKER

mock response / CLI result:
  TOOL_EXECUTION_OK
  subtype=success
  exit=0
```

随后脚本使用同一个 session ID 运行 `--resume`。第三次主请求同时包含首次 user marker、首次最终助手文本 `TOOL_EXECUTION_OK` 和当前 `AGENT_LOOP_RESUME_MARKER`，最终 literal result 为 `RESUME_OK`、exit 0。

固化报告 [agent-loop-tool-result-resume.json](runtime-probes/agent-loop-tool-result-resume.json) 的 13 个 checks 全部为 true。它直接证明：

1. 工具 schema 进入首个真实请求；
2. 完整 `tool_use` 触发内置工具执行；
3. 工具结果以同 ID 回到下一次请求；
4. 最终 result 进入 success terminal state；
5. transcript 持久化后能成功 resume 并恢复历史。

这仍有明确边界：探针只使用 `Read` 和本地 mock server，不证明 Bash/sandbox/网络工具、MCP refresh、远端模型质量或服务端缓存。它证明的是客户端 Agent Loop 合同本身。

### 第二组控制流探针：Stop、maxTurns 与子 Agent

[runtime-controls.json](runtime-probes/runtime-controls.json) 和 [subagent-loop.json](runtime-probes/subagent-loop.json) 又补了三个容易被静态阅读误解的状态转移。

**Stop hook 不是“打印一句警告”。** 首次模型已经以 `end_turn` 结束，Stop hook 返回 block 和 `STOP_HOOK_REENTER_MARKER` 后，CLI 没有直接失败，而是把反馈装入第二个 Messages 请求。第二次模型返回 `STOP_REENTRY_OK`，Stop hook 再次运行但不阻止，最终 `subtype=success`、exit 0。这里消耗的是新的 model iteration；若连续阻止达到 cap，才进入熔断终态。

**`maxTurns=1` 允许本轮工具完成，但禁止工具后的第二次模型决策。** 探针收到 Read `tool_use` 后真实执行了工具，PostToolUse 也发生了；服务端只收到一个 Messages 请求。CLI 随后输出 `subtype=error_max_turns`、`is_error=true`、exit 1。它不是“最多调用一次工具”，而是“最多启动一次模型轮次”；本轮已经开始的工具不会因预算耗尽被回滚。

**本版 `Agent` 的父子回传是两阶段。** 父请求先调用 `Agent`，CLI 立即返回配对 `tool_result`，其语义是 `async_launched`，不是子任务结论。子 Agent 使用独立 prompt、独立工具表和独立 Messages 请求，完成后通过 `<task-notification>` 把 `SUBAGENT_CHILD_RESULT_MARKER` 入父队列。父循环共发出三个请求：启动、等待、消费完成通知并输出 `SUBAGENT_PARENT_OK`。把启动 ACK 当最终结果，会导致父模型重复创建子 Agent。

这三条运行结论都绑定同一个 `2.1.235` 二进制 SHA-256。它们把静态字段 `stopHookBlockingCount`、`maxTurns`、message queue 和 subagent state 还原成了真实时序，而不是只证明字段存在。

## 一个具体执行例子

用户请求：“读取配置文件，修改端口，然后运行测试。”模型在第一轮产生三个 tool use：Read、Edit、Bash。

1. Read 的 block 完成后立即进入执行器；若它被判定 concurrency-safe，可以在模型仍输出后续 blocks 时执行。
2. Edit 被判定非并发安全；如果 Read 仍在执行，Edit 等待，并形成屏障。
3. Bash 位于 Edit 之后，不能越过 Edit 提前运行，避免测试读到修改前文件。
4. 每个工具分别经过 schema、PreToolUse、权限和 sandbox 决策。
5. Read result、Edit result、Bash result 都带原 `tool_use_id` 写入 `toolResults`。
6. PostToolBatch 可以追加审计上下文或阻止继续。
7. 用户在测试期间输入“端口改成 9090”，该消息留在 queue；工具批次结束时被转换为 attachment。
8. 若未超过 `maxTurns`，第二轮模型看到原请求、三个工具结果和追加提示，再决定修正端口、重跑测试或给出最终答案。
9. 若 `maxTurns=1`，CLI 在工具批次后发出 max-turns 状态，不进行第二次模型调用。

这个例子展示了 Agent Loop 的用户价值：它维持工具顺序、结果配对、权限边界和中途输入一致性；同时也说明为什么“一个工具调用事件”不足以解释真实行为。

## 跨版本必须比较什么

后续版本对 Agent Loop 的对比至少覆盖：

| 机制 | 必须回答的问题 |
| --- | --- |
| 主状态机 | 外层函数、状态字段、transition reason、terminal reason 是否变化 |
| 流式工具启动 | 工具在 block stop、message stop 还是整轮结束后启动 |
| 并发调度 | concurrency-safe 判定、顺序屏障、result drain 顺序是否变化 |
| 工具管线 | input coercion/schema、hook、permission、output rewrite 的顺序是否变化 |
| 最大轮数 | 初始值、递增点、错误映射、子 Agent 继承是否变化 |
| Stop hook | 重入语义、默认 cap、环境覆盖和用户提示是否变化 |
| 队列吸收 | 中途输入、poll event、任务通知何时进入下一轮 |
| compact | pre-call、reactive、precomputed swap 与 rapid-refill breaker 是否变化 |
| fallback | tombstone、abort、partial salvage、allowlist 和副作用边界是否变化 |
| 子 Agent | model/tool/permission/worktree/transcript 继承与隔离是否变化 |
| 可观测性 | chain/depth、timing mark、tool decision/result 字段是否变化 |

比较报告不能只写“新增 `tengu_xxx` 事件”。先证明事件所在分支可达，再说明它是否改变工具启动时机、状态转移、失败恢复或用户可见结果。纯埋点变化只能标记为 observability change。

## 证据索引

| 主题 | 可读 JS 位置 | 机器清单 |
| --- | --- | --- |
| USe/HGS/tdf 主链 | 271491-272425 | `first-party-event-callsites.jsonl` 中 query/turn 事件 |
| terminal reason | 270799-270845 | `first-party-event-fields.tsv` 的 `tengu_turn_end` |
| streaming executor | 267089-267279 | tool/diagnostic 事件清单 |
| 模型流与工具 drain 竞速 | 267292-267310、271833-272045 | output protocol identifiers |
| SSE content block 组装 | 409843-409933 | static/template/error callsites |
| 单工具完整管线 | 316092-316487 | tool use/result/decision 事件与字段 |
| Stop hook 重入 | 272253-272264 | hook events、env schema、stop hook fields |
| 工具后处理和下一轮 | 272295-272424 | query attachment/tool refresh events |
| subagent wrapper | 276981-277145 | agent/tool/query source identifiers |

最终 canonical 证据仍是 [`../extracted/cli.js`](../extracted/cli.js)。[`../reverse/javascript/cli.readable.js`](../reverse/javascript/cli.readable.js) 只是从同一发布 bundle 生成的可读化定位视图，行号用于本版本复核，不应跨版本硬编码为稳定 API。
