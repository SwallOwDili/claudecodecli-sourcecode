# 韧性与恢复：Claude Code 出错后如何继续，又有哪些动作无法撤销

“支持重试”不足以描述 Agent 系统的可靠性。Claude Code 一次任务中可能同时发生 HTTP retry、流式降级、模型 fallback、输出续写、malformed tool 修复、reactive compact、工具错误回灌、hook 重入、MCP 重连、session resume 和 file rewind。它们恢复的对象不同，计数器不同，副作用边界也不同。

本章把 `2.1.235` 的恢复路径按故障层拆开，重点回答：失败发生在哪、保留了什么、丢弃了什么、是否会再次执行工具、用户会看到什么，以及为什么 tombstone 不能当事务回滚。

## 先区分七类“重来一次”

| 恢复动作 | 重做对象 | 是否增加 Agent `turnCount` | 工具是否可能重复 | 典型触发 |
| --- | --- | --- | --- | --- |
| HTTP/API retry | 同一模型请求 attempt | 通常不增加 | 尚未产生工具时不会 | 529、连接/服务错误、retryable status |
| stream -> non-stream fallback | 同一逻辑模型轮次的传输方式 | 不增加正常工具轮次 | 取决于失败前是否已有完整 tool block |
| model fallback | 换模型重新完成当前轮次 | 不一定增加 | 已完成 side effect 无法自动撤销，存在重复风险 |
| max_tokens recovery | 从截断 assistant 内容继续生成 | 独立 recovery counter | 通常不重跑已配对工具 |
| malformed tool retry | 修复 stop_reason/tool block 不一致 | 独立一次性恢复 | 未形成完整可执行 block 时不执行 |
| reactive compact retry | 压缩后重做过长请求 | 不等同正常 next turn | 请求前未执行工具时无副作用 |
| Stop hook re-entry | 带 hook feedback 进入下一模型轮次 | 增加 | 后续模型可能选择新动作 |

如果监控只统计 HTTP 次数，会把这些机制混在一起；如果 `maxTurns` 把所有 attempt 都算成 turn，又会让网络抖动提前耗尽 Agent 工作预算。2.1.235 为正常轮次、输出恢复、reactive compact、thinking-only nudge、Stop hook block 分别维护状态。

## 故障恢复总图

```text
build request
  |
  +-- context too long ----------> reactive compact -> rebuild request
  |
  v
send/stream model request
  |
  +-- retryable transport/status -> retry same logical call
  +-- stream unsupported/fails --> non-streaming fallback when allowed
  +-- model unavailable/refusal --> model/refusal fallback policy
  |
  v
parse assistant blocks
  |
  +-- max_tokens ---------------> continuation prompt, bounded counter
  +-- stop=tool_use but no block -> malformed retry once
  +-- thinking only ------------> visible-answer nudge once
  |
  v
execute tools
  |
  +-- validation/permission fail -> error tool_result, model can revise
  +-- runtime error/abort -------> structured result + cleanup
  +-- MCP disconnect -----------> tool error / reconnect / refresh later
  |
  v
decide stop/continue
  |
  +-- Stop hook blocks ---------> feedback + next model turn, cap 8
  +-- maxTurns reached ---------> terminal max_turns
  +-- success ------------------> completed
  +-- unrecoverable ------------> typed terminal reason
  |
  v
persist transcript/checkpoint/telemetry
```

## 请求层：先判断错误是否值得重试

### 可重试不等于所有错误都重试

请求层会区分状态码、provider、beta、模型可用性、cache-control、流式能力和连接状态。典型类别包括：

- overloaded/529、部分 server error；
- stale connection、idle/stall/watchdog；
- 网络超时或连接中断；
- provider 不支持某 beta/字段；
- cache-control rejection；
- model blocked/unavailable；
- rate limit；
- malformed response；
- auth、permission 或不可恢复 4xx。

身份/参数错误如果机械重试，只会放大延迟和流量。相反，短暂 overload 可以按 backoff 重试或切 fallback model。版本报告不能写一个没有分支证据的统一“重试 3 次”，因为不同路径的次数、delay、consent 和 provider fallback 不同。

### 关联一次逻辑请求

可靠诊断需要同时记录 client request ID、server request ID、query/turn、attempt、model、provider、stop reason 和 timing。这样可以区分：

- 用户的一轮 Agent 工作；
- 同一轮内部的多个 HTTP attempts；
- fallback 后不同 serving model；
- 子 Agent 自己的 retry；
- 工具运行期间的 progress。

详见 [遥测专题](telemetry.md)。

## 流式恢复：部分内容怎样处理

### content block 是恢复边界

流式 parser 维护 message/content block 生命周期。只有完整且可解析的 `tool_use` block 才进入 streaming tool executor。半截 JSON 不能执行，这个边界能减少“网络中断时执行一个参数不完整的写操作”。

文本和 thinking 可以逐步显示，但是否能在 fallback 后保留，需要看该分支的 salvage/supersedes 语义。不能因为 UI 已显示部分文本，就假定它已经成为下一轮稳定 transcript。

### Stream 转 non-stream

当 provider/连接不适合继续流式，而 non-streaming fallback 未被禁用时，客户端可以用非流方式重新请求。这个动作恢复的是传输，不是新的 Agent 计划；它不应自动增加正常 `turnCount`。

如果流失败前已经完成并启动一个 tool block，风险会显著提高：重新请求可能让模型再次生成同一动作。客户端会 abort/tombstone provisional 状态，但无法撤销已完成外部副作用。因此工具幂等和结果去重比“能 fallback”更重要。

## 模型 fallback：消息能丢，副作用不能丢

本版 Agent Loop 至少区分：

| fallback | 触发 | 客户端动作 | 风险 |
| --- | --- | --- | --- |
| 普通 model fallback chain | overload、server error、model unavailable 等 | tombstone 当前 provisional assistant/tool state，abort 未完成工具，换模型 | 已完成工具可能在新模型重试时重复 |
| refusal fallback | 模型拒绝，且策略/用户同意允许换模型 | 处理部分 refusal/text，再切换或结束 | 需要保留用户选择和拒绝原因 |
| server mid-stream serving fallback | 流中服务模型变化 | 按 allowlist/supersedes 处理 block 和模型身份 | usage、文本归属和模型权限需重新确认 |

### Tombstone 的准确含义

tombstone 告诉 message graph/UI：“这段 provisional 消息不再是有效主分支的一部分”。它可以避免失败模型输出继续污染下一轮，但不具备以下能力：

- 把写过的文件恢复到原内容；
- 撤销 Git commit/push；
- 取消已经完成的 HTTP/MCP 写请求；
- 收回已经发出的消息；
- 恢复外部数据库事务。

未完成工具可以通过 abort controller 尝试取消。已经完成的动作需要 file checkpoint、工具补偿 API、幂等键或人工回滚。

## 模型输出层的三条自修复路径

### `max_tokens` continuation

模型达到输出上限后，CLI 可以保留已经产生的 assistant 内容，加入隐藏 continuation 提示，要求直接从中断处继续，不道歉、不复述。它使用独立 recovery count，不把每次续写都当正常工具轮次；耗尽后才向上层返回失败/截断结果。

用户影响：长回答或长代码不一定在第一次 `max_tokens` 就结束，但多一次模型请求会增加延迟和输出 token。版本比较要记录 continuation 上限与拼接/去重语义。

### Malformed tool use

API 返回 `stop_reason=tool_use`，但客户端没有得到完整可执行 block 时，本版追加隐藏纠错消息并重试一次。第二次仍不一致才返回 `malformed_tool_use_exhausted`。

关键保障：第一次没有完整 block 就不执行工具，避免对半截参数产生副作用；纠错是有界的，避免模型永久重复错误协议。

### Thinking-only nudge

当响应以 end turn/stop sequence 结束且只有 thinking、没有用户可见文本，CLI 会补一次提示要求给出可见答案。第二次仍无可见文本则接受结束。这个分支改善 UI 完整性，但不应无限消耗 turn。

以上三条位于 Agent Loop 无工具结束判断中，见 `reverse/javascript/cli.readable.js` 272171-272264。

## Context 恢复：请求太长时先缩小问题

### Precompute 与 reactive compact

正常路径会在到达 blocked line 前预计算 compact；如果模型请求仍因 context/image 过长失败，Agent Loop 可以做一次 reactive compact 后重建请求。`hasAttemptedReactiveCompact` 防止同一轮无限压缩重试。

compact 恢复的是“下一次请求能装下并继续”。它不能保证摘要包含所有被删除细节，所以 summary prompt、preserved messages、tool discoveries 和 logical parent 是可靠性的组成部分。

### Auto-compact 关闭

本版 release delta 明确改进了 auto-compact 关闭且达到上限时的错误：提示用户到 `/config` 重新启用，而不是只报抽象 context error。这个变化看似微小，实际把失败从“不可操作”变成“有明确恢复动作”。

### Prompt cache 不是 context recovery

cache miss 增加输入写入成本和 prefill 延迟，但不直接释放窗口；compact/microcompaction 才改变活跃 token。恢复调查需要同时看 `cache_read_input_tokens` 与 context composition，不能把 cache miss 当作窗口溢出原因。

详见 [上下文治理与多层缓存](context-governance-and-caching.md)。

## 工具失败：把错误变成下一轮观察

工具错误一般不需要终止整个 Agent Loop。以下失败会转换为结构化 error `tool_result`：

- 工具不存在；
- JSON/schema/custom validation 失败；
- PreToolUse/permission deny；
- 用户取消；
- sandbox/command/path/network 错误；
- MCP auth/transport/server error；
- tool implementation exception；
- output schema/hook error。

结果保留原 `tool_use_id`，让模型知道哪一个动作失败、为什么失败，再决定缩小参数、换工具、请求用户批准或停止。

### Error result 与 retry 的边界

CLI 不应在不知道语义的情况下自动重跑任意工具。读操作通常更适合 retry；写操作需要幂等键或确认外部状态。模型看到 error 后重新发起同名工具，是新的 Agent 决策，不等于底层透明 retry。

## Hook 恢复：可编程控制也需要熔断

### Pre/Post hook 失败

hook timeout、非零 exit、非法 JSON 或 schema 不匹配需要明确处理：是阻止工具、附加错误、保留原 output，还是继续。2.1.235 对 PostToolUse 的非法 updated output 会保留原始结果并附 hook error，避免成功工具被坏 hook 破坏。

### Stop hook 重入与 cap

Stop/SubagentStop blocking 时：

1. 保存本轮 assistant output。
2. 把 hook feedback 加入 messages。
3. `stopHookActive=true`。
4. `stopHookBlockingCount + 1`。
5. `turnCount + 1` 并重新请求模型。

默认 `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=8`。达到用户 `maxTurns` 或 cap 后，客户端停止继续阻止并发 warning/terminal state。这个熔断保护错误 hook 不把 CLI 永久锁死。

## MCP 与动态工具恢复

MCP server 断开会让工具 call 失败或从可用表移除。恢复包含两步：

1. transport/auth/client 重新连接并重新列 capabilities/tools；
2. tool generation 变化触发 Tool Search/schema cache 失效和下一轮工具表刷新。

仅“socket reconnect 成功”不够。如果模型仍看到旧 schema，下一轮会继续产生无效 input。反过来，正在进行的 API request 也不会因 server 刚连上而热注入工具，刷新发生在下一请求边界。

证据见 `reverse/javascript/cli.readable.js` 491915-491964、231802-231817、272372-272382。

## Session resume：恢复逻辑历史，不复活旧进程

resume 从 transcript 重建 message graph、compact boundary 和当前 leaf。它能够恢复：

- user/assistant/tool result 文本与结构；
- fork/parent/logical parent；
- compact summary 与 preserved segment；
- 可持久化 session/task metadata；
- file checkpoint 引用仍有效时的 rewind 能力。

它不能自动恢复：

- 已退出进程中的连接、Promise、内存 cache 和 abort controller；
- 普通 shell 子进程；
- 未持久化的 background task；
- 已过期 provider prompt cache；
- MCP server 自己丢失的远端状态。

精确版本 probe 对不存在合法 UUID 返回 `No conversation found...` 和 exit 1，证明恢复前先要求本地 conversation 存在。完整机制见 [会话、检查点与 Memory](sessions-checkpoints-memory.md)。

## File rewind：有限的补偿恢复

文件 checkpoint 可以 dry-run 差异并恢复被跟踪内容，本版最多保留 100 个 checkpoint。它是模型 fallback/用户后悔后的重要补偿，但只覆盖客户端知道的文件写入面。

可靠工具还应提供：

- `--dry-run` 或 read-before-write；
- idempotency key；
- expected version/ETag；
- 原子写入或临时文件替换；
- 明确的 undo/compensation API；
- 写后 verify。

Agent Loop 的“验证结果”只有在工具返回了真实、可解释的状态时才有意义。

## Terminal reason 是恢复合同

Agent Loop 结束时需要把“为什么停止”交给 UI/SDK，而不是只有 success/error boolean。本版可观察 reason 包括：

- `completed`；
- `max_turns`；
- `background_requested`；
- `tool_deferred`；
- `hook_stopped`；
- `aborted_tools` / 用户取消类状态；
- reactive compact、malformed tool、API/model error 的耗尽状态；
- 动态 loop wakeup 等专用结束分支。

SDK 最终结果还会把 max turns 映射成 `error_max_turns`，并携带 `num_turns`、usage、cost、stop reason、terminal reason 和 permission denials。调用方可以据此决定展示、恢复、重排队或升级人工处理。

### 为什么不能只看 exit code

交互 CLI、print/SDK、background task 和 tool call 对“成功”的表达不同。某个工具失败后模型修正并最终完成，进程 exit 仍可为 0；达到 maxTurns 则需要 typed terminal reason。可靠自动化应解析结构化 output protocol，而不是只匹配 stderr 文本。

## 可观测性如何定位恢复层

| 现象 | 关键字段/事件 | 判断 |
| --- | --- | --- |
| 首 token 慢 | request start、TTFT、cache read/write | cache miss、provider latency 或请求装配 |
| 中途停顿 | stream stall/watchdog、last event time | 网络/流解析，不一定是工具 |
| 工具前卡住 | PreToolUse duration、permission duration | hook/审批/策略 |
| 工具后不继续 | PostToolBatch、queue absorption、maxTurns | batch hook 或终止条件 |
| 同动作疑似重复 | attempt/model fallback、tool ID、side-effect key | fallback 后模型重发 |
| compact 后质量下降 | pre/post token、messages summarized、preserved fields | summary 信息损失 |
| 子 Agent 长时间无结果 | agent API retry、heartbeat、task status | 子循环请求/工具/后台状态 |
| resume 后工具消失 | MCP generation、server status、Tool Search discover | 重连/刷新未完成 |

## 一个失败链案例

用户要求修改配置并运行部署：

1. 第一轮模型生成 Edit 和远端 Deploy tool。
2. Edit 通过 permission，写入本地文件并建立 checkpoint。
3. Deploy MCP tool 已向远端提交，但模型流随后断开。
4. 客户端 abort 剩余工具、tombstone provisional assistant，并切 fallback model。
5. fallback model 只看到整理后的稳定消息，若没有外部幂等状态，可能再次建议 Deploy。
6. file rewind 可以恢复 Edit 前的本地文件，却不能撤销第一次远端部署。
7. 正确恢复必须先查询远端 deployment ID/status，再决定继续、补偿或停止；不能盲目重试。

这个案例说明恢复设计的核心不是“让模型再试一次”，而是保持足够的动作身份、结果和外部状态，使下一次决策不会重复不可逆副作用。

## 跨版本必须比较什么

- retryable status/error 分类、backoff、attempt 上限和 provider 差异；
- stream watchdog/stall、non-stream fallback gate 和 partial salvage；
- model/refusal/server fallback 的 consent、allowlist、tombstone 与 usage 归属；
- 完整 tool block 的执行边界与 abort 行为；
- max_tokens、malformed tool、thinking-only 的 counter 和 exhaustion reason；
- reactive compact 次数、触发错误和消息保留；
- tool error 的结构、`tool_use_id` 配对和自动/模型重试边界；
- hook error fallback、Stop hook cap 与 maxTurns 交互；
- MCP reconnect、generation refresh、schema cache invalidation；
- transcript resume、file checkpoint/rewind 和 background durability；
- terminal reason、SDK subtype、exit status 和 telemetry correlation。

## 证据位置

- Agent Loop 恢复与终止：`reverse/javascript/cli.readable.js` 271550-272424。
- 无工具恢复分支：`reverse/javascript/cli.readable.js` 272171-272264。
- Stop hook cap：`reverse/javascript/cli.readable.js` 272253-272261。
- 工具批次、MCP refresh、queue、maxTurns：`reverse/javascript/cli.readable.js` 272293-272424。
- 单工具错误映射：`reverse/javascript/cli.readable.js` 316092-316487。
- resume 修链：`reverse/javascript/cli.readable.js` 323188-323443。
- file checkpoint/rewind：`reverse/javascript/cli.readable.js` 194602-194804。
- MCP refresh/cache invalidation：`reverse/javascript/cli.readable.js` 491915-491964、231802-231817。
- 事件、错误和诊断清单：[source inventory](source-inventory/summary.json)。

恢复机制的证据边界必须保持清楚：bundle 能证明客户端如何分类、重试、改写消息和发出结果；远端服务是否幂等、服务端内部路由和账户风控仍需要对应 API/服务证据。
