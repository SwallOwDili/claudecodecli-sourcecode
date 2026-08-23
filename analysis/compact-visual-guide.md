# Claude Code `/compact`：长对话为什么压缩后还能继续工作

一个编码任务跑了很久：Claude 已经读过文件、改过代码、执行过测试，也记住了用户几轮纠正。上下文快满时，用户执行 `/compact`。

接下来最关键的问题不是“删掉了多少条消息”，而是：**旧对话被替换成什么，哪些近期内容和因果关系必须留下，下一次模型请求凭什么还能接着干活？**

> 本文描述 Claude Code CLI `2.1.235`。结论来自该版本可读化 bundle 和同版本运行 Probe；源码定位统一放在文末，不打断主线。

## 一分钟答案

`2.1.235` 的 `/compact` 不是固定发起一次总结请求。`PreCompact` hook 放行后，客户端先检查 precomputed result：命中时不发送新的 summary request，直接复用已有 Summary、原保留组和预计算之后的 `messagesSince` 进入 finalize/rebuild；未命中时，才让模型把较早的合法消息组写成工程交接摘要，并在 prompt-too-long 时缩短待总结前缀重试。两条路径最终都会按各自结果重建有效上下文并写入 `compact_boundary`。

![用户执行 compact 后先检查预计算结果，命中直接重建，未命中才请求 Summary](visuals/compact-lifecycle.svg)

一句话记忆：

```text
Summary 管较早历史的语义，Preserved messages 管近期因果，Attachments 管精确信息，Boundary 管恢复关系。
```

下面先沿着一次**未命中预计算结果的普通手动 `/compact`** 展开 summary miss 路径，再回到 precomputed hit、reactive 和 cold/full compact 的差异。

## 第一步：用户输入 `/compact`

假设当前任务正在重构一个命令行项目：

- 已经修改了三个源文件；
- 刚修复两个测试失败；
- 最近一次工具调用读取了配置文件；
- Plan 中还有一个未完成步骤；
- 用户输入 `/compact 保留测试失败原因和当前重构计划`。

客户端不会把这句话当成普通业务问题交给 Agent Loop 继续执行。它切换到 compact 流程，先运行 `PreCompact` hook。

`PreCompact` 可以：

- 允许继续；
- 给总结任务追加项目自定义要求；
- 直接阻止 compact。

Hook 放行后，客户端先检查是否存在通过 session、model、timestamp、boundary 与 preserved UUID 校验的 precomputed result。命中时直接进入 finalize/rebuild；只有未命中、结果失效或 custom instructions/Hook 追加使预计算结果不再适用时，才准备新的总结请求。

## 第二步：未命中预计算时，客户端才加入“交接文档任务”

在 miss 路径中，模型看到的不是一句简单的“请总结”。客户端构造一条专门的虚拟用户消息，大意如下：

```text
CRITICAL：停止当前业务工作，只生成对话总结。

先输出 <analysis>，按时间检查用户要求、技术决定、文件、错误和反馈；
再输出 <summary>，按照固定九段结构生成可继续工作的交接文档。

不得调用工具。
```

这条提示有三层控制。

### 1. 强制停止干活

模型刚刚可能连续执行了几十轮工具调用，最自然的倾向是“再检查一下文件”。但 compact 的目标是减少上下文，再调用工具只会继续增加消息。

因此客户端不仅在提示词中反复禁止工具，运行权限层也固定拒绝 compact 期间的工具调用。提示词负责引导，权限层负责兜底。

### 2. 先梳理，再交接

模型必须先输出 `<analysis>`，按时间检查哪些内容对后续工作重要，然后再输出 `<summary>`。

这里的 `<analysis>` 是客户端提示词规定的文本格式，不等于模型 API 的原生 thinking 开关。

客户端收到结果后会：

```text
<analysis>...</analysis>   -> 删除
<summary>...</summary>     -> 改写为后续上下文中的 Summary
```

因此，下一次模型请求不会携带这段用于整理的 analysis，只保留正式交接内容。

### 3. 用九段结构防止漏掉工程状态

| Summary 段落 | 它试图保住什么 |
| --- | --- |
| Primary Request and Intent | 用户最终想完成什么 |
| Key Technical Concepts | 后续工作依赖的技术模型 |
| Files and Code Sections | 重要文件、代码和修改原因 |
| Errors and Fixes | 已遇到的错误以及修复方式 |
| Problem Solving | 已解决和仍在排查的问题 |
| All User Messages | 用户反馈和需求变化 |
| Pending Tasks | 明确未完成的任务 |
| Current Work | compact 前正在做什么 |
| Optional Next Step | 紧贴最近请求的下一步 |

安全相关约束要求逐字保留；如果确实存在下一步，还要直接引用最近任务，降低总结导致的方向漂移。

## 第三步：客户端不会只留下 Summary

如果 compact 只留下模型生成的 Summary，压缩率会很高，但可靠性不够。

原因很直接：摘要擅长表达“为什么这样做”，却不保证逐字符保留代码、配置值、测试输出、工具调用关系和当前运行环境。

所以客户端会把上下文重建成下面的结构：

![Compact 前的长历史被重建为 Summary、近期消息、精确附件和运行状态](visuals/compact-rebuilt-context.svg)

### Summary：保存远期语义

Summary 负责把很久以前的讨论压缩成可以交接的任务说明：目标、决定、错误、文件关系、用户反馈和待办。

它的优点是压缩率高；缺点是有损。

### MessagesToKeep / MessagesToPreserve：保存近期因果

这里必须先区分 compact 入口，不能只看到某个底层函数的 `messagesToKeep` 就反推用户命令：

| 路径 | 被总结的范围 | 保留的旧消息内容与因果关系 | 返回结构 |
| --- | --- | --- | --- |
| 当前 `/compact` slash command | 较早的合法 group | 至少最后 1 个合法 group；prompt-too-long 时自适应多保留 | `nFa -> vmi -> Smi`，最终 `messagesToKeep` 非空 |
| manual precomputed hit | 预计算时选定的较早 group | 预计算 preserve UUID + 预计算之后的 `messagesSince` | `_Ev -> Smi` |
| reactive auto / prompt-too-long | 自适应选择的较早 group | 为满足窗口而保留的后缀 group | `messagesToPreserve` |
| cold/full auto 或特定 SDK full compact | 当前全部活跃历史 | 无 | `iyi()` 返回 `messagesToKeep: []` |
| partial/message-selector compact | 选择器指定的一侧 | 另一侧的合法消息 | `messagesToKeep: m`，并写 preserved UUID |

当前 `/compact` 和 reactive/partial 路径不会机械地保留“最后 N 条消息”，而是先按合法消息组划分历史。

例如一个 `tool_result` 不能脱离对应的 `tool_use` 单独存在。否则下一次 API 请求虽然更短，却会变成结构不合法或因果不完整的历史。

MessagesToKeep/MessagesToPreserve 因此负责保留完整因果组：刚才调用了什么工具、返回了什么、模型最后作出了什么判断。只有 cold/full auto 或特定 SDK full compact 走 `iyi()` 时才明确返回空的 `messagesToKeep`，其连续性主要依靠 Summary、重新生成的 Attachments、hooks 和下一条用户输入。

“保留完整因果组”不等于 JavaScript 对象逐字段原封不动。进入 rebuilt context 前，客户端对保留区执行 `messagesToPreserve.map(tNt)`：非 assistant 消息不改；assistant 消息保留内容、UUID 和 `tool_use` 关系，但把四个 usage token 计数字段清零。可直接确认的效果是近期工作现场仍存在，而 rebuilt context 中这些 usage 字段不再保留旧值；代码没有在这里说明更高层计费意图。证据见可读 JS 232865、232883-232885。

### Attachments：恢复精确信息

客户端重新读取最近相关文件，而不是要求 Summary 凭记忆复述所有代码。

`2.1.235` 的文件恢复限制是：

- 最多 5 个文件；
- 每个文件最多 5,000 token；
- 所有恢复文件合计最多 50,000 token。

除了文件，客户端还会重新组装当前任务需要的状态，例如：

- Plan 文件；
- 已调用 Skills；
- MCP instructions；
- Agent 和命令上下文；
- plan mode 状态；
- compact 场景的 SessionStart hook result。

这解释了为什么 Summary 和附件会出现部分重复：

```text
Summary 用低精度、高压缩率保存“理解”；
Attachments 用高精度、受限长度保存“材料”。
```

这种重复不是为了让消息结构看起来简洁，而是用一部分 token 换取任务连续性。

## 第四步：客户端写入 compact boundary

新上下文准备完成后，Claude Code 会向 transcript 追加 `system/compact_boundary`。

它不是给模型阅读的普通总结，而是一条恢复元数据，记录：

- compact 的触发来源；
- compact 前后的 token；
- 多次 compact 累计替代的 token；
- 本次耗时；
- 是否使用预计算结果；
- 被保留消息的 UUID（当前 `/compact` 会写）；
- 保留片段的 head、anchor 和 tail；
- compact 前已经发现的延迟工具。

Resume 重新读取 JSONL 时，会根据 boundary 重建逻辑消息视图：

```text
物理 transcript：仍然保存旧事件、boundary 和新事件
当前 /compact 的模型逻辑历史：Summary + 保留消息 + Attachments/Hooks + compact 后的新消息
cold/full compact 的模型逻辑历史：Summary + Attachments/Hooks + compact 后的新消息
```

所以 compact 不是把磁盘上的旧会话彻底删除，而是改变“下一次送给模型的有效历史表示”。

同版本运行 Probe 已验证：手动 `/compact` 会产生 `system:compact_boundary`；后续 fork 保留 compact summary 和当前 prompt，但不再发送 compact 前的旧 prompt、旧 tool-use ID 和旧 assistant result。

## 第五步：下一次模型请求继续工作

当前 `/compact` 成功后，模型下一次看到的是：

1. 正常 system prompt 和当前动态上下文；
2. compact summary；
3. 保留的近期合法消息组；
4. 最近文件和运行状态附件；
5. compact 场景的 hook 结果与用户后续输入。

若 manual 命中 precomputed result，保留区还包括预计算点之后新增的 `messagesSince`。只有 cold/full auto 或特定 SDK full compact 不带 preserved suffix。

模型不需要知道客户端内部经历了多少次重试。对它而言，这是一段更短、但仍然包含任务目标、最近现场和精确材料的历史。

这就是用户感觉“压缩完还能接着干”的根本原因。

## 需要新 summary request 时，如果总结失败会发生什么

这一节只适用于 miss、reactive 或其他确实需要发起新 summary request 的路径。已经校验通过的 precomputed hit 不发送这次请求，因此也不会进入“本轮总结请求失败”的分支。

![Compact 失败后会缩短待总结前缀、剥离媒体、切换模型或停止重复自动压缩](visuals/compact-recovery.svg)

| 问题 | 客户端怎样调整 | 最终结果 |
| --- | --- | --- |
| PreCompact hook 阻止 | 不绕过 hook，也不写成功 boundary | 保留原历史，等待用户处理 |
| 总结请求 prompt-too-long | 增加按内容和因果关系保留的尾部消息组，缩短待总结前缀 | 自适应重试，耗尽后失败 |
| 媒体内容过大 | 首次命中时剥离非必要媒体 | 使用文本为主的输入重试 |
| 当前总结模型不可用 | 选择策略允许的 fallback model | 用下一模型重新总结 |
| 预计算结果已经过期 | 拒绝旧 sidecar | 重新执行普通总结 |
| Compact 后窗口连续快速回填 | 触发 rapid-refill breaker | 停止浪费自动 compact 调用 |

无论 compact 成功还是失败，它都不能撤销已经发生的外部动作。文件修改、远端请求和工具副作用仍然存在。

## 自动 Compact 和预计算是怎样加入这条主线的

手动 `/compact` 讲清楚以后，其他入口只是改变“何时进入同一套总结和重建流程”。

### Auto-compact

客户端根据模型窗口和有效输入预算计算多条线：

```text
compact_line    = input_budget - 13,000
precompute_line = min(input_budget - input_budget * precompute_fraction,
                      compact_line)
warn_line       = compact_line - 20,000
blocked_line    = model_input_ceiling - 3,000
```

前三条线使用配置后的 auto-compact effective window；`blocked_line` 使用模型原始输入 ceiling，独立于更小的 auto-compact window。达到 warning line 时提醒，达到 compact line 时执行切换，接近 blocked line 时限制继续增长。具体数字会受模型窗口、输出预留、配置和远程状态影响，不是固定百分比。

### Precomputed compact

到达 precompute line 后，客户端可以提前在后台生成 Summary，但不立即替换主历史。

真正需要 compact 时，客户端会检查：

- session 和 model 是否一致；
- 预计算时间是否过旧；
- 当时的边界 UUID 是否还在当前历史；
- 历史增长或缩减是否超限；
- 所有保留 UUID 是否仍然存在。

校验通过时直接换入预计算 Summary，不发送新的 summary request；否则丢弃旧结果并进入普通总结路径。这样可以把等待前移，又不会拿过期交接文档覆盖已经变化的任务。

持久 sidecar 只接受 `agentKey=main`。进程内 registry 则按 agent key 保存，fork/subagent 可以通过 `precomputeSourceKey` 借用另一个 Agent 的结果：借用 pending 项会等待，turn abort 时保留原 entry；借用成功不会消费源 entry。只有读取自己的 entry 才会从 registry 移除并清理对应 sidecar。这是“谁拥有、谁消费”的协议，不是所有 Agent 共用一个会被第一次读取删除的全局缓存。

### Reactive compact

如果普通模型请求已经遇到 prompt-too-long，Agent Loop 会进入 reactive compact。它按 token 缺口调整需要总结和保留的消息组，再进入“Summary + preserved suffix + Boundary”路径。当前手动 `/compact` 复用了同一个 group-based summarizer，但 trigger、precompute reuse 和等待时机不同。

## Compact 带来的实际取舍

| 维度 | 收益 | 代价 | 客户端的补偿 |
| --- | --- | --- | --- |
| 回答质量 | 长任务可以继续 | Summary 可能遗漏细节 | 近期消息和精确附件 |
| 延迟 | 后续请求输入更短 | Compact 增加一次总结调用 | 后台预计算和 fallback |
| Token/费用 | 后续多轮不再重复完整历史 | 总结和恢复附件本身也消耗 token | 阈值、文件总量和 refill 熔断 |
| 恢复 | Resume 能从 boundary 接续 | 进程内 REPL 状态可能被清空 | 明确提示重新定义变量 |
| 外部副作用 | 不影响已完成工作 | 无法通过 compact 回滚错误动作 | 依赖工具幂等、审批和补偿流程 |

## 最后只记住五件事

1. `/compact` 是客户端编排的一次历史表示切换，不是简单删除旧消息。
2. Precomputed hit 不发送新的 summary request；miss 才构造交接任务并处理总结失败。
3. Summary 保存远期语义，但它是有损的；当前手动路径还保留合法后缀组。
4. 文件、Plan、Skills、MCP 和 hooks 用受限附件补回精确信息；cold/full 路径不一定保留旧消息后缀。
5. Compact boundary 让 transcript、resume 和 fork 知道怎样使用新历史；preserved 字段取决于实际 compact 路径。

## 可执行的事实校验合同

后续版本或重做文档时，至少同时验证以下五个断言，任何一个失败都不能继续写成同一条 compact 主线：

| 断言 | `2.1.235` 证据 |
| --- | --- |
| `/compact` 的实际 slash-command 入口走 group compactor | `gEv -> yEv -> nFa -> vmi -> Smi`，见 331301-331367、232845-232876 |
| 当前 `/compact` 至少保留一个合法 group | `vmi()` 从 `s=1` 开始，成功结果含 `messagesToPreserve: m.flat()`，见 262247-262294 |
| cold/full auto 或 SDK full compact 不保留旧消息 | `iyi()` 返回 `messagesToKeep: []`，见 263020-263036、263375-263414、290267 |
| partial compact 保留选择器另一侧 | `qof()` 返回 `messagesToKeep: m`，并调用 `iFa()` 编码 preserved UUID，见 263048-263087 |
| exact-binary manual Probe 案例省略了指定旧结构历史 | 该案例的 fork request 不含指定的 pre-compact prompt、tool-use ID 和旧 assistant result，但含 Summary 与当前 prompt；它不证明所有 manual compact 都没有 preserved messages |

## 源码与运行证据

这一节用于核对结论，不是理解主线的前置阅读。

| 机制 | `reverse/javascript/cli.readable.js` 定位或 Probe |
| --- | --- |
| Summary 模板、九段结构、双标签和 analysis 删除 | 261931-262207 |
| Compact 总结调用与输出处理 | 262209-262235、263099-263170 |
| 合法消息分组、prompt-too-long 和媒体重试（reactive） | 262237-262294 |
| 预计算 sidecar 与 rehydrate 校验 | 262425-262585；`context.precomputed-compact-rehydrate` |
| `/compact` slash-command、manual precompute reuse 与 group summarizer | 331301-331367、232845-232876 |
| cold/full auto 的 `messagesToKeep: []` 与 partial compact 的 `messagesToKeep: m` | 262992-263087、263375-263414 |
| Tool deny、fallback 和附件恢复 | 263099-263190 |
| 文件及 Skill token 限制常量 | 263275 附近 |
| Boundary 字段编解码和累计 dropped token | 211531-212001 |
| Reactive compact 成功写 boundary 和遥测 | 232816-232876 |
| Auto-compact 阈值 | 216096-216175；`context.autocompact-thresholds` |
| 快速回填熔断 | 271657-271659；`resilience.rapid-refill-breaker` |
| 同版本手动 compact Probe | `analysis/runtime-probes/agent-loop-tool-result-resume.json`；`probe.manual-compaction-boundary` |

上下文装配、prompt cache、tool search、context hint 和 microcompaction 见[上下文治理与多层缓存](context-governance-and-caching.md)；消息 UUID、checkpoint、resume 和 fork 见[会话、检查点与记忆](sessions-checkpoints-memory.md)。

图表源文件位于 `analysis/visuals/compact-*.dot`，通过 Graphviz 确定性生成对应 SVG。
