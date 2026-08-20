# Claude Code CLI 2.1.235 机器清单字段阅读指南

`analysis/source-inventory/` 的目标是让每个版本都能确定性重跑和语义 diff，不是让读者直接吞 70 个文件。本指南把 JSONL、TSV 和 TXT 中的重要字段翻译成人话，并说明一条记录能证明什么、不能证明什么。

## 先选对入口

| 你想回答的问题 | 先看 | 再回到 |
| --- | --- | --- |
| 这个版本有哪些主要系统和调用链 | [`technical-architecture.md`](technical-architecture.md) | 可读 JS、对应 inventory |
| context/cache 为什么这样工作 | [`context-governance-and-caching.md`](context-governance-and-caching.md) | settings/env/model/event JSONL |
| 遥测发到哪里、默认是否发送、内容是否脱敏 | [`telemetry.md`](telemetry.md) | event callsite、OTEL、endpoint 清单 |
| 一个 setting/env/model 字段是什么意思 | 本文 | 对应 JSONL 的原始 expression/description |
| 两个版本到底改了什么 | `compare_versions.py` 报告 | `comparisonKey` / `comparisonValue` 与源码位置 |

## 三种文件格式

### TXT：集合

每行一个标准化值，适合回答“增加/删除了什么”。例如：

```text
DISABLE_PROMPT_CACHING
ENABLE_PROMPT_CACHING_1H
FORCE_PROMPT_CACHING_5M
```

TXT 的优点是 Git diff 清楚；缺点是通常不包含调用位置、类型和条件。看到一个名字只证明它出现在对应提取方法的结果中，不证明默认启用，也不证明用户可以直接配置。

### TSV：名称到字段/属性的映射

例如 `third-party-otel-event-fields.tsv`：

```text
api_request	cache_creation_tokens,cache_read_tokens,client_request_id,...
```

第一列是事件名，第二列是该事件在静态调用点直接出现的字段集合。`<no-static-fields>` 表示 payload 由变量或 spread 提供，不能理解为事件真的没有字段。

### JSONL：一行一个结构化事实

JSONL 用于保留位置、表达式、作用域、解析状态和稳定 diff 字段。它最完整，也最容易看花。阅读时先看业务字段，再看比较字段，最后才看 location。

## 所有 JSONL 通用字段

| 字段 | 人类含义 | 是否用于语义 diff |
| --- | --- | --- |
| `comparisonKey` | 这条语义记录的稳定身份。通常由类别、规范化核心内容的 hash 和同值序号组成 | 是，用来配对旧版/新版记录 |
| `comparisonValue` | 去掉 line/offset 等位置噪声后的规范化语义 JSON 字符串 | 是，用来判断内容是否变化 |
| `line` | canonical `extracted/cli.js` 中的 1-based 行号 | 否，只用于定位 |
| `column` | 该行中的 0-based/解析器列位置 | 否，只用于定位 |
| `offset` | canonical bundle 中的字节/字符偏移定位值 | 否，只用于定位 |
| `source` | 原始表达式的摘要对象 | 通常通过规范化后的表达式间接进入 comparison value |
| `length` | 原始文本长度 | 长文本被隐藏时用于确认体积 |
| `sha256` | 原始文本 hash | 长文本/敏感形态不重复落盘时用于比对 |
| `text` | 在允许直接保留时的原始文本 | 是，通常会进入规范化表达式 |

### 为什么 `comparisonKey` 不是业务 ID

它不是 event ID、request ID 或 model ID，而是提取器生成的“记录配对键”。例如：

```text
Fv+H:187fc44e8e6c7ff5d4ca:1
```

- `Fv+H`：记录来自一方 event callsite 类别；
- 中间 hash：规范化核心语义的摘要；
- `:1`：相同核心语义出现多次时的稳定序号。

跨版本比较器用它避免把 minifier 导致的行号移动误报为功能新增/删除。

### 为什么还需要 `comparisonValue`

同一个逻辑记录可能保留配对身份，但 payload、默认值、schema 或 capability 发生变化。`comparisonValue` 保存完整语义。例如 settings 记录会包含 key、builder、description、enum、default/catch 和 RHS expression，但不包含 line/offset。

## 调用点 JSONL

适用文件包括：

- `first-party-event-callsites.jsonl`
- `otel-event-callsites.jsonl`
- `feature-flag-callsites.jsonl`
- `growthbook-callsites.jsonl`
- `error-message-callsites.jsonl`
- `diagnostic-message-callsites.jsonl`

### 调用身份字段

| 字段 | 含义 |
| --- | --- |
| `callee` | 实际被调用的压缩函数名，如 `H`、`Fv`、`Nd`、`et`、`CB`、`T` |
| `function` | 调用所在的最近词法函数名；可能是 minified 名 |
| `functionKind` | `named`、anonymous、arrow 等函数形态 |
| `arguments` | 每个实参的静态分类和原始表达式 |
| `nameArgument` | 被识别为事件名/feature 名的第一个参数 |

`function` 只是定位线索。它能帮助在可读 JS 中找到同一逻辑块，但不能当成 Anthropic 原始 TypeScript 函数名。

### `nameArgument`

常见字段：

| 字段 | 含义 |
| --- | --- |
| `kind=string` | 直接字符串，事件名已确定 |
| `kind=template` | 模板字符串，保留静态片段与插值形状 |
| `kind=identifier` | 事件名来自变量；提取器会尝试向当前/祖先 scope 找赋值 |
| `kind=conditional` | 名称由条件表达式选择 |
| `kind=member-or-call` | 名称来自属性读取或函数返回值 |
| `staticValue` | 能确定时的最终字符串值 |
| `resolvedStaticValue` | 通过 identifier assignment 间接恢复的字符串值 |

看到 `dynamicOrUnresolved` 不表示漏提取，而表示发布 bundle 本身需要运行时值才能确定。

### `payload`

一方/OTEL 事件的第二个参数通常是 object。提取器记录：

| 字段 | 含义 |
| --- | --- |
| `objectStatus=static-object` | 顶层确定是 object literal，可以继续分析 key |
| `objectStatus=not-static-object` | payload 是变量、调用结果等，不能直接枚举全部 key |
| `argument` | payload 原始表达式 |
| `directKeys` | object literal 直接写出的普通 key |
| `shorthandKeys` | `{requestId}` 这类 shorthand key |
| `computedKeys` | `{[dynamicKey]: value}`，key 可能运行时才确定 |
| `spreads` | `{...base}` 中每个 spread 的原表达式 |
| `expandedKeys` | 能递归解析的 spread 加上 direct/shorthand 后的已知完整 key 集合 |
| `unresolvedSpreads` | 仍不能静态展开的 spread；实际 payload 可能还有字段 |
| `resolution` | payload 是 identifier 时找到的最近赋值、scope 和 RHS |

### 真实记录怎么翻译

原始记录的核心形态：

```json
{
  "callee": "H",
  "nameArgument": {"kind": "string", "staticValue": "tengu_feature_ok"},
  "payload": {
    "objectStatus": "static-object",
    "directKeys": ["feature_name"],
    "spreads": [{"kind": "identifier", "source": {"text": "t"}}],
    "unresolvedSpreads": [{"kind": "identifier", "source": {"text": "t"}}]
  },
  "function": "_e"
}
```

人话结论：函数 `_e` 会记录一方事件 `tengu_feature_ok`，此调用点明确写入 `feature_name`，并把变量 `t` 的字段一起展开。因为 `t` 不能在此静态完全展开，不能声称该事件只有 `feature_name` 一个字段。

## Environment schema 与访问记录

### `environment-schema.jsonl`

这是 typed builder 恢复结果，不是正则猜出来的全大写单词。

| 字段 | 含义 |
| --- | --- |
| `name` | 环境变量名 |
| `type` | `str`、`bool`、`triBool`、`int`、`enum` |
| `options` | builder 中保留的默认、范围或 enum 等参数；没有就为 null |
| `minifiedVariable` | bundle 内承载 schema 的压缩变量名 |
| `builderLine/Offset/Column` | typed builder 的位置 |
| `exportLine/Offset/Column` | 变量通过 export/getter 暴露的位置 |

例如：

```json
{"name":"CLAUDE_CODE_MAX_CONTEXT_TOKENS","type":"int","options":null}
```

人话结论：bundle 把它作为整数环境变量解析。仅凭这条记录还不知道优先级和使用效果，必须再查 `environment-access-callsites.jsonl` 和调用分支。

### `environment-access-callsites.jsonl`

| 字段 | 含义 |
| --- | --- |
| `accessor=process.env.property` | `process.env.NAME` |
| `accessor=process.env.computed` | `process.env[expr]` |
| `accessor=environment-proxy.property` | 通过内部 typed 环境代理读取 |
| `name` | 静态可知的变量名 |
| `expression` / `keyExpression` | 动态读取时的原表达式 |

同一个 env 在 schema 中存在、在 access callsite 中出现，仍不等于路径可达。2.1.235 的 `USE_API_CONTEXT_MANAGEMENT` 就是例子：字段和读取都存在，但参与 beta 判断的表达式是 `K.USE_API_CONTEXT_MANAGEMENT && false`，所以单独设置环境变量不会激活该分支。

## Root settings schema

`root-settings-schema.jsonl` 解析根 settings object 的 156 个 direct entry 和 4 个 spread。

| 字段 | 含义 |
| --- | --- |
| `key` | settings JSON 中的字段名 |
| `kind=property` | 直接 property |
| `kind=spread` | 根 schema 通过 spread 引入另一组字段 |
| `builders` | RHS 调用链中出现的 schema builder 名 |
| `descriptions` | `.describe()` 恢复出的产品说明 |
| `enumValues` | 静态 enum 候选 |
| `defaultAndCatchExpressions` | `.default()` / `.catch()` 等表达式 |
| `expression` | 完整 RHS schema 表达式及 hash |

### Builder 名怎么读

minified bundle 中 `N()`、`jt()`、`rt()` 不是稳定公共 API。要结合行为解释：

- `N()` 记录表现为 string schema；
- `jt()` 记录表现为 boolean schema；
- `rt().int()` 表现为 number/integer schema；
- `Nr([...])` 表现为 enum；
- `optional()` 表示字段可省略；
- `min/max/positive/gt/lte` 表示数值约束；
- `catch(void 0)` 表示非法值被回退为 undefined，而不是启动必然失败。

### 三个例子

`autoCompactWindow`：

```text
rt().int().min(1e5).max(1e6).optional().catch(void 0)
```

人话：可选整数，范围 100k 到 1M；非法值在 schema 层回退为未设置。运行时还会被模型最大窗口封顶。

`skillListingBudgetFraction`：

```text
rt().gt(0).lte(1).optional()
```

人话：技能列表字符预算占 context window 的比例，范围 `(0,1]`，默认说明为 1%。超过预算时缩短 description，而不是无限挤占上下文。

`autoMemoryDirectory`：description 明确指出 checked-in project settings 中的值会因安全原因忽略，未设置时使用按 cwd 清理后的项目 memory 目录。这个“作用域限制”比字段类型更重要。

## Model catalog

### `model-catalog.jsonl`

一行一个 baked model：

| 字段 | 含义 |
| --- | --- |
| `id` | catalog 的 canonical model key |
| `family` | haiku/sonnet/opus/fable/mythos |
| `display_name` | UI 显示名 |
| `knowledge_cutoff` | baked 知识截止说明；缺失不等于模型没有 cutoff |
| `provider_ids` | firstParty、Bedrock、Vertex、Foundry、AWS、Gateway 等映射；null 表示此 catalog 没有映射 |
| `context.window` | baked context window |
| `supports_1m_beta/suffix` | 1M 请求方式能力 |
| `native_1m` | 默认原生 1M，不依赖旧式扩窗方式 |
| `max_output_tokens.default` | CLI 默认使用上限 |
| `max_output_tokens.upper` | 允许覆盖到的上限 |
| `pricing` | 指向 pricing tier 名 |
| `resolved_pricing` | 已展开的每百万 token/每次工具价格 |
| `capabilities` | 客户端用于门控的 baked 能力集合 |
| `advisor_rank` | advisor/模型选择排序信号，不是通用质量分 |
| `default_effort` | 默认 effort |
| `effort_cost_index` | 不同 effort 的相对成本/计算指数，不是美元价格 |

### 价格字段

| 字段 | 单位/含义 |
| --- | --- |
| `input` | 每百万未缓存输入 token |
| `output` | 每百万输出 token |
| `cache_write_5m` | 每百万写入 5m prompt cache token |
| `cache_write_1h` | 每百万写入 1h prompt cache token |
| `cache_read` | 每百万 cache read token |
| `web_search` | 每次 web search request |

这些是发布时 baked 值。在线计费、企业合同、未来远程 model config 可以变化，所以用它做本版本实现分析，不能替代实时价格页面。

### `model-pricing-tiers.jsonl`

一行一个可复用价格层。多个模型可以引用同一 tier。跨版本比较时，模型记录未变但 tier 价格变化仍会被单独发现。

### `model-aliases.jsonl`

解释 `opus`、`sonnet`、`haiku`、`fable` 在默认及各 provider 下解析成哪个 canonical model。provider-specific alias 不一致是有意兼容，不应只比较默认值。

## Telemetry 字段字典

### 身份与关联

| 字段 | 含义 |
| --- | --- |
| `event_id` | 单条事件 ID |
| `session_id` | 当前 Claude Code 会话 ID |
| `parent_session_id` | 父会话/fork 来源 |
| `agent_id` / `agent_type` | 子 Agent 或执行角色 |
| `request_id` | API 服务端请求 ID，通常来自响应/错误 |
| `client_request_id` | 客户端发请求前生成的关联 ID |
| `messageID` / `message_id` / `message.uuid` | 消息图中的消息 UUID，命名取决于事件/出口 |
| `organization_uuid` / `account_uuid` | 认证上下文中的组织/账号标识；并非每事件都有 |
| `device_id` | 客户端设备标识字段能力 |
| `query_source` | 请求用途，如主线程、sdk、compact、memory extraction |

`request_id` 和 `client_request_id` 不是同一个字段。前者通常用于和服务端日志对应；后者可关联在拿到服务端 ID 之前的准备、重试和失败。

### Token 与费用

| 字段 | 含义 |
| --- | --- |
| `input_tokens` | 未从 cache 读取/写入的输入 token |
| `output_tokens` | 输出 token |
| `cache_creation_input_tokens` / `cache_creation_tokens` | 本次写 cache 的输入 token |
| `cache_read_input_tokens` / `cache_read_tokens` | 本次从 cache 读出的输入 token |
| `cache_creation_5m_input_tokens` | 5m 写入拆分 |
| `cache_creation_1h_input_tokens` | 1h 写入拆分 |
| `cost_usd` | 浮点美元 |
| `cost_usd_micros` | 百万分之一美元整数，减少浮点误差 |
| `total_cost_usd` | 会话/任务累计费用，具体范围看事件 |
| `web_search_requests` | 服务端工具 usage 中的 web search 次数 |

不同出口会把同一语义命名成 snake_case 或较短字段，必须按事件通道读，不能只按字符串相等做数据仓库 join。

### 延迟、重试与流

| 字段 | 含义 |
| --- | --- |
| `duration_ms` | 当前操作总耗时 |
| `time_to_first_byte_ms` / `ttft` | 首字节/首 token 延迟 |
| `attempt` / `retry_attempt` | 当前尝试序号 |
| `max_retries` | 最大重试数 |
| `timeout_ms` | 当前路径超时配置 |
| `error_code` / `status` | 规范化错误或 HTTP 状态 |
| `stop_reason` | 模型/客户端结束原因 |
| `fallback_cause` | 流式转非流式或模型 fallback 的触发原因 |
| `speed` / `service_tier` | 快速模式/服务等级响应属性 |

### Tool 与权限

| 字段 | 含义 |
| --- | --- |
| `tool_name` | 工具名；Datadog 分支可能把动态 MCP/skill 名归一化 |
| `tool_use_id` | 一次工具调用 ID |
| `decision` | allow/deny/ask 等决策结果 |
| `decision_source` / `source` | user、policy、rule、mode、hook 等来源 |
| `permission_mode` | plan、acceptEdits、bypassPermissions 等当前模式 |
| `duration_blocked_ms` | 等用户批准的阻塞时长 |
| `is_error` | 工具结果或事件是否错误 |

### Context 与 compact

| 字段 | 含义 |
| --- | --- |
| `pre_tokens` / `preCompactTokens` | compact 前 token |
| `post_tokens` / `postCompactTokens` | compact 后 token |
| `tokensSaved` | 本次估算节省 |
| `messages_summarized` | 摘要覆盖消息数 |
| `precomputed` | 是否复用预计算摘要 |
| `thresholdSource` | auto/settings/env/remote 等阈值来源 |
| `effective_window` | 真正采用的窗口，不一定等于模型标称窗口 |
| `enforced` | worker/远端是否强制该状态 |
| `mcApplied` / `mcTokensSaved` | microcompaction 是否执行及节省量 |

更完整的状态机见 [`context-governance-and-caching.md`](context-governance-and-caching.md)。

## Broad heuristic 文件怎么用

以下集合可能混入第三方依赖、内嵌文档或并非用户可配的标识：

- `environment-like-identifiers.txt`
- `schema-property-identifiers.txt`
- `storage-namespaces.txt`
- `named-component-identifiers.txt`
- `urls.txt`
- `probable-config-keys.txt`（位于 reverse index）

正确用法是“发现候选，再回到 callsite/schema/可达分支验证”。错误用法是把 1,048 个全大写词都写成 Claude Code 环境变量，或把 1,971 个 schema property 都写成 root settings。

## 如何读一条版本差异

假设比较报告显示某个 settings JSONL 记录 `comparisonKey` 相同、`comparisonValue` 变化：

1. 对比 `comparisonValue`，确认变化是 description、enum、default、constraint 还是 expression；
2. 用新旧 `line/offset` 回到各自 canonical bundle；
3. 查实际读取 callsite，确认设置是否可达、优先级是什么；
4. 查 CLI/UI 文案和错误分支，确认用户何时能观察到；
5. 查 telemetry/event 是否增加了状态字段；
6. 最后写成“行为变化”，不要只写“字段 hash 变化”。

事件 callsite 新增也不能自动等于新功能。它可能只是新增观测。必须检查事件附近是否有新的命令、设置、请求字段、状态变化或用户输出。

## 静态提取边界

清单能完整保留发布 bundle 中目标 AST 节点的静态形状，但以下内容仍需运行时：

- remote config/feature flag 的当前值；
- API 返回的模型/账户/组织数据；
- 用户 settings、环境变量和项目文件的实际内容；
- 动态 computed key 和无法解析 spread 的最终字段；
- 服务端对事件、cache、风控和请求的内部处理。

`knownStaticExtractionGaps=[]` 的含义是“定义好的静态提取合同没有漏项”，不是“宇宙中所有运行时值都已恢复”。
