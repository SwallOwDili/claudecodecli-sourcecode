# Claude Code 公开技术原理与 2.1.235 验证矩阵

本页回答一个经常被忽略的问题：网上或官方文档描述的是“Claude Code 当前应该怎么工作”，而这个仓库归档的是一个确定的旧发布物。公开资料可以帮助我们提出正确问题，但只有在 `2.1.235` bundle 中找到可达分支，或用同一版本二进制触发出结果，才能把结论写成本版本事实。

调研日期：2026-08-20。公开网页会继续更新。本次不再只保存 URL：每个响应的 HTTP 状态、字节数、SHA-256 和固定摘录分别保存在 [public-sources/manifest.json](public-sources/manifest.json) 与 [public-source-excerpts.md](public-source-excerpts.md)。这些哈希证明“当时读到的响应”，不把当前文档发布日期倒推成本版本发布日期。

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

### Anthropic Engineering

- [Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

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
| memory 为 Agent 提供跨轮/跨会话持久知识 | `Static` | `MEMORY.md` 发现、截断和大小提示；200 行、25KB 处理分支，114154 附近 | memory 是注入上下文的持久文本，不是模型内部记忆 |
| permissions 在执行前约束工具 | `Static` | PreToolUse 与 permission/policy/classifier 在 `tool.call` 前；updated input 会复验 | 权限决策不是 UI 弹窗装饰，而是工具执行调用链的一部分 |
| sandbox 限制 shell 的文件和网络能力 | `Static` | sandbox/network/filesystem/credential settings 和执行分支进入工具策略层 | 客户端有控制面；操作系统实际强制效果仍依平台和运行配置 |
| hooks 能观察、修改或阻止生命周期事件 | `Static` | PreToolUse、PostToolUse、PostToolBatch、Stop/SubagentStop；Stop 连续阻止默认 cap 8 | hook 能改变控制流，因此也需要超时、错误和熔断语义 |
| MCP 可动态提供工具 | `Static` | `reverse/javascript/cli.readable.js` 491915-491964 的 `tools/list_changed` cache invalidation、refresh 与失败时保留旧表 | 动态刷新由可达静态路径证实；空配置 `mcp list` 只证明命令 surface，不证明 refresh 成功运行 |
| 大工具目录可用 Tool Search 延迟加载 schema | `Static` | `defer_loading`、ToolSearch、缓存和失效，114258-114369、156521-156552、231802-231817 | 节省的是 prompt 中常驻 schema token，不是延迟安装工具 |
| subagent 在独立上下文中工作并向主 Agent 返回结果 | `Static` | 默认 `maxTurns: 200`、`model: inherit`、`permissionMode: bubble`；`reverse/javascript/cli.readable.js` 306920-306938 构造独立 prompt、tool context、abort/model/worktree state | 独立上下文由静态状态构造证实；空 `agents --json` 只证明枚举协议，不证明子 Agent 已运行 |
| agent teams 通过任务和消息协作 | `Static` | task claim、team mailbox、send/broadcast/shutdown 等路径，202474-202511、279171-279317 | 本版客户端存在协作基础设施；具体远端可用性仍受配置/feature gate 影响 |

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

以下命令中的 `$CLAUDE_2_1_235` 指向 SHA-256 已核对的精确发布二进制。

### 版本身份

```text
Command: $CLAUDE_2_1_235 --version
Input: none
Literal output: 2.1.235 (Claude Code)
Exit status: 0
Result: 探针执行对象与目标版本一致
```

### Agent Loop、真实 Read、tool_result 回灌与成功 resume

探针脚本：[probe_agent_loop.mjs](../skill/claude-code-version-diff/scripts/probe_agent_loop.mjs)。固化报告：[agent-loop-tool-result-resume.json](runtime-probes/agent-loop-tool-result-resume.json)。它在隔离 HOME/config/workspace 中启动本地 Messages server，不访问真实模型服务。

```text
Command: $CLAUDE_2_1_235 --print AGENT_LOOP_INITIAL_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID
Input: 模型返回 tool_use {id:"toolu_agent_loop_probe", name:"Read", file:"$WORKSPACE/probe-fixture.txt"}；文件 literal 内容为 AGENT_LOOP_FILE_MARKER
Literal output: TOOL_EXECUTION_OK
Exit status: 0
Observed request result: 第一次请求声明 Read；第二次请求同时包含同 ID 的 tool_use 和 tool_result，tool_result 内容包含 AGENT_LOOP_FILE_MARKER
Result: 精确二进制的模型流 -> 工具执行 -> 结果回灌 -> 下一次模型决策闭环已正向证实
```

```text
Command: $CLAUDE_2_1_235 --print AGENT_LOOP_RESUME_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --resume $SESSION_ID
Input: 上一命令创建并持久化的真实 session
Literal output: RESUME_OK
Exit status: 0
Observed request result: resume 请求包含 AGENT_LOOP_INITIAL_MARKER、TOOL_EXECUTION_OK 和 AGENT_LOOP_RESUME_MARKER
Result: 本版成功 resume 会恢复已持久化历史并加入当前输入
```

报告中的 13 个布尔检查全部为 true，主 Messages 请求数为 3。该探针证明客户端实际行为，不依赖“存在某个字符串”或“错误路径能打印提示”。

### MCP 空配置状态

```text
Command: $CLAUDE_2_1_235 mcp list
Input: 隔离 HOME，无 MCP 配置
Literal output: No MCP servers configured. Use `claude mcp add` to add a server.
Exit status: 0
Result: 空配置是正常可观察状态，证明 `mcp list` 命令 surface 与空状态输出；不证明动态 `tools/list_changed` 已运行
```

### Agent 枚举

```text
Command: $CLAUDE_2_1_235 agents --json
Input: 隔离 HOME，无自定义 agent
Literal output: []
Exit status: 0
Result: 命令面和 JSON 输出协议在本版可达；不证明任何子 Agent 已获得独立上下文并完成任务
```

### 非法 session ID

```text
Command: $CLAUDE_2_1_235 --resume not-a-valid-session-id
Input: 非法 session ID
Literal output: Error: --resume requires a valid session ID or session title when used with --print. Usage: claude -p --resume <session-id|title>. Provided value "not-a-valid-session-id" is not a UUID and does not match any session title.
Exit status: 1
Result: resume 参数校验不接受任意字符串；不证明成功恢复路径
```

### 不存在的合法 UUID

```text
Command: $CLAUDE_2_1_235 --resume 00000000-0000-4000-8000-000000000000
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

1. 保存调研日期、官方 URL 和主张摘要，不复制可能漂移的整页正文。
2. 把每条主张拆成可搜索对象：稳定 key、CLI surface、状态字段、默认值、阈值、错误文本和调用顺序。
3. 在 canonical bundle 中证明分支可达，不用单个字符串命中代替调用链。
4. 对 CLI surface、session、MCP、agent、permission 等可隔离路径运行精确版本探针。
5. 把结果标成 `Public`、`Static`、`Probe` 或 `Boundary`。
6. 版本比较先比较实现证据，再用官方 release notes/当前文档解释动机；不能反过来用宣传文案填补代码证据。

这样，“上网搜原理”才真正转化为逆向工作的输入：公开资料负责告诉我们应该验证哪些机制，发布物和探针负责决定哪些结论可以落在这个版本名下。
