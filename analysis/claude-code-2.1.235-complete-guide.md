# Claude Code CLI 2.1.235 完整机制说明书

这份文档只讲 `2.1.235`。它把分散在 Agent Loop、上下文治理、会话恢复、权限、MCP、遥测、原生桥接和发布差异专题中的结论重新组织成一条完整运行链，目标是回答三个问题：Claude Code 到底在本机做了什么；每一层状态怎样进入下一层；用户为什么会看到某种性能、费用、权限或恢复结果。

本文不是字段清单，也不把当前官网行为直接倒灌成 `2.1.235` 的事实。每个重要结论分别依赖以下证据：

- **Static**：`2.1.235` 发布 bundle、可读化 JavaScript、Mach-O、schema、常量或可达分支；
- **Probe**：SHA-256 固定为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748` 的精确二进制在隔离环境中的真实输出；
- **Public**：抓取并固化 hash 的 Anthropic 官方说明，用来解释设计目的或提出验证假设；
- **Boundary**：客户端发布物中不存在的服务端实现、账户状态、隐藏策略或构建前源码。

结构化证据在 [mechanism-evidence.jsonl](mechanism-evidence.jsonl)，逐项命令、输入、输出、退出状态在 [runtime-probe-index.md](runtime-probe-index.md)。本文负责把这些证据讲成人能沿着生命周期理解的系统。

需要查全量表面时，不要在本卷里翻零散提及：先读 [2.1.235：不是 Agent Loop 重写，而是一次状态边界修正](product-surface-evidence-map.md)。要理解用户一句话怎样变成最终请求，读 [Prompt Assembly](prompt-assembly-and-system-reminders.md)；要判断内容留在本机还是发往模型、遥测、Remote、Feedback、MCP/Hook、Artifact或Voice，读 [全局数据流与隐私](client-data-flow-and-privacy.md)。精确的71类inventory、347条claim、三轴证据分类和未完成consumer tracing单独放在[机器证据索引](product-surface-inventory-index.md)。[全面性审计](completeness-audit.md)现在明确区分55项Deep、2项Documented与1项Boundary，不再把IDE extension和updater事务的证据缺口写成“全部Deep”。工具、Settings、CLI/SDK、Slash Command、Hook、Storage及高价值状态机继续由对应专题提供精确集合、生命周期和失败合同。

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
  -> 完整 client tool_use 出现后启动本地工具
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

### 6.7 Prompt Assembly 的真正顺序

上面六节列出了对象，但不能替代调用顺序。目标版实际先构造top-level system、userContext、systemContext和本轮tools，再从transcript message graph选择有效链；每轮还把文件变化、Memory、Skill、MCP/Agent目录、Plan/Auto、IDE/LSP、task/queue和Hook结果并行生成为typed attachment。发送前attachment才被渲染成`isMeta` user reminder，支持时可提升为mid-conversation `role:"system"`；role/tool pair normalizer和cache marker随后才运行。

`<system-reminder>`因此是动态状态的发送编码，不是内部唯一存储格式，也不等于所有内容都获得API system authority。`readFileState`还把Read/Edit/Write和外部文件变化接到这条链；compact会按5个文件、单文件约5k token、总50k等预算重建文件/Skill/task/MCP/Hook附件。完整顺序、失败降级和证据行号见 [Prompt Assembly专题](prompt-assembly-and-system-reminders.md)。

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

本版 inventory 中共有 99 条 API path 和 53 个日期后缀 Beta，但字符串存在不等于产品层调用：有些属于 Claude Code 直接 consumer，有些是发布物内 Enterprise Gateway handler，有些只是打包 SDK、prefix/allowlist 或内嵌迁移参考。Beta 还要经过 descriptor、模型/provider/feature/query-source/sticky gate、云 provider 改写和定向 400 strip，不能把 53 个标识写成“每次请求都会发送”。逐项 owner、method/path、consumer、失败与远端边界见 [API、Beta 与路由所有权](api-beta-route-ownership.md)。

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
8. 完整 client tool_use block 到达后立即排入工具执行器
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

精确二进制 `/compact` 探针产生 `system:compact_boundary`，`trigger=manual`、`preTokens=104`。这里的 `104` 只是该 Probe 输入下 boundary 记录的观测值，不是自动 compact 阈值，也不能推出 2.1.235 存在固定的 compact token 触发线。随后 fork 请求保留 compact summary和当前 prompt，移除 compact 前 prompt、旧 tool-use ID 和旧 assistant result。

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

本版机器清单有 361 个静态 feature key、498 个 `et()` 调用点、6 个静态 GrowthBook config key 和 12 个 `CB()` 调用点。全部 Feature callsite 已绑定 lexical function 与 immediate AST consumer；其中 205 个 key 完成人工 consumer 收口，55 项结构化合同进一步锁定 58 个精确调用点，剩余 156 个仍是 Semantic follow-up。环境侧同样不是“有字段就算懂”：411 个静态名称完成 consumer 合同，104 项结构化合同锁定 122 个调用点，502 个继续待追。

名称、parser 和 export 仍不能直接证明用户行为。一个典型反例是 `tengu_ant_yolo_equiv_strip_config`：`lKS` 能解析 `enabled/includeEntrypoints/excludeEntrypoints` 并被导出，但 `2.1.235` bundle 内没有 caller，Auto Mode 初始化处也没有消费该 predicate，因此它没有被晋级为 Static consumer。可靠结论需要同时满足 reader 类型、可达 consumer branch、默认/fallback、policy/provider/surface/protocol gate 和运行证据。

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
- Perfetto bridge/integration surface（recorder/file 未观察）与 frame timing；
- heap/CPU/process telemetry；
- JSONL/SDK/PTY recording；
- crash/native module诊断。

看到 recording或 profile标识不等于默认上传。需要分别检查创建 gate、文件路径、retention和发送 consumer。

需要从事件下钻时，使用 [遥测场景语义索引与逐事件证据](telemetry-event-catalog.md)：先按 API attempt、工具权限/执行、Permission UI、reactive compact、session、MCP、后台任务、登录、错误终态和 transcript 写入恢复解释事件先后、owner、字段和成功/失败含义，再逐项覆盖 1,441 个静态一方事件、43 个动态名称调用点、181 个 Datadog allowlist、26 个 OTEL 事件、8 个 metrics 和 10 个 spans。原 family `tengu_other` 的 911 event / 1,297 callsite 当前只接受 140 条 exact caller identity，完整收口 19 Single-owner、1 Cross-owner；891 event / 1,157 callsite 保留 Unresolved。每条命中还绑定局部状态变化与 Boundary；这是 Derived 客户端 owner 投影，仍不等于分支运行、采样命中、外部副作用完成或远端送达。需要从异常或日志文本下钻时，先用 [错误与诊断机制图谱](error-diagnostic-atlas.md)理解 abort、重试、tool result、stderr/TUI、LSP attachment、Hook、telemetry 与副作用恢复链，再进入 [Error/Diagnostic 精确 owner 索引](error-diagnostic-owner-index.md)：全 10,234 条互斥投影中只收口 308 Product caller 与 376 Dependency package/function，9,550 保持 Unresolved；Product flow 当前只有 4 条 catch、99 条 retry、13 条 tool-result 获得 exact owner，user-surface 仍为 0，避免把一个 lexical scope 当成完整恢复链。

### 24.10 Telemetry隐私不等于全局数据流

关闭一方telemetry、关闭管理员OTEL、不写本地transcript、不共享Feedback transcript是四个独立动作；它们都不会关闭核心Messages推理。Remote Control同步、WebFetch hostname preflight、MCP/Hook、IDE/Chrome、Artifact/file upload和Voice又各有目的地与consent。

`/compact`、`/clear`、rewind和tombstone只改变客户端持有的消息/文件表示，不是外部删除协议。按`DATA / OWNER / DESTINATION / DEFAULT / CONTENT GATE / CONSENT / RETENTION / DELETE`逐条查看见 [全局数据流与隐私](client-data-flow-and-privacy.md)。

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

Rust/N-API路径保留 `napi-2.16.17`、`cpal-0.15.3`、`coreaudio-rs-0.11.3`。导出录音、播放、状态和 microphone authorization。原版 JS wrapper 只把 native callback 收到的 bytes 原样上抛，本身没有声明采样率转换；可直接观察到的是 SoX fallback 使用 `-r 16000 -e signed -b 16 -c 1`，Voice WebSocket query 声明 `encoding=linear16`、`sample_rate=16000`、`channels=1`。

初始 probe为 `{recording:false, playing:false, mic:0}`；播放启动后 `isPlaying=true`，停止后立即 false。原版 native 内部是否以及怎样完成 16 kHz/mono/s16 重采样仍是 Boundary；重建版按 SoX/wire 消费合同独立实现转换、静音阈值和 buffer policy，测试通过也不把这些实现升级成原始源码事实。

### 26.6 `url-handler.node`

使用 Apple Event `GURL`、direct object和 UTF-8 decode，提供 `waitForUrlEvent(timeout)`。无事件时 timeout返回 null，是正常结果，不应被解释成 native crash。

### 26.7 架构覆盖

ARM64 上 5 个原版/兼容模块完成 contract。报告的 23 个检查项由 22 个真实原版/兼容对照和 1 个最低覆盖审计组成；22 个对照为 `14 exact`、`5 normalized-semantic`、`3 schema-and-invariants`，本次 `environment-boundary` 为 0。动态 hide 候选按 bundle ID 归序后深比较完整成员和字段。原版 `computeHideCandidates` 固定豁免 Finder，并要求窗口为 layer 0、alpha 严格大于 `0.1`、与目标显示器相交；该路径没有 `width/height > 1` 门槛，源码里的尺寸判断属于窗口显示器归属和普通激活候选。`prepareDisplay` 调用方又额外 union host 与 Finder。`previewHideSet` 调用方只传用户给定的豁免集合，但仍经过固定 Finder helper；它会把可选 display ID 解析成指定显示器，缺失或无效时回退主显示器。screenshot 路径单独使用 8 项系统界面 bundle ID 白名单，其中 loginwindow 与 Finder 的 hide 规则不是同一集合。full/region screenshot 比较字段、尺寸、显示器元数据、规范 Base64 及 JPEG 首尾标记，并由对应图像模块实际解码，格式必须为 JPEG，解码宽高必须等于截图返回值；不比较实时帧字节。只有双方返回同一条已知 TCC/ScreenCaptureKit 失败合同才记环境边界，一边成功、一边失败或错误漂移直接失败。构建门从原版 arm64/x86_64 Mach-O 静态数组对象逐项解码 8 个 Swift String，并核对数组初始化、`computeExcludedApps -> Set.contains` 消费链、full/region nil 分支、cstring 地址和 79/75 字节长度；兼容源码也按函数绑定两条错误文本、`captureScreen` 的白名单 union 与 caller-specific catch，内置负向注入证明删掉任一消费点都会失败。同一门还校验 Finder 编码、`0.1` 常量和 preview display 指令。第二份报告采用 `validated-artifacts-and-runtime`：它验证 5/5 supplied compatible 文件为独立 regular x86_64 Mach-O、未复用原版 hash，并在 Rosetta x86 Node 下完成加载和导出合同；Rust x86 target 与 Swift x86 triple 只是 build recipe，没有同次 build output/status。发布物含 x86 slice 的 Input/Swift 两模块完成 19 项同输入行为比较和 1 项覆盖 guard。audio、image、URL 没有 original x86 slice，不能外推原版 x86 行为。两个报告都在比较前使旧文件失效，并通过临时文件、`fsync` 和 rename 原子落盘。

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
- 347 条机制证据：246 Static、52 Probe、33 Public、16 Boundary；Static 细分为 206 runtime、18 consumer、12 constant、4 surface、6 declaration，347 个 claim ID 均唯一；validator 逐条核对 48 个 topic、源码范围、anchors、Probe 字段与 Boundary；
- 58个能力面：55项Deep、IDE/Updater 2项Documented、1项Boundary；
- 93个归一化风险控制项；
- 156个根 settings、361个 feature flag候选；
- 29 项人工维护的核心终端 tool reference、80 个同工厂 AST 注册调用点（77 静态 name、3 动态 expression）、188 个 known-tool catalog 项；
- 31个 hook event；
- 17个 model entry、6个 pricing tier、4个 alias family。

### 33.2 精确二进制 Probe

19份运行报告覆盖命令、协议、持久化、网络和原生行为；每份都绑定版本、输入、literal output、exit status、required checks 与 Boundary：

- Agent Loop工具闭环、resume、manual compact、fork；
- bearer/API-key request shape和 prompt cache开关；
- PreToolUse deny、Stop hook重入、maxTurns；
- MCP generation refresh；
- Plugin Skill listing、launch acknowledgement 与正文注入；
- Plugin LSP stdio initialize/open/definition/shutdown、1-based 到 0-based 坐标和 paired result；
- 子 Agent隔离和两阶段结果回传；
- settings层级、529/400 retry、model fallback；
- OTLP prompt脱敏；
- OTLP HTTP logs 的有效 CA/mTLS/proxy owner，以及 exporter TLS失败与 Agent result隔离；
- Messages proxy/NO_PROXY/CA/mTLS；
- Plugin Evaluation免费 with/without两臂；
- Embedded Grep病态 pattern、`-m` context和工具错误回灌；
- TUI permission comment与快速 Arrow+Enter scope；
- Project purge/import/manifest mismatch；
- filesystem/network sandbox；
- file checkpoint rewind；
- doctor/update gate和 Remote Control负向边界；
- 内部 feature override 不可达；
- 原生 contract、22项原版/兼容对照、0项环境边界和1项覆盖审计。

### 33.3 尚未形成正向 Probe 的部分

- 真实 Anthropic服务端 prompt-cache命中与账单；
- Bedrock、Vertex、Foundry等真实云凭据闭环；
- 登录账户的 Remote Control和 cloud orchestration；
- OTLP gRPC、metrics、traces和远端 collector retention/delivery；
- 除已覆盖的 Shift+Tab 和快速 Arrow+Enter 外，其余多行 highlight、Vim panel 与 VS Code release fix 的自动视觉/宿主回归；
- CLI退出后的真实 background supervisor耐久。

这些缺口不会抹掉已完成的客户端静态与本地 Probe结论，但也不能被“validator PASS”替代。

## 34. 如何继续读证据

| 想解决的问题 | 深入文档 |
| --- | --- |
| 为什么模型只有提案权、本地 runtime 怎样逐请求编译能力、裁决并记因果；Agent Loop、Bash 风控、`compact`、resume、MCP/子 Agent、Artifact、Telemetry 与 native Voice 怎样共同暴露版本技术性格 | [product-surface-evidence-map.md](product-surface-evidence-map.md) |
| top-level system、CLAUDE.md/Memory、typed attachment、`system-reminder`、文件变化、Hook/IDE/MCP和cache marker怎样组成一次真实请求 | [prompt-assembly-and-system-reminders.md](prompt-assembly-and-system-reminders.md) |
| Messages、local transcript、Remote、1P/OTEL、Feedback、WebFetch、MCP/Hook、IDE/Chrome、Artifact/upload和Voice分别去了哪里、如何同意和删除 | [client-data-flow-and-privacy.md](client-data-flow-and-privacy.md) |
| 为什么 29 项核心参考之外还有 80 个注册调用点，工厂怎样展开，哪些会进入真实请求 | [tool-registration-and-host-surfaces.md](tool-registration-and-host-surfaces.md) |
| Brief 模式的主用户输出、附件和漏调修复怎样工作 | [brief-mode-and-user-visible-output.md](brief-mode-and-user-visible-output.md) |
| Plan Mode 怎样阻止实施、保存计划并把批准/拒绝回灌 Agent Loop | [plan-mode-and-human-approval.md](plan-mode-and-human-approval.md) |
| `--json-schema` 怎样变成强制收尾工具和可验证终态 | [structured-output-and-schema-contract.md](structured-output-and-schema-contract.md) |
| REPL 怎样编排内层工具、保留变量并用结果重放恢复 | [repl-programmatic-tool-runtime.md](repl-programmatic-tool-runtime.md) |
| EndConversation 的硬门控、两次确认、abort 与 prompt 风控边界 | [end-conversation-risk-control.md](end-conversation-risk-control.md) |
| Remote routine、runner operator 和通知背压/ack 怎样协作 | [remote-routines-runner-and-notifications.md](remote-routines-runner-and-notifications.md) |
| Connector/Plugin/Skill 目录与 MCP refresh/wait/resource 怎样改变 live state | [connectors-catalog-and-mcp-operators.md](connectors-catalog-and-mcp-operators.md) |
| ClaudeDesign 动态操作与 Projects 文件/RAG/权限链怎样工作 | [claude-design-and-projects.md](claude-design-and-projects.md) |
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
| API、工具、compact、session、MCP 等场景的事件顺序，1,441 个一方事件、Datadog/OTEL 字段、动态事件名，以及 `tengu_other` 140 条 exact / 891 项 Unresolved caller-owner 投影 | [telemetry-event-catalog.md](telemetry-event-catalog.md) |
| 99 条 API path、53 个 Beta 和 Gateway/SDK owner | [api-beta-route-ownership.md](api-beta-route-ownership.md) |
| Error、debug、tool failure、abort 与 LSP diagnostics | [error-diagnostic-atlas.md](error-diagnostic-atlas.md) · [error-diagnostic-owner-index.md](error-diagnostic-owner-index.md) |
| Artifact Watch 评论自动响应 | [artifact-watch-comment-autoreact.md](artifact-watch-comment-autoreact.md) |
| `/insights` 历史分析与 facet cache | [insights-history-analysis-pipeline.md](insights-history-analysis-pipeline.md) |
| CLI 启动 file/plugin/deep-link 资源 | [cli-startup-files-plugins-deeplinks.md](cli-startup-files-plugins-deeplinks.md) |
| 复杂 Slash Command 外部状态机 | [complex-slash-command-lifecycles.md](complex-slash-command-lifecycles.md) |
| 所有机器字段怎样读 | [inventory-field-guide.md](inventory-field-guide.md) |
| 公开资料与本版证据边界 | [public-claims-validation.md](public-claims-validation.md) |
| 每条 Probe命令和原始结果 | [runtime-probe-index.md](runtime-probe-index.md) |

## 35. 十二个容易被清单掩盖的产品状态机

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

### 35.8 REPL：外层一次调用，内层仍是完整工具管线

`REPL` 把一段 JavaScript 放进受宿主管理的持久 VM，让模型用 `rgf()`、`cat()`、`put()` 等 helper 串联多个工具，或用 `registerTool()` 创建后续轮次可见的动态工具。外层 transcript 只有一个 `REPL tool_use`，但每个内层调用仍会生成自己的虚拟 tool pair，并依次经过 schema、isolation latch、`PreToolUse`、permission、真实执行、`PostToolUse` 和结果配对；`REPL.checkPermissions()` 的 allow 只允许进入编排器，不能绕过内层权限。

默认脚本预算是 30 秒，最高 600 秒；内层工具运行时会暂停脚本预算，另有 600 秒 wall clock 和按 native timeout 推导的 watchdog。console 总预算为 52,428,800 bytes，普通结果约 100,000 字符；未 await 的内层调用会在 finally 中 abort，而不是在外层工具结束后继续偷偷产生结果。动态工具名限制为 1-111 位字母、数字、下划线或连字符，schema 必须可 JSON 序列化且不能覆盖宿主内建 global。

进程退出后 VM 不会被原样序列化。客户端记录 `code/calls/threw` replay log；resume/hydration 时再次求值旧代码，但把工具 wrapper 替换成历史缓存结果，所以变量和注册工具可以尽力恢复，已完成的 Bash/Edit/MCP 不会再次执行。调用数量、顺序或 throw 位置因 `Date.now()`、随机数或外部状态发生变化时只报告 replay drift，不伪造精确恢复。结果重放避免的是恢复期重复副作用，不是事务回滚；旧文件写入、进程和远端调用仍需显式补偿。完整 gate、timer、VM sealing、动态工具和恢复合同见 [REPL 程序化工具运行时](repl-programmatic-tool-runtime.md)。

### 35.9 EndConversation：两次调用是硬门控，结束理由主要是模型约束

`EndConversation` 不是模型输出一句“结束”就关闭会话。工具先受 feature flag、模型版本下限、entrypoint/scope 和主运行面 gate；第一次调用只返回完整 reflection 规则并保持 `ended:false`。第二次调用前，客户端从消息尾部回看上一轮同名 `tool_use`：普通 tool result 不会打断确认，但新的业务 user message 会让旧确认失效。子 Agent 即使继承到工具对象也只能得到 no-op 反思结果，不能结束主会话。

真正结束分支会 best-effort 追加 `ended-by-model` marker，再以 `end_conversation` abort 当前 Agent Loop。marker 写失败不会阻止本次结束；TUI 写入 `endedByModel:true`，print/continue 路径以状态 1 结束，未完成工具被取消，已经完成的外部副作用保留。resume 依靠 marker 恢复会话已被模型终止的状态。

“持续直接辱骂”“已经重定向和警告”“演示场景要先取得用户确认”“自伤/伤人场景不得结束”等规则被反复写进工具 prompt，但客户端没有独立语义分类器重新证明这些条件。准确表述必须把 scope/model/two-call/history/abort/terminal guard 记为程序硬控制，把结束理由记为模型行为约束。完整风险强度、失败矩阵和证据边界见 [EndConversation 风控专题](end-conversation-risk-control.md)。

### 35.10 Remote routines、runner 与通知：控制面、执行面和回传面分属三个 owner

`RemoteTrigger` 有 `list/get/create/update/run/create_webhook_trigger/list_runs/get_run_log` 八种 action。它用 `teleport-org` 认证和 20 秒 timeout；`list_runs` 每页 10 条，`get_run_log` 每页取最新 200 个 event，再把 transcript、工具、compact、permission、retry 和终态映射成人类可读投影。原始字段先受 16,000 字符裁剪，单 event 4,000，整体约 100,000；`eventsFetched/eventsShown/nextCursor` 明确告诉读者这不是完整远端 transcript。write timeout 只说明本地停止等待，不能证明服务端没有创建或启动 routine，因此重试前必须先 get/list 查状态。

Self-hosted runner 的九个 operator tool 只在 first-party provider 和 OAuth operator token 下工作，`ANTHROPIC_API_KEY` 不能替代。API timeout 20 秒并保留 401/403/404/409/429；spawn 先询问，再以 detached/unref 进程启动，获得 spawn event 与 PID 后才写 PID file。`requeue_session` 同样要求 ask/classifier，并把观察到的 runner assignment 交给服务端做 conflict 校验，避免基于过期快照移动已改派 session。health/metrics 只探测 loopback，timeout 2 秒；health port 0 表示禁用；log tail 默认读最后 65,536 bytes 并做 credential-shaped redaction。

通知回传使用独立有界队列。单条 content 上限 87,488 字符，pending 上限 100；太大或队列满时不 ack，形成真正背压。已 drain ID 只保留最近 1,000 个用于去重；nudge 只告诉模型“有几条待读”，不注入正文，最多 rearm 两次。`ReadNotifications` 只能由主会话调用，按 90,000 字符预算 oldest-first drain，原子移除本批、记录 ID、清 nudge，然后只 ack 真正 drain 的 transport event。通知 body 仍是外部数据，不因进入 tool result 自动获得 system authority。完整 operator、阈值、失败和不可逆远端边界见 [Remote Routines、Runner 与 Notifications](remote-routines-runner-and-notifications.md)。

### 35.11 Connector、账号 Catalog 与 MCP Operators：发现、建议、启用和当前请求是四种状态

Connector Search/Suggest/List 只在 first-party remote host gate 下出现，走 `teleport-org` route 和 15 秒 timeout。Search 关键词限制为 1-8 个、每个 1-64 字符；Suggest 接受 1-32 个搜索返回 ID。List 通过 `installedServerId` 和 live MCP client 的 `X-MCP-Server-ID` 关联出 `enabledInChat`，但这只描述当前 session 的连接投影；registry 命中不等于已连接，connected 也不等于工具已经进入正在飞行的 request。

Plugin/Skill 账号目录有另一组 policy/provider/HIPAA/entrypoint gate。缺少 `user:plugins` scope 时，标准可刷新 OAuth 会在 credential lock 内扩 scope，并区分 custom client、无 refresh token、lock contention、sibling adoption、save failure 和 scope 未授予。Plugin list 每页 100、最多 20 页、每页 10 秒，失败后等待 500 ms 做一次完整重试；Skill list timeout 30 秒并限制 16 MiB response。可解析的 403 会降级为 not-entitled 空结果，所以空数组不能直接写成“账号没有插件”。

SuggestPluginInstall 只返回等待 UI 接受的 card，并要求后续 `ListPlugins` 观察 enable 状态；SuggestSkills 同样不安装内容。`RefreshMcpTools` 只重读已经连接 client 的 tool list，清 cache、保留 discovery/auth 失败前的 previous tools，用 started/applied sequence 抑制过期并发结果，再重施 deny rules；它不会拨号，也不能热替换已经发出的 request。`WaitForMcpServers` 最多 poll 5 秒，返回 connected/cached/failed/pending/auth/disabled/unconfigured/unknown；Resource list/read/dir 又是 MCP 的独立 capability，空 resource 不代表没有 tools。完整状态表与错误分类见 [Connectors、Catalog 与 MCP Operators](connectors-catalog-and-mcp-operators.md)。

### 35.12 ClaudeDesign 与 Projects：动态远端操作和附着项目不是旧 DesignSync 的同义词

`ClaudeDesign` 首次调用会通过 `/v1/design/mcp` 做 `initialize -> tools/list`，缓存 MCP session、动态 operation schema/hint 和按 agent 记忆的 catalog hash；并发初始化共享 in-flight Promise，旧 session 返回 404 时清状态、重新握手并重试一次。transport 只接受 first-party JSON，timeout 60 秒；401 最多等待 5 秒刷新凭据并用新 token 重试一次，虽然 Accept 含 event stream，本版明确拒绝 `text/event-stream`。catalog hash LRU 最多 64 项，只用于避免重复发送相同 schema，不缓存远端 operation result。

写/删权限分两层。`finalize_plan` 把 writes/deletes 各最多 20 条、单 path 最多 80 字符的计划交给人工，token 只对同一 project、精确路径集合和可枚举 target 生效，最长 15 分钟；durable project grant 由服务端确认，但不覆盖 delete、`CLAUDE.md`、`.claude` 等敏感目标，403 会使客户端失效本地 verified 状态并重新申请一次。结果侧又有三层预算：preview image 130,000 base64 字符、映射 aggregate 130,000 字符、工具框架 100,000 字符，不能混成一个文件上限。

`Projects` 只操作当前会话已经 attach 的一个 Project，固定提供 `project_info/read/search/write/delete` 五种方法，不做 project discovery。首次调用可能在 credential lock 内扩 `user:projects:read/write` scope；API timeout 30 秒。`project_search` 默认 5、范围 1-15 个命中，只有 HTTP 403 才退回 `rag:false` 和文档名列表，不伪造搜索结果。read 的 inline text 上限 256 KiB，raw download 20 MiB；`local_path` write 会同时约束 lexical/real path、打开 fd 后重做 path/device/inode/regular-file 检查，并拒绝超过 25 MiB，防止校验后替换文件。新 bare filename 自动放进 `claude/` namespace，knowledge growth 以 UTF-8 bytes/4 向上估算；这些只是客户端预算前检，服务端存储、授权、RAG、团队可见性和已完成远端写的事务回滚仍是 Boundary。详见 [ClaudeDesign 与 Projects](claude-design-and-projects.md)。

## 36. Auto Mode：确定性规则之后的两阶段权限分类

Auto Mode 不是 `bypassPermissions` 的别名，也不是让模型接管全部权限。单工具仍先经过 deny、工具自身 safety check、ask、交互要求、组织级 ask ceiling 和 safety floor；这些层已经要求拒绝或询问时，分类器不能覆盖。只有普通 permission ask 才可能进入 Auto Mode。命中 `acceptEdits` 模拟或本地 safe allowlist 的动作可以直接放行，未命中者才构造 classifier transcript。

规则只从 `userSettings`、`flagSettings` 和 `policySettings` 聚合；项目和 local settings 中的 `autoMode` 会告警后忽略，防止仓库内容自行放宽权限。`allow`、`soft_deny`、`hard_deny`、`environment` 使用有位置语义的 `$defaults`：第一次出现时把 shipped defaults 插入该位置，没有 `$defaults` 就完全替换默认段。`classifyAllShell=true` 只在 Auto Mode 活跃时暂停 shell allow fast path，不会删除原规则。

默认 `twoStageClassifier="both"`。Stage 1 输出预算为 `64 + thinking overhead`，fast-only 时为 `256 + thinking overhead`，外层与 SDK timeout 都是 60 秒；Stage 1 allow 立即结束，block 倾向或无有效 verdict 进入 Stage 2。Stage 2 预算为 `8192 + thinking overhead`、外层 timeout 120 秒，可以推翻 Stage 1 的 block；但 API unavailable、XML parse failure、safeguard refusal 或最终无 verdict 时，普通工具 fail closed。此时的拒绝表示“没有可靠许可”，不等于模型已经证明动作危险。2.1.235 还有一条缺陷候选：Stage 1 已产生 usage 但无 verdict，随后 Stage 2 request 抛异常时，返回对象没有 `failureMode`/`unavailable`，后续误计为普通 denial 并编码成 `automode-blocked`；该 outcome 不能当作真实危险分类结论。

classifier denial 可触发 `PermissionDenied` Hook。`retry:true` 只向下一轮 Agent Loop 追加可重试提示，原始 tool call 没有执行；setup/apply 又使用 proposal、review 和内容 hash 绑定，防止交互确认后配置被换包。完整输入裁剪、repo visibility/git status 补充、Agent/AskUserQuestion/headless fallback、outcome kind、成本和隐私边界见 [Auto Mode 专题](auto-mode-classifier.md)。

## 37. Plugin Evaluation Harness：高分不等于插件有增益

`claude plugin eval` 先把 `case.yaml` 或 `prompt.md + graders/*.md` 编译成严格 schema，再对 case 目录、grader、plugin tree 做 inode/device、symlink、hardlink、owner、mode 和 containment 检查。`runs` 默认 3、最大 50；`max_turns` 默认 10、最大 200；`timeout_seconds` 默认 300、最大 3600。输入身份检查只能证明父进程执行的是刚审查的内容，不能把第三方 case 或 `scaffold_script` 变成可信代码。

有插件时默认执行 `with-without` ablation：with arm 保留 `pluginDirs`，without arm 只把它清空，其它 resolved case 合同保持一致。`with-only` grader 和默认的 `tool_used: Skill` 不进入两臂效果分母，避免把“基线没有插件工具”直接计成质量提升。没有真实 without arm、replay history 已带插件影响或两臂 grader 规则不同，就不能发布有效 Delta。

每个 run 使用新的 HOME、Claude config、Git workspace、trace 和 credential copy，以 `-p --output-format stream-json --permission-mode dontAsk` 启动同版 child。这里的 sandbox 是状态目录隔离，不是断网、容器或 OS syscall sandbox；获得 Bash、Write、WebFetch 或 MCP grant 后仍会产生真实副作用。费用 ceiling 在 run 开始前检查，所以最多可被一个已启动的 Agent run 越过；之后付费 grader 被跳过、suite 标记 `partial_reason=cost_ceiling`。

六类 grader 分别是 regex、tool order、tool used、file exists、LLM 和 baseline。LLM/baseline 各发 3 次独立 judge，2/3 多数决定 PASS；grader 异常按失败计入，不从平均值消失。完整 suite 达阈值 exit 0，质量/case 错误 exit 1，cost ceiling 或 auth failure partial exit 2；SIGINT/SIGTERM 即使报告仍写 `partial=true, partialReason=interrupted`，最终 shell exit 也分别是 130/143。JSON、HTML 与可选私有 publish 保留每次 run、evidence、judge votes、费用和 Delta。

精确二进制的免费 smoke 已实际运行 1 个 with arm和 1 个 without arm：两臂 regex score 均为 1、Delta 0、partial false；只有 with request带 plugin SessionStart hook context，without request不带；JSON/HTML 均 mode 0644，command使用 `--no-publish --no-scaffold`。这证明 harness 编排，不证明本地 stub代表真实模型质量，也不覆盖 paid judge。完整合同见 [Plugin Evaluation Harness](plugin-evaluation-harness.md)。

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

共同风险是确认后的执行采用顺序副作用：中途失败不会自动撤销先前成功项，manifest mismatch 甚至发生在文件已落盘之后。精确二进制 Probe 已把这条顺序跑通：purge 与 JSON dry-run 不改各自 domain bytes；真实 JSON import 写出 mode 0600 transcript、正确 parent chain、project instructions 和降权后的 `imported-CLAUDE.md`；故意错误的 ZIP manifest 则 exit 1，但 transcript、instructions、`imported-CLAUDE.md` 与 `imported-AGENTS.md` 全部保留。注意 purge dry-run 仍允许普通 CLI bootstrap 创建 `.claude.json`/backup，因此“domain 零写入”不能夸大成“进程 filesystem-silent”。Config import 在离线内置 false gate 下仍不可正向 apply。输入护栏、文件模式、恢复动作和隐私边界见 [Project Purge、Import 与数据生命周期](project-purge-import-and-data-lifecycle.md)。

## 45. Sandbox 安装态与运行态

Windows `claude sandbox install/status` 回答宿主依赖和隔离用户等长期对象是否准备好；Agent Loop 的 sandbox wrapper 回答本 session、这一条 command 是否真的被约束。`installed:true` 只证明安装检查通过，不证明当前设置启用 sandbox，也不证明该工具路径经过 wrapper。运行时还要通过 platform、policy、setting、工具 eligibility 和 `dangerouslyDisableSandbox` 等 gate，并在 session 中懒初始化、合并并发初始化请求。

同样，CLI 最终 exit 0 只说明它成功处理了工具结果，不能代替检查 Bash/tool result 和外部文件/网络状态。Session cleanup 会释放进程级资源，却不等于卸载长期依赖或回滚已产生副作用。两条状态机、UAC/退出码、ACL、fallback 和 exact-binary 负向 Probe 见 [Sandbox 安装与运行 Enforcement](sandbox-install-and-runtime-enforcement.md)。

## 46. Proxy、NO_PROXY、CA 与 mTLS

Claude Code 没有一个覆盖所有网络调用的万能代理开关。主请求/通用 fetch、Axios/undici、WebSocket、AWS SDK、MCP transport和 CCR 子进程分别选择 adapter；`NO_PROXY` 也存在不同匹配器。OTLP HTTP logs虽然带自己的 library env parser，但 Claude会先注入通用 `Kol()` programmatic agent，最终 merge由后者获胜；OTLP gRPC仍是另一条 credentials实现。主模型能联网只证明其 transport 已通过 proxy，不证明 MCP、云 SDK、后台 Agent 或遥测自动等价。

TLS 又分服务端信任和客户端身份：CA store 组合 bundled/system/extra CA，并过滤过期系统证书；mTLS cert/key 要成对校验并在 stale connection 时重载。CCR agent proxy 是只接受 HTTPS CONNECT 的本地 policy relay，带有 allowlist、流控和兼容性边界，不等于任意直连。逐 transport 的优先级、407 helper refresh、证书轮换和排障顺序见 [Proxy、CA 与 mTLS](network-proxy-ca-and-mtls.md)。

Messages HTTPS Probe观察到：小写 `https_proxy` 覆盖冲突的大写值，`no_proxy=localhost` 绕过两个 CONNECT proxy，缺 scheme 的 proxy在 API marker前 fail closed，自签服务从无 CA的 exit 1变为 extra CA下 exit 0，client pair又让 server观察 authorized CN。独立 OTLP HTTP logs Probe进一步证明 effective owner：OTLP专用 CA/client变量没有成为最终 HTTP agent；`NODE_EXTRA_CA_CERTS`、`CLAUDE_CODE_CLIENT_CERT/KEY` 和通用 proxy分别完成 collector POST、mTLS CN与小写 CONNECT precedence。所有 exporter TLS失败仍返回 Agent success/exit 0。两组报告都不外推 Axios、WebSocket、AWS、MCP、OTLP gRPC/metrics/traces、子进程或 CCR。

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

## 52. Plan Mode：从只读探索到人工批准的实施授权流水线

Plan Mode 不是给模型追加一句“先别改代码”。`EnterPlanMode` 先打开专用确认 UI；接受后，客户端把 `toolPermissionContext.mode` 切到 `plan`，把进入前的 `default/acceptEdits/auto/...` 保存为 `prePlanMode`，并处理 Auto Mode 期间需要剥离的危险 allow rules。规划期可以按 `useAutoModeDuringPlan` 采用 Auto 分类语义，但批准后恢复的是进入前模式或用户明确选择的新模式，不会因为规划期用了 Auto 就悄悄升级权限。

Agent Loop 在首次进入、compact 后和长期规划中持续注入 Plan attachment。完整 reminder 说明探索、澄清、方案设计、计划编写和退出协议；间隔不足 5 个 user turn 不重复注入，达到阈值后再用 full/sparse attachment 提醒。`--plan-mode-instructions` 只能在 `--print` host 使用，自定义中段不能移除固定只读前言、实际 plan file 路径和 `ExitPlanMode` footer。

计划文件是明确的写入例外，不是 Plan Mode 允许任意 Edit。主线程和 agent 分别用规范化 slug；自定义 `plansDirectory` 解析后仍必须位于项目根内，并通过路径/链接边界。permission engine 识别当前 session 的 plan/workshop file；普通写工具、非只读 MCP 和自动批准仍受 `mode: plan` 与 `plan_mode_floor`，不能用 bypass/Auto 从侧面放行实施动作。

`AskUserQuestion` 负责需求澄清，不负责批准计划。问题、选项、header、preview 和唯一性有结构化限制；少于两个选项的题目不会展示给用户。AFK 设置只有 `never/60s/5m/10m`，默认是 never；显式启用且 host 条件允许时，timeout 会连同已有部分答案回灌，但它不能代替 `ExitPlanMode` 的实施授权。SDK shutdown 还可以 park 未完成 request ID，避免把 host 关闭误记为人工拒绝。

`ExitPlanMode` 从 canonical plan state 读取真实计划，交给 review UI，而不是信任模型自报正文。用户可以批准并选择退出 permission mode、编辑计划、拒绝并附反馈，或在支持时 clear context 后用批准计划自动续接。超过 200,000 字符的计划因无法完整审阅而 withholding approval，这不是 plan file 写入上限。拒绝保留 plan、`mode=plan` 和 `prePlanMode`，让模型修订后重提；team member 用 request ID 交给 lead 审批，远端 Ultraplan 则从事件流区分 pending/approved/rejected/local/remote execution target，poll 每 3 秒并最多容忍 5 次连续网络错误。

批准只改变后续实施权限，不回滚规划前已经发生的副作用；远端审批存储、账号 capability、Ultraplan 容器和模型计划质量仍是 Boundary。完整 UI、mode 恢复、team/AFK/SDK/remote 失败矩阵见 [Plan Mode 与人工审批](plan-mode-and-human-approval.md)。

## 53. Structured Output：Schema 不是输出装饰，而是 Agent Loop 的强制终态

`--json-schema` 只在 non-interactive/SDK structured-result 路径生效。客户端先 `JSON.parse` 并要求根值是非数组 object，再以 AJV `allErrors:true, validateFormats:false` 校验 schema 和最终 tool input。预检查限制 100,000 nodes、10,000 recursion depth；strict 转换另限 32 层和 100,000 nodes，只接受受控 keyword 子集。strict 转换失败不会关闭功能，而是保留原 schema 和本地 AJV validator。

真正的机制是动态创建一个专用 `StructuredOutput` 工具：它用调用方 schema 替换 `inputJSONSchema`，声明 read-only、concurrency-safe、permission allow，并要求模型在响应结尾恰好调用一次。只有刷新后的真实工具集合仍包含它，query 才设置 `requiresStructuredOutput:true`。普通推理、Read/Bash/Edit/MCP 仍可先执行；schema 只约束最终收尾对象，不证明前置业务事实正确，也不撤销前置副作用。

支持的模型/provider/gate 可以把受限 schema 以 `strict:true` 发到 wire；例如 Foundry 返回特定 400 时，客户端记住该 deployment 不支持 `structured_outputs`，剥离 strict 后重试，但本地 AJV 校验仍不可绕过。`format` 不由这份 AJV 执行，strict 也不接受它，因此 `{testsPassed:true}` 通过 boolean 类型只能证明形状，不证明测试真的运行。

模型调用 `StructuredOutput(input)` 后，本地校验失败会形成带 `tool_use_id`、instance path、message 和 keyword 的标准 tool error，进入下一轮修正。成功返回 `{structured_output: input, endsTurn:true}`，结果映射层把对象保存为 attachment；terminal result 取最后一个仍存活 attachment。当 model fallback tombstone 撤回包含该调用的 assistant message 时，客户端按 tool-use ID 删除 attachment并拒绝晚到结果，避免被撤回对象泄漏到最终输出。

本轮普通和被撤回的 StructuredOutput 尝试累计到默认 5 次且没有存活对象时，turn 以 `error_max_structured_output_retries` 结束。这个修正轮次与“provider 不支持 strict、剥离字段后重发”的 API capability retry 不是同一种计数。每次失败都会增加 tool call、tool error、下一轮模型 token 和延迟；schema/property description 及成功对象也会进入 provider request、本地 transcript 和 stdout/SDK result，因此结构化输出不是脱敏器。

客户端发布物能证明 schema 解析、AJV/strict、工具注入、attempt、attachment、tombstone 和终态；不能证明服务端 constrained decoding 的内部实现、某账号 gate 值或业务对象真实性。完整限制表、失败矩阵和 stdout 协议边界见 [Structured Output 与 Schema 合同](structured-output-and-schema-contract.md)。

## 54. Artifact Watch：评论是不可信数据，不是直达执行器的指令

`--watch-artifact` 不是远端无人值守 Agent。入口只允许当前环境的 Artifact id/URL，并拒绝 remote session、print/SDK、init-only 和重定向输出等没有本地交互 owner 的 host。首次扫描只建立 `seen`、`sentToClaudeAt`、`ownReplyIds`、digest 和 high-water baseline，不把旧评论当成新任务。字段退化时 digest 失效，新信号在当前 scan 结束后重扫，用来抑制并发重复回复。

外部评论先进入无工具、无 thinking、无 prompt cache、128 output-token 的 triage；异常会降级到普通 `pipeline`，不会升级到编辑。只有 `act` 才启动最多 6 turns 的只读 analyst，且 permission wrapper 仅允许目标 Artifact/线程的 comments 与 page data 读取。真正写入前还会重检 plan mode、线程竞态、小时额度、loop breaker 和空 reply permission probe；`ask` 只通知，`deny` 终止，明确 `allow` 才进入 composer。

默认 coalesce 为 5 秒、confirm dwell 为 2 秒，每 Artifact 每小时默认 60 个自动 turn；同线程 30 秒内连续 3 次自动回复打开 loop breaker，连续 3 次 pipeline denial 也会暂停。快速 acknowledgment 与完整回复/编辑是两个真实远端提交，中途失败不会撤回已发 ack；compact、resume、tombstone 和 rewind 也不能撤回已发评论、新 Artifact 版本或 resolve。详见 [Artifact Watch 评论自动响应](artifact-watch-comment-autoreact.md)。

## 55. `/insights`：本地统计、模型 facet 和全局分析是三层成本

`/insights` 先从本地 transcript 产生确定性 session metadata：消息、token、tool、语言、Git 动作、错误、时长和 transcript mtime。它把 metadata 写入 mode `0600` 的 cache，每次最多新建 200 份、刷新 200 份 stale 记录，因此大型历史不保证一次扫完。少于 2 条 user message 或不足 1 分钟的 session 不进入有效分析集。

为给模型生成 facet，user/assistant 文本每段分别截到 500/300 字符；超过 30,000 字符的 session 按 25,000 字符分块，每块最多 500 output token 总结，失败则保留前 2,000 字符。冷缓存最多对 50 个无 facet session 各发一个最多 4,096 output-token 请求，再并行生成 7 个最多 8,192 token 的专题，最后再生成 1 个 8,192-token 总览。不计分块总结，一次冷缓存的静态最大 output-token 配额是 270,336，不是一个纯本地报表。

最重要的准确性缺口是：metadata 会比较 transcript mtime，facet cache 只校验 JSON 结构与 session id，没有用 transcript mtime 使旧语义判断失效。用户继续修改旧 session 后，确定性计数可以更新，目标、outcome、满意度和 friction 却可能继续复用旧 facet。报告写时间戳 HTML 与 `report.html`，都是本地 `0600` 文件；模型分析质量与最终费用仍为 Boundary。详见 [`/insights` 历史分析管线](insights-history-analysis-pipeline.md)。

## 56. CLI 启动资源：下载、加载与提交不是同一件事

`--file` 把 `file_id:relative_path` 通过 Files API 下载到 session uploads。它要求 session access token、first-party provider 且拒绝 HIPAA 组织；单请求 60 秒、最多 3 次、500/1000 ms 退避、默认 5 文件并发。路径只做词法 normalize 与 `..` 拒绝，当前 consumer 没有证明逐级 symlink/realpath/O_NOFOLLOW 防护。resume 显式等待 download promise，新 session 路径在同一分支没有先等待；落盘成功也不会自动把 bytes 放进 Messages 请求。

`--plugin-url` 下载的是当前 session 的可执行控制面，不是普通资料。managed sideload policy 在参数和加载期双重 gate；fetch 超时 30 秒，ZIP 下载上限 256 MiB，解压还限单文件 512 MiB、总量 1 GiB、100,000 个文件和 50:1 压缩比，并拒绝绝对路径与 `..` traversal。但这条具体网络链没有展示 HTTPS/host allowlist、loopback/link-local 拒绝或 redirect 复检；解压安全不能写成 URL 供应链安全。加载后 plugin 可带入 commands、skills、hooks、MCP 和 bin，临时 cache 在退出时清理。

Deep Link handler 固定用 `--handle-uri <uri>`，后续多出 argv 会被当成 argument injection 拒绝。cwd/query 通用路径用 base64url 传递，terminal command 对 shell metacharacter 和 binary path 做安全构造；有效 cwd 会 `chdir` 并刷新 workspace/git cache，prefill 只进 composer，不自动提交。OS handler 注册是跨 session 持久副作用，uploads 与插件树又各有独立生命周期。详见 [CLI 启动文件、插件与 Deep Link](cli-startup-files-plugins-deeplinks.md)。

## 57. 复杂 Slash Command：命令名称相似，状态 owner 和撤销语义完全不同

`/install-github-app` 是多步 GitHub 写入状态机：检查 `gh`、auth、`repo/workflow` scopes、repo 权限与现有 workflow，再由用户确认 App、workflow、auth/secret，最后可能创建 secret、branch、commit 和 PR。后台 session 没有 attached terminal 时拒绝执行。中途失败不是事务回滚；已安装 App、写入 secret 或创建 branch/commit 需要在 GitHub owner 系统撤销。

`/team-onboarding` 先在本地扫描最近 30 天 transcript，跳过超过 50 MiB 的文件，首条消息截到 200 字符，最多保留 60 个 session descriptor，再把降维数据交给只允许 `Edit(ONBOARDING.md)`、`Bash(ls *)` 和 share tool 的受限 agent。本地文档可用 Git 恢复，已分享链接和已复制内容不会随文件 rewind 失效。

`/privacy-settings` 读写 Claude 服务端账号设置，domain exclusion 可强制 false；客户端文案把 off/on 保留期说明为 30 天/5 年，这是本版显示合同，不是对所有账号和服务端删除实现的独立证明。`/web-setup` 上传本地 GitHub token，可替换现有 GitHub App OAuth；默认 environment 创建失败只 warn，credential 可已保留。`/terminal-setup` 按 terminal/OS 分流，Terminal.app 与 Zed 的部分路径先 backup 再写，其他路径可能需要手工 undo；screen-reader 模式下不关 audible bell。`/install-slack-app`、`/stickers`、`/radio` 主要只是 browser handoff，打开 URL 不证明远端安装、购买或播放完成。详见 [复杂 Slash Command 生命周期](complex-slash-command-lifecycles.md)。

## 58. 最终准确性边界

这份说明书能够确定 `2.1.235` 客户端发布物中的调用链、状态、schema、请求装配、本地工具控制、持久化、恢复、遥测出口、原生合同和受控 Probe行为。

以下对象没有存在于客户端发布物中的完整实现证据：Anthropic服务端路由、账户 abuse/risk score、真实缓存命中算法、隐藏 feature rollout、远端容量调度、模型内部推理、发布基础设施和构建前源码。它们保持 Boundary，不用客户端 header、事件名或字符串替代服务端事实。

`2.1.235` 的核心机制已经可以从“用户输入”一直追到“请求、工具、副作用、结果回灌、compact、resume、遥测和终止”。后续版本比较必须沿同一生命周期逐项比较状态、默认值、阈值、失败、成本和证据，而不是只比较 bundle大小、字段数量或 minified symbol。
