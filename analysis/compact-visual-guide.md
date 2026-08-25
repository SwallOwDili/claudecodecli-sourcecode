# Claude Code 2.1.235 的 `/compact` 到底做了什么

`/compact` 改变的是 Claude Code 下一次发给模型的对话，不是工作区里的代码，也不是已经执行过的命令。

下面直接看一次 Claude Code 会话。任务就是分析 `/compact` 自己，不引入其他业务例子。

## 压缩前：模型和客户端已经来回执行了很多轮

用户在 Claude Code 中输入：

```text
找出 Claude Code 2.1.235 执行 /compact 后发生了什么。
必须确认四件事：Summary 怎样生成、近期消息是否保留、文件怎样补回、Resume 怎样接续。
```

模型不能直接回答。它先让客户端搜索发布 bundle：

```text
assistant:
  tool_use(id=grep-compact, Grep)
  pattern: "CRITICAL: Respond with TEXT ONLY|compact_boundary|messagesToPreserve"
  path: reverse/javascript/cli.readable.js
```

Claude Code 客户端执行 `Grep`，再把结果作为同 ID 的工具结果放回消息历史：

```text
user:
  tool_result(tool_use_id=grep-compact)

  261902  CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.
  261933  t2 = t2.replace(/<analysis>...<\/analysis>/, "")
  262271  messagesToPreserve: m.flat()
  263175  async function wmi(...)
  399359  subtype: "compact_boundary"
```

模型接着读取 Summary 提示词和解析器：

```text
assistant:
  tool_use(id=read-summary, Read)
  file_path: reverse/javascript/cli.readable.js
  offset: 261901
  limit: 160
```

工具返回的源码片段中包含：

```js
CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.
Your entire response must be plain text:
an <analysis> block followed by a <summary> block.

function IzS(text) {
  text = text.replace(/<analysis>[\s\S]*?<\/analysis>/, "");
  // 匹配到 <summary> 时改写成 Summary: ...
}
```

到这里，模型只能证明“客户端会要求生成 Summary，并尝试删除 analysis”。它还没有证明 Summary 之外保留了什么。

用户继续纠正：

```text
不要只分析提示词。继续确认当前手动 /compact 是否保留 tool_use/tool_result，
压缩后会重新读取哪些文件，以及 compact_boundary 如何参与 Resume。
```

模型又发起多次工具调用：

```text
Read 232845-232885  -> manual/reactive group compactor 与 finalize
Read 262247-262294  -> 合法消息分组和 messagesToPreserve
Read 263175-263235  -> 最近文件、Plan、Skills、MCP 与 Hook 附件
Read 211993-212001  -> compact_boundary 的序列化字段
Read analysis/runtime-probes/agent-loop-tool-result-resume.json
                    -> /compact、fork 和 resume 的真实请求变化
Bash python3 skill/claude-code-version-diff/scripts/validate_snapshot.py .
                    -> snapshot validation: PASS
```

每次 `Read` 都会把源码正文变成 `tool_result`，每次验证都会把输出放回下一轮请求。加上用户纠正、模型判断和其他上下文，这条会话会越来越长。

此刻任务状态是：

- Summary 提示词和双标签解析已经确认；
- 手动 `/compact` 的合法消息分组已经确认；
- 最近文件恢复的 `5 / 5,000 / 50,000 token` 限制已经确认；
- Boundary 字段和同版本 Probe 已经找到；
- 还需要把这些证据整理成一篇准确说明。

用户这时输入：

```text
/compact 保留用户的两次要求、关键源码位置、Probe 结果和剩余写作任务
```

## 压缩后：下一次模型实际拿到什么

`/compact` 完成后，客户端不会把上面所有搜索结果、源码片段和验证输出原样再次发给模型。

下面是基于 `2.1.235` 客户端规则构造的说明性结果。Summary 的具体措辞由模型生成，保留多少近期消息也取决于本次切点；它不是固定 wire dump。

### 改变输入，亲自观察这次重建

下面的沙盘不会播放一条固定动画，范围明确限定为普通手动 `/compact` 且 precomputed miss，因此会真实走一次 Summary 请求；precomputed hit 仍由后文单独解释。输入参数会改变 Summary 的强调项和附件候选，消息组数量与保留数量会改变切点，附件恢复状态会改变重建后的精确材料；如果 `PreCompact` 阻止，客户端会停在原历史，不写成功 Boundary。每一步都标明执行 owner、证据类型和当前高亮的客户端阶段。

<div class="cc-agent-lab-embed">
<cc-agent-lab scenario="compact" heading-level="4"><div class="cc-agent-lab-fallback"><strong>静态回退：</strong>当前浏览器没有运行交互组件。下文仍按同一顺序完整保留 Summary、preserved messages、attachments、Boundary、恢复分支和三张静态流程图。</div></cc-agent-lab>
</div>

### 较早内容变成一段新文本

本例可能生成这样的 Summary：

```text
Summary:

1. Primary Request and Intent:
   解释 Claude Code 2.1.235 的 /compact。
   必须覆盖 Summary、近期消息、文件恢复和 Resume。

2. Key Technical Concepts:
   manual compact miss、合法消息 group、preserved messages、
   attachment、compact_boundary、逻辑消息视图。

3. Files and Code Sections:
   cli.readable.js 261901-262207：Summary prompt 与标签解析。
   cli.readable.js 262247-262294：group compactor。
   cli.readable.js 263175-263235：附件恢复。
   cli.readable.js 211993-212001：Boundary 字段。

4. Errors and Fixes:
   最初只分析了 Summary prompt；用户指出还必须验证近期消息、附件和 Resume。
   随后补读 group compactor、附件和 Boundary 路径。

5. Problem Solving:
   已确认 compact 不是只留一段摘要，而是重建下一次请求使用的历史。

6. All User Messages:
   用户先要求解释四部分，随后纠正“不要只分析提示词”。

7. Pending Tasks:
   把证据写成读者可理解的文章，并保留精确阈值和失败边界。

8. Current Work:
   源码与 Probe 已核验，文章尚未完成。

9. Optional Next Step:
   按客户端真实顺序写完 /compact 专题并运行验证。
```

这段新文本在实现中叫 compact Summary。九个标题来自客户端提示词；具体句子不是固定输出。

Errors and Fixes、Problem Solving 会保留失败和用户纠正。因此真实机制并不是“识别失败版本，删掉失败，只留下成功”。它要把失败原因压缩成后续仍可使用的语义。

### 最近的完整消息可以继续保留

假设本次切点保留了最后两个消息组，下一次请求里还可能存在：

```text
assistant:
  tool_use(id=read-boundary, Read)
  file_path: reverse/javascript/cli.readable.js
  offset: 211993
  limit: 20

user:
  tool_result(tool_use_id=read-boundary)
  compact_metadata: trigger, pre_tokens, post_tokens,
  preserved_segment, preserved_messages ...

assistant:
  已确认 Boundary 保存前后 token 和 preserved UUID；
  下一步把它与 Resume 修链放进文章。
```

第一条 assistant 工具调用和紧随的 user 工具结果属于一个消息组；后面的 assistant 判断通常是下一个组。客户端不能只保留 `tool_result` 而丢掉同 ID 的 `tool_use`，否则工具因果关系不合法。

这些没有被 Summary 改写、仍以原内容进入新上下文的近期消息，叫 preserved messages。当前 manual `/compact` 至少从保留最后一个合法组开始，但不保证固定保留最后 N 条，也不保证上面两个组每次都会同时留下。

### 最近使用的文件可以被重新装入

客户端会从最近文件集合中重新装入有限的精确材料。如果 `reverse/javascript/cli.readable.js` 进入恢复集合，模型会再次获得受限长度的文件内容，而不必完全依赖 Summary 复述源码。

这种压缩后重新加入的精确材料属于 attachment。`2.1.235` 最多恢复 5 个最近文件；每个文件最多 5,000 token，恢复文件合计最多 50,000 token。文件未被选中、超过预算或读取失败时，不能假装它已经被精确补回。

### Boundary 留在本地会话记录中

Compact 成功后，客户端还会向本地 JSONL transcript 追加 `system/compact_boundary`。简化后可以这样理解：

```text
compact_boundary:
  trigger: manual
  pre_tokens: 压缩前 token
  post_tokens: 压缩后 token
  preserved_messages: 被保留消息的 UUID
```

Boundary 不是第二份 Summary，也不是普通业务内容。它告诉后续 Resume：较早历史已经由 Summary 替代，哪些近期消息仍要接回新链。

## 为什么压缩后还能继续分析 `/compact`

下一轮模型现在掌握四类信息：

- 从 Summary 得知用户两次要求、已确认事实和剩余写作任务；
- 从 preserved messages 得到近期 Read 的精确输入、结果和判断；
- 从 attachment 重新取得仍需引用的源码材料；
- 从 compact 后的新输入得知接下来要继续完成什么。

所以 `/compact` 不是“把全部聊天压成一段摘要”。在当前手动路径中，它总结较早内容，保留部分近期完整消息，再补回仍需使用的精确文件。

![普通手动 compact 会总结较早历史、保留近期因果、恢复精确材料并写入边界](visuals/compact-lifecycle.svg)

## 客户端怎样完成这次切换

上面的例子已经展示了输入和结果。现在再看内部顺序。

### 先找一个不会拆散工具调用的切点

客户端运行 `PreCompact` hook。本例假设 Hook 放行，并且当前没有可复用的预计算结果。

随后客户端按合法消息组切分历史：较早组交给模型总结，近期组留在新上下文中。当前 manual 路径至少从保留最后一个合法组开始；如果 Summary 请求仍然超窗，它会多保留一些尾部组，缩短待总结前缀，再次尝试。

Preserved assistant message 的内容、UUID 和工具因果会保留，但四项旧 usage 计数会清零。因此“保留”指消息语义与关系继续存在，不是 JavaScript 对象每个字段逐字节不变。

### 总结请求只能生成文本，不能继续干活

客户端在待总结前缀末尾加入一条虚拟用户消息，核心要求是：

```text
CRITICAL：停止当前业务工作，只生成对话总结。

不要调用 Read、Bash、Grep、Glob、Edit、Write 或任何其他工具。
先输出 <analysis>，按时间检查要求、文件、决定、错误和反馈；
再输出 <summary>，形成可继续工作的工程交接内容。
```

这次请求只允许一轮模型决策，工具权限函数固定返回 deny。模型不可用且策略允许时，客户端沿 fallback chain 重试；这里不存在一套永远固定的“模型 A 写代码、模型 B 管上下文”。

提示词要求先写 `<analysis>`、再写 `<summary>`。解析器匹配到标签时会删除 analysis，把 summary 改写成后续上下文里的 `Summary:`。这不是严格的结构化输出 schema：若模型返回非空文本却缺少完整标签，当前路径仍可能接受整段文本。

### Summary、近期消息和附件被重新组装

客户端把模型生成的 Summary、选中的近期消息组、最近文件与当前任务状态组装成新的有效上下文。Summary 保存较早语义，近期消息保存刚发生的精确因果，附件补回当前材料。

几部分出现重复并非错误。例如 Summary 会记录某个函数和行号，attachment 里也可能再次出现同一段源码。前者保证任务含义仍在，后者保证精确代码不完全依赖模型复述。

![Compact 前的长历史被重建为 Summary、近期消息、精确附件和后续输入](visuals/compact-rebuilt-context.svg)

### Boundary 让 Resume 采用新历史

下一次模型请求使用的是：

```text
Summary + preserved messages + attachments/hooks + compact 后的新输入
```

本地 transcript 则仍能记录 compact 前事件、Summary、Boundary 和之后的新事件。Resume 读取 JSONL 时不会把所有物理行原样塞回模型，而是按 Boundary 中的保留关系重建逻辑消息链。

如果 Summary 漏了更早的精确片段，客户端会在路径可用时把完整 transcript 路径告诉模型；模型需要主动 `Read`。这是沿明确路径补查，不是客户端发现“记忆缺失”后自动搜索一个外部语义记忆库。

## 预计算只是把 Summary 提前写好

上下文到达 precompute line 后，客户端可以在后台对当时的历史预写 Summary，但不立即替换主历史。当前进程中的 ready result 命中时，客户端确认预计算点仍在当前历史，再把之后的新消息作为 `messagesSince` 接入保留区。

因此 precomputed hit 在**这一次 compact**不发新的 Summary 请求；模型调用只是提前发生。若用户给 `/compact` 加了新 instructions、Hook 追加了新要求，或预计算点已不在当前历史，客户端放弃复用，回到前面讲过的普通路径。

磁盘 sidecar 在重新装入内存前还会检查 session、model、7 天期限、150,000 token 增长、缩减一半和 preserve UUID。Sidecar 记录 CLI version，但 `2.1.235` 不会仅因 CLI version mismatch 拒绝复用。

## 自动触发线怎样算出来

手动 `/compact` 可以随时执行。自动路径必须先给模型输出留位置，再给“提前生成、提醒用户、执行 compact、最终阻断”留出不同缓冲。

以 200k 窗口为例，先预留最多 20k 输出，本例真正可用于输入判断的 budget/ceiling 是 180k：

```text
input budget = 200k - 20k = 180k
precompute   = 180k - 20% = 144k
compact      = 180k - 13k = 167k
warn         = 167k - 20k = 147k
blocked      = 180k model input ceiling - 3k = 177k
```

| 线 | Token | 客户端动作 |
| --- | ---: | --- |
| precompute | 144k | 后台准备 Summary，主历史暂不切换 |
| warn | 147k | UI 开始提示余量 |
| compact | 167k | 触发自动 compact |
| blocked | 177k | 阻止继续无界增加输入 |

这些数字只属于这个算例。模型窗口、输出预算、设置和远程 precompute 配置都会改变结果；源码没有固定 T1-T5，也没有 30%、60%、75%、90% 四档。这里的 20k 是 auto-window 输出预留上限，不是 Summary 的固定输出上限。

## 失败时为什么不会留下半份新历史

只有 Summary、保留区、附件和 Boundary 完成组装，新的有效上下文才正式接管。

![Summary 超窗时调整分组，模型不可用时 fallback，附件失败时降级；只有有效上下文形成后才写 Boundary](visuals/compact-recovery.svg)

| 失败 | 客户端怎样处理 | 结果 |
| --- | --- | --- |
| `PreCompact` 阻止 | 保留原历史，不绕过 Hook | 不写成功 Boundary |
| Summary 请求超窗 | 多保留尾部消息组，缩短待总结前缀 | 自适应重试，耗尽后失败 |
| 当前模型不可用 | 沿允许的 fallback chain 切换 | 用下一模型重新总结 |
| 当前 manual/reactive 附件恢复失败 | 记录错误并使用仍能取得的材料 | 可能继续，但精确材料减少 |

失败时最重要的合同是：成功的新上下文和 Boundary 尚未形成，原 active history 就仍然有效。

无论 compact 成功还是失败，它都不能撤销文件修改、`git push`、数据库写入、MCP 写操作或远端 API 请求。Compact 改变的是模型以后看到的逻辑消息，不是外部系统的事务状态。

## 回到这次 Claude Code 源码分析

Compact 之后，模型继续任务时仍然知道：用户要求解释 Summary、近期消息、文件恢复和 Resume；最初只看提示词是不够的；关键源码范围和 Probe 已经找到；下一步是把这些事实写清楚并验证。

这些信息并非来自一份万能摘要。较早的要求与纠正由 Summary 承接，最近的工具因果由 preserved messages 保留，当前源码由 attachment 补回，Boundary 则让下一次请求和 Resume 知道从哪份短历史继续。

这就是 `2.1.235` 的 `/compact`：**模型负责把较早经历写成有损文本，客户端负责选择合法切点、保留近期因果、重装精确材料并记录历史切换。**

<details>
<summary>源码与运行证据</summary>

| 机制 | `reverse/javascript/cli.readable.js` 定位或 Probe |
| --- | --- |
| Auto threshold 与 effective window | 216095-216245；`context.autocompact-thresholds` |
| Summary 模板、九段结构与双标签解析 | 261901-262207 |
| Group summarizer、token-gap retry 与 preserved suffix | 262209-262294 |
| Precomputed 生成、校验与 `messagesSince` | 262320-262680 |
| Tool deny、模型 fallback 和附件恢复 | 263099-263235 |
| Manual slash command 与 finalize/Boundary | 331301-331367、232845-232876 |
| Boundary 字段与累计 dropped token | 211531-212001 |
| 同版本 manual compact、fork 与 resume Probe | `analysis/runtime-probes/agent-loop-tool-result-resume.json`；`probe.manual-compaction-boundary` |

普通 manual miss 的调用主线是 `gEv -> yEv -> nFa -> vmi -> Smi`。`vmi()` 从至少保留一个合法消息组开始；`Smi()` 负责恢复附件、运行 compact hook、生成 Boundary 并产出新的 active view。

实现边界：manual/reactive 的 Summary 超窗会扩大 preserved suffix；full/partial 使用另一套最多 3 次的截断重试。Auto compact 连续失败 3 次会跳过本 session 后续 auto 尝试；compact 后少于 3 turns 又连续第 3 次触线会触发 rapid-refill breaker。这些保护都不禁止用户手动 `/compact`。

Prompt cache、Tool Search、context hint 与 microcompaction 是相邻但不同的问题，见[上下文治理与多层缓存](context-governance-and-caching.md)；UUID、checkpoint、resume、fork 和 Memory 见[会话、检查点与记忆](sessions-checkpoints-memory.md)。

</details>

图表源文件位于 `analysis/visuals/compact-*.dot`，通过 Graphviz 确定性生成对应 SVG。
