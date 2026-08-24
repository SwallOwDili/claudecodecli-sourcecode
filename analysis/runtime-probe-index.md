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
| `beforeAfter` | domain roots 在命令前后的 path、mode、bytes 与 SHA-256 | dry-run 是否改写目标、失败前哪些文件已经持久化 | 未列入 root 或 CLI bootstrap 之外的系统状态 |
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

### Permission TUI 的按键结果必须落到授权范围，而不只是截图

`probe.tui-shift-tab-comment-scope` 在 `40x120` 的 `xterm-256color` PTY 中启动精确 `2.1.235` 二进制，使用隔离 HOME、配置目录、工作区和本地 Messages stub。模型侧按真实前置条件依次请求 `Read(first) -> Edit(first) -> Read(second) -> Edit(second)`；两个文件都只位于临时工作区。

第一次 Edit 对话框先按 `Tab` 进入 Yes comment，写入 `COMMENT_MARKER`，再发送终端字节 `ESC [ Z`（Shift+Tab）。此前和此后的主请求数都为 `2`，两个文件仍分别为 `FIRST_ORIGINAL`、`SECOND_ORIGINAL`：快捷键没有 settle 当前权限请求，也没有执行 Edit。随后显式按 `Enter` 才把第一个文件改为 `FIRST_CHANGED`；第二次 Edit 仍出现权限对话框且可用 `Escape` 拒绝，第二个文件保持 `SECOND_ORIGINAL`。这同时证明 Shift+Tab 没有误批准当前 Edit，也没有留下 session-wide edit grant。

`probe.tui-quick-arrow-enter-selection` 重新启动全隔离会话，在第一个权限框把 `Down` 和 `Enter` 放进同一次 PTY write。初始焦点是“仅本次允许”，Down 后的新焦点是 session `acceptEdits`；结果两个文件都变成 `*_CHANGED`，第二次 Edit 没有再次弹框，五次主请求链完整结束。若 Enter 仍读取旧 render snapshot，它只会批准第一次，第二次 Edit 必然停在权限框。因此这里验证的是 selection state 的实时读取和该 permission dialog primitive 的实际授权后果，而不是根据屏幕箭头猜测选中项。

报告有意不把另外两个 release fix 升级为 Probe：多行 highlight 需要终端模拟器重建最终 screen 和 ANSI style 坐标，原始 PTY 字节流不是规范化画面；Vim panel 恢复需要跨组件卸载/重挂载观察 mode 与 cursor 的无歧义快照。两者已有 Static 状态所有权和转换证据，但在这些观测器补齐前仍保持 Boundary。

### Embedded Grep：regex 编译、context printer 与 Agent Loop 是三个观察点

`embedded-grep.json` 先把目标锁定到 `2.1.235` 和发布 SHA-256，再证明 native executable 通过 `argv0=rg` 暴露 `ripgrep 14.1.1 (rev fdb5e06cce)`。这不是 PATH 里的系统 `rg`，也不是从 release note 推测出的版本字符串。

`probe.embedded-grep-pathological-fast-fail` 给 embedded engine 输入 `a{1,1000000000}` 和单行 fixture，外部 deadline 为 3 秒。观测结果是空 stdout、exit 2、没有 timeout，stderr 逐字为：

```text
rg: compiled regex exceeds size limit of 104857600
```

报告同时保存 elapsed milliseconds、maximum resident set size 与 peak memory footprint。本次最大 RSS 约 229 MiB，低于 512 MiB 验收线；该值包含大体积 native executable 的映射与运行时页，所以它是“进程有界完成”的证据，不是 regex heap allocation 的精确归因。

`probe.embedded-grep-max-count-context` 对同一 engine 和同一 7 行 fixture 分别执行 `-m 1 -A 2`、`-m 1 -C 2`。前者返回命中行 2 加行 3-4，后者再带行 1；第二个 match 位于行 5，没有越过 match cap。这里验证的是 searcher/context printer 的原始 stdout 和 exit status。

`probe.grep-tool-error-feedback` 再启动本地 Messages stub。首个 request 真实广告 `Grep` schema；模型先搜索 1,217-byte 长行，下一 request 收到同 tool ID 的 `long.txt:1:[Omitted long matching line]`，再执行病态 pattern，第三个 request 收到同 ID 的 `is_error` 与 compiled-size 错误，最后仍以 `EMBEDDED_GREP_TOOL_OK`、exit 0 结束。这把 engine failure 和 Claude Code 的 tool-result/Agent-Loop 行为接了起来。

有意保留的可达性边界：首个 request 的 `Grep.input_schema.properties` 没有 `-m` 或 `max_count`，因此不能让 mock 模型伪造该字段。`-m/-A/-C` 由相同精确二进制的 embedded engine 入口验证；这证明发布说明描述的 engine 能力，不证明模型通过当前 `Grep` schema 可直接设置 match cap。

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

### Plugin Skill 与 LSP 是两条不同的装载闭环

`probe.plugin-skill-load` 用 `--plugin-dir` 装入一个隔离插件。第一个 Messages request 的 Skill listing 出现 `probe-plugin:probe-skill`；模型调用 `Skill` 后，CLI 先回灌同 ID 的 `Launching skill` acknowledgement，再把 Skill 正文 marker 注入第二个 request。也就是说，Skill 的 `tool_result` 证明 dispatch 已接受，真正的指令内容另行进入下一轮上下文，二者不能混成一个字段。

`probe.plugin-lsp-roundtrip` 在同一插件中声明 stdio LSP server。首个 request 没有携带 LSP schema，符合 deferred tool surface；受控模型随后发出 `LSP` tool use 后，CLI 实际完成：

```text
initialize -> initialized -> textDocument/didOpen
-> textDocument/definition(line=0, character=0)
-> paired tool_result -> shutdown
```

工具输入使用编辑器坐标 `line=1, character=1`，server 收到协议坐标 `0,0`。最终 result 是 `PLUGIN_SKILL_LSP_OK`、exit 0。这个 Probe 证明 session plugin、Skill dispatch、LSP process 和 result feedback 的客户端闭环；它不证明任意第三方 language server 的语义正确，也不把 deferred schema 写成首轮常驻 schema。

### 子 Agent 的启动确认不是最终结果

`probe.subagent-isolation` 观察到 child 使用自己的 prompt、工具集合和 Messages 请求，且不包含 parent prompt。`probe.subagent-notification-feedback` 记录父循环收到：

```text
tool_result:async_launched
task-notification:completed
```

第一项只证明任务已启动，第二项才携带完成结果。主 Agent 若把 async launch ACK 当作结论，会在 child 仍运行时错误结束或重复派发。

当前官方网络文档还说明 background agent 由独立 supervisor 承载。该主张已登记为 `Public`，但本组探针没有启动长期 supervisor 或证明重启后的 durability，因此不升级成后台持久化 Probe。

## 遥测与隐私

`probe.telemetry-otlp-redaction` 启动本地 `/v1/logs` HTTP/JSON collector。默认运行收到 user-prompt event，但 `user_prompt` 为 `<REDACTED>`，原 marker 不存在；设置 `OTEL_LOG_USER_PROMPTS=1` 后，第二次导出包含原 prompt marker。

`probe.telemetry-raw-api-default`、`probe.telemetry-raw-api-inline` 和 `probe.telemetry-raw-api-file` 继续复用同一个 collector 和受控 Messages stub：

- 不设 `OTEL_LOG_RAW_API_BODIES` 时，普通 OTLP logs 仍导出，但没有 `api_request_body` / `api_response_body` event，request/response marker 均未进入 collector；
- 设为 `1` 时，collector 同时收到 request/response body event，两个 marker 都在 inline `body` 中；
- 设为 `file:$RAW_BODY_DIR` 时，本地写出 2 个 request JSON 和 1 个 response JSON，collector 只收到 `body_ref` 与长度，不含正文 marker。

五次 CLI 和五次 collector export 都返回 exit 0，目标二进制 SHA-256 仍为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748`。

这证明了四件事：OTLP logs exporter 可达、实际使用 HTTP/JSON、prompt event 会发送、正文默认隐藏且可显式开启。它不代表一方 analytics、Datadog、error reporting 共享同一字段或同一脱敏策略；各 transport 必须分别分析。

## Project purge 与 conversation import

[project-data-lifecycle.json](runtime-probes/project-data-lifecycle.json) 以 schema 2 保存 7 份完整 `env -i` execution contract，在互不共享的临时 HOME、配置目录和目标 cwd 中执行，目标始终是同 SHA-256 的 `2.1.235`；69/69 checks 必须全部为 true：

- `project purge --all --dry-run` exit `0`，计划删除 projects、tasks、debug、file-history 和 history 共 5 项；所有 planned/excluded fixture 的 mode、bytes 和 SHA-256 不变。`shell-snapshots/` 与 backups 只报告警告，不进入删除 plan。
- 独立 `project purge --all -y` exit `0` 并真实删除上述 5 个 owned target；shell snapshot 和 backup fixture 的 metadata/content hash 保持，CLI bootstrap 新建文件继续单列。
- JSON archive `--dry-run` exit `0`，报告 `conversations=1 messages=2 projects=1 docs=1`，目标 cwd 和 transcript root 都没有新增条目。
- 同一 JSON 去掉 dry-run 后 exit `0`，写出 1 个 `0600` transcript，user/assistant UUID 与 `parentUuid` 因果链保持；project prompt 写为 `project-instructions.md`，输入 `CLAUDE.md` 降权为 `imported-CLAUDE.md`。
- ZIP fixture 在所有真实内容写完后发现 manifest 把 2 条 message/1 个 doc 错报成 3/2。命令 exit `1` 并输出 `IMPORT_MANIFEST_MISMATCH`，但 transcript、project instructions、`imported-CLAUDE.md` 和 `imported-AGENTS.md` 全部留存。
- 离线 `import codex --dry-run` 命中 `tengu_import` 内置 false，逐字报告该 build 尚不可用并 exit `1`；fixture 和 Claude config 没有 apply 写入。真实账号 rollout 尚未验证。

Purge 场景还暴露了一个所有权细节：命令自己的 dry-run 没改 domain 数据，但普通 CLI bootstrap 创建了 `.claude.json` 和自动 backup。因此报告把 domain delta 与 startup delta 分开，避免把“purge 不删除”夸大成“整个进程绝对不落盘”。JSON/ZIP transcript 又在替换随机路径后计算 canonical bytes/hash，双跑去除 `capturedAt` 后逐字稳定。完整 fixture、literal stdout/stderr、exit、精确 path/mode/content hash、UUID parent chain 和 before/after 清单见报告；脚本为 [probe_project_data_lifecycle.mjs](../skill/claude-code-version-diff/scripts/probe_project_data_lifecycle.mjs)。

## Doctor、更新与 Remote Control 边界

`probe.exact-binary-identity` 保证所有控制探针先核对版本和 SHA-256。`probe.lifecycle-doctor-update` 进一步观察：

- `DISABLE_UPDATES=1 claude update` 输出管理员禁用更新提示并 exit 0；
- `doctor` 报告 native `2.1.235`、commit、`darwin-arm64`、bundled search、auto-update gate 和损坏的 settings 文件；
- `doctor` 本身不启动模型会话。

`probe.remote-control-custom-endpoint-boundary` 在 `ANTHROPIC_BASE_URL` 指向受控自定义 endpoint 时，doctor 明确报告 Remote Control 只支持 `api.anthropic.com`，同时报告 feature evaluation 被非必要流量开关禁用。这个 Probe 证明“为什么不可用”的客户端诊断，不证明一次已登录的真实 Remote Control 成功连接。

`probe.feature-override-unreachable` 在同一隔离环境中额外设置：

```text
CLAUDE_INTERNAL_FC_OVERRIDES={"tengu_ccr_bridge":true}
```

命令仍 exit 0，并逐字输出：

```text
- Feature-flag evaluation disabled (disabled by CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC)
- Remote Control rollout could not be verified for this account (no server response this session)
```

受控输入让在线求值关闭；若本地 override 分支可达，gate reader 会在 disabled 判断前返回 true。实际结果没有把 rollout 变成 enabled，与 readable source 中提前 `return` 和 override no-op 相互印证。这个 Probe 只证明 `2.1.235` 的该本地 override 没有激活 `tengu_ccr_bridge`，不证明真实账号的在线 flag 值。

## 原生兼容重建

`probe.native-original-compatible` 对 arm64 原始与独立重建模块运行相同 contract 和输入。报告共 23 个检查项，本次其中 22 项是真实原版/兼容对照，1 项是最低覆盖审计；22 项对照细分为 `14 exact`、`5 normalized-semantic`、`3 schema-and-invariants`，没有 `environment-boundary`。不能把覆盖审计也写成行为双跑。

第二份 `native-reconstruction-x86.json` 使用 universal Node 的 x86_64 slice 经 Rosetta 运行。其方法是 `validated-artifacts-and-runtime`：5 个 supplied compatible `.node` 均被验证为独立 regular x86_64 Mach-O、未复用原版 hash，并通过 x86_64 加载与 N-API 导出合同。Rust `x86_64-apple-darwin` target 与 Swift `--triple x86_64-apple-macosx` 只保存在 `buildRecipes`，报告没有同次构建的 literal output/exit status。发布物中只有 `computer-use-input.node` 和 `computer-use-swift.node` 含原版 x86_64 slice，因此同输入行为对照严格限制在这两个模块：19 项真实行为比较加 1 项覆盖 guard 全部 PASS。audio、image、URL 三个 compatible x86 artifact 只有 provenance/load/export 证据，不伪装成原版 x86 行为双跑。

匹配的 export、错误和行为合同只说明兼容实现可以替代这些已覆盖调用，不会把 `reconstructed/` 变成 Anthropic 原始 Rust/Swift/C++ 源码。

## 网络 Proxy、CA 与 mTLS

`network-proxy-tls.json` 使用本地 HTTPS Messages service、两个 CONNECT proxy、一日测试 CA 和 client certificate 驱动精确 `2.1.235` 二进制：

- 无 extra CA 时 literal result 为 `API Error: Unable to connect to API: Self-signed certificate detected...`，exit `1`，HTTPS server 在 HTTP 层零命中；加入 `NODE_EXTRA_CA_CERTS` 后 result 为 `NETWORK_OK`，exit `0`。
- 同时设置 `https_proxy=$A` 与 `HTTPS_PROXY=$B` 时，只有 A 收到 CONNECT；加入 `no_proxy=localhost` 后两个 proxy 的计数都不增加，请求仍为 `NETWORK_OK`。
- `https_proxy=proxy.invalid:8080` 缺 scheme 时 exit `1`，API server 零 marker，证明配置在受控请求前 fail closed。
- 加入 `CLAUDE_CODE_CLIENT_CERT/KEY` 后 result 为 `MTLS_OK`，exit `0`，server 观察到 authorized client CN=`Claude Probe Client`。

这 14 项检查只证明主 Messages HTTPS transport；不证明 Axios、undici、WebSocket、AWS、MCP、子进程或 CCR relay。OTLP HTTP logs由下一组独立报告验证。22 个专属伪造用例会拒绝改写版本/SHA、check、命令 marker、exit/result、API/proxy 命中、mTLS peer、TLS setup 或 Boundary。

## OTLP HTTP logs 的 effective network owner

`otlp-tls.json` 先用 Node客户端证明普通 HTTPS、TLS 1.2和强制 mTLS三种 collector都返回 200，再让精确 `2.1.235` 二进制跑 15 个隔离进程。每个进程都先完成受控 Messages请求并返回 `OTLP_TLS_MODEL_OK`、exit 0，因此 collector零命中不能被“业务请求没运行”解释。

最重要的结果是配置 owner 与变量表面不同。设置 signal/common `OTEL_EXPORTER_OTLP_*_CERTIFICATE` 后，collector仍零 HTTP并记录 TLS错误；换成 `NODE_EXTRA_CA_CERTS` 后收到一次 `POST /v1/logs`。OTLP client cert/key pair同样没有进入 mTLS handshake，而 `CLAUDE_CODE_CLIENT_CERT/KEY` 让 server观察到 authorized CN=`Claude OTLP Probe Client`；只给 Claude client cert不给 key时仍被 server拒绝。

Proxy臂把 `collector.invalid` 的 CONNECT定向到本地 collector，同时设置冲突的小写/大写 proxy。小写 proxy收到一次规范化 `CONNECT collector.invalid:$TLS_PORT`，大写零命中，collector POST成功。由此可见 OTLP HTTP logs实际使用 Claude注入的通用 `Kol()` agent，而不是 bundled OTLP library较低优先级的 environment agent。

30 个 required checks全部通过，26 个专属伪造分别攻击 signal CA假成功、global CA成功删除、OTLP client假发送、Claude mTLS authorization/CN、proxy owner、literal result与 Boundary，均被拒绝。`NODE_TLS_REJECT_UNAUTHORIZED=0` 只是一条诊断对照，不能作为修复。报告不覆盖 OTLP gRPC、metrics、traces、collector retention/remote delivery或 CCR relay。

## Plugin Evaluation 免费两臂 Smoke

`plugin-evaluation.json` 用一个本地插件、1 个 case、1 次 with run、1 次 without run、免费 regex grader 和本地 Messages stub 驱动精确二进制。command literal为 `plugin eval ... --ablation with-without --runs 1 --threshold 1 --no-publish --no-scaffold`，exit `0`；CLI literal输出规范化为 `Wrote $RESULT_JSON` 和 `Report: $HTML_REPORT`。

两臂分数都是 `1`、`Delta=0`、`partial=false`。with request独有 `PLUGIN_EVAL_WITH_ARM_HOOK_MARKER`，without request明确没有，证明不是只在 aggregate JSON 中换标签；JSON/HTML 均写为 mode `0644`。23 个专属伪造用例会拒绝 arm、score、Delta、partial、hook context、plugin problem、路径和 Boundary 篡改。

本 Probe 不测真实模型或插件质量，不运行 LLM/baseline paid judge，不触发 cost ceiling，也不证明 claude.ai report publish/retention；Eval 的 temp sandbox 仍不是 OS/网络隔离。

## Probe 结论索引

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
| `probe.native-original-compatible` | `native-reconstruction.json` | 原始/兼容 arm64 contract；22 项真实对照、0 项环境边界、1 项覆盖审计 |
| `probe.native-x86-build-load` | `native-reconstruction-x86.json` | 稳定 claim ID；5 个 supplied compatible x86_64 artifact 完成 provenance、Rosetta 加载和导出合同，recipe 不构成本次 build attestation |
| `probe.native-x86-original-compatible` | `native-reconstruction-x86.json` | 原版有 x86 slice 的 Input/Swift 两模块完成 19 项同输入行为对照和覆盖 guard |
| `probe.network-proxy-routing` | `network-proxy-tls.json` | 小写 proxy 优先、NO_PROXY 绕过、非法 proxy 在 API 命中前拒绝 |
| `probe.network-extra-ca` | `network-proxy-tls.json` | 自签失败 exit 1，加入 extra CA 后 Messages 请求成功 exit 0 |
| `probe.network-mtls-client-identity` | `network-proxy-tls.json` | client cert/key 进入 TLS handshake，server 观察授权 CN |
| `probe.telemetry-otlp-effective-ca-owner` | `otlp-tls.json` | OTLP专用 CA零 HTTP；`NODE_EXTRA_CA_CERTS` 使 JSON collector成功 |
| `probe.telemetry-otlp-effective-mtls-owner` | `otlp-tls.json` | OTLP client pair未发送；Claude global pair产生授权 CN |
| `probe.telemetry-otlp-proxy-routing` | `otlp-tls.json` | 外部 collector经小写 CONNECT proxy成功，大写值未使用 |
| `probe.telemetry-otlp-failure-isolation` | `otlp-tls.json` | exporter TLS失败不改变 Agent success envelope或 exit 0 |
| `probe.plugin-evaluation-free-ablation` | `plugin-evaluation.json` | with/without 各 1 run，免费 grader 都得 1，Delta 0；with 请求独有 plugin hook context |
| `probe.project-purge-dry-run` | `project-data-lifecycle.json` | purge 计划 5 项但不改 planned/excluded domain bytes；bootstrap 文件单列 |
| `probe.project-purge-positive` | `project-data-lifecycle.json` | 独立 `--all -y` 删除 5 个 owned target，保留 shell snapshot/backup 原字节并单列 bootstrap |
| `probe.project-conversation-import` | `project-data-lifecycle.json` | JSON dry-run 零 domain 写入；真实导入写 0600 transcript、父链、instructions 与降权 CLAUDE.md |
| `probe.project-import-manifest-mismatch` | `project-data-lifecycle.json` | ZIP manifest mismatch exit 1 前 transcript 与 reserved project 文件已经持久化 |
| `probe.config-import-gate` | `project-data-lifecycle.json` | 离线内置 false 阻断 config import，精确诊断且零 apply 写入 |
| `probe.settings-layer-precedence` | `settings-resilience.json` | flag、local、project、user 运行优先级可观察 |
| `probe.http-retry-classification` | `settings-resilience.json` | 529 重试，400 不重试 |
| `probe.model-fallback-sequence` | `settings-resilience.json` | 主模型三次 529 后切备用模型 |
| `probe.telemetry-otlp-redaction` | `telemetry-otlp.json` | OTLP prompt 默认脱敏，显式开关后包含正文 |
| `probe.telemetry-raw-api-default` | `telemetry-otlp.json` | raw-body gate 默认不产生 request/response body event |
| `probe.telemetry-raw-api-inline` | `telemetry-otlp.json` | inline 模式将受控 request/response 正文送入 collector |
| `probe.telemetry-raw-api-file` | `telemetry-otlp.json` | file 模式本地落正文，collector 只收 `body_ref` |
| `probe.sandbox-filesystem-enforcement` | `sandbox-enforcement.json` | workspace 写入成功，denyWrite 不落盘 |
| `probe.sandbox-network-enforcement` | `sandbox-enforcement.json` | 空 allowlist 下目标 server 零命中 |
| `probe.tui-shift-tab-comment-scope` | `tui-regressions.json` | Shift+Tab 退出备注但不执行 Edit，也不留下 session grant |
| `probe.tui-quick-arrow-enter-selection` | `tui-regressions.json` | 同批 Down+Enter 选择实时焦点，并使第二个 Edit 继承 session grant |
| `probe.manual-compaction-boundary` | `agent-loop-tool-result-resume.json` | 手工 compact 产生 boundary 并替换旧结构历史 |
| `probe.session-fork-identity` | `agent-loop-tool-result-resume.json` | fork 使用新 session ID 并继承 summary |
| `probe.checkpoint-rewind-positive` | `checkpoint-rewind.json` | Edit 后 file rewind 恢复原字节且零模型请求 |
| `probe.request-api-key-auth` | `runtime-controls.json` | API key 使用 x-api-key，移除 Authorization |
| `probe.prompt-cache-disable` | `runtime-controls.json` | 禁用 prompt caching 后 cache marker 为零 |
| `probe.lifecycle-doctor-update` | `lifecycle-doctor.json` | 更新 gate 与 doctor 多故障域诊断可达 |
| `probe.remote-control-custom-endpoint-boundary` | `lifecycle-doctor.json` | 自定义 endpoint 明确阻断 Remote Control |
| `probe.feature-override-unreachable` | `lifecycle-doctor.json` | 内部环境 override 未在 disabled gate 前把 rollout 变成 true |
| `probe.plugin-skill-load` | `plugin-skill-lsp.json` | Plugin Skill listing、dispatch acknowledgement 与正文注入分离 |
| `probe.plugin-lsp-roundtrip` | `plugin-skill-lsp.json` | deferred LSP 经 stdio 完成 1-based/0-based 坐标与结果闭环 |
| `probe.embedded-grep-pathological-fast-fail` | `embedded-grep.json` | 病态 regex 在 deadline 内以固定 compiled-size limit 和 exit 2 结束，RSS 有界 |
| `probe.embedded-grep-max-count-context` | `embedded-grep.json` | `-m 1` 停止新 match 后仍逐字完成 `-A 2` / `-C 2` context |
| `probe.grep-tool-error-feedback` | `embedded-grep.json` | 长行被明确省略，病态 regex 以配对 `is_error` 回灌后循环继续 |

## 仍然保留的边界

这些探针没有证明：真实 Anthropic 服务端的缓存命中算法、账号风控评分、远端模型路由、feature flag 实时值、Remote Control entitlement、云端 session orchestration、所有 macOS/Linux 版本的 sandbox 等价性，以及任何已在生产构建前删除的源代码。

新增版本时必须重跑同一探针合同，并比较命令、受控输入、literal output、exit status、请求序列和 required checks。只比较 `pass` 或 JSON 文件哈希，会把真正的机制变化和时间戳变化混在一起。
