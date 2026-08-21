# TUI、IDE、Remote Control 与 Cloud Session

Claude Code 2.1.235 不是只有一个 terminal renderer。它同时支持交互 TUI、`--print`/stream-json、IDE integration、Remote Control、cloud/teleport、background/subagent 和桌面侧桥接。它们共享 Agent Loop 与会话对象，但输入来源、渲染责任、权限对话、附件传输、断线恢复和 session ownership 不同。

## 一张图看清多界面架构

```text
                      local session state
                 messages / tools / permissions
                             |
             +---------------+---------------+
             |               |               |
         terminal TUI     print/SDK      remote bridge
         Ink/React        JSON stream    event/session API
             |                               |
      keyboard/mouse                        web/mobile
      local dialogs                         remote dialogs
             |
          IDE bridge
      selection/diff/open/status

cloud session --teleport--> local transcript/session copy
remote-control ------------> local Agent Loop remains owner
```

关键差异不是“画面在哪里显示”，而是谁持有执行进程。Remote Control 把终端进程连接给 claude.ai viewer；cloud session 则运行在远端环境；teleport 会把 cloud session 拉到本机继续，形成新的本地执行边界。

## TUI 持有什么状态

交互界面需要维护的不只是 messages：

- 当前输入缓冲、历史、粘贴和附件；
- streaming assistant block、thinking、tool progress；
- permission、question、plan 等 dialog；
- notifications、status line、terminal title；
- model、effort、permission mode、fast mode；
- tasks、background agents、MCP clients；
- IDE installation status；
- remote bridge active/session URL；
- theme、syntax highlight、virtual scroll、screen reader 和 mouse mode。

readable JS 584395-584397 的状态 provider 把 `mainLoopModel`、MCP、IDE status、transcript、settings、permission mode、tasks、remote bridge、fast mode 和 effort 聚合给 UI。588099 附近的主循环 context 又把同一批状态转成 Agent Loop 可消费的 options。这解释了为什么 UI 问题和执行问题能分开：renderer 卡住不必然说明模型请求停了，反之 streaming executor 工作也不保证远端 viewer 收到所有附件。

## Interactive、print 与 SDK 的差异

### Interactive TUI

TUI 负责本地输入、增量渲染和人工决策。Stop hook、permission prompt、AskUserQuestion、plan review 等都能打开对话。输入还可以在模型工作时进入 queue，下一轮前被 Agent Loop 吸收。

### `--print` / stream-json

非交互模式把生命周期变成机器协议。它需要明确 `--output-format=stream-json`、`--verbose` 等组合，permission prompt 不能依赖本地 UI。精确 Agent Loop 探针就是通过这个入口获取 `system.init`、assistant/tool/result 事件，并确认最终 subtype 为 `success`。

### SDK transport

SDK 模式还包含 control request/response、permission prompt tool 和 stream close。SDK host 可以成为 UI/credential/provider 的持有者，因此源码区分 `hostOwnsStdinOrigin`、remote transport 和 provider-managed-by-host。

同一个“无输出”故障必须先确认入口模式。TUI 无渲染、stream-json 没 result、SDK control request 未响应，是三种不同问题。

## TUI 的渲染与输入治理

2.1.235 暴露一组专门的终端开关：alternate screen、mouse、mouse clicks、virtual scroll、native cursor、no flicker、syntax highlight、scroll speed、screen reader/accessibility。它们不是装饰：

- alternate screen 决定是否占用独立终端缓冲区；
- virtual scroll 与真实 terminal scrollback 的行为不同；
- native cursor 会影响 IME、选择和输入位置；
- mouse/clicks 控制交互命中和终端兼容性；
- screen reader 需要减少动态区域和视觉-only 状态；
- no-flicker 与增量重绘影响高延迟终端体验。

排查 TUI 时应先区分 terminal capability 与业务 state。最小复现可以关闭 alternate screen/mouse/virtual scroll，再看 stream-json 是否仍正常。如果 machine output 正常而 TUI 异常，问题位于 renderer/input 层，而不是 Agent Loop。

## IDE integration 是双向上下文通道

`/ide` 在 `reverse/javascript/cli.readable.js` 333265-333268 被注册为 `local-jsx` 命令，描述为“Manage IDE integrations and show status”。主 app state 还持续携带 `ideInstallationStatus`。

IDE integration 的价值通常包括：

- 当前文件、selection 和 diagnostics 作为上下文；
- diff/open file/navigation 动作；
- IDE 内展示状态或接受命令；
- 自动安装/连接检测与失败提示。

这条通道的安全边界与读取普通工作区文件不同。IDE 能提供编辑器当前状态，但客户端仍需要验证 workspace trust、路径和可执行 helper。`CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` 说明自动安装本身也有独立 gate。

当前官方 [IDE integrations](https://code.claude.com/docs/en/ide-integrations) 把协议边界写得更具体：extension 在 `127.0.0.1` 的随机端口启动本地 MCP server，每次 activation 生成新 token，保存在用户权限保护的 lock file，CLI 用 `X-Claude-Code-Ide-Authorization` 连接。当前 selection 和 active-file path 会进入 prompt context；匹配的 Read deny rule 会同时阻止选中文本和 open-file notice。该公开主张登记为 `public.ide-loopback-contract`。

这解释了三个容易混淆的判断：loopback transport 不等于无认证；IDE 提供上下文不等于绕过 Read deny；extension 内部 RPC 数量也不等于全部工具都暴露给模型。本快照有对应 bridge 与 permission 静态分支，但没有启动真实 VS Code extension 完成连接，因此仍标为 Public + Static，而不是成功 Probe。

版本分析不能只统计 `/ide` 命令是否存在。应比较：连接协议、IDE 状态字段、自动安装 gate、selection/diagnostic payload、断线降级、是否改变工具权限。

## Remote Control：远端是 viewer，终端仍是执行 owner

Remote Control 会把本地 session 注册为可从 web/mobile 查看和交互的远程会话。其客户端状态包括：

- 本地 session 与 remote session ID 的映射；
- owner account/org；
- sequence/ack 与 history backfill；
- supported dialog kinds；
- remote credential refresh；
- outbound event queue 和 reconnect state；
- attachment delivery capability。

当前官方 [Remote Control](https://code.claude.com/docs/en/remote-control) 明确给出 ownership：本地进程只建立出站 HTTPS，不开放入站端口；执行和 filesystem access 留在本机；连接期间 messages、responses 与 tool activity transcript 存放在 Anthropic server，用于跨设备同步和掉线重连。对应 `public.remote-local-execution` 与 `public.remote-transcript-security`。

所以“代码不上传执行”与“transcript 不离开本机”是两件事。Remote Control 的工具副作用发生在本机，但同步 transcript 是服务端状态；对 ZDR/compliance 环境必须按官方 eligibility 和组织政策判断，不能只看本地 filesystem ownership。

源码 302491-302493 给出一组明确的韧性参数：14 次 reconnect attempt、约 30 分钟不可达描述、24 小时内 drop 次数预算，以及 6 分钟/30 秒/5 分钟/5 秒级别的节奏常量。它不是无限重连；达到条件后会向用户表明连接耗尽。

Remote Control 还区分本地可见内容与远端可交付内容。readable JS 292325 和 299402 附近保留“NOT delivered to Remote Control (phone/web) viewers”的附件提示。用户在桌面看到了文件，不等于手机端收到文件内容；报告必须记录 `rendered_locally`、附件能力和远端 delivery outcome。

## Remote dialog 与权限

远端控制不能假设所有本地对话都能在客户端呈现。协议维护 supported dialog kinds，并为 permission、question、plan 等 request 分配 request ID、pending state、cancel/timeout 和 response。未知或旧协议版本可能没有某种 dialog 的 delivery path。

这会产生三个必须区分的状态：

1. 工具还未执行，等待远端审批；
2. dialog 已发出，但 viewer 未响应或断线；
3. stream close 导致请求被取消、保留或本地接管。

如果协议不支持某 dialog，正确行为应是显式降级/拒绝，而不是默认允许。远端 UI 的可达性是权限执行链的一部分。

## 登录、token refresh 与 session ownership

Remote Control 只在满足账户/provider 条件时可用。源码保留“only available with claude.ai subscriptions”、`/login`、OAuth token refresh、账户/组织变化和 resume reattach 的错误路径。304586-304840 附近能看到：

- 无 OAuth token；
- claude.ai login rejected/expired；
- refresh chain exhausted；
- 账户或组织变更后要求重新连接；
- resume 时 remote credentials 获取失败。

这不是普通 Messages API key 可以完全替代的协议。即使自定义 gateway 能跑 Agent Loop，也不代表它能注册 Remote Control session。

`probe.remote-control-custom-endpoint-boundary` 使用自定义 `ANTHROPIC_BASE_URL` 运行 doctor，literal output 明确指出 Remote Control 只在 `api.anthropic.com` 路径可用，并同时报告 feature-flag evaluation 被 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 禁用。命令 exit 0，因为 doctor 正常完成诊断；`remoteControlAvailable=false` 才是被测状态。

当前官方文档还说明：若断线期间 compact 改写了会话，或用户用 `/resume` 切换过 conversation，再 reconnect 会归档之前的 server session，对应 `public.remote-compact-reconnect`。本版客户端存在 reconnect/archival 分支，但本地探针没有真实登录态和服务端 session，因此不能把该 Public 主张升级成成功 Remote Control Probe。

## Cloud session 与 teleport

源码 276313 附近清楚区分：

- `teleport`：把 cloud session 拉到本机 terminal；
- `session`：会话已经在 Claude Code web 运行；
- `remote-control`：本机 terminal session 连接 claude.ai。

teleport 后的本地执行拥有自己的 cwd、工具和外部环境。历史可以复制，但远端容器里的未提交文件、进程、凭据、端口和外部 side effect 不会仅靠 transcript 自动搬到本机。相反，Remote Control 下执行环境仍是原来的本机进程。

因此交接时要分别迁移：

- transcript/message graph；
- repo state 与未提交 diff；
- artifact/attachment；
- environment/credentials；
- background tasks；
- remote/cloud ownership metadata。

## 故障定位矩阵

| 症状 | 首查层 | 证据 |
| --- | --- | --- |
| 终端不刷新但任务继续 | TUI renderer | stream-json 是否仍有 progress/result |
| 手机看不到附件 | remote delivery | attachment outcome、`rendered_locally` |
| 远端一直等待审批 | dialog protocol | request ID、supported kinds、pending/timeout |
| Remote Control 反复掉线 | reconnect budget | attempt、elapsed、24h drop counter |
| `/ide` 存在但未连接 | IDE bridge | installation status、socket/extension state |
| teleport 后找不到文件 | environment transfer | repo diff/artifact 是否实际复制 |
| gateway 能对话但不能 remote | product protocol | OAuth/session endpoint 与 entitlement |

## 微小但关键的特性

- `/ide` 是 local JSX command，不是发给模型的 slash prompt。
- Remote Control 可能只发送摘要或 metadata，不保证传输本地渲染附件。
- terminal session 从 bridge 断开后可变成本地副本；新工作不一定继续同步到 app。
- reconnect 有上限和长时间窗口，不能把“会重试”写成“永不掉线”。
- account/org 变化会使已有 remote credentials 失效。
- non-interactive/background session 没有本地 TUI，skill/status 类命令需要文本输出路径。
- IDE context 是额外上下文源，不代表 IDE 可绕过 tool permission。
- cloud、remote-control、local 是 session kind，不只是 UI 标签。

## 用户影响与成本

多界面让同一 Agent Loop 可以从 terminal、IDE、web/mobile 继续，但也引入：

- event fan-out 与序列确认开销；
- attachment 体积和隐私边界；
- remote dialog latency；
- reconnect/backfill 的状态复杂度；
- teleport 时环境不一致；
- UI 状态与真实执行状态暂时不同步。

面向用户的文档必须告诉他“执行在哪里发生、什么被同步、什么只在本地、断线后谁继续持有 session”，而不是只列出命令。

## 证据与边界

结构化证据条目：`remote-control.reconnect-budget`、`ide.command-surface`、`public.remote-local-execution`、`public.remote-transcript-security`、`public.remote-compact-reconnect`、`public.ide-loopback-contract`、`probe.remote-control-custom-endpoint-boundary`。CLI surface 见 [cli-surface.txt](cli-surface.txt)，但命令名只能证明注册；当前 Probe 证明 custom endpoint 的明确不可用原因，不证明已登录 first-party 环境中的成功连接。精确命令、literal output 和 exit status 见 [精确二进制运行证据指南](runtime-probe-index.md)。

服务端 session registry、claude.ai entitlement、移动端实现和 cloud runtime orchestration 不在本地 bundle 中。客户端能证明本地桥接协议、错误处理和状态字段，不能独自证明远端当前部署状态。
