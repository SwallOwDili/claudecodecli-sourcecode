# 工具、权限与 Hooks：一次动作为什么要经过十几道关卡

模型生成 `tool_use` 只是在申请执行一个动作，不等于动作已经获准。Claude Code 2.1.235 会把模型给出的名称和 JSON input 依次送入工具查找、schema、自定义校验、hook、permission/policy、sandbox、实际调用和输出校验。每一层管理不同风险，失败也必须转换成模型能理解的 `tool_result`，否则 Agent Loop 会得到一段断裂历史。

本章解释客户端本地执行控制面。它不声称恢复 Anthropic 服务端账户风控、abuse score 或封禁规则；发布 bundle 没有这些服务端内部实现证据。

## 完整控制管线

`2.1.235` 单工具核心路径位于 `reverse/javascript/cli.readable.js` 316092-316487。用可读语义展开如下：

```text
model emits tool_use(name, id, raw input)
  |
  v
1. 按 canonical name / alias 查找工具
  |
2. 检查 abort signal 与 isolation latch
  |
3. 解析或正规化 JSON input
  |
4. 工具 input schema 校验
  |
5. 工具自定义 validateInput
  |
6. 运行 PreToolUse hook
  |      可附加 context、改 input、给 permission decision、阻止/defer
  v
7. 汇合 permission mode、allow/deny rule、managed policy、
   classifier、sandbox eligibility、working directory 与用户审批
  |
8. hook/permission 若返回 updatedInput，再次跑 schema/validate
  |
9. 标记 tool in-progress，进入实际 tool.call
  |
10. OS/sandbox/network/filesystem/credential 控制实际约束动作
  |
11. 把实现返回值映射为标准 tool_result
  |
12. 运行 PostToolUse / PostToolUseFailure
  |
13. updatedToolOutput 再做 output schema 校验
  |
14. 写 result、attachments、context layers、timing，清除 in-progress
```

这条顺序解释了三个常见误区：

- schema 通过不表示权限通过；参数合法仍可能是危险动作。
- permission allow 不表示操作系统一定能执行；sandbox、文件权限和网络仍可拒绝。
- `tool.call` 返回不表示结果一定进入下一轮；PostToolUse 和 output schema 仍可能报告问题或回退修改。

## 工具查找：名称本身就是协议

### Canonical name 与 alias

模型输出的是字符串工具名。客户端需要把它解析到当前 turn 的工具对象；工具可能来自内置 catalog、MCP、plugin、skill/command 或 Agent 专用集合。alias 可以兼容旧名或展示名，但最终必须落到一个拥有 input schema、permission 行为和 `call` 方法的实现。

找不到工具时，客户端不会让整个 Agent Loop 抛裸异常，而是生成带原 `tool_use_id` 的 error `tool_result`，并可附相似工具提示。下一轮模型因此能改名重试。

### Deferred tool 的特殊错误

当 Tool Search 把工具标记为 `defer_loading` 时，模型初始可能只知道工具名而没见过完整 schema。如果模型直接猜 input，校验错误会提示先发现/加载工具。这个分支很关键：它把“模型参数错了”与“运行时故意没提供 schema”区分开，避免模型在未知接口上无限试错。

## Input schema 不是形式检查

输入校验至少承担四项职责：

1. 拒绝无法解析的 JSON 和错误基本类型。
2. 检查必填字段、enum、路径/范围等结构约束。
3. 让工具的 `validateInput` 做依赖运行状态的语义检查。
4. 在 hook 或 permission 改写 input 后重新验证。

第四项是安全边界。如果 hook 把一个已验证的只读路径改成另一个路径，而客户端不复验，前面的 schema 与 permission 就失去意义。2.1.235 明确对 `updatedInput` 重新跑验证；无效改写会成为配置/hook 错误，不会直接进入 `tool.call`。

## PreToolUse：动作前的可编程控制点

PreToolUse 位于实际权限汇合之前，可以：

- 读取 tool name、input、session/query/agent 上下文；
- 输出进度或补充 attachment/context；
- 给出 `allow`、`deny`、`ask`、`defer` 等 permission decision；
- 返回 `updatedInput`；
- 阻止继续并给出模型可读原因；
- 在特定 print/SDK 流程中 defer 单个工具。

`defer` 不是普遍挂起语义。本版在交互模式会忽略 defer；同一模型响应含多个 sibling tools 时也不能安全地只 defer 一个，因为 resume 后可能破坏 `tool_use`/`tool_result` 配对。因此 defer 受运行模式和批次形态门控。

## Permission 决策不是一张 allow/deny 表

### 六种本版权限模式

机器表面恢复出：

| 模式 | 核心意图 | 仍受什么约束 |
| --- | --- | --- |
| `default` | 按默认规则和必要审批执行 | deny rule、policy、sandbox、trust gate |
| `acceptEdits` | 降低常规文件编辑审批摩擦 | 非编辑工具和高风险分支仍单独判断 |
| `plan` | 强制先规划/只读阶段 | 退出计划模式和写动作需要协议/批准 |
| `dontAsk` | 不弹交互审批；未预授权动作不能靠对话放行 | 更容易 fail closed，不等于全部允许 |
| `bypassPermissions` | 跳过常规 permission prompt | 必须显式启用；managed settings 可禁用；OS/sandbox 边界仍独立 |
| `auto` | 由自动分类与规则决定低风险动作 | 未评估动作、长 transcript 等分支可转人工或阻止 |

输入兼容层还接受 `manual`，随后规范化为 `default`；它不是第七种内部决策模式。跨版本比较应分别看用户输入 alias 和内部 enum，避免同一个语义重复计数。

`--dangerously-skip-permissions` 和 `--allow-dangerously-skip-permissions` 属于显式 CLI 表面。bundle 还会在运行时拒绝被 settings 禁止的 `bypassPermissions`，而 `auto` 需要 feature gate 可用。

### 决策输入

最终结果会综合：

- 当前 permission mode；
- `--allowed-tools` / `--disallowed-tools` 和 settings rules；
- 工具自身 `canUseTool`；
- path、working directory、command 和网络目标；
- classifier / safety check；
- PreToolUse 或 PermissionRequest hook；
- managed policy 与 enterprise helper；
- sandbox 是否覆盖该动作；
- 用户本次、会话或持久批准。

机器清单中的 decision sources 包括 `classifier`、`hook`、`mode`、`rule`、`safetyCheck`、`sandboxOverride`、`workingDir`、`asyncAgent` 等。版本比较应关注决策优先级和 fail-closed 语义，而不是只比较 mode 名称。

### 拒绝如何进入 Agent Loop

拒绝不会执行工具。客户端构造同 `tool_use_id` 的 error result，记录 decision reason/source，并把它作为下一轮观察。模型可以改成只读方案、缩小路径、换工具或向用户解释阻塞。若直接丢掉 result，Anthropic message protocol 会留下孤立的 `tool_use`。

## Hooks 与生命周期

本版机器清单恢复出 31 个 hook event。与工具和循环最关键的包括：

| Hook | 发生时机 | 能改变什么 |
| --- | --- | --- |
| `PreToolUse` | input 校验后、permission/call 前 | input、permission decision、上下文、是否继续 |
| `PermissionRequest` | 需要权限决策时 | allow/deny/ask 等审批结果 |
| `PostToolUse` | 单工具成功后 | attachment、上下文、候选 output |
| `PostToolUseFailure` | 单工具失败后 | 诊断与补充反馈 |
| `PostToolBatch` | 一批工具全部 resolve、下一次模型请求前 | 观察整批结果、阻止继续、批量收尾 |
| `Stop` | 主 Agent 即将正常结束时 | 允许结束或用 blocking feedback 让模型继续 |
| `SubagentStop` | 子 Agent 即将结束时 | 同类控制，但作用于子 Agent |
| `PreCompact` | compact 前 | 观察/阻止/准备上下文治理 |
| `Notification` | 通知生命周期 | 外部提醒或集成 |

### PostToolUse 与 PostToolBatch 的并发差异

多个 concurrency-safe 工具可以并行，因此每个工具的 PostToolUse 也可能并发发生。PostToolBatch 在所有 sibling tools 都 resolve 后只执行一次，并拿到整批状态。需要跨工具一致性的审计、汇总或阻止逻辑应放在 batch 层，不能假设多个 PostToolUse 严格按模型输出顺序串行。

该语义在 `schema-descriptions.txt` 中有明确描述：PostToolBatch 在下一次模型请求前触发一次，PostToolUse 则逐工具触发且并行工具可并发。

### Stop hook 能重新打开 Agent Loop

Stop/SubagentStop 返回 blocking error 时，CLI 把 assistant output 和 hook feedback 加回消息图，设置 `stopHookActive`，增加 `turnCount`，再请求模型修正。默认连续阻止 cap 为 8；超过后客户端覆盖 hook，避免坏脚本永久困住会话。

这意味着 Stop hook 是控制流，不只是通知。hook 必须检查 `stop_hook_active`，并在修正条件满足后返回成功。

## PostToolUse 与 output contract

工具实现返回的原始对象会先由 mapper 转成 Anthropic `tool_result`。PostToolUse 可追加 attachment 或提出 `updatedToolOutput`，但修改后的输出仍必须满足工具 output schema。

复验失败时，本版保留原始工具输出，并生成 hook error attachment。这样一个错误 hook 不会把原本成功的结果替换成协议不合法对象，也不会让下一轮 message graph 断裂。

## Sandbox：permission 之后仍有执行边界

### Runtime 开关

本版存在：

- `sandbox.enabled`；
- `sandbox.failIfUnavailable`；
- `sandbox.allowUnsandboxedCommands`；
- `sandbox.autoAllowBashIfSandboxed`；
- `sandbox.enableWeakerNetworkIsolation`。

`failIfUnavailable` 决定 sandbox 无法建立时是启动/执行失败还是降级。`allowUnsandboxedCommands` 控制是否能绕开隔离；它不是 permission mode 的同义词。

### 文件系统

控制面包括 allow/deny read/write paths、managed read paths、filesystem disabled 和 working directory/trust gate。有效规则需要处理路径规范化、symlink、父子目录与附加工作目录，不能只做字符串前缀比较。

### 网络

控制面包括：

- allowed/denied domains；
- strict allowlist；
- managed domains only；
- local binding；
- Unix sockets；
- Mach lookup；
- TLS terminate；
- weaker isolation fallback。

strict 模式无匹配时会 fail closed。域名 allow 不自动等于所有 socket/本地服务都允许，这些维度有独立规则。

### 凭据

bundle 中可以看到 env/file credential 的 deny/mask、JWT decode、claim masking、host injection、AWS pair 与 SigV4 等控制面。它们的目的不是替代 secret manager，而是减少把本地凭据原文暴露给工具进程、网络目标或模型上下文的概率。

## Workspace trust 与扩展信任

以下 gate 在工具执行前后影响可装载能力：

- workspace trust；
- bare Git repository 与 `gitdir` redirect 检查；
- deep-link argument injection 拒绝；
- credential file permission 检查；
- 未信任 workspace 在读取 MCP headers helper 前阻止执行；
- strict MCP config 和企业 `allowedMcpServers`；
- safe mode / bare mode 对 plugin、hook、skill、MCP 的收缩。

信任项目不等于信任该项目声明的一切扩展。MCP helper、hook command、plugin 和 imported instructions 仍有各自来源与 policy 边界。

## Managed settings 为什么优先级更高

企业治理面包括 `allowManagedPermissionRulesOnly`、`allowedMcpServers`、`availableModels`、`forceLoginOrgUUID`、managed settings、policy helper、process wrapper，以及 managed-only filesystem/network 规则。

它们的共同语义是：普通 user/project/local settings 不能覆盖管理员限定。对逆向报告而言，重要的不只是发现 key，而是验证合并顺序：同名用户配置存在时，最终有效值是否仍由 managed source 决定；解析失败时是忽略、回退还是 fail closed。

## 工具并发如何影响权限与 hook

多个只读工具可能在模型仍流式输出时开始执行。每个工具独立完成 schema、PreToolUse 和 permission；一个工具等待用户审批时，已经获准的 sibling 是否继续取决于调度屏障与具体工具安全性。

非并发安全工具形成顺序屏障：后续工具不能越过它。这个规则既保护共享文件状态，也让审批顺序更可理解。最终结果按 `tool_use_id` 配对，不依赖实际完成顺序；PostToolBatch 等全部 resolve 后再统一收尾。

详见 [Agent Loop](agent-loop.md) 的 streaming executor 和 concurrency barrier。

## 精确二进制：PreToolUse deny 到底阻止了什么

[runtime-controls.json](runtime-probes/runtime-controls.json) 用隔离 settings 注册 PreToolUse/PostToolUse/Stop hooks，并让模型请求读取一个带固定 marker 的本地文件。PreToolUse 对 Read 返回 `permissionDecision=deny`：

1. PreToolUse 事件带到了原 `tool_use_id`；
2. Read 没有读取 fixture，因此回灌内容不包含文件 marker；
3. 下一次 Messages 请求仍有同 ID 的 `tool_result`；
4. 该 result 是 error，并包含 hook 给出的拒绝原因；
5. 模型据此返回 `HOOK_DENY_OK`，进程仍以 success 结束。

这验证了权限链的关键合同：deny 阻止的是 `tool.call`，不是阻止 Agent Loop 继续推理。对用户而言，“工具被拒绝”与“会话失败”是两个不同状态；模型仍能改计划、换工具或解释阻塞。PostToolUse 没有机会撤销动作，PreToolUse 才位于副作用前。

## 失败矩阵

| 失败层 | 是否调用工具 | 下一轮看到什么 | 用户应该查什么 |
| --- | --- | --- | --- |
| 工具不存在 | 否 | unknown tool error result | tool registry、MCP refresh、名称/alias |
| JSON/schema 错误 | 否 | InputValidationError | schema、deferred tool 是否已 discover |
| PreToolUse block | 否 | hook feedback/error result | hook stdout/exit/timeout、匹配器 |
| permission deny | 否 | denial reason/source | mode、rules、managed policy、审批选择 |
| sandbox block | 通常否或进程立即失败 | sandbox/command error | path/domain/socket/availability |
| tool.call exception | 已尝试 | structured tool error | 实现、外部依赖、abort、timeout |
| PostToolUse output 非法 | 工具已成功 | 原 output + hook error attachment | hook 修改和 output schema |
| PostToolBatch block | 一批工具已完成 | blocking batch feedback | 已发生副作用与后续重入 |
| Stop hook block | 本轮动作已完成 | hook feedback，Agent Loop 再运行 | cap、maxTurns、stop_hook_active |

后置 hook 阻止的是“继续或结束”，不能撤销前面已完成的 side effect。需要事务性的工具必须自己实现 dry run、幂等键、补偿操作或明确确认点。

## 用户如何判断权限为什么总弹

按顺序检查：

1. 当前 permission mode 是否是预期值。
2. 工具名和 input 是否每次变化，导致已有 rule 无法命中。
3. 项目/user rule 是否被 managed-only policy 排除。
4. hook 是否返回 `ask`、修改 input 或每次产生新 command/path。
5. sandbox 是否覆盖动作；“已 sandbox”可能允许 auto-approve 某些 Bash，未覆盖则继续问。
6. UI 提供的是本次、会话还是持久授权；本次授权不会自动写规则。
7. 子 Agent 是否使用 `permissionMode: bubble`，把审批上浮到主会话。

## 跨版本必须比较什么

- permission mode 集合、CLI flags、启用 gate 与切换拒绝语义；
- rule source、managed source 和决策优先级；
- tool input schema、alias、自定义 validation 和 updatedInput 复验；
- hook event 集合、字段、timeout、permission decision 与 blocking 语义；
- PostToolUse/PostToolBatch 的并发和调用次数；
- Stop hook cap、maxTurns 交互和 terminal reason；
- sandbox availability fallback、filesystem/network/socket/domain 规则；
- credential mask/deny/inject 行为；
- trust gates、MCP/plugin/helper 的装载边界；
- 失败 result 是否继续保证 `tool_use_id` 配对。

## 证据位置

- 单工具完整管线：`reverse/javascript/cli.readable.js` 316092-316487。
- streaming executor 与并发屏障：`reverse/javascript/cli.readable.js` 267124-267268。
- Stop hook 和默认 cap 8：`reverse/javascript/cli.readable.js` 272253-272264。
- 机器化风控表面：[risk-control-surface.txt](risk-control-surface.txt)。
- hook event：[hook-events.txt](source-inventory/hook-events.txt)。
- hook/permission/schema 字段说明：[schema-descriptions.txt](source-inventory/schema-descriptions.txt)。
- root settings 结构：[root-settings-schema.jsonl](source-inventory/root-settings-schema.jsonl)。

字段存在只证明客户端认识这个配置。真正的行为结论必须同时查看默认值、来源优先级、feature/platform gate、调用位置和失败分支。
