# Claude Code CLI 2.1.235 深度逆向快照

本分支是 Claude Code CLI `2.1.235` 的完整发布产物逆向快照。它不是 Anthropic 内部原始 TypeScript 仓库的镜像，而是从实际发布的签名 Mach-O 可执行文件中，把仍然存在的内容最大化恢复并分类保存：逐字节 Bun 模块图、完整 JSC bytecode、可读化 JavaScript 分析视图、5 个原生模块的多架构静态分析、稳定字符串/配置/端点/风控索引，以及可长期复用的跨版本对比 skill。

> **先理解一条真实请求：** [Prompt Assembly](analysis/prompt-assembly-and-system-reminders.md) -> [Agent Loop](analysis/agent-loop.md) -> [权限与 Hooks](analysis/tools-permissions-hooks.md) -> [Context / Cache / Compact](analysis/context-governance-and-caching.md) -> [全局数据流与隐私](analysis/client-data-flow-and-privacy.md)
>
> **先看版本结论：** [2.1.235 状态边界修正](analysis/product-surface-evidence-map.md) · [技术文章总入口](ARTICLES.md) · [完整机制说明书](analysis/claude-code-2.1.235-complete-guide.md) · [全面性审计](analysis/completeness-audit.md)
>
> **外部系统与高风险状态机：** [Auto Mode](analysis/auto-mode-classifier.md) · [Plan Mode](analysis/plan-mode-and-human-approval.md) · [MCP / Agents](analysis/mcp-agents-background.md) · [Remote / Cloud](analysis/cloud-background-channels.md) · [Artifact](analysis/workflow-artifact-design.md) · [安装 / 自更新](analysis/install-update-doctor-lifecycle.md) · [Native Bridge](analysis/native-bridge-runtime.md)
>
> **逐项可检索参考：** [842/842 环境变量](analysis/environment-variable-reference.md) · [361/361 Feature key](analysis/feature-flag-reference.md) · [遥测排障场景与 1,441 个一方事件](analysis/telemetry-event-catalog.md) · [99 条 API 路径与 53 个 Beta](analysis/api-beta-route-ownership.md) · [Error/Diagnostic 684 条 exact owner](analysis/error-diagnostic-owner-index.md) · [错误与诊断机制图谱](analysis/error-diagnostic-atlas.md)

`extracted/` 永远保存未格式化、未改名的原始打包字节；`reverse/` 保存从这些字节生成的分析视图。两者不能互相替代。

## 先读什么

这个仓库同时服务两类读者：人需要理解系统为什么这样设计，比较器需要稳定、无遗漏地逐版本 diff。不要从 71 个 JSONL/TXT 文件开始读，也不要把字段数量当成技术分析。

核心专题统一采用三层阅读结构，技术细节没有被摘要替换：

| 阅读层 | 先回答什么 | 内容形态 |
| --- | --- | --- |
| 60 秒模型 | 这个机制解决什么问题、拥有哪份状态、一次成功路径怎样流动 | 读者问题、单句模型、贯穿场景、状态变化表、可编辑机制图 |
| 10 分钟机制 | gate、优先级、阈值、并发、失败、重试、恢复和用户影响 | 原有完整调用链与专题正文 |
| 证据层 | 结论如何复核、哪些仍是边界 | 源码范围、字段语义、Probe、literal result、exit status、机器清单 |

`analysis/visuals/` 中每张发布图都同时保留 Graphviz `.dot` 和渲染后的 `.svg`。图只负责建立状态模型；函数定位、数值阈值、失败分支、隐私/安全/成本影响和版本边界仍保留在正文与证据索引中。

| 入口 | 解决的问题 |
| --- | --- |
| [`analysis/product-surface-evidence-map.md`](analysis/product-surface-evidence-map.md) | **先读这一篇架构长文**：从未信任项目启动开始，用同一任务讲清能力编译、Agent Loop 四种时钟、工具分层风控、上下文治理、Telemetry、Resume 消息图、MCP/Skills/子 Agent、Artifact 未知结果和 Native/Voice；每章都解释状态 owner、失败、恢复、用户影响与设计取舍，C/Q/E/S/O 只在结尾作为 Derived 阅读索引 |
| [`analysis/product-surface-inventory-index.md`](analysis/product-surface-inventory-index.md) | **机器证据索引，不是入门文章**：由同一生成器维护 71 类 inventory 的 canonical hash、提取来源、所有权、证明层级、阅读面和当前 consumer-tracing 欠账；避免把文件数、字段数和 claim 数堆进主文 |
| [`analysis/compact-visual-guide.md`](analysis/compact-visual-guide.md) | **图文样板、最快理解一个复杂机制**：从真实场景、前后状态和三张图进入，再逐步展开 `/compact` 的 summary、消息分组、附件恢复、boundary、失败重试、版本差异和源码证据 |
| [`analysis/claude-code-2.1.235-complete-guide.md`](analysis/claude-code-2.1.235-complete-guide.md) | **首选入口、单卷完整版**：用 58 章从发布物、请求装配、Agent Loop、工具注册/权限、Plan Mode、Structured Output、Brief 用户可见输出、上下文/cache/compact、会话恢复、多 Agent、遥测、Artifact Watch、`/insights`、启动资源和复杂 Slash Command 一直讲到最终边界 |
| [`analysis/completeness-audit.md`](analysis/completeness-audit.md) | **全面性审计**：58 个能力面中 56 项 Deep、1 项 Documented、1 项 Boundary；Updater 已按目标版事务闭合，IDE 只保留 CLI bridge 的正向协议 Probe 缺口 |
| [`analysis/prompt-assembly-and-system-reminders.md`](analysis/prompt-assembly-and-system-reminders.md) | **Prompt Assembly 与 System Reminder**：top-level system、user/system context、typed attachment、mid-conversation system、文件新鲜度、compact/resume重建和cache前缀怎样编译成一次真实请求 |
| [`analysis/client-data-flow-and-privacy.md`](analysis/client-data-flow-and-privacy.md) | **全局数据流与隐私**：Messages、local transcript、Remote、1P/Datadog/Error、OTEL、Feedback/Survey、WebFetch、MCP/Hook、IDE/Chrome、Artifact/upload和Voice各自去了哪里、由谁同意、如何删除 |
| [`analysis/plan-mode-and-human-approval.md`](analysis/plan-mode-and-human-approval.md) | **Plan Mode 与人工审批**：进入批准、`prePlanMode`、只读边界、计划文件、`AskUserQuestion`、`ExitPlanMode`、批准/拒绝、AFK、SDK park、team lead 与 Ultraplan 远端审批 |
| [`analysis/structured-output-and-schema-contract.md`](analysis/structured-output-and-schema-contract.md) | **Structured Output 与 Schema 终态**：`--json-schema` 解析、AJV、strict schema、`StructuredOutput` 工具注入、失败修正轮次、tombstone/fallback 与最终 `structured_output` 选择 |
| [`analysis/artifact-watch-comment-autoreact.md`](analysis/artifact-watch-comment-autoreact.md) | **Artifact Watch 评论自动响应**：外部评论不可信数据隔离、baseline/digest、triage、只读 analyst、permission probe、60/h 配额、3 次 breaker、ack/edit/reply/resolve 竞态和远端副作用 |
| [`analysis/insights-history-analysis-pipeline.md`](analysis/insights-history-analysis-pipeline.md) | **`/insights` 历史分析管线**：transcript metadata/facet 双缓存、500/300 截断、30k/25k 分块、50 facet、7+1 模型请求、270,336 output-token 静态上限与 facet mtime 失效缺口 |
| [`analysis/cli-startup-files-plugins-deeplinks.md`](analysis/cli-startup-files-plugins-deeplinks.md) | **CLI 启动资源**：`--file` 下载落盘但不自动入模、`--plugin-url` 下载/ZIP 防护/MCP 信任，以及 `--handle-uri` argv 注入拒绝、shell-safe 构造和 prefill 不自动提交 |
| [`analysis/complex-slash-command-lifecycles.md`](analysis/complex-slash-command-lifecycles.md) | **复杂 Slash Command 生命周期**：`/install-github-app`、`/team-onboarding`、`/privacy-settings`、`/web-setup`、`/terminal-setup` 的独立 gate、状态 owner、部分成功、backup 和不可逆副作用 |
| [`analysis/auto-mode-classifier.md`](analysis/auto-mode-classifier.md) | **Auto Mode 两阶段分类器**：确定性权限前置层、可信规则来源、`$defaults`、Stage 1/2 XML verdict、fail-closed、PermissionDenied Hook、交互 fallback 与 hash-bound setup |
| [`analysis/plugin-evaluation-harness.md`](analysis/plugin-evaluation-harness.md) | **Plugin Evaluation Harness**：case/插件信任、with/without ablation、六类 grader、3 票多数、费用上限、partial/Delta 语义、scaffold 风险与 CI exit code |
| [`analysis/runtime-supervision-and-processes.md`](analysis/runtime-supervision-and-processes.md) | **Runtime Supervision**：Agent View、daemon、PTY host、worker、rendezvous、Storage job record、adopt/respawn、processWrapper、内存回收与 `asyncRewake` |
| [`analysis/enterprise-gateway-runtime.md`](analysis/enterprise-gateway-runtime.md) | **Enterprise Gateway Runtime**：OIDC/device flow、Gateway session、managed policy、provider/model 路由、CRI/JWKS、spend/Postgres、OTLP 和失败隔离 |
| [`analysis/auth-account-and-subscription-lifecycle.md`](analysis/auth-account-and-subscription-lifecycle.md) | **Auth/Account/Subscription**：CLI/TUI/SDK 登录、OAuth/token、组织校验、setup-token、logout revoke/wipe 与运行时 cache 换代 |
| [`analysis/onboarding-workspace-trust-and-safe-startup.md`](analysis/onboarding-workspace-trust-and-safe-startup.md) | **Onboarding/Workspace Trust**：项目风险扫描、persisted/session trust、trust 后重新发现，以及 safe/bare/print 启动责任边界 |
| [`analysis/thinking-effort-and-fast-mode.md`](analysis/thinking-effort-and-fast-mode.md) | **Thinking/Effort/Fast Mode**：三条控制轴、request-time 优先级、模型/组织 gate、兼容性回退、service tier 冷却与成本估算 |
| [`analysis/usage-cost-credits-and-limits.md`](analysis/usage-cost-credits-and-limits.md) | **Usage/Cost/Credits/Limits**：token 与美元账本、额度窗口、warning/checkpoint、credits 和 stale-safe auto-resume |
| [`analysis/project-purge-import-and-data-lifecycle.md`](analysis/project-purge-import-and-data-lifecycle.md) | **Project/Data Lifecycle**：purge plan、Codex/Gemini config import、conversation archive、digest/manifest 与部分完成恢复；exact-binary Probe 已覆盖 purge/JSON dry-run、真实 0600 transcript import、reserved-name 降权，以及 `IMPORT_MANIFEST_MISMATCH` exit 1 后写入仍保留 |
| [`analysis/sandbox-install-and-runtime-enforcement.md`](analysis/sandbox-install-and-runtime-enforcement.md) | **Sandbox 安装与运行**：Windows install/status 和逐命令 wrapper 两条状态机，区分安装成功、工具结果和 CLI exit status |
| [`analysis/network-proxy-ca-and-mtls.md`](analysis/network-proxy-ca-and-mtls.md) | **Proxy/CA/mTLS**：fetch/Axios/WebSocket/AWS/MCP adapter、NO_PROXY、407 helper、CA store、cert reload 与 CCR relay |
| [`analysis/active-goal-and-stop-loop.md`](analysis/active-goal-and-stop-loop.md) | **Active Goal**：`/goal` 注册 session Stop hook，未满足时回灌原因并继续，满足/不可能时清理，连续阻止有 cap |
| [`analysis/background-model-tasks-and-memory-consolidation.md`](analysis/background-model-tasks-and-memory-consolidation.md) | **后台模型任务**：Auto Dream、Away/Post-turn Summary、Prompt Suggestion、Feedback Draft 的状态 owner、成本、持久化和隐私差异 |
| [`analysis/advisor-dual-model-runtime.md`](analysis/advisor-dual-model-runtime.md) | **Advisor**：request-time model rank、server tool、流式结果、fallback 重算、wire strip 和额外 token/延迟 |
| [`analysis/ultrareview-cloud-review.md`](analysis/ultrareview-cloud-review.md) | **Ultrareview**：Git scope、diff/费用 gate、cloud session、poll/recovery、本地 `--fix` 和单条 PR comment `--post` |
| [`analysis/tool-registration-and-host-surfaces.md`](analysis/tool-registration-and-host-surfaces.md) | **80/80 工具注册调用点与宿主表面**：解释为什么 29 是人工维护的核心参考，80 是 `Yi({...})` AST 调用点，3 个动态 name expression 中两个工厂还能静态展开为 4 个名称；五类归属经 gate 后才形成一次请求的 `tools[]` |
| [`analysis/brief-mode-and-user-visible-output.md`](analysis/brief-mode-and-user-visible-output.md) | **Brief 与用户可见输出**：`--brief`、`/brief`、`defaultView=chat`、`SendUserMessage`、附件 upload lane、主视图隐藏、单次漏调修复和 Remote viewer 差异 |
| [`analysis/repl-programmatic-tool-runtime.md`](analysis/repl-programmatic-tool-runtime.md) | **REPL 程序化工具运行时**：持久 VM、内层工具完整权限管线、动态注册工具、虚拟 tool pair、timer 清理、结果重放与副作用不重做边界 |
| [`analysis/end-conversation-risk-control.md`](analysis/end-conversation-risk-control.md) | **EndConversation 风控**：发布/模型/宿主 gate、连续两次调用、主会话限制、transcript marker、abort/exit，以及 prompt 规则与客户端硬校验之间的证据边界 |
| [`analysis/remote-routines-runner-and-notifications.md`](analysis/remote-routines-runner-and-notifications.md) | **Remote Routines、Runner 与通知**：8 类远端动作、9 个 operator tool、runner spawn/requeue/health/log、100 项背压队列、90k drain、去重、ack 与最多两次 rearm |
| [`analysis/connectors-catalog-and-mcp-operators.md`](analysis/connectors-catalog-and-mcp-operators.md) | **Connector/Catalog/MCP Operators**：Connector Search/Suggest/List、Plugin/Skill 账号目录、OAuth scope expansion、suggestion 非安装、MCP refresh/wait/resource 的 live-state 语义 |
| [`analysis/claude-design-and-projects.md`](analysis/claude-design-and-projects.md) | **ClaudeDesign 与 Projects**：动态 operation catalog、project grant、预览/结果预算、Projects 五种方法、RAG 403 fallback、TOCTOU 文件上传和知识配额边界 |
| [`analysis/builtin-tools-reference.md`](analysis/builtin-tools-reference.md) | **29/29 核心终端参考手册**：逐工具解释状态 owner、副作用、持久化、失败、恢复、成本、隐私与安全；29 是维护集合，不是从完整装配数组自动推导的全部工具 |
| [`analysis/settings-resolution-and-reload.md`](analysis/settings-resolution-and-reload.md) | **Settings 解析、合并与热重载专题**：进程级 store、五层与 admin tier、四类 merge、ConfigChange、程序写入、consumer 刷新差异、remote managed settings 与 policy helper 恢复 |
| [`analysis/settings-reference.md`](analysis/settings-reference.md) | **156/156 根 Settings 全字段参考**：逐项说明类型、来源、merge、生命周期、consumer、用户影响和证据边界，并单独解释 4 个 spread |
| [`analysis/environment-variable-reference.md`](analysis/environment-variable-reference.md) | **842/842 typed 环境变量参考**：2,548/2,548 个 access 都给出 read/write/delete、lexical function、immediate role/operator/target 和位置；145 个动态下标中只有 7 个满足完整静态支配/引用合同，覆盖 22 个有限名称；138 个按 7 类主失败原因保留 source-located unresolved proof；原表达式和跨版本 comparison 投影均不变；411 个静态名称已人工收口完整合同，其中 104 项结构化绑定 122 个精确调用点的 owner、读取位置、precedence、state delta、失败边界和用户影响；502 个显式标 Semantic follow-up，80 个 typed 声明没有静态 consumer |
| [`analysis/cli-command-reference.md`](analysis/cli-command-reference.md) | **完整 CLI 命令树**：恢复 90 个 Commander/manual/fast-path 路径、alias、hidden/conditional gate、arguments/options、handler owner、副作用和失败；另列 8 个内部 worker/OS 入口，并解释为什么顶层 `--help` 会漏项 |
| [`analysis/cli-sdk-output-protocol.md`](analysis/cli-sdk-output-protocol.md) | **CLI、SDK 与输出协议专题**：区分 text/JSON/stream-json、本地 envelope、42 个 schema RPC、16 个额外 handler、46 个观察 subtype、44 个 Managed Agents event 和 103 个 slash command |
| [`analysis/plugins-skills-commands-lsp.md`](analysis/plugins-skills-commands-lsp.md) | **动态扩展生命周期**：marketplace 信任、安装/enable/session registry、Skill listing、三类 slash command、reload、MCP cache 与 LSP process/diagnostics |
| [`analysis/slash-command-reference.md`](analysis/slash-command-reference.md) | **103/103 Slash Command 全量参考**：逐命令解释 type/twin、可见性、host、gate、状态 owner、成功、失败、持久化、成本与不可逆副作用 |
| [`analysis/hooks-event-reference.md`](analysis/hooks-event-reference.md) | **31/31 Hook 事件全量参考**：事件时机、输入字段、matcher、command/HTTP/MCP runner、阻塞和修改能力、timeout、并发与后置副作用 |
| [`analysis/storage-v5-reference.md`](analysis/storage-v5-reference.md) | **32/32 Storage v5 namespace 全量参考**：typed key、scope、写入纪律、precondition、transcript legacy/V5 压实、真实 consumer、敏感度、并发与 backend 边界 |
| [`analysis/workflow-artifact-design.md`](analysis/workflow-artifact-design.md) | **Workflow、Artifact 与 Design 数据链**：确定性脚本/journal、发布身份与 TOCTOU、CSP/assets/comments/DB、build/diff/validate/upload/sidecar |
| [`analysis/feature-flags-remote-config.md`](analysis/feature-flags-remote-config.md) | **Feature Flags/Remote Config 深挖**：361 keys、498 callsites 的启用门、属性、fresh/disk/default、exposure、刷新、账号切换和 override 不可达事实 |
| [`analysis/feature-flag-reference.md`](analysis/feature-flag-reference.md) | **361/361 Feature key 逐项参考**：准确拆分 455 个可静态解析调用点（444 literal + 11 assignment-resolved）和 43 个真正动态调用点；498/498 个调用点都保留 lexical function 与 immediate role/operator/target，205 个 key 已人工收口 fallback、二次 gate、状态变化和失败边界，其中 55 项结构化绑定 58 个精确调用点；其余 156 个保留 Static immediate consumer。只有定义/导出而无 bundle 内 caller 的 `tengu_ant_yolo_equiv_strip_config` 继续留在 Semantic follow-up，不以配置字段名称制造用户行为 |
| [`analysis/tui-input-accessibility-media-ide-chrome.md`](analysis/tui-input-accessibility-media-ide-chrome.md) | **TUI、输入、无障碍、媒体、IDE 与 Chrome**：renderer/composer/spellcheck/paste/image/voice/IDE/bridge 的状态机、阈值、权限、重试和竞态 |
| [`analysis/cloud-background-channels.md`](analysis/cloud-background-channels.md) | **后台执行、Channels 与 Cloud**：Git/worktree/task、Cron/loop/Monitor/Push、Channel 队列、Remote Control、cloud/CCR/BYOC/self-hosted runner owner |
| [`analysis/technical-mechanism-atlas.md`](analysis/technical-mechanism-atlas.md) | **快速总览**：一次请求跨越的九个子系统、三条闭环、状态归属、故障表现和专题阅读路由 |
| [`analysis/public-claims-validation.md`](analysis/public-claims-validation.md) | 官方 Claude Code/Agent SDK/Engineering 原理与 `2.1.235` bundle、精确二进制探针逐项对照，防止版本倒灌 |
| [`analysis/technical-architecture.md`](analysis/technical-architecture.md) | 从用户输入到 system prompt、工具、API、权限、compact、transcript 和遥测的完整架构图 |
| [`analysis/agent-loop.md`](analysis/agent-loop.md) | Agent Loop 状态机、流中工具执行、并发屏障、工具结果反馈、Stop hook、maxTurns、fallback 和子 Agent |
| [`analysis/context-governance-and-caching.md`](analysis/context-governance-and-caching.md) | 上下文装配、多层缓存、5m/1h TTL、tool search、microcompaction、auto-compact、resume 和成本算例 |
| [`analysis/sessions-checkpoints-memory.md`](analysis/sessions-checkpoints-memory.md) | message graph、JSONL、compact boundary、resume/fork、100 个 file checkpoint、rewind 与 `MEMORY.md` 边界 |
| [`analysis/tools-permissions-hooks.md`](analysis/tools-permissions-hooks.md) | 工具从 schema 到 call 的完整控制管线，六种 permission mode、hooks、sandbox、凭据与企业 policy |
| [`analysis/mcp-agents-background.md`](analysis/mcp-agents-background.md) | MCP 动态工具表、Tool Search、子 Agent 独立上下文、后台任务、task claim、mailbox 与 worktree |
| [`analysis/resilience-and-recovery.md`](analysis/resilience-and-recovery.md) | API retry、流式降级、模型 fallback、输出修复、reactive compact、resume、rewind 与副作用边界 |
| [`analysis/models-auth-providers-request.md`](analysis/models-auth-providers-request.md) | provider 选择优先级、模型目录、OAuth/API key/cloud credentials、base URL gate 与 Messages 请求装配 |
| [`analysis/settings-feature-flags-policy.md`](analysis/settings-feature-flags-policy.md) | user/project/local/flag/policy 五层配置、字段合并语义、feature gate 与 managed-only 风控 |
| [`analysis/tui-ide-remote-cloud.md`](analysis/tui-ide-remote-cloud.md) | TUI/print/SDK、IDE 双向上下文、Remote Control 重连与附件边界、cloud/teleport ownership |
| [`analysis/install-update-doctor-lifecycle.md`](analysis/install-update-doctor-lifecycle.md) | **Native 安装与自更新完整状态机**：owner/channel/policy、manifest SHA-256、staging、原子版本发布、launcher ownership/symlink、部分成功、restart、version lock、清理、Doctor 与数据回退边界 |
| [`analysis/native-bridge-runtime.md`](analysis/native-bridge-runtime.md) | 5 个 `.node` 的 JS consumer、N-API 合同、Rust/Swift/macOS framework、生命周期与副作用 |
| [`analysis/telemetry.md`](analysis/telemetry.md) | 一方事件、OTEL、Datadog、GrowthBook、错误上报、本地日志、队列、重试和隐私门；包含 `OTEL_LOG_RAW_API_BODIES` 默认/inline/file 三模式精确二进制审计 |
| [`analysis/telemetry-event-catalog.md`](analysis/telemetry-event-catalog.md) | **场景语义索引 + 全量逐事件证据**：先用 API、工具授权、Permission UI、compact、session、MCP、后台任务、登录、错误终态和 transcript 恢复解释事件顺序、owner、字段和成功/失败状态，再保留 1,441 个静态一方事件、43 个动态调用点、Datadog/OTEL/metric/span 的逐项证据与 Boundary |
| [`analysis/api-beta-route-ownership.md`](analysis/api-beta-route-ownership.md) | **API、Beta 与路由所有权**：逐项归属 99 条 API path 与 53 个日期后缀 Beta，区分产品 consumer、发布物内 Gateway handler、SDK/依赖、prefix/allowlist、内嵌参考文本和远端 Boundary |
| [`analysis/error-diagnostic-atlas.md`](analysis/error-diagnostic-atlas.md) | **错误与诊断机制图谱**：把 4,831 个 `Error/TypeError/RangeError` 构造点和 5,403 个 `T()` diagnostic 调用点放回异常分类、局部恢复、tool result、stderr/TUI、LSP attachment、telemetry 与不可回滚副作用链；684 条 exact owner 中 Product 308、Dependency 376，9,550 仍待追 |
| [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md) | `comparisonKey`、payload spread、settings/env/model/遥测字段分别是什么意思 |
| [`analysis/source-surface.md`](analysis/source-surface.md) | 按全产品能力面查证据，区分 Observed、Derived、Compatible 和 Heuristic |
| [`analysis/mechanism-evidence.jsonl`](analysis/mechanism-evidence.jsonl) | 每条核心结论对应的 evidence class、源码 view、真实行号、anchors 或运行探针字段，供 validator/comparator 自动复核 |
| [`analysis/runtime-probe-index.md`](analysis/runtime-probe-index.md) | 30 条精确二进制 Probe 的命令、受控输入、literal output、状态变化、字段读法与证明边界 |

一次主线程请求的实际路径可以概括为：

```text
输入/resume JSONL
  -> 恢复会话消息图
  -> 装配固定 system prompt + 动态机器/项目上下文
  -> 从核心终端、条件 CLI、hosted/internal 对象和动态 registry 装配候选工具
  -> 经过 host/account/feature/session/policy/Tool Search 形成当前请求 tools[]
  -> 延迟不需要的工具 schema
  -> 规范化消息并执行 permission/policy/hook/sandbox 门控
  -> 切分 stable/org system 前缀并插入消息 cache breakpoint
  -> 构造 model/beta/thinking/tools/context-management 请求
  -> Agent Loop 流式解析 content block
  -> tool_use block 完成即进入并发/串行执行器
  -> schema、hook、permission、sandbox 门控后执行
  -> tool_result 按 ID 回灌，决定结束或下一轮模型请求
  -> 写 usage、telemetry、JSONL transcript
  -> 需要时清理旧 tool result、预计算或执行 compact
  -> 写 compact boundary，供下次 resume 修复逻辑消息链
```

这里的“多层缓存”不是一个模糊名词：进程内工具 schema/model config cache 降低本地重复计算；API prompt cache 复用 system/message 前缀；tool search 避免未使用 schema 常驻；precomputed compact cache 提前准备摘要。Transcript 和 memory 是持久状态，不是 prompt cache。每层的命中、失效和费用影响见上下文专题。

每个重要机制都按同一合同解释：它解决什么问题，拥有哪份状态，从哪里进入，调用链按什么顺序执行，受哪些 gate/优先级控制，默认值和阈值是什么，成功与失败各留下什么，什么时候失效，用户在质量、延迟、token、费用、隐私、安全和恢复上会感受到什么，以及哪些结论仍属于服务端或版本边界。公开资料只用于提出假设；本版本结论必须回到 `2.1.235` bundle 或同哈希二进制探针。31 个官方页面同时固化原始响应 hash、去噪正文 hash 与 40 条逐摘录 hash；刷新脚本还要求每条引用逐句存在于当次页面可见正文，见 [`analysis/public-sources/manifest.json`](analysis/public-sources/manifest.json)。

当前结构化机制证据共 `356` 条：`254 Static`、`52 Probe`、`33 Public`、`17 Boundary`。Static 细分为 `214 runtime`、`18 consumer`、`12 constant`、`4 surface`、`6 declaration`，共覆盖 48 个 topic；356 个 claim ID 均唯一。每条记录都必须有 topic、证据等级和可复核形状；`surface`/`declaration` 只证明命令、schema 或用户提示存在，不能替代可达 runtime/consumer。Plan Mode、Structured Output、REPL、EndConversation、Remote/Runner/Notifications、Connector/MCP、ClaudeDesign/Projects、Native updater，以及 Artifact Watch、`/insights`、CLI 启动资源、复杂 Slash Command、遥测事件目录、API/Beta owner、错误图谱、raw-body OTEL、OTLP TLS owner、Embedded Grep、TUI 权限、Project 数据生命周期和双架构 native 都维持独立 topic 或 Probe 合同，不能退回“文章存在但没有 claim 级生命周期、失败恢复和 Boundary”的状态。

19 份运行报告覆盖 Agent Loop/resume/compact、request/cache/hook/turn 控制、MCP/Subagent、Plugin Skill/LSP、settings/retry/fallback、OTEL raw-body与TLS effective owner、sandbox/rewind、doctor/Remote Control、Embedded Grep、TUI permission、Project purge/import、Messages proxy/CA/mTLS、Plugin Eval free ablation，以及 arm64 和 x86_64 两套 native 原版/兼容证据。报告分别保存 command、input、literal output、exit status、required checks 和边界，不能用总 PASS 代替逐项状态。逐项解释见 [`analysis/runtime-probe-index.md`](analysis/runtime-probe-index.md)，归一化原始结果位于 [`analysis/runtime-probes/`](analysis/runtime-probes/)。

原生重建验证输出 `native-reconstruction.json` 与 `native-reconstruction-x86.json`。arm64 的 23 个检查项由 22 项真实原版/兼容对照和 1 项最低覆盖审计组成；22 项对照细分为 `14 exact`、`5 normalized-semantic`、`3 schema-and-invariants`，本次报告的 `environment-boundary` 为 0。动态 hide 候选会先按 bundle ID 排序，再对成员和全部字段做深比较。原版公共候选 helper 固定豁免 Finder，只接受 layer 0、alpha 严格大于 `0.1` 且与目标显示器相交的窗口；这里没有 `width/height > 1` 门槛，源码中另外两处尺寸判断分别服务于窗口所属显示器和普通激活候选，不参与 hide candidate 判定。`prepareDisplay` 调用方又把 host 与 Finder 加入豁免集合，形成原版保留的冗余双保险。`previewHideSet` 的调用方不另加 Finder，但同样经过公共 helper，并把可选 display ID 解析成指定显示器；ID 缺失或无效时回退主显示器。screenshot 另用精确的 8 项系统界面 bundle ID 白名单，其中包含 loginwindow，但不包含 Finder。full/region screenshot 比较字段、请求尺寸、显示器元数据、规范 Base64 和 JPEG 首尾标记，并分别交给原版/重建版 image processor 实际解码；格式必须为 JPEG，解码宽高必须等于截图返回值，但不比较实时桌面的连续帧字节。只有双方返回同一条已知 TCC/ScreenCaptureKit 边界时才记 `environment-boundary`，一边成功、一边失败或错误文本漂移都会失败。构建门会从 arm64/x86_64 原版 Mach-O 的静态数组对象逐项解码 8 个 Swift String，并核对数组初始化、`computeExcludedApps -> Set.contains` 消费链、full/region nil 分支、cstring 地址和 79/75 字节长度；兼容源码还按函数分别绑定 full/region 文本、`captureScreen` 对 `systemChromeBundleIds` 的实际 union 和 `failureMessage` catch，内部故障注入会证明删掉消费链或 catch 都被拒绝。x86 报告的方法是 `validated-artifacts-and-runtime`：它证明 supplied compatible 文件是独立 regular x86_64 Mach-O、未复用原版 hash，并在 Rosetta x86 Node 下完成 5/5 加载与导出合同；发布物真正含 x86 slice 的 Input/Swift 两模块再完成 19 项同输入行为对照和 1 项覆盖 guard。Rust target 和 Swift triple 只记录为 build recipe，报告没有同次 build output/status。audio、image、URL 没有 original x86 slice，所以不能外推原版 x86 行为。两个报告都在比较前使旧结果失效，并以临时文件、`fsync`、rename 原子写入。

## 快照信息

| 项目 | 值 |
| --- | --- |
| Git 分支 | `2.1.235` |
| 本机 CLI 输出 | `2.1.235 (Claude Code)` |
| 原始程序 | arm64 Mach-O，`313,334,608` 字节 |
| 原始程序 SHA-256 | `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748` |
| 代码签名 | Anthropic PBC，Team ID `Q6L2SF6YDW` |
| Bun 载荷 | 从文件偏移 `69,107,720` 开始，共 `243,390,734` 字节 |
| 模块表 | 15 个文件，每项 52 字节 |
| 实际解包内容 | `38,648,719` 字节 |
| 主 JavaScript | `27,305,344` 字节，65,943 行 |
| 主源码 SHA-256 | `22642ddc2aa33ff16a5ee3c5a5bffb14f03c270f0047b4e5e40ba6a22efbeb8e` |
| JSC bytecode | `204,740,576` 字节，SHA-256 `7b21c8166859f877db611d1aa3b22754b1777faa878b4ab58bb752f0f432da59` |
| bytecode 提交形式 | gzip `47,461,235` 字节，SHA-256 `8f846bf9698cb7d998e951d18b10b36e2ee8ea0d85d136a7b5d671926192d611` |
| 可读化 JavaScript | `34,418,467` 字节，638,179 行，SHA-256 `99c8608118d643802dbca7bf86b031bb3f565fb78bad093494a841de3e6783b4` |
| 原生模块逆向 | 5 个 `.node`，共 7 个架构 slice |
| 解包工具 | `bun-unpacker 0.10.1`，提交 `a1bdf5488e16b41792062d60bb52d72c1c5326ea` |
| 解包模式 | `--path-patching false`，不改写打包字节 |

完整机器可读记录见 [`analysis/version.json`](analysis/version.json)。所有内嵌文件的偏移、大小、类型和哈希见 [`analysis/unpack-manifest.json`](analysis/unpack-manifest.json)。

## 目录结构

```text
.
|-- VERSION
|-- README.md
|-- ARTICLES.md                       技术文章总入口
|-- extracted/
|   |-- cli.js                         Claude Code 主应用 bundle
|   |-- *-processor.js / *-capture.js 原生模块加载器
|   |-- *.node                         图像、音频、URL、Computer Use 原生桥接
|   |-- chart.umd.min.js               Chart.js 渲染运行时
|   |-- hljsBundle.generated.min.js    Highlight.js 语法高亮运行时
|   |-- mermaid.min.js                 Mermaid 渲染运行时
|   `-- payload.template.html.asset    Artifact/报告使用的 HTML 载荷
|-- analysis/
|   |-- claude-code-2.1.235-complete-guide.md 单卷完整机制说明书
|   |-- version.json                   二进制与解包元数据
|   |-- unpack-manifest.json           每个文件的偏移和哈希
|   |-- release-notes.md               2.1.235 官方变更记录
|   |-- cli-surface.txt                用于 diff 的标准化 CLI 表面
|   |-- cli-command-inventory.json     90 个完整命令路径、gate、owner、副作用与失败合同
|   |-- cli-command-reference.md       Commander、fast path、manual parser 完整命令树
|   |-- risk-control-surface.txt        权限、沙箱、凭据和企业策略风控表面
|   |-- technical-mechanism-atlas.md    九层运行机制总图与问题导向阅读路由
|   |-- public-claims-validation.md     官方原理、bundle 证据和运行探针对照
|   |-- mechanism-evidence.jsonl        结论到源码范围/anchor/探针字段的结构化证据合同
|   |-- public-sources/manifest.json    官方页面响应、去噪正文与逐摘录 SHA-256
|   |-- public-source-excerpts.md       与本版验证问题对应的固定官方摘录
|   |-- runtime-probe-index.md          30 条精确二进制探针的人类解释与字段指南
|   |-- compact-visual-guide.md         /compact 的读者优先图文机制样板
|   |-- auto-mode-classifier.md         Auto Mode 两阶段权限分类与 fail-closed
|   |-- plugin-evaluation-harness.md    Plugin Eval ablation、grader 与报告合同
|   |-- runtime-supervision-and-processes.md daemon、PTY、worker 与恢复监督
|   |-- enterprise-gateway-runtime.md   身份、策略、路由、花费与遥测网关
|   |-- completeness-audit.md           58 个能力面的全面性审计与收口合同
|   |-- auth-account-and-subscription-lifecycle.md 登录、账号、组织、订阅和 token 生命周期
|   |-- onboarding-workspace-trust-and-safe-startup.md 首次启动、项目信任和安全模式
|   |-- thinking-effort-and-fast-mode.md Thinking、Effort、Fast Mode 请求控制
|   |-- usage-cost-credits-and-limits.md token、成本、额度、credits 和自动续跑
|   |-- project-purge-import-and-data-lifecycle.md 项目清理、配置/会话导入和部分完成
|   |-- sandbox-install-and-runtime-enforcement.md sandbox 安装态与逐命令运行态
|   |-- network-proxy-ca-and-mtls.md    transport proxy、CA、mTLS 和 CCR relay
|   |-- active-goal-and-stop-loop.md    `/goal`、Stop hook 和目标完成状态机
|   |-- background-model-tasks-and-memory-consolidation.md 后台摘要、建议、反馈和长期记忆
|   |-- advisor-dual-model-runtime.md   Advisor server tool 与 fallback/strip
|   |-- ultrareview-cloud-review.md     云端 review、本地 fix 和受限 PR post
|   |-- product-surface-evidence-map.md 模型提案权、本地裁决、九条机制主线与 Derived 阅读索引
|   |-- product-surface-inventory-index.md 71 类机器证据的三轴分类、哈希与语义欠账
|   |-- tool-registration-and-host-surfaces.md 80 个 Yi 注册调用点、工厂展开、分类、gate 与请求表面
|   |-- brief-mode-and-user-visible-output.md Brief 主视图、附件与漏调修复
|   |-- plan-mode-and-human-approval.md Plan Mode、计划文件与人工批准/拒绝
|   |-- structured-output-and-schema-contract.md JSON Schema、强制收尾工具与结构化终态
|   |-- repl-programmatic-tool-runtime.md 持久 VM、内层工具管线与结果重放
|   |-- end-conversation-risk-control.md 双调用确认、abort 与结束会话风控边界
|   |-- remote-routines-runner-and-notifications.md 远端例程、runner operator 与通知背压
|   |-- connectors-catalog-and-mcp-operators.md 账号目录、OAuth scope 与 MCP operators
|   |-- claude-design-and-projects.md    Design operation 与 Projects 数据生命周期
|   |-- artifact-watch-comment-autoreact.md 评论 watch、只读分析与受控远端写入
|   |-- insights-history-analysis-pipeline.md transcript、facet cache 与报告生成
|   |-- cli-startup-files-plugins-deeplinks.md file/plugin/deep-link 启动资源
|   |-- complex-slash-command-lifecycles.md GitHub、隐私、Web 与终端命令状态机
|   |-- builtin-tools-reference.md      29 项人工维护核心终端 reference 的逐项机制
|   |-- settings-reference.md           156 个 direct root setting 的全字段参考
|   |-- cli-sdk-output-protocol.md      CLI/SDK 输入输出、control 与 event 协议
|   |-- plugins-skills-commands-lsp.md  插件、Skill、命令与 LSP 动态扩展生命周期
|   |-- slash-command-reference.md      103 个 slash command 的全量生命周期参考
|   |-- hooks-event-reference.md        31 个 Hook 事件的字段、时机与阻塞合同
|   |-- storage-v5-reference.md         32 个 Storage v5 namespace 的逐项参考
|   |-- workflow-artifact-design.md     Workflow、Artifact 与 Design 数据链
|   |-- feature-flags-remote-config.md  Feature flag、remote eval、缓存与刷新
|   |-- tui-input-accessibility-media-ide-chrome.md 输入、媒体、IDE 与 Chrome 状态机
|   |-- cloud-background-channels.md    后台、Channels、Remote/Cloud owner
|   |-- visuals/                        可复现的 Graphviz 图表源文件与 SVG
|   |-- technical-architecture.md       面向人的完整技术架构导读
|   |-- agent-loop.md                   Agent Loop 状态机、工具调度和终止语义
|   |-- context-governance-and-caching.md 上下文治理、多层缓存、压缩与恢复
|   |-- sessions-checkpoints-memory.md  会话图、JSONL、checkpoint、rewind、memory
|   |-- tools-permissions-hooks.md       工具合同、权限、hooks、sandbox、policy
|   |-- mcp-agents-background.md        MCP、Tool Search、Agents、task 与 mailbox
|   |-- resilience-and-recovery.md      retry/fallback/compact/resume/副作用恢复
|   |-- models-auth-providers-request.md 模型、认证、provider 与请求装配
|   |-- settings-feature-flags-policy.md settings 来源、feature gate 与 managed policy
|   |-- tui-ide-remote-cloud.md         TUI、IDE、Remote Control 与 cloud session
|   |-- install-update-doctor-lifecycle.md 安装、更新、doctor 与版本生命周期
|   |-- native-bridge-runtime.md        JavaScript、N-API 与 Rust/Swift native bridge
|   |-- runtime-probes/                 精确版本正向运行探针的归一化结果
|   |-- telemetry.md                   遥测、日志、重试、隐私和诊断架构
|   |-- telemetry-event-catalog.md     排障场景语义索引 + 1,441 个一方事件与 OTEL/Datadog 逐项证据
|   |-- api-beta-route-ownership.md    99 条 API path 与 53 个 Beta 的 owner 归属
|   |-- error-diagnostic-atlas.md      异常、恢复、日志和诊断出口图谱
|   |-- inventory-field-guide.md        JSONL/settings/env/model/遥测字段字典
|   |-- source-surface.md              全产品能力面和证据边界
|   `-- source-inventory/              71 类确定性机器清单及逐文件哈希
|-- reverse/
|   |-- summary.json                   深度逆向机器摘要
|   |-- manifest.json                  全部派生产物的大小与 SHA-256
|   |-- bytecode/                      完整 JSC bytecode 与字符串
|   |-- javascript/                    可读化 JS 分析视图
|   |-- index/                         稳定标识符和原生 API 对比索引
|   `-- native/<module>.node/<arch>/   符号、依赖、段表和反汇编
|-- reconstructed/                    5 个原生模块的可编译 Rust/Swift 兼容重建
`-- skill/claude-code-version-diff/    可复用的快照、深度逆向与版本对比 skill
```

## 机器证据层：一次性全量静态提取

下面的计数表是完整性索引，不是阅读入口。字段含义先看 [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md)，系统行为先看上面的机制总图和专题文档。

除 packed bytes、bytecode、native reverse 和人工能力说明外，本分支还从 canonical `extracted/cli.js` 确定性生成 71 类机器清单。清单不是挑选出来的“亮点”，而是后续每个版本必须重跑和逐项 diff 的归档合同。

| 能力面 | 本版本计数 | 机器证据 |
| --- | --- | --- |
| 环境访问 | 并集 1,300；2,548 个逐调用点记录；dynamic `process.env[...]` 143；typed schema 842；观测 schema 71、默认表达式 23 | [`environment-access-callsites.jsonl`](analysis/source-inventory/environment-access-callsites.jsonl)、[`environment-schema.jsonl`](analysis/source-inventory/environment-schema.jsonl) |
| 一方遥测 | `H` 2,162、`Fv` 32，共 2,194 个调用点；静态事件 1,441；动态模板 3；event-field 1,441；`tengu_*` 1,939 | [`first-party-event-callsites.jsonl`](analysis/source-inventory/first-party-event-callsites.jsonl)、[`first-party-events.txt`](analysis/source-inventory/first-party-events.txt) |
| 第三方观测 | OTEL event 26、metric 8、span 10；Datadog allowlist 181、tag 34、删除字段 26 | [`third-party-otel-events.txt`](analysis/source-inventory/third-party-otel-events.txt)、[`otel-metrics.tsv`](analysis/source-inventory/otel-metrics.tsv)、[`datadog-forwarded-events.txt`](analysis/source-inventory/datadog-forwarded-events.txt) |
| 动态观测调用 | `Nd` 52；feature `et` 498；GrowthBook `CB` 12；动态/变量参数和 unresolved spread 全部保留 | [`otel-event-callsites.jsonl`](analysis/source-inventory/otel-event-callsites.jsonl)、[`feature-flag-callsites.jsonl`](analysis/source-inventory/feature-flag-callsites.jsonl)、[`growthbook-callsites.jsonl`](analysis/source-inventory/growthbook-callsites.jsonl) |
| Settings/schema | 根 settings 156；160 条结构化 schema；typed env 842；schema property 1,165；description 1,150；enum group 201 | [`root-settings-schema.jsonl`](analysis/source-inventory/root-settings-schema.jsonl)、[`environment-schema.jsonl`](analysis/source-inventory/environment-schema.jsonl) |
| 工具与命令 | built-in tool 29；tool registration 80（77 静态名、3 动态名）；known-tool catalog 188；named component 182；slash command 103 | [`tool-registrations.jsonl`](analysis/source-inventory/tool-registrations.jsonl)、[`known-tool-catalog.txt`](analysis/source-inventory/known-tool-catalog.txt)、[`slash-command-identifiers.txt`](analysis/source-inventory/slash-command-identifiers.txt) |
| 协议与 hooks | SDK control subtype 89；output protocol event 44；hook event 31 | [`sdk-control-subtypes.txt`](analysis/source-inventory/sdk-control-subtypes.txt)、[`hook-events.txt`](analysis/source-inventory/hook-events.txt) |
| 模型与 beta | 完整 model catalog 17；pricing tier 6；alias 4；model literal 37；date-suffixed beta/API version 53 | [`model-catalog.jsonl`](analysis/source-inventory/model-catalog.jsonl)、[`model-pricing-tiers.jsonl`](analysis/source-inventory/model-pricing-tiers.jsonl) |
| API/runtime | API path 99；API/path template 119；HTTP method route 19；runtime require 54 | [`api-paths.txt`](analysis/source-inventory/api-paths.txt)、[`api-path-templates.jsonl`](analysis/source-inventory/api-path-templates.jsonl) |
| 存储 | Claude storage namespace 32；全 bundle namespace 41；用户配置目录名 13 | [`claude-storage-namespaces.txt`](analysis/source-inventory/claude-storage-namespaces.txt)、[`storage-namespaces.txt`](analysis/source-inventory/storage-namespaces.txt) |
| 错误与诊断 | Error/TypeError/RangeError 调用 4,831，其中模板/表达式 1,526；`T()` 调用 5,403，其中模板/表达式 4,438 | [`error-message-callsites.jsonl`](analysis/source-inventory/error-message-callsites.jsonl)、[`diagnostic-message-callsites.jsonl`](analysis/source-inventory/diagnostic-message-callsites.jsonl) |
| 全词法表面 | quoted string 260,838 次、85,095 个唯一值；template 30,114 次、25,187 个唯一值 | [`static-string-literals.jsonl`](analysis/source-inventory/static-string-literals.jsonl)、[`template-literals.jsonl`](analysis/source-inventory/template-literals.jsonl) |
| 网络 | URL 557；URL template 236；API/path template 119；归一化 endpoint host 179 | [`urls.txt`](analysis/source-inventory/urls.txt)、[`url-templates.jsonl`](analysis/source-inventory/url-templates.jsonl)、[`endpoint-hosts.txt`](analysis/source-inventory/endpoint-hosts.txt) |

71 类清单的逐项表、定义和证据等级见 [`analysis/source-surface.md`](analysis/source-surface.md)，字段逐项解释见 [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md)。format v5 提取器固定使用仓库内置 Acorn `8.15.0` 解析整个 canonical bundle，精确定位调用、参数、词法作用域、赋值、字符串、模板、环境访问和同工厂工具注册调用点；JSONL 用稳定的 `comparisonKey` / `comparisonValue` 做跨版本语义比较，offset/line 只作定位证据。环境、schema、namespace、named component 等广义集合会混入依赖和内嵌文档，因此仍明确标为 heuristic/candidate。

`summary.json` 的完成审计确认：目标调用点全部记录、全部词法字符串/模板均计数、动态表达式保留、根 settings 的 key 与结构化行一致、模型目录完整解析，`knownStaticExtractionGaps` 为空。这里的“完成”指发布 bundle 中仍存在的静态信息；远程配置返回值、用户文件/环境的运行时值、服务端规则，以及构建前已经删除的源码不在发布产物中。

校验器会在临时目录重新执行提取器，比较 `summary.json`、canonical source hash、文件集合、每个文件内容、行数、大小和 SHA-256。手改清单、漏跑生成器或 source 变化后未更新清单都会失败。

## 完整逆向包含什么

### 1. 原始 Bun 模块图

`extracted/` 是最重要的保真基线。15 个文件全部按可执行文件中的 packed bytes 保存，清单哈希逐项一致：主应用 bundle、5 个原生 loader、5 个 `.node`、Chart.js、Highlight.js、Mermaid 和 HTML payload。主模块没有经过 prettier、变量改名或人工拆分。

### 2. 完整 JSC bytecode

`reverse/bytecode/cli.jsc.gz` 是可执行文件偏移 `69,107,840` 处、长度 `204,740,576` 的完整 JavaScriptCore bytecode cache，使用 gzip level 9、mtime 0 确定性压缩。校验器会流式解压并重新计算原始 SHA-256，证明提交文件可以无损恢复原 bytecode。

同时保存 `strings.txt.gz`，用于搜索 JSC 中保留的函数名、配置键、错误消息和运行时标识符。bytecode 是和 Bun/JSC 版本、CPU 架构绑定的执行缓存，不是另一份 TypeScript 源码，但它是发布程序实际携带内容的一部分，现已完整纳入快照。

### 3. 可读化 JavaScript

`reverse/javascript/cli.readable.js` 使用 `esbuild 0.25.10` 对原始 bundle 重新解析并展开为 638,179 行，便于定位调用链、分支和常量。它的角色是分析视图，原始比较基线仍然是 `extracted/cli.js`。

解析验证确认可读版和原始版的 538 个 `ANTHROPIC_*`/`CLAUDE_CODE_*` 标识符集合一致，endpoint host 集合一致。esbuild 可重新解析生成文件，并保留了原 bundle 的 3 个静态警告：一个永远不成立的 `typeof x === "null"` 分支、两个重复的 DOM class member。stock Node 的语法检查不适用于 bundle 中 Bun 支持的 `using` 语法。

### 4. 五个原生模块

每个 `.node` 都保存了文件类型、UUID、签名状态、Mach-O header/load commands、动态库依赖、导入/导出符号、完整符号表、字符串、Objective-C runtime 数据、间接符号和 text section 反汇编。universal 文件分别分析 x86-64 和 arm64：

- `audio-capture.node`：arm64 Rust/N-API 模块。字符串恢复出录音、播放、状态查询、写入播放数据和麦克风授权接口，并能看到 CoreAudio/AudioUnit 调用。
- `image-processor.node`：arm64 Rust/N-API 模块。恢复出 `process_image`、`ImageProcessor`、剪贴板图像读取/探测、resize/fit/withoutEnlargement、JPEG/PNG/GIF/TIFF/WebP 等格式路径和 CoreGraphics/ImageIO 依赖。
- `url-handler.node`：arm64 Rust/N-API 模块。恢复出 `wait_for_url_event` / `waitForUrlEvent` 和 macOS Apple Event handler 路径。
- `computer-use-input.node`：x86-64 + arm64 Rust/N-API 模块。恢复出文本输入、按键按下/释放/组合键、鼠标移动/按钮/滚轮/位置和辅助功能权限处理，底层直接导入 `CGEvent*`。
- `computer-use-swift.node`：x86-64 + arm64 Swift/N-API 模块。每个 slice 保留 1,237 个 Swift 符号；demangle 后可以看到屏幕区域捕获、窗口/显示器选择、允许应用过滤、JPEG 质量、缩放结果、已安装应用、ESC event tap 和 bundle ID 解析等实现结构。

### 5. 可跨版本稳定索引

`reverse/index/` 不是简单的全文字符串 dump，而是用于版本差异的归一化集合：

- 环境变量和 feature identifiers；
- 完整 URL 与 endpoint host；
- probable dotted config keys（启发式集合，单独标明，不冒充 schema）；
- 打包残留的源码/构建路径；
- 原生架构、依赖、全部 import/export、N-API import；
- 仅属于 `ComputerUseSwift` 的 demangled project symbols；
- 标准化 CLI option/command surface。

地址变化和整块反汇编变化噪声很大；长期对比优先使用这些索引，再回到压缩的完整报告确认实现细节。

### 6. 可编译的原生源码重建

[`reconstructed/`](reconstructed/) 在静态逆向证据之上，提供 5 个 `.node` 模块的可编译 Rust/Swift 重建：4 个 Rust crate 和 1 个 Swift Package。它们不是从调试信息直接导出的原文件，而是按 `Observed`、`Derived`、`Compatible` 三类证据编写，并用原版模块做接口与行为双跑。

已经恢复和验证的细节包括：

- 5 个模块的完整 N-API 导出和 `computerUse` 嵌套对象树；
- 图像链式 API、一次性消费错误，以及固定输入 JPEG/PNG/WebP 的逐字节一致输出；
- 输入模块空组合键、非法 key/action/button/axis 的原版错误文本；
- AVFoundation 麦克风授权查询、NSWorkspace 前台应用、GURL Apple Event 超时；
- Spotlight 本地化应用列表、重复项保留、64x64 PNG 图标、窗口命中和隐藏预览；
- ScreenCaptureKit 全屏/区域截图的 Promise、字段、尺寸和裸 JPEG base64。

验证脚本每次创建新的 `.node` 加载目录，不覆盖已映射的 Mach-O：

```bash
reconstructed/scripts/build_and_validate.sh extracted /tmp
```

当前 arm64 macOS 实测为 5 个模块契约和 23/23 报告项通过，其中 22 项是真实原版/兼容对照、1 项是最低覆盖审计，本次环境边界为 0。x86_64/Rosetta 对 supplied compatible artifacts 完成 5/5 provenance/load/export contract，原版有 x86 slice 的 Input/Swift 两模块完成 20/20 行为/覆盖检查；报告不证明这些 artifact 在同次采集中由 build recipe 新鲜构建。比较器仍保留 screenshot 的 TCC/ScreenCaptureKit 环境边界分支。详细源码边界和逐模块证据见 [`reconstructed/EVIDENCE.md`](reconstructed/EVIDENCE.md)。

## 2.1.235 的版本变化

### 输入框拼写检查

本版本增加了可选的实时拼写检查。实现可在 [`extracted/cli.js`](extracted/cli.js) 中检索 `spellcheck`、`aspell`、`hunspell` 和 `ispell`：

- 自动按 `aspell`、`hunspell`、`ispell` 顺序探测，也支持显式指定检查器。
- 配置包含 `spellcheck.enabled`、`spellcheck.checker`、`spellcheck.language` 和 `spellcheck.color`。
- `language` 只接受普通词典名称，并分别传给 `aspell --lang`、`hunspell -d` 或 `ispell -d`。
- 拼错的单词会显示下划线，颜色支持终端颜色名、RGB/hex、ANSI-256 和 ANSI 命名颜色。
- 检查器以长驻子进程运行，使用 Ispell `-a` 协议，不会为每个单词启动一个新进程。
- 对响应设置超时；慢批次会被跳过；进程失败后重启一次；连续失败后只关闭本次会话的拼写检查。
- 项目级和 local 级 `spellcheck` 配置会被忽略，这项配置被限定为用户级设置。

### Prompt Cache 与 LSP

语言服务器在会话中途断开或重连时，不再让整个 prompt cache 失效。LSP 在线状态属于机器动态状态，而长会话中稳定、昂贵的 prompt 前缀可以继续复用。

### 终端渲染与输入正确性

- Markdown 列表在第 3 层及更深层级时能够正确对齐。
- 自动换行的列表项使用悬挂缩进。
- 多行输入中的 slash command、关键词和 mention 高亮不再发生字符偏移。
- 快速按方向键后紧接 Enter，会选择屏幕上当前高亮项，不再选择旧状态。
- Vim NORMAL 模式和光标位置在切换详细 transcript 或关闭面板后保持不变。
- Claude 回复过程中执行 slash command 时，HTML entity 会被还原成实际字符。

### 权限与审批

- 在权限弹窗的备注输入框中按 Shift+Tab，只关闭输入框，不再误触发编辑批准并授予整次会话编辑权限。
- 权限弹窗的说明文字、授权范围和 `don't ask again` 选项保持一致。
- 当提议内容无法完整展示时，不提供持久授权选项。
- Notebook 单元格删除/替换审批无法读取旧内容时，会明确说明原因，不再静默省略旧内容。

### Agent、云任务与跨会话消息

- 当会话中不存在通用默认 Agent 时，省略 `subagent_type` 会明确报错并列出可用 Agent。
- `/ultrareview`、`/autofix-pr` 等后台云任务不再在每次更新时重新扫描和渲染完整事件流，降低长任务的 CPU 和内存增长。
- `SendMessage` 在发送前检查跨会话消息大小，超限时返回可见错误，不再静默丢弃。
- `claude rc` 与交互式 Remote Control 启动使用同一套企业网关可用性检查。

### 原生工具与细节修复

- 内嵌 `grep` 遇到病态模式时会快速失败，不再持续耗尽内存。
- `grep -m N` 与 `-A`/`-C` 组合时能够返回正确的上下文。
- 达到上下文上限且 auto-compact 被关闭时，错误会明确说明并提示到 `/config` 重新启用。
- 后台自动更新完成后，输入框底部会保留 `Update installed` 重启提示。
- 恢复仍有未完成任务的会话时，`ctrl+t` 任务列表会恢复之前的展开状态。
- VS Code 恢复多个 Claude 面板时，不再在标签页之间自动抢焦点。

官方原始条目保存在 [`analysis/release-notes.md`](analysis/release-notes.md)。

本分支只陈述 `2.1.235` 本身能由 release note、bundle 和精确二进制 Probe 证明的行为。跨版本差异应在拥有两个完整版本分支后由长期 skill 重新生成，不能把其它版本的临时分析混入本版阅读入口。

## 本版本的完整能力面

### 会话与 Agent 生命周期

- 支持交互式终端会话和非交互 `--print` 模式。
- 支持按 ID resume、继续当前目录最近会话、resume 时 fork、显式 session ID，以及关闭会话持久化。
- 支持会话命名、后台 Agent、可脚本化的 `agents --json`、Git worktree 隔离，以及 tmux/iTerm2 worktree 窗格。
- 支持自定义 Agent、指定当前 Agent、在 stream JSON 中转发子 Agent 文本/思考块，以及跨会话通信。
- 支持 cloud session、自托管环境、teleport/resume、Remote Control、从 PR 恢复会话，以及云端多 Agent `ultrareview`。

### Agent Loop 执行引擎

- 主执行链是异步生成器 `USe -> HGS -> tdf`。一次用户请求可以包含多次模型轮次、API retry/fallback 和多个工具批次，它们不是同一个“turn”概念。
- `tool_use` 不必等整个 assistant message 结束：单个 content block 完成且 JSON 可解析后就进入 streaming tool executor；模型继续流式输出时，工具 progress/result 可以同步回到 UI/SDK。
- 多个 `concurrency-safe` 工具可以重叠执行；非并发安全工具形成顺序屏障，后续工具不能越过它。并发资格由工具和本次 input 共同判断。
- 单工具必须经过工具/alias 查找、isolation latch、JSON/schema、自定义 validate、PreToolUse、permission/policy/classifier、updatedInput 复验、tool.call、PostToolUse 和 output schema 复验。
- 工具异常、拒绝、取消和不存在都会生成带原 `tool_use_id` 的 error `tool_result`，保证下一轮消息仍能正确配对。
- `maxTurns` 从第一次模型请求的 1 开始，只在工具结果或 blocking Stop hook 准备触发下一次模型调用时增加；API retry、流转非流和同轮纠错不等于增加 turn。
- Stop/SubagentStop hook 可以阻止结束并让模型继续；连续阻止默认超过 8 次时客户端覆盖 hook，避免永久循环。
- fallback 会 tombstone 当前消息、abort 未完成工具并清理 UI 状态，但无法自动撤销已经完成的文件、Git 或远端副作用。
- custom/subagent 使用同一个核心循环，但拥有独立 model/effort/maxTurns、工具、权限上下文、abort controller、worktree 和 transcript。

完整状态字段、时序图、终止原因和一个 Read/Edit/Bash 的执行例子见 [`analysis/agent-loop.md`](analysis/agent-loop.md)；与官方 Agent SDK 原理的逐项验证见 [`analysis/public-claims-validation.md`](analysis/public-claims-validation.md)。

### 模型与上下文控制

- 支持模型别名或完整模型 ID、print 模式下的 fallback model 链，以及 `low` 到 `max` 的 effort 级别。
- System prompt 不是单块字符串：客户端将 billing/identity、global 稳定前缀和 org 动态后缀分段，并分别决定是否写 `cache_control`。
- 消息 cache breakpoint 会向后寻找合法 user/assistant/api-system block；fork 可额外 pin 分叉点，`skipCacheWrite` 会主动退后，避免错误写入本轮尾部。
- Prompt cache 默认 5 分钟；1 小时 TTL 受强制开关、provider、订阅/overage 和 query-source allowlist 控制。Sonnet 4.6 的 baked 价格为普通输入 `$3/MTok`、5m 写入 `$3.75/MTok`、1h 写入 `$6/MTok`、读取 `$0.30/MTok`。
- Tool Search 将大工具目录标记为 `defer_loading`，初始只驻留工具名，需要时再追加完整 schema；旧 Vertex/不支持的 Foundry/model 会明确关闭并记录原因。
- Context hint 在潜在可清理旧工具结果达到 20k token 时才发送；本地 microcompaction 默认保留最近 5 个结果，旧结果可持久化到文件后替换为短引用。
- Auto-compact 支持自动模式或显式 100k-1M token 窗口。以 200k 模型为例，输出预留后默认约在 144k 预计算、147k warning、167k compact、177k blocked，而不是等到 200k 才处理。
- compact boundary 保存 pre/post token、摘要消息数、保留 UUID、logical parent 和是否预计算；resume 会据此修复消息图，不是简单拼接 JSONL 文本。
- 可将 cwd、环境、memory path、Git 状态等机器动态段从 system prompt 移到第一条 user message，提高跨用户 prompt cache 复用率。
- 支持替换或追加 system prompt、JSON Schema 结构化输出、美元预算上限、prompt suggestion 和 partial message streaming。

完整调用链、优先级、失败回退、设置/环境变量和成本算例见 [`analysis/context-governance-and-caching.md`](analysis/context-governance-and-caching.md)。消息图、transcript、checkpoint、rewind 和 memory 的恢复边界见 [`analysis/sessions-checkpoints-memory.md`](analysis/sessions-checkpoints-memory.md)。

### 工具、权限与隔离

- 支持 tool allow/deny、内置工具选择，以及 `default`、`acceptEdits`、`auto`、`bypassPermissions`、`dontAsk`、`plan` 六种权限模式。
- Safe mode 会关闭 `CLAUDE.md`、skills、plugins、hooks、MCP、custom commands、agents、主题等自定义内容，但保留认证、模型、内置工具和权限系统。
- Bare mode 会跳过 hooks、LSP、plugin sync、attribution、auto-memory、后台预取、keychain 和自动 `CLAUDE.md` 发现，但仍接受显式传入的配置。
- 支持额外可读目录、隔离 worktree、strict MCP config 和企业托管设置。

单工具从查找、input schema、PreToolUse、permission/policy 到 output schema 的完整顺序，以及 hook、sandbox、凭据和 managed settings 的失败语义见 [`analysis/tools-permissions-hooks.md`](analysis/tools-permissions-hooks.md)。

### 风控、安全与企业治理

这里的“风控”是 CLI 在本机执行 Agent、工具、Shell、MCP 和扩展时实施的风险控制，不等于 Anthropic 服务端的账号风控、滥用检测或封禁评分。发布 bundle 能直接证实以下控制面：

| 控制层 | 已恢复的能力 | 微小但重要的行为 |
| --- | --- | --- |
| 工具审批 | `--allowed-tools`、`--disallowed-tools`、工具级 allow/ask/deny 规则，以及 `default`、`acceptEdits`、`auto`、`dontAsk`、`plan`、`bypassPermissions` 六种模式 | `dontAsk` 遇到未授权操作会拒绝而不是弹窗；`bypassPermissions` 有单独的危险开关，帮助文本只建议在无外网沙箱中使用 |
| Auto 风险判定 | Auto mode 会把待执行动作交给 classifier；决策原因区分 rule、mode、hook、sandbox、safety check、classifier 等来源 | 无法评估时使用 `blocking it for safety` 路径；对话超过 classifier 窗口时回退人工审批；`dangerousRemoval`、`isolatePeerMachines` 等 circuit breaker 中存在不受 bypass 影响的类别 |
| Shell/Git 防护 | Bash command clamp、只读命令识别、复合命令拆分检查、工作目录和 Git 元数据检查 | 权限检查崩溃走 fail-closed；`cd` 后执行 Git、可植入的 `.git` 文件/符号链接、bare-repo 指示物和可能触发不可信 hook 的路径会重新要求审批 |
| 文件与进程沙箱 | `allowWrite`、`denyWrite`、`denyRead`、`allowRead`，并支持 `failIfUnavailable`、禁止 unsandboxed command、Linux seccomp/bwrap、macOS sandbox 和 Windows 隔离用户路径 | 管理策略一旦配置文件限制，用户可写设置不能关闭它；Apple Events 和 weaker network isolation 被显式标为降低隔离强度的选项 |
| 网络出口 | 域名 allow/deny、strict allowlist、managed-domain-only、Unix socket、本地监听和 macOS Mach/XPC service allowlist | denied domain 优先；strict allowlist 未匹配时直接拒绝；managed-domain-only 会忽略用户、项目和 CLI 临时放宽的域名，只接受策略层许可 |
| 凭据防泄漏 | 对文件和环境变量支持 `deny` 或 `mask`；可用 regex 只遮蔽捕获片段，也可识别 JWT、按 claim 遮蔽、处理重复 secret，并用 `injectHosts` 限定真实凭据注入目标 | Agent/命令看到 sentinel 或假 JWT，宿主代理只在许可出口替换为真实值；macOS/Windows 的文件 `mask` 当前会降级为 `deny`；配置可选择 no-match 时 warn、deny 或 error |
| Workspace 与扩展信任 | workspace trust、`--strict-mcp-config`、safe mode、bare mode、MCP tool permission、PreToolUse hook 的 allow/deny/ask/defer | MCP `headersHelper` 在 workspace trust 确认前会被阻止；hook 改写后的 tool input 会重新进入权限检查；HTTP hook 只有 `allowedEnvVars` 列出的变量可以进入 header |
| 企业治理 | managed/policy settings、`policyHelper(s)`、`allowManagedPermissionRulesOnly`、`allowedMcpServers`、`availableModels`、`forceLoginOrgUUID`、`processWrapper` | admin policy 可以锁定权限来源、MCP、模型、组织登录、文件读取范围和网络域名；Safe mode 仍保留 policy 层，不会绕过管理员配置 |

此外还存在两个启动前输入防护：凭据文件若 group/world 可读或可写会拒绝使用并要求修正为 `0600`；`--handle-uri` 后出现额外参数会按 URL 参数注入处理并拒绝启动。

结构化清单保存在 [`analysis/risk-control-surface.txt`](analysis/risk-control-surface.txt)。它用于长期版本对比，记录稳定的权限模式、circuit breaker、sandbox 设置、凭据控制、信任门和企业策略键；不把 bundle 中没有证据的服务端账号评分、关联检测或滥用规则写成已恢复能力。Auto Mode 在确定性规则之后怎样分类、为什么 unavailable 时 fail closed，见 [`analysis/auto-mode-classifier.md`](analysis/auto-mode-classifier.md)；Enterprise Gateway 如何把身份、策略、上游凭据、花费和遥测串成独立运行链，见 [`analysis/enterprise-gateway-runtime.md`](analysis/enterprise-gateway-runtime.md)。

### 扩展与集成

- 支持 skills/slash commands、目录/ZIP/URL 插件、MCP server 配置和 setting source 选择。
- `claude plugin eval` 内置 case 信任、with/without ablation、六类 grader、费用/partial 控制和机器可读报告；它是实验编排器，不是“插件被加载过就算有效”。
- 支持 IDE 自动连接、Chrome 集成、终端 screen reader 模式和 VS Code 会话。
- 支持 Anthropic API、Claude 订阅、Bedrock、Vertex AI、Foundry 和企业 gateway 路径。
- 顶层命令包含 gateway、project purge、auth、install/update、setup-token、plugin、MCP、import、auto-mode 和 doctor。

后台执行也不等于一个脱离状态管理的子进程：daemon supervisor、PTY host、Claude worker、rendezvous 控制通道、Storage V5 job record 和 Agent View 分别拥有不同状态。完整 adopt/respawn、socket auth、ring buffer、processWrapper 和 `asyncRewake` 合同见 [`analysis/runtime-supervision-and-processes.md`](analysis/runtime-supervision-and-processes.md)。

### 输入输出协议

- 输出支持文本、单个 JSON 结果或实时 stream JSON。
- 输入支持文本或 stream JSON，并可回放用户消息用于确认。
- Stream 模式可以输出 hook 生命周期、partial assistant chunk、子 Agent 转发内容和结构化任务进度。

标准化后的**公开顶层帮助 token** 保存在 [`analysis/cli-surface.txt`](analysis/cli-surface.txt)，适合避免终端换行噪声的快速 diff，但它不是完整 CLI authority。`2.1.235` 还有 hidden/conditional Commander 节点、Remote Control/daemon/background/self-hosted runner fast path 和内部 worker 入口；完整路径、alias、arguments/options、handler、副作用与失败见 [`analysis/cli-command-inventory.json`](analysis/cli-command-inventory.json) 和 [完整 CLI 命令树专题](analysis/cli-command-reference.md)。

### 遥测、日志、实验和性能诊断

完整数据流、字段和隐私控制见 [`analysis/telemetry.md`](analysis/telemetry.md)，字段的人类解释见 [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md)。排查具体故障时先进入 [`analysis/telemetry-event-catalog.md`](analysis/telemetry-event-catalog.md) 的场景语义索引：它先把 API attempt、工具权限与执行、compact、session/MCP/后台任务、登录、错误终态和 transcript 写入放回各自 owner 与状态机，再下钻到 1,441 条静态事件证据。`tengu_other` 仍只是 family 兜底；140 条 exact caller allowlist 当前完整收口 20 个事件（19 Single-owner、1 Cross-owner），其余 891 个 event / 1,157 callsite 明确保留 Unresolved，导航区间不会自动赋 owner。每条已收口规则还绑定局部状态变化和 Boundary，防止把 logger caller 误读成运行已发生、外部副作用已完成或遥测已送达。本版本不是只有一个“是否有遥测”的布尔开关，而是多条独立链路：

- 一方 analytics 在 sink 安装前保留 1,000 条全局事件，在一方 provider 初始化前再保留 1,024 条；provider 默认 queue 为 8,192。
- 提取器先从稳定 export、OTEL envelope、settings/model/Datadog 锚点发现本版短符号，再由 Acorn AST 找到一方 `H` 2,162 次、`Fv` 32 次、OTEL `Nd` 52 次、feature `et` 498 次和 dynamic config `CB` 12 次。JSONL 同时保存跨版本稳定的 `calleeRole` 与本版 `callee`，并保留静态名、模板、变量/条件表达式、完整参数、函数作用域、payload property/spread 和 unresolved spread。
- `DISABLE_TELEMETRY`、`DO_NOT_TRACK`、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 进入共享非必要流量/遥测门；error reporting 另有 `DISABLE_ERROR_REPORTING` 和组织 policy/compliance 门。
- 一方采样由 `tengu_event_sampling_config` 按事件控制；被采中事件会把实际 `sample_rate` 写入 metadata。
- 一方 batch config 为 `tengu_1p_event_batch_config`；默认 10 s flush、200 batch、10 s request timeout、100 ms batch delay；单个 exporter 实例当前连续失败周期最多 8 attempts，成功或进程重启会重置内存计数；backoff 为 500 ms 到 30 s。
- 默认一方 endpoint 为 `https://api.anthropic.com/api/event_logging/v2/batch`。失败事件保存为 `1p_failed_events.<session>.<run>.json` 或 v5 `log/telemetry` stream，后续启动会重试遗留 batch。
- 带 auth 的一方请求收到 401 时，会用基础 headers、不带 auth 再试一次。
- 一方 envelope 可承载 event/session/model、device/email/account/org、platform/runtime/CI/remote、process memory/CPU、skill/plugin/MCP/team/head SHA 和 event-specific metadata；不是每个事件都会填满全部字段。
- 第三方 OTEL 由 `CLAUDE_CODE_ENABLE_TELEMETRY` 显式启用。metrics 支持 console/OTLP/Prometheus，logs 支持 console/OTLP，traces 支持 console/OTLP；OTLP 支持 grpc、http/json、http/protobuf。
- bundled OTEL library解析 global/signal-specific endpoint/header/protocol/cert/key/compression；但 2.1.235 的 HTTP exporter先注入 `n1i()->Kol()` programmatic agent，merge会遮蔽 library certificate/client agent。
- exact OTLP TLS Probe证明 effective owner：`NODE_EXTRA_CA_CERTS`、`CLAUDE_CODE_CLIENT_CERT/KEY` 和小写优先的通用 proxy分别控制 HTTPS、mTLS CN和 CONNECT；OTLP专用 cert/client变量未形成 HTTP/client identity，所有 exporter失败仍不改变 Agent success/exit 0。metrics temporality 未显式设置时强制为 `delta`；默认 flush timeout 5 s、shutdown timeout 2 s。
- 静态恢复出 8 个 metric、10 个 span 和 26 个 structured event；场景语义索引、名称、逐事件字段、调用点和出口资格均已生成并绑定验证。
- 环境解析覆盖 2,548 个访问点、145 个 dynamic `process.env[...]`、842 个 typed schema entry、71 个观测相关 schema entry 和 23 个观测默认/fallback 表达式。
- OTEL user prompt 默认 `<REDACTED>`；assistant、tool content/details 也有独立开关。`OTEL_LOG_RAW_API_BODIES` 是另一条更高风险路径：默认不生成 body event，inline 模式将 request/response 正文送入 collector，`file:` 模式把正文落本地并只上报 `body_ref`；三模式已用精确 2.1.235 二进制验证。
- Datadog 只运行于 first-party provider，受 `tengu_log_datadog_events` 和 181 项 allowlist 控制；默认 15 s flush、100 batch、5 s timeout。
- Datadog 发送前删除 26 个字段，选择 34 个 tag，折叠 MCP/skill tool name，归一化 Claude model/version/HTTP status，并对 peer 事件做每 event/server 每分钟 10 条限制。
- GrowthBook experiment 复用一方批量 transport，包含 experiment/variation、device/session、account/org 和序列化 attributes/metadata。
- 还恢复出 error reporting、secret scrubber、Perfetto bridge/integration surface（recorder/file 未观察）、startup/query profiling、debug logs、diagnostics file、frame timing、session/JSONL/PTY recording 等观测面；对应 4,831 个 error callsite、5,403 个 diagnostic callsite 及全部动态模板均可逐点检索。本地 debug/profile 文件不能自动等同为网络上报。

### 其余完整系统面

[`analysis/technical-architecture.md`](analysis/technical-architecture.md) 先把这些系统串成一条可读调用链；[`analysis/source-surface.md`](analysis/source-surface.md) 再逐层整理 build/runtime、CLI/protocol、settings/env/schema、models/providers/auth、session/transcript/memory/cache/storage、agent/team/worktree/background、MCP/hooks/plugins/skills/LSP、IDE/Chrome/Computer Use、cloud/remote/CCR/BYOC/workflow/artifacts、install/update/doctor、UI/accessibility/voice，以及 API/error/retry/rate-limit/compact。每一层都区分 Observed、Derived、Compatible 和 Heuristic。

### 十一个容易被总图压扁的专用状态机

- **Auth/account/subscription**：登录不是拿到 token 就结束；credential、account/org、subscription、派生 API key/role、feature 与 Remote Control cache 要按提交顺序换代，logout 还要区分远端 revoke 和本地 wipe。
- **Onboarding/workspace trust**：账号准备和项目信任是两份状态；项目 hooks、MCP、skills、commands、helper 和预授权规则只有 trust 后重新发现才进入 session。
- **Thinking/Effort/Fast Mode**：三条控制轴在每次 request attempt 重新受模型能力、组织上限、provider、policy、兼容性 latch 和服务冷却裁决。
- **Usage/cost/credits/limits**：token/美元成本账本与账号额度窗口分离；warning、checkpoint、usage credits 和 reset 后 auto-resume 又是独立状态链。
- **Project purge/import**：preview/digest/manifest 能防输入漂移与明显损坏，却不提供跨文件事务；exit 1 后可能保留已经完成的删除或写入。
- **Sandbox**：宿主安装态与逐命令运行态分离；`installed:true`、CLI exit 0 和工具动作成功是三个不同结论。
- **Proxy/CA/mTLS**：fetch、Axios、WebSocket、AWS、MCP、OTLP 和 CCR relay分别选择或组合 adapter/信任材料；OTLP HTTP已证明由通用 `Kol()` agent接管，其他 transport仍需逐项验证。
- **Active Goal**：`/goal` 注册 session Stop hook；模型准备结束时才检查，未满足就回灌原因并继续，达到 cap 或完成后才清理。
- **后台模型任务**：Away/Post-turn Summary、Prompt Suggestion、Feedback Draft 多数只改变临时 UI/协议状态；只有 Auto Dream 会持久改写 memory Markdown。
- **Advisor**：不是第二个本地 Agent，而是同一个 Messages 请求中的 server tool；fallback 会重算模型组合，不支持时只 strip wire view。
- **Ultrareview**：客户端先确定 Git scope、规模、费用和 cloud task；findings 回来后 `--fix` 才在本地 Agent Loop 执行，`--post` 只允许一条普通 PR comment。

## 打包与技术细节

### Bun standalone 格式

本机安装包是签名的 arm64 Mach-O 文件，包含 `__BUN.__bun` 段。Bun 在这里保存序列化的 standalone module graph，同时保留 bundle 后的 JavaScript 和 JavaScriptCore bytecode cache。

主模块开头为：

```js
// @bun @bytecode @bun-cjs
```

含义如下：

- `@bun`：这是 Bun 打包模块。
- `@bytecode`：可执行文件还包含 JSC bytecode cache，用于缩短启动时间。
- `@bun-cjs`：源码依赖 Bun 内部 CommonJS wrapper 约定。

本分支同时提交 bytecode cache 的无损 gzip 形式和可读化 JavaScript，但两者都不会覆盖逐字节 JavaScript 基线。跨版本源码级比较以 `extracted/cli.js` 和 `reverse/index/` 为主；bytecode 哈希用于确认运行时生成物是否变化。

### 解出的模块图

15 个内嵌文件并不是 Anthropic 原始源码目录，而是产品构建完成后实际写入可执行文件的 bundle：

- 1 个 26.0 MB 主应用 bundle。
- 5 个约 2.1 KB 的原生能力 JavaScript loader。
- 5 个 `.node` 原生模块，负责图像处理、音频采集、URL handling、Swift Computer Use 和输入注入。
- Chart.js、Highlight.js、Mermaid 浏览器运行时。
- 1 个 2.13 MB 的 Artifact/报告 HTML 模板。

图像、音频和 URL 原生模块是 arm64 Mach-O；两个 Computer Use 模块是同时包含 x86-64 和 arm64 slice 的 universal Mach-O。

### 保真度与可运行性

解包时使用 `--path-patching false`。清单中每个文件的 `sha256` 都等于 `sha256Packed`，证明仓库内容与本机可执行文件内的原始打包字节一致。

主 bundle 可用于全文检索和跨分支对比，但不是普通独立 `cli.js`。直接交给 stock Bun 运行，会在 Bun 内部 CommonJS wrapper 边界报错。已验证的运行行为仍来自原始签名程序；本仓库是分析快照。

主 bundle 没有内嵌 source map，5 个原生模块也没有可用的源码级 debug information。生产构建已经丢弃的原始 TypeScript 文件名、注释、格式、bundle 前模块边界、被压缩改写的局部变量名，以及 tree shaking 删除的代码，无法从发布可执行文件精确反推出原值。

因此，本仓库的“完整”定义是：发布可执行文件中仍存在的 packed 文件和 bytecode 全量保留，对 JavaScript 和所有原生模块生成可复现的最大静态分析视图，并为 5 个原生模块提供可编译、双跑验证的兼容源码重建；不把重建目录冒充 Anthropic 原始源码仓库。

## 长期版本对比

可复用 skill 位于 [`skill/claude-code-version-diff`](skill/claude-code-version-diff)，并已安装到本机，可通过 `$claude-code-version-diff` 使用。

从本版本开始，skill 的交付合同分成两层：

- **机器证据层**：packed bytes、bytecode、native reports、结构化 inventory 和稳定语义 diff，保证没有靠人工挑选遗漏字段。
- **人类解释层**：机制总图、公开主张验证、技术架构、Agent Loop、上下文治理/缓存、会话/checkpoint/memory、工具/权限/hooks、Auto Mode、Plugin Eval、Runtime Supervision、Enterprise Gateway、Auth/Trust、Thinking/Effort/Fast、Usage/Limits、数据生命周期、Sandbox、Proxy/CA/mTLS、Active Goal、后台模型任务、Advisor、Ultrareview、MCP/Agents/后台协作、韧性恢复、遥测、风控、字段字典和版本专题。每个机制必须解释 purpose、owned state、call chain、gate/precedence、threshold、failure、lifecycle、user impact、evidence 和 boundary。

后续版本不能只更新 count table。任何新增 settings/env/model/event 字段都要说明字段语义、来源、默认/约束、谁读取、何时生效、如何失效、用户怎样观察；任何上下文/cache/compact 变化都要给出旧版和新版的状态机与成本影响。官方当前文档或 Engineering 文章只用于提出验证假设，必须标明调研日期，并分别标注目标版本的静态证据、运行 probe 和未证实边界。

验证任意版本分支：

```bash
python3 skill/claude-code-version-diff/scripts/validate_snapshot.py .
```

重新生成架构长文和独立的 71 类机器证据索引（命令会同时写出两个文件）：

```bash
python3 skill/claude-code-version-diff/scripts/build_product_surface_map.py . \
  --output analysis/product-surface-evidence-map.md
```

隔离验证 Plugin Skill 与 LSP 闭环：

```bash
CLAUDE_BIN="$CLAUDE_TARGET" \
  node skill/claude-code-version-diff/scripts/probe_plugin_skill_lsp.mjs
```

重跑 OTLP HTTP logs 的 HTTPS、mTLS 与 proxy owner 探针：

```bash
node skill/claude-code-version-diff/scripts/probe_otlp_tls.mjs \
  --output analysis/runtime-probes/otlp-tls.json
python3 skill/claude-code-version-diff/scripts/validate_otlp_tls.py .
python3 skill/claude-code-version-diff/scripts/test_otlp_tls_validator.py .
```

验证校验器会拒绝隐私路径、伪引用、未归属 inventory、受 topic-depth 合同保护却降回 `Documented` 的能力面、没有具体缺失事实的 `Documented` 行、未索引 Probe 和失败 required check，并确认每次负向变更都恢复原哈希：

```bash
python3 skill/claude-code-version-diff/scripts/test_validator_negative.py .
```

单独验证深度逆向，包括流式解压 bytecode 后重新计算哈希：

```bash
python3 skill/claude-code-version-diff/scripts/validate_deep_reverse.py .
```

对比两个版本分支并输出 Markdown 报告：

```bash
python3 skill/claude-code-version-diff/scripts/compare_versions.py \
  . 2.1.234 2.1.235 --output comparison-2.1.234-to-2.1.235.md
```

对比器会输出：

- 版本元数据、二进制大小和载荷大小变化；
- 新增、删除和内容变化的内嵌文件；
- 新增或删除的 CLI option/command；
- 新增或删除的权限模式、风控 circuit breaker、沙箱/凭据/信任和企业治理控制；
- `analysis/source-inventory/summary.json` 中全部 71 类清单的 count delta、added 和 removed，包括调用点、动态表达式、事件/payload、OTEL、Datadog、typed env、settings schema、模型目录/pricing/alias、全部字符串/模板、80 个 `Yi({...})` 工具注册调用点、commands、hooks/protocol、storage、API、errors、URLs/hosts；
- 人类解释层的章节级变化：完整请求机制、公开主张验证状态、请求装配、上下文预算、cache scope/TTL/breakpoint、tool deferral、microcompaction、auto-compact、session/checkpoint/memory、MCP/Agent/task/mailbox、retry/fallback/resume/rewind、遥测 transport/privacy、风险控制与字段语义；
- Agent Loop 的主状态字段、流中工具启动点、并发屏障、tool pipeline、Stop hook、maxTurns、fallback sweep、terminal reason 和子 Agent 隔离变化；
- 老分支没有全量 inventory 时，才回退到 `ANTHROPIC_*`、`CLAUDE_CODE_*`、`ENABLE_*` 和 endpoint host 的旧式扫描；
- JSC bytecode 与可读化 JavaScript 大小/哈希变化；
- 原生架构、动态库、import/export、N-API 和 Swift 项目符号变化；
- 主 bundle 与分析文件的 Git 行数变化。

## 验证结论

快照校验器检查分支/版本约定、15 个解包文件哈希、93 个归一化风控条目、71 类 source inventory 的确定性重生成、逐文件哈希，以及产品运行时长文的三世界中心命题、Prompt Assembly、Agent Loop 四种嵌套生命周期单位、client/server tool 分流、Bash 改写前并发分类、权限 scope、compact 普通 miss 与 hit/miss、全局数据流、遥测 raw-body 三模式、OTLP TLS effective owner、按对象局部恢复、Artifact 响应合同、Voice 证据等级、Native updater 10 阶段事务、Derived 阅读路由、折叠证据方法和独立机器证据索引；71 类清单只证明分类完整、顺序稳定与映射可复核，不代表所有 identifier 已完成 consumer tracing。校验器同时检查 356 条结构化机制证据、52 条 Probe 的人类索引、31 个官方来源、40 条逐句正文命中的固定摘录、固定 commit 的 19 条上游 Release Notes 原文、Acorn 版本、JSONL 比较字段、调用点覆盖、58 个能力面的 Deep/Documented/Boundary 状态、读者优先深度专题及其 DOT/SVG，以及遥测场景语义索引、1,441 个一方事件 catalog marker、正文与机制图合同。它还检查主源码 Bun banner、bundle 内版本号、深度逆向 manifest、完整 bytecode 解压哈希、可读版稳定标识符集合、5 个原生源文件哈希，并精确核对人工维护的 29 项核心终端参考、80 个同工厂 AST 注册调用点及 29/28/16/4/3 人工分类、156 个 direct setting、103 个 slash command、31 个 Hook event、32 个 Claude storage namespace、89 个 SDK subtype 和 44 个 protocol event。原生重建另外要求 arm64 23/23 与 x86_64 20/20 两份报告同时 PASS，x86 supplied compatible artifacts 5/5 完成 provenance/load/export contract，recipe 不作为同次 build attestation，且只对发布物确有 x86 slice 的两个模块声明行为对照。原始 `2.1.235` 发布程序在全部逆向和重建完成后 SHA-256 仍为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748`。

本分支只排除 298.8 MB 的原始签名可执行文件本体，因为其中可分离的 Bun packed 内容与 bytecode 已经逐项保存；需要验证实际运行行为时仍使用本机原始签名程序。

仓库元数据使用 `$CLAUDE_INSTALL_ROOT` 和 `$CLAUDE_ENTRYPOINT` 表示本机安装位置，不提交用户名、home 目录或 Codex 工作区绝对路径。隐私校验覆盖 Git 已跟踪文件和待提交的未跟踪文件，拒绝采集机 home/workspace 路径和 credential-shaped value。`extracted/` 与 `reverse/` 中由发布二进制自身携带的上游构建路径属于原始证据，不属于采集机器信息。
