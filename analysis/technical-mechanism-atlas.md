# Claude Code CLI 2.1.235 技术机制总图

Claude Code 不是“终端里包了一层模型 API”。一个用户请求会同时穿过请求装配、Agent Loop、工具执行、权限与 hook、上下文治理、会话持久化、MCP/子 Agent 协作、错误恢复和遥测九条主链；工具对象还要经过宿主与运行时 gate 才能进入请求。Plan Mode、Structured Output、REPL、Brief、EndConversation、Remote/Runner/Notifications、Connector/Catalog/MCP 和 ClaudeDesign/Projects 又各自拥有独立状态机；登录、workspace trust、Thinking/Fast、usage limit、数据导入、sandbox、网络证书、Active Goal、后台模型任务、Advisor 和 Ultrareview也会按条件启动。

本页是阅读路由，不替代各专题。它把公开设计原则、`2.1.235` bundle 静态证据和精确版本运行探针放在同一张生命周期图里。

## 60 秒建立全局模型

**读者问题：** 用户只输入一句“读取配置、修改端口并运行测试”，为什么 CLI 内部会同时出现模型请求、工具调用、权限判断、上下文压缩、会话文件和遥测事件？

**一句话模型：** Claude Code 用 Agent Loop 反复决策，用上下文治理控制模型看到什么，用工具控制管线决定动作能否发生，再把可恢复历史和不可自动回滚的外部状态分开管理。

![一次 Claude Code 任务在上下文、Agent Loop、工具控制、外部状态和恢复状态之间循环](visuals/system-lifecycle.svg)

贯穿本仓库的场景是：Claude 读取项目配置，把端口从 `8080` 改成 `9090`，运行测试，收到失败结果后再次修改。这个任务至少经历两次模型决策、多个工具调用和一次结果回灌；用户中途输入、权限拒绝、窗口不足或网络失败都会改变下一步，却不会把已经完成的外部动作自动抹掉。

| 对象 | 任务开始前 | 运行时转换 | 任务结束后 | 用户看到什么 |
| --- | --- | --- | --- | --- |
| 模型消息视图 | 当前历史、system prompt、工具目录 | 装配、缓存、清理或 compact | 可继续推理的有效上下文 | 回答是否连贯、token 是否增长 |
| Agent Loop 状态 | `turnCount=1`、无本轮工具结果 | 请求模型、执行工具、吸收队列、判断终止 | 下一轮状态或 terminal reason | 连续执行还是提前停止 |
| 外部状态 | 原配置和测试状态 | Edit/Bash/MCP 等工具改变真实世界 | 文件、进程或远端系统已变化 | 修改是否真实发生 |
| 可恢复状态 | 旧 transcript/checkpoint | 追加消息、boundary、文件快照 | resume/rewind 可用的投影 | 重启后能恢复到什么程度 |

先记住一个边界：消息、摘要和 tombstone 属于“模型以后看到什么”；文件、进程、远端写入属于“世界已经发生什么”。前者可以重建，后者只有工具自身的幂等、检查点或补偿机制才能处理。

## 先看完整请求生命周期

```text
用户输入 / SDK message / queue message
                  |
                  v
        [1. 会话与消息图]
        选择 session、恢复 parent 链、装载 transcript
                  |
                  v
        [2. 上下文治理]
        system/user/tool schema 分层、cache breakpoint、
        tool-result cleanup、compact、memory 注入
                  |
                  v
        [3. Agent Loop]
        建立本轮状态 -> 请求模型 -> 解析流 -> 判断下一状态
                  |
          assistant content stream
                  |
                  v
        [4. 工具调度器]
        tool_use block 一完成即可排队；并发安全工具重叠，
        非并发安全工具形成顺序屏障
                  |
                  v
        [5. 工具控制管线]
        查找 -> JSON/schema -> validate -> PreToolUse ->
        permission/policy -> call -> PostToolUse -> output schema
                  |
                  v
        [6. 结果回灌与继续条件]
        tool_result 配对、用户队列吸收、Stop hook、maxTurns
                  |
          +-------+-------+
          |               |
       再请求模型       terminal reason
          |               |
          +-----> [7. 持久化/检查点]
                  transcript、file checkpoint、compact boundary
                           |
                           v
                [8. MCP / Agent / Team]
                动态工具刷新、子上下文、任务领取、mailbox

所有阶段同时写入 [9. 可观测性]
query/turn/tool/context/cache/retry/error/permission timing 与事件
```

这九层不是串行微服务。它们共享一个本地进程和若干显式状态对象：Agent Loop 在模型流未结束时已经能驱动工具；工具完成后可能触发 hook、消息队列和 MCP 刷新；compact 会重写下一轮发送给模型的消息视图，但 transcript 仍保留逻辑历史；fallback 可以丢弃失败模型产生的消息，却不能撤销已经发生的外部副作用。

`2.1.235` 还有四个不能塞进单一方框的专用运行时。Auto Mode 横跨 permission 和模型请求，但只处理确定性前置规则仍未裁决的动作；Plugin Eval 在主产品之外启动受限 child Agent Loop，用 ablation 和 grader 判断插件增益；Runtime Supervision 把 daemon、PTY、worker、rendezvous 和 Storage 投影拆成不同 owner；Enterprise Gateway 则是独立 Bun server，拥有 OIDC/session、managed policy、operator credential、spend/Postgres 和 OTLP fanout。另有多条经常被清单掩盖的横向合同：29 项人工维护的核心终端参考不等于 bundle 的 80 个同工厂 AST 注册调用点，更不等于一次请求的实际工具集合；普通 assistant text 存在不等于 Brief 主视图已经收到；Connector suggestion 不等于安装；MCP refresh 不等于新工具已进入当前 request；EndConversation 的 prompt 规则不等于客户端做过语义判案。对应入口见 [工具注册与宿主表面](tool-registration-and-host-surfaces.md)、[Brief 用户可见输出](brief-mode-and-user-visible-output.md)、[Connector/Catalog/MCP](connectors-catalog-and-mcp-operators.md) 和 [EndConversation 风控](end-conversation-risk-control.md)。

## 三条必须同时理解的闭环

### 1. 推理执行闭环

```text
模型观察当前上下文
  -> 生成文本或 tool_use
  -> CLI 执行工具
  -> tool_result 回到消息图
  -> 模型观察新状态
  -> 继续或结束
```

这是通常所说的 Agent Loop。它解决的不是“多调几次 API”，而是让非确定性的模型通过确定性工具观察和改变外部世界，并在每一步之后重新决策。循环必须保存工具调用与结果的 ID 配对、轮次计数、停止原因、用户中途输入和恢复状态，否则模型会看到一段无法解释的历史。

详见 [Agent Loop 专题](agent-loop.md)。

### 2. 上下文控制闭环

```text
会话和工具产生更多 token
  -> 估算窗口、缓存和可清理内容
  -> defer tool schema / microcompact old tool results
  -> warning / precompute compact / reactive compact
  -> 建立更短但可继续工作的消息视图
  -> 后续轮次再次增长
```

它解决“历史越长越贵、越慢、越难聚焦”的问题。Claude Code 的治理对象不只是聊天消息，还包括 system prompt、机器动态信息、工具 schema、MCP 目录、thinking、tool results、compact summary 和 memory。缓存降低重复前缀的计费与延迟，压缩降低窗口占用，两者不是同一个机制。

详见 [上下文治理与多层缓存](context-governance-and-caching.md)。

### 3. 控制与恢复闭环

```text
执行动作前做 schema/hook/permission/sandbox 决策
  -> 执行后做 output validation/PostToolUse/持久化
  -> 失败时按错误层级 retry/fallback/compact/abort
  -> 保存 terminal reason、checkpoint 和诊断证据
  -> resume/rewind/下一轮从可解释状态继续
```

它解决“能执行”不等于“可控、可恢复”。权限提示只是其中一层；managed settings、工具级规则、hook、sandbox、工作目录边界、网络限制、凭据门控、最大轮数和 Stop hook 熔断共同决定动作是否继续。

详见 [工具、权限与 Hooks](tools-permissions-hooks.md) 和 [韧性与恢复](resilience-and-recovery.md)。

## 九个机制分别管什么

| 机制 | 核心对象 | 关键状态变化 | 主要失败表现 | 用户直接感受 |
| --- | --- | --- | --- | --- |
| 会话与消息图 | message UUID、parent、session、transcript | append、fork、compact boundary、resume 修链 | resume 找不到、parent 断裂、恢复到错误分支 | 历史是否连续、是否能 fork/继续 |
| 上下文治理 | system/user/tool blocks、token budget | cache 标记、defer、cleanup、compact | cache miss、窗口阻塞、摘要丢细节 | 首 token、费用、长任务稳定性 |
| Agent Loop | messages、toolUseContext、turnCount、transition | model -> tool -> result -> next/terminal | 无限重入、错误计轮、终止原因丢失 | 能否自主完成多步骤任务 |
| 工具调度 | tool_use block、并发队列、屏障 | enqueue、overlap、barrier、abort | 顺序错乱、重复动作、工具悬挂 | 修改与测试是否按正确顺序发生 |
| 权限与 hook | tool input、decision、updatedInput、policy | allow/deny/ask/defer/modify/block | 误授权、重复弹窗、hook 永久阻止 | 是否可预测地批准本地动作 |
| MCP 与 Agent | tool registry、server generation、agent context | discover、invalidate、refresh、spawn、message | 工具目录过期、子 Agent 无结果 | 扩展能否即插即用、并行是否有效 |
| 持久化与检查点 | JSONL、file snapshots、compact metadata | write、rewind、restore、prune | 文件能回退但外部动作不能回退 | checkpoint 是否真的救得回来 |
| 韧性与恢复 | attempt、fallback、abort、tombstone | retry、switch model、reactive compact、terminal | 副作用已发生却再次执行 | 出错后是否继续、是否需要人工确认 |
| 遥测与诊断 | query/turn/tool correlation、timing、event | queue、sample、batch、export、persist | 看见“慢”但分不清慢在哪 | 能否定位模型、权限、工具或 compact |

### 十九个按条件启动的专用运行时

九条主链解释每次请求的共同骨架，下面这些机制只有在对应命令、设置、账号能力或环境出现时启动，但它们拥有独立状态、失败和副作用，不能被压扁成一个 feature flag：

| 专用机制 | 触发入口 | 真正拥有的状态 | 最容易误判的地方 |
| --- | --- | --- | --- |
| Brief/user-visible output | `--brief`、`CLAUDE_CODE_BRIEF`、`defaultView=chat`、`/brief` | `isBriefOnly`、`SendUserMessage` tool result、附件 lane、renderer projection、单次 sentinel | 普通文字进 transcript 不等于主视图已交付；附件 error 不一定表示消息正文失败 |
| Plan Mode/human approval | `EnterPlanMode`、启动 mode、team/Ultraplan | `mode/prePlanMode`、plan attachment/file、question/approval request | reminder 不是唯一约束；澄清答案不等于实施批准；批准后才恢复实施 mode |
| Structured Output | `--json-schema`、SDK initialize schema | AJV validator、strict schema、专用工具、attachment、attempt counter | 类型/形状正确不等于业务事实正确；被 tombstone 的对象不能进入终态 |
| REPL programmatic runtime | `REPL` tool、动态注册工具 | persistent VM、inner tool pairs、timer/watchdog、replay log | 外层 allow 不绕过内层 permission；resume 重放结果，不重做副作用 |
| EndConversation | 合格主会话中的两次同名 tool call | reflection state、history boundary、ended marker、abort/terminal state | 辱骂/警告/自伤规则主要在 prompt；硬代码不重新理解语义 |
| Remote routines/runner/notifications | `RemoteTrigger`、operator tools、queued notification | routine/run cursor、runner process/assignment、pending/drained/nudge | 控制面快照不等于远端执行成功；通知正文是外部数据且队列有背压 |
| Connector/catalog/MCP operators | Connector/Plugin/Skill/MCP tools | registry/catalog、OAuth scope、live client generation、resource cache | suggestion 不安装；connected 不等于 enabledInChat；refresh 不改已发 request |
| ClaudeDesign/Projects | 动态 Design MCP、attached Project tool | MCP session/catalog、consent/plan/grant、Project docs/budget | DesignSync 不是同一机制；RAG 403 fallback 只给目录；远端写不自动回滚 |
| Auth/account/subscription | `auth login/status/logout`、`/login`、setup-token | credential、account/org/subscription、派生 cache generation | 拿到 token 不等于账号换代完成；本地 logout 不证明远端 revoke 成功 |
| Onboarding/workspace trust | 首次启动、项目扫描、safe/bare/print | onboarding state、persisted/session trust、项目能力 registry | 扫到配置不等于已执行；接受 trust 后还必须重新发现 |
| Thinking/Effort/Fast | settings、slash command、request attempt | thinking shape、effort、service tier、cooldown latch | UI opt-in 不等于最终请求一定携带该字段或服务端一定采用 |
| Usage/cost/credits/limits | API usage、quota header/API、`/usage` | modelUsage、cost、limit windows、auto-resume timer | 美元成本与账号额度不是同一个数；reset 不会重放旧工具 |
| Project purge/import | CLI command、preview/confirm、archive manifest | purge/import plan、digest、文件写入进度 | digest 防输入漂移，不提供跨文件事务或自动 rollback |
| Sandbox install/runtime | Windows install/status、每条命令 wrapper | host install state、session initializer、command result | `installed:true` 和 CLI exit 0 都不能证明动作成功且被隔离 |
| Proxy/CA/mTLS | transport 初始化、407、cert reload、CCR relay | adapter、proxy auth cache、CA store、client identity | 主请求成功不代表 MCP/AWS/WebSocket/OTLP 同样成功 |
| Active Goal | `/goal`、Agent Loop Stop point | session goal、Stop prompt hook、blocking counter | 模型声称完成不等于 runtime 允许结束；清目标不回滚副作用 |
| Background model tasks | turn/session events、idle scheduler、feedback tool | recap/summary/suggestion/draft、Auto Dream lock 与 memory | `skipTranscript` 不等于不发上下文；只有 Auto Dream 改持久 memory |
| Advisor | request-time eligibility、server tool | advisor model selection、server-tool blocks、strip retry | 不是第二个本地 Agent；咨询发生在服务端且增加 token/延迟 |
| Ultrareview | `/ultrareview`、CLI cloud review | Git scope、cloud task/event、findings、fix/post consent | 云端 review 不直接改本地；post 只允许一条普通 PR comment |

## 状态不是都存在同一个地方

### 进程内状态

- 当前 Agent Loop 的 `messages`、`toolUseContext`、`turnCount` 和 recovery counters。
- streaming tool executor 的待执行队列、并发任务和屏障。
- MCP server/tool generation、工具 schema cache、模型配置 cache。
- permission prompt、hook 执行、abort controller 和后台任务句柄。

进程退出后，这些对象本身消失。可恢复性依赖它们是否已经被投影到 transcript、checkpoint、settings 或外部任务状态中。

### 会话持久状态

- JSONL transcript 中的消息、system event、compact boundary 和 tool result。
- session ID、message UUID、parent UUID、logical parent 和 fork 信息。
- file checkpoint 元数据与可恢复文件内容。
- project/user memory 和 session metadata。

它们让 `--resume`、fork 和 rewind 有基础，但不会自动保存任何外部系统的事务状态。

### 外部状态

- 文件系统、Git、shell 子进程、远端 API、数据库和 MCP server 自身状态。
- 子 Agent 所在 worktree、后台任务、team mailbox 和任务列表。
- 服务端账户、模型配额、远程 feature/config 和组织策略。

这类状态不受“删掉一条 assistant message”支配。CLI 可以 abort 仍在运行的工具、tombstone 失败分支、恢复本地文件 checkpoint，但不能普遍撤销已经推送的 Git commit、已经发送的消息或已经完成的远端写操作。

## 一次真实任务为什么会跨越所有层

以“读取配置、修改端口、运行测试，并在失败时修复”为例：

1. 会话层把用户消息写进当前 message graph，并确定它接在哪个 parent 后面。
2. 上下文层装配 system prompt、memory、历史、工具 schema；若窗口接近阈值，先清理旧工具结果或 compact。
3. Agent Loop 发起第一次模型请求，流式接收 Read、Edit、Bash 三个 `tool_use`。
4. Read block 完成即可开始；Edit 形成写屏障；Bash 不能越过 Edit 提前测试旧文件。
5. 每个工具都独立经过 schema、PreToolUse、权限和 sandbox；hook 还可以修改 input，修改后必须重新校验。
6. 工具结果用原 `tool_use_id` 回灌。测试失败不是循环失败，而是一个可供模型判断的新观察。
7. 用户在测试期间输入“端口改成 9090”，消息进入 queue，在下一次 API call 前被吸收，而不是改写已经发出的请求。
8. 第二轮模型看到修改结果、测试错误和追加指令，再决定继续 Edit/Bash 或结束。
9. transcript 保存逻辑过程，file checkpoint 保存可支持 rewind 的文件状态；若发生模型 fallback，失败分支消息可被 tombstone，但已完成的文件写入仍需显式恢复。
10. query、turn、tool、permission、hook、compact 和 retry timing 让诊断者判断时间花在模型、等待审批、工具还是压缩上。

这才是“Agent 能执行多步骤任务”的技术含义：不是模型一次性规划得完美，而是运行时让它反复获得经过约束的新事实，同时保证状态仍可配对、可停止、可诊断。

## 公开原理与本版本实现怎么对应

Anthropic 官方文档把 Agent Loop 描述为“收集上下文、采取行动、验证结果、重复”；工程文章强调 context 是有限资源，工具是确定性系统与非确定性 Agent 之间的契约，多 Agent 通过独立上下文并行探索。它们解释了设计动机，但不自动证明某个版本的 CLI 有某个字段、阈值或调用顺序。

本仓库采用三类正向证据和一类明确边界：

| 层级 | 能回答什么 | 不能回答什么 |
| --- | --- | --- |
| 官方公开主张 | 产品设计意图、概念模型、当前文档行为 | `2.1.235` 是否已包含后来新增的实现 |
| `2.1.235` bundle 静态证据 | 客户端分支、默认值、阈值、状态字段、调用链 | 服务端未下发的值、真实账户策略、未走到的分支结果 |
| `2.1.235` 隔离运行探针 | 精确二进制对给定输入的实际输出和 exit status | 未触发路径、远端依赖、所有平台和账户差异 |
| Boundary | 说明为什么发布物、当前探针或公开资料不足以证明 | 不用“可能支持”填补缺失证据 |

逐项映射见 [公开主张与 2.1.235 验证矩阵](public-claims-validation.md)。30 条 Probe 的命令、输入、literal output、exit status、状态变化和窄边界见 [精确二进制运行证据指南](runtime-probe-index.md)。

## 按问题选择阅读入口

| 你想回答的问题 | 先读 | 再读 |
| --- | --- | --- |
| 当前58个能力面哪些是Deep、哪些仍是Documented或外部Boundary | [全面性审计](completeness-audit.md) | [全量能力面](source-surface.md) |
| 用户一句话怎样与system、CLAUDE.md/Memory、attachment、IDE/Hook/MCP、文件变化和tools组成最终request | [Prompt Assembly](prompt-assembly-and-system-reminders.md) | [上下文治理与多层缓存](context-governance-and-caching.md) |
| 代码、prompt、transcript、telemetry、Feedback、Remote、Web/MCP/Hook、Artifact/upload和Voice分别去了哪里 | [全局数据流与隐私](client-data-flow-and-privacy.md) | [遥测、日志与诊断](telemetry.md) |
| 为什么核心参考只有 29 项，bundle 却定义了 80 个 `Yi({...})` 注册调用点 | [工具注册与宿主表面](tool-registration-and-host-surfaces.md) | [核心终端工具逐项参考](builtin-tools-reference.md) |
| 29 项核心终端参考工具分别改变什么状态、怎样失败和恢复 | [核心终端工具逐项参考](builtin-tools-reference.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| Brief 模式为什么普通文字存在但主视图仍空，附件为何只在桌面可见 | [Brief 用户可见输出](brief-mode-and-user-visible-output.md) | [Agent Loop](agent-loop.md) |
| Plan Mode 为什么能读文件却不能实施，批准后怎样恢复权限 | [Plan Mode 与人工审批](plan-mode-and-human-approval.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| `--json-schema` 为什么通过工具调用收尾，fallback 后对象为何会消失 | [Structured Output 与 Schema 合同](structured-output-and-schema-contract.md) | [CLI、SDK 与输出协议](cli-sdk-output-protocol.md) |
| REPL 为什么能持久变量和动态工具，又不会在 resume 时重做旧副作用 | [REPL 程序化工具运行时](repl-programmatic-tool-runtime.md) | [Agent Loop](agent-loop.md) |
| EndConversation 哪些规则是客户端硬门控，哪些只是 prompt 约束 | [EndConversation 风控](end-conversation-risk-control.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| Remote routine、runner 与通知队列分别由谁持有和确认 | [Remote Routines、Runner 与 Notifications](remote-routines-runner-and-notifications.md) | [后台、Channels 与 Cloud](cloud-background-channels.md) |
| Connector suggestion、账号 catalog、MCP refresh/wait/resource 各改变什么状态 | [Connector/Catalog/MCP Operators](connectors-catalog-and-mcp-operators.md) | [MCP、Agents 与后台协作](mcp-agents-background.md) |
| ClaudeDesign 的 operation catalog、授权和 Projects 文件/RAG 怎样串起来 | [ClaudeDesign 与 Projects](claude-design-and-projects.md) | [Workflow、Artifact 与 Design](workflow-artifact-design.md) |
| 156 个根 settings 字段从哪里来、怎样 merge、由谁消费 | [Settings 全字段参考](settings-reference.md) | [Settings、Flags 与 Policy](settings-feature-flags-policy.md) |
| CLI/SDK 的 stream-json、control RPC、event 和终态怎样配对 | [CLI、SDK 与输出协议](cli-sdk-output-protocol.md) | [Agent Loop](agent-loop.md) |
| Plugin、Skill、slash command 和 LSP 为什么安装后仍可能不可见 | [Plugins、Skills、Commands 与 LSP](plugins-skills-commands-lsp.md) | [MCP、Agents 与后台协作](mcp-agents-background.md) |
| 为什么 Claude 会连续调用多个工具 | [Agent Loop](agent-loop.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| 为什么长会话越来越贵或突然 compact | [上下文治理与多层缓存](context-governance-and-caching.md) | [会话、检查点与 Memory](sessions-checkpoints-memory.md) |
| permission、hook、sandbox 谁先决定 | [工具、权限与 Hooks](tools-permissions-hooks.md) | [风控能力面](risk-control-surface.txt) |
| Auto Mode 为什么有时直接允许、有时询问、有时 unavailable 后拒绝 | [Auto Mode 分类器](auto-mode-classifier.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| Plugin Eval 的高分是否来自插件，Delta 何时不可比较 | [Plugin Evaluation Harness](plugin-evaluation-harness.md) | [Plugins、Skills、Commands 与 LSP](plugins-skills-commands-lsp.md) |
| 终端退出后后台 Agent 谁持有，attach 与 respawn 为什么分离 | [Runtime Supervision](runtime-supervision-and-processes.md) | [后台、Channels 与 Cloud](cloud-background-channels.md) |
| Enterprise Gateway 怎样串联身份、策略、路由、花费和遥测 | [Enterprise Gateway Runtime](enterprise-gateway-runtime.md) | [模型、认证与请求装配](models-auth-providers-request.md) |
| 登录后为什么还要刷新组织、feature 和 Remote Control | [Auth、账号与订阅](auth-account-and-subscription-lifecycle.md) | [模型、认证与请求装配](models-auth-providers-request.md) |
| 不可信仓库何时才允许加载 hooks、MCP、skills 和 helper | [Onboarding 与 Workspace Trust](onboarding-workspace-trust-and-safe-startup.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| Thinking、Effort、Fast Mode 为什么显示开启但请求仍会降级 | [Thinking、Effort 与 Fast Mode](thinking-effort-and-fast-mode.md) | [模型、认证与请求装配](models-auth-providers-request.md) |
| `/usage` 为什么同时涉及 token、美元、额度和自动续跑 | [Usage、成本与 Limits](usage-cost-credits-and-limits.md) | [遥测、日志与诊断](telemetry.md) |
| Purge/import 为什么 exit 1 后磁盘仍可能部分变化 | [Project Purge 与 Import](project-purge-import-and-data-lifecycle.md) | [Storage v5](storage-v5-reference.md) |
| Sandbox status 成功为什么不证明当前命令已隔离 | [Sandbox 安装与运行](sandbox-install-and-runtime-enforcement.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| HTTPS_PROXY、CA 和 client cert 为什么只对部分调用生效 | [Proxy、CA 与 mTLS](network-proxy-ca-and-mtls.md) | [Enterprise Gateway Runtime](enterprise-gateway-runtime.md) |
| `/goal` 为什么会在模型准备结束时重新启动一轮 | [Active Goal 与 Stop-loop](active-goal-and-stop-loop.md) | [Agent Loop](agent-loop.md) |
| Recap、summary、suggestion、feedback 和 memory consolidation 是否同一机制 | [后台模型任务与 Memory](background-model-tasks-and-memory-consolidation.md) | [会话、检查点与 Memory](sessions-checkpoints-memory.md) |
| Advisor 是否在本地运行第二个 Agent | [Advisor 双模型运行时](advisor-dual-model-runtime.md) | [Agent Loop](agent-loop.md) |
| Ultrareview 在哪里审查、修复和发评论 | [Ultrareview 云端审查](ultrareview-cloud-review.md) | [后台、Channels 与 Cloud](cloud-background-channels.md) |
| resume、fork、rewind 到底恢复什么 | [会话、检查点与 Memory](sessions-checkpoints-memory.md) | [韧性与恢复](resilience-and-recovery.md) |
| MCP 工具为什么会动态出现或失效 | [MCP、Agents 与后台协作](mcp-agents-background.md) | [上下文治理与多层缓存](context-governance-and-caching.md) |
| 子 Agent 是否只是另一个 prompt | [MCP、Agents 与后台协作](mcp-agents-background.md) | [Agent Loop](agent-loop.md) |
| fallback 后会不会重复副作用 | [韧性与恢复](resilience-and-recovery.md) | [Agent Loop](agent-loop.md) |
| 模型、provider、endpoint 和凭据最终怎么选 | [模型、认证与请求装配](models-auth-providers-request.md) | [上下文治理与多层缓存](context-governance-and-caching.md) |
| settings 为什么不生效、managed policy 能锁什么 | [Settings、Flags 与 Policy](settings-feature-flags-policy.md) | [工具、权限与 Hooks](tools-permissions-hooks.md) |
| TUI、IDE、Remote Control、cloud session 谁持有执行 | [TUI、IDE 与远程会话](tui-ide-remote-cloud.md) | [会话、检查点与 Memory](sessions-checkpoints-memory.md) |
| 更新、doctor、版本文件和 rollback 怎么区分 | [安装、更新与 Doctor](install-update-doctor-lifecycle.md) | [韧性与恢复](resilience-and-recovery.md) |
| `.node` 到底被谁调用、能重建到什么程度 | [Native Bridge](native-bridge-runtime.md) | [原生重建证据](../reconstructed/EVIDENCE.md) |
| 字段表里的值是什么意思 | [机器清单字段指南](inventory-field-guide.md) | [全量能力面](source-surface.md) |
| 遥测会记录什么、怎么判断慢在哪 | [遥测、日志与诊断](telemetry.md) | [字段指南](inventory-field-guide.md) |
| 某条 Probe 到底执行了什么、能证明到哪 | [精确二进制运行证据指南](runtime-probe-index.md) | [结构化证据注册表](mechanism-evidence.jsonl) |

## 证据索引

- Agent Loop 主状态机：`reverse/javascript/cli.readable.js` 271550-272424。
- 单工具完整控制管线：`reverse/javascript/cli.readable.js` 316092-316457。
- Tool Search 与 deferred schema：`reverse/javascript/cli.readable.js` 114258-114369、156521-156552。
- MCP 动态刷新与循环中途换表：`reverse/javascript/cli.readable.js` 491915-491964、272372-272382。
- resume 消息图恢复：`reverse/javascript/cli.readable.js` 323188-323443。
- file checkpoint 与 rewind：`reverse/javascript/cli.readable.js` 194602-194804。
- 子 Agent 默认与隔离配置：`reverse/javascript/cli.readable.js` 156505-156518、306930 附近。
- team mailbox 与 task claim：`reverse/javascript/cli.readable.js` 279171-279317、202474-202511。
- Stop hook 熔断与 maxTurns：`reverse/javascript/cli.readable.js` 272253-272261、272423-272424。
- Plan Mode 进入、计划、问答与退出审批：`reverse/javascript/cli.readable.js` 277750-281816、322141-322157、395299-396236、526806-527199。
- Structured Output schema、工具、attempt 与终态：`reverse/javascript/cli.readable.js` 155369-155532、270482-270507、592685-592774、597607-597884。
- REPL VM、内层工具与结果重放：`reverse/javascript/cli.readable.js` 292788-294325。
- EndConversation gate、双调用、marker 与终态：`reverse/javascript/cli.readable.js` 301900-302055、402877-402889、602890 附近。
- Remote routine、runner operator 与通知队列：`reverse/javascript/cli.readable.js` 291287-291487、297840-298625。
- Connector/Catalog/MCP operators：`reverse/javascript/cli.readable.js` 154255-154330、296542-296834、298630-299430。
- ClaudeDesign 与 Projects：`reverse/javascript/cli.readable.js` 214610-214762、299631-301897。
- Auto Mode 权限入口与 classifier：`reverse/javascript/cli.readable.js` 395392-395501、326151-326177。
- Plugin Eval case/run/grader/report：`reverse/javascript/cli.readable.js` 445210-448274。
- Daemon、PTY、rendezvous 与 worker respawn：`reverse/javascript/cli.readable.js` 420733-422667。
- Enterprise Gateway 启动与路由：`reverse/javascript/cli.readable.js` 625081-627750。
- Auth/account/subscription：`reverse/javascript/cli.readable.js` 361874-361937、486299-486471、627842-627948。
- Onboarding/workspace trust：`reverse/javascript/cli.readable.js` 593377-594275、89533-89656、91820-91909。
- Thinking/Effort/Fast Mode：见 `thinking-effort-and-fast-mode.md` 的逐分支源码索引。
- Usage/cost/credits/limits：见 `usage-cost-credits-and-limits.md` 的 cost、quota 与 auto-resume 源码索引。
- Project purge/import：`reverse/javascript/cli.readable.js` 333321-334186、627978-628459、629343-629623。
- Sandbox install/runtime：见 `sandbox-install-and-runtime-enforcement.md` 的安装链、wrapper 与 exact-binary Probe。
- Proxy/CA/mTLS：见 `network-proxy-ca-and-mtls.md` 的 transport、CA、cert reload 与 CCR relay 索引。
- Active Goal：见 `active-goal-and-stop-loop.md` 的 `/goal`、Stop hook 与 blocking cap 索引。
- 后台模型任务：`reverse/javascript/cli.readable.js` 268272-270366、584410-584563、295584-296019。
- Advisor：`reverse/javascript/cli.readable.js` 163403-163507、399749-409965。
- Ultrareview：`reverse/javascript/cli.readable.js` 204529-205430、508681-508823、628676-628838。

函数名、行号和分支来自发布 bundle 的可读化布局，不是 Anthropic 原始 TypeScript 模块名。跨版本比较应优先比较状态语义、稳定字段、阈值和可达分支，不能把压缩符号改名本身当成功能变化。

核心结论的机器可校验证据合同见 [mechanism-evidence.jsonl](mechanism-evidence.jsonl)。validator 会检查文件、真实行数、范围内 anchors、Probe 报告字段、每个 Probe claim 是否进入人类索引、官方来源 manifest、引用逐句命中状态和 excerpt hash；不能再靠“文档够长、出现关键词”通过。
