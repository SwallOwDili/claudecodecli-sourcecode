# 2.1.235 精确二进制运行证据指南

这份文档解决一个具体问题：静态源码能说明“客户端写了哪些分支”，但不能单独说明“这个发布二进制在受控输入下实际走了哪条分支”。`analysis/runtime-probes/*.json` 因而不是测试日志堆积，而是把重要机制转换为可重复观察的状态变化。

所有探针都绑定同一目标：Claude Code `2.1.235`，发布二进制 SHA-256 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748`。模型端使用本地受控 Messages 服务，文件、设置、HOME、MCP 和 OTLP collector 均位于临时隔离环境。探针验证客户端请求装配、状态机、工具控制与本地持久化，不声称本地 mock 等价于 Anthropic 服务端。

## JSON 字段怎么读

| 字段 | 含义 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| `target` | 目标版本、二进制 SHA-256、发布文件占位路径 | 探针没有误用 PATH 中的其他版本 | 二进制来源之外的发布流水线 |
| `capturedAt` | 本次探针完成时间 | 报告不是手工抄写的无时间结果 | 未来版本行为 |
| `environment` | OS、架构、Node 版本 | 结果在哪个平台真实执行 | 其他平台自动等价 |
| `commands` | 可复现命令，敏感路径和值用稳定占位符表示 | 入口参数、开关和执行模式 | 命令字符串本身不代表分支成功 |
| `input` | mock 响应、临时文件、设置层或 collector 的受控输入 | 触发条件没有依赖真实用户环境 | 真实模型质量、账号 entitlement |
| `literalOutput` | CLI 或 collector 的归一化原始结果 | 用户或协议端实际看到什么 | 未记录的内部中间状态 |
| `observed` | 请求次数、header、模型序列、文件字节、session ID 等观察值 | 机制的状态转换和副作用 | 服务端收到请求后的内部实现 |
| `exitStatus` | 每个命令的进程退出状态 | CLI 成功、受控失败或预算终止 | 单靠 0 不能证明语义正确 |
| `checks` | 从以上字段计算的验收断言 | 报告为何判定 PASS | 断言集合之外的泛化结论 |
| `pass` | 所有要求检查是否通过 | 本报告满足当前探针合同 | 整个产品没有其他故障 |

判断顺序必须是：先确认 `target`，再读 `commands` 和 `input`，然后联合检查 `literalOutput`、`observed`、`exitStatus`，最后才看 `checks/pass`。只读一个 `pass: true` 会丢掉失败分类、请求次数和副作用边界。

## Agent Loop 与会话状态机

### 工具结果不是 UI 事件，而是下一轮模型输入

`probe.agent-loop-tool-feedback` 在第一轮让 mock 模型返回完整 `Read` tool use。CLI 读取包含 `AGENT_LOOP_FILE_MARKER` 的真实临时文件；第二个 Messages 请求同时出现原 `tool_use` 和同 ID 的 `tool_result`，最后输出 `TOOL_EXECUTION_OK`、exit 0。

这证明 `tool_use_id` 是跨“模型流 -> 本地执行 -> 下一轮模型决策”的关联键。工具卡片出现在终端不是闭环完成的充分条件；只有配对结果进入下一请求，模型才真正观察到执行结果。

### Resume、compact、fork 是三种不同变换

- `probe.resume-history`：恢复请求包含初始 prompt、初始 assistant result 和当前 prompt，证明 resume 重建持久消息历史。
- `probe.manual-compaction-boundary`：`/compact` 产生 `system:compact_boundary`，`trigger=manual`、`preTokens=104`；随后 fork 请求保留摘要，移除 compact 前 prompt、tool-use ID 和旧 assistant result。
- `probe.session-fork-identity`：fork 得到新 session ID，但保留 compact summary 与当前 fork prompt。

因此 resume 恢复的是同一 transcript 身份，compact 改写送模的逻辑历史，fork 则从现有逻辑状态创建新的持久身份。三者都不复活旧进程，也不撤销已发生的外部动作。

### Stop hook 和 maxTurns 管的是循环，不是 HTTP attempt

`probe.stop-hook-reentry` 让第一次 Stop hook 阻止结束并提供反馈。反馈进入第二个 Messages 请求，第二次模型决策成功结束。`probe.max-turns-terminal` 则设置 `maxTurns=1`：第一个模型请求选择的工具与 PostToolUse 均完成，但不会再发第二个模型请求，最终 subtype 为 `error_max_turns`、exit 1。

这两个结果把四个计数对象分开：用户 turn、Agent/model iteration、HTTP attempt、tool batch。Stop hook 可以要求再进行一次 Agent 决策；`maxTurns` 限制新的模型 iteration，却不会中途抹掉已完成的工具副作用。

## 请求、认证与缓存

### 同一个 endpoint，两种 credential 产生两种 wire shape

- `probe.request-bearer-auth`：`ANTHROPIC_AUTH_TOKEN` 产生 `Authorization: Bearer $TOKEN`，不发送 `x-api-key`。
- `probe.request-api-key-auth`：只有 `ANTHROPIC_API_KEY` 时发送 `x-api-key: $API_KEY`，不发送 `Authorization`。

这证明 credential source 在 request builder 之前已经完成选择。报告故意不保存真实 token，只保留 header 形状占位符；它验证客户端选择和装配，不验证远端凭据有效性。

### Prompt cache 开关改变实际请求体

`probe.request-cache-shape` 的默认请求包含 3 个 `cache_control`，并声明 Read schema。`probe.prompt-cache-disable` 对同类请求设置 `DISABLE_PROMPT_CACHING=1` 后计数变为 0，命令仍成功。

这证明 prompt cache 不是只有配置常量：开关会改变发出的 wire body。它仍不能证明服务器命中缓存；命中和费用需要响应 usage 的 cache token 字段。

## 设置、权限与沙箱

### 设置优先级需要运行值，而不是文件名推测

`probe.settings-layer-precedence` 构造 user、project、local 和 `--settings` 四层不同 model 值：全量加载时 flag 值 `claude-opus-4-6` 胜出；去掉 flag 后 local 值 `claude-opus-4-5` 胜出；`--setting-sources user` 后只剩 user 的 `claude-haiku-4-5`。

这个探针证明 CLI flag > local > project > user 的已触发路径。macOS managed policy 使用固定系统目录，探针没有伪造管理员目录，因此 managed > CLI 仍由静态分支与官方文档证明，报告明确保留这一平台边界。

### Hook deny 发生在工具本体之前

`probe.hook-deny-feedback` 让 PreToolUse 返回 deny。第二个模型请求收到同 ID 的 error tool result 和 hook 原因，临时文件 marker 没有出现在结果中，说明 `Read` 本体没有成功执行。拒绝是模型可观察结果，不是 Agent Loop 崩溃。

### Permission bypass 不等于绕过 OS sandbox

- `probe.sandbox-filesystem-enforcement`：在 `bypassPermissions` 下，工作区内写入成功；`denyWrite` 路径没有产生文件，工具结果为 error。
- `probe.sandbox-network-enforcement`：严格空域名表下，Bash 请求本地 HTTP 地址失败，受控 server 的 hit count 为 0。

这证明 permission decision 与 sandbox enforcement 是两层控制。前者决定是否询问/放行工具，后者限制已经启动的子进程能触及的文件和网络对象。

## Retry 与模型 fallback

### 529 和 400 不属于同一重试类别

`probe.http-retry-classification` 对 529 返回序列 `529,529,200`，CLI 共请求三次后成功；对受控 400 只请求一次并 exit 1。`CLAUDE_CODE_MAX_RETRIES=2` 表示初次尝试之外最多再进行两次，不是总请求数为二。

### Fallback 在耗尽主模型重试后切换

`probe.model-fallback-sequence` 的请求模型序列为：

```text
claude-sonnet-4-5
claude-sonnet-4-5
claude-sonnet-4-5
claude-haiku-4-5
```

前三个主模型请求收到 529，第四个请求使用 `--fallback-model` 指定的备用模型并成功。这个结果证明本路径的顺序，不应泛化为所有错误都在三次后 fallback；400、认证、计费、请求尺寸和 transport 有独立分类。

## MCP、子 Agent 与后台状态

### MCP generation refresh 有装配延迟

`probe.mcp-generation-refresh` 观察到初始化、首次 `tools/list`、工具调用、`notifications/tools/list_changed`、第二次 `tools/list` 和新增工具。`probe.mcp-refresh-delay` 进一步记录：第二个 Messages 请求仍只有旧 schema，第三个请求才出现新工具。

因此 MCP server 的工具表变化会推进 generation 并失效缓存，但不会修改已经装配或正在发送的请求。动态刷新按请求边界生效。

### 子 Agent 的启动确认不是最终结果

`probe.subagent-isolation` 观察到 child 使用自己的 prompt、工具集合和 Messages 请求，且不包含 parent prompt。`probe.subagent-notification-feedback` 记录父循环收到：

```text
tool_result:async_launched
task-notification:completed
```

第一项只证明任务已启动，第二项才携带完成结果。主 Agent 若把 async launch ACK 当作结论，会在 child 仍运行时错误结束或重复派发。

当前官方网络文档还说明 background agent 由独立 supervisor 承载。该主张已登记为 `Public`，但本组探针没有启动长期 supervisor 或证明重启后的 durability，因此不升级成后台持久化 Probe。

## 遥测与隐私

`probe.telemetry-otlp-redaction` 启动本地 `/v1/logs` HTTP/JSON collector。默认运行收到 user-prompt event，但 `user_prompt` 为 `<REDACTED>`，原 marker 不存在；设置 `OTEL_LOG_USER_PROMPTS=1` 后，第二次导出包含原 prompt marker。两次命令与 collector 均成功。

这证明了四件事：OTLP logs exporter 可达、实际使用 HTTP/JSON、prompt event 会发送、正文默认隐藏且可显式开启。它不代表一方 analytics、Datadog、error reporting 共享同一字段或同一脱敏策略；各 transport 必须分别分析。

## Doctor、更新与 Remote Control 边界

`probe.exact-binary-identity` 保证所有控制探针先核对版本和 SHA-256。`probe.lifecycle-doctor-update` 进一步观察：

- `DISABLE_UPDATES=1 claude update` 输出管理员禁用更新提示并 exit 0；
- `doctor` 报告 native `2.1.235`、commit、`darwin-arm64`、bundled search、auto-update gate 和损坏的 settings 文件；
- `doctor` 本身不启动模型会话。

`probe.remote-control-custom-endpoint-boundary` 在 `ANTHROPIC_BASE_URL` 指向受控自定义 endpoint 时，doctor 明确报告 Remote Control 只支持 `api.anthropic.com`，同时报告 feature evaluation 被非必要流量开关禁用。这个 Probe 证明“为什么不可用”的客户端诊断，不证明一次已登录的真实 Remote Control 成功连接。

## 原生兼容重建

`probe.native-original-compatible` 对原始与独立重建模块运行相同 contract 和输入，23 项行为检查全部通过。`probe.native-architecture-boundary` 明确限制：arm64 compatible 经过构建和运行，原版两个 Computer Use 模块的 x86_64 slice 只有静态证据，compatible x86_64 没有构建和执行。

匹配的 export、错误和行为合同只说明兼容实现可以替代这些已覆盖调用，不会把 `reconstructed/` 变成 Anthropic 原始 Rust/Swift/C++ 源码。

## 27 条 Probe 结论索引

| Claim ID | 报告 | 核心状态变化 |
| --- | --- | --- |
| `probe.agent-loop-tool-feedback` | `agent-loop-tool-result-resume.json` | Read 执行结果按 tool ID 回灌下一请求 |
| `probe.resume-history` | `agent-loop-tool-result-resume.json` | resume 恢复旧 prompt/result 并加入新 prompt |
| `probe.request-bearer-auth` | `runtime-controls.json` | bearer 使用 Authorization，移除 API key header |
| `probe.request-cache-shape` | `runtime-controls.json` | 默认 request 含 3 个 cache marker 和 Read schema |
| `probe.hook-deny-feedback` | `runtime-controls.json` | PreToolUse deny 阻止工具并回灌 error result |
| `probe.stop-hook-reentry` | `runtime-controls.json` | Stop block 反馈触发下一次模型决策 |
| `probe.max-turns-terminal` | `runtime-controls.json` | 工具完成后以 error_max_turns 结束，不再请求模型 |
| `probe.mcp-generation-refresh` | `mcp-refresh.json` | list_changed 触发重新 list 并注册新工具 |
| `probe.mcp-refresh-delay` | `mcp-refresh.json` | 新工具到第三个 Messages request 才可见 |
| `probe.subagent-isolation` | `subagent-loop.json` | child 有独立 prompt、tools 和 API call |
| `probe.subagent-notification-feedback` | `subagent-loop.json` | async ACK 与 completed notification 分离 |
| `probe.exact-binary-identity` | `runtime-controls.json` | 版本和发布 SHA-256 一致 |
| `probe.native-original-compatible` | `native-reconstruction.json` | 原始/兼容 arm64 contract 与 23 项行为通过 |
| `probe.native-architecture-boundary` | `native-reconstruction.json` | x86_64 只保留原版静态证据 |
| `probe.settings-layer-precedence` | `settings-resilience.json` | flag、local、project、user 运行优先级可观察 |
| `probe.http-retry-classification` | `settings-resilience.json` | 529 重试，400 不重试 |
| `probe.model-fallback-sequence` | `settings-resilience.json` | 主模型三次 529 后切备用模型 |
| `probe.telemetry-otlp-redaction` | `telemetry-otlp.json` | OTLP prompt 默认脱敏，显式开关后包含正文 |
| `probe.sandbox-filesystem-enforcement` | `sandbox-enforcement.json` | workspace 写入成功，denyWrite 不落盘 |
| `probe.sandbox-network-enforcement` | `sandbox-enforcement.json` | 空 allowlist 下目标 server 零命中 |
| `probe.manual-compaction-boundary` | `agent-loop-tool-result-resume.json` | 手工 compact 产生 boundary 并替换旧结构历史 |
| `probe.session-fork-identity` | `agent-loop-tool-result-resume.json` | fork 使用新 session ID 并继承 summary |
| `probe.checkpoint-rewind-positive` | `checkpoint-rewind.json` | Edit 后 file rewind 恢复原字节且零模型请求 |
| `probe.request-api-key-auth` | `runtime-controls.json` | API key 使用 x-api-key，移除 Authorization |
| `probe.prompt-cache-disable` | `runtime-controls.json` | 禁用 prompt caching 后 cache marker 为零 |
| `probe.lifecycle-doctor-update` | `lifecycle-doctor.json` | 更新 gate 与 doctor 多故障域诊断可达 |
| `probe.remote-control-custom-endpoint-boundary` | `lifecycle-doctor.json` | 自定义 endpoint 明确阻断 Remote Control |

## 仍然保留的边界

这些探针没有证明：真实 Anthropic 服务端的缓存命中算法、账号风控评分、远端模型路由、feature flag 实时值、Remote Control entitlement、云端 session orchestration、所有 macOS/Linux 版本的 sandbox 等价性，以及任何已在生产构建前删除的源代码。

新增版本时必须重跑同一探针合同，并比较命令、受控输入、literal output、exit status、请求序列和 required checks。只比较 `pass` 或 JSON 文件哈希，会把真正的机制变化和时间戳变化混在一起。
