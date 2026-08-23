# Claude Code CLI 2.1.235 全面性审计与收口合同

本文不负责证明“文章很多”，而是回答一个更严格的问题：Claude Code CLI `2.1.235` 发布物中能够归属于产品的每一块能力，是否已经有足够准确、可读、可复核的人类说明。

当前结论：能力矩阵把 `2.1.235` 发布物中可归属于产品的 57 个客户端能力面标为机制层 `Deep`，服务端、账号实时状态、第三方实现和构建前源码单列为 `Boundary`。这里的 `Deep` 只表示该能力已有 owner、生命周期、gate、失败恢复和边界说明，**不等于所有 identifier、字段和分支都完成逐项 consumer 追踪，也不等于 validator 已对 57 项逐一建立同等强度的深度合同。** 本轮除修正 29 项核心参考、80 个同工厂 AST 注册调用点和 Brief 主视图三组旧口径外，还把 Plan Mode、Structured Output、Artifact Watch、`/insights`、CLI 启动资源和复杂 Slash Command 提升为独立能力面，并对 REPL、EndConversation、Remote/Runner/Notifications、Connector/Catalog/MCP、ClaudeDesign/Projects 建立独立读者优先专题和机制证据；Telemetry event catalog、API/Beta route ownership 与 Error/Diagnostic atlas 则把三个最容易被字符串清单误读的横切面绑定回现有能力 owner。

这里必须区分三个层级：`Deep` 表示能力级 owner、调用顺序、gate、失败恢复、用户影响和证据边界已讲清；`Static immediate consumer` 表示某个 identifier 已绑定 lexical function、read/write/delete 或 immediate role/operator/target，但全部 caller、二次 gate、状态变化和失败恢复还没有人工收口；`Static consumer` 教学解释才表示该逐项机制已完成。`Boundary` 只保留给服务端状态、最终运行时动态名称、第三方内部、缺失源码或发布物之外的事实；不得用 Boundary 掩盖可继续追的客户端欠账。

[模型只有提案权：2.1.235 本地执行系统解剖](product-surface-evidence-map.md) 继续作为发布路由。它用三个状态世界串起能力编译、Agent Loop、分层风控、上下文治理、Telemetry、Resume、MCP/子 Agent、Artifact 和 Native/Voice，不再把文件数、字段数和完成度统计放在正文中制造深度；完整数量、canonical hash、三轴分类和语义欠账移到 [机器证据索引](product-surface-inventory-index.md)。逐 identifier 参考已将 2,548/2,548 个环境 access 和 498/498 个 Feature callsite 绑定到 lexical function 与 immediate consumer context：145 个动态环境下标中只有 7 个满足完整静态支配/引用证明，覆盖 22 个有限名称；138 个剩余项保留运行时表达式和 7 类主失败链。307 个静态环境名称已完成人工 consumer 合同，606 个已知静态名称保留 Semantic follow-up，80 个 typed 声明没有静态 consumer。361 个静态 Feature key 中 150 个已完成人工合同，其余 211 个保留 immediate role/operator/target，codename 只标 `Opaque name`。

## “全面”到底怎样判定

一块能力只有同时回答下列问题，才能从“发现过”升级为“讲清楚”：

| 维度 | 必须回答的问题 | 可接受证据 |
| --- | --- | --- |
| 产品归属 | 它是一方产品代码、依赖、内嵌文档还是 heuristic？ | canonical bytes、AST/catalog、调用点分类 |
| 入口 | 用户、CLI、SDK、hook、协议或后台事件从哪里进入？ | command/schema/注册表；仅能证明 surface 时必须标注 |
| 消费者 | 哪个可达分支读取输入并改变状态？ | readable JS 真实 consumer，或 exact-binary Probe |
| 状态所有权 | 状态属于当前 render、进程、session、project、account、remote service 还是外部系统？ | 状态对象、storage namespace、协议字段 |
| 调用顺序 | 解析、校验、gate、执行、持久化、通知按什么顺序发生？ | 完整调用链，而非单个字符串 |
| Gate/优先级 | provider、账号、feature、setting、policy、trust、平台如何共同决定可达性？ | 分支与 precedence；远端值保持 Boundary |
| 默认/阈值 | 默认值、上限、timeout、buffer、retention、并发和重试是多少？ | 常量或 schema default；缺失时明确“未在 schema 声明” |
| 成功结果 | 哪个字段、事件、文件或 UI 状态证明成功？ | 返回 schema、事件、持久化对象或 Probe literal result |
| 失败与恢复 | 校验失败、权限拒绝、超时、断线、进程退出后如何处理？ | error branch、retry/fallback、terminal state |
| 副作用 | 哪些动作已发生且不能被 tombstone、resume、rewind 撤销？ | tool/native/network/file 边界 |
| 用户影响 | 对延迟、token、费用、隐私、安全、可恢复性和可操作性有什么影响？ | 由本版机制推导，并注明服务端边界 |
| 版本边界 | 哪些是 `2.1.235` Static/Probe，哪些只是当前 Public 或不可恢复信息？ | mechanism evidence registry 与 public manifest |

### 四种覆盖状态

| 状态 | 含义 |
| --- | --- |
| `Deep` | 已有读者优先专题，并覆盖上述完整合同；强结论有 Static/Probe/Boundary 证据 |
| `Documented` | 已有人类说明，但部分字段、生命周期、失败或用户影响仍需下钻 |
| `Inventory only` | 只有 schema/catalog/string/清单，不能代替机制说明 |
| `Boundary` | 发布物不携带实现，例如服务端 abuse score；文档必须解释为何不能恢复 |

## 权威能力面

本矩阵只把下列材料当作穷举入口：

1. `analysis/unpack-manifest.json` 的 15 个实际 packed 文件；
2. `analysis/cli-surface.txt` 的公开顶层 help token，以及 `analysis/cli-command-inventory.json` 的 90 个 Commander/manual/fast-path 路径、8 个内部入口和 65 组精确二进制 help/失败 Probe；
3. `analysis/source-inventory/summary.json` 注册的 71 类确定性清单；
4. 一方集合：29 项人工维护的核心终端 tool reference、80 个同工厂 AST 注册调用点（77 个静态 name、3 个动态 name expression）、156 个 direct root setting、103 个静态 slash command、31 个 hook event、89 个 SDK control subtype、44 个 output protocol event、32 个 Claude storage namespace、17 个 baked model entry、1,441 个静态一方遥测事件、99 条 API path、53 个 Beta identifier、4,831 个错误构造调用点和 5,403 个 diagnostic 调用点；这些数量证明集合/调用点没有漏采，不自动证明逐 identifier 业务语义已经恢复；
5. `analysis/release-notes.md` 的 `2.1.235` 19 条发布变化；
6. `analysis/mechanism-evidence.jsonl` 的 335 条唯一 claim、48 个 topic 与 44 条 exact-binary Probe 结论；
7. 5 个 shipped `.node` 及其 7 个 Mach-O slice。

`known-tool-catalog.txt` 中的 106 个 `mcp__github__*` 属于内嵌 MCP/文档能力面，不是 106 个 Claude Code 内置工具。Chart.js、Highlight.js、Mermaid 等是 Artifact 渲染链依赖；只有进入可达 Artifact consumer 后才能写成产品机制的一部分。

## 当前覆盖矩阵

| # | 能力面 | 权威产品 surface | 当前人类文档 | 当前状态 | 收口前还需要什么 |
| ---: | --- | --- | --- | --- | --- |
| 1 | 发布物、提取与证据边界 | 15 packed files、bytecode、hash、manifest | README、`source-surface.md`、`technical-architecture.md` | Deep | 保持不可恢复源码边界，不把 compatible reconstruction 称为原始源码 |
| 2 | 请求装配、模型、provider、API/Beta 与凭据选路 | 17 model entries、4 aliases、99 API paths、53 Beta identifiers、provider/credential branches | `models-auth-providers-request.md`、`api-beta-route-ownership.md`、完整说明书 | Deep | 已逐项区分产品 consumer、发布物内 Gateway handler、SDK/依赖、prefix/allowlist 和内嵌参考文本；header/path 存在不证明 runtime 已发送或服务端已开放，账号/组织/subscription 生命周期见第 40 项 |
| 3 | Agent Loop | loop state、stream parser、tool batch、terminal reason | `agent-loop.md`、完整说明书 | Deep | 保持并发、maxTurns、Stop hook、副作用边界回归 |
| 4 | Context、Prompt Cache、Tool Search、compact | cache/compact constants、request fields、Probe | `context-governance-and-caching.md`、`compact-visual-guide.md` | Deep | 服务端 cache 命中和账单仍为 Boundary |
| 5 | Session、transcript、fork、checkpoint、memory | message graph、32 storage namespaces 中相关对象 | `sessions-checkpoints-memory.md`、`storage-v5-reference.md` | Deep | 保持 transcript、storage backend 和外部副作用三层边界 |
| 6 | 工具统一控制管线 | lookup/schema/hook/permission/sandbox/call/result | `tools-permissions-hooks.md` | Deep | 与 29 个具体工具的专属状态/失败语义互链 |
| 7 | 核心终端参考、条件工具与宿主注册表面 | `builtin-tool-identifiers.txt`、`tool-registrations.jsonl` | `builtin-tools-reference.md`、`tool-registration-and-host-surfaces.md`、`workflow-artifact-design.md`、`repl-programmatic-tool-runtime.md` | Deep | 29/29 人工维护核心参考与 80/80 同工厂 AST 调用点均精确覆盖；调用点按 29 Core、28 Conditional CLI、16 Hosted/product、4 Internal/eval、3 Dynamic factory 做证据驱动的人工归属，并明确直接调用点、工厂模板、静态调用展开、runtime enabled 与 request advertised 的区别；REPL 另下钻持久 VM、内层完整权限管线、动态工具、timeout/watchdog 与结果重放 |
| 8 | 31 类 Hooks | `hook-events.txt`、hook transport/runner | `tools-permissions-hooks.md`、`hooks-event-reference.md` | Deep | 31/31 事件字段、时机、matcher、阻塞、timeout、载体和副作用已覆盖；外部 Hook 程序行为仍是 Boundary |
| 9 | MCP、Tool Search 与动态刷新 | transports、generation、registry、OAuth | `mcp-agents-background.md`、`connectors-catalog-and-mcp-operators.md` | Deep | 已覆盖 request-time generation、Tool Search、live client refresh、kept-previous、concurrent sequence、wait 状态分类、resource list/read/dir 和 cache invalidation；refresh 不拨号、不热替换已发出的 request，第三方 MCP 语义保持 Boundary |
| 10 | Custom Agent、subagent、team、task、mailbox | Task/SendMessage/worktree、protocol/telemetry | `mcp-agents-background.md` | Deep | 已覆盖 child-loop isolation、Task registry/claim、panel 投影、mailbox delivery/ack/size、跨 session channel drain/redelivery、worktree 和 durable/ephemeral owner；远端 coordination service 与旧进程外实体是否仍存活保持 Boundary |
| 11 | Error/Diagnostic、retry、fallback、resume、rewind | 4,831 error constructors、5,403 diagnostic callsites、error classifiers、counters、tombstones | `error-diagnostic-atlas.md`、`resilience-and-recovery.md`、`cloud-background-channels.md` | Deep | 已区分异常对象、abort/expected/permission/sandbox/auth 分类、局部恢复、tool result、stderr/TUI、LSP attachment、Hook/telemetry 观察面和外部副作用；constructor/diagnostic inventory 现已附 lexical function 与 immediate consumer context，但逐 callsite 的 Product/Dependency、catch owner 和用户 surface 仍是客户端 Semantic follow-up |
| 12 | Telemetry、OTEL、Datadog、GrowthBook、诊断 | 1,441 first-party events、2,194 callsites、181 Datadog allowlist、26 OTEL events、8 metrics、10 spans | `telemetry.md`、`telemetry-event-catalog.md` | Deep | transport/queue/sampling/privacy/flush/retry 生命周期为机制层 Deep；raw API body 三模式已有 wire Probe；原 family `tengu_other` 的 911 event / 1,297 callsite 只接受 25 条 exact caller allowlist，当前完整收口 5 Single-owner、1 Cross-owner，905 event / 1,272 callsite 保持 Unresolved。event/function/consumer/comparisonKey/fingerprint 必须同时匹配，导航 range 不参与分类；运行 gate、采样、动态 payload、远端接收与保留仍需各自证据 |
| 13 | Native bridge 与媒体底座 | 5 `.node`、7 slices、JS wrappers | `native-bridge-runtime.md`、`tui-input-accessibility-media-ide-chrome.md` | Deep | arm64 5 模块完成 23/23；x86_64 supplied compatible artifact 5/5 完成 provenance/load/export，原版有 x86 slice 的 Input/Swift 完成 20/20；x86 build command 仅为 recipe，真实麦克风、键鼠注入与跨权限环境仍需平台 Probe |
| 14 | Settings 来源、合并、policy、reload | 156 direct keys + 4 spreads | `settings-resolution-and-reload.md`、`settings-feature-flags-policy.md`、`settings-reference.md` | Deep | 156/156 已按 Probe、alias consumer、Static consumer、declaration 互斥分级；已覆盖进程 store、五层/admin tier、四类 merge、ConfigChange、程序写、consumer 刷新、remote/helper 恢复，实时管理员 payload 与外部 helper 行为保持 Boundary |
| 15 | Feature flags 与 remote config | 361 keys、498 callsites、GrowthBook | `settings-feature-flags-policy.md`、`feature-flags-remote-config.md`、`feature-flag-reference.md` | Deep | evaluation/cache/refresh/exposure/override 生命周期为机制层 Deep；498/498 callsite 已绑 lexical function 与 immediate role/operator/target，150/361 key 已人工收口 fallback、二次 gate、状态变化和失败边界，余下 211 项保留 Static immediate consumer 与 Semantic follow-up；codename 仅标 Opaque name，账号实时 value/rule/rollout 保持 Boundary |
| 16 | CLI 命令树、print、Agent SDK 输入输出 | `cli-surface.txt`、`cli-command-inventory.json`、input/output schemas | `cli-command-reference.md`、`cli-sdk-output-protocol.md` | Deep | 59 次显式 `.command` 注册、90 个 root/Commander/manual/fast-path 路径和 65 组 help/失败 Probe 已覆盖 alias、hidden/conditional gate、arguments/options、owner、副作用与失败；8 个内部入口另逐项绑定 input protocol、ordered lifecycle、success state、failure boundary、external side effects、dispatcher/handler source；第三方/远端成功保持 Boundary |
| 17 | 89 个 SDK control subtype | `sdk-control-subtypes.txt` | `cli-sdk-output-protocol.md` | Deep | 已把 89 拆成 42 request、2 verdict、46 observation（`success` 重叠），逐项覆盖方向、字段、response、owner、失败、取消和副作用；schema-only 与 worker-only 分支保持证据分级 |
| 18 | 44 个 output protocol event | `output-protocol-event-identifiers.txt` | `cli-sdk-output-protocol.md` | Deep | 已逐项区分 36 个 named-SSE parser event、6 个 webhook-only identifier、1 个 embedded-doc 合同和 1 个词法误报，并解释关联键、终态、reconcile、retry 与幂等边界 |
| 19 | 103 个 slash command | `slash-command-identifiers.txt` | `slash-command-reference.md`、`plugins-skills-commands-lsp.md` | Deep | 103/103 已逐命令解释 type/twin、gate、owner、成功、失败和副作用；账号/host 远端成功仍按条目保留 Boundary |
| 20 | Plugins、marketplaces、Skills、commands | plugin registry/cache、command reload、skill sources | `plugins-skills-commands-lsp.md`、`connectors-catalog-and-mcp-operators.md` | Deep | 覆盖来源信任、安装/enable/session 分层、依赖、listing、reload、冲突与成本，并下钻账号 Plugin/Skill catalog、`user:plugins` scope expansion、分页/重试、403 not-entitled 与 suggestion-card 非安装语义；精确二进制已验证 `--plugin-dir` Skill listing、dispatch acknowledgement 和正文注入，任意第三方扩展语义属于 Boundary |
| 21 | LSP 生命周期与工具 | built-in `LSP`、server/plugin/reconnect/diagnostics | `plugins-skills-commands-lsp.md`、`builtin-tools-reference.md` | Deep | 9 operations、配置、generation、process、diagnostics、超时/崩溃/重连已覆盖；Probe 验证 stdio initialize/open/definition/shutdown、1-based 到 0-based 与 result 回灌，第三方索引算法属于 Boundary |
| 22 | Workflow、Artifact、Chart/Mermaid/HTML | built-in tools + bundled payloads | `builtin-tools-reference.md`、`workflow-artifact-design.md` | Deep | Workflow/journal、Artifact identity/upload/CSP/watch/comments/DB/assets 已串联；真实远端服务可用性保持 Boundary |
| 23 | DesignSync、ClaudeDesign、Projects、文件传输 | known product tools、OAuth、upload/download paths | `workflow-artifact-design.md`、`claude-design-and-projects.md` | Deep | 已区分旧 DesignSync 与 ClaudeDesign 动态 MCP operation；覆盖 session/catalog、consent、15 分钟精确 path plan、durable grant、结果预算、Projects 五方法、OAuth scope、RAG 403 fallback、TOCTOU 上传和知识预算；账号/project 服务端状态为 Boundary |
| 24 | Chrome bridge 与 WebBrowser | CLI/command/tool/bridge lifecycle | `tui-input-accessibility-media-ide-chrome.md` | Deep | 已覆盖 socket/token/pairing/permission timer/tool call/断线/迟到副作用；真实扩展与页面兼容仍需 Probe |
| 25 | TUI 输入、keybindings、渲染与可访问性 | settings/events/release branches | `tui-input-accessibility-media-ide-chrome.md` | Deep | renderer/composer/Vim/highlight/permission comment/screen reader/native cursor 与竞态已覆盖 |
| 26 | Voice/audio/image/spellcheck | native module、commands/settings、policy gates | `tui-input-accessibility-media-ide-chrome.md`、`native-bridge-runtime.md` | Deep | capture/STT/retry/circuit breaker、paste/image/native processor/spellcheck 生命周期已覆盖；真实设备/TCC 为 Boundary |
| 27 | IDE/VS Code | discovery/socket/context/diff/panel/focus | `tui-input-accessibility-media-ide-chrome.md` | Deep | discovery/auth/selection/focus/diagnostics/断线 ownership 已覆盖；第三方 IDE host 兼容为 Boundary |
| 28 | Git/worktree/background shell/task | worktree tools、process/task registries | `cloud-background-channels.md` | Deep | checkout owner、后台写保护、task/output/stop、supervisor 和不可逆副作用已覆盖 |
| 29 | Cron、loops、remote routines、channels、主动通知 | Cron tools、RemoteTrigger、scheduled event、commands/settings | `cloud-background-channels.md`、`builtin-tools-reference.md`、`remote-routines-runner-and-notifications.md` | Deep | session/durable schedule、fixed/dynamic loop、Monitor、Push、Channel gate/queue/reconnect 已覆盖；另覆盖 RemoteTrigger 八 action、run/log pagination/condensation，以及通知 100 pending、1000 drained ID、90k drain、87,488 单条、ack/backpressure 与两次 rearm |
| 30 | Remote Control 与 cloud session | CLI/SDK/API/status/daemon | `cloud-background-channels.md`、`tui-ide-remote-cloud.md` | Deep | 本地/远端 owner、重连、附件、create/attach/teleport 已覆盖；登录账户正向服务 Probe 保持 Boundary |
| 31 | CCR、BYOC、自托管 runner、cloud workflow | env/schema/API/tools | `cloud-background-channels.md`、`remote-routines-runner-and-notifications.md` | Deep | bundle/runner/lease/watchdog/token/stage root/capacity/drain 与 Git proxy 边界已覆盖；另下钻九个 operator tool、OAuth-only preflight、20 秒 API、detached spawn/PID、assignment-conflict requeue、2 秒 loopback health/metrics、65,536-byte log tail 与 redaction；实际服务调度为 Boundary |
| 32 | Storage v5 与本地状态目录 | 32 Claude namespaces | `storage-v5-reference.md` | Deep | 32/32 key、scope、write discipline、consumer、敏感度和缺失 consumer 已覆盖；另下钻 transcript legacy/V5 压实、torn tail、shared inode 与并发尾追加；本版自建 backend 不可达 |
| 33 | Install、update、doctor、migration | CLI/install layout/update gates/diagnostics | `install-update-doctor-lifecycle.md` | Deep | 保持真实二进制 hash、升级和配置 schema 回退边界 |
| 34 | `2.1.235` 19 条 release changes | release notes + matching source evidence | 完整说明书第 28 章及 LSP/cloud/TUI 专题 | Deep | 19 条均已回填专属生命周期；跨版本归因仍区分 2.1.234 与 2.1.235 |
| 35 | 本地风控与企业治理 | risk surface、sandbox/policy/credentials/trust | 风控 README、工具/settings/遥测专题、`end-conversation-risk-control.md` | Deep | 已覆盖权限、路径/网络/凭据/trust/policy/sandbox 与 EndConversation 的发布/模型/宿主 gate、连续两次调用、主会话、marker、abort、terminal guard；持续辱骂/已警告/用户确认/自伤禁止主要是 prompt 约束，服务端 abuse score、封禁模型和模型语义遵循保持 Boundary |
| 36 | Auto Mode 两阶段权限分类 | deterministic permission pipeline、trusted rule sources、classifier request/verdict、Hook | `auto-mode-classifier.md`、完整说明书第 36 章 | Deep | 权限前置层、fast path、`$defaults`、Stage 1/2、fail-closed、fallback、setup/hash 与用户影响已覆盖；模型内部 safeguard 和真实线上质量保持 Boundary |
| 37 | Plugin Evaluation Harness | `plugin eval` command、case schema/trust、ablation、grader/report | `plugin-evaluation-harness.md`、完整说明书第 37 章 | Deep | with/without、六类 grader、3 票多数、费用 partial、scaffold、CI exit 和 Delta 可比性已覆盖；尚无绑定本版二进制的付费 eval 正向 Probe |
| 38 | Runtime Supervision 与后台进程所有权 | daemon/PTY/worker/rendezvous/roster/job record | `runtime-supervision-and-processes.md`、完整说明书第 38 章 | Deep | cold start、processWrapper、socket auth、ring、adopt/respawn、stale heartbeat、pressure reap 与 `asyncRewake` 已覆盖；真实断电/service-manager 全组合保持 Boundary |
| 39 | Enterprise Gateway Runtime | gateway command、OIDC/session、managed policy、providers、CRI、spend、OTLP | `enterprise-gateway-runtime.md`、完整说明书第 39 章 | Deep | 启动、route 顺序、身份/策略、credential replacement、failover、Postgres、JWKS/webhook、metering 和 telemetry 已覆盖；IdP/CRI issuer/provider 内部实现保持 Boundary |
| 40 | Auth、账号、组织、订阅与 setup-token | `auth login/status/logout`、OAuth/token store、org/subscription consumers | `auth-account-and-subscription-lifecycle.md`、模型/认证专题 | Deep | 远端撤销、组织 entitlement 和账号后台状态保持 Boundary |
| 41 | Onboarding、workspace trust 与安全启动 | setup state、trust scanner、safe/bare/print startup branches | `onboarding-workspace-trust-and-safe-startup.md`、工具/settings 专题 | Deep | trust 前项目 helper 不执行；第三方项目内容本身保持外部风险 |
| 42 | Thinking、Effort 与 Fast Mode | thinking request shape、effort precedence、service-tier/cooldown state | `thinking-effort-and-fast-mode.md`、请求装配专题 | Deep | 服务端真实调度、质量和延迟收益保持 Boundary |
| 43 | Usage、成本、credits、limits 与自动续跑 | usage accumulator、headers/API quota state、checkpoint/auto-resume | `usage-cost-credits-and-limits.md`、遥测/会话专题 | Deep | 真实账单、额度政策、credit purchase 和 reset 服务端行为保持 Boundary |
| 44 | Project purge、配置/会话导入与数据生命周期 | purge plans、import digest、ZIP/manifest guards、Storage history rewrite | `project-purge-import-and-data-lifecycle.md`、Storage 专题 | Deep | exact-binary 已证明 purge/JSON dry-run 的 domain 零写入、真实 JSON import 的 0600 transcript/父链/reserved-name 降权，以及 ZIP manifest mismatch exit 1 前的部分持久化；config import 在离线内置 false gate 下仍不可正向 apply，外部归档来源可信度保持 Boundary |
| 45 | Sandbox 安装与逐命令运行 enforcement | Windows install/status、session initializer、command wrapper、cleanup | `sandbox-install-and-runtime-enforcement.md`、工具/权限专题 | Deep | installed 不等于当前命令已隔离；跨平台内核实现保持平台 Boundary |
| 46 | Proxy、NO_PROXY、CA 与 mTLS | fetch/axios/ws/AWS/MCP adapters、CA store、cert reload、CCR relay | `network-proxy-ca-and-mtls.md`、Enterprise/遥测专题 | Deep | 每个第三方 transport 和远端 TLS/policy 必须独立验证 |
| 47 | Active Goal 与 Stop-loop | `/goal` state、session Stop prompt hook、blocking cap、SDK/Remote projection | `active-goal-and-stop-loop.md`、Agent Loop/Hooks 专题 | Deep | 目标是否真实完成仍由模型判定；已发生副作用不因目标清除而回滚 |
| 48 | 后台模型任务与 Memory consolidation | background model queue、dedupe/cache、memory merge/flush lifecycle | `background-model-tasks-and-memory-consolidation.md`、会话/后台专题 | Deep | 服务端模型质量和跨设备最终一致性保持 Boundary |
| 49 | Advisor 双模型运行时 | primary/advisor ownership、snapshot request、feedback injection、cost gate | `advisor-dual-model-runtime.md`、模型/Agent Loop 专题 | Deep | Advisor 质量增益和服务端 capacity 保持 Boundary |
| 50 | Ultrareview 云端审查 | command gate、snapshot/upload、cloud task/event、review result integration | `ultrareview-cloud-review.md`、Cloud/后台专题 | Deep | 云端 worker、仓库权限、retention、计费和最终审查质量保持 Boundary |
| 51 | Brief Mode 与用户可见输出 | `SendUserMessage`/`Brief` tool、`--brief`、`/brief`、default view、renderer、attachment lanes、turn-end sentinel | `brief-mode-and-user-visible-output.md`、完整说明书第 51 章 | Deep | 已覆盖 entitlement/enable/tool assembly、普通 text 与主视图投影、附件校验/部分交付、单次漏调补发、成本隐私与不可逆发送边界；账号实时 entitlement 和远端 viewer 服务保持 Boundary |
| 52 | Plan Mode 与人工审批 | `EnterPlanMode`、permission context、plan attachment/file、`AskUserQuestion`、`ExitPlanMode`、team/AFK/SDK/remote approval | `plan-mode-and-human-approval.md`、完整说明书第 52 章 | Deep | 已覆盖进入专用批准、`prePlanMode`、5-turn/attachment reminder、plan file 写入例外、MCP/permission floor、200,000 字符 review withholding、批准/拒绝/mode 恢复、team lead、AFK partial answers、SDK park 与 Ultraplan；远端审批存储和计划质量保持 Boundary |
| 53 | Structured Output 与 Schema 终态 | `--json-schema`、AJV/strict schema、`StructuredOutput` tool、attempt/attachment/tombstone/result | `structured-output-and-schema-contract.md`、完整说明书第 53 章 | Deep | 已覆盖 JSON/object guard、100k/10k/32 深度与节点预算、tool injection、wire strict/Foundry strip、本地 validation、默认 5 次修正、fallback tombstone、最后存活 attachment 和 `error_max_structured_output_retries`；服务端 constrained decoding 与业务真实性保持 Boundary |
| 54 | Artifact Watch 与评论自动响应 | watch baseline/digest、untrusted comment triage、read-only analyst、permission probe、ack/reply/edit/resolve | `artifact-watch-comment-autoreact.md`、完整说明书第 54 章 | Deep | 已覆盖 local/interactive/environment gate、5s coalesce、2s dwell、60/h cap、30s 内 3 次 loop breaker、3 次 denial breaker、只读 analyst、写前权限探针、ack 与完整管线竞态；远端 Artifact 服务与已发副作用保持 Boundary |
| 55 | `/insights` 历史分析管线 | transcript parser、metadata/facet cache、long-session reduction、7+1 model analysis、HTML report | `insights-history-analysis-pipeline.md`、完整说明书第 55 章 | Deep | 已覆盖 200+200 metadata 刷新、50 facet、500/300 字符截断、30k/25k 分块、270,336 output-token 静态上限、0600 报告和 facet 不校验 transcript mtime 的准确性缺口；模型语义质量保持 Boundary |
| 56 | CLI 启动文件、URL 插件与 Deep Link | `--file`、`--plugin-url`、`--handle-uri`、uploads、ZIP gate、plugin graph、cwd/prefill | `cli-startup-files-plugins-deeplinks.md`、完整说明书第 56 章 | Deep | 已覆盖 file 的 first-party/HIPAA/token gate、60s/3 attempts/5 concurrency、plugin 30s/256MiB 下载与 512MiB/1GiB/100k/50:1 ZIP gate、session cache/MCP/precedence、argv 注入拒绝、shell-safe 启动与 prefill 不自动提交；远端内容与 URL 供应链保持 Boundary |
| 57 | 复杂 Slash Command 外部系统生命周期 | `/install-github-app`、`/team-onboarding`、`/privacy-settings`、`/web-setup`、`/terminal-setup` 及 URL handoff | `complex-slash-command-lifecycles.md`、`slash-command-reference.md`、完整说明书第 57 章 | Deep | 已覆盖命令专属 gate、现状发现、人工确认、GitHub/Claude/file/OS 副作用、部分成功、backup 恢复和手工撤销；浏览器打开不证明远端流程完成 |
| 58 | 服务端、模型内部与构建前源码 | bundle 不携带 | 多篇边界说明 | Boundary | 不得用 header、event、字符串或当前官网替代实现证据 |

## 数量覆盖不能冒充机制覆盖

以下数字按人工 Markdown 统计，排除 generated comparison、public excerpts 与本矩阵自身，包含 README 和 `ARTICLES.md`。它们只证明 identifier 在人类入口中出现，不证明 consumer、失败分支和用户影响已经讲深：

| 集合 | 总数 | 审计时在人类文档中出现 | 未出现 | 正确解释 |
| --- | ---: | ---: | ---: | --- |
| direct root settings | 156 | 156 | 0 | `settings-reference.md` 提供全量入口，但大量条目仍是 declaration/surface |
| curated core terminal references | 29 | 29 | 0 | `builtin-tools-reference.md` 已逐项覆盖；29 来自维护 name set 与静态 assignment 的交集，不是完整装配数组或一次请求的实际 `tools[]` 数量 |
| tool registration callsites | 80 | 80 | 0 | `tool-registration-and-host-surfaces.md` 精确覆盖 `Yi({...})` AST 调用点与五类人工归属；调用点存在不等于 factory instance、enabled 或 request advertised |
| CLI command paths | 90 | 90 | 0 | `cli-command-reference.md` + structured inventory 区分 Commander、fast path、manual parser 和内部入口；help/registration 不冒充 action 成功 |
| slash commands | 103 | 103 | 0 | `slash-command-reference.md` 已逐命令给出 type/twin、owner、gate 和失败边界；仍不等于所有账号/host 都正向 Probe |
| SDK control subtype | 89 | 89 | 0 | 89 是混合集合；真实 request、notification、compatibility identifier 不能混称已 Probe |
| output protocol event | 44 | 44 | 0 | 已有事件/字段表，大量 host 消费仍是 Boundary |
| Claude storage namespace | 32 | 32 | 0 | `storage-v5-reference.md` 逐项区分真实 consumer 与 Boundary；名字仍不自动证明 backend active、retention 或事务 |
| hook event | 31 | 31 | 0 | `hooks-event-reference.md` 逐事件解释时机、字段、matcher、阻塞和 timeout；外部 Hook 程序仍需各自验证 |

这些数字用来定位入口缺口，不是最终质量 KPI。156/156 或 103/103 只能消灭“没提到”的问题；字段仍必须放回消费者和生命周期，不能通过复制 key 或 identifier 就把对应能力改成 `Deep`。

## Release note 回填要求

`2.1.235` 的 19 条发布说明已经全部收录，但以下条目必须从“版本表格”回填到相应机制：

| 变化 | 必须进入的机制解释 |
| --- | --- |
| LSP reconnect 不再破坏 prompt cache | server generation、dynamic prompt section、cache breakpoint、断线重建 |
| cloud event 不再重复扫描完整历史 | event cursor/增量状态、渲染成本、重复抑制和重连 |
| embedded grep 病态 pattern 修复 | pattern validation、worker/timeout、失败结果与 Agent Loop 反馈 |
| Task panel 状态修复 | task registry 与 UI 派生状态的所有权和一致性 |
| VS Code 多 panel focus 修复 | panel/session identity、focus event、竞争窗口 |
| 列表缩进、方向键+Enter、Shift+Tab、Vim、HTML entity | composer/render state transition，而不是“UI 小修复”一句带过 |

## 自动校验当前能证明什么

validator 现在强制 58 行能力矩阵，对 15 个高风险能力应用 14 个 topic-depth 合同，并对 47 个 mechanism topic 强制 claim 数量、证据类型、源码范围与 anchors；Artifact Watch、`/insights`、CLI 启动资源、复杂 Slash Command、Telemetry catalog、API/Beta owner 与 Error atlas 现在也有独立 topic 最低证据。它还要求 2,548/2,548 个环境 access 与 498/498 个 Feature callsite 都有 lexical context、immediate consumer 与有效范围；但其余 42 个能力面仍未拥有同等强度的 topic-depth/Probe 合同，不能宣传成“57 项都做了语义等价验证”。

它仍不能把“集合完整”自动升级成“机制全面”。继续收口还需要：

1. 每个集合继续拆分提取来源、所有权和证明层级，尤其不能把 whole-bundle AST callsite 统一标成 Product；
2. 每个强运行结论必须有 consumer Static 或 Probe，schema/help-only 只能标 `surface/declaration`；
3. 后续版本若新增 Settings、CLI/SDK、Plugin/LSP surface，必须先补 consumer/lifecycle/Boundary，再允许保持 `Deep`；
4. 服务端 entitlement、feature 实时值、cloud orchestration、第三方 IDE/MCP 和跨平台设备行为保持 Boundary；
5. 新鲜远端检出后重新运行相同校验，避免本地未跟踪文件制造假完整。

## 后续版本回归顺序

1. 每个新版本先重生成 canonical inventory，精确比较核心 tool 集合、同工厂注册对象、分类/gate/alias、156 settings、103 commands、31 hooks、32 storage namespaces、89 SDK subtype 和 44 protocol event。
2. 按状态机比较 Agent Loop/context/session/tool/recovery/model/settings/feature/UI/cloud/native，而不是只看 key 数量或 minified symbol。
3. 将新增/删除 surface 回填专属文章、完整说明书、`ARTICLES.md`、README、机制证据和可编辑图。
4. 对 changed branch 扩充 exact-binary Probe；未触发的 remote/third-party/cross-platform 行为保持 Boundary。
5. 运行全量、负向、隐私、SVG、重建、Probe 与远端 fresh-checkout 验证后再推送。

当前矩阵仍显示 57 项机制层 `Deep`、1 项产品外 `Boundary`，但这不再被解读为“全面完成”。明确剩余工作包括环境名称与 Feature key 的人工语义收口、仍含运行参数的动态环境表达式、905 个 `tengu_other` 事件 caller-owner、error/diagnostic 逐 callsite owner、遥测运行 gate/动态 payload/远端 delivery、未覆盖的高风险正向 Probe 与其余能力面的同等强度深度合同。精确数量由生成参考和产品总纲从机器摘要读取；Anthropic 服务端、账号实时状态、第三方实现、原始 TypeScript/C++/Swift 仓库或 tree-shaking 删除内容仍保持 Boundary。
