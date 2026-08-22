# Claude Code CLI 2.1.235 完整机制说明书

这份文档只讲 `2.1.235`。它把分散在 Agent Loop、上下文治理、会话恢复、权限、MCP、遥测、原生桥接和发布差异专题中的结论重新组织成一条完整运行链，目标是回答三个问题：Claude Code 到底在本机做了什么；每一层状态怎样进入下一层；用户为什么会看到某种性能、费用、权限或恢复结果。

本文不是字段清单，也不把当前官网行为直接倒灌成 `2.1.235` 的事实。每个重要结论分别依赖以下证据：

- **Static**：`2.1.235` 发布 bundle、可读化 JavaScript、Mach-O、schema、常量或可达分支；
- **Probe**：SHA-256 固定为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748` 的精确二进制在隔离环境中的真实输出；
- **Public**：抓取并固化 hash 的 Anthropic 官方说明，用来解释设计目的或提出验证假设；
- **Boundary**：客户端发布物中不存在的服务端实现、账户状态、隐藏策略或构建前源码。

结构化证据在 [mechanism-evidence.jsonl](mechanism-evidence.jsonl)，逐项命令、输入、输出、退出状态在 [runtime-probe-index.md](runtime-probe-index.md)。本文负责把这些证据讲成人能沿着生命周期理解的系统。

需要查全量表面时，不要在本卷里翻零散提及：先读 [71 类证据归属地图](product-surface-evidence-map.md) 判断每类 inventory 是产品结构、真实调用点、混合 heuristic、依赖还是证据底座，再读 [全面性审计](completeness-audit.md) 判断 52 个能力面的证据深度；读 [工具注册与宿主表面](tool-registration-and-host-surfaces.md) 区分人工维护的 29 项核心参考、80 个同工厂 AST 注册调用点、工厂调用展开和一次请求真实 `tools[]`，读 [核心终端工具参考](builtin-tools-reference.md) 查逐工具状态与副作用，读 [Brief 用户可见输出](brief-mode-and-user-visible-output.md) 查主视图、附件和漏调修复。Settings、CLI/SDK、Slash Command、Hook、Storage 及其他专用状态机继续由对应专题提供精确集合和完整失败合同。

## 1. 先给结论：它不是聊天壳，而是本地 Agent 运行时

Claude Code CLI 同时承担六类责任：

1. **上下文编排器**：收集用户输入、system prompt、CLAUDE.md、Git、IDE、memory、工具 schema 和历史消息，控制它们何时进入模型窗口。
2. **Agent 执行器**：反复调用模型，解析流式 `tool_use`，执行工具，再把 `tool_result` 回灌给下一轮模型。
3. **本地控制面**：实施 permission、managed policy、hook、sandbox、文件路径、网络域名、凭据和扩展信任规则。
4. **状态存储器**：保存 JSONL transcript、消息图、compact boundary、file checkpoint、task、Agent、memory 和一部分客户端缓存。
5. **多入口产品壳**：提供 TUI、print/SDK、IDE、Remote Control、cloud session、后台 Agent、voice 和 Computer Use。
6. **观测与恢复层**：处理 retry、fallback、compact、resume、rewind、debug、OTEL、Datadog、一方事件和 doctor。

因此，一次“帮我修改代码并运行测试”并不是一次 HTTP 请求，而是本地状态、模型状态和外部副作用反复交接的过程。

```text
用户输入
  -> 读取会话、设置、项目、工具、Agent 和环境状态
  -> 计算本轮可发送的 system/messages/tools
  -> 添加 cache marker、beta、model/provider/auth 字段
  -> 调用 Messages API 并解析流
  -> 完整 tool_use 出现后启动本地工具
  -> schema / hook / permission / policy / sandbox / tool body
  -> 生成同 tool_use_id 的 tool_result
  -> 吸收中途消息、MCP 变化、Stop hook 和剩余工具结果
  -> 决定结束、继续、compact、retry、fallback 或进入后台
  -> 保存 transcript、checkpoint、usage、telemetry 和 UI 状态
```

## 2. 发布物身份：这份分析绑定哪一个程序

| 项目 | `2.1.235` 实际值 |
| --- | --- |
| 本机归档源 | `$CLAUDE_INSTALL_ROOT/versions/2.1.235` |
| 文件类型 | Mach-O 64-bit executable, arm64 |
| 文件大小 | `313,334,608` bytes |
| SHA-256 | `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748` |
| 签名主体 | `Developer ID Application: Anthropic PBC (Q6L2SF6YDW)` |
| Bun payload | `243,390,734` bytes |
| 主 packed JavaScript | `27,305,344` bytes，`65,943` 行 |
| JSC bytecode | `204,740,576` bytes |
| 解包文件 | 15 个 |
| 原生模块 | 5 个模块，7 个架构 slice |

`command -v claude` 只是入口。真正归档时必须解析符号链接并 hash 版本文件，因为当前 PATH 随升级变化，而历史探针需要一直指向同一个发布物。`analysis/version.json`、`unpack-manifest.json` 和所有 runtime report 都记录同一 hash。

发布物是 Bun standalone。可执行文件内部同时包含 packed JavaScript、JSC bytecode、`.node` 模块和资源。`extracted/cli.js` 是 canonical packed bytes 的可检索视图，不是可以直接交给普通 Node/Bun 独立运行的源码仓库；它仍依赖 standalone 的 Bun wrapper、虚拟文件系统和 bytecode 组织。

## 3. 逆向结果分成哪几层

| 层 | 保存内容 | 最适合回答的问题 | 证据边界 |
| --- | --- | --- | --- |
| `extracted/` | 发布物实际携带的 15 个文件 | 文件、资源、module payload 是否存在 | 不恢复打包前模块树 |
| `reverse/bytecode/` | 完整 JSC bytecode dump | 发布物携带了多少字节码 | 不是 JavaScript 源码 |
| `reverse/javascript/` | 固定工具生成的可读 JS | 调用链、分支、字段、常量 | 局部变量名和格式不是原值 |
| `reverse/native/` | Mach-O headers、imports、exports、symbols、strings、反汇编 | 原生依赖、ABI 和底层框架 | 没有源码级 DWARF |
| `reconstructed/` | 独立兼容实现 | 能否重新实现观察到的 N-API 合同 | 不等于 Anthropic 原始 Rust/Swift/C++ |
| `source-inventory/` | 71 类确定性清单 | 跨版本稳定比较字段 | 广义字符串需要回 callsite |
| `analysis/*.md` | 人类机制解释 | 为什么、怎么运行、失败与影响 | 结论必须回到上述证据 |

生产构建已经丢弃的注释、原始 TypeScript 文件名、模块边界、未压缩局部名、tree shaking 删除代码和原生优化前函数体没有留在发布物中。兼容重建通过测试，只说明外部合同在覆盖范围内一致。

## 4. 启动入口与运行模式

### 4.1 交互式 TUI

默认 `claude` 启动终端界面。TUI 持有输入缓冲区、消息列表、tool progress、permission dialog、任务列表、Agent 状态、模型、effort、permission mode、context/费用显示和若干 panel 状态。

输入框不是普通 readline。它还处理：

- 多行文本、历史、mention、slash command 和粘贴；
- Vim 模式、光标、selection、快捷键和输入法；
- spellcheck 子进程与高亮位置映射；
- permission comment field、计划审批和任务面板；
- terminal resize、alternate screen、screen reader 和无障碍模式。

因此 `2.1.235` 的 Shift+Tab、快速方向键加 Enter、Vim 光标和多行高亮修复都属于状态正确性，而不仅是视觉调整。

### 4.2 Print/SDK

`--print` 用于非交互调用，可输出 text、JSON 或 stream JSON。SDK 控制面还支持：

- partial message 和完整 result；
- `--max-turns`、预算、model、effort；
- `--session-id`、`--resume`、`--fork-session`；
- allowed/disallowed tools 和 permission prompt tool；
- JSON Schema structured output；
- init、assistant、user、stream event、tool result、compact boundary、control request/response、hook 和 MCP 状态。

自动化调用不能只看进程 exit code。一个工具失败后模型修正并最终完成，exit 仍可为 0；达到 `maxTurns` 则会形成 `error_max_turns`、`is_error=true` 和结构化 terminal reason。

### 4.3 IDE、Remote Control 与 Cloud

IDE 连接负责把编辑器选区、打开文件、诊断、面板焦点和会话身份与 CLI 交换。Remote Control 把 UI/设备连接到本地或远端会话；cloud/teleport/thin-client 路径把部分模型、cwd、tools、MCP 和 autocompact 状态交给 worker。

这些路径并不共享一份简单全局状态。TUI、IDE extension、Remote Control client、cloud worker 和本地 Agent Loop各自持有连接与显示状态，通过协议消息同步。Malformed frame、错误 ownership 或不支持的 endpoint 需要 fail closed，而不是把远端字段直接当可信配置。

## 5. 状态所有权：先分清谁保存什么

### 5.1 进程内临时状态

- 当前 Agent Loop 的 `messages`、`turnCount`、recovery counter；
- streaming response 和 in-progress tool 表；
- AbortController、hook runner、permission context；
- tool schema cache、model config cache；
- MCP connection、generation 和 discovery cache；
- TUI 输入、panel、focus、光标和临时审批状态。

进程退出后，这些对象不会自动复活。Resume 会重新构造能持久化的逻辑状态，但不会恢复旧 Promise、socket、abort controller 或普通子进程。

### 5.2 会话持久状态

- JSONL transcript 的 user/assistant/tool/system/progress/attachment 条目；
- message UUID、parent UUID、logical parent 和 leaf；
- compact summary、`compact_boundary` 和 preserved messages；
- session ID、fork identity、部分 task/Agent metadata；
- file checkpoint 与 rewind 索引；
- session 展开状态、任务状态和部分 UI metadata。

### 5.3 项目与用户持久状态

- user/project/local/managed/flag settings；
- CLAUDE.md、rules、skills、commands、agents、plugins；
- auto memory 和 `MEMORY.md`；
- MCP 配置、项目批准和 OAuth/credential metadata；
- telemetry failed batch、client-data cache、update 状态。

### 5.4 外部状态

- 文件系统、Git、Shell 子进程；
- MCP server、数据库、远端 API、部署系统；
- IDE、浏览器、终端和 macOS 应用；
- 麦克风、屏幕、键鼠、TCC；
- Anthropic 或 provider 服务端会话、缓存、配额和账号状态。

消息 tombstone、模型 fallback 和 transcript rewind只能改变 CLI 已持有的表示。已经写入外部系统的动作需要 checkpoint、幂等键、补偿 API 或人工回滚。

## 6. 一次请求到底装了什么

模型请求不是把 transcript 原样发出。CLI 先产生本轮“逻辑消息视图”，再装配 system、tools、betas、缓存 marker 和 provider 字段。

### 6.1 历史消息

输入来源包括：

- 当前 session 的 user/assistant/tool 消息；
- 最后一个有效 compact boundary 之后的逻辑历史；
- compact summary 和 preserved message；
- resume/fork 修复后的主链；
- 当前轮用户输入和中途排队消息；
- task notification、hook feedback、MCP/tool error；
- 被外置的旧 tool result 占位信息。

JSONL 是事件存储，送给模型的是过滤、修链、压缩和替换后的表示。二者不能用行数直接等同。

### 6.2 System prompt 固定层

固定层包含 Agent 身份、工具使用规则、代码和安全约束、输出协议等较稳定内容。为了提高 prompt-cache 复用，客户端会尝试让这部分在多轮之间保持字节稳定。

### 6.3 机器动态层

动态内容包括 cwd、Git 状态、环境提醒、可用工具、IDE 状态、memory path、日期和部分 session 状态。动态段若混入稳定 prefix，每次小变化都可能让整段 cache 失效。代码提供把 cwd/environment/memory/Git 状态从 system prompt 移到第一条 user message 的路径，用来改善稳定前缀复用。

### 6.4 User context 与 system context

CLAUDE.md、rules、memory、项目说明、IDE 选区、文件片段、Git diff、附件和工具发现结果可以作为不同来源的上下文进入消息。来源不同意味着信任、缓存、持久化和更新生命周期不同，不能全部称为“system prompt”。

### 6.5 工具 schema

每个实际可用工具需要 name、description、input schema 和可选的 output contract。工具集合来自核心终端对象、条件 CLI 对象、hosted/product wrapper、内部/eval wrapper、动态 factory、MCP、plugins 和 Agent 模式。`2.1.235` 的 29 项核心终端清单来自提取器维护的 name allowlist 与 bundle 静态 assignment 交集；Acorn 另从 canonical bundle 的同一工具工厂恢复出 80 个 `Yi({...})` AST 调用点，其中 77 个 name 可直接解析、3 个保留动态 expression，并按 consumer/host 人工分类为 29 Core terminal、28 Conditional CLI、16 Hosted/product、4 Internal/eval、3 Dynamic factory。两个 `e.name` 工厂还能由本版调用参数展开成 `ListPlugins`、`ListSkills`、`SearchPlugins`、`SearchSkills`；只有 eval factory 的最终名称和数量依赖运行时。29、80、工厂展开实例和一次请求的实际工具数不是同一个口径。

直接调用点或工厂模板之后还要经过工厂调用、宿主归属、账号/feature/platform/session gate、alias canonicalization、deny/policy、Tool Search/defer、MCP generation 和 request builder。`isEnabled`、`isReadOnly`、`isConcurrencySafe`、`shouldDefer` 等字段说明注册对象字面量声明的运行合同，不表示当前状态一定启用，也不表示没有网络、呈现、遥测或附件副作用。完整 80/80 调用点表和七道门见 [工具注册、条件工具与宿主表面](tool-registration-and-host-surfaces.md)。

当工具太多时，Tool Search 可以只暴露延迟工具的名称和 `defer_loading` 合同，模型需要先发现再取得完整 schema。这减少常驻工具说明，但增加一次发现路径和动态刷新复杂度。

### 6.6 最终请求字段

最终 Messages body 可包含：

| 字段 | 含义 | 何时变化 |
| --- | --- | --- |
| `model` | provider 解析后的实际模型 ID | alias、provider、fallback、dynamic config |
| `messages` | 本轮逻辑消息视图 | queue、compact、resume、tool result、hook |
| `system` | 分段 system blocks | 动态 prompt relocation、cache scope |
| `tools` | 当前可调用工具 schema | mode、MCP generation、Tool Search、permission |
| `tool_choice` | 是否强制/限制工具选择 | command/SDK/内部恢复路径 |
| `betas` | 客户端申请的协议能力 | provider、model capability、feature gate |
| `metadata` | 请求关联与产品元信息 | session/query/source 等 |
| `max_tokens` | 输出上限 | model catalog、dynamic config、请求模式 |
| `thinking` | thinking/effort 配置 | model capability、用户设置、模式 |
| `output_config` | structured output 等输出约束 | SDK/schema 请求 |
| `context_management` | API context management 对象 | capability beta 被选中时 |
| `context_hint` | 服务端上下文提示 | first-party 主线程且阈值/gate 满足 |
| `cache_control` | prompt cache marker/TTL/scope | breakpoint、provider、disable switch |

字段存在于 bundle 不代表每次请求都会发送。请求 builder 会根据 provider、base URL、认证来源、model capability、query source、feature/client data 和错误 latch 选择。

## 7. Model、Provider、认证和请求路由

### 7.1 Model catalog

`2.1.235` 内置 17 个 model entry、6 个 pricing tier 和 4 个 alias family。entry 可携带：

- first-party、Bedrock、Vertex、Foundry 等 provider model ID；
- context window、1M context 能力和最大输入/输出；
- effort、adaptive thinking、fast mode、mid-conversation system；
- prompt-cache 5 分钟/1 小时写入价格和读取价格；
- image limit、advisor rank、fallback provider model。

内置 catalog 是离线基线。动态 model config 成功时可补充服务端 `max_input_tokens`、`max_tokens` 等；失败时客户端保留已有 catalog/client-data，而不是让整个启动因配置拉取失败。

### 7.2 Provider 选择

代码存在 gateway、Bedrock、Foundry、Anthropic cloud variant、Mantle、Vertex 和 first-party 等分支。选择发生在 request builder 之前，因为 endpoint、模型 ID、认证 header、beta 和某些能力都随 provider 改变。

自定义 `ANTHROPIC_BASE_URL` 默认不自动获得 first-party 身份；host 为 `api.anthropic.com` 或显式 override 才进入对应 first-party 判断。这样可以避免把任意兼容网关当作拥有全部 Anthropic 私有能力。

### 7.3 认证来源与 wire shape

隔离探针实测两条路径：

- `ANTHROPIC_AUTH_TOKEN` -> `Authorization: Bearer ...`，不发送 `x-api-key`；
- 仅 `ANTHROPIC_API_KEY` -> `x-api-key: ...`，不发送 `Authorization`。

`apiKeyHelper` 是可执行来源，不是普通设置字符串。它还受 workspace trust 和配置来源约束。Cloud provider credential、OAuth/profile/subscription entitlement 有各自分支；当前本地探针没有伪造真实云账号成功路径。

### 7.4 Request attempt 不等于 Agent turn

一次 Agent 模型轮次可能包含多个 HTTP attempt。实测 `CLAUDE_CODE_MAX_RETRIES=2` 时，受控 529 序列为 `529, 529, 200`，总请求数 3；受控 400 只请求 1 次。`maxTurns` 管新的模型决策轮次，不会因为网络 retry 自动消耗同样数量的 Agent turn。

## 8. Agent Loop：持续执行的核心状态机

### 8.1 Loop 持有的关键状态

| 状态 | 作用 |
| --- | --- |
| `messages` | 当前逻辑消息历史和新结果 |
| tool context | 工具集合、权限、hook、MCP、Agent 环境 |
| `turnCount` | 已进行的模型决策轮次 |
| Stop hook count/active | 控制 Stop hook 重入与熔断 |
| recovery state | max_tokens、malformed tool、thinking-only、reactive compact |
| model/fallback state | 当前模型、备用模型、fallback consent/credit |
| streaming executor | 已排队、运行中、完成的工具调用 |
| abort state | 用户取消、fallback、tool abort 和 loop cleanup |

### 8.2 每次迭代的顺序

```text
1. 吸收排队的用户消息、task notification 和外部状态
2. 修复/过滤消息，计算本轮逻辑历史
3. 检查 context、microcompact、precompute/reactive compact
4. 刷新当前工具、MCP generation 和 Agent context
5. 创建本轮 streaming tool executor
6. 构造 model/system/messages/tools/fallback 请求
7. 解析流式 content block、usage、stop reason 和 timing
8. 完整 tool_use block 到达后立即排入工具执行器
9. 模型流结束后排空剩余 tool_result
10. 处理 Stop hook、maxTurns、tool endsTurn、defer、background
11. 决定 completed、继续下一轮或 typed terminal error
```

### 8.3 工具可以在模型仍流式输出时开始

执行边界是“一个 `tool_use` content block 已完整结束并且 input 可解析”，而不是“整个 assistant response 已结束”。这样前面的独立工具能与后续模型输出重叠，降低总延迟。

半截 JSON、尚未闭合的 tool block 或仅出现工具名不会执行。这个边界避免网络中断时拿不完整参数触发写操作。

### 8.4 并发不是无条件 `Promise.all`

streaming executor 只允许标为 concurrency-safe 的工作重叠。非安全工具形成屏障：它需要等待前面的并发安全任务完成，并阻止后续任务跨过自己执行。

```text
safe A -----+
safe B -----+--> barrier write C --> safe D / safe E
```

结果仍按各自 `tool_use_id` 关联，不以完成时间改变模型声明的身份。执行器维护 in-progress 表，yield 完成结果后再移除对应 ID。

### 8.5 工具结果如何形成闭环

精确二进制探针让模型返回一个真实 `Read` tool use。CLI 读取临时文件后，第二个 Messages 请求同时携带：

- 原 assistant 的 `tool_use`；
- 同 ID 的 user `tool_result`；
- 文件中的受控 marker。

模型随后返回 `TOOL_EXECUTION_OK`。这证明工具卡片显示在终端并不等于模型已经看到结果；只有同 ID 的 `tool_result` 进入下一请求，闭环才完成。

### 8.6 无工具响应的恢复分支

- **普通完成**：有用户可见文本，stop reason 合法，进入 Stop hook/terminal 判断。
- **`max_tokens`**：保留已有 assistant 内容，加入 continuation 提示，用独立 counter 继续生成。
- **malformed tool use**：stop reason 声称 tool use，但没有完整 block；追加纠错消息并有界重试。
- **thinking-only**：只有 thinking、没有可见答案；追加一次要求给出用户可见结果的提示。

这些恢复不应统一称为“重试”。它们重做的对象、计数器、消息保留和副作用风险不同。

### 8.7 Stop hook 会重新打开 Loop

Stop hook 可以阻止本轮结束并返回反馈。客户端把反馈加入 messages，增加 `turnCount` 和 blocking count，再请求模型。默认连续 blocking cap 为 8，避免错误 hook 让会话永久循环。

探针实测第一次 Stop hook block 后，反馈进入第二个 Messages 请求，第二次模型决策才成功结束。

### 8.8 `maxTurns` 的准确语义

`maxTurns=1` 探针中：

1. 第一次模型请求成功选择工具；
2. 工具和 PostToolUse 都完成；
3. CLI 不再发第二次模型请求；
4. 最终 subtype 为 `error_max_turns`，exit 1。

因此 `maxTurns` 限制“还能不能进行下一次模型决策”，不会为了满足预算而中途抹掉已经完成的工具动作。

### 8.9 主 Agent 与子 Agent

子 Agent 复用核心 Loop，但拥有独立 prompt、tool set、model/effort、query source、permission context、worktree、abort 和 Messages 请求。探针显示 child 请求不包含 parent prompt。

后台子 Agent 的 `async_launched` tool result 只是启动确认；完成结果通过后续 task notification 回到父循环。父 Agent 把 launch ACK 当成最终结果会过早结束或重复派发。

## 9. 单个工具调用的完整管线

模型输出 `tool_use` 后，CLI 仍会经过多道关卡：

```text
查找工具
  -> 解析 input JSON
  -> JSON Schema 校验
  -> 工具自定义 input 校验
  -> PreToolUse hook
  -> hook updatedInput 后重新校验
  -> permission / rule / managed policy / classifier
  -> sandbox / path / network / credential 环境
  -> 工具实现
  -> PostToolUse hook
  -> output schema / hook output 校验
  -> 生成 tool_result
```

### 9.1 工具不存在

返回与原 `tool_use_id` 配对的 error result，让模型知道名称不可用或工具集合已变化。CLI 不应因此直接丢失整个 Agent Loop。

### 9.2 Input 错误

JSON parse、schema、enum、路径或工具自定义验证失败，都发生在真实副作用之前。模型可在下一轮缩小参数或换工具。

### 9.3 PreToolUse

PreToolUse 可以允许、阻止、要求 defer，或返回修改后的 input。修改后的 input 必须重新验证，不能因为 hook 已运行就跳过 schema。

探针实测 PreToolUse deny 阻止 `Read` 本体，下一请求收到带 hook 原因的 paired error result，且没有临时文件 marker。

### 9.4 Permission 与 policy

permission decision 会综合 mode、deny/ask/allow rule、managed policy、命令/路径分类、workspace trust 和当前会话批准。持久 allow 规则、session allow 和本次批准是不同作用域。

### 9.5 工具实现与 PostToolUse

工具成功后，PostToolUse 可以观察或修改输出。非法 hook output 不应把一个成功动作伪装成从未执行；客户端需要保留原结果并附加 hook error。异常、abort、timeout 和 output validation failure也要映射成结构化 `tool_result`。

### 9.6 工具批次之后

Loop 在批次结束后还会处理：

- 剩余并发工具结果；
- PostToolBatch；
- MCP/tool generation 变化；
- 中途用户输入和 task notification；
- `tool endsTurn`、defer/background request；
- Stop hook、maxTurns 和 abort。

所以“工具返回成功”仍不是一次 Agent 任务的最终终止点。

## 10. 权限、风控、Sandbox 和企业治理

### 10.1 六种规范化 permission mode

`2.1.235` 的规范化模式为：

- `default`：按规则决定自动允许、询问或拒绝；
- `acceptEdits`：扩大编辑类动作的自动接受范围；
- `auto`：面向自动推进的策略组合；
- `bypassPermissions`：跳过 Claude Code 交互审批层；
- `dontAsk`：不弹交互询问，未自动允许的动作走拒绝；
- `plan`：限制在计划/分析阶段；

输入表面还接受 `manual` 作为 `default` 的兼容 alias。模式不是 OS 能力。即使 `bypassPermissions`，sandbox、macOS TCC、文件权限和远端服务权限仍可能阻止动作。

### 10.2 Rule 顺序

官方和本版结构都区分 deny、ask、allow。核心原则是 deny 优先于 ask，ask 优先于 allow，而不是“最具体规则永远赢”。Managed policy还可以锁定只使用管理员 permission rules，清空 CLI/session 额外 allow 表面。

### 10.3 Settings source 不是简单对象覆盖

普通设置大体遵循 managed、command line、local、project、user 的优先级，但具体字段可能：

- 整块替换；
- 数组合并或去重；
- 只允许 user/managed；
- project/local 被忽略；
- managed-only；
- policy helper 刷新失败时保留旧值或使用静态默认。

探针用四层不同 model 值验证：flag settings 胜 local，local 胜 project，project 胜 user；`--setting-sources user` 会排除 project/local。管理员目录和 managed helper 未用普通用户路径伪造。

### 10.4 文件系统控制

文件治理包括：

- workspace root 和 additional directories；
- read/write allow/deny；
- symlink 和路径解析；
- worktree 边界；
- 外部 CLAUDE.md import trust；
- file checkpoint 可恢复范围；
- Git metadata、bare repo、可植入 hook 路径和复合命令检查。

探针在 `bypassPermissions` 下验证：workspace 内写入成功，`denyWrite` 目标没有落盘。说明 permission 与 sandbox 是两层控制。

### 10.5 网络控制

网络治理不仅是 URL allowlist。还要考虑：

- Bash 子进程网络；
- MCP transport；
- provider/model endpoint；
- redirect 和实际 hostname；
- proxy、NO_PROXY 和 credential forwarding；
- WebFetch/WebSearch/浏览器/IDE bridge 的独立通道；
- managed network policy。

严格空域名探针中，Bash 请求本地 HTTP 地址失败，受控 server hit count 为 0。它证明当前 macOS 路径真实阻断了该连接，不自动外推所有平台和所有网络工具。

### 10.6 凭据与 helper

API key、bearer token、AWS/GCP/Azure credential、OAuth、keychain 和 helper需要按来源、传播范围和子进程 scrub 分开分析。项目配置不能任意取得管理员 helper 权限。关闭 telemetry也不等于模型请求、MCP 或 updater停止联网。

### 10.7 Hooks 是可编程控制层

31 个 hook event 覆盖 session、prompt、tool、permission、compact、stop、subagent 等生命周期。Hook 可以：

- 记录或审计；
- 修改 input/output；
- 阻止工具；
- 要求 defer 或用户确认；
- 在 Stop/SubagentStop 时重新打开 Agent Loop；
- 在 compact 前执行自定义逻辑。

Hook 自身也有 timeout、exit code、JSON/schema 和来源信任问题。错误 hook 不能被描述为“更强的权限系统”；它可能扩大延迟、破坏结果或造成循环，因此需要 cap 和 fail-closed/fallback 规则。

### 10.8 客户端风控与服务端风控边界

客户端可观察的是工具、文件、网络、命令、凭据、扩展、workspace trust、企业 policy 和用户批准。账户 abuse score、封禁、隐藏模型路由、服务端内容风控和容量调度属于服务端边界。仓库中专门登记 `boundary.server-risk-scoring`，避免用本地 permission 规则冒充 Anthropic 账号风控。

## 11. 上下文治理：不是“快满了就总结”

上下文治理同时处理四个不同问题：

1. **窗口容量**：本轮输入是否装得下；
2. **注意力质量**：旧噪声是否挤压当前高价值内容；
3. **缓存成本**：稳定前缀是否重复写入；
4. **持久恢复**：compact 后能否 resume/fork 并保持逻辑链。

把 prompt cache、tool schema cache、microcompaction、auto-compact 和 transcript storage 统称为“多层缓存”会掩盖它们完全不同的对象和失效条件。

## 12. 多层缓存逐层解释

### 12.1 Tool schema 进程缓存

客户端按 release-local composite key 重用已构建的 schema object，减少本地重复转换。每次请求仍可能序列化工具 schema并计入输入 token。它优化 CPU/构造开销，不直接减少 API 接收的 token。

### 12.2 Model/client-data cache

持久 client-data slot 以 entrypoint、model、CLI version 和 organization 组合键保存，最多 12 项。精确 slot 超过 24 小时视为 stale；兼容 stale match 最长允许 7 天，并容忍 5 分钟未来时钟偏差。刷新会比较 account、model、pricing、access、organization default 和 auto-compact data，内容不变时跳过写入。

### 12.3 System prompt 分段 cache

system blocks会区分稳定和动态段，并在内部标记 `global`/`org`。只有 `global` 才在 wire 上显式写出 `scope:"global"`；内部 `org` 分支会省略 scope 字段。本版能证明 serializer 的字段形状，不能证明服务端如何解释省略值。provider、beta、base URL、overage 和 query source 不满足时回退到非 global/无对应 marker 分支。

### 12.4 Message breakpoint

客户端从消息尾部向前选择可缓存点：

- 跳过 `skipCacheWrite`；
- 避免把不可缓存 assistant tail 当稳定断点；
- 可以使用显式或推断的 fork pin；
- 将选中的 system/message block 序列化为 `cache_control`。

探针中默认请求真实出现 3 个 cache marker；设置 `DISABLE_PROMPT_CACHING=1` 后 marker 变为 0，而工具闭环仍能完成。

### 12.5 5 分钟与 1 小时 TTL

强制 5 分钟开关优先于 1 小时开关，之后还要经过 provider、overage、query-source 等 gate。TTL 改变写入价格和复用时间，不改变模型窗口容量。

### 12.6 LSP reconnect 修复的成本意义

`2.1.235` release note 明确修复 LSP disconnect/reconnect 让整个 prompt cache 失效的问题。LSP 在线状态属于动态机器信息，不应该污染稳定 prefix identity。

以本版 baked Sonnet `tier_3_15` 为例，每百万 token 的 5 分钟 cache write 为 3.75 美元，cache read 为 0.30 美元。若一段 1M token 稳定前缀原本因 reconnect 被重写，而新版保持一次读取，理论差额是 3.45 美元。真实节省取决于实际缓存 token、TTL 和服务端命中；客户端快照没有伪造账单结果。

## 13. Tool Search、Context Hint 与 Microcompaction

### 13.1 Tool Search

Tool Search解决“工具 schema 本身占满上下文”的问题。启用受 provider、settings、first-party base URL 和 beta gate 控制。延迟工具先暴露名称，取得完整 schema 后才能调用。

MCP工具表变化会推进 generation并使发现 cache 失效，但不会修改已经装配的请求。探针观察到 `tools/list_changed` 后重新 list，新工具没有进入紧接着的第二个 Messages 请求，到第三个请求才出现。

### 13.2 Context Hint

Context hint 只在特定 first-party 主线程路径使用，并要求 keep-recent 估算达到阈值。422/424、unsupported 400、409、529 和 stream error有不同 latch/fallback。它是向 API 传递治理提示，不等同本地删除内容。

### 13.3 Microcompaction

本地 microcompaction面向旧 tool result：保留最新配置数量，估算至少节省 20,000 token 才执行。持久化成功时用带路径的 `<persisted-output>` 短提示替换大结果；保存失败或不适合持久化时才退回 `[Old tool result content cleared]`。

它不总结整个对话，也不改变用户/assistant 主结论。目的在于清理高体积、低复用的工具输出，同时保留可追溯引用。

## 14. Auto-compact、预计算与手工 compact

### 14.1 四条阈值线

`2.1.235` 从有效输入预算计算不同阈值：

- compact reservation：`window - 13,000`；
- warning line：有效窗口再减 `20,000`；
- blocked line：输入上限再减 `3,000`；
- precompute line：还受 `precomputeBufferFraction` 控制。

`CLAUDE_CODE_AUTO_COMPACT_WINDOW` 优先于 settings、client-data、experiment 和 model default。阈值不是一个写死百分比；model window、dynamic config、output reservation 和输入上限都会改变实际值。

### 14.2 200k 窗口例子

若有效 input window 为 200,000 token：

- compact 参考线约为 187,000；
- warning 线还需按有效窗口减 20,000；
- blocked 线按输入上限减 3,000；
- precompute 会在 compact 前按 buffer fraction 更早启动。

具体 UI 显示仍取决于本轮工具 schema、system、附件、output reservation 和 model config，不能只用 transcript 字数判断。

### 14.3 Precomputed compact

预计算让 summary在真正触顶前后台生成。持久 summary需要通过 session、model、timestamp、boundary 和 preserved UUID 检查才能 rehydrate；版本、模型、边界或时效不一致会明确拒绝，避免把旧摘要换进错误消息链。

### 14.4 Manual compact

精确二进制 `/compact` 探针产生 `system:compact_boundary`，`trigger=manual`、`preTokens=104`。随后 fork 请求保留 compact summary和当前 prompt，移除 compact 前 prompt、旧 tool-use ID 和旧 assistant result。

这说明 compact改写的是下一轮送模结构历史，不是删除磁盘上一切事件，也不是清空 memory。

### 14.5 Reactive compact

请求因 context/image 过长失败时，Loop可以做一次 reactive compact后重建请求。`hasAttemptedReactiveCompact` 防止同一轮无限压缩重试。Auto-compact 连续快速 refill还存在 `rapid_refill_breaker`，避免反复总结却立刻再次触顶。

### 14.6 Compact 失败

总结 API失败时记录 trigger、耗时、preTokens 和错误，不创建成功 boundary。关闭 auto-compact并触顶时，`2.1.235` 改进了错误文案，直接指向 `/config` 恢复设置。

Compact减少窗口占用，但摘要可能丢细节；prompt cache减少重复前缀成本，但不释放窗口。这两个机制必须分开诊断。

## 15. Transcript、消息图、Resume 与 Fork

### 15.1 Transcript 不是普通聊天数组

主要消息带 UUID，通常还有 parent UUID。用户、assistant、tool、system、progress、attachment 和 compact boundary共同组成事件图。Fork、compact、恢复修链和保留消息会改变逻辑 parent，因此文件中的最后一行不一定是当前主链 leaf。

Resume大致需要：

1. 找到目标 transcript；
2. 逐行解析 JSONL；
3. 丢弃 malformed 或缺少合格 UUID 的记录；
4. 修复中断的 tool/message 配对；
5. 定位 compact boundary 和 preserved segment；
6. 选择当前 leaf/fork 链；
7. 恢复 session、checkpoint、task 和可持久 metadata；
8. 重新初始化本进程的 hook、tools、MCP、model 和 abort state。

### 15.2 Resume 恢复什么

精确二进制 probe恢复后，下一请求包含初始 prompt、初始 assistant result 和新 prompt。它证明同一 session逻辑历史被重建。

Resume不恢复旧进程中的：

- socket、Promise、AbortController；
- tool schema/model config内存 cache；
- 普通 shell 子进程；
- MCP server自己已丢失的远端状态；
- 已过期的 provider prompt cache；
- 未持久化 background job。

### 15.3 Fork 的身份语义

Fork从已有逻辑历史建立新 session ID。探针显示 fork保留 compact summary和新的 fork prompt，但身份与原 session分离。后续写入、leaf选择和继续执行不会再被当成同一 transcript主线。

### 15.4 Compact boundary 字段怎么读

Boundary可记录：

- `trigger`：manual、auto、reactive/precompute相关来源；
- `preTokens` / `postTokens`：总结前后估算；
- summary message和被总结消息数量；
- preserved UUID、logical parent和边界 UUID；
- 是否来自预计算及其验证信息。

它的作用是告诉恢复器“旧历史的哪一段已经被摘要替代”，而不是声明原 JSONL 已被物理删除。

## 16. File Checkpoint 与 Rewind

### 16.1 保存对象

File checkpoint保存 Claude Code已追踪文件在动作前后的可恢复状态，并用消息/动作身份关联。活跃恢复集最多保留 100 个 snapshot；增加新 snapshot会淘汰更旧项并记录结果。

### 16.2 正向探针

探针完成 Read/Edit 后执行独立 `--rewind-files`：

- 文件恢复为原始字节；
- rewind阶段没有新的模型请求；
- exit和恢复结果被固化在报告中。

这说明 rewind是本地文件补偿操作，不需要模型重新“想一遍”。

### 16.3 覆盖边界

File checkpoint不覆盖：

- Bash执行产生的任意外部变化；
- Git commit/push和远端分支；
- MCP/API/数据库写入；
- 子 Agent或外部程序未通过受追踪文件工具完成的变化；
- 链接路径和未纳入快照的文件；
- 键鼠、应用、部署、消息发送等外部副作用。

因此 checkpoint是有限补偿机制，不是 Agent Loop事务。

## 17. Memory、CLAUDE.md 与 Skills 的上下文预算

### 17.1 Memory 的不同来源

- 用户级 CLAUDE.md；
- 项目级 CLAUDE.md 和 rules；
- local workspace说明；
- auto memory目录及其 `MEMORY.md` 入口；
- skill/command/agent描述和按需正文。

这些来源的信任和持久范围不同。Checked-in project setting不能任意指定 `autoMemoryDirectory` 到不受信任位置。

### 17.2 `MEMORY.md` 前门预算

`MEMORY.md` 入口只加载前 200 行或 25,000 个 JavaScript UTF-16 code units，纯 ASCII 时约等于 25KB。目的不是限制 memory总目录，而是避免每轮把所有历史经验常驻上下文。详细内容应由入口索引到单独文件，再按任务需要读取。

### 17.3 Skill/command listing 预算

单个 description上限为 1536 字符，默认总 listing预算按 context比例控制。完整 SKILL.md正文通常按触发读取。技能越多并不意味着每轮都把所有正文发给模型；真正的常驻成本主要来自 listing、描述和未延迟工具 schema。

### 17.4 Memory 与 prompt cache 的区别

Memory是内容来源和持久知识；prompt cache是 API对相同输入前缀的计费/计算复用。Memory内容变化会导致请求和 cache identity变化，但二者不是同一种存储。

## 18. MCP：动态扩展如何进入 Agent Loop

### 18.1 配置与信任

MCP配置可以来自不同 settings层和项目来源。项目配置可能需要批准；strict config、allowed/disallowed tools、managed policy和 workspace trust共同决定是否加载。Settings parse error会让相关项目 MCP approval被跳过，并提示用 doctor诊断。

### 18.2 连接生命周期

```text
读取配置
  -> 信任/来源检查
  -> 建立 stdio/HTTP 等 transport
  -> auth/XAA/OAuth
  -> initialize/capabilities
  -> list tools/resources/prompts
  -> 转换为 Claude tool schema
  -> 进入 Tool Search或直接进入本轮 tools
```

连接成功不等于工具已经进入当前请求。工具表还需要完成 list、schema转换、generation更新和下一次请求装配。

### 18.3 动态刷新

`notifications/tools/list_changed` 会使 discovery cache失效并重新 list。刷新失败时保留旧工具表，避免一次临时 server错误立即清空所有能力。成功 refresh推动 generation，但当前已装配请求不会热更新。

### 18.4 MCP 工具失败

认证、transport、server、schema或调用错误最终映射为原 `tool_use_id` 的 error result。模型可以换参数、重新认证或选择其它工具。CLI不会在不了解外部副作用的情况下无限自动重跑写类 MCP工具。

### 18.5 Roots、resources 与 prompts

工作目录变化可通过 roots list_changed表达。Resources/prompts和 tools是不同 capability；不能只因为 server列出 resource就认为它已经成为模型可调用 tool。

## 19. Custom Agent、子 Agent、Team 与后台任务

### 19.1 Agent 定义

Custom Agent可以指定 prompt、工具、model/effort、permission和工作目录策略。内置 fork Agent默认可继承 model，并有独立轮次预算；本版静态路径显示 fork默认上限为 200 turns，并支持权限向上冒泡。

### 19.2 Context 隔离

子 Agent拥有独立上下文窗口。父 Agent通常只向 child发送任务和必要背景，child完成后压缩结果回父线程。这样可以隔离大量搜索/分析 token，但也产生额外 API调用、cache、tool和协调成本。

### 19.3 Task ownership

Team/task registry有显式 claim语义。已经被领取的任务返回 already-claimed分支，避免两个 Agent默默拥有同一任务。可靠协作还需要 task状态、owner、依赖和完成通知一致。

### 19.4 SendMessage

跨会话/Agent消息有大小限制。`2.1.235` 将超限行为从静默丢失改为发送前显式拒绝。模型收到失败后可以缩短、拆分或改用文件；没有 delivery/ack 的消息不会再伪装成功。

### 19.5 Mailbox 与完成通知

启动确认、消息送达和最终任务完成是三种事件。父 Agent先收到 async launch result，之后才从 task notification取得 child结果。状态机需要区分：

- 请求已接受；
- child已开始；
- child仍运行/等待工具；
- child完成或失败；
- 父 Agent已吸收并确认结果。

### 19.6 Background durability

当前官方资料说明后台 session可由独立 supervisor承载，但本版精确探针没有正向验证“CLI进程退出后真实后台任务继续并重连”。因此仓库把它保留为 Public主张，不升级为 `2.1.235` 本机 Probe事实。

## 20. Retry、Fallback 与恢复：七种“再来一次”

| 机制 | 重做对象 | 是否增加正常 turn | 副作用风险 |
| --- | --- | --- | --- |
| HTTP retry | 同一个模型请求 attempt | 通常不增加 | 工具尚未形成时较低 |
| stream -> non-stream | 同一逻辑调用的传输方式 | 不增加 | 已启动 tool block 时需谨慎 |
| model fallback | 换模型完成当前轮次 | 依分支 | 已完成工具可能重复 |
| `max_tokens` continuation | 截断的 assistant输出 | 独立 counter | 通常不重跑已配对工具 |
| malformed tool retry | 修复协议不一致 | 独立有界恢复 | 无完整 block时不执行 |
| reactive compact | 缩小输入后重建请求 | 不等同下一正常 turn | 请求前通常无工具副作用 |
| Stop hook re-entry | 带反馈进行新模型决策 | 增加 | 后续模型可能选择新动作 |

### 20.1 HTTP retry 分类

529/部分服务错误、连接中断、stale/idle/stall和 provider状态有自己的 retry/backoff。认证、无效参数、请求尺寸、计费和普通 4xx不会统一照搬相同次数。

### 20.2 Model fallback

探针中主模型连续三次 529，第四次请求切到配置的 fallback model并成功。顺序为 primary、primary、primary、fallback。这个结果只适用于该受控 overload路径。

Fallback会：

- abort未完成工具；
- 区分已完成、已 abort和从未启动的工具；
- tombstone丢弃的 provisional消息；
- 重建 streaming executor和消息视图；
- 记录 fallback模型和 usage。

### 20.3 Tombstone 不回滚副作用

Tombstone只表示某段 provisional assistant/tool消息不再属于有效主分支。它不会恢复文件、撤销 Git push、取消已经完成的 HTTP写入或收回已发送消息。Fallback前已完成动作必须靠动作身份、外部查询、checkpoint或补偿逻辑处理。

### 20.4 Stream fallback与部分输出

文本/thinking可以在 UI逐步显示，但 provisional显示不代表已成为稳定 transcript。只有完整 tool block才执行；传输切换后要按照 salvage/supersedes规则决定保留哪些内容和 usage归属。

### 20.5 Typed terminal reason

终止不只分 success/error。可观察类别包括 completed、max_turns、background_requested、tool_deferred、hook_stopped、aborted_streaming、rapid_refill_breaker、malformed/recovery耗尽和 API/model error。SDK调用者应解析 subtype、terminal reason、num_turns、usage、cost和permission denials。

## 21. TUI：视觉状态为什么会影响安全和正确性

### 21.1 输入状态

TUI维护“当前高亮项”和“提交时读取项”两份时序状态。`2.1.235` 修复快速方向键后立即 Enter仍提交旧 highlight的问题。这不是单纯渲染延迟，而是用户选择和实际动作不一致。

### 21.2 Permission dialog

Shift+Tab在 permission comment field中原本可能触发批准并授予 session-wide edit permission。新版让它只关闭/退出输入状态。Permission dialog还改进显示文本、实际 grant scope和 `don't ask again`的对应关系；内容无法完整显示时不提供持久授权入口。

### 21.3 Markdown 与高亮

- 深度 3 以上 nested list对齐；
- wrapped list item使用 hanging indentation；
- 多行 prompt的 mention/slash/highlight offset不再错位；
- Claude响应期间执行 slash command时，HTML entity恢复为真实字符。

这些修复减少“屏幕看见的文本”和“内部索引/提交内容”之间的分叉。

### 21.4 Vim 与 Panel

切换详细 transcript或关闭 panel后，Vim保持 NORMAL mode和 cursor位置。Session恢复时 open tasks的 expanded list状态也会恢复，而不是每次从 collapsed开始。

### 21.5 更新提示

后台 auto-update完成后，footer显示 `Update installed`并提醒重启。这个 UI状态需要跨后台任务更新保存，不能因为主界面重渲染而丢失。

## 22. IDE、VS Code、Remote Control 与 Cloud

### 22.1 IDE 上下文

IDE连接提供选区、打开文件、diagnostics、tab/panel和编辑器命令。该上下文随焦点变化，是动态 prompt信息，不适合无条件进入稳定 cache prefix。

### 22.2 VS Code 多 Panel

`2.1.235` 修复恢复/重载包含多个 Claude panel的窗口时，focus在 tabs间跳转。问题属于 extension panel identity和恢复时序，不改变 Agent Loop模型请求。

### 22.3 Remote Control

Remote Control有 endpoint、登录 entitlement、gateway availability、device/session ownership、连接、重连和 attachment生命周期。`claude rc` alias在 `2.1.235` 复用与交互启动相同的 enterprise-gateway availability gate，避免别名入口绕过前置环境判断。

自定义 endpoint负向探针中，doctor明确报告 Remote Control仅支持 `api.anthropic.com` 路径，并说明 feature evaluation受非必要流量开关影响。该 probe证明客户端诊断与阻断，不证明真实登录账户已成功完成 Remote Control连接。

### 22.4 Cloud session

`/ultrareview`、`/autofix-pr` 等后台 cloud task会持续接收事件。`2.1.235` 避免每次更新都重扫和重渲染完整 event stream，降低长任务的 CPU和内存增长。它优化客户端事件消费，不代表远端 worker本身更快。

### 22.5 Thin client 信任边界

Thin client可能采用 worker下发的 model、cwd、tools、MCP和 autocompact状态。正确实现需要验证 frame schema、ownership和允许字段；malformed frame应 fail closed。远端告诉客户端“有什么工具”不等于绕过本地 policy和 OS权限。

## 23. Settings、Feature Flag 与 Managed Policy

### 23.1 156 个根 setting不等于 156 个独立开关

Root schema记录字段类型、description、enum和嵌套对象，但每个字段的 merge语义、允许来源和生效时机要回消费者。常见类别包括：

- model/effort/output；
- permission、sandbox、network、filesystem、credential；
- MCP、plugins、skills、agents、hooks；
- context、cache、compact、memory、cleanup；
- telemetry、OTEL、debug、privacy；
- IDE、Remote、voice、UI；
- update、doctor、installation；
- enterprise managed-only字段。

### 23.2 Live reload

当前官方说明多数 settings可在运行 session中 reload并产生 ConfigChange。本版静态结构保留 settings watcher、source和迁移路径，但具体字段是否即时生效仍看消费者：有些重建 permission/tool context，有些只影响下一请求，有些需要重连/重启外部进程。

### 23.3 Feature flag 的证据等级

本版机器清单有 361 个静态 feature key、498 个 `et()` 调用点、6 个静态 GrowthBook config key 和 12 个 `CB()` 调用点。名称只能说明存在读取调用，不能直接证明默认值、账户 rollout或用户已获得功能。可靠结论需要同时满足 reader 类型、consumer branch、默认/fallback、policy/provider/surface/protocol gate 和运行证据。

在线 feature evaluation 还依赖一方事件通道：`DISABLE_GROWTHBOOK`、非一方 provider、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`、`DISABLE_TELEMETRY` 或 `DO_NOT_TRACK` 可以让在线求值关闭。显式 `CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF` 只允许一方 provider 在关闭在线流量时读旧磁盘值，不会让它变 fresh。

同步 reader 的实际可达顺序是 fresh memory -> disk cache -> baked default；disk cache 没有读取 TTL。gate reader 对 cached true 走快路径，对 false/缺失则可能阻塞初始化。默认 refresh 是 360 分钟；远端 cadence 以 5-360 分钟为基准并加 0.9-1.1 jitter，360 分钟向上的 jitter 会再封顶。

本版虽然导出 `CLAUDE_INTERNAL_FC_OVERRIDES` 相关 API，但 `getEnvironmentOverrides()` 在 parse 前提前返回，config override 读写也是 no-op。精确二进制把 `tengu_ccr_bridge` override 设为 true 后，doctor 仍报告 feature evaluation disabled、rollout 无法验证。它不能作为用户可用的强开入口。

### 23.4 Policy helper

管理员可通过 policyHelper/per-OS helper提供 policy。Refresh失败时，如果有静态默认则使用默认，否则保留当前 policy。这样临时 helper故障不会自动退回宽松空策略。

### 23.5 Managed permission lock

`allowManagedPermissionRulesOnly`启用时，只聚合 policySettings rules；CLI allowedTools和 session allow也会被替换为空 allow列表。它控制的是“哪些来源有资格放宽权限”，而不是只在最终结果上再叠一条 deny。

## 24. Telemetry：所有出口、默认值与字段含义

Telemetry不能概括成“会上报”。`2.1.235` 至少有一方 analytics、Datadog、OTEL、GrowthBook、error reporting、debug/profile和本地 recording等不同通道。

### 24.1 一方事件流水线

调用点先进入初始化前队列或运行队列，再经过采样、batch、认证和发送。内置默认值包括：

- 默认一方事件 endpoint；
- 每批最多 200 events；
- batch delay 100ms；
- 单个 exporter 实例当前连续失败周期最多 8 attempts；成功会把计数归零，进程重启也不会延续内存计数；
- quadratic backoff并受最大延迟限制。

发送失败的 batch可以写入文件或 storage-v5 stream，在下次启动重试。401还存在无认证 fallback配置路径。`H()`调用点数量不等于 HTTP请求数量。

### 24.2 Event envelope 怎么读

常见字段类别：

- session/query/request/model/provider身份；
- trigger、source、reason、outcome；
- duration、TTFT、waited_ms、late_by_ms；
- token、cache read/write、cost；
- tool name、decision、permission source；
- Agent depth、is_subagent、task/owner；
- error type/status/retry/fallback；
- platform/version/entrypoint。

字段是否出现取决于具体事件和隐私 gate。机器 inventory中的 `possible fields`是静态候选，不能假定每次 envelope都带齐。

### 24.3 采样、批量、落盘与重试

采样决定是否入队；batch决定何时合并；失败持久化决定进程退出前后的耐久；重试/backoff决定流量节奏。它们是四个不同阶段。关闭某一外部 exporter也不必然关闭一方事件或 debug log。

### 24.4 Datadog

Datadog使用固定 logs intake、batch常量和 event allowlist，并对部分字段删除/归一化。Allowlist表示哪些一方事件可以转发；redacted field表只约束 Datadog这条路径，不能代表 OTEL或一方 analytics的全部内容政策。

### 24.5 OpenTelemetry

`CLAUDE_CODE_ENABLE_TELEMETRY`是第三方 OTEL总 gate，metrics、logs、traces再独立选择 exporter。支持 console、OTLP、Prometheus以及 HTTP/gRPC等组合；signal-specific endpoint/protocol优先于 generic设置，headers可合并。

本版静态清单恢复出 8 个 metrics和 10 个 spans；structured logs/events还有独立调用点。名称、unit、description和 attribute需要结合对应 TSV/JSONL读取。

### 24.6 Prompt 正文隐私

OTLP探针启动本地 HTTP/JSON collector：

- 默认会收到 user-prompt event，但 `user_prompt` 为 `<REDACTED>`；
- 原 marker不存在；
- 设置 `OTEL_LOG_USER_PROMPTS=1` 后，第二次导出包含原正文。

这证明 prompt event和 prompt正文是两个开关层次。它不自动证明 assistant/tool/raw API内容共用同一 gate。

### 24.7 GrowthBook

Experiment evaluation可生成 experiment、variation、environment和可选 account/session属性，并复用一方 batch transport。Flag名和 variation只说明客户端观察到一次评估，不证明服务端 rollout的业务含义。

### 24.8 Error reporting

Error reporting要求 first-party authenticated路径，并经过 organization policy、version gate和 `DISABLE_ERROR_REPORTING`。它与普通 analytics、OTEL和本地 debug是不同通道。

### 24.9 本地诊断与录制

还存在：

- debug log和 diagnostics file；
- startup/query profiling；
- Perfetto/frame timing；
- heap/CPU/process telemetry；
- JSONL/SDK/PTY recording；
- crash/native module诊断。

看到 recording或 profile标识不等于默认上传。需要分别检查创建 gate、文件路径、retention和发送 consumer。

## 25. `2.1.235` 的 Usage-limit 遥测如何解释

本版一方事件把 usage-limit 自动续跑拆成一组可独立诊断的状态，而不是只记录一个“额度不足”结果：

- armed：已进入等待；
- cancelled：用户或状态取消；
- fired：到时触发，记录 early/rearm/waited_ms；
- stale：恢复太晚，记录 late_by_ms；
- stale_resumed：过期状态重新进入；
- offer/menu/setting changed：UI和设置决策。

其它细粒度事件覆盖 Remote Control pill、content block healing、device bridge reannounce/drain、goal check-in、bridge owner变化和 device/account绑定。

这表示观测状态更细，不表示传输和隐私门被放宽：telemetry endpoint、OTEL metrics/spans、Datadog tag/redaction和一方 environment字段数量均无变化。

## 26. 五个原生模块：JavaScript 到 macOS 的边界

### 26.1 共同运行模型

```text
bundled JavaScript wrapper
  -> require('/$bunfs/root/<module>.node')
  -> N-API function/object/prototype
  -> Rust或Swift runtime
  -> AppKit / ScreenCaptureKit / CoreGraphics / CoreAudio / Apple Events
```

`.node` 在同一进程地址空间运行。ABI mismatch、panic或 native crash可直接影响 CLI。JS wrapper决定 lazy load、fallback、参数归一化、错误映射和产品生命周期，因此只看 exports不够。

### 26.2 `image-processor.node`

导出 `processImage`、clipboard检查和 `ImageProcessor` prototype。对象支持 metadata、resize、jpeg/png/webp、toBuffer、dispose。

重要生命周期：

```text
input -> processImage -> 同一个 native resource
      -> resize/encode链式配置
      -> toBuffer 或 dispose
      -> consumed，后续调用报统一错误
```

固定 1x1 RGBA PNG双跑中，JPEG/PNG/WebP长度和 SHA-256与原版逐字节一致。内部 resize策略等兼容实现仍标 Derived/Compatible。

### 26.3 `computer-use-swift.node`

能力树覆盖 screenshot、apps、TCC、display、hotkey和 prepare capture。静态证据包含 ScreenCaptureKit、AppKit、CoreGraphics、Spotlight和 CGEvent tap。

微小合同：

- screenshot base64是裸 JPEG，不带 Data URL prefix；
- installed apps保留 Spotlight顺序和重复 bundle ID；
- Spotlight无法启动时 rejected Promise，不静默换文件扫描；
- icon重绘为透明 64x64 PNG；
- `appUnderPoint`可返回 Dock等覆盖窗口，结果不带 pid；
- Accessibility和 Screen Recording TCC与 Claude permission是两层授权。

### 26.4 `computer-use-input.node`

导出 key/keys/typeText、moveMouse、mouseButton、mouseScroll、mouseLocation和 frontmost app。保留 F1-F20、左右修饰键、媒体/亮度/Launchpad/Mission Control/numpad映射。

无副作用 probe验证参数错误和 Accessibility `NoPermission`，默认不主动注入真实键鼠。真实点击/按键一旦发生，message tombstone和 file rewind均无法撤销。

### 26.5 `audio-capture.node`

Rust/N-API路径保留 `napi-2.16.17`、`cpal-0.15.3`、`coreaudio-rs-0.11.3`。导出录音、播放、状态和 microphone authorization。CLI消费 16kHz mono signed 16-bit PCM。

初始 probe为 `{recording:false, playing:false, mic:0}`；播放启动后 `isPlaying=true`，停止后立即 false。重采样、静音阈值和内部 buffer policy属于兼容重建，不声明逐指令一致。

### 26.6 `url-handler.node`

使用 Apple Event `GURL`、direct object和 UTF-8 decode，提供 `waitForUrlEvent(timeout)`。无事件时 timeout返回 null，是正常结果，不应被解释成 native crash。

### 26.7 架构覆盖

ARM64上 5 个原版/兼容模块完成 contract。报告的 23 个检查项由 22 个真实原版/兼容对照和 1 个最低覆盖审计组成；22 个对照为 `14 exact`、`5 normalized-semantic`、`3 schema-and-invariants`，本次没有 `environment-boundary`。不能把覆盖审计也称为行为双跑。两个 Computer Use原版含 x86_64 slice，但兼容 x86_64尚未构建运行；其证据仅为静态 Mach-O归档。

## 27. 安装、更新与 Doctor

### 27.1 Native安装布局

Native安装将版本文件保存在 `~/.local/share/claude/versions/<version>`，入口符号链接指向当前版本。版本文件和内嵌 `.node` 必须成套，不能跨版本混装。

### 27.2 两个更新开关

- `DISABLE_AUTOUPDATER`：停止后台检查/安装，手动 update/install仍可存在；
- `DISABLE_UPDATES`：阻断包括手动命令在内的更新路径。

`DISABLE_UPGRADE_COMMAND`、`DISABLE_DOCTOR_COMMAND`只控制命令表面；`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`影响 update check/feature evaluation，但不等同管理员锁定全部更新。

### 27.3 设置迁移

旧 `autoUpdates:false`会迁移到 user settings的 `env.DISABLE_AUTOUPDATER=1`。成功后清理旧字段；失败时保留错误 telemetry和兼容状态，避免两个位置同时丢失。

### 27.4 Doctor 的故障域

Doctor分别检查：

- PATH、launcher、版本文件和旧 npm安装；
- OS/arch、native dependencies和 sandbox；
- update channel、写权限和 auto update gate；
- settings parse/schema/source conflict；
- workspace trust、MCP/helper/hook；
- provider/endpoint/credential；
- IDE、Remote Control和 feature evaluation。

隔离 probe中，doctor识别 native `2.1.235`、commit `ba01fa45e3d1`、`darwin-arm64`、bundled search、auto-update gate、损坏 settings和 Remote Control不可用原因。`DISABLE_UPDATES=1 claude update`输出管理员禁用提示并 exit 0；这里 exit 0表示策略被正常处理，不表示完成更新。

### 27.5 安装回滚与会话回滚不是一回事

- 安装 rollback：入口指回旧的完整版本文件；
- session resume/rewind：恢复消息或文件；
- Git rollback：恢复代码库；
- 外部系统 compensation：撤销 API/部署/消息。

旧 binary还可能不理解新 settings/transcript schema，所以回切后必须验证配置和会话兼容，而不是只看 `--version`。

## 28. `2.1.235` 的 19 条发布变化：逐项解释与证据强度

| # | 变化 | 解决的问题 | 用户影响 | 当前证据 |
| ---: | --- | --- | --- | --- |
| 1 | `spellcheck` setting | 输入缺少本地拼写反馈 | 默认关闭；外部 checker失败时会话内降级 | Release + Static |
| 2 | LSP reconnect不再使整段 prompt cache失效 | 动态状态污染稳定 cache identity | 降低重复 cache write与首 token延迟 | Release + Static机制；无真实账单 Probe |
| 3 | 深层 Markdown list对齐和 hanging indent | 终端层级/换行难读 | 输出结构更可靠 | Release + Static UI路径 |
| 4 | 多行 prompt highlight offset修复 | 显示位置与真实字符索引分叉 | mention/slash/高亮不再错位 | Release + Static UI路径 |
| 5 | Permission comment的 Shift+Tab修复 | 退出输入可能误批准 session edit | 消除权限范围误映射 | Release + Static；无自动键盘 Probe |
| 6 | Agent默认值修复 | 广告当前不可用的 general-purpose agent | 省略 type时列出真实可用 Agent | Release + Static |
| 7 | Notebook cell审批显示旧内容失败原因 | 审批人误以为旧 cell为空 | 权限决定有完整上下文 | Release + Static |
| 8 | 响应中 slash command HTML entity修复 | 显示编码与真实文本不同 | 命令结果可读 | Release + Static UI路径 |
| 9 | Footer保留 update restart notice | 后台更新完成但提示消失 | 用户知道需要重启 | Release + Static lifecycle/UI |
| 10 | Task list恢复 expanded状态 | Resume后任务面板假装初始态 | 长任务状态连续 | Release + Static session/UI |
| 11 | Cloud event增量消费 | 每次 update全量重扫/重渲染 | 长任务 CPU/内存更低 | Release + Static；无长时性能基准 |
| 12 | Permission dialog scope/text/persistent option对齐 | 展示和实际授权范围分叉 | 看不全内容时不提供长期授权 | Release + Static |
| 13 | Embedded grep病态 pattern和 `-m` context修复 | 高 CPU/错误上下文 | 搜索快速失败且上下文正确 | Release；未做精确 binary行为 Probe |
| 14 | Auto-compact关闭时 context错误引导 `/config` | 触顶后缺少恢复入口 | 错误可操作 | Release + Static |
| 15 | Vim mode/panel状态保持 | 打开关闭 panel重置模式/光标 | 编辑连续 | Release + Static UI |
| 16 | 快速 arrow + Enter使用新 option | stale highlight被提交 | 屏幕选择与动作一致 | Release + Static UI |
| 17 | `SendMessage`超限显式拒绝 | 跨会话消息静默丢失 | 模型可缩短/拆分后重试 | Release + Static |
| 18 | `claude rc`复用 enterprise gateway gate | alias入口检查不一致 | 企业环境诊断一致 | Release + Static + custom endpoint负向 Probe |
| 19 | VS Code多 panel恢复焦点修复 | tab之间抢焦点 | 多会话编辑稳定 | Release + Static extension路径 |

这里的 `Release` 表示 Anthropic明确将变化归入 `2.1.235`；`Static` 表示发布 bundle中可找到对应状态/分支或消费者；`Probe`才表示精确二进制已在受控输入下真实触发。没有 Probe的项目不会被包装成已完成运行验证。

## 29. 三个需要单独理解的根 Setting

本版根 schema 中，`spellcheck`、`autoContinueAtUsageLimit` 和 `syncClaudeAiSkills` 都有完整 consumer，但三者分别控制本地输入辅助、额度恢复和账号侧 Skill 同步，不能只按字段名推断行为。

### 29.1 `spellcheck`

对象字段包括 `enabled`、`checker`、`language`、`color`。只读取 user、flag和 managed settings，并取最高优先级来源的整个 block；project/local不参与子字段拼接。

默认关闭。`checker=auto`按 `aspell`、`hunspell`、`ispell`顺序找 PATH程序。检查器是长驻子进程；慢批次跳过，失败重启一次，连续失败只关闭当前会话，不阻断输入和 Agent Loop。它不把拼写结果发给模型，也不改变 token预算。

### 29.2 `autoContinueAtUsageLimit`

控制 claude.ai usage limit后的持久等待/自动恢复：armed、cancelled、fired、stale、rearm等事件表明它维护时间和过期状态，而不是简单 sleep。开启后进程/session可能更长时间存活；恢复仍遵守 transcript、permission和外部副作用边界。

### 29.3 `syncClaudeAiSkills`

本地只接受 `false`作为控制信号，`true`不能越过服务端账户 gate提前打开同步。User/managed false会停止下载并隐藏/清理已同步 skill；local/flag false只限制当前 workspace/invocation，不移动全局文件；project设置不读取该字段。

## 30. 关键字段字典：看到数据时应该怎样理解

### 30.1 Agent Loop 字段

| 字段 | 表示什么 | 常见误读 |
| --- | --- | --- |
| `turnCount` / `num_turns` | 模型决策轮次 | 误当 HTTP请求数 |
| request/attempt ID | 一次模型调用及其 retry | 误当用户会话 ID |
| `tool_use_id` | 模型动作和结果的关联键 | 只按工具名配对 |
| in-progress tool ID | 工具执行器仍拥有的调用 | 看到 UI卡片就当完成 |
| `stopHookActive` | 当前是否由 Stop hook重入 | 误当模型 stop reason |
| terminal reason | Loop最终停止原因 | 只看 exit code |
| `is_subagent` / depth | 当前 query属于哪条 Agent链 | 把父子 usage混在一起 |

### 30.2 Session 字段

| 字段 | 表示什么 |
| --- | --- |
| session ID | transcript身份 |
| message UUID | 单个持久事件身份 |
| parent UUID | 原始消息图父节点 |
| logical parent | compact/fork修链后的逻辑父节点 |
| leaf | 当前恢复主链终点 |
| compact boundary UUID | 摘要替换旧历史的边界 |
| preserved UUID | compact后仍保留的原消息 |
| checkpoint message ID | 文件快照与对话动作的关联 |

### 30.3 Cache/Context 字段

| 字段 | 表示什么 |
| --- | --- |
| `cache_control` | 请求中的 cache breakpoint/TTL标记 |
| cache read input tokens | 服务端报告的缓存读取量 |
| cache creation input tokens | 本轮写入缓存量 |
| `skipCacheWrite` | 当前候选不应产生写 marker |
| fork pin | 缓存断点对齐显式/推断 fork点 |
| `preTokens` / `postTokens` | compact前后估算 |
| effective input budget | model窗口扣除输出和保留后的输入容量 |
| context hint | 服务端上下文治理提示，不是本地删除结果 |

### 30.4 Permission/Tool 字段

| 字段 | 表示什么 |
| --- | --- |
| decision | allow/ask/deny等结果 |
| source/reason | 哪一层规则或用户动作产生决定 |
| updatedInput | hook修改后的工具输入，需要重新校验 |
| isError | tool result是否表达失败 |
| permission denial | SDK最终结果汇总的拒绝动作 |
| concurrency-safe | 是否允许与其它安全工具重叠 |
| endsTurn/deferred | 工具是否要求本轮终止或稍后继续 |

### 30.5 Telemetry 字段

| 字段 | 表示什么 |
| --- | --- |
| trigger/source/reason | 为什么进入该状态 |
| outcome | 成功、失败、取消、过期等结果 |
| duration/TTFT | 总耗时或首 token时间 |
| waited_ms/late_by_ms | 等待和过期程度 |
| model/provider | 请求选择与实际 serving归属 |
| cache read/write | 缓存成本结构，不等于窗口剩余 |
| content length | 可能仅保留长度，正文受独立 gate |

## 31. 常见误解与正确判断

### 31.1 “一个用户提示只请求一次模型”

错误。一个任务可能包含多次 Agent turn，每个 turn又有 HTTP retry、fallback、continuation或 compact请求。

### 31.2 “工具执行完，任务就结束”

错误。结果必须按 ID回灌，Loop还需处理剩余工具、hook、MCP变化、中途消息、maxTurns和下一次模型决策。

### 31.3 “Prompt cache减少上下文长度”

错误。Cache主要减少重复前缀计算/计费；compact和 microcompaction才改变活跃输入。

### 31.4 “Resume会恢复上一次进程”

错误。Resume重建持久消息图和可保存 metadata，不复活 socket、Promise、子进程和内存 cache。

### 31.5 “bypassPermissions可以绕过所有限制”

错误。它跳过 Claude Code交互审批层；sandbox、managed policy、OS权限、TCC和远端权限仍独立生效。

### 31.6 “Fallback会撤销失败模型做过的事情”

错误。它能 abort未完成工作并 tombstone消息，已完成外部副作用需要补偿或幂等处理。

### 31.7 “Feature flag名字就是已发布功能”

错误。还需要 consumer、默认值、账户 rollout或运行证据。

### 31.8 “重建 `.node` 就是恢复了原始源码”

错误。重建是满足观察合同的 Compatible实现；原始注释、局部名、文件结构和优化前算法没有留在二进制中。

## 32. 如何定位真实问题

| 用户现象 | 先看什么 | 典型层 |
| --- | --- | --- |
| 首 token突然变慢 | cache read/write、TTFT、LSP/MCP/plugin变化 | cache/provider |
| Context不长却触顶 | tool schema、附件、大 tool result、output reservation | context composition |
| Compact后质量下降 | summary、preserved UUID、pre/post token | compaction |
| 工具一直等待 | PreToolUse、permission duration、sandbox/MCP | control pipeline |
| 工具执行后模型没继续 | paired tool result、batch drain、maxTurns、Stop hook | Agent Loop |
| 同一写动作疑似重复 | attempt、fallback、tool ID、外部 idempotency key | recovery |
| Resume后工具消失 | MCP reconnect、generation、Tool Search | dynamic tools |
| 子 Agent只显示启动 | task notification和完成状态 | background Agent |
| 消息发送但对方没收到 | SendMessage size/error/ack | coordination |
| 遥测担心泄露 prompt | exporter、`OTEL_LOG_USER_PROMPTS`、通道级 gate | observability/privacy |
| Native功能失败 | module hash、N-API shape、TCC、display/device | native bridge |

## 33. 当前覆盖已经证实什么

### 33.1 静态覆盖

- 15个 packed文件和逐文件 hash；
- 71类 source inventory；
- 5个 native module、7个 slice和完整静态报告；
- 204,740,576字节 JSC bytecode；
- 211 条机制证据：146 Static、30 Probe、33 Public、2 Boundary；
- 52个能力面：51项 Deep、1项 Boundary；
- 93个归一化风险控制项；
- 156个根 settings、361个 feature flag候选；
- 29 项人工维护的核心终端 tool reference、80 个同工厂 AST 注册调用点（77 静态 name、3 动态 expression）、188 个 known-tool catalog 项；
- 31个 hook event；
- 17个 model entry、6个 pricing tier、4个 alias family。

### 33.2 精确二进制 Probe

11份运行报告覆盖，其中 10 份绑定精确 CLI 二进制，1 份用于原生模块原版/兼容对照：

- Agent Loop工具闭环、resume、manual compact、fork；
- bearer/API-key request shape和 prompt cache开关；
- PreToolUse deny、Stop hook重入、maxTurns；
- MCP generation refresh；
- Plugin Skill listing、launch acknowledgement 与正文注入；
- Plugin LSP stdio initialize/open/definition/shutdown、1-based 到 0-based 坐标和 paired result；
- 子 Agent隔离和两阶段结果回传；
- settings层级、529/400 retry、model fallback；
- OTLP prompt脱敏；
- filesystem/network sandbox；
- file checkpoint rewind；
- doctor/update gate和 Remote Control负向边界；
- 内部 feature override 不可达；
- 原生 contract、22项原版/兼容对照、0项环境边界和1项覆盖审计。

### 33.3 尚未形成正向 Probe 的部分

- 真实 Anthropic服务端 prompt-cache命中与账单；
- Bedrock、Vertex、Foundry等真实云凭据闭环；
- 登录账户的 Remote Control和 cloud orchestration；
- `2.1.235`多数 TUI/VS Code release fix的自动键盘/视觉回归；
- embedded grep病态 pattern和 context组合的精确 binary行为测试；
- x86_64 compatible native构建运行；
- CLI退出后的真实 background supervisor耐久。

这些缺口不会抹掉已完成的客户端静态与本地 Probe结论，但也不能被“validator PASS”替代。

## 34. 如何继续读证据

| 想解决的问题 | 深入文档 |
| --- | --- |
| 71 类机器清单怎样归属，哪些不能直接算产品功能 | [product-surface-evidence-map.md](product-surface-evidence-map.md) |
| 为什么 29 项核心参考之外还有 80 个注册调用点，工厂怎样展开，哪些会进入真实请求 | [tool-registration-and-host-surfaces.md](tool-registration-and-host-surfaces.md) |
| Brief 模式的主用户输出、附件和漏调修复怎样工作 | [brief-mode-and-user-visible-output.md](brief-mode-and-user-visible-output.md) |
| Agent为何循环、何时并发、为何停止 | [agent-loop.md](agent-loop.md) |
| Context、cache、compact和成本 | [context-governance-and-caching.md](context-governance-and-caching.md) |
| Session、fork、checkpoint、memory | [sessions-checkpoints-memory.md](sessions-checkpoints-memory.md) |
| 工具、permission、hook、sandbox | [tools-permissions-hooks.md](tools-permissions-hooks.md) |
| MCP、Agent、team、background | [mcp-agents-background.md](mcp-agents-background.md) |
| Retry、fallback、恢复与副作用 | [resilience-and-recovery.md](resilience-and-recovery.md) |
| Model、provider、auth、request | [models-auth-providers-request.md](models-auth-providers-request.md) |
| Settings、feature flag、policy | [settings-feature-flags-policy.md](settings-feature-flags-policy.md) |
| Feature evaluation、disk cache、refresh、exposure | [feature-flags-remote-config.md](feature-flags-remote-config.md) |
| 103 个 slash command 的 host、gate 与状态 owner | [slash-command-reference.md](slash-command-reference.md) |
| 31 个 Hook 事件的字段、阻塞与 timeout | [hooks-event-reference.md](hooks-event-reference.md) |
| 32 个 Storage namespace 的 key、写入、transcript 压实与 consumer | [storage-v5-reference.md](storage-v5-reference.md) |
| Workflow、Artifact、Design 的数据与发布边界 | [workflow-artifact-design.md](workflow-artifact-design.md) |
| TUI、输入、拼写、图片、语音、IDE、Chrome | [tui-input-accessibility-media-ide-chrome.md](tui-input-accessibility-media-ide-chrome.md) |
| 后台 task、Cron、Channel、Remote、Cloud 与 runner | [cloud-background-channels.md](cloud-background-channels.md) |
| Auto Mode 的权限前置层、两阶段 verdict 与 fail-closed | [auto-mode-classifier.md](auto-mode-classifier.md) |
| Plugin Eval 的 ablation、grader、费用与 Delta 可比性 | [plugin-evaluation-harness.md](plugin-evaluation-harness.md) |
| Daemon、PTY、worker、rendezvous 与 respawn 谁拥有状态 | [runtime-supervision-and-processes.md](runtime-supervision-and-processes.md) |
| Enterprise Gateway 的身份、策略、provider、spend 与 OTLP | [enterprise-gateway-runtime.md](enterprise-gateway-runtime.md) |
| Auth、账号、组织、订阅与 setup-token 怎样换代 | [auth-account-and-subscription-lifecycle.md](auth-account-and-subscription-lifecycle.md) |
| 首次启动、workspace trust、safe/bare/print 谁加载项目能力 | [onboarding-workspace-trust-and-safe-startup.md](onboarding-workspace-trust-and-safe-startup.md) |
| Thinking、Effort、Fast Mode 怎样进入请求并降级 | [thinking-effort-and-fast-mode.md](thinking-effort-and-fast-mode.md) |
| Token、美元成本、额度、credits 和自动续跑怎样串联 | [usage-cost-credits-and-limits.md](usage-cost-credits-and-limits.md) |
| Project purge、配置导入和会话归档为何会部分完成 | [project-purge-import-and-data-lifecycle.md](project-purge-import-and-data-lifecycle.md) |
| Sandbox 安装成功为何不等于命令真的被隔离 | [sandbox-install-and-runtime-enforcement.md](sandbox-install-and-runtime-enforcement.md) |
| Proxy、NO_PROXY、CA、mTLS 和 CCR relay 如何逐 transport 生效 | [network-proxy-ca-and-mtls.md](network-proxy-ca-and-mtls.md) |
| `/goal` 怎样通过 Stop hook 阻止过早结束 | [active-goal-and-stop-loop.md](active-goal-and-stop-loop.md) |
| Away recap、post-turn summary、suggestion、feedback 与 memory consolidation 有何区别 | [background-model-tasks-and-memory-consolidation.md](background-model-tasks-and-memory-consolidation.md) |
| Advisor 是否真的启动第二个本地 Agent | [advisor-dual-model-runtime.md](advisor-dual-model-runtime.md) |
| Ultrareview 在哪里审、在哪里修、什么时候才会发 GitHub 评论 | [ultrareview-cloud-review.md](ultrareview-cloud-review.md) |
| TUI、IDE、Remote、cloud | [tui-ide-remote-cloud.md](tui-ide-remote-cloud.md) |
| 安装、更新、doctor | [install-update-doctor-lifecycle.md](install-update-doctor-lifecycle.md) |
| Native bridge和兼容重建 | [native-bridge-runtime.md](native-bridge-runtime.md) |
| 遥测、日志、隐私、诊断 | [telemetry.md](telemetry.md) |
| 所有机器字段怎样读 | [inventory-field-guide.md](inventory-field-guide.md) |
| 公开资料与本版证据边界 | [public-claims-validation.md](public-claims-validation.md) |
| 每条 Probe命令和原始结果 | [runtime-probe-index.md](runtime-probe-index.md) |

## 35. 七个容易被清单掩盖的产品状态机

### 35.1 Slash Command：103 是静态集合，不是菜单数量

`2.1.235` 的 command object 分成 `local`、`local-jsx` 和 `prompt`。同名 command 还可能有 interactive/noninteractive/thin-client twin。判断一个命令是否可用，必须分别看：

1. parser 是否能解析；
2. 当前 host 选中了哪一个 twin；
3. `isEnabled`、`isHidden`、availability、feature、provider、policy 是否放行；
4. handler 是修改 App/session/settings/file/process/task，还是生成 prompt 进入 Agent Loop；
5. handler 返回后，状态是否真正持久化或由远端确认。

因此 `version`、`pause-memory`、`loops` 等保留 object/identifier 的命令不能自动写成当前可用；hidden、stub、host-only 和 remote-event-only 也必须单独标出。103/103 marker 证明集合未漏，不替代逐命令失败边界。

### 35.2 Hooks：前置控制与后置观察不能混写

31 个事件至少跨越 prompt、tool、compact、session、config/file、MCP elicitation、task/team/worktree 和 display/notification。共同 runner 之外，每个事件的时机、matcher 字段和阻塞语义不同：

- `PreToolUse` 在 permission/call 前，可 deny/defer/update input，timeout fail closed；
- `PostToolUse`、`PostToolBatch` 和 `PostCompact` 已处于副作用或状态变换之后，不能回滚；
- `Stop` 可让 Agent Loop 继续，但有连续阻止 cap；
- `UserPromptSubmit`、`ConfigChange`、`TaskCompleted` 等 exit 2 的对象不同；
- command、HTTP 和 MCP Hook 的可用事件、环境、输出和网络信任边界不同。

“配置了 hook”只证明配置存在；还要观察 matcher、runner 启动、timeout、exit/JSON 解析和调用方是否采纳结果。

### 35.3 Storage v5：namespace 不是自动事务数据库

32 个 Claude namespace 用 typed key 把 segment、scope 和允许形状固定下来；其中 `transcript`、`history`、`log` 是不能漏掉的流式入口。底层支持 atomic replace、in-place 和 append 等写入纪律，也有 expected stat/value/version 一类 precondition。它解决的是路径、key 与单次写入合同，不自动提供：

- namespace-wide lock；
- 跨 key transaction；
- 统一 migration；
- 统一 TTL/retention；
- consumer 的业务幂等。

更关键的是，本版 `tryCreateV5Backend()` 直接返回空。也就是说，storage v5 consumer 和 key contract 大量存在，但不能宣称普通本地 CLI 一定自行创建并启用 backend。`identity`、`recording`、`scratch`、`sessionLog` 等缺少足够 active consumer 的 namespace 保持 Boundary。

### 35.4 Workflow、Artifact、Design：三条链没有共享事务

Workflow 把自包含脚本、phase、agent call、journal、run/task ID 和同 session resume 绑定；`async_launched` 只证明运行已登记。Artifact 则把具体本地文件身份、hash/version、supporting files、CSP、远端 URL、comments/DB/assets/watch 绑定，发布批准针对 bytes，不只是路径字符串。Design Sync 再把本地 repo、build/diff/validate/capture、sidecar、远端 project 和 ownership 对齐。

三者可以串联，却不能共同回滚：Workflow 后续 phase 失败不会撤销已发布 Artifact；Artifact URL 不证明 Design project 已同步；远端 upload 成功也不会把本地 Git 状态自动变干净。

### 35.5 TUI、媒体、IDE、Chrome：输入不是一条字符串

Composer 持有文本、selection、Vim mode、permission comment、history 和 focus；renderer 还区分 alternate screen、screen reader、native cursor 和 diff strategy。Spellcheck 是受限本地子进程，有批量、缓存、字符过滤、timeout 和 circuit breaker。Paste 先做 gesture 分类，再按 MIME/bytes/扩展名走文本、文件、native image processor 或 clipboard fallback。Voice 是本地 capture + 远端 STT + 文本注入，不是直接把音频当普通 message。

IDE 与 Chrome 又拥有各自的 socket/token/selection/page/permission/timer state。断线、tool timeout 和迟到页面副作用是三种结果；permission dialog 可以暂停计时，却不能倒放已发生的浏览器动作。

### 35.6 Background、Channels、Remote 与 Cloud：显示端不等于执行 owner

本地 Bash/Agent 可由 task/supervisor 承载，Cron/loop/Monitor/Channel 只负责在请求边界排入新 input/notification。Remote Control 通常是远端看、本地 CLI 执行；cloud session、CCR/BYOC/self-hosted runner 才把 Agent Loop 或 workspace owner 放到远端环境。

所以关闭终端、关闭网页、resume transcript、停止 task、断开 viewer 的效果不同。`async_launched`、task metadata、Channel notification、remote event cursor 和 runner lease 也不是同一种完成信号。长 cloud task 在 `2.1.235` 使用增量 event cursor/owned state，减少重复扫描历史；它优化本地消费，不证明远端 worker 更快或更便宜。

### 35.7 Feature Flags：同版本差异来自状态链，不来自版本号本身

Feature manager 同时持有 fresh map、disk last-known-good、experiment metadata、pending/logged exposure、auth identity、generation 和 refresh loop。每个 consumer 还要继续通过 settings、policy、provider、command/tool surface 和协议门。

这套结构解释了四个用户现象：同版本不同账号不同；退出登录后 rollout 改变；关闭非必要流量后在线求值关闭；旧 disk true 在刷新前继续生效。它也解释了准确性边界：客户端可以证明取值和消费顺序，不能恢复服务端 targeting rule、账号实时值、entitlement 或实验分配。

## 36. Auto Mode：确定性规则之后的两阶段权限分类

Auto Mode 不是 `bypassPermissions` 的别名，也不是让模型接管全部权限。单工具仍先经过 deny、工具自身 safety check、ask、交互要求、组织级 ask ceiling 和 safety floor；这些层已经要求拒绝或询问时，分类器不能覆盖。只有普通 permission ask 才可能进入 Auto Mode。命中 `acceptEdits` 模拟或本地 safe allowlist 的动作可以直接放行，未命中者才构造 classifier transcript。

规则只从 `userSettings`、`flagSettings` 和 `policySettings` 聚合；项目和 local settings 中的 `autoMode` 会告警后忽略，防止仓库内容自行放宽权限。`allow`、`soft_deny`、`hard_deny`、`environment` 使用有位置语义的 `$defaults`：第一次出现时把 shipped defaults 插入该位置，没有 `$defaults` 就完全替换默认段。`classifyAllShell=true` 只在 Auto Mode 活跃时暂停 shell allow fast path，不会删除原规则。

默认 `twoStageClassifier="both"`。Stage 1 输出预算为 `64 + thinking overhead`，fast-only 时为 `256 + thinking overhead`，外层与 SDK timeout 都是 60 秒；Stage 1 allow 立即结束，block 倾向或无有效 verdict 进入 Stage 2。Stage 2 预算为 `8192 + thinking overhead`、外层 timeout 120 秒，可以推翻 Stage 1 的 block；但 API unavailable、XML parse failure、safeguard refusal 或最终无 verdict 时，普通工具 fail closed。此时的拒绝表示“没有可靠许可”，不等于模型已经证明动作危险。2.1.235 还有一条缺陷候选：Stage 1 已产生 usage 但无 verdict，随后 Stage 2 request 抛异常时，返回对象没有 `failureMode`/`unavailable`，后续误计为普通 denial 并编码成 `automode-blocked`；该 outcome 不能当作真实危险分类结论。

classifier denial 可触发 `PermissionDenied` Hook。`retry:true` 只向下一轮 Agent Loop 追加可重试提示，原始 tool call 没有执行；setup/apply 又使用 proposal、review 和内容 hash 绑定，防止交互确认后配置被换包。完整输入裁剪、repo visibility/git status 补充、Agent/AskUserQuestion/headless fallback、outcome kind、成本和隐私边界见 [Auto Mode 专题](auto-mode-classifier.md)。

## 37. Plugin Evaluation Harness：高分不等于插件有增益

`claude plugin eval` 先把 `case.yaml` 或 `prompt.md + graders/*.md` 编译成严格 schema，再对 case 目录、grader、plugin tree 做 inode/device、symlink、hardlink、owner、mode 和 containment 检查。`runs` 默认 3、最大 50；`max_turns` 默认 10、最大 200；`timeout_seconds` 默认 300、最大 3600。输入身份检查只能证明父进程执行的是刚审查的内容，不能把第三方 case 或 `scaffold_script` 变成可信代码。

有插件时默认执行 `with-without` ablation：with arm 保留 `pluginDirs`，without arm 只把它清空，其它 resolved case 合同保持一致。`with-only` grader 和默认的 `tool_used: Skill` 不进入两臂效果分母，避免把“基线没有插件工具”直接计成质量提升。没有真实 without arm、replay history 已带插件影响或两臂 grader 规则不同，就不能发布有效 Delta。

每个 run 使用新的 HOME、Claude config、Git workspace、trace 和 credential copy，以 `-p --output-format stream-json --permission-mode dontAsk` 启动同版 child。这里的 sandbox 是状态目录隔离，不是断网、容器或 OS syscall sandbox；获得 Bash、Write、WebFetch 或 MCP grant 后仍会产生真实副作用。费用 ceiling 在 run 开始前检查，所以最多可被一个已启动的 Agent run 越过；之后付费 grader 被跳过、suite 标记 `partial_reason=cost_ceiling`。

六类 grader 分别是 regex、tool order、tool used、file exists、LLM 和 baseline。LLM/baseline 各发 3 次独立 judge，2/3 多数决定 PASS；grader 异常按失败计入，不从平均值消失。完整 suite 达阈值 exit 0，质量/case 错误 exit 1，cost ceiling 或 auth failure partial exit 2；SIGINT/SIGTERM 即使报告仍写 `partial=true, partialReason=interrupted`，最终 shell exit 也分别是 130/143。JSON、HTML 与可选私有 publish 保留每次 run、evidence、judge votes、费用和 Delta。完整合同见 [Plugin Evaluation Harness](plugin-evaluation-harness.md)。

## 38. Runtime Supervision：后台存活、可连接与任务完成是三件事

后台运行至少有六个 owner：Agent View 负责展示与控制，daemon supervisor 持有 worker roster/PID/phase/respawn，PTY host 持有 Bun.Terminal、socket 和输出 ring，Claude worker 持有 Agent Loop/tool/transcript，rendezvous 传 heartbeat/state/reply，Storage V5 job record 保存可恢复业务投影。`running` 只是派生状态；它既不保证模型正在生成 token，也不保证 PTY 可 attach。

企业 `processWrapper` 来自环境或受信 settings，按 argv 解析而不经过 shell；launcher 必须是绝对路径、regular executable，并且必须 `exec` 进入 Claude。配置存在但失效时 self-spawn fail closed。worker 在 12 秒内出现“launcher exit 0 但 Claude 尚未 ready”会被判为 fork-and-exit 违规，避免 wrapper 自己退出后留下无法监督的后继。

PTY host 为新 attacher 回放最近 `256 KiB`，单客户端 writable queue 超过 `1 MiB` 就断开；60 秒 ping 连续漏 3 次只回收该连接。Unix orphan watchdog 每 2 秒检查 parent/client，连续 30 次无 owner 后先 `SIGTERM` child，5 秒仍不退出再 `SIGKILL`。PTY auth 与 rendezvous auth 各使用 16 random bytes hex token，Unix 优先通过 mode `0600` 一次性文件交付。

异常退出后 supervisor 先查 job 是否 settled、cwd 是否存在、transcript 能否 resume，再等待 10 秒 respawn，最多 20 attempts；3 次在 5 秒内 fast crash 会提前终止，稳定 5 分钟后 attempt budget 可重置。rendezvous 120 秒无 heartbeat 只记录 stalled 证据，不等同立即杀进程。空闲至少 30 分钟且主循环不忙的 local background Bash 可被 memory-pressure reap；`asyncRewake` command Hook 只有 exit 2 才以 Stop-hook feedback 唤醒下一轮。完整状态和故障定位见 [Runtime Supervision](runtime-supervision-and-processes.md)。

## 39. Enterprise Gateway：身份、策略、上游凭据与计量的独立运行时

`claude gateway --config` 只在 native Bun binary 中运行。启动先严格展开 YAML 的 `${ENV_NAME}` 与绝对路径 `${file:/...}`，拒绝未知 key 和旧 `dev:` 配置；随后连接 Postgres、获取 advisory lock 并迁移，再构造 admin/spend、session key ring、可选 CRI authenticator/JWKS、policy webhook、OIDC、provider clients、managed policies 和 TLS。除 CRI JWKS prime 可降级外，构造失败都阻止 listen。

普通开发者先走 RFC 8628 device flow 和公司 OIDC，Gateway 校验 code/PKCE/nonce/browser binding 后签发自己的短期 HS256 session JWT，不把 IdP token 直接交给 CLI。默认 device grant 有效 10 分钟，Gateway session TTL 1 小时。CRI 则使用外部 Anthropic `cri+jwt`，固定验证 issuer、JWKS、audience、org、scope，只能进入 inference path，不能读取 managed settings、spend admin 或 Gateway OTLP。

请求顺序是 IP deny、health/readiness、IP allow、URL/header/body limits、公开 OAuth、admin 特殊认证、session/CRI admission、endpoint dispatch、session spend precheck、JSON/CRI webhook、model allowlist/mapping、顺序 upstream failover、response hygiene 和成功 usage metering。admin 路径中 `x-api-key` 一旦出现就不再回退 bearer；用户 Gateway token 在身份墙被消费，上游看到的是 operator credential。Anthropic、Bedrock、Vertex、Foundry 等模型名因此可映射到不同 provider ID，但云 IAM、配额和内容审核仍属于外部系统。

默认请求体上限 32 MiB、Postgres pool 5、upstream TTFB 120 秒；spend 在 75%/95% 提示并在 cap 处返回 `billing_error`。CRI JWKS fetch 10 秒、默认 10 分钟刷新、6 小时 hard age、unknown-kid 1 分钟 cooldown；webhook 默认 2 秒且 fail closed。OTLP 对客户端立即 200，再以 128 in-flight、连续 5 次失败开路 30 秒、destination timeout 10 秒后台 fanout，所以 Collector 故障不阻塞 CLI，但可能丢观测数据。完整 endpoint、YAML、Postgres schema、provider 错误映射、CRI hygiene、retention 和安全边界见 [Enterprise Gateway Runtime](enterprise-gateway-runtime.md)。

## 40. Auth、账号、组织、订阅与 setup-token

`claude auth login`、交互式 `/login` 和 SDK `claude_authenticate` 共享账号换代核心，但入口合同不同。成功路径不是“拿到 OAuth token 就结束”：客户端先裁决登录方式和组织约束，再取得 OAuth/token，隔离旧账号派生状态，保存凭据，按 subscription scope 获取派生 API key/角色信息，最后校验组织并刷新账号、feature、Remote Control 等运行时 cache。真正的提交点是新身份已持久化且当前进程的派生状态已换代。

`setup-token` 生成的是长寿命凭据，不是普通网页登录的别名。Logout 则区分远端 refresh-token revoke、本地 credential wipe 和进程 cache 清理；远端撤销失败不会阻止本地退出，但也不能证明旧 token 在服务端已失效。认证材料的来源、文件权限、组织强制登录、订阅类型和 remote entitlement 必须分开诊断，详见 [Auth、账号与订阅生命周期](auth-account-and-subscription-lifecycle.md)。

## 41. Onboarding、Workspace Trust 与安全启动

首次 onboarding 解决账号和客户端准备，workspace trust 解决当前项目是否能把 settings、hooks、MCP、skills、commands、agents、目录扩展或 helper 带入运行时。信任扫描不只看 `.mcp.json`；它会归纳可执行命令、网络/凭据 helper、权限预授权、额外目录等风险。接受后必须重新发现项目定制，不能只把一个布尔值翻为 true；拒绝则保留基础 CLI，但不让项目内容在确认前进入执行面。

`--safe-mode`、`--bare` 和 `--print` 缩小的是不同层：safe mode 保留认证、模型、内置工具、权限和 policy，却关闭多数项目定制；bare mode 跳过更多自动发现和后台设施，但仍可接受显式输入；noninteractive 没有 trust dialog，因此调用方承担更严格的预信任责任。准确装载矩阵、persisted/session trust 和撤销边界见 [Onboarding 与 Workspace Trust](onboarding-workspace-trust-and-safe-startup.md)。

## 42. Thinking、Effort 与 Fast Mode

Thinking、Effort 和 Fast Mode 是三条控制轴。Thinking 决定请求是否带扩展思考以及采用 adaptive/显式预算等形态；Effort 是模型工作强度，受模型能力、组织上限、launch pin、session setting 和兼容性 latch 共同决定；Fast Mode 请求高速度服务通道，可能伴随模型切换，但仍要通过账号、policy、provider 和 session opt-in。UI 显示开启只代表本地意图，request builder 会在每次请求前重新裁决。

本版还会在特定 400 后对不兼容 effort 建立 session latch，在 Fast Mode 遭遇 429/529 后进入冷却并回退普通通道。`effort_cost_index` 是本地估算维度，不等于服务端真实账单。字段优先级、thinking 与 `tool_choice` 的约束、组织状态预取、成本和恢复路径见 [Thinking、Effort 与 Fast Mode](thinking-effort-and-fast-mode.md)。

## 43. Usage、成本、Credits、Limits 与自动续跑

每次响应的 input/output/cache token 先进入本地 `modelUsage` 和 session cost 账本；价格来自模型目录/动态价格并受 Fast Mode、Advisor 等路径影响。额度状态则来自响应 header 和 `/api/oauth/usage`，它描述 session/weekly 等 account limit，不是美元成本的另一种显示。客户端用 identity/generation 防止旧账号的异步 usage 结果污染新账号。

接近限制时，客户端按多级阈值显示 warning，并在 grace window 插入 wrap-up/checkpoint 提示；被额度拒绝后，满足设置和状态 gate 才会 arm auto-resume。reset 到点时排入一条“继续但不要重复工作”的虚拟用户消息，而不是重放最后一个工具调用。用户输入、session 状态变化、过期时间和 rearm cap 都能取消或抑制它。credits 购买/分配属于独立账号流程，完整状态机见 [Usage、成本、Credits 与 Limits](usage-cost-credits-and-limits.md)。

## 44. Project Purge、配置导入与会话归档

`claude project purge`、`claude import` 和隐藏的 conversation import 没有共享一个事务引擎。Purge 先建立项目状态计划，按 transcript 归属、Storage/history 和 prompt history 分别删除或过滤重写；Config import 先扫描 Codex/Gemini 等输入，映射可支持项并用 digest 绑定 preview 与 apply；Conversation import 对 JSON/ZIP 做体积、条目、路径和 no-overwrite 约束，再写文件并在最后核对 manifest。

共同风险是确认后的执行采用顺序副作用：中途失败不会自动撤销先前成功项，manifest mismatch 甚至发生在文件已落盘之后。Preview 能做到零写入，digest 能发现 TOCTOU，却不提供跨文件事务。输入护栏、文件模式、恢复动作和隐私边界见 [Project Purge、Import 与数据生命周期](project-purge-import-and-data-lifecycle.md)。

## 45. Sandbox 安装态与运行态

Windows `claude sandbox install/status` 回答宿主依赖和隔离用户等长期对象是否准备好；Agent Loop 的 sandbox wrapper 回答本 session、这一条 command 是否真的被约束。`installed:true` 只证明安装检查通过，不证明当前设置启用 sandbox，也不证明该工具路径经过 wrapper。运行时还要通过 platform、policy、setting、工具 eligibility 和 `dangerouslyDisableSandbox` 等 gate，并在 session 中懒初始化、合并并发初始化请求。

同样，CLI 最终 exit 0 只说明它成功处理了工具结果，不能代替检查 Bash/tool result 和外部文件/网络状态。Session cleanup 会释放进程级资源，却不等于卸载长期依赖或回滚已产生副作用。两条状态机、UAC/退出码、ACL、fallback 和 exact-binary 负向 Probe 见 [Sandbox 安装与运行 Enforcement](sandbox-install-and-runtime-enforcement.md)。

## 46. Proxy、NO_PROXY、CA 与 mTLS

Claude Code 没有一个覆盖所有网络调用的万能代理开关。主请求/通用 fetch、Axios/undici、WebSocket、AWS SDK、MCP transport、OTLP exporter 和 CCR 子进程分别选择 adapter；`NO_PROXY` 也存在不同匹配器。主模型能联网只证明其 transport 已通过 proxy，不证明 MCP、云 SDK、后台 Agent 或遥测能走同一路径。

TLS 又分服务端信任和客户端身份：CA store 组合 bundled/system/extra CA，并过滤过期系统证书；mTLS cert/key 要成对校验并在 stale connection 时重载。CCR agent proxy 是只接受 HTTPS CONNECT 的本地 policy relay，带有 allowlist、流控和兼容性边界，不等于任意直连。逐 transport 的优先级、407 helper refresh、证书轮换和排障顺序见 [Proxy、CA 与 mTLS](network-proxy-ca-and-mtls.md)。

## 47. Active Goal 与 Stop-loop

`/goal` 把目标注册为 session-scoped `Stop` prompt hook。正常工具执行期间不会每一步都另开一次目标检查；只有主 Agent 准备结束时，hook 才让模型判断目标已满足、未满足或不可能。未满足会把原因回灌消息图并开启下一轮，满足或不可能才清除目标，因此“模型说做完了”和“运行时允许结束”是两层状态。

连续阻止有 cap，避免错误目标或评估让 Agent Loop 永久重入。后台任务运行、特殊终止、SDK/Remote projection 还会临时拆下或忽略 blocking 结果；这些分支不会撤销已经发生的文件、命令或远端副作用。完整 gate、状态字段和失败路径见 [Active Goal 与 Stop-loop](active-goal-and-stop-loop.md)。

## 48. 后台模型任务与 Memory Consolidation

Away Summary、Post-turn Summary、Prompt Suggestion、Feedback Draft 和 Auto Dream 不是一套“后台总结”。前三者主要生成短暂 UI/协议状态，Feedback Draft 只在本地排队并等待用户确认上传；只有 Auto Dream 会 fork 一个受限 Agent，读取历史 session 和 memory Markdown，并真实改写持久记忆。默认触发还受 24 小时、至少 5 个 session、10 分钟扫描等 gate 和跨进程 lock/CAS 保护。

Prompt Suggestion 要求至少 2 个 assistant turn，上一轮 usage 超过 10000 时会以冷缓存成本为由抑制，结果还必须满足 2-12 words、少于 100 chars、单句、无 Markdown 等产品过滤。`skipTranscript`/`skipCacheWrite` 不等于没把上下文发给模型或没有 token 成本。五种机制的 owner、持久化、取消与隐私边界见 [后台模型任务与 Memory Consolidation](background-model-tasks-and-memory-consolidation.md)。

## 49. Advisor 双模型运行时

Advisor 不是客户端并行启动第二个本地 Agent Loop。每个 API attempt 会重新检查 feature/provider/model catalog，并选择等级不低于当前执行模型的 advisor；满足条件时，把 `advisor_20260301` 作为 server tool 加进同一个 Messages 请求。主模型按需调用，服务端执行咨询并在同一 stream 中返回 `advisor_tool_result`，客户端只负责协议组装、流解析、显示与持久化。

因为 fallback 可能切换执行模型，advisor 组合必须按 attempt 重算。关闭 Advisor 或目标服务不支持时，wire view 会 strip 历史 server-tool blocks；特定 400 还能触发 `retry:advisor-strip`，但本地 transcript 原始事实不被删除。Advisor 会额外读取会话、消耗 token 和增加等待；其服务端 prompt、调度和计费细节保持 Boundary。详见 [Advisor 双模型运行时](advisor-dual-model-runtime.md)。

## 50. Ultrareview 云端审查

`/ultrareview --fix --post` 先经过账号、策略、Git identity、repo/scope、diff 规模、quota 和费用确认，再为 PR ref 或本地 branch bundle 创建有资源上限的 cloud session。Scope builder 拒绝错误 repo、缺失 merge-base，以及超过 500 files/8000 lines 的 diff；云端返回 findings 前不会直接改本地工作树。

`--fix` 在 findings 回来后交回本地主 Agent Loop，因此仍经过工具、permission、hook 和 sandbox；`--post` 则启动受限 routine，只允许一次 `add_issue_comment`，发布的是 plain PR comment，不是 approve/request-changes/merge。独立 CLI 默认等待 30 分钟、每 3 秒 poll、最多容忍连续 5 个连接错误；Ctrl-C 只停止本地等待，远端任务继续。Post consent 不跨恢复保留，网络 timeout 后也不会盲目重发，以避免重复外部评论。详见 [Ultrareview 云端审查](ultrareview-cloud-review.md)。

## 51. Brief Mode：普通 assistant text 不等于用户已经收到

Brief Mode 改变的是输出所有权，不是把回答自动缩短。`--brief`、`CLAUDE_CODE_BRIEF`、`defaultView=chat`、`/brief` 和 TUI toggle 最终汇入 `isBriefOnly`，但还要通过账号 entitlement、host/session 状态和工具装配，`SendUserMessage` 才会进入当前工具集合。普通 assistant text 仍会进入 transcript/detail；brief 主视图把 `SendUserMessage` 的 tool use/result 当作主要用户消息，因此“模型已经写了文字”和“用户主视图已经收到”是两种状态。

`SendUserMessage` 输入包含 Markdown `message`、`normal/proactive` status，以及本地路径或预上传对象附件。本地路径会拒绝 URL、UNC、`/net`、非 regular file 和不可访问对象；客户端再按 REPL、Brief env、CCR、BYOC、hosted SDK 或 local-only 条件选择 lane。所有允许上传的 lane 共用 `uploadBriefAttachment -> /api/oauth/file_upload`，lane 主要控制跳过、本地 fallback 和遥测标签，不是已证明的不同 transport。多附件并行且允许部分成功：正文可能已经送达，但部分附件只在当前桌面可见，或因没有本地兜底而让 tool result 带 `is_error:true`。HTTP `201` 与 `file_uuid` 只证明客户端认定上传成功，不证明任意 remote viewer 已渲染；该 error 只描述附件交付不完整，不撤销已经显示的正文。

如果主线程或 SDK 的 brief turn 完全没有调用 `SendUserMessage`，客户端会在 turn end 最多插入一次 `You ended the turn without calling SendUserMessage.` meta message，让 Agent Loop 再给模型一次补发机会；sentinel guard 防止同一漏调无限循环。切换 transcript 只是改变 view projection，不删除历史；已经发出的消息、上传的附件和通知也不能被 compact、resume、tombstone 或 rewind 撤销。完整入口、schema、renderer、上传结果和证据范围见 [Brief 与用户可见输出](brief-mode-and-user-visible-output.md)。

## 52. 最终准确性边界

这份说明书能够确定 `2.1.235` 客户端发布物中的调用链、状态、schema、请求装配、本地工具控制、持久化、恢复、遥测出口、原生合同和受控 Probe行为。

以下对象没有存在于客户端发布物中的完整实现证据：Anthropic服务端路由、账户 abuse/risk score、真实缓存命中算法、隐藏 feature rollout、远端容量调度、模型内部推理、发布基础设施和构建前源码。它们保持 Boundary，不用客户端 header、事件名或字符串替代服务端事实。

`2.1.235` 的核心机制已经可以从“用户输入”一直追到“请求、工具、副作用、结果回灌、compact、resume、遥测和终止”。后续版本比较必须沿同一生命周期逐项比较状态、默认值、阈值、失败、成本和证据，而不是只比较 bundle大小、字段数量或 minified symbol。
