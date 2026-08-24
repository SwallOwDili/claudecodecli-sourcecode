# Claude Code 公开技术原理与 2.1.235 验证矩阵

本页回答一个经常被忽略的问题：网上或官方文档描述的是“Claude Code 当前应该怎么工作”，而这个仓库归档的是一个确定的旧发布物。公开资料可以帮助我们提出正确问题，但只有在 `2.1.235` bundle 中找到可达分支，或用同一版本二进制触发出结果，才能把结论写成本版本事实。

调研刷新：2026-08-24。公开网页会继续更新。本次不再只保存 URL：31 个响应的 HTTP 状态、字节数、原始响应 SHA-256、去噪正文 SHA-256、40 条逐摘录 SHA-256、逐句正文命中状态和固定摘录分别保存在 [public-sources/manifest.json](public-sources/manifest.json) 与 [public-source-excerpts.md](public-source-excerpts.md)。刷新脚本会拒绝任何不能在当次可见正文逐句找到的“引用”。这些哈希证明“当时读到的响应”和“可读语义是否变化”，不把当前文档发布日期倒推成本版本发布日期。

## 证据标签

| 标签 | 定义 | 写作规则 |
| --- | --- | --- |
| `Public` | Anthropic 官方产品文档或 Engineering 文章的公开主张 | 用来解释目的和设计原则，不单独证明版本实现 |
| `Static` | `2.1.235` 发布 bundle 中可定位的字段、分支、阈值或调用链 | 必须给出文件位置和行为解释 |
| `Probe` | SHA-256 与本快照一致的 `2.1.235` 二进制的实际输入/输出 | 必须记录命令、输入、literal output、exit status |
| `Boundary` | 当前文档存在，但本版 bundle/探针没有证实，或属于服务端行为 | 只列为待验证能力，不写成本版已实现 |

精确探针二进制的 SHA-256 为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748`，与 [version.json](version.json) 中的发布物记录一致。系统 PATH 中另一个 `claude` 版本不是目标，因此所有探针都显式使用版本目录中的 `2.1.235` 文件。

## 官方资料清单

### 产品与 Agent SDK 文档

- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [Agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- [Context window](https://code.claude.com/docs/en/context-window)
- [Prompt caching](https://code.claude.com/docs/en/prompt-caching)
- [Sessions](https://code.claude.com/docs/en/sessions)
- [Checkpointing](https://code.claude.com/docs/en/checkpointing)
- [Memory](https://code.claude.com/docs/en/memory)
- [Permissions](https://code.claude.com/docs/en/permissions)
- [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Hooks](https://code.claude.com/docs/en/hooks)
- [MCP](https://code.claude.com/docs/en/mcp)
- [Subagents](https://code.claude.com/docs/en/sub-agents)
- [Agent teams](https://code.claude.com/docs/en/agent-teams)
- [Monitoring usage](https://code.claude.com/docs/en/monitoring-usage)
- [Settings](https://code.claude.com/docs/en/settings)
- [Model configuration](https://code.claude.com/docs/en/model-config)
- [Authentication](https://code.claude.com/docs/en/authentication)
- [Enterprise network configuration](https://code.claude.com/docs/en/network-config)
- [Remote Control](https://code.claude.com/docs/en/remote-control)
- [IDE integrations](https://code.claude.com/docs/en/ide-integrations)
- [Setup](https://code.claude.com/docs/en/setup)
- [Troubleshooting](https://code.claude.com/docs/en/troubleshooting)
- [Data usage](https://code.claude.com/docs/en/data-usage)

### Anthropic Engineering

- [Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Prompt caching is everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything)
- [How we built Claude Code auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode)
- [Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)

## 总体验证矩阵

| 公开主张 | `2.1.235` 状态 | 本版实现证据 | 结论 |
| --- | --- | --- | --- |
| Agent 反复收集上下文、采取行动、验证结果，直到完成或达到停止条件 | `Static` | `USe -> HGS -> tdf`，`while (true)` 管理 model/tool/result/terminal transition，271550-272424 | 本版有真实状态机，不是 SDK 文档里的概念伪代码 |
| tool call 是 Agent 与确定性系统之间的契约 | `Static` | 单工具依次经过输入解析、schema、validate、hook、permission、call、output validate，316092-316457 | 契约在客户端被拆成多道可失败关卡 |
| 工具结果会回到下一轮上下文供模型验证 | `Static` | tool result 保留 `tool_use_id`，批次后合并 messages 并进入下一轮，272293-272424 | 工具错误同样作为观察回灌，不等于循环崩溃 |
| context 是有限资源，运行中需要持续整理 | `Static` | hint、microcompaction、precompute/reactive compact、blocked threshold 和 compact tracking | 本版不是只有 `/compact` 手工命令，而是每轮前后都在治理 |
| prompt caching 复用稳定前缀 | `Static` | system prompt 分段 cache control、message breakpoint、5m/1h TTL gating | 本版实现比“打开缓存”更细，关键在稳定边界和写入资格 |
| session 可以继续、fork 并持久化 transcript | `Static` + `Probe` | `reverse/javascript/cli.readable.js` 323188-323443；精确二进制成功创建 session，再 `--resume`，第三次请求带回初始 prompt、初始助手结果和新 prompt | 本版的成功 resume 与 history 注入已正向证实；不存在 UUID 只作为错误分类证据 |
| checkpointing 支持回退代码和对话 | `Static` | file checkpoint 数量上限 100；edit tracking/rewind，194602-194804 | 能恢复被跟踪文件与会话视图，不是通用外部事务回滚 |
| memory 为 Agent 提供跨轮/跨会话持久知识 | `Static` | `MEMORY.md` 发现、截断和大小提示；200 行、25,000 UTF-16 code-unit 处理分支，114154 附近；官方另以约 25KB 描述 | memory 是注入上下文的持久文本，不是模型内部记忆；非 ASCII 时不能把 code units 当成 UTF-8 字节 |
| permissions 在执行前约束工具 | `Static` | PreToolUse 与 permission/policy/classifier 在 `tool.call` 前；updated input 会复验 | 权限决策不是 UI 弹窗装饰，而是工具执行调用链的一部分 |
| sandbox 限制 shell 的文件和网络能力 | `Static` | sandbox/network/filesystem/credential settings 和执行分支进入工具策略层 | 客户端有控制面；操作系统实际强制效果仍依平台和运行配置 |
| hooks 能观察、修改或阻止生命周期事件 | `Static` | PreToolUse、PostToolUse、PostToolBatch、Stop/SubagentStop；Stop 连续阻止默认 cap 8 | hook 能改变控制流，因此也需要超时、错误和熔断语义 |
| MCP 可动态提供工具 | `Static` + `Probe` | `reverse/javascript/cli.readable.js` 491915-491964；精确二进制收到 `tools/list_changed` 后再次 `tools/list`，新工具在第三个 Messages 请求出现 | 动态刷新已正向证实；本路径有一个请求装配延迟，不是即时热替换 |
| 大工具目录可用 Tool Search 延迟加载 schema | `Static` | `defer_loading`、ToolSearch、缓存和失效，114258-114369、156521-156552、231802-231817 | 节省的是 prompt 中常驻 schema token，不是延迟安装工具 |
| subagent 在独立上下文中工作并向主 Agent 返回结果 | `Static` + `Probe` | 默认 `maxTurns: 200`、`model: inherit`、`permissionMode: bubble`；精确探针观察独立 prompt/tools 请求、异步启动 tool result 和 completed task notification | 独立上下文与两阶段回传均已正向证实；启动 ACK 不是最终结果 |
| agent teams 通过任务和消息协作 | `Public` + `Static` | 官方 Agent Teams 页面明确标注适用于 2.1.178 起；本版 task claim、team mailbox、send/broadcast/shutdown 路径位于 202474-202511、279171-279317 | 2.1.235 客户端与公开版本范围相容；账户、配置和 feature gate 仍决定实际可用性 |
| settings 使用 managed、CLI、local、project、user 多层来源 | `Public` + `Static` + `Probe` | 官方顺序；bundle merge/source 限制；精确探针观察 flag > local > project > user 和 `--setting-sources user` | 普通 scalar 的已触发顺序已证实；managed 路径因系统目录限制保留静态/官方证据 |
| 529 可重试而受控 400 不重试 | `Static` + `Probe` | retry 分类分支；探针请求次数分别为 3 和 1 | “请求失败”不能统一解释，status 分类直接影响延迟和重复风险 |
| 主模型不可用时按 chain fallback | `Public` + `Static` + `Probe` | 当前模型文档；连续 529 计数与 `fui=3`；探针模型序列为 primary x3 -> fallback x1 | 本路径正向证实；认证、计费、rate limit、尺寸和 transport 不自动套用该序列 |
| API bearer 与 API key 使用不同 header | `Public` + `Static` + `Probe` | 官方 credential 顺序；request builder；两次受控 wire capture | bearer 使用 Authorization，API key 使用 x-api-key，二者不会在这两个路径同时发送 |
| prompt caching 可被环境开关移出请求 | `Static` + `Probe` | request cache marker 分支；默认 3 个 marker，禁用后为 0 | 证明请求形状，不证明服务端 cache hit 或最终账单 |
| OTLP prompt 正文默认脱敏 | `Public` + `Static` + `Probe` | monitoring 文档；`<REDACTED>` 分支；本地 `/v1/logs` collector 双跑 | 默认导出事件但隐藏正文；显式开启后正文进入管理员配置的 collector |
| sandbox 在 permission bypass 后仍执行文件/网络限制 | `Public` + `Static` + `Probe` | 两层官方说明、sandbox policy 分支、denyWrite 与零网络命中探针 | permission 与 OS sandbox 是独立控制层，不能用 bypassPermissions 推断子进程无限制 |
| manual compact、fork、file rewind 分别改变不同状态 | `Public` + `Static` + `Probe` | compact boundary、message graph、checkpoint；同版本正向探针 | compact 改逻辑历史，fork 换 session ID，rewind 恢复被跟踪文件；都不回滚远端动作 |
| 官网把 doctor 定义为只读诊断；目标版 handler不repair，但共享preAction可持久化migration，Keychain probe还会add并发起未等待结果的delete；`DISABLE_UPDATES`阻断手动更新 | `Public` + `Static` + `Probe` | setup文档；preAction/migration/Keychain/update gate/doctor分支；真实literal output | “只读”是产品意图，不是端到端filesystem/settings事实；禁用auto updater与禁用全部update也不同 |
| Remote Control 执行留在本机、transcript 经服务端同步 | `Public` + `Static` + negative `Probe`；成功路径 `Boundary` | 官方连接/安全说明；本地 reconnect/attachment 代码；custom endpoint doctor 负向诊断 | 本版能证明客户端边界与不可用原因；未用真实账号触发成功连接和服务端 entitlement |
| IDE 使用 loopback MCP、token 和 Read deny 过滤编辑器上下文 | `Public` + `Static` | 当前 IDE 协议文档与本版 IDE bridge/tool/permission 分支 | 没有在本探针环境启动真实 VS Code extension，故不升级为成功 IDE Probe |
| Prompt Cache 不是局部优化，而是稳定前缀约束整个 Harness | `Public` + `Static` | 官方给出 system/tools -> CLAUDE.md -> session context -> messages 与 reminder/Plan/Tool Search/cache-safe compact；本版对应 system boundary、typed attachment、固定工具状态转换、`defer_loading` 与 parent-prefix compact | 官方设计解释不能替代本版 scope/TTL/gate/hit；详见 Prompt Assembly 和 Context 专题 |
| Auto Mode 同时防 overeager、mistake、prompt injection 与 model misalignment，但不是人工审批等价物 | `Public` + `Static` + `Boundary` | 官方两层 probe/classifier、输入裁剪和评测；本版确定性权限前置、Stage 1/2 XML、fail-closed、denial counters | `0.4% FPR / 17% / 5.7% FNR` 是官方内部数据，不是本机统计；server-side probe 仍是 Boundary |
| Tool Search 在大工具目录中可显著减少常驻 schema，但多一步搜索有延迟 | `Public` + `Static` | 官方 58 tools≈55K、示例 77K->8.7K；本版有 schema token estimate、auto threshold、defer/discover/generation | 85% 是官方示例，不是本workspace固定节省；实际收益看本轮 tools 与 usage |
| 有效 sandbox 要同时限制 filesystem 与 network | `Public` + `Static` + `Probe` | 官方 bubblewrap/Seatbelt + 外部Unix-socket proxy设计；本版两层配置与 bypassPermissions下文件/网络零副作用Probe | 官方84%少弹窗是内部统计；跨平台内核等价性仍是Boundary |
| 模型请求、本地transcript、一方事件、OTEL、Feedback与Remote是独立数据流 | `Public` + `Static` + `Probe` | 当前Data usage提出目的地问题；本版逐条证明request builder、30天本地cleanup、独立telemetry gates、Feedback二次确认、Remote同步 | 当前retention/ZDR/training/delete政策不能由旧binary证明；详见全局数据流专题 |

## Agent Loop：从公开四步到客户端状态机

公开文档常把循环总结为：gather context、take action、verify work、repeat。这个模型有教学价值，但不足以解释 CLI 为什么不会在每个 HTTP retry 时耗掉一个 `maxTurns`，也解释不了工具在流式响应尚未结束时为什么已经开始执行。

`2.1.235` 中实际多了至少六层状态：

1. 请求前吸收用户 queue、passive command 和后台停止信号。
2. 根据 context、cache 和 compact 状态重建本轮消息视图。
3. 模型流逐 block 解析，完整 `tool_use` block 立即进入 executor。
4. scheduler 根据工具与 input 的 concurrency-safe 判定建立重叠或屏障。
5. 工具结果、PostToolBatch 和新用户消息合并到消息图。
6. 根据 Stop hook、maxTurns、fallback、malformed tool use 和 terminal reason 选择继续方式。

所以“Agent Loop 已证实”的含义不是 bundle 中出现 `agent_loop` 字符串，而是这些状态与转换可以连成从输入到下一次 API call 的可达调用链。完整拆解见 [Agent Loop](agent-loop.md)。

## Context Engineering：公开原则如何落到本地机制

Engineering 文章强调，context engineering 管理的是 system instructions、tools、MCP、外部数据和 message history 的整体，而不是只改 system prompt。`2.1.235` 的实现与这条原则有清晰对应：

| 上下文对象 | 本版控制手段 | 为什么存在 |
| --- | --- | --- |
| stable system prefix | 分段 `cache_control` | 降低跨轮重复前缀写入成本 |
| machine dynamic context | 可移动到首条 user block | 避免 cwd/Git/LSP 等变化污染稳定 system cache |
| message history | breakpoint、compact boundary、resume graph repair | 在缓存合法性、窗口和可恢复性间取舍 |
| tool schemas | Tool Search `defer_loading` | MCP/插件很多时避免所有 JSON schema 常驻 |
| old tool results | context hint、microcompaction、文件引用 | 把低价值大结果从活跃窗口移出 |
| long-running plan/knowledge | compact summary、`MEMORY.md` | 压缩后保留继续工作所需高信号状态 |

公开文章的“最小高信号 token 集”是设计目标；具体的 20k 清理提示、最近 5 个 tool result、200k 窗口阈值和 5m/1h cache 价格分支才是本版本静态事实。详见 [上下文治理与多层缓存](context-governance-and-caching.md)。

## Tool Design：为什么 schema 和返回值是执行质量的一部分

Anthropic 的工具文章把工具描述为确定性系统与非确定性 Agent 之间的接口，并强调 namespacing、明确描述、有效返回上下文和 token efficiency。`2.1.235` 的工具管线说明这些建议不只是 prompt 写法：

- 工具名/alias 决定能否解析到真实实现。
- JSON schema 和自定义 validator 决定模型生成的 input 是否可执行。
- `updatedInput` 允许 hook/permission 层修正参数，但修正后必须再次验证。
- output schema 决定工具实现是否履行对 Agent 的返回契约。
- error `tool_result` 仍需保留原 ID 和可解释错误，否则下一轮无法修正策略。
- Tool Search 是否 defer 决定描述/schema 在什么时候消耗上下文。

因此，工具质量问题可能表现成“模型笨”，实际根因却是 description 不清、schema 太宽、错误结果无上下文、输出过大或权限语义与动作不匹配。

## Multi-Agent：独立上下文不是免费并行

公开多 Agent 文章强调 orchestrator-worker 模式、独立 context window、并行搜索和结果压缩，同时明确指出协调复杂度和 token 成本会快速增长。`2.1.235` 的客户端结构支持这个判断：

- 子 Agent 拿到独立的 messages、tools、model/effort、maxTurns、permission context 和 abort controller。
- `model: inherit` 只表示默认继承模型选择，不表示共享同一个模型调用或上下文窗口。
- `permissionMode: bubble` 允许子 Agent 的关键审批上浮，而不是默认绕过主会话控制。
- team/task/mailbox 需要显式 task claim、消息投递和生命周期状态；并行本身不能防止重复研究和任务缝隙。
- 子 Agent 最终要把压缩后的发现返回主 Agent；把完整轨迹无节制复制回主上下文会抵消隔离收益。

这解释了为什么编码任务不应机械地“多开 Agent”：任务存在强顺序依赖或共享文件写冲突时，协调成本可能高于并行收益。详见 [MCP、Agents 与后台协作](mcp-agents-background.md)。

## 精确版本运行探针

以下命令中的 `$CLAUDE_TARGET` 指向 SHA-256 已核对的精确发布二进制。

### 版本身份

```text
Command: $CLAUDE_TARGET --version
Input: none
Literal output: 2.1.235 (Claude Code)
Exit status: 0
Result: 探针执行对象与目标版本一致
```

### Agent Loop、真实 Read、tool_result 回灌与成功 resume

探针脚本：[probe_agent_loop.mjs](../skill/claude-code-version-diff/scripts/probe_agent_loop.mjs)。固化报告：[agent-loop-tool-result-resume.json](runtime-probes/agent-loop-tool-result-resume.json)。它在隔离 HOME/config/workspace 中启动本地 Messages server，不访问真实模型服务。

```text
Command: $CLAUDE_TARGET --print AGENT_LOOP_INITIAL_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID
Input: 模型返回 tool_use {id:"toolu_agent_loop_probe", name:"Read", file:"$WORKSPACE/probe-fixture.txt"}；文件 literal 内容为 AGENT_LOOP_FILE_MARKER
Literal output: TOOL_EXECUTION_OK
Exit status: 0
Observed request result: 第一次请求声明 Read；第二次请求同时包含同 ID 的 tool_use 和 tool_result，tool_result 内容包含 AGENT_LOOP_FILE_MARKER
Result: 精确二进制的模型流 -> 工具执行 -> 结果回灌 -> 下一次模型决策闭环已正向证实
```

```text
Command: $CLAUDE_TARGET --print AGENT_LOOP_RESUME_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --resume $SESSION_ID
Input: 上一命令创建并持久化的真实 session
Literal output: RESUME_OK
Exit status: 0
Observed request result: resume 请求包含 AGENT_LOOP_INITIAL_MARKER、TOOL_EXECUTION_OK 和 AGENT_LOOP_RESUME_MARKER
Result: 本版成功 resume 会恢复已持久化历史并加入当前输入
```

报告中的 25 个布尔检查全部为 true；初始工具闭环加 resume 的 Messages 请求数为 3，后续同一脚本还验证 manual compact 与 fork。该探针证明客户端实际行为，不依赖“存在某个字符串”或“错误路径能打印提示”。

### 补强探针矩阵

完整命令、受控输入、字段解释和 30 条 Claim ID 见 [精确二进制运行证据指南](runtime-probe-index.md)。这里列出影响公开主张判定的 literal result，避免把当前官网文字直接倒灌进旧版本。

| 报告 | 受控输入 | Literal output / observable result | Exit | 结论 |
| --- | --- | --- | ---: | --- |
| `settings-resilience.json` | 四层不同 model；529/400；fallback model | settings 最终值为 flag/local/user；529 请求 3 次，400 请求 1 次；模型序列 primary x3 -> fallback | 成功路径 0，400 为 1 | 层级、retry 分类和 fallback 顺序均为本版实际行为 |
| `telemetry-otlp.json` | 本地 `/v1/logs` collector；prompt gate 开/关 | 默认 `user_prompt=<REDACTED>` 且原 marker 不存在；开启后原 marker 出现 | 0 / 0 | monitoring 文档中的 prompt 隐私门在 2.1.235 可达 |
| `sandbox-enforcement.json` | bypassPermissions；workspace/denyWrite；空域名表 | workspace 文件内容 `ALLOWED`；denyWrite 文件不存在；HTTP server hit count 0 | 0 / 0 / 0 | 工具循环成功结束不等于被拒绝的子动作成功，必须读 tool result 和副作用 |
| `agent-loop-tool-result-resume.json` | persisted session；`/compact`；fork | `system:compact_boundary`、`trigger=manual`、新 fork session ID；旧结构历史不进 fork 请求 | 0 / 0 | manual compact 与 fork 的状态转换正向证实 |
| `checkpoint-rewind.json` | Read/Edit 将文件改为 `CHECKPOINT_MODIFIED`；真实 user UUID | `Files rewound to state at message $USER_MESSAGE_UUID`；最终字节恢复 `CHECKPOINT_ORIGINAL`；rewind 阶段模型请求 0 | 0 | file rewind 是本地补偿操作，不依赖再次询问模型 |
| `runtime-controls.json` | bearer、API key、cache disable、hook deny、Stop hook、maxTurns | Authorization/x-api-key 二选一；cache marker 3 -> 0；deny feedback；Stop 第二请求；`error_max_turns` | 成功路径 0，maxTurns 为 1 | request、cache、控制 hook 和预算终态均有 wire/runtime 证据 |
| `lifecycle-doctor.json` | `DISABLE_UPDATES=1`；损坏 settings；custom endpoint | 管理员禁用更新；doctor 输出 version/commit/platform/search/update/settings/Remote Control 原因 | 0 / 0 | update gate 与 doctor 多故障域可达，自定义 endpoint 边界有明确诊断 |
| `mcp-refresh.json` / `subagent-loop.json` | list_changed；child prompt/tool | 第二次 list；新工具第三请求出现；父循环收到 async ACK 和 completed notification | 0 / 0 | 动态工具与异步 child 都按请求边界进入主循环 |
| `native-reconstruction.json` | 原始与兼容模块相同输入和环境能力审计 | contract PASS；22 项真实对照、0 项 `environment-boundary`、1 项最低覆盖审计，共 23 checks | 0 | arm64 兼容层达到已触发调用合同；本次显示器、Accessibility 与应用图标路径均形成实际对照，x86_64 仍是静态边界 |

这些 Probe 使用本地协议对端的原因，是把变量限制在客户端。它们没有把本地 mock 返回成功写成“Anthropic 服务端也已成功”，也没有把 doctor 的不可用诊断写成真实 Remote Control 成功连接。

### MCP 空配置状态

```text
Command: $CLAUDE_TARGET mcp list
Input: 隔离 HOME，无 MCP 配置
Literal output: No MCP servers configured. Use `claude mcp add` to add a server.
Exit status: 0
Result: 空配置是正常可观察状态，证明 `mcp list` 命令 surface 与空状态输出；不证明动态 `tools/list_changed` 已运行
```

### Agent 枚举

```text
Command: $CLAUDE_TARGET agents --json
Input: 隔离 HOME，无自定义 agent
Literal output: []
Exit status: 0
Result: 命令面和 JSON 输出协议在本版可达；不证明任何子 Agent 已获得独立上下文并完成任务
```

### 非法 session ID

```text
Command: $CLAUDE_TARGET --resume not-a-valid-session-id
Input: 非法 session ID
Literal output: Error: --resume requires a valid session ID or session title when used with --print. Usage: claude -p --resume <session-id|title>. Provided value "not-a-valid-session-id" is not a UUID and does not match any session title.
Exit status: 1
Result: resume 参数校验不接受任意字符串；不证明成功恢复路径
```

### 不存在的合法 UUID

```text
Command: $CLAUDE_TARGET --resume 00000000-0000-4000-8000-000000000000
Input: 结构合法但不存在的 UUID
Literal output: No conversation found with session ID: 00000000-0000-4000-8000-000000000000
Exit status: 1
Result: 本版区分“ID 合法”与“本地存在可恢复 transcript”；成功恢复由上面的三请求正向探针证明
```

`--max-turns 0` 的尝试进入了后续执行路径，未在参数解析阶段立即拒绝，随后被人工中断。它不能证明 0 的最终运行语义，因此不列为成功探针，也不据此推断“无限制”或“禁止执行”。

## 尚未由 2.1.235 证实的边界

以下内容即使出现在当前官方文档，也不能仅凭文档写成 `2.1.235` 客户端事实：

- 后续版本新增的命令、hook event、settings key、权限模式或 Agent Teams UI。
- 远端 feature flag 在某账户、组织、地区和订阅上的实时返回值。
- Anthropic 服务端的 abuse/risk score、模型路由、缓存命中判定和限流策略内部实现。
- 客户端 schema 中声明但目标平台、provider 或 feature gate 未启用的分支。
- source map、原始 TypeScript 文件名、注释、被 tree-shaking 删除的代码。
- 操作系统 sandbox 在所有 macOS/Linux 版本上的等价强制效果。

这些边界不是“没有能力”，而是证据层不同。版本归档必须把“当前产品文档说有”与“目标二进制已证实”分开，否则下一次版本 diff 会把文档更新误判成代码变化。

## 长期验证规则

以后每个版本都按同一顺序处理公开资料：

1. 保存调研日期、官方 URL、HTTP 状态、响应字节、原始响应 SHA-256、去噪正文 SHA-256 和逐摘录 SHA-256。
2. 把每条主张拆成可搜索对象：稳定 key、CLI surface、状态字段、默认值、阈值、错误文本和调用顺序。
3. 在 canonical bundle 中证明分支可达，不用单个字符串命中代替调用链。
4. 对 CLI surface、session、MCP、agent、permission 等可隔离路径运行精确版本探针。
5. 把结果标成 `Public`、`Static`、`Probe` 或 `Boundary`。
6. 版本比较先比较实现证据，再用官方 release notes/当前文档解释动机；不能反过来用宣传文案填补代码证据。

校验器还会扫描所有 Markdown 中的 Anthropic 官方 URL；只要文章引用了一个未进入 manifest 的页面，快照验证就失败。这样能避免“正文链接已经拿来下结论，但机器清单没有记录”的不一致。

这样，“上网搜原理”才真正转化为逆向工作的输入：公开资料负责告诉我们应该验证哪些机制，发布物和探针负责决定哪些结论可以落在这个版本名下。
