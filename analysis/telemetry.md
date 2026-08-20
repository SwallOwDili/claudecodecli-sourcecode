# Claude Code CLI 2.1.235 遥测、日志与诊断能力

本文只记录发布 bundle 中可以静态证实的客户端行为。它覆盖一方事件、OpenTelemetry、Datadog、GrowthBook、错误上报、Perfetto、启动/查询 profiling、本地 debug/diagnostic 日志，以及对应的门控、字段、队列、重试和隐私控制。

完整事件名和字段不在本文手工复制。机器清单是最终证据：

- [一方事件 1,436 项](source-inventory/first-party-events.txt)
- [一方动态事件模板 3 项](source-inventory/first-party-event-templates.txt)
- [一方事件到字段映射 1,411 行](source-inventory/first-party-event-fields.tsv)
- [一方事件 schema 34 字段](source-inventory/first-party-event-schema-fields.txt)
- [一方环境 schema 36 字段](source-inventory/first-party-environment-fields.txt)
- [OTEL structured events 26 项](source-inventory/third-party-otel-events.txt)
- [OTEL event 字段映射 26 行](source-inventory/third-party-otel-event-fields.tsv)
- [OTEL metrics 8 项](source-inventory/otel-metrics.tsv)
- [OTEL spans 10 项](source-inventory/otel-spans.txt)
- [OTEL 环境变量 77 项](source-inventory/otel-environment-variables.txt)
- [Datadog allowlist 181 项](source-inventory/datadog-forwarded-events.txt)
- [Datadog tag 字段 34 项](source-inventory/datadog-tag-fields.txt)
- [Datadog 删除字段 26 项](source-inventory/datadog-redacted-fields.txt)
- [GrowthBook 事件字段 15 项](source-inventory/growthbook-event-fields.txt)

## 通道总览

| 通道 | 默认目的地/出口 | 主要门控 | 数据形态 | 静态证据 |
| --- | --- | --- | --- | --- |
| 一方事件 | `https://api.anthropic.com/api/event_logging/v2/batch` | 一方 provider、共享非必要流量/遥测门、killswitch、采样 | `ClaudeCodeInternalEvent`、`GrowthbookExperimentEvent` 批量 JSON | `reverse/javascript/cli.readable.js` 77436-78100 |
| Datadog 日志 | `https://http-intake.logs.us5.datadoghq.com/api/v2/logs` | 仅一方 provider、`tengu_log_datadog_events`、181 项 allowlist | 归一化 JSON log | 同文件 90690-90900 |
| 第三方 OTEL metrics | console、OTLP、Prometheus | `CLAUDE_CODE_ENABLE_TELEMETRY` 和 exporter 配置 | 8 个 metric instruments | 同文件 361450-361710 |
| 第三方 OTEL logs | console、OTLP | 同上 | 26 个 structured events | 同文件 93720-94360、361450-361710 |
| 第三方 OTEL traces | console、OTLP | OTEL 总开关和 enhanced telemetry beta | 10 类 span | 同文件 93980-94360、361450-361710 |
| GrowthBook experiment | 复用一方批量 transport | GrowthBook/一方遥测门 | experiment/variation 和序列化 attributes | 同文件 77990-78060 |
| 错误上报 | bundle 中的错误上报客户端 | 一方 provider、登录状态、版本、feature、组织 policy、`DISABLE_ERROR_REPORTING` | 异常、上下文、经过 scrub 的属性 | 同文件 73690-73880 |
| Perfetto | 本地 trace 文件 | `CLAUDE_CODE_PERFETTO_TRACE` | interaction、LLM、tool 等 trace slice | 同文件 93980-94290 |
| Profiling/diagnostics | 本地文件或 stderr/debug log | 对应 debug/profile 环境变量 | 启动 checkpoint、查询阶段、内存/CPU、frame timing、JSONL | 同文件 17097、267260-267390 |

## 共享隐私和流量门

`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`、`DISABLE_TELEMETRY`、`DO_NOT_TRACK` 在 bundle 中先被归一化为共享流量级别。前者进入 `essential-traffic`，后两者进入 `no-telemetry`。一方事件通过该门禁用，GrowthBook 和多个非必要网络能力也复用相同判断。

`DISABLE_ERROR_REPORTING` 是独立的错误上报开关。错误上报还要求：

- provider 为 first-party；
- 当前认证/登录状态满足条件；
- 版本不低于内置最低版本；
- `tengu_orford_ness` feature gate 开启；
- 组织 policy 的 `allow_error_reporting` 允许；
- HIPAA/ZDR 等 compliance taint 不阻断；
- API key helper、环境 bearer token、无 scope OAuth 等路径通过单独判断。

第三方 OTEL 是用户/管理员显式配置的出口，以 `CLAUDE_CODE_ENABLE_TELEMETRY` 为总开关。它不等同于 Anthropic 一方事件通道。

## 一方事件流水线

### 调用和排队

业务代码通过 `H(event, metadata)` 和 `Fv(event, metadata)` 记录同步/异步事件：

1. analytics sink 尚未安装时进入全局 FIFO；上限 1,000，满时删除最旧项并增加 dropped count。
2. sink 安装后用 microtask 排空全局队列。
3. 一方 logger provider 尚未初始化时进入第二层 `preInitQueue`；上限 1,024，超过上限的新事件不再加入。
4. provider 初始化完成后依序重新提交 pre-init 事件。
5. 运行中批量配置变化时，旧 provider 先 force-flush，再重建 provider；失败则恢复旧 provider/logger。

静态证据见 `reverse/javascript/cli.readable.js` 5310-5352、77970-78100。

### 采样

采样配置 key 为 `tengu_event_sampling_config`，按事件名查 `sample_rate`：

- 缺少配置、类型不对、超出 `[0,1]` 或等于 1：不额外采样，事件正常发送；
- `sample_rate <= 0`：丢弃；
- `0 < sample_rate < 1`：使用 `Math.random()` 判定；
- 被采中的事件会在 metadata 写入实际 `sample_rate`；
- 同一结果同时用于一方 transport 和 Datadog 分支。

### 批量、队列和默认值

远程配置 key 为 `tengu_1p_event_batch_config`。2.1.235 的内置默认值：

| 参数 | 默认值 |
| --- | ---: |
| provider flush interval | 10,000 ms |
| exporter max batch | 200 events |
| provider max queue | 8,192 events |
| HTTP request timeout | 10,000 ms |
| batch 间延迟 | 100 ms |
| 基础 backoff | 500 ms |
| 最大 backoff | 30,000 ms |
| 最大 attempts | 8 |

endpoint 默认拼接为 `https://api.anthropic.com/api/event_logging/v2/batch`；staging base URL 会切到 staging，同样允许远程 batch config 覆盖 `baseUrl`、`path`、`skipAuth`、`maxAttempts`、batch 和 queue 参数。

### 失败持久化和重试

发送失败的剩余 batch 会落盘，文件命名形态为 `1p_failed_events.<session>.<run>.json`，位于 telemetry storage。启用 storage v5 时改用 `namespace=log`、`channel=telemetry`、带 `runId` 的 stream。

启动时会扫描同一 session 的前次 run：

- 旧 JSON batch 在后台重试；
- v5 会枚举历史 telemetry stream；
- legacy flat batch 可以迁移进 v5 stream，并用稳定 record ID 去重；
- 空 batch 删除；
- 达到最大 attempts 后删除遗留 batch；
- 部分发送成功时，只把未发送事件重新写回。

backoff 为二次增长：`base * attempts^2`，并限制在 500 ms 至 30 s。当前 batch 的文件/stream 修改通过 promise lock 串行化，避免同进程并发覆盖。

认证请求收到 HTTP 401 时，代码会用基础 headers、不带认证头重试一次。基础 headers 包含 `Content-Type`、`User-Agent` 和 `x-service-name: claude-code`。

### 一方 envelope 和可能字段

一方事件 schema 明确包含：

- event：`event_name`、`event_id`、client/server timestamp；
- session/model：`session_id`、`parent_session_id`、`agent_id`、`agent_type`、`model`、`betas`、entrypoint、client type；
- identity/auth：`device_id`、`email`、account UUID、organization UUID、client-reported auth；
- environment：platform、raw platform、arch、runtime、terminal、shell、package managers、CI、GitHub Actions、WSL、Linux distro/kernel、remote/container/session IDs、deployment environment、build/version；
- process：uptime、RSS、heap、external/arrayBuffers、CPU usage/percent/window 等序列化后放入 `process`；
- extensions：skill、plugin、marketplace、MCP server/tool、team、head SHA；
- event-specific metadata：清理保留字段后编码进 `additional_metadata`。

这表示 schema 具备承载这些字段的能力，不表示每个事件都会填满所有字段。每个静态 callsite 的显式字段见 `first-party-event-fields.tsv`。其中 284 行以 `<no-static-fields>` 标记，表示解析器发现了事件和对象 callsite，但顶层只由 spread、变量或当前静态解析器不能展开的结构组成；这些 payload 和动态模板仍需回到 canonical bundle 追踪。静态字符串原值若以空格或 tab 结尾，生成器会写成 `\x20`/`\t`，避免证据被 Git 尾随空白规则改变。

## Datadog 分支

Datadog 分支只在 `Gn() === "firstParty"` 时运行，并且同时要求：

- `tengu_log_datadog_events` feature key 开启；
- 事件名存在 181 项 allowlist；
- Datadog 初始化成功且没有 killswitch。

默认 batch 100，flush 15 s，HTTP timeout 5 s。请求使用内置 public client token 写入 US5 logs intake。

发送前执行的归一化和数据缩减：

- 删除 26 个字段，完整名单见 `datadog-redacted-fields.txt`；
- 34 个稳定字段被转换为 tag，完整名单见 `datadog-tag-fields.txt`；
- `mcp__*` 和动态 MCP tool 折叠成 `mcp`；
- `skill__*` 折叠成 `skill`，具体 skill feature 折叠成通用分类；
- 非 Claude model 不转发；Claude model 归一化到内置 catalog，否则记为 `other`；
- build version 去除临时 build/sha 尾缀；
- HTTP status 同时写入精确值和范围；
- peer-rate-bound 事件按 event/server 每分钟最多转发 10 条，并在下一条中报告中间 dropped 数；
- rate map 最多保留 200 个 key，超过时淘汰最旧 key。

Datadog 的 26 个删除字段不能被解释为整个 Claude Code 遥测系统的统一删除表，它只适用于这个 Datadog forwarding 分支。

## 第三方 OpenTelemetry

### Exporter 和协议

metrics exporter 支持 `console`、`otlp`、`prometheus`；logs 支持 `console`、`otlp`；traces 支持 `console`、`otlp`。OTLP 三类 signal 都支持：

- `grpc`
- `http/json`
- `http/protobuf`

global 与 signal-specific 的 endpoint、headers、protocol、certificate、client certificate/key、compression、timeout 均能从环境读取。完整 77 项见 `otel-environment-variables.txt`。

如果用户没有显式设置 `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE`，Claude Code 在 bootstrap 阶段把它设为 `delta`。显式配置不会被覆盖。

默认 force-flush timeout 为 5,000 ms，shutdown timeout 为 2,000 ms，可分别由 `CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS`、`CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS` 调整。

traces 除总开关/exporter 外还需要 enhanced telemetry beta。内部 beta tracing 还存在 `BETA_TRACING_ENDPOINT` 委托出口，分别拼接 `/v1/traces` 和 `/v1/logs`。

### Metrics

2.1.235 静态恢复出 8 个 metric：active time、code-edit permission decision、commit count、cost、lines of code、pull request count、session count、token usage。名称、unit 和 description 的原值见 `otel-metrics.tsv`。

resource/attributes 可包含 service name/version、OS/arch、WSL、`OTEL_RESOURCE_ATTRIBUTES`，以及根据隐私配置选择的 user/session/account/entrypoint/version 字段。`OTEL_METRICS_INCLUDE_*` 有内置默认 map，不能把所有可选 attribute 当作默认发送字段。

### Structured logs/events

恢复出 26 个事件：API request/error/refusal/retries、assistant response、user prompt、tool/tool result/tool decision、system prompt、auth、compaction、MCP connection、hook lifecycle、plugin/skill、subagent、retention、feedback 等。逐事件字段见 `third-party-otel-event-fields.tsv`。

内容字段默认收缩：

- user prompt 默认写 `<REDACTED>`；
- `OTEL_LOG_USER_PROMPTS` 才记录 user prompt；
- `OTEL_LOG_ASSISTANT_RESPONSES` 控制 assistant content，并兼容 user-prompt 开关；
- `OTEL_LOG_TOOL_CONTENT` 控制 tool content；
- `OTEL_LOG_TOOL_DETAILS` 扩大 tool 细节；
- `OTEL_LOG_RAW_API_BODIES` 控制原始 API body。

内容长度取 `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH`、通用 OTEL attribute limit、log-record attribute limit、span attribute limit 中的最小值。过长内容会被截断，不会因为单独提高其中一个限制就绕过其他限制。

### Traces 和 Perfetto 关联

恢复出 10 个 span name：bash subprocess、compaction、hook、interaction、LLM request、MCP RPC、subagent spawn、tool、tool blocked-on-user、tool execution。

interaction、LLM 和 tool span 同时可以关联 Perfetto span ID。LLM 完成时会记录 TTFT、TTLT、prompt/output/cache token、success/error、request setup、attempt start、request ID 和 client request ID；permission unblock 会记录 decision/source。

## GrowthBook experiment events

`GrowthbookExperimentEvent` 复用一方 logger/exporter，不是单独 HTTP 客户端。静态字段包括 event/timestamp、experiment/variation、environment、device/session、account/org auth、serialized user attributes、experiment metadata，以及兼容字段 `variation_key`、`anonymous_id`、`client_reported_auth`、`event_metadata_vars`。

一方 logger 尚未初始化且 batch config 也未知时，GrowthBook 调用返回可接受状态；config 已知但 logger 不可用时返回失败状态，让上层决定是否重试/降级。

## 错误上报、debug 和本地诊断

除 analytics/OTEL 外，bundle 还包含以下可观察性面：

- error reporting：受 `DISABLE_ERROR_REPORTING`、provider、auth、组织 policy、compliance taint、版本和 feature key 多重门控；
- secret scrubber：内置 URL userinfo、JWT、Anthropic/OpenAI/GitHub/GitLab/AWS/GCP/Azure 等 credential-shaped pattern，用于日志/错误内容清理；
- debug log：`CLAUDE_DEBUG`、`DEBUG`、`CLAUDE_CODE_DEBUG_LOG_LEVEL`、`CLAUDE_CODE_DEBUG_LOGS_DIR`；
- diagnostics file：`CLAUDE_CODE_DIAGNOSTICS_FILE`；
- session/SDK/transcript recording：`CLAUDE_CODE_SESSION_LOG`、`CLAUDE_CODE_JSONL_TRANSCRIPT`、`CLAUDE_CODE_TEE_SDK_STDOUT`、terminal/PTY recording；
- frame/repaint timing：frame timing log、sample interval、debug repaints；
- OTEL diagnostics：`CLAUDE_CODE_OTEL_DIAG_STDERR`；
- startup profiling：`CLAUDE_CODE_PROFILE_STARTUP`；
- query profiling：`CLAUDE_CODE_PROFILE_QUERY=1`，记录 context loading、autocompact、query setup、tool schemas、normalization、client creation、network TTFB、tool execution，并关联内存快照；
- Perfetto：`CLAUDE_CODE_PERFETTO_TRACE` 和 write interval，输出本地 trace；
- heap/process telemetry：RSS、heap、external、array buffers、CPU、uptime 等。

这些本地文件类功能是否产生网络流量取决于具体后续 exporter/上传路径。仅看到 `DEBUG`、profile 或 diagnostics 标识，不能推断内容会自动上传。

## 审计和版本比较规则

后续版本必须重新运行：

```bash
python3 skill/claude-code-version-diff/scripts/extract_source_inventory.py .
python3 skill/claude-code-version-diff/scripts/validate_snapshot.py .
```

跨版本比较器会遍历 `analysis/source-inventory/summary.json` 中登记的每个文件，输出 count delta、added 和 removed。任何新增 exporter、endpoint、event、field、redaction、metric、span、环境变量、feature gate 或 schema 都应先出现在机器清单，再更新本文的架构解释。

静态清单的边界：直接字面量可穷举；变量 payload、computed key、spread、运行时远程配置、服务端处理规则和 bundle 中不存在的服务端风控无法由静态清单穷举。此边界不影响已经恢复的 canonical bytes、逐事件显式字段和客户端分支行为。
