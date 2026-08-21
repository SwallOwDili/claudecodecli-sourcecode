# Claude Code CLI 2.1.235 全量可提取能力面

本文是发布 bundle 的能力地图。70 类机器清单负责穷举稳定字面量、全部目标调用点、动态表达式和结构化 schema/catalog，本文负责解释它们属于哪一层系统、哪些结论可以直接成立、哪些只能作为线索。

本文仍然是“查证据用的地图”，不是第一次阅读入口。先看 [技术机制总图](technical-mechanism-atlas.md)，模型与工具持续执行看 [Agent Loop 专题](agent-loop.md)，上下文/cache/compact 看 [上下文治理专题](context-governance-and-caching.md)，session/checkpoint/memory 看 [持久化专题](sessions-checkpoints-memory.md)，动作控制看 [工具、权限与 Hooks](tools-permissions-hooks.md)，动态扩展看 [MCP、Agents 与后台协作](mcp-agents-background.md)，再回到下面的 70 类索引定位原始证据。字段“存在”不等于分支可达，当前官网“有此功能”也不等于 `2.1.235` 已实现；逐项边界见 [公开主张验证矩阵](public-claims-validation.md)。

## 证据等级

| 等级 | 定义 | 可以如何表述 |
| --- | --- | --- |
| Observed | canonical packed bytes、CLI help、schema、明确分支、具体错误、endpoint、N-API contract 或运行探针直接证明 | “存在/支持/拒绝/发送/持久化” |
| Derived | 多个 observed 片段组成的调用链或数据流 | 必须给出组成证据和边界 |
| Compatible | `reconstructed/` 独立实现达到相同 contract/行为 | 只能称兼容重建，不能称原始源码 |
| Heuristic | regex/字符串集合，可能混入依赖或文档内容 | 只能称候选/索引，不能冒充产品 schema |

`extracted/cli.js` 是 canonical JavaScript packed bytes；`reverse/javascript/cli.readable.js` 是可读分析视图；`reverse/native/` 是原生静态分析；`reconstructed/` 是兼容源码。没有 source map/debug info 时，原始 TypeScript 文件树、注释、bundle 前边界和被 tree shaking 删除的代码不可精确恢复。

## 全量机器清单

生成器：`skill/claude-code-version-diff/scripts/extract_source_inventory.py`。摘要和逐文件哈希见 [source-inventory/summary.json](source-inventory/summary.json)。

### 环境、配置和 feature

| 清单 | 数量 | 说明 |
| --- | ---: | --- |
| [environment-access-identifiers](source-inventory/environment-access-identifiers.txt) | 1,300 | direct、environment proxy 和广义标识的并集 |
| [environment-access-callsites](source-inventory/environment-access-callsites.jsonl) | 2,548 | AST 识别的实际访问点、accessor、fallback 和位置 |
| [direct-process-environment-accesses](source-inventory/direct-process-environment-accesses.txt) | 453 | 直接 `process.env` 静态访问 |
| [dynamic-process-environment-callsites](source-inventory/dynamic-process-environment-callsites.jsonl) | 143 | 动态 `process.env[expression]`，保留表达式 |
| [environment-proxy-accesses](source-inventory/environment-proxy-accesses.txt) | 589 | bundle 环境代理对象静态属性访问 |
| [environment-like-identifiers](source-inventory/environment-like-identifiers.txt) | 1,048 | 广义环境形态 token，含依赖项 |
| [environment-schema](source-inventory/environment-schema.jsonl) | 842 | typed env builder、类型、options 和导出映射 |
| [otel-environment-variables](source-inventory/otel-environment-variables.txt) | 77 | OTEL 和相关遥测变量 |
| [observability-environment-schema](source-inventory/observability-environment-schema.jsonl) | 71 | typed env schema 的观测子集 |
| [observability-environment-defaults](source-inventory/observability-environment-defaults.jsonl) | 23 | 观测变量的 `??`/`||` fallback 表达式 |
| [feature-flags](source-inventory/feature-flags.txt) | 361 | `et()` 静态 feature key |
| [feature-flag-callsites](source-inventory/feature-flag-callsites.jsonl) | 498 | 全部 `et()` 调用及动态/作用域解析状态 |
| [growthbook-keys](source-inventory/growthbook-keys.txt) | 6 | `CB()` 静态 GrowthBook key |
| [growthbook-callsites](source-inventory/growthbook-callsites.jsonl) | 12 | 全部 `CB()` 调用及动态表达式 |
| [root-settings-keys](source-inventory/root-settings-keys.txt) | 156 | Claude Code 根 settings schema 键 |
| [root-settings-schema](source-inventory/root-settings-schema.jsonl) | 160 | 156 direct + 4 spread，含 RHS、builder、description、enum/default/catch |
| [schema-property-identifiers](source-inventory/schema-property-identifiers.txt) | 1,165 | 全 bundle schema property 候选，含依赖 schema |
| [schema-descriptions](source-inventory/schema-descriptions.txt) | 1,150 | `.describe()` 静态说明文本 |
| [static-enum-groups](source-inventory/static-enum-groups.tsv) | 201 | 静态 enum value group |
| [user-config-directories](source-inventory/user-config-directories.txt) | 13 | Claude 用户配置目录名集合 |

### 遥测、协议和生命周期

| 清单 | 数量 | 说明 |
| --- | ---: | --- |
| [tengu-identifiers](source-inventory/tengu-identifiers.txt) | 1,939 | 所有静态 `tengu_*` 标识 |
| [observability-identifiers](source-inventory/observability-identifiers.txt) | 149 | telemetry/log/debug/profile/recording 相关稳定标识 |
| [observability-templates](source-inventory/observability-templates.jsonl) | 166 | 观测相关 template 及插值表达式 |
| [telemetry-endpoints](source-inventory/telemetry-endpoints.txt) | 5 | 观测形态 endpoint 候选，含依赖示例，需按 callsite 定性 |
| [first-party-events](source-inventory/first-party-events.txt) | 1,441 | 一方静态事件名 |
| [first-party-event-templates](source-inventory/first-party-event-templates.txt) | 3 | 归一化动态模板 |
| [first-party-event-callsites](source-inventory/first-party-event-callsites.jsonl) | 2,194 | 全部 `H`/`Fv` 调用、参数、scope 和 payload/spread |
| [first-party-event-fields](source-inventory/first-party-event-fields.tsv) | 1,441 | 一方 event 到显式顶层字段映射 |
| [first-party-event-families](source-inventory/first-party-event-families.tsv) | 40 | 一方事件 family 计数 |
| [first-party-event-schema-fields](source-inventory/first-party-event-schema-fields.txt) | 34 | 一方 internal-event envelope 字段 |
| [first-party-environment-fields](source-inventory/first-party-environment-fields.txt) | 36 | 一方 environment envelope 字段 |
| [third-party-otel-events](source-inventory/third-party-otel-events.txt) | 26 | 第三方 OTEL structured event |
| [third-party-otel-event-fields](source-inventory/third-party-otel-event-fields.tsv) | 26 | OTEL event 到字段映射 |
| [otel-event-callsites](source-inventory/otel-event-callsites.jsonl) | 52 | 全部 `Nd()` 调用和动态事件表达式 |
| [otel-metrics](source-inventory/otel-metrics.tsv) | 8 | metric 名、unit、description |
| [otel-spans](source-inventory/otel-spans.txt) | 10 | trace span 名 |
| [datadog-forwarded-events](source-inventory/datadog-forwarded-events.txt) | 181 | Datadog allowlist |
| [datadog-tag-fields](source-inventory/datadog-tag-fields.txt) | 34 | Datadog tag 字段 |
| [datadog-redacted-fields](source-inventory/datadog-redacted-fields.txt) | 26 | Datadog 删除字段 |
| [growthbook-event-fields](source-inventory/growthbook-event-fields.txt) | 15 | experiment event envelope |
| [sdk-control-subtypes](source-inventory/sdk-control-subtypes.txt) | 89 | SDK control subtype |
| [output-protocol-event-identifiers](source-inventory/output-protocol-event-identifiers.txt) | 44 | user/agent/session/span protocol event |
| [hook-events](source-inventory/hook-events.txt) | 31 | hook lifecycle event |

### 工具、命令、模型和 API

| 清单 | 数量 | 说明 |
| --- | ---: | --- |
| [builtin-tool-identifiers](source-inventory/builtin-tool-identifiers.txt) | 29 | 静态一方 built-in tool 赋值 |
| [known-tool-catalog](source-inventory/known-tool-catalog.txt) | 188 | 工具归一化 catalog，含 internal/hosted/静态 MCP |
| [named-component-identifiers](source-inventory/named-component-identifiers.txt) | 182 | name+description 组件，含依赖组件 |
| [slash-command-identifiers](source-inventory/slash-command-identifiers.txt) | 103 | local/local-jsx/prompt slash command |
| [model-identifiers](source-inventory/model-identifiers.txt) | 37 | Claude model literal |
| [model-catalog](source-inventory/model-catalog.jsonl) | 17 | 完整 baked model 条目及 resolved pricing |
| [model-pricing-tiers](source-inventory/model-pricing-tiers.jsonl) | 6 | 输入/输出/cache/web-search 定价 tier |
| [model-aliases](source-inventory/model-aliases.jsonl) | 4 | family alias 及 provider-specific resolution |
| [model-catalog-metadata](source-inventory/model-catalog-metadata.jsonl) | 1 | schema version、latest family、best/default 元数据 |
| [anthropic-beta-identifiers](source-inventory/anthropic-beta-identifiers.txt) | 53 | date-suffixed beta/API version literal |
| [api-paths](source-inventory/api-paths.txt) | 99 | 静态 API path |
| [api-path-templates](source-inventory/api-path-templates.jsonl) | 119 | 动态 API/path template 和插值表达式 |
| [http-route-identifiers](source-inventory/http-route-identifiers.txt) | 19 | `METHOD /path` route 标识 |
| [runtime-requires](source-inventory/runtime-requires.txt) | 54 | 静态 runtime `require()` target |

### 存储、错误和网络

| 清单 | 数量 | 说明 |
| --- | ---: | --- |
| [claude-storage-namespaces](source-inventory/claude-storage-namespaces.txt) | 29 | Claude storage key factory namespace |
| [storage-namespaces](source-inventory/storage-namespaces.txt) | 41 | 全 bundle namespace，含依赖 |
| [error-message-literals](source-inventory/error-message-literals.txt) | 2,248 | Error/TypeError/RangeError 静态 literal |
| [error-message-callsites](source-inventory/error-message-callsites.jsonl) | 4,831 | 全部 Error/TypeError/RangeError 调用及参数/scope |
| [error-message-templates](source-inventory/error-message-templates.jsonl) | 1,526 | error 第一个参数的 template/expression 记录 |
| [diagnostic-message-literals](source-inventory/diagnostic-message-literals.txt) | 830 | `T()` debug/diagnostic literal |
| [diagnostic-message-callsites](source-inventory/diagnostic-message-callsites.jsonl) | 5,403 | 全部 `T()` 调用及参数/scope |
| [diagnostic-message-templates](source-inventory/diagnostic-message-templates.jsonl) | 4,438 | diagnostic 第一个参数的 template/expression 记录 |
| [static-string-literals](source-inventory/static-string-literals.jsonl) | 85,095 | 260,838 次 quoted-string occurrence 的全量归组 |
| [template-literals](source-inventory/template-literals.jsonl) | 25,187 | 30,114 次 template occurrence 的全量归组 |
| [urls](source-inventory/urls.txt) | 557 | 静态 URL |
| [url-templates](source-inventory/url-templates.jsonl) | 236 | URL template 和插值表达式 |
| [endpoint-hosts](source-inventory/endpoint-hosts.txt) | 179 | URL 归一化 host |

## Build、package 和 runtime

- arm64 signed Mach-O standalone，包含 Bun `__BUN.__bun` payload。
- 15 个 packed 文件逐字节恢复：主 bundle、5 个 JS loader、5 个 `.node`、Chart.js、Highlight.js、Mermaid、HTML payload。
- 主 bundle banner 为 `// @bun @bytecode @bun-cjs`。
- 完整 JSC bytecode 204,740,576 bytes 已确定性 gzip 保存，可重新解压校验。
- 主 bundle 同时包含产品代码、第三方依赖、内嵌文档/skills、schema 和静态资源，因此任何广义 regex 清单必须区分一方产品面与依赖面。
- runtime requires 覆盖 Node/Bun 内置模块和打包运行时依赖；它是加载面，不是 npm lockfile。
- 版本、build time、Git SHA、DD sourcemap group、签名 identity、Team ID 和 packed offsets 已结构化保存在 `analysis/version.json`。

## CLI、命令和输出协议

- 标准化顶层 option/command 见 `analysis/cli-surface.txt`，用于避免终端换行噪声。
- 交互、`--print`、text/JSON/stream-json 输入输出、partial message、structured output JSON Schema、budget、fallback model、resume/fork/session ID 均有 CLI/schema 证据。
- 103 个 slash command 是静态 command object 的保守集合；feature-gated、host 注入或动态 plugin command 可能不在集合中。
- 89 个 SDK control subtype 和 44 个 protocol event 覆盖 init、control request/response、hook、task progress、session/thread/outcome 等协议面。
- stream 输出能够携带 assistant text/thinking、tool use/result、hook、subagent、task progress、system init 和最终 result。
- `--handle-uri` 有额外参数注入防护；输入格式、schema validation、unknown subtype 和状态转换错误均可从错误清单追踪。

## Settings、环境、schema 和 enum

- 根 settings schema 恢复 156 个 direct 键和 4 个 spread；结构化清单保存每个 RHS、builder、description、enum、default/catch 和未解析 spread。
- 1,165 schema property、1,150 description、201 enum group 是更广集合，包含 SDK、MCP、OTEL、依赖库和内嵌文档 schema，不能全部称为用户 setting。
- settings 来源包含 policy/managed、flag、user、project、local、CLI 和 host/remote 注入；不同字段有 scope、trust、remote policy 和 merge precedence。
- project/local 不允许覆盖某些 user-only setting，例如本版本新增的 spellcheck。
- environment 既有 direct `process.env`，也有统一代理和 host-safe env union；2,548 个实际访问点、143 个动态 key 和 842 个 typed schema entry 可逐项比较。1,300 并集仍是调用线索，不代表 1,300 个公开支持变量。
- `safe mode`、`bare mode`、managed settings、strict policy helper keys、remote managed settings 都会改变加载面。

## 模型、provider、auth 和 beta

- 17 条内置 model catalog 同时记录 family、所有 provider ID、knowledge cutoff、context window、output limit、6 个 pricing tier、capabilities、default/各档 effort、fallback、image limit 和 advisor rank；4 个 alias 记录默认及 provider-specific resolution。
- provider 面包括 first-party、Bedrock、Vertex、Foundry、Anthropic AWS、Anthropic Google Cloud、Mantle、gateway/企业 base URL。
- auth 面包括 Claude subscription OAuth、API key、auth token、managed key、apiKeyHelper、AWS/GCP helper、WIF、mTLS、proxy auth 和 host credential file。
- credential helper 有 TTL、权限和输出校验；credentials file 要求严格文件权限。
- 53 个 date-suffixed beta identifier 同时包含 Anthropic beta、provider API version 和内嵌文档字符串，需回到 callsite 确认是否运行时使用。
- model literal 集合包含当前和前瞻 catalog 条目；出现字符串不等于该账号/组织当前可用。

## Session、transcript、memory、cache 和 storage

- session 支持 create/resume/continue/fork、显式 ID、alias/name、archive/delete、从 PR 或 remote/cloud 恢复。
- transcript 使用 JSONL/stream storage，支持 v5 storage namespace、session alias、history、checkpoint、attachment、tool result、task state。
- Claude 自有 29 个 storage namespace 覆盖 global config、project/local state、sessions、aliases、logs、telemetry、memory/cache 等；完整名单单独保存。
- auto-memory、CLAUDE.md、skills、plugins、project memory、remote memory、scratchpad、memory sync 都有独立门控。
- prompt cache 会区分稳定 system prefix 和 cwd/env/git/LSP 等机器动态内容；本版本修复 LSP reconnect 导致的 cache invalidation。
- auto-compact、manual compact、context limit、cold compact、1M context、compaction OTEL span/event 均可追踪。
- file checkpointing、local checkpoint commit、resume consistency、retention sweep 和 storage migration 都有事件/错误/schema 证据。

## Agent、subagent、team、worktree 和后台任务

- custom agent、default agent、subagent type、model/effort/tool/permission inheritance、agent SDK 和 hosted/cloud agent 均存在。
- Task/TaskCreate/TaskGet/TaskList/TaskOutput/TaskUpdate、SendMessage、Enter/ExitWorktree 是静态工具面的一部分。
- team name、parent session/agent、subagent span、teammate idle、task completed、跨会话 message 都有协议/hook/telemetry 字段。
- Git worktree 可隔离 agent，支持 tmux/iTerm2 pane、cleanup 和 policy/sandbox path 注册。
- background task、daemon、remote control worker、cloud workflow、ultrareview/autofix-pr 等拥有独立事件 family 和错误路径。
- 本版本对缺少 default agent、后台云事件流重复扫描、SendMessage 过大消息做了明确修复。

## 权限、沙箱、网络、凭据和本地风控

完整稳定 token 见 `analysis/risk-control-surface.txt`。核心控制链：

- permission mode：default、acceptEdits、auto、dontAsk、plan、bypassPermissions；
- tool rules：allow/ask/deny，CLI allowed/disallowed tools，managed-only rules；
- Auto classifier：rule/mode/hook/sandbox/safety/classifier decision source，无法评估走 blocking path；
- circuit breaker：dangerous removal、peer isolation 等类别可不受普通 bypass 影响；
- Bash/Git：命令拆分、只读识别、cwd、`.git` 植入、symlink、bare repo、hook 风险和 fail-closed；
- filesystem sandbox：allow/deny read/write、failIfUnavailable、unsandboxed command policy；
- runtime：macOS sandbox、Linux seccomp/bwrap、Windows isolation user；
- network：domain allow/deny、strict allowlist、managed-domain-only、Unix socket、local bind、Mach/XPC/Apple Events；
- credentials：env/file deny/mask、regex capture、JWT claim、sentinel/fake JWT、host-bound injection；
- trust：workspace trust、MCP headersHelper、plugin/skill/hook、CLAUDE.md external include；
- enterprise：allowed MCP、available models、forced org、process wrapper、policy helpers、managed permission sources。

这是客户端本地执行风控，不等于 Anthropic 服务端账号评分、关联风控、滥用检测或封禁策略。bundle 不包含的服务端规则不能逆向出来。

## MCP、hooks、plugins、skills 和 LSP

- MCP 支持 stdio、HTTP/SSE/SDK、registry、OAuth、headers、headersHelper、dynamic tool/resource/prompt、strict config 和 enterprise allowlist。
- 31 个 hook event 覆盖 tool、permission、prompt、session、subagent、compact、notification、config、worktree、team/task 生命周期。
- PreToolUse 可 allow/deny/ask/defer 或改写 input；改写后重新进入权限检查。
- hook transport 包括 command、HTTP 和 SDK callback；HTTP header 只允许显式 env allowlist。
- plugin 支持 directory、ZIP、URL、marketplace、install/update/enable/disable、eval、doctor；plugin/skill attribution 有 hash/redaction 路径。
- skills 可来自 bundled、user、project、plugin、account/remote sync；safe/bare/policy/compliance 会分别关闭部分来源。
- LSP 覆盖 server lifecycle、diagnostic、tool、推荐、plugin integration、disconnect/reconnect 和 prompt cache 交互。

## IDE、Chrome、Computer Use 和原生模块

- IDE 自动连接、VS Code panel/session restore、selection/context、diff、diagnostic、focus 和 extension install 均存在。
- Chrome bridge 有 connection/tool-call lifecycle、timeout/error、permission/onboarding 和默认 enable setting。
- Computer Use 原生输入模块支持 keyboard、mouse、scroll、position、accessibility permission；Swift 模块支持 display/window/region capture、installed app、ESC event tap、bundle ID。
- image processor 支持 clipboard、resize/fit、JPEG/PNG/GIF/TIFF/WebP；audio capture 支持 permission、record/play/status；URL handler 处理 macOS URL event。
- 5 个模块 contract、原始/重建双跑和架构边界见 `reconstructed/EVIDENCE.md`。

## Cloud、remote、CCR、BYOC、workflow 和 artifacts

- remote session、Remote Control、CCR、teleport、cloud session/self-hosted environment、daemon worker、session ingress token 都有 API/环境/schema 证据。
- BYOC runner 注入 provider、OTEL、remote/session token、stage root、memory dir、activity FD、watchdog 和 update-disable 环境。
- workflow、artifact、chart、Mermaid、syntax highlight、HTML payload、file upload/download、send file、design sync、projects tool 是独立能力面。
- cloud/self-hosted 能力受组织 policy、compliance taint、nonessential traffic、provider 和 entitlement/feature gate 控制。
- API path 清单混合本地 server route、Anthropic endpoint、managed agents 内嵌文档和依赖字符串；19 个 `METHOD /path` 标识更适合 route-level diff。

## 遥测、日志、实验和性能诊断

完整说明见 [telemetry.md](telemetry.md)。覆盖：

- 一方事件双层 pre-init queue、采样、batch、失败持久化、重试和 401 无认证重试；
- 第三方 OTEL metrics/logs/traces、protocol、content redaction、attribute limit；
- Datadog allowlist、字段删除、tag、归一化和 peer rate bound；
- GrowthBook experiment；
- error reporting、secret scrubber、Perfetto、startup/query profiling、debug/diagnostic/frame/session logs。

## Install、update 和 doctor

- 顶层 install/update/doctor、auto updater、native/package install method、protected update、channel、update feed、restart prompt 均有证据。
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 和 auto-update policy 可以禁止 update lookup/download。
- doctor 检查安装、配置、权限、MCP/plugin/LSP、shell、sandbox、network 和 telemetry 状态；具体诊断文本进入 830 项 diagnostic 清单。
- 本版本修复后台 update 完成后 `Update installed` 提示的保留。

## UI、输入、可访问性和 voice

- 终端 alternate screen、screen reader/accessibility、Vim mode、key binding、multi-line input、mention/slash highlight、selection、diff sidebar、brief transcript、timestamps、progress/status line 均有 settings/event/error 证据。
- spellcheck 支持 aspell/hunspell/ispell、语言、颜色、长驻进程、timeout 和失败后 session-disable。
- voice/audio 包含 permission、capture/playback、file transcription、组织 policy/compliance gate。
- image/artifact/chart/Mermaid/HTML preview 和 accessibility label/notification 是 bundled UI 能力。
- 本版本的列表缩进、方向键+Enter、Shift+Tab permission、Vim 状态、HTML entity、VS Code focus 修复均能在 release note 和 source literal/branch 互证。

## API、错误、重试、rate limit 和 compact

- API client 包括 first-party Messages、Bedrock、Vertex、Foundry、Anthropic AWS/Google Cloud、Mantle/gateway adapter。
- request 构建覆盖 model alias/provider ID、betas、thinking/effort、tools、streaming、prompt cache、structured output、compaction/context management。
- retry 覆盖 network、timeout、429/5xx、overloaded、auth refresh、fallback model/provider、watchdog 和 max retries；不同路径的 retry 语义需按 callsite 分开。
- rate limit、service tier、token/cost、cache read/write、web search、context/output limit 在 schema/model catalog/telemetry 中均有字段。
- 2,248 个 error literal 和 830 个 diagnostic literal 是去重静态集合；4,831/5,403 个完整调用点以及 1,526/4,438 个动态模板参数另存 JSONL，不再只留在 canonical source。
- compact 覆盖自动/手动、关闭时的 context-limit 提示、compaction event/span、summary/retention 和 resume consistency。

## 维护规则

每个新版本必须：

1. 从发布 executable 重新提取 canonical packed bytes，不复制旧版本清单。
2. 运行 source inventory extractor，并让 validator 在临时目录重生成后逐文件比较。
3. 对 `summary.json` 中每个清单做 count/added/removed diff。
4. 把新字面量先归类为 product、dependency、embedded docs 或 heuristic，再写能力结论。
5. 更新 telemetry、risk-control、native contract、README 和 release delta。
6. 更新机制总图、公开主张验证、Agent Loop、session/checkpoint/memory、tools/permissions/hooks、MCP/Agents/background 和 resilience 专题；每项实质变化解释旧/新状态、gate、threshold、failure 和 user impact。
7. 扫描所有可发布文件中的采集机 home、workspace 和 credential-shaped value；只允许 `extracted/`、`reverse/` 保留发布产物自身携带的上游构建路径证据。
8. 要求 `completionAudit` 的全部布尔项为 true 且 `knownStaticExtractionGaps` 为空；不可恢复边界只能是发布产物本身不存在的运行时/服务端/构建前信息。
