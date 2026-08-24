# Claude Code CLI 2.1.235 Error/Diagnostic 精确 owner 索引

**读者问题：** 4,831 个错误构造点和 5,403 个 diagnostic 调用点里，哪些真是 Claude Code 产品机制，哪些只是打包依赖，失败后又由谁捕获、重试、写 tool_result 或展示给用户？

**一句话模型：** constructor/diagnostic 只说明“这里生成了失败对象或调试记录”；本投影只有在完整 exact callsite identity 命中人工规则时才授予 owner，行号区间和相似文案永远不能替代 caller、consumer 与 source fingerprint。

## 结论：先把总数拆成三种证据状态

| 状态 | Error constructor | Diagnostic | 合计 | 能证明什么 |
| --- | ---: | ---: | ---: | --- |
| Product exact caller | 54 | 254 | 308 | exact lexical caller 属于已审阅的客户端机制；catch/retry/tool-result/user-surface 仍逐字段判定 |
| Dependency exact package/function | 250 | 0 | 250 | constructor 位于精确依赖 package/function；不自动继承产品恢复语义 |
| Unresolved | 4,527 | 5,149 | 9,676 | 只有 lexical/immediate consumer inventory，尚无经过复核的 owner |
| **全量** | **4,831** | **5,403** | **10,234** | 每条 canonical callsite 恰好出现一次 |

这不是把 `Unresolved` 换成漂亮标签。当前只收口高置信第一批；剩余记录继续作为可量化的 semantic debt。特别是 diagnostic 的 `T()` 名称在压缩 bundle 中可能与依赖局部符号碰撞，未审阅 scope 不按“看起来像日志”归 Product。

## 四个 Product 后续 owner 字段怎样读

| 字段 | 它回答的问题 | `Resolved exact rule` 的门槛 |
| --- | --- | --- |
| `catchOwner` | 谁接住或翻译这个失败 | 已审阅 caller/catch wrapper；不能由 `Error` class 猜 |
| `retryOwner` | 谁持有 attempt、backoff、fallback 或 breaker | callsite 所在精确机制直接维护该预算 |
| `toolResultOwner` | 谁把失败写回模型消息图 | exact scope 位于 tool-result ledger/pairing/end-turn 链 |
| `userSurfaceOwner` | 谁把结果变成 TUI/stderr/SDK 输出 | exact scope 或其已审阅 wrapper 明确拥有表面；debug 文案本身不算 |

没有证据的字段写 `Unresolved`。同一条 Product callsite 可以确认 retry owner，却仍不知道最终是否进入 tool_result 或用户界面。

## 场景索引：从故障症状追 owner，而不是翻流水账

| 场景 | owner class / owner | mapped callsites | 已确认的状态机特征 | 仍不能断言 |
| --- | --- | ---: | --- | --- |
| AWS SDK credential and protocol invariants | Dependency: @aws-sdk/core | 30 | SigV4 configuration and protocol serializers | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| AWS credential source/profile guards | Dependency: @aws-sdk/credential-providers | 4 | credential provider profile resolver | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| AWS endpoint provider precondition | Dependency: @aws-sdk/util-endpoint | 1 | endpoint configuration resolver | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Ajv compiler internal invariants | Dependency: ajv | 33 | schema compiler and removeSchema | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| MCP trust, policy and local config guards | Product: mcp/config-policy | 30 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| MCPB, plugin, connector and policy compilation | Product: mcp/config-policy | 41 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| OTLP protobuf object/array verification | Dependency: protobufjs OpenTelemetry OTLP generated codec | 102 | generated verify/fromObject field guards | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| OpenTelemetry global API registration guards | Dependency: @opentelemetry/api | 2 | global API register/version check | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| PreTool and permission hook entry diagnostics | Product: tool/hooks-permission | 2 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| REPL sandbox violation one-shot relaxation | Product: sandbox/enforcement | 1 | retryOwner=single unsandboxed retry gate | No exact runtime Probe proves that this branch executed in the inspected session. |
| Smithy CBOR precision and undefined-value guards | Dependency: @smithy/core/cbor | 2 | CBOR serializer | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Smithy HTTP protocol base invariant | Dependency: @smithy/core | 1 | HttpProtocol event-stream marshaller guard | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Smithy HTTP protocol implementation guards | Dependency: @smithy/core/protocols | 4 | HTTP protocol base methods | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Smithy endpoint configuration guard | Dependency: @smithy/middleware-endpoint | 1 | default endpoint rule-set resolver | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Smithy event-stream union guard | Dependency: @smithy/core/event-streams | 1 | event stream serializer | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Smithy normalized schema invariants | Dependency: @smithy/core/schema | 8 | NormalizedSchema and protocol schema helpers | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Smithy numeric serde invariant | Dependency: @smithy/core/serde | 1 | NumericValue parser | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Stainless Anthropic client fetch precondition | Dependency: @anthropic-ai/sdk | 1 | Anthropic client fetch shim VQc | The dependency constructor is proven; its Product catch, translation and user surface remain unresolved until a first-party caller is traced. |
| Storage V5 transcript compact | Product: session/transcript | 6 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| UTF-8 encoder contract | Dependency: @smithy/util-utf8 | 2 | toUtf8 encoder | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| Zod schema conversion internal invariants | Dependency: zod | 12 | Zod parser and JSON Schema converter | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| base64 encoder contract | Dependency: @smithy/util-base64 | 11 | toBase64 encoder | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| claude.ai MCP connector bounded fetch | Product: mcp/config-policy | 13 | retryOwner=claude.ai connector bounded fetch budget | No exact runtime Probe proves that this branch executed in the inspected session. |
| deferred tool resume re-entry | Product: tool/hooks-permission | 3 | toolResultOwner=deferred tool resume owner | No exact runtime Probe proves that this branch executed in the inspected session. |
| end-turn hook decisions after tool result | Product: tool/hooks-permission | 4 | toolResultOwner=tool pipeline end-turn owner | No exact runtime Probe proves that this branch executed in the inspected session. |
| hook runner cancellation and failure diagnostics | Product: tool/hooks-permission | 5 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| manual compact and context-hint diagnostics | Product: context/compact | 4 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| manual compact fallback and autocompact breakers | Product: context/compact | 8 | retryOwner=model fallback, circuit breaker and rapid-refill owner | No exact runtime Probe proves that this branch executed in the inspected session. |
| manual compact model policy gate | Product: context/compact | 6 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| precomputed compact sidecar lifecycle | Product: context/compact | 16 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| reactive compact bounded retry ladder | Product: context/compact | 4 | retryOwner=reactive compact media-strip and prompt-gap ladder | No exact runtime Probe proves that this branch executed in the inspected session. |
| reactive compact hook and response diagnostics | Product: context/compact | 3 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| reactive compact response validation | Product: context/compact | 2 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| remote session persistence conflict and retry | Product: session/persistence | 10 | retryOwner=remote persistence conflict/backoff owner | No exact runtime Probe proves that this branch executed in the inspected session. |
| request degradation, retry and fallback | Product: model/request | 63 | retryOwner=request attempt, fallback-model and payload-repair controllers | No exact runtime Probe proves that this branch executed in the inspected session. |
| sampling tool-result pairing and capability validation | Dependency: @modelcontextprotocol/sdk | 28 | Client methods createMessageStream/createMessage and exact capability guards | The dependency constructor is proven; its Product catch, translation and user surface remain unresolved until a first-party caller is traced. |
| sandbox mount, bridge and platform invariants | Product: sandbox/enforcement | 13 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| sandbox trust compilation and one-shot relaxation | Product: sandbox/enforcement | 53 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |
| socket connect and inactivity timeout | Dependency: @smithy/node-http-handler | 2 | NodeHttpHandler timeout guards | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| stream source, capability and index guards | Dependency: @smithy/util-stream | 4 | ChecksumStream and stream helpers | The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message. |
| tool-result graph invariants | Product: tool/runtime | 3 | toolResultOwner=tool-result ledger and model-message pairing guard | No exact runtime Probe proves that this branch executed in the inspected session. |
| tool-result persistence and context budget | Product: tool/runtime | 3 | toolResultOwner=tool-result ledger and context attachment owner | No exact runtime Probe proves that this branch executed in the inspected session. |
| transcript and persistence continuity diagnostics | Product: session/persistence | 15 | exact lexical caller only | No exact runtime Probe proves that this branch executed in the inspected session. |

## 五条值得读的机制结论

### 1. compact 的失败不是一个 retry counter

Reactive compact、precomputed sidecar、manual compact、model fallback、autocompact breaker 与 Storage V5 transcript compact 分属不同 owner。`retryOwner` 只有在精确 scope 直接持有 media-strip、prompt-gap ladder、re-arm cap、fallback 或 breaker 时才解析；它不能回答本次压缩是否真的触发，也不能把 transcript compact 的存储失败算成模型 API retry。

### 2. tool_result 是因果账本，不是错误字符串的展示容器

tool-result pairing、持久化、deferred resume 与 end-turn hook 各自拥有不同状态。只有进入 pairing/ledger 的 exact caller 才解析 `toolResultOwner`；PostTool diagnostic 即使写了 `error`，也可能只是观察到 hook 取消，并未产生新的模型反馈轮。

### 3. sandbox failure 可能是风控成功，而不是可靠性失败

mount pin、credential mask、bridge socket、platform capability 与 single unsandboxed retry 都是独立 guard。分类器把这些 exact Product caller 放入 sandbox owner，但只有 retry scope 能声明 retry owner；其他拒绝仍可能是 fail-closed 的预期结果。非零退出或 diagnostic 也不证明外部命令没有先产生副作用。

### 4. MCP 有“依赖协议 guard”和“产品配置/策略”两层

`@modelcontextprotocol/sdk` 的 capability/tool_result 校验属于 Dependency exact package/function；Claude Code 的 MCPB、workspace trust、managed policy、connector fetch 与 agent frontmatter 属于 Product exact caller。两层可能抛出相似 message，但恢复 owner 不同：SDK 抛给调用者，产品层才决定 config warning、reauth、tool failure 或用户表面。

### 5. `level:error` 与 `Error(...)` 都不是产品故障率

OpenTelemetry protobuf、Ajv、Zod、Smithy 和 Anthropic/MCP SDK 的 constructor 都打包在同一 bundle。dependency constructor 数量反映代码体积和生成器形状，不反映 Claude Code 用户遇到多少错误；diagnostic 是否写盘、上传或展示还受 logger、telemetry、privacy 和 UI gate 控制。

## Exact classifier 合同

1. 每条记录的 identity 绑定 stream、callee role、comparison key、canonical line/column/offset、scopePath、lexical function、immediate consumer 和 message source hash。
2. owner lookup 只读取规则中的 `exactCallsiteIds`。`reviewSelector`、canonical line range、message preview 和 scenario 仅供审阅/导航，明确标记 `classificationInput=false`。
3. rules 文件、两个 canonical input、投影 JSONL 都有固定 SHA-256；删除规则、修改 identity、换 owner 或改输入都会失败。
4. 相似 message 不继承 owner；同一 lexical function 名出现在另一 scope 也不继承 owner；扩大导航范围不会增加 mapped callsite。
5. Product 四个 flow 字段独立 fail closed；owner 已解析不等于 catch/retry/tool-result/user-surface 全解析。
6. 机器摘要把这一约束固定为 `messageSimilarityClassifies=false`、`lineRangesClassify=false`、`reviewSelectorsClassify=false`；validator 会检查字段和值。

## 机器产物与剩余欠账

- [`error-diagnostic-owner-projection.jsonl`](error-diagnostic-owner-projection.jsonl)：10,234 条互斥投影，每个 callsite 一行；
- [`error-diagnostic-owner-summary.json`](error-diagnostic-owner-summary.json)：覆盖、owner/scenario、flow 证据与全部 artifact hash；
- [`error-diagnostic-owner-rules.json`](error-diagnostic-owner-rules.json)：43 条 reviewed rules 和逐 callsite exact allowlist；
- 原始清单：[`error-message-callsites.jsonl`](source-inventory/error-message-callsites.jsonl) 与 [`diagnostic-message-callsites.jsonl`](source-inventory/diagnostic-message-callsites.jsonl)。

当前明确欠账是 **9,676 / 10,234 callsites Unresolved**。后续应按风险优先追 request terminal、tool failure、auth、filesystem write、remote side effect 和 process supervisor 的 caller/catch/user surface；不能用宽行区间或关键词批量填平。

**Static：** 所有映射限定 2.1.235 canonical bundle 与当前 source-inventory hash。

**Boundary：** 本投影不证明分支 runtime reachability、实际错误值、出现频率、日志写盘/上传、服务端接收/保留，也不证明已经发生的文件、进程或远端副作用被回滚。
