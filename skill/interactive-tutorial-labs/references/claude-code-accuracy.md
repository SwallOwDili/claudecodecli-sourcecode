# Claude Code accuracy contract

实现 Claude Code 机制场景时使用。它约束 owner、消息、协议和版本事实，不规定文章文风。

## 全局边界

- Static source 只证明客户端分支、顺序和可达性。
- Exact Probe 只证明被实际观察的输入、输出和版本。
- Teaching fixture 负责具体用户输入、虚拟文件、控件选择和失败注入。
- Step actor 与 evidence owner 分开记录。
- 不用客户端 dispatch 源码证明模型选择了某个具体工具。
- 不用 Hook deny Probe 证明用户 permission deny。
- 不把当前官网或其他版本行为倒灌到目标版本。

## Agent Loop

- 用户文本不拥有 available tool schemas。
- 输入可改变 fixture 模拟的模型选择，不得让客户端词法解析后删 schema。
- 模型只收到 message blocks，不收到文件系统 snapshot。
- 后续 request 包含完整 assistant `tool_use` 和 user `tool_result` content，不只传 ID。
- 串行 iteration 与同一 assistant response 的独立工具 batch 必须选一种并说明。
- 同一 response 中的后续 tool call 看不到本 response 刚完成的 result。
- permission deny 发生在 side effect 前。
- 测试失败不能自动撤销已完成 Edit。
- read/search-only、edit-only、test-only、edit+test 的终态文案分别生成。

## Compact

- 明确场景是 manual miss、precomputed hit、auto 还是 reactive。
- `/compact` 参数是 custom instructions，不是旧历史中的 user turn。
- `pre_tokens` 只计算旧历史。
- 按目标版本合法 assistant groups 切 suffix。
- 不拆 assistant group 或 `tool_use/tool_result`。
- 分开保存：
  1. 模型原始 Summary response；
  2. 客户端 parser 产出的 `Summary:`；
  3. continuation wrapper 内的 synthetic compact-summary user message。
- Synthetic summary role 是目标版本的 user，不是 assistant。
- `compact_metadata` 使用目标版本字段形状。
- `preserved_segment` 和 `preserved_messages` 的 anchor/head/tail/UUID 必须可解析。
- 附件恢复、SessionStart hook results 和 PostCompact 分开。
- PostCompact 接收目标版本规定的 Summary 形态。
- PreCompact block 不生成成功 Summary、Boundary 或重建上下文。
- Manual compact 完成后等待新输入，不重复发送 slash command。
- 用户提到的附件路径先规范化；只有虚拟文件系统中真实存在的文件标为 restored。
- Missing 文件进入 failure，不生成假内容。
- Token 数明确标为 fixture estimate。

## Permissions、Hooks、Sandbox

- 原始 schema/custom validation 在 PreToolUse 之前。
- `old == new` 拒绝。
- `replace_all=false` 时 old 必须唯一。
- Hook rewrite 后只重跑目标版本实际会重跑的 validation。
- Permission allow 不覆盖 filesystem/network sandbox。
- Edit 不经过 Bash OS-command sandbox。
- tool.call failure 后按目标版本触发 PostToolUseFailure。
- Session allow、once allow、deny 的作用域分别展示。
- 外部磁盘漂移值必须与用户目标值不同。
- Hook matching count、additionalContext 和虚拟 result 是 Teaching fixture。

## Wire contract

`tool_result` wire block只包含目标协议允许字段。Decision source、denial kind、Diff、owner 和 fixture 状态放入 `clientMetadata`。

对于 `tool_use/tool_result`：

- 一对一；
- 同 ID；
- 顺序正确；
- error result 也配对；
- 测试 multiplicity，不只比较唯一集合。

## Side effects

以下已发生动作标为 `reversible:false`：

- 文件写入；
- 已运行进程；
- transcript/Boundary 追加；
- session permission rule；
- 外部磁盘漂移；
- 已提交远端动作。

回放后退只重放虚拟 snapshot，不代表真实回滚。
