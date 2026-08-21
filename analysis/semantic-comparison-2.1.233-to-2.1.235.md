# Claude Code 2.1.233 -> 2.1.235 机制级语义对比

## 结论

`2.1.235` 不是 Agent Loop、CLI 命令或权限模型的一次重写。两版的命令/选项表、风险控制词表、模型目录、价格、tool catalog、hook event 和公开 beta 标识均无增删。真正变化集中在五类问题：

1. **上下文与缓存稳定性**：LSP 断开/重连不再让整段 prompt cache 失效；关闭 auto-compact 后触顶的诊断更可操作。
2. **交互状态正确性**：权限备注框的 Shift+Tab、快速方向键后 Enter、Vim panel 状态、Markdown 列表、多行高亮、task list 恢复和 VS Code focus 被修正。
3. **Agent 协作可靠性**：不可用的默认 Agent 不再被广告；`SendMessage` 超限从静默丢失变成发送前显式拒绝；后台云事件不再反复全量扫描和渲染。
4. **设置与持续运行**：净新增 `spellcheck`、`autoContinueAtUsageLimit`、`syncClaudeAiSkills` 三个根 setting，其中只有 `spellcheck` 被 `2.1.235` release note 明确归因。
5. **观测与远程执行**：一方事件净增 17 类、调用点增加 40 个，重点覆盖 usage-limit 自动续跑、Remote Control、device bridge 和内容块修复；遥测出口、OTEL 指标/span、Datadog 脱敏字段没有变化。

机器报告见 [comparison-2.1.233-to-2.1.235.md](comparison-2.1.233-to-2.1.235.md)。本文件只保留能由稳定字段、可达结构、精确版本探针或 release note 支撑的语义结论。

## 证据边界

| 标签 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| `Release` | 上游把某项行为明确列为 `2.1.235` 变化 | 不能单独证明具体客户端调用链 |
| `Static` | 两版发布 bundle 中存在稳定 key、分支、错误、请求字段或状态迁移 | 不能证明服务端一定接受、远程 flag 一定开启 |
| `Probe` | 同 SHA 二进制在受控输入下真实执行并产生固化输出 | 不能外推未触发平台、账户或服务端路径 |
| `Boundary` | 明确说明发布物中缺少什么证据 | 不能用“看起来相关”补齐缺口 |

本比较跨过 `2.1.234`。因此：

- [release-notes.md](release-notes.md) 中的条目可以归因到 `2.1.235`。
- 机器净差异只能说明“`2.1.233` 没有、`2.1.235` 有”，不能把所有新增字段自动归因到 `2.1.235` 单个版本。
- 当前没有单独固化 `2.1.234` release note 和二进制快照；无法按 `233 -> 234 -> 235` 拆分的项目会明确标成“中间版本归因未知”。

## 总量变化

| 面 | 2.1.233 | 2.1.235 | 含义 |
| --- | ---: | ---: | --- |
| 签名程序 | 306,981,408 B | 313,334,608 B | 增加 6,353,200 B |
| Bun payload | 237,044,184 B | 243,390,734 B | 增加 6,346,550 B |
| 主 JavaScript | 26,599,210 B | 27,305,344 B | 增加 706,134 B、1,053 行 |
| JSC bytecode | 199,100,160 B | 204,740,576 B | 增加 5,640,416 B |
| CLI command/option | 无变化 | 无变化 | 主要是既有入口内部行为变化 |
| 风险控制词表 | 93 | 93 | 模式/开关表面稳定，不代表权限 UI 没修 bug |
| 根 settings | 153 | 156 | 新增 3 个稳定 key |
| feature flags | 348 | 361 | 16 增、3 删；名称本身不等于功能结论 |
| 一方事件调用点 | 2,154 | 2,194 | 增加 40 个调用点 |
| 一方事件名 | 1,424 | 1,441 | 净增 17 个事件名 |
| API path | 95 | 99 | 净增 4 个路径 |
| storage namespace | 40 | 41 | 新增 `recording` |
| 机制证据 | 134 | 135 | 新版已补齐上下文治理证据，并拆开 beta 选择与请求字段注入 |

## 1. Settings：新增字段不是同一种开关

### 1.1 `spellcheck`：本地输入辅助，不进入模型推理

**旧行为**：`2.1.233` 根 settings schema 没有 `spellcheck`。输入框能编辑和高亮，但没有通过外部词典程序做实时拼写检查。

**新行为**：`2.1.235` 增加一个对象 setting，字段为 `enabled`、`checker`、`language`、`color`。

**来源和优先级**：只读取 user、flag 和 managed settings，使用最高优先级来源的整个 block；项目 `.claude/settings.json` 和 local `.claude/settings.local.json` 被忽略。这不是把四个子字段跨层拼起来。

**默认和 gate**：默认关闭。`checker=auto` 时按 `aspell`、`hunspell`、`ispell` 顺序寻找 PATH 中第一个可用程序；机器没有这些程序时保持关闭，不阻塞输入。

**生命周期**：检查器是长驻子进程，不是每个单词启动一次。慢批次会被跳过；进程失败后重启一次；连续失败只关闭当前会话的拼写检查。

**用户影响**：收益在输入质量和视觉反馈；模型请求体、token 预算和 prompt cache 不因拼写检查本身增加。它会增加一个本地子进程和少量输入时 CPU，但失败路径是降级关闭，不阻断 Agent Loop。

证据：[root-settings-schema.jsonl](source-inventory/root-settings-schema.jsonl) 的 `key=spellcheck`、[release-notes.md](release-notes.md) 和 [README.md](../README.md) 的拼写检查专题。

### 1.2 `autoContinueAtUsageLimit`：把 rate-limit 对话框变成持久等待状态

**净差异**：`2.1.235` schema 新增该布尔 setting，但当前证据不能确定它是在 `2.1.234` 还是 `2.1.235` 首次加入。

**关闭时**：claude.ai usage limit 终止当前推进后，对话框提供“等待重置后继续”的选择，用户决定是否驻留。

**开启时**：客户端保存等待/重置状态，到预计重置时间后自动重新进入任务，不要求用户再次提交同一提示。

**状态证据**：新增 `tengu_quota_auto_resume_armed`、`cancelled`、`fired`、`stale`、`stale_resumed`、offer 与 menu 选择事件。`fired` 记录 `early`、`rearm`、`waited_ms`；`stale` 记录 `late_by_ms`。这些字段说明它不是简单 sleep，而是有装载、过期、重武装和用户取消状态。

**用户影响**：长任务在配额窗口后可以延续，但会让进程/会话更长时间存活。恢复仍遵守 transcript、permission 和外部副作用边界；自动续跑不回滚先前已完成的工具调用。

### 1.3 `syncClaudeAiSkills`：只有 `false` 是本地控制信号

**净差异**：`2.1.233` 没有该根 key，`2.1.235` 有；中间版本归因未知。

**语义**：只有 `false` 被本地客户端接受。`true` 不能提前打开服务端尚未为账户启用的同步能力。

**作用域差异**：

- user/managed 设置为 false：停止下载；已同步 skill 对后续会话隐藏，并在下次启动移到 `.claude/skills/.trash`，按 `cleanupPeriodDays` 清理。
- local 或 `--settings` 设置为 false：只阻止当前 workspace/本次 invocation 使用和继续下载，不移动全局文件。
- project setting 不读取该字段。

**正常生命周期**：服务端启用后，已同步 skill 对会话可见，约每 10 分钟重同步；claude.ai 侧停用后，本地会删除对应同步项。

**用户影响**：这是能力分发和本地持久化控制，不是模型工具权限。禁用后 skill 不应进入新会话上下文，但不会删除普通项目 skill、plugin skill 或 bundled skill。

## 2. 上下文治理与缓存

### 2.1 LSP reconnect 不再污染整段 prompt cache

**旧故障**：LSP 在线/离线属于机器动态状态。它在会话中途变化时，如果被混入稳定 system prefix 的 cache identity，会让原本可复用的大前缀整体失效。

**新行为**：`2.1.235` release note 明确修复 LSP disconnect/reconnect 导致 whole-prompt-cache invalidation。动态机器状态与稳定 system prompt/cache breakpoint 的职责进一步分离。

**成本含义**：两版模型目录和价格不变。以 baked Sonnet `tier_3_15` 为例，每百万 token 的 5 分钟 cache write 为 3.75 美元、cache read 为 0.30 美元。若一次 reconnect 过去迫使 1M token 前缀重写，而新版保持命中，理论差额是 `3.75 - 0.30 = 3.45` 美元；实际节省取决于被缓存 token 数、TTL 和命中条件，本快照没有伪造命中率。

**不变项**：cache scope、message breakpoint、5m/1h TTL gate、tool schema cache、microcompact、precomputed compact 和 transcript 仍是不同层；修复 LSP invalidation 不等于取消其它失效条件。

### 2.2 Compact 阈值没有证据显示发生改变

补齐后的 `2.1.235` 静态证据仍显示：

- compact reservation 使用 `window - 13,000`；
- warning line 使用有效窗口再减 `20,000`；
- blocked line 使用输入上限再减 `3,000`；
- precompute 还受 `precomputeBufferFraction` 控制；
- `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 优先于 settings、client-data、experiment 和 model default。

因此本次版本差异应表述为“触顶诊断和 LSP cache invalidation 改进”，不能写成 compact 算法整体重做。

### 2.3 关闭 auto-compact 后的错误更可恢复

**旧体验**：达到 context limit 时，用户能看到失败，但错误与修复入口连接不够直接。

**新体验**：当 auto-compact 被关闭且上下文触顶，错误明确指出该状态，并链接到 `/config` 重新启用。

**边界**：这是客户端诊断和操作路径变化，不表示服务端 context window 变大，也不表示已超限请求会自动重试成功。

证据：[context-governance-and-caching.md](context-governance-and-caching.md)、`context.*` 结构化 claim 和 [release-notes.md](release-notes.md)。

## 3. Agent Loop 与多 Agent 协作

### 3.1 核心 Loop 合同保持稳定

两版均维持同一高层合同：模型流产生完整 `tool_use` block 后进入工具执行；并发安全调用可以重叠，非安全调用形成屏障；结果按 `tool_use_id` 回灌；Stop hook、maxTurns、retry/fallback 和 subagent isolation 仍由客户端控制。

没有新增/删除 CLI command、builtin tool、hook event 或 risk-control mode，因此本次变化不能描述为“Agent Loop 2.0”。变化发生在 Agent 选择、协作消息和后台事件消费的边界。

### 3.2 不可用的通用 Agent 不再被当成默认值

**旧故障**：Agent tool schema 可能广告 general-purpose default，即使当前会话的 gate、模式或可用 Agent 集合中并不存在它。省略 `subagent_type` 后会进入一个无法兑现的默认路径。

**新行为**：不存在可用默认 Agent 时，省略 `subagent_type` 会返回可见错误并列出当前可用 Agent。

**用户影响**：失败从运行后期/错误路由提前到参数选择阶段。它减少“任务被默默交给错误 Agent”的歧义，但不会自动选择一个语义相近的替代 Agent。

### 3.3 `SendMessage` 从静默丢失改为发送前拒绝

**旧故障**：跨会话消息超过 delivery limit 时可能被静默丢弃。发送方以为状态已同步，接收方却没有消息，team task、阻塞和结论会分叉。

**新行为**：发送前做大小检查，超限返回显式错误。

**状态变化**：`tool.call` 可以返回失败结果，下一轮模型能看到拒绝并选择缩短、拆分或改用文件。没有接收方 ack 的消息不再冒充成功。

**边界**：显式拒绝不保证之后的重试一定送达；它也不会撤销消息之前已经执行的外部工具副作用。

### 3.4 后台 cloud event 从全量重扫转向增量消费

`/ultrareview`、`/autofix-pr` 等长任务过去会在每次 update 时重新扫描和渲染完整事件流。`2.1.235` 避免这种重复工作，降低运行时间越长时的 CPU、内存和 TUI render 压力。

这项变化优化的是客户端事件消费，不代表 cloud worker 执行更快，也不改变远端任务所有权和网络往返。

## 4. 权限与交互状态机

### 4.1 Shift+Tab 修复是权限正确性，不只是快捷键修复

**旧故障**：permission prompt 的 comment field 中按 Shift+Tab，本意是关闭/退出备注输入，却可能批准 edit，并授予 session-wide edit permission。

**新行为**：Shift+Tab 只关闭该输入状态，不触发批准。

**风险变化**：风险控制词表仍是同样 93 项，因为 permission mode、policy key 和 sandbox gate 没有新增；真正修复的是 UI event 到 grant action 的错误映射。只看风控 token diff 会漏掉这类高价值安全修复。

### 4.2 Permission dialog 的文本、scope 和持久选项对齐

新版让展示文本、实际 grant scope 和 `don't ask again` 选项一致；如果提议内容无法完整展示，就不提供持久授权。核心原则是：用户看不完整时，不能给出比当前操作更宽的长期授权入口。

Notebook cell 删除/替换在旧内容读取失败时也会明确说明原因，不再让审批人误以为对比内容为空。

### 4.3 终端 UI 修复的是“视觉状态”和“提交状态”分叉

- 快速方向键后 Enter 使用新高亮项，不再提交旧 selection state。
- Vim 在 `ctrl+o` 详细 transcript 或关闭 panel 后保留 NORMAL mode 和 cursor。
- 第 3 层以上 Markdown 列表与换行项使用正确对齐/悬挂缩进。
- 多行 prompt 的 slash/mention/highlight 不再因 offset 漂移错位。
- 回复过程中执行 slash command 时，HTML entity 还原为真实字符。
- 有 open tasks 的 resumed session 会恢复 expanded task list 状态。
- 后台更新完成后 footer 保留 `Update installed` restart notice。
- VS Code 恢复多个 Claude panel 时不再跨 tab 抢焦点。

这些修复没有改变模型推理，但减少“屏幕显示 A、实际提交 B”和“状态恢复后 UI 假装初始态”的错误。

## 5. 本地工具与运行时

### 5.1 Embedded grep

**病态 pattern**：新版在 native macOS/Linux build 中快速失败，避免单次搜索持续消耗内存或 CPU。

**`-m N` 与 context**：与 `-A`/`-C` 组合时，达到匹配上限后仍输出正确上下文，不再因停止条件截断或错配周边行。

这改变的是内嵌 grep 实现行为，不是 Bash 工具权限。命令是否允许执行仍经过原有 schema、hook、permission、policy 和 sandbox 管线。

## 6. Remote Control、API 与持久状态

### 6.1 `claude rc` 复用 enterprise gateway gate

旧 alias 路径与交互启动的企业网关可用性检查不完全一致。新版让 `claude rc` 经过同一 availability gate，避免 alias 绕开企业环境不支持/未配置的前置判断。

这不是认证绕过修复的证明；它只证明客户端入口 gate 一致。远端账户、gateway 服务端授权和连接成功仍需运行环境证据。

### 6.2 新增 API/storage 表面

净新增 API path：

- `/api/frame/`
- `/v1/code/agent-proxy/artifact`
- `/v1/code/agent-proxy/frame`
- `/worker/record-created-pr`

storage namespace 新增 `recording`。这些稳定字符串证明客户端新增了 frame/agent-proxy/PR 记录和 recording 持久化表面，但不能仅凭路径推断服务端协议、权限或默认开启状态。

## 7. Telemetry：观测范围扩大，出口和脱敏合同稳定

### 7.1 新事件集中在哪里

净新增 17 个一方事件名，最完整的一组是 quota auto-resume：armed、cancelled、fired、offer、setting changed、stale 和 stale resumed。它们把“等待配额恢复”从一个 UI 选择拆成可观测状态机。

其它新增事件包括：

- `tengu_rc_pill_clicked`：记录 Remote Control pill 的 label 和 trigger；同时进入 Datadog allowlist。
- `tengu_content_block_healed`：记录 block type、message/request ID 与缺失 signature/text/thinking 的修复动作。
- `tengu_device_bridge_reannounce*`：记录 drain timeout、inflight、outcome、reason 和竞争状态。
- `tengu_goal_checkin_injected`：记录 active agents/shells、checkin count、defer 时间与 trigger。
- `tengu_bridge_owner_changed`、`tengu_device_bind_account`：补充 remote/device ownership 变化。

事件字段不是“堆数据”：它们分别回答触发来源、等待时长、是否过期、是否重武装、谁拥有会话、修复了哪类内容块，以及 bridge drain 是否完成。

### 7.2 哪些遥测合同没有变化

- telemetry endpoint：5 -> 5。
- OTEL metrics：8 -> 8；spans：10 -> 10；structured event callsites：52 -> 52。
- Datadog tag fields：34 -> 34；redacted fields：26 -> 26。
- 一方 environment fields：36 -> 36。
- GrowthBook key 数：6 -> 6。

因此可以确认“观测点变多”，不能声称“遥测隐私门或传输出口被放宽”。完整队列、采样、批处理、失败落盘、重试、auth fallback 和内容脱敏见 [telemetry.md](telemetry.md)。

### 7.3 Feature flag 只能当线索

feature flag 16 增、3 删，调用点增加 24。`tengu_record_created_pr_to_ccr` 等名字能形成验证假设，但大量代号没有稳定公开语义。除非能同时找到消费者分支、默认值、事件或 release note，否则不能把 flag 名直接翻译成已发布功能。

## 8. Native 模块

两版仍是 5 个 `.node`、7 个架构 slice。`audio-capture.node` 与 `image-processor.node` 的 arm64 hash 改变但文件大小相同；依赖、imports、exports、Swift project symbols 和 N-API contract 没有增删。

可以确认：原生二进制内容发生了重编译或内部变化，外部合同保持稳定。不能仅凭 hash 变化声称音频捕获、图像编码质量或权限行为改变。

兼容重建仍覆盖相同 5 个模块。23 项 original/compatible 检查通过；没有显示器、Accessibility 或 Spotlight 时记录为 `environment-boundary`，不把截图、指针查询或应用图标路径冒充已执行成功。

## 9. 明确不变项

| 不变面 | 结论 |
| --- | --- |
| CLI | command/option 无增删；升级后脚本入口兼容性较高 |
| 风控表面 | permission modes、sandbox/network/filesystem/credential/policy 词表无增删 |
| Tool catalog | builtin tool 29、known tool catalog 188，均无变化 |
| Hooks | 31 个 hook event，无变化 |
| Models | catalog 17、alias 4、pricing tier 6，均无变化 |
| Public beta IDs | 53 -> 53 |
| Telemetry transport | endpoint、OTEL metric/span、Datadog redaction/tag 无变化 |
| Native contract | exports/imports/dependencies/N-API object tree无增删 |
| Public research snapshot | public response 和 excerpt hash 无变化 |

“不变”不等于 bundle 没变化，而是这些稳定合同没有证据显示发生语义增删。压缩符号、行号、bytecode hash 和大段诊断调用点变化不能单独当成功能变化。

## 10. 如何读这次升级

如果关心 token 与成本，先读 [context-governance-and-caching.md](context-governance-and-caching.md)：本次最有价值的是 LSP reconnect 不再破坏稳定 cache prefix，而不是 compact 阈值变化。

如果关心 Agent 可靠性，读 [agent-loop.md](agent-loop.md) 和 [mcp-agents-background.md](mcp-agents-background.md)：核心 Loop 不变，修复发生在默认 Agent 解析、跨会话消息大小和后台事件消费。

如果关心安全，读 [tools-permissions-hooks.md](tools-permissions-hooks.md)：风险表面无增删，但 Shift+Tab 修复说明 UI event mapping 同样属于权限系统的一部分。

如果关心字段和遥测，读 [inventory-field-guide.md](inventory-field-guide.md) 与 [telemetry.md](telemetry.md)：先理解 `comparisonKey`、payload field、event family、allowlist 和 redaction，再看机器 diff。

## 11. 最终准确性判断

可以确定：

- 两版发布物、哈希、清单、机制证据和原生合同都已在本地验证。
- `2.1.235` release note 的 19 个条目都能放回对应客户端能力面解释。
- 三个根 setting、遥测事件、API/storage 和 native 差异来自两版 bundle 的稳定净 diff。
- 上下文治理证据已补齐到新分支，不再出现旧版 134 条、新版反而只剩 121 条的覆盖倒退。

仍然不能确定：

- 未单独快照 `2.1.234` 前，所有净新增字段的首次版本归属。
- server-side account scoring、abuse/risk model、remote flag 实际值和服务端协议实现。
- 没有 source map/debug info 时的原始 TypeScript 文件名、注释、模块边界和被 tree-shaking 删除的代码。
- `.node` hash 改变对应的原始 Anthropic Rust/Swift/C++ 提交内容；本仓库只能提供静态证据与兼容重建。

