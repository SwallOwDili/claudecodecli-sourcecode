# Claude Code CLI 2.1.235 全面性审计与收口合同

本文不负责证明“文章很多”，而是回答一个更严格的问题：Claude Code CLI `2.1.235` 发布物中能够归属于产品的每一块能力，是否已经有足够准确、可读、可复核的人类说明。

当前结论：**`2.1.235` 客户端发布物的主要产品生命周期已经形成系统化深挖，但仍不能把服务端、账号实时状态、所有第三方集成和构建前源码描述成“全部可恢复”。** Agent Loop、上下文、工具控制、会话恢复、遥测、native bridge，以及本轮新增的 Slash Commands、Hooks、Storage v5、Workflow/Artifact/Design、Feature Flags、TUI/媒体/IDE/Chrome、后台/Channels/Cloud 都有独立机制文章和可编辑图。仍为 `Documented` 的表面主要缺真实 host/第三方/跨平台正向 Probe，而不是缺 identifier 入口。

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
2. `analysis/cli-surface.txt` 的顶层 CLI surface；
3. `analysis/source-inventory/summary.json` 注册的 70 类确定性清单；
4. 一方集合：29 个 built-in tool、156 个 direct root setting、103 个静态 slash command、31 个 hook event、89 个 SDK control subtype、44 个 output protocol event、29 个 Claude storage namespace、17 个 baked model entry；
5. `analysis/release-notes.md` 的 `2.1.235` 19 条发布变化；
6. `analysis/mechanism-evidence.jsonl` 与 exact-binary Probe 报告；
7. 5 个 shipped `.node` 及其 7 个 Mach-O slice。

`known-tool-catalog.txt` 中的 106 个 `mcp__github__*` 属于内嵌 MCP/文档能力面，不是 106 个 Claude Code 内置工具。Chart.js、Highlight.js、Mermaid 等是 Artifact 渲染链依赖；只有进入可达 Artifact consumer 后才能写成产品机制的一部分。

## 当前覆盖矩阵

| # | 能力面 | 权威产品 surface | 当前人类文档 | 当前状态 | 收口前还需要什么 |
| ---: | --- | --- | --- | --- | --- |
| 1 | 发布物、提取与证据边界 | 15 packed files、bytecode、hash、manifest | README、`source-surface.md`、`technical-architecture.md` | Deep | 保持不可恢复源码边界，不把 compatible reconstruction 称为原始源码 |
| 2 | 请求装配、模型、provider、auth | 17 model entries、4 aliases、provider/auth branches | `models-auth-providers-request.md`、完整说明书 | Deep | 真实 Bedrock/Vertex/Foundry 凭据闭环保持未 Probe 边界 |
| 3 | Agent Loop | loop state、stream parser、tool batch、terminal reason | `agent-loop.md`、完整说明书 | Deep | 保持并发、maxTurns、Stop hook、副作用边界回归 |
| 4 | Context、Prompt Cache、Tool Search、compact | cache/compact constants、request fields、Probe | `context-governance-and-caching.md`、`compact-visual-guide.md` | Deep | 服务端 cache 命中和账单仍为 Boundary |
| 5 | Session、transcript、fork、checkpoint、memory | message graph、29 storage namespaces 中相关对象 | `sessions-checkpoints-memory.md`、`storage-v5-reference.md` | Deep | 保持 transcript、storage backend 和外部副作用三层边界 |
| 6 | 工具统一控制管线 | lookup/schema/hook/permission/sandbox/call/result | `tools-permissions-hooks.md` | Deep | 与 29 个具体工具的专属状态/失败语义互链 |
| 7 | 29 个内置工具逐项合同 | `builtin-tool-identifiers.txt` | `builtin-tools-reference.md`、`workflow-artifact-design.md` | Documented | 29/29 已有状态所有权和失败边界；未逐工具完成 exact-binary 正向 Probe |
| 8 | 31 类 Hooks | `hook-events.txt`、hook transport/runner | `tools-permissions-hooks.md`、`hooks-event-reference.md` | Deep | 31/31 事件字段、时机、matcher、阻塞、timeout、载体和副作用已覆盖；外部 Hook 程序行为仍是 Boundary |
| 9 | MCP、Tool Search 与动态刷新 | transports、generation、registry、OAuth | `mcp-agents-background.md` | Deep | 插件注入 MCP 与 LSP plugin integration 回填扩展专题 |
| 10 | Custom Agent、subagent、team、task、mailbox | Task/SendMessage/worktree、protocol/telemetry | `mcp-agents-background.md` | Deep | Task panel、跨 session channel、durable owner 继续下钻 |
| 11 | Retry、fallback、resume、rewind | error classifiers、counters、tombstones | `resilience-and-recovery.md`、`cloud-background-channels.md` | Deep | 保持远端服务重试与本地恢复边界 |
| 12 | Telemetry、OTEL、Datadog、GrowthBook、诊断 | 1,441 first-party events、OTEL/Datadog schemas | `telemetry.md` | Deep | 新专题新增事件必须解释通道归属、内容控制与字段 |
| 13 | Native bridge 与媒体底座 | 5 `.node`、7 slices、JS wrappers | `native-bridge-runtime.md`、`tui-input-accessibility-media-ide-chrome.md` | Deep | x86_64 compatible build 未执行；真实麦克风/屏幕/TCC 仍需平台 Probe |
| 14 | Settings 来源、合并、policy、reload | 156 direct keys + 4 spreads | `settings-feature-flags-policy.md`、`settings-reference.md` | Documented | 156/156 已有字段索引；仍需把 declaration 与真实 consumer 逐项分级，不能仅凭命中升级 Deep |
| 15 | Feature flags 与 remote config | 361 keys、498 callsites、GrowthBook | `settings-feature-flags-policy.md`、`feature-flags-remote-config.md` | Deep | 已覆盖 enable、attributes、fresh/disk/default、payload、exposure、refresh、auth reset 与 override dead path；账号实时值保持 Boundary |
| 16 | CLI、print、Agent SDK 输入输出 | `cli-surface.txt`、input/output schemas | `cli-sdk-output-protocol.md` | Documented | 已讲入口、状态和输出链；各 host/thin-client 分支仍需更多 exact-binary Probe |
| 17 | 89 个 SDK control subtype | `sdk-control-subtypes.txt` | `cli-sdk-output-protocol.md` | Documented | 89/89 有协议索引，其中真实请求与通知/兼容标识必须继续区分，不能整体标 Deep |
| 18 | 44 个 output protocol event | `output-protocol-event-identifiers.txt` | `cli-sdk-output-protocol.md` | Documented | 44/44 有字段表；大量 host 消费和终止边界仍是 Boundary |
| 19 | 103 个 slash command | `slash-command-identifiers.txt` | `slash-command-reference.md`、`plugins-skills-commands-lsp.md` | Deep | 103/103 已逐命令解释 type/twin、gate、owner、成功、失败和副作用；账号/host 远端成功仍按条目保留 Boundary |
| 20 | Plugins、marketplaces、Skills、commands | plugin registry/cache、command reload、skill sources | `plugins-skills-commands-lsp.md` | Documented | 已覆盖安装、信任、发现、刷新、冲突、禁用、同步；逐插件运行 Probe 仍取决于具体扩展 |
| 21 | LSP 生命周期与工具 | built-in `LSP`、server/plugin/reconnect/diagnostics | `plugins-skills-commands-lsp.md`、`builtin-tools-reference.md` | Documented | 已覆盖 9 operations、server lifecycle 和错误文本；实际第三方 server 行为仍为外部边界 |
| 22 | Workflow、Artifact、Chart/Mermaid/HTML | built-in tools + bundled payloads | `builtin-tools-reference.md`、`workflow-artifact-design.md` | Deep | Workflow/journal、Artifact identity/upload/CSP/watch/comments/DB/assets 已串联；真实远端服务可用性保持 Boundary |
| 23 | DesignSync、Projects、文件传输 | known product tools、OAuth、upload/download paths | `workflow-artifact-design.md` | Deep | 本地 build/diff/validate/capture、sidecar、ownership、计划和上传边界已覆盖；账号/project 服务端状态为 Boundary |
| 24 | Chrome bridge 与 WebBrowser | CLI/command/tool/bridge lifecycle | `tui-input-accessibility-media-ide-chrome.md` | Deep | 已覆盖 socket/token/pairing/permission timer/tool call/断线/迟到副作用；真实扩展与页面兼容仍需 Probe |
| 25 | TUI 输入、keybindings、渲染与可访问性 | settings/events/release branches | `tui-input-accessibility-media-ide-chrome.md` | Deep | renderer/composer/Vim/highlight/permission comment/screen reader/native cursor 与竞态已覆盖 |
| 26 | Voice/audio/image/spellcheck | native module、commands/settings、policy gates | `tui-input-accessibility-media-ide-chrome.md`、`native-bridge-runtime.md` | Deep | capture/STT/retry/circuit breaker、paste/image/native processor/spellcheck 生命周期已覆盖；真实设备/TCC 为 Boundary |
| 27 | IDE/VS Code | discovery/socket/context/diff/panel/focus | `tui-input-accessibility-media-ide-chrome.md` | Deep | discovery/auth/selection/focus/diagnostics/断线 ownership 已覆盖；第三方 IDE host 兼容为 Boundary |
| 28 | Git/worktree/background shell/task | worktree tools、process/task registries | `cloud-background-channels.md` | Deep | checkout owner、后台写保护、task/output/stop、supervisor 和不可逆副作用已覆盖 |
| 29 | Cron、loops、channels、主动通知 | Cron tools、scheduled event、commands/settings | `cloud-background-channels.md`、`builtin-tools-reference.md` | Deep | session/durable schedule、fixed/dynamic loop、Monitor、Push、Channel gate/queue/reconnect 已覆盖 |
| 30 | Remote Control 与 cloud session | CLI/SDK/API/status/daemon | `cloud-background-channels.md`、`tui-ide-remote-cloud.md` | Deep | 本地/远端 owner、重连、附件、create/attach/teleport 已覆盖；登录账户正向服务 Probe 保持 Boundary |
| 31 | CCR、BYOC、自托管 runner、cloud workflow | env/schema/API/tools | `cloud-background-channels.md` | Deep | bundle/runner/lease/watchdog/token/stage root/capacity/drain 与 Git proxy 边界已覆盖；实际服务调度为 Boundary |
| 32 | Storage v5 与本地状态目录 | 29 Claude namespaces | `storage-v5-reference.md` | Deep | 29/29 key、scope、write discipline、consumer、敏感度和缺失 consumer 已覆盖；本版自建 backend 不可达 |
| 33 | Install、update、doctor、migration | CLI/install layout/update gates/diagnostics | `install-update-doctor-lifecycle.md` | Deep | 保持真实二进制 hash、升级和配置 schema 回退边界 |
| 34 | `2.1.235` 19 条 release changes | release notes + matching source evidence | 完整说明书第 28 章及 LSP/cloud/TUI 专题 | Deep | 19 条均已回填专属生命周期；跨版本归因仍区分 2.1.234 与 2.1.235 |
| 35 | 本地风控与企业治理 | risk surface、sandbox/policy/credentials/trust | 风控 README、工具/settings/遥测专题 | Deep | 服务端账号关联、abuse score、封禁模型保持 Boundary |
| 36 | 服务端、模型内部与构建前源码 | bundle 不携带 | 多篇边界说明 | Boundary | 不得用 header、event、字符串或当前官网替代实现证据 |

## 数量覆盖不能冒充机制覆盖

以下数字按人工 Markdown 统计，排除 generated comparison、public excerpts 与本矩阵自身，包含 README 和 `ARTICLES.md`。它们只证明 identifier 在人类入口中出现，不证明 consumer、失败分支和用户影响已经讲深：

| 集合 | 总数 | 审计时在人类文档中出现 | 未出现 | 正确解释 |
| --- | ---: | ---: | ---: | --- |
| direct root settings | 156 | 156 | 0 | `settings-reference.md` 提供全量入口，但大量条目仍是 declaration/surface |
| built-in tools | 29 | 29 | 0 | `builtin-tools-reference.md` 已逐项覆盖，但深度仍按专属状态机分别判断 |
| slash commands | 103 | 103 | 0 | `slash-command-reference.md` 已逐命令给出 type/twin、owner、gate 和失败边界；仍不等于所有账号/host 都正向 Probe |
| SDK control subtype | 89 | 89 | 0 | 89 是混合集合；真实 request、notification、compatibility identifier 不能混称已 Probe |
| output protocol event | 44 | 44 | 0 | 已有事件/字段表，大量 host 消费仍是 Boundary |
| Claude storage namespace | 29 | 29 | 0 | `storage-v5-reference.md` 逐项区分真实 consumer 与 Boundary；名字仍不自动证明 backend active、retention 或事务 |
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

本轮已经把新增专题纳入 validator：强制存在正文和对应可编辑 `.dot + .svg`，并从权威 inventory 精确核对 29 个 built-in tool、156 个 direct setting、89 个 SDK subtype、44 个 protocol event、103 个 slash command、31 个 Hook event 和 29 个 Claude storage namespace。覆盖缺项、重复项、多余项或顺序漂移会直接失败；负向测试覆盖工具、setting、SDK request、slash、hook、storage 与新增专题/图缺失。

它仍不能把“集合完整”自动升级成“机制全面”。继续收口还需要：

1. 每个集合继续区分 `Product`、`Dependency`、`Embedded docs`、`Heuristic`；
2. 每个强运行结论必须有 consumer Static 或 Probe，schema/help-only 只能标 `surface/declaration`；
3. 当前仍为 `Documented` 的 Settings、CLI/SDK、Plugin/LSP 表面继续增加字段级 consumer 与真实 host/第三方 Probe；
4. 服务端 entitlement、feature 实时值、cloud orchestration、第三方 IDE/MCP 和跨平台设备行为保持 Boundary；
5. 新鲜远端检出后重新运行相同校验，避免本地未跟踪文件制造假完整。

## 后续版本回归顺序

1. 每个新版本先重生成 canonical inventory，精确比较 29 tools、156 settings、103 commands、31 hooks、29 storage namespaces、89 SDK subtype 和 44 protocol event。
2. 按状态机比较 Agent Loop/context/session/tool/recovery/model/settings/feature/UI/cloud/native，而不是只看 key 数量或 minified symbol。
3. 将新增/删除 surface 回填专属文章、完整说明书、`ARTICLES.md`、README、机制证据和可编辑图。
4. 对 changed branch 扩充 exact-binary Probe；未触发的 remote/third-party/cross-platform 行为保持 Boundary。
5. 运行全量、负向、隐私、SVG、重建、Probe 与远端 fresh-checkout 验证后再推送。

在矩阵所有非 Boundary 行达到 `Deep`，并且证据审计没有版本倒灌或高强度误述之前，`2.1.235` 不宣称“全面”。
