# Claude Code 2.1.235 release notes

固定上游来源：

- Commit：`16440d0f6ee8c47f34169687044b89eafa8b0f8d`
- URL：`https://raw.githubusercontent.com/anthropics/claude-code/16440d0f6ee8c47f34169687044b89eafa8b0f8d/CHANGELOG.md`
- 抓取日期：`2026-08-22`
- 完整响应：`36,864` bytes，SHA-256 `ca5698c578b3e3a97b8ff8388a08f4095a64c69696709dd07337605fe5f30fe3`
- `## 2.1.235` 至下一版本标题前的原始段落：`2,707` bytes，SHA-256 `04943db50acf834556450fc580d0e3617ae0de7a7b62a5aed9444013420c5d17`

下面 19 条逐字复制自这个固定 commit；大小写、标点、反引号、括号和措辞均不做润色。逐项机制解释另放在后表，避免再把解释性改写冒充上游原文。

> 版本归属边界：以下 19 条是上游明确归入 `2.1.235` 的原文。`Release` 只证明版本声明；`Static` 表示本分支 bundle 中存在对应 consumer、状态或失败分支；`Probe` 表示固定 SHA-256 的精确二进制真实走过该路径；`Boundary` 表示还需要真实终端、编辑器、云任务或平台环境。不要把 release note 本身当成运行测试。

## 上游原文（19/19）

- Added an optional `spellcheck` setting that underlines misspelled words in the prompt input as you type, using your installed `aspell`, `hunspell`, or `ispell`
- Fixed whole-prompt-cache invalidation when a language server disconnected or reconnected mid-session
- Fixed nested markdown list items misaligning at depth 3+ and added a hanging indent to wrapped list items in the terminal UI
- Fixed prompt input highlights (slash commands, keywords, mentions) appearing shifted by one or more characters in some multi-line prompts
- Fixed Shift+Tab inside the permission prompt's comment field approving the edit and granting session-wide edit permission instead of closing the field
- Fixed the Agent tool advertising a general-purpose default in sessions where that agent is unavailable: an omitted `subagent_type` there now gets a clear error listing the available agents
- Fixed notebook cell delete/replace approval dialogs silently omitting the existing cell content when the notebook or cell could not be read; the dialog now says why
- Fixed slash commands run while Claude is responding showing HTML entities instead of the actual characters
- Fixed the prompt footer not showing the "Update installed" restart notice after a background auto-update
- Fixed the expanded task list (`ctrl+t`) always starting collapsed when resuming or relaunching into a session that still has open tasks
- Improved memory and CPU usage while cloud sessions such as `/ultrareview` or `/autofix-pr` run in the background — their event streams are no longer re-scanned and re-rendered on every update
- Improved permission dialogs: display text and "don't ask again" options now always match what a grant would cover, and "don't ask again" is withheld when contents cannot be fully displayed
- Improved the embedded `grep` in native macOS/Linux builds: pathological patterns now fail fast instead of exhausting memory, and `-m N` with `-A/-C` prints correct context
- Improved the context-limit error to say when auto-compact is off and point to `/config` to re-enable it
- Vim mode: NORMAL mode and cursor position are now preserved when toggling the detailed transcript (ctrl+o) or closing a panel
- Dialogs: arrow keys and Enter pressed in quick succession now select the option you navigated to instead of the previously highlighted one
- `SendMessage` now refuses messages too large for cross-session delivery up front instead of silently dropping them
- Remote Control: `claude rc` now applies the same enterprise-gateway availability check as interactive startup
- [VSCode] Fixed focus jumping between open Claude tabs on its own when a window with several Claude panels is restored or reloaded

## 逐项机制回填

| # | 原来的失败状态 | `2.1.235` 的状态变化 | 用户实际得到什么 | 证据与边界 |
| ---: | --- | --- | --- | --- |
| 1 | prompt 输入没有本地拼写反馈 | 新增 user/flag/managed-only 的 `spellcheck` block；按 `aspell -> hunspell -> ispell` 选择长驻子进程，带 batch、cache、timeout、一次重启和 session-disable | 默认仍关闭；开启后只改变本地输入高亮，不修改发送给模型的文本或 token | **Release + Static**：[完整生命周期](tui-input-accessibility-media-ide-chrome.md#三spellcheck-是受限本地子进程不是模型纠错)。未证明目标机装有 dictionary |
| 2 | LSP 断线/重连把动态连接状态混入稳定 cache identity，导致整段 prompt cache 失效 | 连接状态变化与稳定 prompt prefix 分离；普通 reconnect 不再等同 plugin full reload | 减少无意义 cache rewrite、首 token 延迟与 cache write 成本 | **Release + Static mechanism**：[LSP 边界](plugins-skills-commands-lsp.md#本版-prompt-cache-修复的准确含义)。没有真实账单/命中率 Probe |
| 3 | 深度 3+ 列表 marker 与正文缩进 owner 分叉，wrapped line 回到错误列 | marker display width 决定首行和 hanging indent，嵌套 block 单独缩进 | 长回答的层级和换行更容易扫描 | **Release + Static**：[452860-452935](../reverse/javascript/cli.readable.js#L452860)。终端字体宽度仍是环境边界 |
| 4 | 多行输入的 raw offset 被直接套到 rendered line，第二行后 highlight 漂移 | 先把 raw/rendered offset 映射成逐行 segment，再渲染 spellcheck/mention/slash 等 decoration | 屏幕标记与真正提交的字符重新一致 | **Release + Static**：[428992-429151](../reverse/javascript/cli.readable.js#L428992)。未自动化遍历所有 Unicode/terminal 组合 |
| 5 | permission comment 中 `Shift+Tab` 会落入批准路径并扩大成 session-wide edit grant | comment input mode 先消费按键并退出输入，之后才允许处理 grant shortcut | 消除“想关备注框却批准并持久授权”的权限错误 | **Release + Static + exact-binary PTY Probe**：[531443-531454](../reverse/javascript/cli.readable.js#L531443)、[531724-531759](../reverse/javascript/cli.readable.js#L531724)、[`tui-regressions.json`](runtime-probes/tui-regressions.json)。Shift+Tab 前后均为 2 次主请求、两个文件零变化；显式 Enter 后第二个 Edit 仍需审批，排除了 session grant |
| 6 | Agent tool 在 `general-purpose` 不可用时仍把它广告成省略 `subagent_type` 的默认值 | schema/validation 使用当前可用 Agent 集合；没有可用默认时返回列表化错误 | 失败更早、更可诊断，不会静默路由到不存在的 Agent | **Release + Static**：[Agent 工具合同](builtin-tools-reference.md#agenttaskmailbox-与-worktree)。不证明任意第三方 Agent 定义可运行 |
| 7 | Notebook delete/replace 无法读旧 cell 时，审批 UI像是“旧内容为空” | dialog 保留读取失败原因并收缩可展示/可持久授权范围 | 审批者能区分空 cell 与读取失败 | **Release + Static UI/permission path**：[工具与权限专题](tools-permissions-hooks.md)。未做真实 notebook Probe |
| 8 | Claude 正在响应时执行 slash command，文本经过错误的 HTML entity 展示路径 | command result 在进入 TUI 时恢复真实字符 | `&lt;`、`&amp;` 等不再冒充命令真实输出 | **Release + Static UI path**：[输入界面专题](tui-input-accessibility-media-ide-chrome.md#十一本版-release-note-与静态实现如何对齐)。不改变 shell/tool output bytes |
| 9 | background updater 已安装新版本，但 footer 重渲染后丢失 restart notice | `Update installed` 成为可持续读取的更新 UI 状态 | 用户知道当前进程仍跑旧 bytes，需要重启 | **Release + Static lifecycle/UI**：[更新生命周期](install-update-doctor-lifecycle.md)。不代表自动重启或安装一定成功 |
| 10 | resume/relaunch 后有 open tasks，expanded task list 却总回到 collapsed | 展开状态与任务/session 恢复状态重新绑定 | 长任务回来后保留操作现场 | **Release + Static session/UI**：[TUI 状态专题](tui-input-accessibility-media-ide-chrome.md#二composer-是可恢复的编辑状态机不是一个-react-文本框)。不恢复未持久化进程内组件状态 |
| 11 | `/ultrareview`、`/autofix-pr` 每次 cloud event 更新都全量重扫并重渲染历史 | consumer 改为增量处理新增 event | 长时间后台任务的 CPU、内存和 render 压力不再随历史线性重复放大 | **Release + Static architecture**：[后台与 Cloud 专题](cloud-background-channels.md)。没有长时性能基准，不能给出节省百分比 |
| 12 | permission 文案、实际 grant scope 与 `don't ask again` 选项可能不一致；内容显示不全仍可持久批准 | display model 与 grant model 对齐；不能完整展示时隐藏 persistent option | “看到什么、批准什么、记住什么”重新一致 | **Release + Static**：[permission input](tui-input-accessibility-media-ide-chrome.md#二composer-是可恢复的编辑状态机不是一个-react-文本框)。不代表所有 tool 自定义 dialog 已 Probe |
| 13 | embedded grep 遇病态 pattern 消耗过高；`-m N` 与 `-A/-C` 的停止边界会截错 context | native binary 以 `argv0=rg` 进入内嵌 `ripgrep 14.1.1 (rev fdb5e06cce)`；`a{1,1000000000}` 在 3 秒 deadline 内 fast-fail，以 exit 2 和固定 `compiled regex exceeds size limit of 104857600` 失败，`-m 1 -A 2` / `-m 1 -C 2` 则在达到 match cap 后逐字保留 2 行 after-context | 病态搜索成为模型可观察的 `is_error` tool result，而不是拖死 Agent Loop；有限匹配的周边行可按原行号消费 | **Release + Static + exact-binary Probe**：[Grep 机制](builtin-tools-reference.md#globgrep)、[`embedded-grep.json`](runtime-probes/embedded-grep.json)。本次 macOS arm64 峰值 RSS 为报告中的约 229 MiB、低于 512 MiB 验收界线；RSS 包含 313 MB native 可执行文件的映射/运行时页，不等于 regex heap。Grep 模型 schema 不暴露 `-m`，所以 `-m` 回归通过同一精确二进制的 embedded `argv0=rg` 入口验证，不能写成模型已发送 `-m` |
| 14 | 关闭 auto-compact 后触顶只给失败，缺少直接恢复入口 | context-limit error 明确指出 auto-compact 状态并链接 `/config` | 用户可直接恢复配置，而不是误判模型窗口变小 | **Release + Static diagnostic**：[上下文专题](context-governance-and-caching.md)。不改变窗口、阈值或自动重试语义 |
| 15 | 打开详细 transcript 或关闭 panel 会让 composer 重挂载，Vim 回 INSERT、cursor 跳位 | 外部 store 保存 `vimMode` 与 cursor offset，重挂载时恢复 NORMAL 语义 | 编辑现场连续，减少误操作 | **Release + Static**：[269426-269454](../reverse/javascript/cli.readable.js#L269426)、[519247-519263](../reverse/javascript/cli.readable.js#L519247)。新进程不恢复未提交 prompt |
| 16 | 快速 Arrow + Enter 时 Enter handler 读到旧 highlight | 提交时读取最新 `getFocusedValue()`，而非上一 render 的 selection | 屏幕新高亮项与实际动作一致 | **Release + Static + exact-binary PTY Probe**：[429483-429620](../reverse/javascript/cli.readable.js#L429483)、[`tui-regressions.json`](runtime-probes/tui-regressions.json)。同批 Down+Enter 选中 session `acceptEdits`，两个 Edit 都执行且第二次不再弹框；只覆盖使用该 dialog primitive 的界面 |
| 17 | 超过 cross-session delivery limit 的 `SendMessage` 被静默丢弃 | 发送前显式拒绝并把失败交回 tool result | 模型可以缩短、拆分或改用文件，不再把未送达误当成功 | **Release + Static**：[多 Agent 消息专题](mcp-agents-background.md)。拒绝不保证之后重试送达，也不回滚此前副作用 |
| 18 | `claude rc` alias 与 interactive Remote Control 的 enterprise-gateway availability gate 不一致 | 两个入口复用同一前置检查 | 企业网关环境得到一致的可用/不可用诊断 | **Release + Static + negative Probe**：[Remote Control](cloud-background-channels.md#1-remote-control远端看本地跑)、[`lifecycle-doctor.json`](runtime-probes/lifecycle-doctor.json)。未证明真实账号连接成功 |
| 19 | VS Code 恢复多个 Claude panel 时 focus ownership 在 tab 间跳动 | 上游 extension/CLI integration 修复 panel restore/reload 的 focus 协调 | 多会话编辑时输入焦点更稳定 | **Release + CLI Static surface + Boundary**：[IDE ownership](tui-input-accessibility-media-ide-chrome.md#六ide-integration-把编辑器现场接进来但不拥有-prompt)。extension 内部算法和真实多 panel 结果未在 bundle 内恢复 |

## 这 19 条合起来说明了什么

它们不是一次 Agent Loop 重写。`2.1.235` 的主循环、人工维护的 29 项核心终端 built-in reference、103 个 slash command、31 个 Hook event 和 provider 顶层集合没有因这些 release note 整体换代。变化集中在四类边界：

1. **输入与授权状态一致性**：第 3、4、5、7、8、12、15、16、19 条都在修复“屏幕状态”和“实际提交/授权状态”分叉，其中第 5、12 条直接属于风控正确性。
2. **长会话的增量与持久状态**：第 2、9、10、11 条避免动态状态污染稳定 cache，或避免重渲染/重启后丢失现场。
3. **失败必须可见、可恢复**：第 6、13、14、17、18 条把不存在的 Agent、病态搜索、context limit、超限消息和不可用 Remote Control 从静默/晚失败变成明确终态。
4. **本地辅助能力**：第 1 条加入 spellcheck，但 gate、subprocess 和失败降级都留在客户端，不把用户文本交给模型外的拼写服务。

因此版本验收不能只做 `claude --version` 和一次普通问答。最低回归合同应覆盖：多行 composer 与 Vim panel 重挂载、permission comment shortcut、快速 dialog selection、LSP reconnect 前后 request cache identity、后台 update notice、resume 后 task panel、`SendMessage` 超限、embedded grep pathological/context cases、custom endpoint 下 `claude rc` gate，以及 VS Code 多 panel restore。当前仓库只把已经真实跑过的项目标为 Probe，其余保留 Static 或 Boundary，没有用 19/19 文档覆盖率冒充 19/19 运行测试。
