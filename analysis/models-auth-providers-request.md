# 模型、认证、Provider 与请求装配

这一层决定 Claude Code 最终把什么上下文交给哪个模型、通过哪条网络路径发送、使用哪种凭据，以及哪些 beta、缓存、thinking 和工具能力能够进入请求。它不是一个简单的 `model + apiKey + messages` 对象：同一个模型别名在 first-party、Bedrock、Vertex、Foundry、Anthropic cloud variants、Mantle 或 gateway 下，模型 ID、鉴权材料、endpoint、可用 beta 和失败恢复路径都可能不同。

## 先建立正确的调用链

```text
用户 --model / agent model / settings / 环境默认
                    |
                    v
              模型别名解析与能力目录
                    |
                    v
provider selector -> provider-specific model ID / region / endpoint
                    |
                    v
credential selector -> OAuth / API key / auth token / helper / cloud credentials
                    |
                    v
context builder -> system + messages + tools + thinking + cache + betas
                    |
                    v
Messages streaming request -> SSE parser -> Agent Loop / retry / fallback
```

Agent Loop 在 `reverse/javascript/cli.readable.js` 271832-271842 调用 `m.callModel` 时，已经把 `messages`、`systemPrompt`、`thinkingConfig`、当前工具表、signal、主模型、下一 fallback model、是否非交互、MCP 状态、effort、cache 行为和 tracing 回调交给模型层。也就是说，`callModel` 不是从零读取所有配置；它消费的是前面多层已经解析好的有效状态。

## Provider selector 持有什么状态

2.1.235 的 provider 判定函数位于 `reverse/javascript/cli.readable.js` 62740-62743。顺序是：

1. gateway 状态先于普通环境开关；
2. `CLAUDE_CODE_USE_BEDROCK`；
3. `CLAUDE_CODE_USE_FOUNDRY`；
4. `CLAUDE_CODE_USE_ANTHROPIC_AWS`；
5. `CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD`；
6. `CLAUDE_CODE_USE_MANTLE`；
7. `CLAUDE_CODE_USE_VERTEX`；
8. 都未命中时为 `firstParty`。

这是实际优先级，不是“哪个环境变量最后写入就覆盖”。多个 selector 同时为真时，排在前面的分支获胜。用户排查“明明设置了 Vertex 却走 Bedrock”时，第一步应打印所有 provider selectors，而不是只看期望使用的那个变量。

Provider 状态还会影响：

- 模型别名映射到哪种 provider model ID；
- region 和 endpoint 选择；
- 使用 API key、OAuth、AWS、GCP 还是 Foundry 凭据；
- prompt cache 1h、Tool Search、某些 beta 和 first-party account capability 是否可用；
- 错误文本、doctor 检查和 fallback 是否进入 provider-specific 分支；
- telemetry 中记录的 provider 标签和诊断维度。

## 自定义 Base URL 为什么不只是换域名

`ANTHROPIC_BASE_URL` 会改变 endpoint，也会改变“这是不是 first-party host”的判断。`reverse/javascript/cli.readable.js` 62783-62798 明确把 `api.anthropic.com` 作为已知 first-party host；设置其他 host 时，除非 `_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL` 显式覆盖，否则相关逻辑会把它视为非 first-party。

这会直接影响能力门控。例如 Tool Search 在 `reverse/javascript/cli.readable.js` 114358-114369 检查 first-party provider 与 base URL；代理若能完整转发 `tool_reference`，仍需要显式配置对应开关。仅把代理做成 Anthropic-compatible JSON 并不自动证明它支持所有 first-party beta、SSE 事件、cache TTL、OAuth 或 remote-control 协议。

因此代理兼容性必须拆成至少五层验证：

| 层 | 要验证的对象 | 失败表现 |
| --- | --- | --- |
| HTTP | path、method、headers、status | 401/404/代理握手失败 |
| Messages schema | system/messages/tools/thinking | 参数拒绝或字段被丢弃 |
| SSE | block start/delta/stop/message stop | 流中断、空结果、thinking/tool JSON 断裂 |
| Agent Loop | `tool_use` 与 `tool_result` 配对 | 工具执行后无法继续 |
| 产品协议 | beta、Tool Search、OAuth、remote/cloud | 功能被客户端 gate 或服务端拒绝 |

本仓库的正向探针已经证明普通 HTTP `ANTHROPIC_BASE_URL` 可以驱动 2.1.235 完成真实工具闭环；它没有把该本地 endpoint 声称为 first-party，也没有据此证明所有 beta。

## 认证不是单一优先级列表

认证需要先按 provider 分流，再在 provider 内选择 credential source。环境契约在 `reverse/javascript/cli.readable.js` 39422-39432 把以下对象分组：

- provider selectors 与 cloud workspace/project/region；
- endpoints；
- `ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN`、`CLAUDE_CODE_OAUTH_TOKEN`；
- `apiKeyHelper`、`awsAuthRefresh`、`awsCredentialExport`、`gcpAuthRefresh`；
- AWS/GCP credential files；
- model override；
- proxy、TLS certificate 和 nonessential-traffic controls。

API-key 选择路径在 `reverse/javascript/cli.readable.js` 87433-87455 显式返回 `apiKeySource`，能区分直接环境 key、`apiKeyHelper` 和无 key。OAuth 还维护 token source、401 refresh、存储凭据与用户显式 `CLAUDE_CODE_OAUTH_TOKEN` 的冲突处理。Cloud provider 则需要自己的 region/project/profile/refresh 组合。

这里有两个容易漏掉的安全细节：

1. `apiKeyHelper` 是可执行程序，不是静态字符串。2.1.235 在 workspace trust 未确认前调用 helper 会触发安全错误，相关 guard 在 readable JS 86609-86635。
2. 子进程、background worker 和 host-managed provider 不能无条件继承全部父进程环境。源码维护专门的 credential/environment 分类集合，用于传播、清理或交给 host refresh。

所以诊断认证时不能只问“有没有 key”，还要问：当前 provider 是谁、source 是谁、helper 是否获信任、refresh 是否成功、最终 header 由客户端还是 host 注入。

## 模型选择分成名称、能力和 provider ID

机器清单中的 [model-catalog.jsonl](source-inventory/model-catalog.jsonl)、[model-aliases.jsonl](source-inventory/model-aliases.jsonl)、[model-catalog-metadata.jsonl](source-inventory/model-catalog-metadata.jsonl) 和 [model-pricing-tiers.jsonl](source-inventory/model-pricing-tiers.jsonl) 分别回答四个问题：

- bundle 认识哪些 baked model；
- `sonnet`、`opus`、`haiku` 等别名如何指向具体模型；
- 每个模型声明了哪些窗口、thinking、fast mode 或 provider metadata；
- token、cache write/read 和长上下文成本如何计价。

有效模型不只来自 `--model`。主会话、subagent definition、`ANTHROPIC_MODEL`、默认模型、small/fast model、fallback model、advisor/compact/background classifier 都可以持有不同选择。`model: inherit` 只表示子 Agent 默认继承父会话的模型选择；它仍然拥有独立请求与上下文。

版本比较时应以稳定的 catalog/alias/provider mapping 为主，不能把 minified 局部变量变化当成模型变更。真正有意义的变化包括：别名指向改变、某 provider 从 `null` 变为可用、窗口/价格/能力 metadata 改变、默认 fallback 顺序改变。

## Request construction：每一类字段解决什么问题

模型请求至少由以下组组成：

| 组 | 典型字段 | 目的 |
| --- | --- | --- |
| 身份 | `model`、provider-specific ID | 选择实际推理端点 |
| 上下文 | `system`、`messages` | 提供指令、历史和观察结果 |
| 输出预算 | `max_tokens` | 控制单次响应上限，不等同于 Agent 总轮数 |
| 思考 | `thinking`、effort | 控制推理预算与展示策略 |
| 工具 | `tools`、`tool_choice` | 声明可调用工具合同 |
| 缓存 | `cache_control`、cache breakpoint | 稳定前缀复用与 TTL |
| Beta | `anthropic-beta` | 协商 tool search、cache、thinking 等协议能力 |
| 观测 | request ID、trace headers、metadata | retry、成本、诊断与链路关联 |

SDK 层最终向 `/v1/messages?beta=true` 发送 body，并依据 `stream` 选择流式路径；可读源码 12294-12307 还保留 non-streaming timeout、beta header、user-profile header 和 count-tokens 路径。Agent Loop 的主请求不是直接拼接原始 transcript：在此之前已经完成 message graph 选择、compact、tool-result cleanup、system 分段、deferred schema、cache breakpoint 和 provider-specific betas。

最关键的字段关系是 `tool_use.id` 与下一轮 `tool_result.tool_use_id`。本版精确二进制探针实际观测到：第一次请求声明 `Read`；模型返回 ID 为 `toolu_agent_loop_probe` 的调用；第二次请求同时包含该 `tool_use` 和同 ID、含文件 marker 的 `tool_result`；最终 result 为 `TOOL_EXECUTION_OK`。完整输入、literal output 和 exit status 见 [agent-loop-tool-result-resume.json](runtime-probes/agent-loop-tool-result-resume.json)。

## Retry、fallback 与“轮次”的边界

HTTP retry、SSE 续流、同模型请求重试、模型 fallback 和 Agent turn 不是同一个计数器。Agent Loop 的 `turnCount` 代表逻辑模型-工具循环；网络层可在一次逻辑 turn 内做多次 API attempt。fallback 还会携带 refusal lane、fallback credit、silent/visible model 和 streaming fallback 回调。

用户看到“请求了三次”不能直接推断“消耗三个 maxTurns”。反过来，工具已完成后再发生 fallback，也不能把外部副作用回滚。请求层能丢弃 provisional message、生成 synthetic error 或重建下一次消息；文件写入、shell 命令和远端 API 已经发生的动作仍需要工具自身的幂等、检查点或人工恢复。

## 微小但会影响真实使用的特性

- 自定义 base URL 会改变 Tool Search 等 optimistic gate，不只是 URL 字符串。
- `ANTHROPIC_AUTH_TOKEN` 与 `ANTHROPIC_API_KEY` 是不同 source；OAuth 401 refresh 又是另一条状态机。
- `apiKeyHelper` 输出必须是可接受的 printable ASCII token，且不能在 workspace trust 前运行。
- provider 选择优先级固定，多 selector 同时开启不会合并 provider。
- model alias 和 provider mapping 分离：同一个用户名称能映射成不同云平台 ID。
- count-tokens、compaction 请求和主 Messages 请求不是同一种调用，分析 capture 时要分类。
- non-streaming timeout 会参考 `max_tokens`；流式路径则还受 stream idle timeout 和事件完整性约束。
- 关闭 telemetry 不等于关闭模型请求；`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 的边界应按具体 traffic family 验证。

## 精确二进制请求捕获

[runtime-controls.json](runtime-probes/runtime-controls.json) 对 SHA-256 固定的版本文件运行受控请求，观察到：

- `ANTHROPIC_AUTH_TOKEN` 变成 `Authorization: Bearer $TOKEN`；
- `x-api-key` 不存在；
- `anthropic-version` 与 `anthropic-beta` 存在；
- `model` 为命令行指定的 `claude-sonnet-4-5`；
- `tools` 包含 Read schema；
- 请求体出现 3 个 `cache_control`。

这给 provider/auth/request 章节增加了 wire-level 证据。它只证明客户端构造结果，不证明自定义 endpoint 实现了这些 beta，也不证明 Anthropic 服务端接受同样的 token、cache 或 routing 语义。

## 跨版本比较清单

每个新版本至少比较 provider precedence、first-party host 判定、credential source、helper trust gate、model alias/provider ID、Messages body 字段、beta 集合、cache TTL、thinking/effort、fallback lane、retry 参数和正向工具回灌 probe。某个 endpoint host 或压缩符号变化只作为线索；只有稳定 key、请求字段、可达分支、probe 或官方 release note 与本地证据互相印证，才写成功能变化。

## 证据与边界

结构化证据条目：`provider.selection`、`provider.first-party-host`、`auth.environment-contract`、`auth.key-source`、`agent-loop.model-call`、`probe.agent-loop-tool-feedback`。

已证实的是客户端 selector、credential source、request state 和本地工具闭环。未从发布物中恢复的是 Anthropic 服务端的真实路由器、缓存命中算法、账户 abuse/risk score、服务端隐藏 beta 分流、容量调度和模型内部实现。这些必须保留为 `Boundary`，不能因为客户端发送了某个 header 就写成服务端一定执行了对应策略。
