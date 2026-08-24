# Claude Code CLI 2.1.235 技术机制总图

用户在项目目录中输入：

> 打开 `config/server.json`，把服务端口从 `8080` 改成 `9090`，运行测试；如果测试失败，找出原因并修好。

Claude Code 不会把这句话直接翻译成一次文件写入。它先把当前会话、项目规则和本轮可用工具装进一个模型请求。模型读不到磁盘本身，只能先提出一个动作：

```json
{
  "type": "tool_use",
  "id": "toolu_read_config",
  "name": "Read",
  "input": {"file_path": "config/server.json"}
}
```

这时文件还没有被读取。`tool_use` 只是模型提出的调用。客户端等这个 block 完整后，在当前工具 registry 中找到 `Read`，解析并校验输入，执行适用的 Hook、权限和路径检查，最后才调用真正的读取实现。成功后，客户端把结果配回原来的 ID：

```text
tool_result(tool_use_id=toolu_read_config)
{"port": 8080, "host": "127.0.0.1"}
```

这对 `tool_use/tool_result` 会进入下一次模型请求。模型现在看到的不是一句“读取成功”，而是自己请求过什么以及客户端实际读到了什么。它据此生成 `Edit`，把 `8080` 精确替换成 `9090`，随后生成 `Bash` 运行测试。`Edit` 仍要经过 schema、自定义校验、`PreToolUse`、permission/policy 和写入检查；`Bash` 也要经过自己的权限与 sandbox 路径。调度器不会让测试越过写入屏障去验证旧文件。

这次测试进程返回：

```text
tool_result(tool_use_id=toolu_test_server)
FAIL tests/server.test.ts
expected http://127.0.0.1:8080
received http://127.0.0.1:9090
```

这不是整个任务的终点。失败输出会作为 `Bash` 的 `tool_result` 回到消息图。下一轮模型看到配置已经修改、哪条断言仍是旧值，以及前面每个动作的配对关系，于是读取并修改测试，再运行一次。第二次测试返回 `PASS` 后，结果再次回灌；模型这次不再提出工具，而是向用户说明改了哪些文件、测试是否通过。客户端还会运行 Stop Hook 并检查轮次与恢复条件，全部放行后才形成 terminal result。

![一次 Claude Code 任务在上下文、Agent Loop、工具控制、外部状态和恢复状态之间循环](visuals/system-lifecycle.svg)

这条执行链就是整个系统的主干：模型负责根据当前观察提出下一步，客户端负责决定提议能否执行并保存因果关系，文件系统和进程负责承载已经发生的结果。下面的机制都可以从这条链上的一个具体时刻找到入口，而不需要先背一张模块分类表。

## 模型第一次请求之前：上下文决定它能看到什么

第一次模型请求不只有用户那句话。客户端还会装入 system prompt、当前会话历史、项目与用户记忆、动态环境信息，以及这一轮真正可见的工具 schema。对话变长后，prompt cache、Tool Search、tool-result cleanup 和 compact 会改变这些内容的成本或表示方式，但不会替模型执行工具，也不会撤销已经完成的写入。

要继续追请求是怎样组装出来的，读 [Prompt Assembly](prompt-assembly-and-system-reminders.md)；要理解缓存、工具 schema 延迟加载和上下文压缩，读 [上下文治理与多层缓存](context-governance-and-caching.md)。

## 从 `tool_use` 到真实调用：客户端掌握执行权

模型输出 `Edit` 或 `Bash` 不代表系统已经接受。客户端还要确认工具当前确实存在，输入能通过 JSON/schema 与工具自身校验，Hook 和权限规则允许，必要时再进入 sandbox，调用完成后还要验证和映射输出。Hook 可以拒绝、延迟或改写输入；permission 可以要求一次性或更大范围的授权；这些决定都会影响随后写回模型的结果。

完整执行顺序见 [Agent Loop 专题](agent-loop.md) 和 [工具、权限与 Hooks](tools-permissions-hooks.md)。工具为什么“存在于发布物”却不一定进入本次请求，见 [工具注册与宿主表面](tool-registration-and-host-surfaces.md)。

## `tool_result` 回来之后：历史必须能解释刚才发生了什么

客户端用 `tool_use_id` 把结果配回调用，并把这段因果写入会话历史。Transcript 保存事件，消息图保存逻辑父子关系，file checkpoint 保存受管文件的可恢复内容；它们解决的是不同问题。进程退出后，内存里的调度队列会消失，只有已经投影到这些持久对象中的状态才可能被 `resume`、fork 或 rewind 找回。

这些对象的关系见 [会话、检查点与 Memory](sessions-checkpoints-memory.md)。模型回复、prompt、transcript、远端系统和本地文件分别流向哪里，见 [全局数据流与隐私](client-data-flow-and-privacy.md)。

## 请求或工具失败之后：恢复的是具体对象，不是整个世界

网络重试可以重发尚未完成的 API attempt，fallback 可以切换模型，reactive compact 可以重建更短的消息视图，tombstone 可以移除失败分支的临时消息，rewind 可以恢复受管文件。但已经启动的命令、已经发送的远端请求和已经完成的外部写入不会因为消息被删掉而自动撤销。恢复逻辑必须先回答“哪个 owner 持有这份状态”，再决定重试、重连、补偿还是停止。

分层恢复路径见 [韧性与恢复](resilience-and-recovery.md)；后台执行、MCP、子 Agent 与团队状态的 owner 见 [MCP、Agents 与后台协作](mcp-agents-background.md)。

## 整条链怎样被观察：事件不等于业务事实

同一次任务会产生模型请求耗时、首 token、工具排队和执行、权限等待、Hook、compact、retry 与 terminal reason 等记录。它们可以帮助定位“慢在哪里、为什么停止”，但一条事件名存在只证明客户端定义或触发了一个候选观察；是否采样、是否导出、远端是否接收，以及业务动作是否真正成功，还要分别验证。

先读 [遥测、日志与诊断](telemetry.md) 理解各条观测通道，再在 [事件语义目录](telemetry-event-catalog.md) 中查询具体事件和字段。

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

## 按条件启动的专用运行时

上面的执行链解释普通请求怎样从模型提议走到真实结果。下面这些机制只在对应命令、设置、账号能力或环境出现时启动；它们有独立状态、失败和副作用，查到相关问题时再展开。

<details>
<summary>查看条件运行时的触发入口、状态和常见误判</summary>


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

</details>

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

## 同一条执行链怎样处理并发和中途输入

模型可以在一个响应中产生多个 `tool_use`。客户端不必等整段文字流结束才开始工作：一个完整 block 到达后就能进入调度器。只读且并发安全的调用可以重叠；`Edit` 这类会改变共享状态的调用形成屏障，后面的 `Bash` 不能越过它去测试旧文件。并发只改变等待时间，不改变每个结果与 `tool_use_id` 的配对关系。

用户也可能在测试尚未结束时补一句“测试里的旧端口也一起更新”。这条消息进入 queue，不会改写已经发出的模型请求，也不会篡改正在执行的工具输入。客户端在下一次 API call 前吸收它，让模型同时看到测试结果和新的用户要求；如果吸收失败，消息不会被静默丢弃。

这期间，transcript 持续记录逻辑过程，file checkpoint 保存可支持 rewind 的文件状态。若模型请求发生 fallback，失败分支的临时消息可以被 tombstone，但已经完成的文件写入仍需显式恢复。`maxTurns=1` 也只阻止工具结果之后的下一次模型判断，不会把第一轮已经执行的工具当成没有发生。

这才是“Agent 能执行多步骤任务”的技术含义：模型不必一次规划完美；运行时让它不断获得经过约束的新事实，同时保持调用与结果可配对、任务可停止、失败可诊断。

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
