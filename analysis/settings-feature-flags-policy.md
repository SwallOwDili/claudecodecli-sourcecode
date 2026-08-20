# Settings、Feature Flags 与 Managed Policy

Claude Code 的配置不是一个 JSON 文件，而是一组来源、作用域、信任等级和动态值共同形成的有效配置。用户看到的同一个字段，可能来自 user settings、project settings、local settings、命令行 `--settings`/flags、企业 managed policy、环境变量、GrowthBook/feature value 或当前 session state。要解释“为什么这个开关没有生效”，必须先回答它属于哪类状态、允许从哪些来源读取、谁能覆盖谁、是否在启动后刷新。

## 五层 settings 模型

`reverse/javascript/cli.readable.js` 39176-39215 暴露了五个核心 settings source：

```text
userSettings
  < projectSettings
  < localSettings
  < flagSettings
  < policySettings
```

这里的数组顺序是从普通可写来源走向更高控制来源。对应含义是：

| Source | 典型载体 | 作用域 | 主要用途 |
| --- | --- | --- | --- |
| `userSettings` | 用户配置目录的 settings | 当前用户 | 个人默认、UI、模型、环境、工具偏好 |
| `projectSettings` | `.claude/settings.json` | 项目共享 | 团队规则、hooks、permissions、MCP |
| `localSettings` | `.claude/settings.local.json` | 当前项目本机 | 不提交的本地覆盖 |
| `flagSettings` | CLI `--settings`、参数派生值 | 当前进程 | 一次运行的显式覆盖 |
| `policySettings` | managed settings、registry、policy helper | 组织/设备 | 管理员强制约束和不可降级策略 |

`--setting-sources` 只能选择 user/project/local 这三个普通来源；实现仍会加入 `flagSettings` 与 `policySettings`。所以“只加载 user”不等于“绕过 managed policy”，也不应被写成一种策略逃逸方式。

## 合并不是所有字段都用同一算法

最容易误导用户的说法是“后面的配置覆盖前面的配置”。实际字段至少有四种合并语义：

1. **标量覆盖**：例如 theme、model、某些 boolean，通常由高优先级来源取最终值。
2. **规则集合合并**：permissions、denied domains、hooks 等可能从多来源累积，再按自己的决策顺序解释。
3. **只接受特定来源**：安全敏感字段会忽略 project/local。
4. **managed pin**：一旦管理员部署某类约束，普通来源不能再关闭或放宽。

因此版本分析需要记录的不只是 schema key，而是每个关键字段的 merge strategy、allowed sources 和 fail-closed 条件。

## 安全字段为什么拒绝项目配置

项目仓库是潜在不可信输入。如果克隆一个仓库就能通过 `.claude/settings.json` 关闭 filesystem isolation、替换 sandbox runtime、允许 Apple Events 或运行 credential helper，那么 workspace trust 之前就已经失去意义。

2.1.235 的 sandbox schema 在 `reverse/javascript/cli.readable.js` 32614-32646 直接写明多项来源限制：

- `network.strictAllowlist` 只接受 user、managed/policy 或 CLI settings，忽略 project/local；
- TLS termination 路径同样忽略 project/local；
- filesystem isolation 的 `disabled` 只接受受控来源；
- managed settings 一旦配置 filesystem restrictions，普通来源不能关闭 isolation；
- `bwrapPath`、`socatPath` 只接受 admin-controlled managed settings；
- `allowAppleEvents` 不接受 project/local，默认 false；
- `failIfUnavailable` 可让 sandbox 启动失败变成进程启动失败，而不是警告后 unsandboxed 继续。

这类字段的重点不是默认值本身，而是“谁有权写”。企业风控强度取决于 policy 能否锁住降级入口，而不只取决于 CLI 是否实现了 sandbox。

## Permissions 的规则优先级与 settings 来源是两件事

官方权限文档的固定摘录说明 permission rules 按 `deny -> ask -> allow` 解释，第一命中决定结果，具体度不改变这个顺序。settings source precedence 决定哪些规则进入有效集合；permission precedence 决定集合中的规则如何裁决。

例如：

- managed policy 提供 `deny Bash(aws *)`；
- project settings 提供 `allow Bash(aws s3 ls *)`；
- 即使 project rule 更具体，deny 阶段仍先命中；
- `--setting-sources project` 也不会移除 policy layer。

把这两套优先级混为一谈，会错误地建议用户用更具体 allow 覆盖企业 deny。

## Environment 与 settings 的关系

环境变量不是独立于 settings 的“第六个 JSON 文件”。2.1.235 将部分 settings 的 `env` 注入到进程环境代理，也把某些旧偏好迁移成 settings。例如 `reverse/javascript/cli.readable.js` 595195-595206 会把旧 `autoUpdates: false` 迁移为 user settings 中的 `env.DISABLE_AUTOUPDATER=1`，并记录迁移成功或写入失败。

关键问题是每个变量的读取时机：

- provider selectors、base URL、auth 通常在请求/客户端构造时读取；
- UI/terminal flags 在 TUI 初始化时读取；
- `DISABLE_TELEMETRY`、`DO_NOT_TRACK` 等决定非必要流量和 exporter；
- timeout/concurrency/token budget 可能在工具或请求创建时读取；
- 部分环境代理支持进程内更新，部分库在初始化后已经缓存。

因此“改了环境变量但当前会话没变化”需要检查值是否已经被初始化对象捕获，不能一律建议重启，也不能一律宣称热更新。

## Feature flag 不等于已交付功能

机器清单 [feature-flags.txt](source-inventory/feature-flags.txt) 和 [feature-flag-callsites.jsonl](source-inventory/feature-flag-callsites.jsonl) 记录 bundle 中出现的稳定 flag key 与调用点。它们只能证明客户端存在读取路径，不能单独证明：

- 当前账户拿到 true；
- 远端服务支持对应协议；
- 所有 prerequisite 都满足；
- UI 命令已对用户显示；
- 功能在所有 provider 可用。

2.1.235 同时存在 baked default、环境 override、settings gate、provider gate、account/org capability 和 remote feature value。一个功能真正可用，通常需要多门同时打开。

### 建议的 feature 可达性表

| 维度 | 要记录的内容 |
| --- | --- |
| key | 稳定 flag/settings/env 名 |
| default | bundle 内默认值 |
| source | environment、settings、GrowthBook、account API |
| provider gate | first-party only 或云 provider 限制 |
| policy gate | managed setting 是否可禁用/强制 |
| surface gate | 命令、工具或 UI 是否注册 |
| protocol gate | endpoint/beta/SSE subtype 是否存在 |
| probe | 精确二进制是否触发成功路径 |

只有 key 命中而没有 surface/protocol/probe，应标成 `Static` 或 `Boundary`，不能写成“用户已经能用”。

## Managed policy 的控制面

根 settings schema 在 readable JS 40285 附近包含 `policyHelper` 与 `policyHelpers`。后者支持按 macOS/Linux/Windows/WSL 选择 helper、inline script、refresh interval、静态 default settings 和 fallback chain。这里管理的是“如何得到有效政策”，不是某个单独 permission rule。

有效 managed policy 可以控制：

- permission rules 和 permission modes；
- sandbox availability、network/domain、filesystem、credentials；
- MCP server allow/deny 与 strict config；
- hooks、helpers、process wrapper；
- update、telemetry、login/provider 与组织功能；
- 某些 UI/command surface 是否出现；
- project settings 的哪些部分被接受。

`policyHelper` 执行失败必须记录是沿用静态 default、保留上次值还是启动失败。只写“支持 managed settings”无法回答真实风控问题。

## Lifecycle：启动、监听、刷新、失效

settings 系统维护内部写时间，用于区分自身写入与外部文件变化；还维护 enabled source cache。不同子系统对配置变化的响应不同：

- 一部分 UI 设置可立即重绘；
- tool/MCP/plugin 变化会触发 registry 或 cache invalidation；
- provider/auth/client 对象常需要重新构造；
- policy helper 可以按 refresh interval 更新；
- project trust 改变后，之前被阻止的 helper/hook/MCP 才能进入装载；
- background agent 已复制的上下文不会自动等同于主会话最新状态。

跨版本比较必须关注 lifecycle，而不仅是新增 key。新增字段但未接入 reload path，和运行中可刷新是两种不同能力。

## 典型故障定位

### “我改了 project settings，但 sandbox 还是没关”

先看该字段是否明确忽略 project/local，再看 managed policy 是否已配置 filesystem restrictions。对这类字段，改 project 文件本来就不会生效。

### “更具体的 allow 为什么赢不了 deny”

settings source 只决定规则集合；permissions 仍按 deny、ask、allow 顺序裁决。具体度不改变阶段顺序。

### “设置了 flag，命令还是不存在”

检查 provider、account/org capability、command registration 和 protocol gate。flag key 存在不是成功 probe。

### “企业配置偶尔消失”

检查 policy helper refresh、timeout、fallback payload、上次有效值策略和日志事件；不要只检查启动时文件。

## 用户影响与成本

- 设置来源过多会提高诊断成本，因此 UI/doctor 应展示最终值与来源，而不是只展示值。
- project-local 可写配置若能触及高风险字段，会形成供应链入口；本版对多项 sandbox 字段做了来源隔离。
- managed-only 限制提高安全性，但错误 policy 也可能让 CLI fail closed，部署前需要 staged validation。
- feature flag 动态化便于灰度，但会让同一版本不同账户行为不同；版本归档必须保存 bundle default 和 probe 环境边界。
- env 注入可能把凭据传播到子进程；源码因此维护 credential/environment 分类与 scrub 路径。

## 微小但关键的特性

- `--setting-sources` 不接受 `policy` 作为可删除来源，policy 始终加入。
- local settings 被标成 project scope、gitignored，不等于 user settings。
- `strictAllowlist` 只约束 sandboxed commands；in-process `WebFetch` 需要自己的权限控制。
- filesystem isolation 关闭时，network isolation 仍可保留；这两层不能合并成一个“sandbox on/off”。
- `allowAppleEvents` 会显著改变 macOS 隔离边界，默认 false 且不接受项目配置。
- `failIfUnavailable` 决定 sandbox 不可用时是 warning 后继续还是启动失败。
- `DISABLE_AUTOUPDATER` 既有历史环境路径，也有 settings 迁移路径。

## 证据与边界

结构化证据条目：`settings.layer-order`、`settings.managed-sandbox-gates`、`update.settings-migration`。字段目录见 [root-settings-schema.jsonl](source-inventory/root-settings-schema.jsonl)，但 schema 行只证明声明；每个高风险字段仍要回到实际读取、merge 和执行分支验证。

客户端能证明本地 precedence、source restrictions 和 policy hook。组织后台如何下发 entitlement、服务端如何做账户风控、某个用户实时拿到什么 flag 不在静态 bundle 内，必须保留为运行时或服务端边界。
