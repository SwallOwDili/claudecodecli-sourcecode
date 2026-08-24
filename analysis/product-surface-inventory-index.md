# Claude Code CLI 2.1.235 机器证据索引

> 这是一份确定性审计页，不是技术文章。先读 [状态边界与本地执行系统解剖](product-surface-evidence-map.md)，需要复核覆盖和跨版本差异时再回到这里。

## 当前语义收口状态

[`summary.json`](source-inventory/summary.json) 注册 71 类 inventory；canonical source SHA-256 为 `22642ddc2aa33ff16a5ee3c5a5bffb14f03c270f0047b4e5e40ba6a22efbeb8e`。[`mechanism-evidence.jsonl`](mechanism-evidence.jsonl) 当前有 339 条 claim，覆盖 48 个 topic：243 Static、48 Probe、33 Public、15 Boundary。

仍需人工收口的客户端证据包括：[环境变量参考](environment-variable-reference.md)中的 562 个静态环境名称和 138 个动态环境表达式、[Feature 参考](feature-flag-reference.md)中的 186 个 Feature key、[Telemetry 场景索引](telemetry-event-catalog.md)中的 899 个 `tengu_other` caller-owner。[Error/Diagnostic owner 索引](error-diagnostic-owner-index.md)已对 558/10234 个 callsite 建立 exact owner（Product 308、Dependency 250），仍有 9676 个；此外还有遥测运行 gate/动态 payload/远端 delivery和未触发 transport/remote/paid-judge Probe。这些是 `Untraced/Inventory only`，不是服务端 Boundary。环境/Feature 本批分别新增 44/25 项结构化人工合同，生成器会按 lexical owner、调用点数量和 access mode 拒绝伪收口。

## 三轴怎样读

- **提取来源**回答记录怎样从 canonical bundle 得到。
- **所有权**区分 Product、Dependency、Mixed 与 Unresolved。
- **证明层级**只允许 Candidate、Declaration、Callsite、Structured surface 或 Evidence substrate；它们都不会自动升级为运行结论。

表中的运行面沿用 [主文末尾的 Derived 阅读索引](product-surface-evidence-map.md#把-cqeso-留作阅读索引)：`C` 控制、`Q` 请求与上下文、`E` 本地执行、`S` 持久状态、`O` 观测与诊断。它们是阅读路由，不是源码原生模块。

## 全部 71 类机器清单

<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->
| 机器清单 | 提取来源 | 所有权 | 证明层级 | 运行面 | 当前仍缺什么 |
| --- | --- | --- | --- | --- | --- |
| [`anthropic-beta-identifiers.txt`](source-inventory/anthropic-beta-identifiers.txt) | `Broad static scan` | `Mixed` | `Candidate` | `C/Q` | 用于发现入口；必须二次绑定 consumer；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`api-path-templates.jsonl`](source-inventory/api-path-templates.jsonl) | `Template-prefix projection` | `Mixed` | `Candidate` | `Q/E/S` | 不是 fetch/request AST callsite；模板可来自文档或依赖。 |
| [`api-paths.txt`](source-inventory/api-paths.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `Q/E/S` | 无逐项 consumer 权威；产品、依赖、文档可混合；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`builtin-tool-identifiers.txt`](source-inventory/builtin-tool-identifiers.txt) | `Manual allowlist intersection` | `Mixed` | `Candidate` | `Q/E` | 不代表完整工具装配、启用结果或发给模型的 schema。 |
| [`claude-storage-namespaces.txt`](source-inventory/claude-storage-namespaces.txt) | `Structured extraction` | `Product` | `Structured surface` | `S` | 集合完整；行为仍需 consumer/状态机；adapter、外部进程和平台依赖是否真实可用需要运行或环境证据。 |
| [`datadog-forwarded-events.txt`](source-inventory/datadog-forwarded-events.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`datadog-redacted-fields.txt`](source-inventory/datadog-redacted-fields.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`datadog-tag-fields.txt`](source-inventory/datadog-tag-fields.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`diagnostic-message-callsites.jsonl`](source-inventory/diagnostic-message-callsites.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `S/O` | 用于防漏和定位；不单独证明产品归属；文本出现不能单独证明分支可达、错误分类正确或恢复成功。 |
| [`diagnostic-message-literals.txt`](source-inventory/diagnostic-message-literals.txt) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `S/O` | 用于防漏和定位；不单独证明产品归属；文本出现不能单独证明分支可达、错误分类正确或恢复成功。 |
| [`diagnostic-message-templates.jsonl`](source-inventory/diagnostic-message-templates.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `S/O` | 用于防漏和定位；不单独证明产品归属；文本出现不能单独证明分支可达、错误分类正确或恢复成功。 |
| [`direct-process-environment-accesses.txt`](source-inventory/direct-process-environment-accesses.txt) | `process.env text projection` | `Mixed` | `Candidate` | `C` | 逐调用点、fallback 和动态下标以 environment-access-callsites.jsonl 为准。 |
| [`dynamic-process-environment-callsites.jsonl`](source-inventory/dynamic-process-environment-callsites.jsonl) | `Whole-bundle AST` | `Mixed` | `Callsite` | `C/Q/E/S/O` | 扫描整个 bundle 的动态 process.env 下标；产品代码与依赖混合，必须继续追 lexical function、caller 和可达性。 |
| [`endpoint-hosts.txt`](source-inventory/endpoint-hosts.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `Q` | 无逐项 consumer 权威；产品、依赖、文档可混合；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`environment-access-callsites.jsonl`](source-inventory/environment-access-callsites.jsonl) | `Whole-bundle AST` | `Mixed` | `Callsite` | `C/Q/E/S/O` | 扫描整个 bundle 的 process.env/env-proxy 访问，包含 @grpc/grpc-js 等依赖；Callsite 为真不等于一方产品归属。 |
| [`environment-access-identifiers.txt`](source-inventory/environment-access-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `C` | 无逐项 consumer 权威；产品、依赖、文档可混合；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`environment-like-identifiers.txt`](source-inventory/environment-like-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `C` | 无逐项 consumer 权威；产品、依赖、文档可混合；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`environment-proxy-accesses.txt`](source-inventory/environment-proxy-accesses.txt) | `Env-proxy projection` | `Mixed` | `Candidate` | `C` | 集合行没有 consumer 位置；AST 权威文件是 environment-access-callsites.jsonl。 |
| [`environment-schema.jsonl`](source-inventory/environment-schema.jsonl) | `Environment-builder extraction` | `Mixed` | `Declaration` | `C` | builder 同时覆盖一方字段、provider/SDK 字段和依赖声明；typed declaration 不等于一方 ownership 或运行 consumer。 |
| [`error-message-callsites.jsonl`](source-inventory/error-message-callsites.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `S/O` | 用于防漏和定位；不单独证明产品归属；文本出现不能单独证明分支可达、错误分类正确或恢复成功。 |
| [`error-message-literals.txt`](source-inventory/error-message-literals.txt) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `S/O` | 用于防漏和定位；不单独证明产品归属；文本出现不能单独证明分支可达、错误分类正确或恢复成功。 |
| [`error-message-templates.jsonl`](source-inventory/error-message-templates.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `S/O` | 用于防漏和定位；不单独证明产品归属；文本出现不能单独证明分支可达、错误分类正确或恢复成功。 |
| [`feature-flag-callsites.jsonl`](source-inventory/feature-flag-callsites.jsonl) | `Targeted AST` | `Product` | `Callsite` | `C` | 逐行可定位真实调用点；不自动证明分支运行；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`feature-flags.txt`](source-inventory/feature-flags.txt) | `Structured extraction` | `Product` | `Structured surface` | `C` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`first-party-environment-fields.txt`](source-inventory/first-party-environment-fields.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`first-party-event-callsites.jsonl`](source-inventory/first-party-event-callsites.jsonl) | `Targeted AST` | `Product` | `Callsite` | `O` | 逐行可定位真实调用点；不自动证明分支运行；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`first-party-event-families.tsv`](source-inventory/first-party-event-families.tsv) | `Prefix bucket projection` | `Mixed` | `Candidate` | `O` | 未命中项进入 tengu_other；family 是分析投影，不是客户端字段。 |
| [`first-party-event-fields.tsv`](source-inventory/first-party-event-fields.tsv) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`first-party-event-schema-fields.txt`](source-inventory/first-party-event-schema-fields.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`first-party-event-templates.txt`](source-inventory/first-party-event-templates.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`first-party-events.txt`](source-inventory/first-party-events.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`growthbook-callsites.jsonl`](source-inventory/growthbook-callsites.jsonl) | `Targeted AST` | `Product` | `Callsite` | `C` | 逐行可定位真实调用点；不自动证明分支运行；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`growthbook-event-fields.txt`](source-inventory/growthbook-event-fields.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`growthbook-keys.txt`](source-inventory/growthbook-keys.txt) | `Structured extraction` | `Product` | `Structured surface` | `C` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`hook-events.txt`](source-inventory/hook-events.txt) | `Structured extraction` | `Product` | `Structured surface` | `E` | 集合完整；行为仍需 consumer/状态机；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`http-route-identifiers.txt`](source-inventory/http-route-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `Q/E/S` | 无逐项 consumer 权威；产品、依赖、文档可混合；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`known-tool-catalog.txt`](source-inventory/known-tool-catalog.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `Q/E` | 无逐项 consumer 权威；产品、依赖、文档可混合；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`model-aliases.jsonl`](source-inventory/model-aliases.jsonl) | `Structured extraction` | `Product` | `Structured surface` | `C/Q` | 集合完整；行为仍需 consumer/状态机；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`model-catalog-metadata.jsonl`](source-inventory/model-catalog-metadata.jsonl) | `Structured extraction` | `Product` | `Structured surface` | `C/Q` | 集合完整；行为仍需 consumer/状态机；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`model-catalog.jsonl`](source-inventory/model-catalog.jsonl) | `Structured extraction` | `Product` | `Structured surface` | `C/Q` | 集合完整；行为仍需 consumer/状态机；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`model-identifiers.txt`](source-inventory/model-identifiers.txt) | `Broad static scan` | `Mixed` | `Candidate` | `C/Q` | 用于发现入口；必须二次绑定 consumer；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`model-pricing-tiers.jsonl`](source-inventory/model-pricing-tiers.jsonl) | `Structured extraction` | `Product` | `Structured surface` | `C/Q/O` | 集合完整；行为仍需 consumer/状态机；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`named-component-identifiers.txt`](source-inventory/named-component-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `C/Q/E/S/O` | 无逐项 consumer 权威；产品、依赖、文档可混合；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`observability-environment-defaults.jsonl`](source-inventory/observability-environment-defaults.jsonl) | `Observability-filtered environment callsites` | `Mixed` | `Callsite` | `O` | 是真实 callsite 投影，但混合产品和依赖；fallback 存在不证明当前运行值或 exporter 已启用。 |
| [`observability-environment-schema.jsonl`](source-inventory/observability-environment-schema.jsonl) | `Observability regex projection` | `Mixed` | `Declaration` | `O` | 底层 declaration 可复核，但投影混合一方、provider 和依赖字段；不能统一标为 Product。 |
| [`observability-identifiers.txt`](source-inventory/observability-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `O` | 无逐项 consumer 权威；产品、依赖、文档可混合；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`observability-templates.jsonl`](source-inventory/observability-templates.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `O` | 用于防漏和定位；不单独证明产品归属；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`otel-environment-variables.txt`](source-inventory/otel-environment-variables.txt) | `Prefix-filtered environment union` | `Mixed` | `Candidate` | `C/O` | 从 broad environment union 按 OTEL 前缀筛选，混合客户端接线与 OpenTelemetry SDK 自身变量；须逐项绑定 consumer。 |
| [`otel-event-callsites.jsonl`](source-inventory/otel-event-callsites.jsonl) | `Targeted AST` | `Product` | `Callsite` | `O` | 逐行可定位真实调用点；不自动证明分支运行；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`otel-metrics.tsv`](source-inventory/otel-metrics.tsv) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`otel-spans.txt`](source-inventory/otel-spans.txt) | `Structured extraction` | `Product` | `Structured surface` | `O` | 集合完整；行为仍需 consumer/状态机；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`output-protocol-event-identifiers.txt`](source-inventory/output-protocol-event-identifiers.txt) | `Structured extraction` | `Product` | `Structured surface` | `Q/E/S/O` | 集合完整；行为仍需 consumer/状态机；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`root-settings-keys.txt`](source-inventory/root-settings-keys.txt) | `Structured extraction` | `Product` | `Structured surface` | `C` | 集合完整；行为仍需 consumer/状态机；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`root-settings-schema.jsonl`](source-inventory/root-settings-schema.jsonl) | `Structured extraction` | `Product` | `Structured surface` | `C` | 集合完整；行为仍需 consumer/状态机；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`runtime-requires.txt`](source-inventory/runtime-requires.txt) | `Require literal scan` | `Mixed` | `Callsite` | `E/S/O` | 不能把整份清单统一写成依赖，也不能仅凭 require 证明当前平台加载成功。 |
| [`schema-descriptions.txt`](source-inventory/schema-descriptions.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `C/E/S` | 无逐项 consumer 权威；产品、依赖、文档可混合；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`schema-property-identifiers.txt`](source-inventory/schema-property-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `C` | 无逐项 consumer 权威；产品、依赖、文档可混合；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`sdk-control-subtypes.txt`](source-inventory/sdk-control-subtypes.txt) | `Structured extraction` | `Product` | `Structured surface` | `Q/E/S` | 集合完整；行为仍需 consumer/状态机；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`slash-command-identifiers.txt`](source-inventory/slash-command-identifiers.txt) | `Structured extraction` | `Product` | `Structured surface` | `C/E/S` | 集合完整；行为仍需 consumer/状态机；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`static-enum-groups.tsv`](source-inventory/static-enum-groups.tsv) | `Heuristic scan` | `Mixed` | `Candidate` | `C/E/S` | 无逐项 consumer 权威；产品、依赖、文档可混合；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
| [`static-string-literals.jsonl`](source-inventory/static-string-literals.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `C/Q/E/S/O` | 用于防漏和定位；不单独证明产品归属；词法完整不等于产品归属或运行可达，必须回到 AST consumer 和状态机。 |
| [`storage-namespaces.txt`](source-inventory/storage-namespaces.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `S/O` | 无逐项 consumer 权威；产品、依赖、文档可混合；adapter、外部进程和平台依赖是否真实可用需要运行或环境证据。 |
| [`telemetry-endpoints.txt`](source-inventory/telemetry-endpoints.txt) | `URL keyword projection` | `Mixed` | `Candidate` | `Q/O` | 包含依赖文档地址和示例 URL；真实出口须绑定 transport consumer。 |
| [`template-literals.jsonl`](source-inventory/template-literals.jsonl) | `Lexical/AST substrate` | `Unresolved` | `Evidence substrate` | `C/Q/E/S/O` | 用于防漏和定位；不单独证明产品归属；词法完整不等于产品归属或运行可达，必须回到 AST consumer 和状态机。 |
| [`tengu-identifiers.txt`](source-inventory/tengu-identifiers.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `C/Q/E/S/O` | 无逐项 consumer 权威；产品、依赖、文档可混合；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`third-party-otel-event-fields.tsv`](source-inventory/third-party-otel-event-fields.tsv) | `Dependency schema` | `Dependency` | `Declaration` | `O` | 只在一方 consumer 可达时进入产品结论；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`third-party-otel-events.txt`](source-inventory/third-party-otel-events.txt) | `Dependency schema` | `Dependency` | `Declaration` | `O` | 只在一方 consumer 可达时进入产品结论；服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。 |
| [`tool-registrations.jsonl`](source-inventory/tool-registrations.jsonl) | `Structured extraction` | `Product` | `Structured surface` | `Q/E` | 集合完整；行为仍需 consumer/状态机；第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。 |
| [`url-templates.jsonl`](source-inventory/url-templates.jsonl) | `Heuristic scan` | `Mixed` | `Candidate` | `Q/E/O` | 无逐项 consumer 权威；产品、依赖、文档可混合；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`urls.txt`](source-inventory/urls.txt) | `Heuristic scan` | `Mixed` | `Candidate` | `Q/E/O` | 无逐项 consumer 权威；产品、依赖、文档可混合；远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。 |
| [`user-config-directories.txt`](source-inventory/user-config-directories.txt) | `Broad static scan` | `Mixed` | `Candidate` | `C` | 用于发现入口；必须二次绑定 consumer；运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。 |
<!-- SOURCE_INVENTORY_COVERAGE_END -->

机器覆盖只证明候选证据没有从生成物中消失。最终行为结论仍以 [全面性审计](completeness-audit.md)、逐项 reference 和对应机制文章中的 consumer/state-machine 追踪为准。
