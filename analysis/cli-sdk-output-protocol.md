# Claude Code 2.1.235 CLI、SDK 与输出协议

> **版本边界：** 本文只解释仓库中 Claude Code CLI `2.1.235` 的 CLI 帮助、bundle schema、可读化 JavaScript、生成清单与已有精确二进制 Probe。当前官网没有被用来补写本版行为。

## 先回答读者真正会遇到的问题

**读者问题：** 为什么同一个 Claude Code，直接运行时是 TUI，`-p` 时可以只打印一段文本，SDK 却能边收消息、边审批工具、边切模型，而且 `stream-json` 里的 `success`、`agent.message`、`control_response` 看起来像三套不同协议？

**一句话模型：** `2.1.235` 把同一个 Agent Loop 包在三种入口外面：TUI 持有本地交互，`--print` 把一轮结果投影为 text/json/NDJSON，SDK 再在 NDJSON 上叠加带 `request_id` 的双向控制 RPC；消息流负责“观察发生了什么”，控制流负责“请求另一端改变或补充状态”。

![CLI、SDK 与 stream-json 从输入、初始化、Agent Loop、观察消息、双向控制到最终 result 的生命周期](visuals/cli-sdk-protocol-lifecycle.svg)

图的结论：`result` 是一轮结束信号，不是整个输出协议；`control_response` 是某个 RPC 的答复，不是模型回答；SDK host 与 CLI worker 可以同时成为 request 的发起方。

## 60 秒模型

贯穿场景：一个自动化程序恢复已有会话，要求 Claude 检查仓库；模型先输出文字，再请求 `Read`。SDK host 收到 `can_use_tool`，批准后 CLI 执行工具并继续模型轮次，最终产出符合 JSON Schema 的对象。

| 对象 | 之前 | 转换 | 之后 | 用户可见效果 |
| --- | --- | --- | --- | --- |
| 入口 | SDK 调用参数 | SDK 启动 CLI 子进程并固定 `stream-json + verbose` | stdin/stdout 成为 NDJSON 双工通道 | 调用方不需要解析 TUI |
| 会话 | 一个 session ID 或 resume 条件 | CLI 重建 transcript；`fork` 时派生新 session ID | 同一逻辑历史或新的 fork 身份 | 可以续接，也可以从现场另开分支 |
| 配置 | SDK options | `initialize` 传 hooks、MCP、schema、agents、skills 等 | worker 返回模型、命令、账户、权限模式和能力 | host 知道可用表面并能渲染控件 |
| 工具审批 | Agent Loop 等待决定 | CLI 发 `can_use_tool`，host 用相同 `request_id` 回答 | allow/deny 进入工具管线 | 本地没有 TUI 也能审批 |
| 内容 | 模型正在流式生成 | 可选 `stream_event` 增量 + 完整 assistant 消息 | 消费者得到预览和权威完整消息 | 可以实时显示且能在回撤时修正 |
| 结构化结果 | JSON Schema | 注入 `StructuredOutput` 工具并校验调用输入 | `result.structured_output` 或重试耗尽错误 | 调用方拿到对象而不是再解析自然语言 |
| 终态 | Agent Loop 尚未结束 | 每轮恰好一个 `result` | `success` 或四类 error subtype | `is_error` 决定进程退出码 |

## 三个协议面不能混在一起

| 协议面 | 载体 | 方向 | 状态所有者 | 本文证据 |
| --- | --- | --- | --- | --- |
| 本地 CLI 输出 | stdout 文本、单个 JSON 或 NDJSON | CLI -> 调用者 | CLI 的本轮 Agent Loop | CLI 选项与 `runHeadless` 分支 |
| SDK control channel | NDJSON 中的 `control_request/response/cancel` | 双向 | request 发起者持有 pending；接收者持有处理中的 abort | control schema、Query 类、worker handler |
| Managed Agents session event | HTTP list/SSE event | client -> service 或 service -> client | 远端 session/thread orchestration | bundle 内 SDK parser、tool runner与随包文档 |

`analysis/source-inventory/output-protocol-event-identifiers.txt` 的 44 项属于第三行的远端事件词汇。它们不是本地 `--output-format=stream-json` 的 44 种 stdout frame。把两者合并会导致错误的 parser、错误的重连语义和错误的状态归属。

## 入口与格式矩阵

### 交互模式与 `--print`

- 默认入口是交互 TUI；`-p/--print` 打印响应后退出。
- 该版帮助明确说明：非交互入口会跳过 workspace trust 对话；无效 settings 在该模式下没有对话框，可能被静默忽略。因此 `--print` 是自动化入口，不等于更严格的信任入口。
- SDK 不是第二套 Agent Loop。TypeScript SDK 启动同一个 CLI，并固定添加 `--output-format stream-json --verbose --input-format stream-json`。

### `input-format` 与 `output-format`

| 输入 | 输出 | 是否成立 | 实际行为 |
| --- | --- | --- | --- |
| `text` | `text` | 是，默认 | 最终成功文本或固定的人类错误短句 |
| `text` | `json` | 是 | 默认只输出最终 `result` 对象；`--verbose` 输出该轮收集的消息数组 |
| `text` | `stream-json` | 是，但必须 `--print --verbose` | 每个 stdout frame 一行 JSON |
| `stream-json` | `stream-json` | 是，但必须 `--print` | stdin/stdout 都保持为逐行 JSON；可多轮输入 |
| `stream-json` | `text/json` | 否 | 启动阶段直接报错并 exit 1 |
| 任意 | 其他字符串 | 否 | Commander choices 或启动校验拒绝 |

进一步约束：

- `--replay-user-messages` 需要 input/output 都是 `stream-json`。
- `--include-partial-messages`、`--forward-subagent-text` 需要 `--print + stream-json`；仅由内部条件隐式打开而用户没有显式传 flag 时，非法组合会被关闭而不是总是报错。
- `--prompt-suggestions` 只在 `--print + stream-json` 输出。
- `--sdk-url` 同时要求输入和输出为 `stream-json`，并有保留给 Remote Control worker 的 host 校验。
- `stream-json` 还要求 `--verbose`，否则在加载会话后、进入主循环前 exit 1。

### 三种输出的终态差异

`text` 只保留人类可读投影：成功打印 `result`，四类错误分别打印固定短句。`json` 保留 result 字段。`stream-json` 不再额外打印终态，因为 result 本身已经是一条 NDJSON frame。

不要只看 `subtype`：`subtype: "success"` 仍可能同时有 `is_error: true`，表示 API error 文本被装进 `result`。该版最终退出规则是 `result.is_error` 或永久 transport close 为 exit 1，否则 exit 0。

## 本地 stdout/stdin 的真实 envelope

### stdout

schema 把 stdout 定义为“一行一个 JSON object”，主要成员是：

| `type` | 作用 | 关键字段 | 是否需要答复 |
| --- | --- | --- | --- |
| `assistant` | 完整 assistant message | `message`, `uuid`, `session_id`, `parent_tool_use_id`, attribution/error 元数据 | 否 |
| `user` | CLI 生成或 replay 的 user/tool_result message | `message`, `uuid`, `tool_use_result`, `tool_result_meta` | 否 |
| `stream_event` | Messages 流的增量事件 | `event`, `ttft_ms`, `uuid`, `session_id` | 否 |
| `system` | init、retry、task、hook、compact 等状态 | `subtype` + subtype 专属字段 | 否 |
| `tool_progress` | 工具/子 agent 进度 | tool ID/name、elapsed、retry | 否 |
| `result` | 一轮终态 | subtype、usage/cost、turns、result/errors | 否；是 turn-complete signal |
| `control_request` | CLI 向 host 请求决定/能力 | `request_id`, `request.subtype` | 通常需要一条 response |
| `control_response` | 回答 host 发来的 request | `response.request_id`, success/error | 已是答复 |
| `control_cancel_request` | 撤回自己发出的 pending request | `request_id` | cancel 本身无答复 |
| `keep_alive` | 长等待期间保活 | 无 payload | 忽略 |

另外还有 `auth_status`、`tool_use_summary`、`rate_limit_event`、`prompt_suggestion`、`conversation_reset`、`command_lifecycle`、`transcript_mirror`、`active_goal`、`autocompact_state`。这再次证明“89 subtype 清单”不是完整 stdout 类型表。

### stdin

stdin schema允许 user message、内部 `bash_command`、双向 control frames、`update_environment_variables`、`queued_notification` 和 `session_notice`。`initialize` 通常是第一条，但不是强制；第一条 user message 可以用默认值完成初始化。后到的 `initialize` 会返回当前状态，标题、SDK MCP server 与进度摘要仍可处理，但 system prompt/hooks/agents/skills 等一次性配置不会再次应用。

输入流关闭的语义是“让 CLI 完成当前 turn 后退出”，不是立即 kill。SDK 在存在双向回调需求时会等到首个 result，再关闭子进程 stdin。

## Partial messages：实时预览不是简单透传

打开 `--include-partial-messages` 后，CLI 把底层 `message_start`、`content_block_*`、`message_delta`、`message_stop` 包成 `type: stream_event`。完整 assistant message仍是权威记录。

该版还维护 `message id` 与当前 block index。在 fallback、refusal 或 tombstone 回撤已经预览的内容时，它会合成缺失的 `content_block_stop`、`message_delta` 和 `message_stop`，把消费者看到的流闭合，再开始新的 message。否则 UI 会永久停留在“block 未结束”状态，或把被撤回的文字当成最终回答。

代价是 stdout 字节数、解析次数和 UI 状态复杂度增加；普通批处理应只读完整 assistant/result，需要低延迟预览时再打开 partial。

## Structured output：不是在最后做一次 JSON.parse

1. `--json-schema` 先解析为 JSON object；字符串、数组或无效 schema 在启动阶段失败。
2. CLI 用 AJV 校验 schema，本版拒绝过大的 schema，并尝试派生 strict schema，失败时回落非 strict。
3. CLI 创建名为 `StructuredOutput` 的内置工具，把用户 schema 作为 tool input schema，并提示模型必须在结尾调用一次。
4. 工具调用输入通过 schema 校验后，返回 `structured_output` attachment 且 `endsTurn: true`。
5. 最终 `result.structured_output` 取最后一个仍存活的 attachment；若 model fallback tombstone 回撤了对应 tool call，该 attachment 也被移除。
6. 默认最多允许 `5` 次结构化输出尝试；`MAX_STRUCTURED_OUTPUT_RETRIES` 可覆盖。耗尽后返回 `error_max_structured_output_retries`。

因此结构化输出会占用工具 schema、至少一次 tool call，并可能增加模型轮次、token、时延和费用。它保证的是工具输入通过本地 schema 校验，不证明业务语义正确。

## Session、resume 与 fork

| 操作 | session 身份 | 逻辑历史 | 进程状态 | usage/cost |
| --- | --- | --- | --- | --- |
| 新 `--session-id` | 指定或生成 | 新历史 | 新进程 | 本次 query 从零累计 |
| `--resume` / `--continue` | 复用 transcript 身份 | 从持久记录重建 | 不复活旧 socket/Promise/子进程 | 本次 query 重新累计 |
| `--fork-session` + resume | 新 session ID | 继承选择后的逻辑历史 | 新进程 | 新 query 累计 |

不存在或含糊的 resume 目标会 exit 1，不会静默变成新会话。fork 在恢复消息后改写 session 身份，并保留逻辑历史。已有精确二进制 Probe 已证明 resume 会注入旧 prompt/result，fork 会产生不同 session ID 并继承 compact summary；详见 [运行探针索引](runtime-probe-index.md)。

## Control request/response 生命周期

### 普通成功路径

1. 发起端生成在当前 in-flight 集合中唯一的 `request_id`。
2. 它先登记 pending resolver，再写出 `control_request`。
3. 接收端按 subtype 处理；需要长操作时可发 `control_request_progress`。
4. 接收端写一条 `control_response`，其中 `response.request_id` 必须相同，verdict 为 `success` 或 `error`。
5. 发起端移除 pending，成功时按 subtype response schema 校验 payload，失败时 reject。

### 配对、重复与乱序

- SDK host 允许 response 比 waiter 更早到达：先放入 unmatched map，稍后 `awaitControlResponse` 再领取。
- unmatched map 上限为 `1024`，超限淘汰最老项，防止错误/恶意 peer 无限占用内存。
- worker 对未知 request ID 不会错误地完成另一个 request；`can_use_tool` 还校验 response 的 tool name。
- 已解决 toolUseID 的重复 response 会忽略。
- `request_user_dialog` 的 `error` response 不被当作用户选择，dialog 保持 parked；只有 completed/cancelled 语义的成功 response 才结算。

### cancel、abort 与关闭

发起者 abort 时删除 pending 并发送 `control_cancel_request`。cancel 没有自己的 response；接收端可中止工作，也可能来不及中止并仍发回晚到 response。发起者已经停止等待，晚到 response 不应改变已结束状态。

关闭 transport 会 reject 所有 pending control/MCP promise，并终止或清理 callback。它只能恢复协议一致性，不能撤销已执行的文件写入、命令、网络请求或反馈上传。

### initialize 的特殊重连语义

`initialize` response 除普通 payload 外可带 `pending_permission_requests` 与 `pending_user_dialog_requests`。新 host 加入已经运行的 session 时据此重新挂载未完成对话；同一 request 还可能作为 live/replay frame 到达，消费者必须按 `request_id` 去重。

## 89 个 subtype 清单到底是什么

生成器的规则是扫描所有 `subtype: literal("...")` schema。结果精确为 89 个唯一字符串，但它混合了：

- **42 个 schema 化 control request subtype**；
- **`success/error` 两个 control response verdict**，其中 `success` 同时也是 result subtype；
- **46 个观察型 system/result subtype**。

所以数学关系是 `42 + 2 + 46 - 1(success 重叠) = 89`。清单名是历史命名，不能据此宣称“SDK 有 89 个 RPC”。

### 42 个 schema 化 control request

方向中的 `client` 指 SDK/远端 host -> CLI loop，`agent` 指 CLI loop -> host，`both` 指双向。状态栏写主要被修改或读取的对象。

| subtype | 方向 | 关键请求字段 | 成功响应/状态所有权 |
| --- | --- | --- | --- |
| `initialize` | client -> loop | hooks, sdkMcpServers, jsonSchema, prompts, agents, skills, supportedDialogKinds | worker session config；返回 commands/models/account/current mode |
| `interrupt` | client -> loop | reason, cancel_queued | 当前 turn/queue；可返回 still_queued/cancelled |
| `set_permission_mode` | client -> loop | mode, ultraplan | worker permission context；返回实际 mode |
| `set_model` | client -> loop | model, system_prompt | session model |
| `set_max_thinking_tokens` | client -> loop | max_thinking_tokens, thinking_display | session thinking override |
| `rename_session` | client -> loop | title | transcript/session metadata |
| `set_color` | client -> loop | color | session UI metadata；schema 存在，主 worker handler 未见对应分支 |
| `apply_flag_settings` | client -> loop | settings | flag settings layer |
| `get_settings` | client -> loop | 无 | 返回 effective/sources/applied/errors |
| `get_context_usage` | client -> loop | 无 | 返回分类 token、window、threshold、message breakdown |
| `get_session_cost` | client -> loop | 无 | 返回格式化 cost text |
| `get_usage` | client -> loop | 无 | experimental session/rate-limit usage |
| `get_binary_version` | client -> loop | 无 | 返回 version/buildTime |
| `list_models` | client -> loop | 无 | worker 可选 model catalog |
| `file_suggestions` | client -> loop | query | 返回 fuzzy path suggestions |
| `read_file` | client -> loop | path, max_bytes, encoding | 受 Read 权限约束；返回内容/绝对路径/截断标记 |
| `get_workspace_diff` | client -> loop | 无 | 返回 capped git diff 或 null |
| `get_plan` | client -> loop | 无 | 返回 exists/content/path，不创建 plan |
| `rewind_files` | client -> loop | user_message_id, dry_run | file checkpoint state；返回预览/恢复结果 |
| `seed_read_state` | client -> loop | path, mtime | Edit 前置 read cache |
| `set_cwd` | client -> loop | path, trust_accepted, trusted_directory | cwd/trust/transcript relocation；非 ok 保持 cwd |
| `register_repo_root` | client -> loop | directory, reload_* | working roots 与 CLAUDE.md/plugin/skill reload |
| `cancel_async_message` | client -> loop | message_uuid | command queue；返回 cancelled |
| `stop_task` | client -> loop | task_id | task registry，not-found/not-running 幂等成功 |
| `background_tasks` | client -> loop | optional tool_use_id | foreground task ownership；可返回 backgrounded |
| `mcp_status` | client -> loop | 无 | 返回 MCP connection snapshot |
| `mcp_set_servers` | client -> loop | servers | 动态 MCP set；返回 added/removed/errors |
| `mcp_reconnect` | client -> loop | serverName | MCP connection generation/cache |
| `mcp_toggle` | client -> loop | serverName, enabled | MCP enabled state |
| `set_mcp_permission_mode_override` | client -> loop | serverName, mode | per-server tighten-only permission override |
| `mcp_call` | client -> loop | tool, arguments, expiry/timeout/files | 可信 control channel 直接调用 MCP；无模型 turn/普通 permission prompt |
| `mcp_message` | both | server_name, JSON-RPC message | SDK-hosted MCP transport；响应含 mcp_response |
| `reload_plugins` | client -> loop | 无 | commands/agents/plugins/MCP generation |
| `reload_skills` | client -> loop | 无 | skill command list |
| `message_rated` | client -> loop | messageUuid, sentiment, surface, cleared | product feedback event state |
| `submit_feedback` | client -> loop | description, draft_id, attach_transcript 等 | feedback policy/upload；返回 ID 或 unavailable/failure reason |
| `can_use_tool` | loop -> client | tool/input/decision metadata/tool_use_id | host permission UI/callback；返回 allow/deny 与可选更新 |
| `hook_callback` | loop -> client | callback_id, input, tool_use_id | SDK host hook callback |
| `oauth_token_refresh` | loop -> client | 无 | host-owned OAuth credential；返回 accessToken/null |
| `host_auth_token_refresh` | loop -> client | 无 | host-owned provider credential；返回 authToken/materialUnchanged |
| `elicitation` | loop -> client | MCP server/message/mode/schema/display | host MCP elicitation UI；返回 accept/decline/cancel |
| `request_user_dialog` | loop -> client | dialog_kind, opaque payload, tool_use_id | host renderer；返回 completed/cancelled + opaque result |

### schema 清单之外的 16 个 worker 分支

实际 worker handler 还识别下列 string-only subtype：

`add_directory`, `channel_enable`, `claude_authenticate`, `claude_oauth_callback`, `claude_oauth_wait_for_completion`, `end_session`, `generate_session_title`, `mcp_authenticate`, `mcp_clear_auth`, `mcp_oauth_callback_url`, `poll_event`, `remote_control`, `rewind_conversation`, `side_question`, `stage_file`, `ultrareview_launch`。

它们证明“89 清单”甚至不是全部 control handler 表面。反过来，schema 中 `set_color` 没有出现在这条主 worker dispatch；因此本文不把 schema 存在升级为已执行证明。`2.1.235` 的静态事实是：schema 定义 42 个、主 worker 分支识别 51 个、两者并集 58 个；不同 transport/capability 仍决定可达性。

### 46 个观察型 subtype

| 类别 | subtype 与关键字段 | 状态归属 |
| --- | --- | --- |
| 启动/会话 | `init`(version/cwd/tools/models/capabilities), `status`, `session_state_changed`, `worker_shutting_down`, `commands_changed`, `turn_duration` | worker 与当前 turn |
| compact/总结 | `compact_boundary`(metadata/logical parent), `post_turn_summary`, `away_summary`, `task_summary` | transcript/message graph 或展示摘要 |
| API/模型恢复 | `api_error`, `api_retry`, `control_request_progress`, `model_fallback`, `model_consent_fallback`, `model_refusal_fallback`, `model_refusal_no_fallback` | 当前 API attempt/fallback chain |
| thinking/提示 | `thinking`, `thinking_tokens`, `informational`, `notification` | 展示层；thinking token 是估算信号 |
| hook/权限 | `hook_started`, `hook_progress`, `hook_response`, `stop_hook_summary`, `permission_denied`, `permission_retry`, `elicitation_complete` | hook run、permission/tool request |
| task/agent | `task_started`, `task_progress`, `task_updated`, `task_notification`, `background_tasks_changed`, `agents_killed`, `scheduled_task_fire` | task registry/background lifecycle |
| 文件/持久化 | `file_snapshot`, `files_persisted`, `mirror_error` | checkpoint、sync/mirror adapter |
| 插件/记忆 | `plugin_install`, `memory_recall`, `memory_saved` | plugin install 与 memory store |
| 外部变更/反馈 | `code_change_published`, `vcs_state_changed`, `feedback_draft_queued`, `local_command_output` | 外部 repo/UI/feedback 状态；部分字段只是提示，需重查权威对象 |
| 终态 | `success` | result；含 result/structured_output/usage/cost/turns/permission denials |

`error` 是 control response verdict，不是观察事件。四个 result error subtype 使用一个 enum，因此没有进入这份 89 字符串清单：`error_during_execution`、`error_max_turns`、`error_max_budget_usd`、`error_max_structured_output_retries`。

## 44 个 Managed Agents event identifier

这 44 项由宽词法规则从 bundle 恢复。bundle 内 Anthropic SDK SSE parser 会接收这些 event name，SessionToolRunner 对 tool/status 子集有真实消费分支；随包 Managed Agents 文档解释更广表面。它证明该依赖和随包知识携带这些名称，不证明本地 CLI stdout 会发出它们，也不证明远端服务在任意账户上开放。

共同字段以远端 event record 为中心，通常包含 `type`、event `id` 和处理时间；下表只列 bundle 消费点或随包文档能证明的专属关键字段，未恢复的字段明确标为边界。

| event | 方向 | 关键字段/配对 | 状态所有者 |
| --- | --- | --- | --- |
| `user.message` | client -> remote session；stream echo | `content` | session input log |
| `user.interrupt` | client -> remote session；通常 echo | 未恢复稳定专属字段；budget pause 时可被接受但不落 event | remote scheduler/session |
| `user.tool_confirmation` | client -> session；echo | `tool_use_id`, `result: allow/deny` | pending tool approval |
| `user.tool_result` | client -> session；echo | `tool_use_id`, `is_error`, `content` | built-in tool call pairing |
| `user.custom_tool_result` | client -> session；echo | `custom_tool_use_id`, `is_error`, `content` | custom tool call pairing |
| `user.define_outcome` | client -> session；echo | outcome/rubric shape由随包 outcome 文档定义 | outcome evaluation loop |
| `agent.message` | service -> client | `content`; buffered record 是权威文本 | thread conversation |
| `agent.thinking` | service -> client | 进度信号；随包文档明确不携带 thinking content | active model request |
| `agent.tool_use` | service -> client | `id`, `name`, `input`, optional evaluated_permission | built-in tool lifecycle |
| `agent.tool_result` | service -> client | 与 agent tool use 关联；稳定完整 shape 未从 runtime consumer恢复 | remote tool executor |
| `agent.mcp_tool_use` | service -> client | tool identity/input；完整 shape 边界 | remote MCP executor |
| `agent.mcp_tool_result` | service -> client | 对应 MCP use；完整 shape 边界 | remote MCP executor |
| `agent.custom_tool_use` | service -> client | `id`, `name`, `input`, permission；需要 custom result | client-owned custom tool |
| `agent.thread_context_compacted` | service -> client | 随包示例提到 `pre_compaction_tokens`，部分示例可省略 | thread context state |
| `agent.thread_message_sent` | service -> client | `to_session_thread_id` | cross-thread mailbox |
| `agent.thread_message_received` | service -> client | `from_session_thread_id` | cross-thread mailbox |
| `agent.session_thread_message_sent` | service -> client | inventory 可证明名称；稳定专属字段未恢复 | session/thread bridge boundary |
| `agent.session_thread_message_received` | service -> client | inventory 可证明名称；稳定专属字段未恢复 | session/thread bridge boundary |
| `session.status_scheduled` | service -> client | 状态 event；字段边界 | scheduler queue |
| `session.status_run_started` | service -> client | run start identity；字段边界 | scheduler run |
| `session.status_running` | service -> client | 无必须专属字段被 runtime consumer依赖 | session lifecycle |
| `session.status_rescheduled` | service -> client | retry/reschedule 状态 | scheduler |
| `session.status_idle` | service -> client | `stop_reason`；end_turn/requires_action/budget_reached | session lifecycle |
| `session.status_idled` | webhook/alternate lifecycle词汇 | inventory 可证明名称；与 status_idle 不得自行合并 | server boundary |
| `session.status_terminated` | service -> client | terminal reason/detail shape 边界；完成或错误都可终止 | terminal session |
| `session.updated` | service -> client | 只带 changed fields；删除 budget 用 `budget:null` | session resource |
| `session.usage` | service -> client | cumulative usage/list cost snapshot | session budget/accounting |
| `session.error` | service -> client | error payload；稳定细分 shape 边界 | session processing |
| `session.archived` | service -> client/webhook | resource identity；字段边界 | session resource |
| `session.deleted` | service -> client | resource identity；SessionToolRunner 将其视为终止 | session resource |
| `session.thread_created` | service -> client | thread identity/name；可代表 subagent/advisor | thread registry |
| `session.thread_status_created` | service -> client | thread identity；字段边界 | thread lifecycle |
| `session.thread_status_running` | service -> client | thread identity/status | thread lifecycle |
| `session.thread_status_rescheduled` | service -> client | retry state | thread scheduler |
| `session.thread_status_idle` | service -> client | `stop_reason` | thread lifecycle |
| `session.thread_status_terminated` | service -> client | thread identity/terminal state | thread lifecycle |
| `session.thread_idled` | webhook/alternate lifecycle词汇 | inventory 可证明名称；字段边界 | server boundary |
| `session.thread_terminated` | webhook/alternate lifecycle词汇 | inventory 可证明名称；字段边界 | server boundary |
| `session.outcome_evaluation_ended` | webhook/alternate lifecycle词汇 | evaluation/session identity；字段边界 | outcome evaluator |
| `span.model_request_start` | service -> client | span/request identity、model；完整 shape 边界 | model request span |
| `span.model_request_end` | service -> client | start correlation、model usage | model request span |
| `span.outcome_evaluation_start` | service -> client | evaluation span identity | outcome evaluator |
| `span.outcome_evaluation_ongoing` | service -> client | ongoing grader progress | outcome evaluator |
| `span.outcome_evaluation_end` | service -> client | evaluation result/correlation；完整 shape 边界 | outcome evaluator |

远端流还有 `event_start/event_delta` 预览帧，但不进入这 44 个 `{domain}.{action}` 标识；随包文档明确它们只在 SSE preview 中出现，不在普通 event list 中。这个差异与本地 `stream_event` 仍然是两套协议。

## 103 个 slash command 的协议归属

slash command 首先是 **输入扩展/本地命令路由**，不是 control subtype。命令可能：只改 TUI、本地读写 session/settings、生成 prompt 进入 Agent Loop，或在 remote mode 下转成 control request。不能从命令名推断网络协议。

| 路由类别 | 2.1.235 inventory 中的命令 |
| --- | --- |
| 会话、上下文、历史、目录 | `add-dir`, `autocompact`, `branch`, `brief`, `btw`, `cd`, `clear`, `compact`, `context`, `export`, `focus`, `fork`, `goal`, `import`, `memory`, `pause-memory`, `recap`, `rename`, `resume`, `rewind`, `session`, `exit` |
| 模型、权限、执行模式 | `advisor`, `auto-mode-setup`, `effort`, `fast`, `model`, `permissions`, `plan`, `powerup`, `ultraplan`, `ultrareview`, `autofix-pr`, `passes` |
| agent、task、background、schedule | `agents`, `background`, `list-agents`, `loops`, `stop`, `subtask`, `tasks`, `team-onboarding` |
| MCP、plugin、skill、hook | `hooks`, `mcp`, `plugin`, `reload-plugins`, `reload-skills`, `skill-doctor`, `skills` |
| IDE、浏览器、远端与 daemon | `chrome`, `daemon`, `desktop`, `ide`, `mobile`, `remote-control`, `remote-env`, `teleport`, `web-setup` |
| workflow、artifact、design | `artifacts`, `design`, `design-consent`, `design-login`, `design-revoke`, `workflow-launch-exec`, `workflows` |
| 安装、账户、provider、升级 | `config`, `extra-usage`, `install`, `install-github-app`, `install-slack-app`, `login`, `logout`, `privacy-settings`, `pro-trial-expired`, `rate-limit-options`, `setup-bedrock`, `setup-vertex`, `update`, `upgrade`, `usage`, `usage-credits` |
| TUI、输入、可访问性、媒体 | `color`, `copy`, `keybindings`, `radio`, `scroll-speed`, `status`, `statusline`, `stickers`, `terminal-setup`, `theme`, `tui`, `voice`, `wellbeing` |
| 帮助、诊断、信息与反馈 | `bug`, `diff`, `feedback`, `heapdump`, `help`, `init`, `insights`, `release-notes`, `version` |

这张表覆盖生成清单中的全部 103 个名字，但只说明入口归属。具体某个命令是 local/local-jsx/prompt、有哪些 feature gate、是否在 remote mode 改走 control channel，需要回到对应 command object 与 handler，不能由这份词法清单推出。

## 失败恢复与诊断顺序

| 症状 | 先检查 | 原因 |
| --- | --- | --- |
| 没有任何 stdout | format validation、是否 `--verbose`、子进程 spawn | Agent Loop 可能尚未启动 |
| 有 init 没 result | stdin 是否关闭、pending control request、transport close | result 是 turn-complete gate |
| permission 卡住 | `can_use_tool.request_id` 是否有对应 response/cancel | assistant stream 与审批 RPC 是两条状态线 |
| partial UI 卡在生成中 | 是否收到合成/真实 `message_stop`，是否处理 tombstone 后续 | 预览可能被 fallback 回撤 |
| subtype success 但进程 exit 1 | 看 `is_error` 与 `api_error_status` | success 表示 result shape，不保证无 API error |
| structured output 缺失 | 看 tool call 是否发生、是否被 tombstone、retry count | 文本成功不等于 schema tool 成功 |
| resume 后状态不同 | 区分 transcript state 与 process-local pending/socket | resume 不复活旧进程 |
| 收到未知 type/subtype | 忽略并记录，继续等待 result；control unknown 应等 error response | schema 明确要求 forward-compatible consumer |

## 安全、隐私与成本

- `system/init` 可包含 cwd、工具、MCP server、plugin/skill、账户 email/organization、模型和权限模式；assistant/user/tool result 还可包含源码、文件路径和命令输出。NDJSON 必须按会话数据处理，不能当普通 debug log 公开。
- `submit_feedback` 可以附带 transcript；schema 说明会运行 policy/redaction，但调用者仍要把 `attach_transcript` 当成显式数据外发决定。
- `mcp_call` 的 schema 说明 control channel 被视为可信，不走普通 model-turn permission check。任何能写入 stdin control frame 的进程都处在高信任边界。
- `update_environment_variables` 只应用 allowlist 键；非 allowlist 被拒绝。remote stdin 还会过滤 server-authored-only frame，防止伪造 ingress provenance。
- `read_file` 复用 Read 权限规则；`set_cwd` 复用目录校验和 trust，但 trust attestation 可能先持久化，随后因 busy/relocation 失败而 cwd 不变。
- `result.total_cost_usd` 与 `modelUsage` 是当前 `query()` 的累计估算；多轮 streaming input 应读取最新 result，不要把每轮累计值相加。resume 新 query 重新累计。
- partial events、hook events、replay、verbose JSON 数组会增加传输/内存成本。structured output 默认最多 5 次尝试，会增加模型调用成本。

## 可验证证据

| 结论 | 2.1.235 可读源码/清单 |
| --- | --- |
| CLI flags 与公开格式 | [CLI surface](cli-surface.txt)、[CLI option definitions](../reverse/javascript/cli.readable.js#L603757) |
| input/output 组合校验与 JSON Schema 装载 | [592654-592773](../reverse/javascript/cli.readable.js#L592654) |
| SDK 固定启动 `stream-json + verbose` | [417551-417660](../reverse/javascript/cli.readable.js#L417551) |
| Query pending、unmatched cap、initialize、request/cancel | [417820-418430](../reverse/javascript/cli.readable.js#L417820) |
| stdout/stdin/control schema 与方向/字段 | [595960-595972](../reverse/javascript/cli.readable.js#L595960) |
| stdin 解析、重复/未知 response、schema sampling | [596065-596390](../reverse/javascript/cli.readable.js#L596065) |
| partial 回撤、result 与 structured output retry | [597607-597884](../reverse/javascript/cli.readable.js#L597607) |
| stream/json/text 输出与 exit rule | [600172-600302](../reverse/javascript/cli.readable.js#L600172) |
| worker control dispatch | [601930-602550](../reverse/javascript/cli.readable.js#L601930) |
| StructuredOutput tool/AJV | [155470-155532](../reverse/javascript/cli.readable.js#L155470) |
| 89 subtype 生成清单 | [sdk-control-subtypes.txt](source-inventory/sdk-control-subtypes.txt) |
| 44 remote event identifier | [output-protocol-event-identifiers.txt](source-inventory/output-protocol-event-identifiers.txt) |
| Managed Agents SSE parser 与 runtime tool consumer | [9261-9274](../reverse/javascript/cli.readable.js#L9261)、[10496-10680](../reverse/javascript/cli.readable.js#L10496) |
| bundle 随包 Managed Agents event guide | [569615](../reverse/javascript/cli.readable.js#L569615) |
| 103 slash command inventory | [slash-command-identifiers.txt](source-inventory/slash-command-identifiers.txt) |

## 仍然不能从本版证明的边界

- schema/handler 的存在不证明任意账户、provider、remote service 或 feature flag 下都可达。
- 44 个 Managed Agents 名称中一部分只有依赖 parser 或随包文档证据；没有本地登录态的 service Probe，不能宣称远端实际发送了每一种事件。
- `output-protocol-event-identifiers.txt` 是宽词法 inventory，不是生成自一份完整 runtime discriminated union；表中标注“字段边界”的事件不能凭名称补造字段。
- `set_color` 有 schema 声明但主 worker dispatch 未见处理；16 个 string-only handler 又未进入 schema inventory。客户端必须做 capability/version negotiation，不能硬编码某一集合为永恒协议。
- control cancel、resume、fork、rewind 都不能回滚已经完成的外部副作用。
