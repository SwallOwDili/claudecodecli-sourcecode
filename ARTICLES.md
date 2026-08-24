# Claude Code CLI 2.1.235 技术文章总入口

这里是给人阅读的入口。机器清单、反汇编和 JSONL 用来证明结论，不应该挡在文章前面。

## 先读这七篇

1. [2.1.235：不是 Agent Loop 重写，而是一次状态边界修正](analysis/product-surface-evidence-map.md)：先把本版 Release delta 与既有架构分开，再用“改端口、跑测试、compact、resume、Artifact timeout”这一条因果链讲清逐请求能力编译、四时钟 Agent Loop、分层风控、上下文表示、消息图恢复、扩展委派、Telemetry 与 Native/Voice 的权力边界。
2. [完整机制说明书](analysis/claude-code-2.1.235-complete-guide.md)：单卷 58 章，从发布物、请求装配、Agent Loop、工具注册、Plan/Structured Output、Brief 输出、上下文、权限、多 Agent、恢复、遥测一直讲到 Artifact Watch、`/insights`、启动资源、复杂 Slash Command、原生桥和准确性边界。
3. [Agent Loop 专题](analysis/agent-loop.md)：解释 Claude Code 为什么能连续读文件、改代码、执行测试、吸收工具结果并继续决策。
4. [`/compact` 图文专题](analysis/compact-visual-guide.md)：用一个完整场景和三张图说明 Summary、近期消息、附件恢复、compact boundary 与失败恢复。
5. [Plan Mode 与人工审批](analysis/plan-mode-and-human-approval.md)：解释“先规划、后实施”怎样由 permission mode、计划文件、工具底线、问答与人工批准共同实现。
6. [Structured Output 与 Schema 终态](analysis/structured-output-and-schema-contract.md)：解释 `--json-schema` 如何变成本地验证的强制收尾工具，以及失败、重试、fallback、tombstone 和最终结果选择。
7. [Auto Mode 分类器专题](analysis/auto-mode-classifier.md)：解释确定性权限前置层、可信规则合并、两阶段 XML verdict、fail-closed、PermissionDenied Hook 和 hash-bound 配置向导。

![Claude Code 任务在上下文、Agent Loop、工具控制、外部状态和恢复状态之间循环](analysis/visuals/system-lifecycle.svg)

## 本轮新增的全量参考

1. [模型提案权、本地裁决与九条机制主线](analysis/product-surface-evidence-map.md)：正文只讲可执行的因果链与设计取舍，不再用文件数、字段数和完成度数字制造深度；71 类 inventory、339 条 claim 和仍未收口的 consumer 统一进入独立的 [机器证据索引](analysis/product-surface-inventory-index.md)。
2. [全面性审计与收口合同](analysis/completeness-audit.md)：按 58 个产品能力面区分 Deep 与 Boundary；57 个客户端能力面逐项收口，1 个不可恢复面明确保留边界，不以文章篇幅或清单数量冒充全面。
3. [80 个工具注册调用点、条件工具与宿主表面](analysis/tool-registration-and-host-surfaces.md)：解释人工维护的 29 项核心参考、80 个 `Yi({...})` AST 调用点、77/3 静态 name/动态表达式、工厂展开、五类人工归属和七道运行时 gate。
4. [Brief 与用户可见输出](analysis/brief-mode-and-user-visible-output.md)：解释 `SendUserMessage`、`--brief`、`/brief`、chat/transcript projection、附件 upload lane、部分失败和 turn-end 单次补发。
5. [29 项核心终端参考工具逐项说明](analysis/builtin-tools-reference.md)：维护集合 29/29 覆盖，并深入说明 Workflow、Cron、LSP、Task、Artifact、Worktree、文件工具和后台输出的状态与失败边界。
6. [Settings 解析、合并与热重载](analysis/settings-resolution-and-reload.md)：讲清进程级 store、五层/admin tier、四类 merge、ConfigChange、程序写入、consumer 刷新、remote managed settings 与 policy helper 恢复。
7. [156 个 Settings 全字段参考](analysis/settings-reference.md)：156/156 direct key 逐项解释类型、来源、merge、consumer、生命周期和影响，另解释 4 个 spread。
8. [完整 CLI 命令树](analysis/cli-command-reference.md)：恢复 90 个普通/隐藏/条件/fast-path/manual-parser 路径及 8 个内部入口，逐层解释 alias、arguments/options、gate、handler、副作用和失败，说明为什么顶层 `--help` 不是全貌。
9. [CLI、SDK 与输出协议](analysis/cli-sdk-output-protocol.md)：讲清 text/JSON/stream-json、stdin/stdout envelope、control request/response、观察事件、structured output、session 与终态。
10. [Plugins、Skills、Slash Commands 与 LSP](analysis/plugins-skills-commands-lsp.md)：讲清来源信任、安装与 enable、session registry、listing 预算、reload、MCP cache 和 language server 生命周期。
11. [842 个 typed 环境变量](analysis/environment-variable-reference.md)：区分 842 个 schema 声明、2,161 个 typed named read、137 个非 typed 名称与 145 个动态调用点；只有 7 个动态 callsite 通过完整支配/引用证明并恢复 22 个有限名称，138 个保留 7 类主失败链。351 个静态名称已人工追到 owner、precedence、state delta、失败边界与用户影响，其余 562 个继续标 Semantic follow-up，不用名称猜 consumer。
12. [361 个 Feature key](analysis/feature-flag-reference.md)：精确拆分 444 个 literal、11 个 assignment-resolved 和 43 个真正动态调用点；175 个 key 已人工追到 fallback、secondary gate、state delta、失败边界和用户影响，其余 186 个保留 Static immediate consumer 与服务端 Boundary。
13. [遥测排障场景与 1,441 个一方事件](analysis/telemetry-event-catalog.md)：先按 API、工具授权、Permission UI、compact、session、MCP、后台任务、登录、错误终态和 transcript 恢复解释事件顺序、owner、字段与状态变化，再逐事件保留 payload field、spread、function、Datadog/OTEL 资格和动态名称边界；原 `tengu_other` 的 911 个事件 / 1,297 callsite 当前用 79 条 exact caller identity 收口 11 个 Single-owner、1 个 Cross-owner，899 项及其 1,218 个 callsite 继续明确标为 Unresolved，不再用宽行号桶制造假完整。
14. [99 条 API 路径与 53 个 Beta 的所有权](analysis/api-beta-route-ownership.md)：逐项区分客户端 product consumer、发布物内 Gateway handler、SDK/依赖、prefix/allowlist 和内嵌参考文本，解释 header/path 出现为什么不等于 runtime 已发送或服务端已开放。
15. [错误与诊断机制图谱](analysis/error-diagnostic-atlas.md)与[精确 owner 索引](analysis/error-diagnostic-owner-index.md)：把 4,831 个错误构造点、5,403 个 diagnostic 调用点放回恢复链，并以 exact callsite identity 区分 308 个 Product caller、250 个 Dependency package/function 和 9,676 个未解析项；catch、retry、tool-result、user-surface 四个 owner 独立 fail closed。

## 七个不能只写成工具名的新专题

1. [Plan Mode 与人工审批](analysis/plan-mode-and-human-approval.md)：从 `EnterPlanMode` 的专用批准、`prePlanMode`、周期 reminder、plan file 写入例外，到 `AskUserQuestion`、`ExitPlanMode`、批准/拒绝、AFK、SDK park、team lead 和远端 Ultraplan。
2. [Structured Output 与 Schema 合同](analysis/structured-output-and-schema-contract.md)：从 CLI schema 解析、AJV/strict schema、工具注入，到 validation error 修正轮、重试上限、attachment、tombstone 和最终 `structured_output`。
3. [REPL 程序化工具运行时](analysis/repl-programmatic-tool-runtime.md)：解释持久 VM 怎样编排内层工具、每个内层调用为什么仍经过 Hook/permission、动态工具怎样跨轮保留，以及 resume 为什么重放结果而不重做副作用。
4. [EndConversation 风控](analysis/end-conversation-risk-control.md)：区分发布/模型/宿主 gate、连续两次调用、主会话限制、marker/abort/exit 这些硬控制，与“持续辱骂、已警告、自伤场景禁止结束”等 prompt 规则。
5. [Remote Routines、Runner 与 Notifications](analysis/remote-routines-runner-and-notifications.md)：串起 8 类 RemoteTrigger、9 个 runner operator、spawn/requeue/health/log、通知的 100 项 pending、1000 drained ID、90k drain、ack 和最多两次 rearm。
6. [Connectors、账号 Catalog 与 MCP Operators](analysis/connectors-catalog-and-mcp-operators.md)：讲清 search/list/suggest、Plugin/Skill OAuth scope expansion、suggestion card 与安装的区别，以及 refresh/wait/resource 对 live MCP 状态真正改变了什么。
7. [ClaudeDesign 与 Projects](analysis/claude-design-and-projects.md)：讲清动态 operation catalog、project grant、预览/结果预算、Projects 五种方法、RAG 403 fallback、路径/inode TOCTOU 与远端知识配额。

## 四个不能埋在参数和 Slash Command 表里的状态机

1. [Artifact Watch 评论自动响应](analysis/artifact-watch-comment-autoreact.md)：讲清外部评论为什么先做 baseline/digest、无工具 triage 和只读 analyst，写前如何经过 plan/cap/breaker/permission probe，以及 ack、edit、reply、resolve 为什么不是一个可回滚事务。
2. [`/insights` 历史分析管线](analysis/insights-history-analysis-pipeline.md)：讲清 metadata 与 facet 双缓存、500/300 字符截断、30k/25k 分块、50 个 facet、7+1 模型分析、270,336 output-token 静态上限，以及 facet 不比较 transcript mtime 导致的过期语义窗口。
3. [CLI 启动文件、URL 插件与 Deep Link](analysis/cli-startup-files-plugins-deeplinks.md)：讲清 `--file` 下载落盘不等于进入模型，`--plugin-url` 为什么是会话级可执行能力，ZIP 防护与 URL 信任为什么是两层边界，以及 Deep Link 如何拒绝 argv 注入并只预填不提交。
4. [复杂 Slash Command 生命周期](analysis/complex-slash-command-lifecycles.md)：逐条下钻 `/install-github-app`、`/team-onboarding`、`/privacy-settings`、`/web-setup`、`/terminal-setup`，区分 GitHub、Claude 服务端、workspace 和 OS 状态 owner，以及部分成功后需要在外部系统撤销的副作用。

## 本轮完成的产品表面深挖

1. [103 个 Slash Command 生命周期](analysis/slash-command-reference.md)：103/103 精确覆盖，逐命令说明 `local`、`local-jsx`、`prompt`、thin-client twin、可见性、gate、状态 owner、失败和副作用。
2. [31 个 Hook 事件参考](analysis/hooks-event-reference.md)：31/31 精确覆盖，解释事件时机、公共/专属字段、matcher、command/HTTP/MCP 载体、阻塞、输入输出修改、超时和后置副作用边界。
3. [32 个 Storage v5 namespace](analysis/storage-v5-reference.md)：32/32 精确覆盖，解释 typed key、scope、atomic/in-place/append、transcript 物理压实、前置条件、真实 consumer、敏感度，以及本版不会自行创建 v5 backend 的边界。
4. [Workflow、Artifact 与 Design 数据链](analysis/workflow-artifact-design.md)：从确定性 Workflow/journal，到 Artifact 文件身份、CSP、comments/DB/assets，再到 Design build/diff/validate/upload/sidecar。
5. [Feature Flags 与 Remote Config](analysis/feature-flags-remote-config.md)：解释 361 个 key、498 个调用点背后的启用门、属性、fresh/disk/default、实验 exposure、刷新、账号切换和不可用 override。
6. [TUI、输入、无障碍、媒体、IDE 与 Chrome](analysis/tui-input-accessibility-media-ide-chrome.md)：把 renderer/composer/spellcheck/paste/image/voice/IDE/Chrome 的状态机、阈值、权限、重试和竞态串起来。
7. [后台执行、Channels 与 Cloud](analysis/cloud-background-channels.md)：区分本地 task/supervisor、Cron/loop/Monitor/Push、Channel 队列、Remote Control、本地/云执行 owner、CCR/BYOC/self-hosted runner。

## 四个不能埋在清单里的运行专题

1. [Auto Mode 两阶段分类器](analysis/auto-mode-classifier.md)：确定性权限前置层、可信规则来源、`$defaults`、Stage 1/2、XML verdict、fail-closed 与拒绝后的 Hook 重试语义。
2. [Plugin Evaluation Harness](analysis/plugin-evaluation-harness.md)：case 信任、with/without ablation、六类 grader、3 票多数、费用中断、真实 scaffold 风险、Delta 可比性与 CI exit code。
3. [Runtime Supervision](analysis/runtime-supervision-and-processes.md)：Agent View、daemon、PTY host、worker、rendezvous、Storage job record、respawn、memory-pressure reap 与 `asyncRewake`。
4. [Enterprise Gateway Runtime](analysis/enterprise-gateway-runtime.md)：OIDC/device flow、Gateway session、managed policy、provider 路由、CRI、spend、Postgres、OTLP、失败隔离与服务端边界。

## 十一个新拆出的专用状态机

1. [Auth、账号与订阅生命周期](analysis/auth-account-and-subscription-lifecycle.md)：CLI/TUI/SDK 登录、OAuth/token、组织校验、subscription、setup-token、远端 revoke、本地 wipe 与 cache 换代。
2. [Onboarding、Workspace Trust 与安全启动](analysis/onboarding-workspace-trust-and-safe-startup.md)：项目风险扫描、persisted/session trust、接受后重新发现，以及 `--safe-mode`、`--bare`、`--print` 的精确装载边界。
3. [Thinking、Effort 与 Fast Mode](analysis/thinking-effort-and-fast-mode.md)：三条控制轴、请求前优先级、模型/组织 gate、兼容性 latch、service tier、429/529 冷却和成本估算。
4. [Usage、成本、Credits 与 Limits](analysis/usage-cost-credits-and-limits.md)：token/cost 账本、plan limit、warning/checkpoint、credits、auto-resume、取消与 stale/rearm。
5. [Project Purge、Import 与数据生命周期](analysis/project-purge-import-and-data-lifecycle.md)：项目状态清理、Codex/Gemini 配置导入、会话 ZIP/JSON 导入、digest/manifest、顺序副作用和恢复。
6. [Sandbox 安装与运行 Enforcement](analysis/sandbox-install-and-runtime-enforcement.md)：Windows 安装/status 与逐命令 wrapper 两条状态机，解释 `installed:true`、工具结果和 CLI exit status 的不同含义。
7. [Proxy、NO_PROXY、CA 与 mTLS](analysis/network-proxy-ca-and-mtls.md)：fetch/Axios/WebSocket/AWS/MCP 的 transport 差异、407 helper、CA store、client cert reload 和 CCR CONNECT relay。
8. [Active Goal 与 Stop-loop](analysis/active-goal-and-stop-loop.md)：`/goal` 如何注册 session Stop hook、阻止过早结束、触发下一轮、达到 cap 并在完成后清理。
9. [后台模型任务与 Memory Consolidation](analysis/background-model-tasks-and-memory-consolidation.md)：Auto Dream、Away Summary、Post-turn Summary、Prompt Suggestion、Feedback Draft 的 owner、成本、持久化和隐私差异。
10. [Advisor 双模型运行时](analysis/advisor-dual-model-runtime.md)：request-time model rank、server tool、流式 result、fallback 重算、wire strip 与额外 token/延迟。
11. [Ultrareview 云端审查](analysis/ultrareview-cloud-review.md)：Git scope、diff 上限、preflight、cloud task、poll/recovery、本地 `--fix` 与单条 PR comment `--post`。

## 按问题阅读

| 你想弄清楚什么 | 对应文章 |
| --- | --- |
| `2.1.235` 到底改了什么；为什么它不是 Agent Loop 重写，而是一次状态边界修正 | [2.1.235 状态边界与本地执行系统解剖](analysis/product-surface-evidence-map.md) |
| 一次请求从输入到工具执行、持久化和遥测经历什么 | [技术机制总图](analysis/technical-mechanism-atlas.md) |
| 当前分析到底覆盖了什么、还有哪些能力面不能称为全面 | [全面性审计与收口合同](analysis/completeness-audit.md) |
| Artifact 评论为什么不能直接指挥 Agent，自动回复怎样被 plan、permission 和 breaker 阻止 | [Artifact Watch 评论自动响应](analysis/artifact-watch-comment-autoreact.md) |
| `/insights` 为什么不是纯本地报表，facet cache 为什么可能长期过期 | [`/insights` 历史分析管线](analysis/insights-history-analysis-pipeline.md) |
| `--file`、`--plugin-url` 和 Deep Link 分别改变本地文件、插件图还是输入框 | [CLI 启动文件、URL 插件与 Deep Link](analysis/cli-startup-files-plugins-deeplinks.md) |
| GitHub App、onboarding、privacy、web setup 和 terminal setup 为什么不能共用一种撤销语义 | [复杂 Slash Command 生命周期](analysis/complex-slash-command-lifecycles.md) |
| 为什么核心参考是 29 项，bundle 却有 80 个 `Yi({...})` 注册调用点 | [工具注册、条件工具与宿主表面](analysis/tool-registration-and-host-surfaces.md) |
| 29 项核心终端参考工具分别改变什么状态、哪些副作用不能 rewind | [核心终端工具逐项参考](analysis/builtin-tools-reference.md) |
| Brief 模式为什么普通文字存在但主视图仍可能看不到，附件为什么桌面与手机结果不同 | [Brief 与用户可见输出](analysis/brief-mode-and-user-visible-output.md) |
| Plan Mode 为什么能读文件却不能改业务代码，批准后又怎样恢复原 permission mode | [Plan Mode 与人工审批](analysis/plan-mode-and-human-approval.md) |
| `--json-schema` 为什么不是对最终文本做一次 `JSON.parse` | [Structured Output 与 Schema 合同](analysis/structured-output-and-schema-contract.md) |
| REPL 为什么能跨轮保留变量，却不会在 resume 时再次执行旧 Bash/Edit | [REPL 程序化工具运行时](analysis/repl-programmatic-tool-runtime.md) |
| 模型结束会话前哪些规则是客户端硬控制，哪些只是工具 prompt 约束 | [EndConversation 风控](analysis/end-conversation-risk-control.md) |
| Remote routine、self-hosted runner 和 queued notification 分别由谁持有、怎样背压和确认 | [Remote Routines、Runner 与 Notifications](analysis/remote-routines-runner-and-notifications.md) |
| Connector suggestion 为什么不等于安装，MCP refresh 为什么不等于新工具已进入当前请求 | [Connectors、Catalog 与 MCP Operators](analysis/connectors-catalog-and-mcp-operators.md) |
| ClaudeDesign 与 Projects 为什么不是旧 DesignSync 的别名，上传怎样防路径替换 | [ClaudeDesign 与 Projects](analysis/claude-design-and-projects.md) |
| Settings 为什么写入后不一定立刻被所有子系统采用，policy helper 失败后怎样恢复 | [Settings 解析、合并与热重载](analysis/settings-resolution-and-reload.md) |
| 156 个 settings 字段各自从哪里来、怎样 merge、由谁消费 | [Settings 全字段参考](analysis/settings-reference.md) |
| 为什么 `claude --help` 看不到 daemon/runner/hidden 命令，alias 和 gate 到底怎样分流 | [完整 CLI 命令树](analysis/cli-command-reference.md) |
| `--print`、stream-json、control RPC、event 和终态怎样配对 | [CLI、SDK 与输出协议](analysis/cli-sdk-output-protocol.md) |
| Plugin 安装后为什么仍不可见，Skill/command/LSP 何时刷新 | [Plugins、Skills、Commands 与 LSP](analysis/plugins-skills-commands-lsp.md) |
| 103 个 slash command 哪些可见、谁执行、改变什么状态 | [Slash Command 全量参考](analysis/slash-command-reference.md) |
| 31 个 Hook 事件何时运行、能阻止或修改什么 | [Hooks 全事件参考](analysis/hooks-event-reference.md) |
| 32 个 Storage namespace 各存什么、怎样写、transcript 如何压实、哪些只是声明 | [Storage v5 全量参考](analysis/storage-v5-reference.md) |
| Workflow、Artifact、Design 为什么不是同一种“生成内容” | [Workflow、Artifact 与 Design](analysis/workflow-artifact-design.md) |
| 同一版本为什么不同账号拿到不同功能，flag 缓存怎样刷新 | [Feature Flags 与 Remote Config](analysis/feature-flags-remote-config.md) |
| TUI 输入、拼写、图片、语音、IDE、Chrome 的状态怎样汇入 Agent Loop | [TUI、媒体、IDE 与 Chrome](analysis/tui-input-accessibility-media-ide-chrome.md) |
| 后台命令、定时唤醒、Channel、Remote Control、Cloud 到底在哪里跑 | [后台执行、Channels 与 Cloud](analysis/cloud-background-channels.md) |
| system prompt、messages、tools、provider 和请求体怎样装配 | [技术架构导读](analysis/technical-architecture.md) |
| Prompt Cache、Tool Search、microcompaction 和 auto-compact 有什么区别 | [上下文治理与多层缓存](analysis/context-governance-and-caching.md) |
| Resume、fork、rewind、checkpoint 和 Memory 分别恢复什么 | [会话、检查点与 Memory](analysis/sessions-checkpoints-memory.md) |
| 工具执行为什么还要经过 hook、permission、policy 和 sandbox | [工具、权限与 Hooks](analysis/tools-permissions-hooks.md) |
| Auto Mode 为什么有时放行、有时弹框、有时因 unavailable 而拒绝 | [Auto Mode 两阶段分类器](analysis/auto-mode-classifier.md) |
| Plugin Eval 的高分是否真由插件造成，Delta 什么时候失效 | [Plugin Evaluation Harness](analysis/plugin-evaluation-harness.md) |
| 退出终端后谁继续持有后台 Agent，attach 与 respawn 为什么会失败 | [Runtime Supervision](analysis/runtime-supervision-and-processes.md) |
| Enterprise Gateway 怎样串联身份、策略、路由、花费和遥测 | [Enterprise Gateway Runtime](analysis/enterprise-gateway-runtime.md) |
| 登录成功后哪些账号、组织、订阅和 cache 状态真正换代 | [Auth、账号与订阅生命周期](analysis/auth-account-and-subscription-lifecycle.md) |
| 不可信仓库什么时候才允许加载 hooks、MCP、skills 和 helper | [Onboarding 与 Workspace Trust](analysis/onboarding-workspace-trust-and-safe-startup.md) |
| Thinking、Effort、Fast Mode 为什么开启后仍可能降级 | [Thinking、Effort 与 Fast Mode](analysis/thinking-effort-and-fast-mode.md) |
| `/usage` 的 token、美元、额度、credits 和自动续跑分别是什么 | [Usage、成本、Credits 与 Limits](analysis/usage-cost-credits-and-limits.md) |
| purge/import 为什么失败后仍可能留下部分磁盘变化 | [Project Purge、Import 与数据生命周期](analysis/project-purge-import-and-data-lifecycle.md) |
| sandbox status 成功为什么不等于当前 Bash 已被隔离 | [Sandbox 安装与运行 Enforcement](analysis/sandbox-install-and-runtime-enforcement.md) |
| 主 API 代理正常但 MCP/AWS/WebSocket/OTLP 仍失败时怎么查 | [Proxy、NO_PROXY、CA 与 mTLS](analysis/network-proxy-ca-and-mtls.md) |
| `/goal` 为什么会在模型准备结束时再开一轮 | [Active Goal 与 Stop-loop](analysis/active-goal-and-stop-loop.md) |
| recap、summary、suggestion、feedback 和长期 memory 是否同一机制 | [后台模型任务与 Memory Consolidation](analysis/background-model-tasks-and-memory-consolidation.md) |
| Advisor 是不是第二个本地 Agent、费用和上下文怎么变化 | [Advisor 双模型运行时](analysis/advisor-dual-model-runtime.md) |
| Ultrareview 在哪里审、哪里修、`--post` 实际写了什么 | [Ultrareview 云端审查](analysis/ultrareview-cloud-review.md) |
| MCP 工具何时刷新，子 Agent 和后台任务怎样回传结果 | [MCP、Agents 与后台协作](analysis/mcp-agents-background.md) |
| Retry、fallback、reactive compact 和 file rewind 分别恢复哪一层 | [韧性与恢复](analysis/resilience-and-recovery.md) |
| 模型别名、provider、凭据、base URL、beta 和 request body 怎样决定 | [模型、认证、Provider 与请求装配](analysis/models-auth-providers-request.md) |
| 99 条 API path 和 53 个 Beta 哪些是产品 consumer、Gateway handler、SDK 或内嵌文本 | [API、Beta 与路由所有权](analysis/api-beta-route-ownership.md) |
| 为什么 settings 或 feature flag 写了却不生效 | [Settings、Feature Flags 与 Managed Policy](analysis/settings-feature-flags-policy.md) |
| TUI、IDE、Remote Control 和 Cloud Session 谁真正持有执行状态 | [TUI、IDE、Remote Control 与 Cloud Session](analysis/tui-ide-remote-cloud.md) |
| 安装、更新、Doctor 和版本回退怎样验证真实二进制 | [安装、更新、Doctor 与版本生命周期](analysis/install-update-doctor-lifecycle.md) |
| `.node` 模块怎样连接 JavaScript、N-API、Rust/Swift 和 macOS | [Native Bridge 与 JavaScript Runtime](analysis/native-bridge-runtime.md) |
| 一方事件、OTEL、Datadog、错误上报和本地诊断记录什么 | [遥测、日志与诊断](analysis/telemetry.md) |
| 一次 API、工具、compact、session 或 MCP 故障应该按什么事件顺序排查，1,441 个事件各有哪些字段和出口资格 | [遥测场景语义索引与逐事件证据](analysis/telemetry-event-catalog.md) |
| `Error(...)`、debug log、tool failure、abort 和 LSP diagnostics 怎样进入恢复与用户结果 | [错误与诊断机制图谱](analysis/error-diagnostic-atlas.md) · [逐 callsite 精确 owner 索引](analysis/error-diagnostic-owner-index.md) |
| JSONL 中 `comparisonKey`、payload、schema 和 model 字段怎么读 | [机器清单字段阅读指南](analysis/inventory-field-guide.md) |
| bundle 到底还能提取出哪些产品能力和证据 | [全量可提取能力面](analysis/source-surface.md) |

## 每篇文章怎么读

核心专题都按三层组织：

1. **60 秒模型**：读者问题、单句结论、贯穿场景、状态表和机制图。
2. **完整机制**：调用顺序、状态字段、gate、优先级、阈值、并发、失败与恢复。
3. **证据层**：`2.1.235` 源码范围、精确二进制 Probe、literal output、exit status 和不可证明边界。

图是为了先把状态变化讲清楚，不会替代字段、阈值、失败路径或源码证据。
