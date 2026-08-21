# Claude Code CLI 2.1.235 MCP、Agents 与后台协作：Claude Code 如何扩展一条主循环

Claude Code 的扩展能力不是“启动时读取一张工具列表”这么简单。MCP server 会连接、鉴权、断开和重新列工具；Tool Search 会把大目录中的 schema 延迟到需要时；子 Agent 拥有独立上下文和循环；后台任务、team mailbox 与 task claim 又把多个执行单元连接起来。理解这些机制，才能判断工具为什么突然不可用、子 Agent 为什么花费更多 token、并行为什么产生重复工作，以及 resume 后为什么需要重新发现能力。

## 总体拓扑

```text
                        +----------------------+
                        | Main Agent Loop      |
                        | messages/tools/state |
                        +----------+-----------+
                                   |
             +---------------------+---------------------+
             |                     |                     |
             v                     v                     v
      Built-in tools         MCP client set       Agent/Task tools
                               |                     |
                   +-----------+----------+          +------------------+
                   |                      |                             |
              MCP server A          MCP server B                 Subagent loop
              list/call/auth         list/call/auth          own messages/tools/
                   |                      |                   model/permissions
                   +----------+-----------+                             |
                              |                                         v
                      generation refresh                      result/message/task
                              |                                         |
                              +----------------+------------------------+
                                               v
                                    next main-loop iteration
```

主 Agent 并不共享子 Agent 的完整内部轨迹；它通常接收任务状态、progress 和最终压缩结果。MCP 工具也不是复制进二进制的内置函数；客户端持有 server connection/client 和当前工具定义，在 call 时跨 transport 调用外部实现。

## MCP 生命周期不是一次 `listTools`

### 配置来源

MCP 配置可能来自用户、项目、local、CLI/SDK、plugin、enterprise managed source。最终是否装载还受：

- workspace trust；
- `--strict-mcp-config`；
- `allowedMcpServers` 和 server policy；
- safe/bare mode；
- transport、command、URL 和 headers/helper 校验；
- OAuth/XAA/credential 状态；
- 当前平台和 feature gate。

项目声明了 server 不代表客户端一定连接。未信任 workspace 在执行 headers helper 前就会阻止，避免“为了读取配置”先运行项目提供的命令。

### 连接与能力发现

连接成功后，client 可以发现 tools、resources、prompts 和 server capabilities。工具定义至少包含名称、description、input schema 以及客户端包装的 permission/metadata。Claude Code 再把这些定义合并进本轮工具集合。

精确版本空配置探针：

```text
Command: $CLAUDE_TARGET mcp list
Input: 隔离 HOME，无 MCP 配置
Literal output: No MCP servers configured. Use `claude mcp add` to add a server.
Exit status: 0
```

这证明空 MCP 是正常状态，不会阻止主 CLI 工作。

### Generation 与刷新

MCP 工具表有 generation/refresh 语义。server 连接、断开、重连或工具列表变化时，旧定义不能永久留在 prompt 和执行 registry 中。本版动态列表刷新位于 `reverse/javascript/cli.readable.js` 491915-491964；Agent Loop 在工具批次结束、进入下一轮前还会检查刷新，见 272372-272382。

因此，一次 turn 内可能出现：

1. 模型请求时 server A 还未就绪，工具不在初始列表。
2. 模型执行其他工具期间 A 恢复连接。
3. 本批次收尾检测到 generation 变化。
4. 下一次模型请求得到更新后的工具集合。

无需重启进程，但已经发出的 API request 不会被中途改写；新工具只能影响后续模型轮次。

## Tool Search 管的是 schema residency

### 问题：工具越多，prompt 越重

每个工具的名称、description 和 JSON schema 都会消耗 context。几十上百个 MCP/plugin 工具全部常驻时，用户还没输入任务，模型已经要阅读大量低概率接口；这同时增加 token、prefill latency 和选错工具的概率。

### `defer_loading`

本版 Tool Search 会把候选工具标成 `defer_loading`。初始上下文保留可发现信息，而完整 schema 在模型搜索/选择后再加入。判断与 schema 说明位于 `reverse/javascript/cli.readable.js` 114258-114369、156521-156552。

这不是“缓存工具执行结果”，也不是“按需安装 MCP server”。它改变的是工具定义何时进入模型上下文：

```text
always-loaded tool: name + description + full schema -> first request
deferred tool:      discoverable name/index          -> first request
                    Tool Search hit                  -> full schema in later request
```

### Gate 与 fallback

Tool Search 受模型、provider、远端能力和工具规模等条件控制。旧 Vertex、部分不支持 Foundry/model 的路径会关闭并记录 reason。关闭时必须回到可工作的完整工具表，而不是让 deferred 工具既没有 schema 又不可发现。

### 缓存失效

已发现 schema 的缓存需要绑定当前工具 generation。MCP server 的 tool definition 变化后，旧 schema 若仍缓存，会产生两类错误：模型按旧字段调用；permission/validator 按新字段拒绝。2.1.235 的 Tool Search cache invalidation 位于 `reverse/javascript/cli.readable.js` 231802-231817。

## MCP 调用仍走统一工具管线

MCP tool 被发现后，不会绕过 Claude Code 的本地控制层。它仍需要：

- 名称和 schema 匹配；
- PreToolUse hook；
- MCP tool permission `allow|ask|blocked`；
- user/managed allow/deny rules；
- transport/auth 可用；
- output/error 转成标准 `tool_result`；
- PostToolUse/PostToolBatch；
- result size/context 清理。

区别在于真正副作用发生在 MCP server 或其下游系统。客户端 file checkpoint 通常无法自动回滚这类远端动作。

## 子 Agent 不是“换一段 system prompt”

### 独立运行对象

子 Agent 复用同一套核心 Agent Loop，但创建独立运行上下文，通常包括：

- 自己的 messages 与 context window；
- 自己的 model/effort/maxTurns；
- 过滤后的 tools 和 Agent definition；
- permission context 和 `bubble` 行为；
- abort controller；
- query/usage/telemetry 关联；
- 可选 worktree、cwd、transcript 和后台 task state。

本版 fork Agent 默认配置在 `reverse/javascript/cli.readable.js` 156505-156518：`maxTurns: 200`、`model: inherit`、`permissionMode: bubble`。

### 三个默认值的真实含义

| 默认 | 含义 | 不意味着什么 |
| --- | --- | --- |
| `maxTurns: 200` | 子循环有自己的较高轮次上限 | 一定会运行 200 轮，或没有 Stop/hook/abort 限制 |
| `model: inherit` | 未显式指定时继承父 Agent 模型选择 | 与父 Agent 共用同一次 API call/context |
| `permissionMode: bubble` | 子 Agent 无法自行解决的审批可上浮 | 自动允许所有子 Agent 动作 |

### 为什么独立 context 有价值

独立窗口让子 Agent 可以读取大量专题资料、运行自己的工具轨迹，再把高信号结果压缩回主线程。它减少主 context 被搜索噪声淹没，也降低不同探索方向的 path dependency。

代价同样明确：每个子 Agent 都有 system/tool/history token 和模型调用；结果还要回到主线程。公开多 Agent 文章指出 token usage、tool calls 和 model choice 是性能/成本的重要解释变量，并提醒强依赖的编码任务不一定适合大量并行。

## Agent definition 如何改变能力

一个 custom Agent definition 可以限定：

- 角色/系统指令；
- 允许的工具集合；
- 模型与 effort；
- maxTurns；
- permission mode；
- background/worktree 等执行方式；
- 输出预期和返回主 Agent 的格式。

如果当前会话不存在可作为通用默认的 Agent，而调用方又省略 `subagent_type`，2.1.235 会明确报错并列出可用 Agent。这是本版 release delta，避免把任务默默交给错误配置。

精确版本探针还证明命令面存在：

```text
Command: $CLAUDE_TARGET agents --json
Input: 隔离 HOME，无自定义 agent
Literal output: []
Exit status: 0
```

空数组表示命令成功但没有用户 Agent，不表示客户端不支持内置/条件 Agent 路径。

## 主 Agent 如何接收子 Agent 状态

子 Agent 状态构造与消息队列位于 `reverse/javascript/cli.readable.js` 306930、307605-307608 附近。上游可以看到：

- task/agent ID；
- running/completed/failed 等状态；
- progress 或 tool heartbeat；
- API retry 进度；
- 最终 result/error；
- parent tool use ID，用于把子 Agent 当作主 Agent 的一个工具调用配对。

这层包装很重要。没有 parent tool use 关联，主线程会把子 Agent 的异步输出当成无来源消息；没有 terminal state，Agent Loop 也不知道何时可以 drain 本批工具。

## Background Agent 与普通并发工具的差别

普通 concurrency-safe 工具仍属于当前模型轮次，批次结束前 executor 会 drain。Background Agent/Task 则可能跨越当前前台 turn，需要 task registry 保存句柄或 durable metadata，并通过 progress、notification 或后续读取返回状态。

主要差异：

| 维度 | 同轮并发工具 | Background Agent/Task |
| --- | --- | --- |
| 生命周期 | 当前 tool batch | 可跨前台 turn/会话阶段 |
| 收尾 | `getRemainingResults()` drain | task registry、stop/attach/notification |
| 上下文 | 当前主 Agent 或短工具调用 | 独立 Agent context |
| 用户中断 | abort 当前 turn | 可能选择只取消前台、停止任务或 handoff |
| resume | tool result 已写入即可读取 | 只有持久化任务元数据才能重连 |

恢复 transcript 不会凭空复活只存在旧进程内存中的后台 Promise。版本报告必须区分 durable background task 与普通进程内 task。

当前官方 [Enterprise network configuration](https://code.claude.com/docs/en/network-config) 进一步说明：background agents 不运行在派发它们的 terminal 内，而由按需启动、可超过 shell 生命周期的 per-user supervisor 承载。仅在某个 shell 里 export proxy、CA 或 mTLS 变量，会导致“哪个 shell 首次启动 supervisor”决定配置是否继承；user/managed settings 的 `env` 才是所有 background session 都能稳定读取的配置入口。该主张登记为 `public.background-network-settings`。

这是当前文档对 supervisor ownership 的说明，不等于本快照已完成 supervisor 重启/reattach Probe。2.1.235 对 background/task 的客户端分支可以静态定位，但跨进程 durability 仍需另建长生命周期运行场景后才能写成 Probe。

## Task registry 与 claim

Agent team 需要共享任务状态，但不能让多个 teammate 同时无条件执行同一任务。`2.1.235` 的 task claim 路径位于 `reverse/javascript/cli.readable.js` 202474-202511，核心语义是：

1. 读取/定位 task。
2. 检查当前状态和依赖。
3. 由一个 Agent 声明领取。
4. 更新 owner/status。
5. 失败或状态冲突时返回可见结果，而不是双方都假设成功。

claim 解决的是归属竞争，不自动解决文件写冲突。两个不同 task 仍可能修改同一文件，因此 worktree 隔离、任务边界和主 Agent 合并策略仍然必要。

## Team mailbox 与消息语义

team mailbox 实现在 `reverse/javascript/cli.readable.js` 279171-279317。它支持面向 teammate/leader 的消息、广播、shutdown/request/response 等协作状态。SendMessage 的价值不只是聊天：它让 Agent 能传递发现、阻塞、计划审批和任务状态。

消息系统需要处理：

- sender/recipient/team/session 身份；
- 投递、读取和 ack；
- size budget；
- 不存在/已关闭 teammate；
- broadcast 与单播；
- resume 后未 drain 事件是否重投；
- 过多更新对主 context 和 UI 的压力。

2.1.235 release notes 特别修复了跨会话 SendMessage 大小检查：发送前超限会返回可见错误，不再静默丢弃。这个小修复实际改变了分布式协作的可靠性，因为“发送成功但对方没收到”会让任务状态分叉。

## Notifications 与队列吸收

后台 webhook、scheduled trigger 或 Agent message 可以先进入队列，再提示模型调用读取工具。机器 schema 说明中明确：只有 drain 后才 ack；未 drain 事件在 resume 时可以重新投递。

主 Agent Loop 在工具批次后还会吸收用户 command/poll events，转换成 attachment，再进入下一次 API request。外部事件因此遵守“只在请求边界改变模型上下文”的原则，不会篡改正在流式传输的请求。

## 精确二进制：MCP refresh 不是立即热替换

[mcp-refresh.json](runtime-probes/mcp-refresh.json) 启动一个隔离 stdio MCP server。初始 `tools/list` 只有 `probe_echo`；第一次 `tools/call` 后 server 发出 `notifications/tools/list_changed`，并在下一次 `tools/list` 增加 `probe_new`。2.1.235 的实测时序是：

```text
Messages #1: tools 含 probe_echo
  -> tools/call #1
  -> MCP 发 tools/list_changed
  -> CLI 再次 tools/list，已看到 probe_new
Messages #2: 仍未包含 probe_new
  -> tools/call #2
Messages #3: tools 开始包含 probe_new
  -> 最终 MCP_REFRESH_OK
```

因此 `tools/list_changed` 会失效并刷新工具表，但在这条路径中存在一个 request-assembly 延迟。已经组装或正在发送的请求不会被热改写；“MCP server 已报告新工具”与“模型本轮已经拿到新 schema”不是同一时刻。排障时要记录 generation、`tools/list` 完成时刻和具体 Messages request 的 tool names，不能只看 connection status。

## 精确二进制：子 Agent 是异步任务通知，不是同步函数返回

[subagent-loop.json](runtime-probes/subagent-loop.json) 证明父 Agent 首先收到 `async_launched` 的配对 tool result，子 Agent 完成后再通过 task notification 入队。子请求不含父 prompt，拥有自己的工具表；父循环消费通知后才得到子结果。这个差异直接影响编排器：启动 ACK 只能用于登记 task/agent ID，不能作为 findings；最终结论必须等 completed notification 或显式查询任务输出。

## Worktree 隔离解决什么

子 Agent 使用独立 Git worktree 时，可以减少：

- 同一路径并发写；
- 一个 Agent 的未提交改动污染另一个 Agent 观察；
- 测试/构建互相覆盖；
- 主会话难以辨认改动来源。

它不解决：

- 两个分支修改同一逻辑导致 merge conflict；
- 共享数据库、端口、缓存目录或远端环境冲突；
- Agent 任务描述重叠；
- 合并后整体测试失败。

因此 worktree 是文件隔离，不是完整资源隔离。

## 一次多 Agent 任务如何流动

以“并行研究 API、UI、测试并由主 Agent 汇总”为例：

1. 主 Agent 把目标拆成互斥子任务，定义输出格式和证据标准。
2. 每个子 Agent 建立独立 messages、tools、model/permission context。
3. task registry 记录 owner/running 状态；必要时每个 Agent 获得 worktree。
4. 子 Agent 在自己的 Agent Loop 中调用 Read/Search/Bash/MCP。
5. permission `bubble` 把无法自动决策的动作送回主会话审批。
6. progress 通过 parent tool use/task ID 回到主 UI，但不把全部轨迹复制进主 prompt。
7. 子 Agent 完成后返回压缩的 findings、证据路径、测试结果和未解决项。
8. 主 Agent 合并结论，必要时发送 follow-up 或重新分配 task。
9. task 状态完成后，主 Agent 才进行跨专题验证和最终回答。

如果第 1 步只写“你去看看”，多个 Agent 很容易重复搜索或留下缝隙。公开多 Agent 文章也强调 objective、output format、tools/sources 和 task boundaries 必须明确。

## 故障定位

### MCP server 显示 connected，但模型不会用工具

检查 tool list generation、Tool Search 是否 defer、工具是否已 discover、model/provider 是否支持该模式、description/schema 是否清晰，以及 permission 是否 blocked。连接成功只证明 transport，不证明 schema 已进入本轮 prompt。

### MCP 重连后仍按旧 schema 调用

检查 generation 是否变化、Tool Search cache 是否失效、下一轮请求是否真正重建 tools。当前已发出的请求不会热替换 schema。

### 子 Agent 一直等权限

检查 `permissionMode: bubble`、主会话是否有可处理 prompt 的 UI/SDK host、`dontAsk` 是否让未预授权动作直接失败，以及 managed rule 是否禁止父级批准。

### 多 Agent 花费暴涨但结果重复

检查任务是否真正可并行、每个子任务是否有边界和停止条件、是否复制了完整历史、是否使用过多工具调用，以及返回主 Agent 的结果是否经过压缩。

### Resume 后后台任务消失

区分 durable task metadata 与旧进程内句柄。transcript 能恢复“曾启动任务”的事件，不保证重建外部执行实体；需要 task/service 自身提供查询和 reattach。

## 跨版本必须比较什么

- MCP config sources、trust/strict/managed gates；
- transport、auth、XAA、server status 和错误语义；
- tool list generation、refresh 时机和 Agent Loop 换表位置；
- Tool Search enable/disable reason、`defer_loading`、cache invalidation；
- MCP tool permission 和统一工具管线是否改变；
- Agent definition 字段和默认 `maxTurns/model/permissionMode`；
- 子 Agent context/tools/transcript/worktree/abort 隔离；
- parent tool use、progress、retry 和 terminal result 映射；
- background task 的 durable/ephemeral 状态；
- task claim 原子性、依赖和 owner/status；
- mailbox message type、大小、ack、redelivery 和 shutdown；
- release notes 中 Agents/Cloud/Remote 修复的可达实现。

## 证据位置

- Tool Search gates：`reverse/javascript/cli.readable.js` 114258-114369。
- deferred tool 判断和 schema：`reverse/javascript/cli.readable.js` 156521-156552。
- Tool Search cache invalidation：`reverse/javascript/cli.readable.js` 231802-231817。
- MCP 动态列表刷新：`reverse/javascript/cli.readable.js` 491915-491964。
- Agent Loop 中途刷新 MCP tools：`reverse/javascript/cli.readable.js` 272372-272382。
- fork Agent 默认：`reverse/javascript/cli.readable.js` 156505-156518。
- 子 Agent 状态和消息队列：`reverse/javascript/cli.readable.js` 306930、307605-307608 附近。
- task claim：`reverse/javascript/cli.readable.js` 202474-202511。
- team mailbox：`reverse/javascript/cli.readable.js` 279171-279317。

结构化运行主张：`probe.mcp-generation-refresh`、`probe.mcp-refresh-delay`、`probe.subagent-isolation`、`probe.subagent-notification-feedback`。公开主张：`public.mcp-roots-change`、`public.multiagent-context`、`public.agent-teams-coordination`、`public.multiagent-compression`、`public.background-network-settings`。完整命令、请求序列、literal output 和 exit status 见 [精确二进制运行证据指南](runtime-probe-index.md)。

这些证据证明客户端已经携带对应控制与协作路径。实际 MCP server 行为、远端 team 服务、feature flag 和组织权限仍需按目标环境另做运行验证。
