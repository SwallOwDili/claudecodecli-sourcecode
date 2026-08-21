# Claude Code CLI 2.1.235 安装、更新、Doctor 与版本生命周期

版本归档不能只保存 `claude --version`。Claude Code 的安装生命周期决定“正在运行的到底是哪一个字节文件”、更新能否原子切换、旧版本是否仍可回退、native module 与主 bundle 是否匹配，以及 doctor 看到的是 PATH、symlink、签名、权限还是 provider 配置问题。

## 60 秒理解版本生命周期

**读者问题：** `claude --version` 显示 `2.1.235` 时，怎样证明正在运行的是哪个文件；自动更新失败或回退后，又为什么不能只改一个 symlink 就宣布完成？

**一句话模型：** PATH 入口必须先解析到真实版本文件并核对 hash、签名和架构；更新器在策略允许时下载、校验并切换入口；Doctor 按故障域检查安装与运行依赖；回退还要验证 settings、transcript 和 native module 的向后兼容。

![Claude Code 从 PATH 入口解析真实版本文件，经更新切换、Doctor 检查和回退验证形成完整生命周期](visuals/release-lifecycle.svg)

贯穿场景：PATH 中的 `claude` 指向当前 launcher，真实文件位于版本目录。更新器发现新 channel 版本后下载并切换入口，但新版本 native module 装载失败。Doctor 必须同时核对 resolved path、主文件 hash/签名、Bun payload 与 `.node` 匹配；回退到 `2.1.235` 后还要确认新版本写入的 settings 或 transcript 没有让旧版解析失败。

| 对象 | 更新前 | 转换 | 更新/回退后 | 验证重点 |
| --- | --- | --- | --- | --- |
| PATH entry | launcher/symlink | 安装器原子切换目标 | 指向新或旧真实版本 | 不能只看入口文件内容 |
| Real version file | 固定 bytes、hash、signature、arch | 下载与完整性校验 | 可重复识别的发布物 | `--version`、SHA-256、签名一致 |
| Embedded/native payload | 主 bundle 与 5 个 `.node` 成套 | 随版本整体更换 | 加载同一 release 的 ABI | 不能混用旧 native module |
| Settings/transcript | 旧 schema 与持久数据 | 新版本可能迁移或新增字段 | 回退时仍要可解析 | 二进制回退不等于数据降级 |
| Update/Doctor state | channel、policy、last check、faults | 查询、安装、诊断、提示 | 明确成功或具体故障域 | 禁止安装、禁止检查、隐藏命令要区分 |

后文先解释 `2.1.235` 发布物与安装状态机，再进入更新 gate、Doctor 故障域和回滚边界；每一步都以真实版本文件为基准。

## 2.1.235 发布物形态

本快照的目标是 macOS arm64 Bun standalone executable：

- 一个 313,334,608 字节的主可执行文件；
- 主入口内嵌 Bun module graph、JSC bytecode、JavaScript、assets 和 5 个 `.node`；
- 安装目录以版本号保存真实文件；
- PATH 中的 `claude` 入口可以是指向当前版本的 launcher/symlink；
- `.node` 通过 `/$bunfs/root/...` 从 standalone 虚拟文件系统加载。

精确事实保存在 [version.json](version.json) 和 [unpack-manifest.json](unpack-manifest.json)。归档前必须 resolve symlink，再对真实版本文件计算 SHA-256。只 hash PATH 入口可能记录的是短 launcher，而不是发布物。

## 安装状态机

```text
下载/安装 release
      |
      v
写入版本目录中的 immutable candidate
      |
      v
校验格式、架构、签名、版本与可执行性
      |
      v
切换 current launcher/symlink
      |
      v
启动时 installation checks / migrations
      |
      v
运行 session
      |
      +--> update check --> 下载新 candidate --> 下次切换
      |
      +--> doctor --> 检查安装与配置故障
```

真正可靠的 updater 应把“下载完整文件”和“切换当前版本”分开。否则中途退出会留下半写可执行文件。快照仓库不直接证明安装器内部每一步的原子实现，但版本目录 + current entrypoint 的形态说明归档时必须分别记录 candidate 和当前选择。

## 为什么版本号不够

同一个 `2.1.235` 文本仍需要核对：

- SHA-256；
- size；
- Mach-O container 与 CPU architecture；
- code signature；
- embedded build time/Git SHA；
- module manifest hashes；
- JSC bytecode 与 readable-view hash；
- native slice/exports/dependencies。

本仓库正向探针使用的二进制 SHA-256 是 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748`。探针脚本显式选择版本文件，而不是相信当前 PATH 永远不变。

## Auto-update 持有什么状态

Auto-update 至少需要：

- 当前版本和发布 channel；
- 上次检查时间；
- 是否禁用更新/自动安装；
- 下载中的 candidate；
- 安装方式与可写权限；
- 是否需要 sudo/npm 外部安装；
- 强制安装窗口或延后状态；
- 更新失败原因与重试节奏。

2.1.235 同时保留 `DISABLE_AUTOUPDATER`、`DISABLE_UPDATES`、settings 中的 auto update 状态和更新命令 surface。`reverse/javascript/cli.readable.js` 595195-595206 会把旧 `autoUpdates: false` 迁移到 user settings 的 `env.DISABLE_AUTOUPDATER=1`，成功时清理旧字段，失败时保留错误 telemetry。

这段迁移说明：同一行为可能经历 schema 演进。跨版本比较不能只看新 key 是否新增，还要看旧 key 是否仍读取、何时迁移、写失败时是否保留兼容。

## `DISABLE_AUTOUPDATER` 与 `DISABLE_UPDATES` 不应混写

两个名字表达的范围不同：

- `DISABLE_AUTOUPDATER` 停止后台 update check/install，但手动 `claude update` 与 `claude install` 仍可使用；
- `DISABLE_UPDATES` 阻断包括手动命令在内的全部客户端更新路径；
- `DISABLE_UPGRADE_COMMAND`、`DISABLE_DOCTOR_COMMAND` 只控制命令 surface；
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 会影响 update check 和 feature evaluation，但不等价于管理员锁定所有更新命令。

这组范围同时由当前官方 Setup 文档和本版运行 Probe 交叉验证。面向企业部署时仍要区分“客户端不更新”和“IT 已经通过其他渠道强制分发”；前者不自动推出后者。

## Doctor 不是一个健康布尔值

`claude doctor` 的价值是把多个故障域分开：

| 故障域 | 典型检查 |
| --- | --- |
| 安装 | PATH、launcher、版本文件、写权限、旧 npm 安装 |
| 平台 | OS/arch、native dependencies、sandbox runtime |
| 更新 | 是否能检查/下载/切换、auto update 配置 |
| 配置 | settings parse error、未知字段、source conflict |
| 信任 | workspace trust、project MCP/helper/hook 是否被阻止 |
| Provider | selector、region/project、endpoint、credentials |
| MCP | config、连接、auth、list discovery |
| IDE | extension/command/socket/status |
| 风控 | sandbox availability、managed policy、permission mode |

readable JS 583492 保留“Claude Code can't auto-update · run `claude doctor`”；594139 还在 project MCP approval 因 settings error 被跳过时要求用 doctor 列出错误。这证明 doctor 是聚合诊断入口，而不是只检查 binary version。

当前官方 [Setup](https://code.claude.com/docs/en/setup) 把 `claude doctor` 定义为不启动 session 的只读安装与 settings 诊断，对应 `public.doctor-readonly`。`probe.lifecycle-doctor-update` 又在隔离环境中加入损坏 JSON settings、自定义 endpoint、禁用 auto updater 与非必要流量，真实输出同时识别 native `2.1.235`、commit `ba01fa45e3d1`、`darwin-arm64`、bundled search、auto-update gate、invalid settings 和 Remote Control 不可用原因。

同一探针执行 `DISABLE_UPDATES=1 claude update`，literal output 为 `Updates are disabled by your administrator. Contact your IT team to get the latest version.`，exit 0。这里 exit 0 表示管理员禁用策略被正常处理，不表示更新已经完成。

## Installation checks 与 command gates

环境清单包含 `DISABLE_INSTALLATION_CHECKS`、`DISABLE_DOCTOR_COMMAND`、`DISABLE_UPGRADE_COMMAND` 等开关。它们的存在不意味着用户应该普遍关闭检查；它们允许托管环境或测试 harness 调整启动行为。

需要区分：

- **不运行检查**：可能减少启动时间，但也不再提示错误安装；
- **隐藏命令**：只改变 surface，不自动修复底层问题；
- **关闭自动更新**：保留手动/IT 分发；
- **关闭所有更新流量**：可能同时失去安全修复提醒。

快照验证应在 nonessential traffic 关闭的隔离环境运行，避免 validator 意外联网或改变当前安装；但发布文档必须说明这不是普通用户的默认运行状态。

## Native module 与主版本必须成套

Standalone 中的 `.node` 由主 executable 内嵌和加载。混用不同版本的 JavaScript 与 native module 会产生：

- 导出缺失；
- N-API shape 不匹配；
- 参数/返回 schema 漂移；
- Rust/Swift runtime 或 framework 依赖不匹配；
- universal slice 与当前架构不匹配。

本仓库的 `extracted/` 保存同一个发布物的成套字节；`reconstructed/` 是独立兼容实现，不能放回版本目录覆盖原模块。动态加载器还可能持有已映射 Mach-O，原地替换已加载文件会造成不可预测行为。

## 回退与回滚边界

安装级 rollback 是把 current launcher 指回旧的完整版本文件；session rollback 是 resume/rewind；代码 rollback 是 Git 或 file checkpoint。它们不能混用：

- 切回旧 CLI 不会自动降级新版本写过的 settings/transcript schema；
- file checkpoint 不会恢复安装文件；
- resume 不会撤销 updater 已完成的切换；
- old binary 可能无法理解新版本 session metadata。

长期版本库应保留每个版本的 schema/CLI/probe 证据，以便在回退前检查兼容，而不是只保留 executable。

## 版本归档的可重复流程

1. resolve `command -v claude` 到真实版本文件；
2. 记录 `--version`、size、SHA-256、container、arch、signature；
3. 复制/读取发布物，前后复核原 hash；
4. 提取 module graph，不改变 packed bytes；
5. 生成 deep reverse、native indexes 和 source inventory；
6. 用精确版本文件执行离线 probe；
7. 校验隐私，不提交捕获机器路径；
8. 以数字版本为 branch；
9. push 后从远端新鲜 checkout 再跑 validator。

这套流程已经固化在仓库内 [claude-code-version-diff skill](../skill/claude-code-version-diff/SKILL.md)。

## 微小但关键的特性

- PATH 中 `claude --version` 正确，不代表 hash 与目标快照一致。
- update setting migration 写失败时应保留旧值，不能留下“两个字段都清空”的中间状态。
- 禁用 auto updater 不等于禁用手动 update，也不等于已有 IT 分发。
- doctor 会关联 settings error 与 MCP approval，被跳过的审批不应被误判为 MCP server 不存在。
- native module 是 release set 的一部分，不能按文件名跨版本拼装。
- `--version` probe 应使用隔离 HOME，避免启动 migrations 污染真实配置。
- rollback 后还需验证 settings/transcript 兼容，不只是可执行文件能启动。

## 证据与边界

结构化证据条目：`update.settings-migration`、`native.bundle-entrypoints`、`public.doctor-readonly`、`public.disable-updates`、`probe.exact-binary-identity`、`probe.lifecycle-doctor-update`。发布物身份由 [version.json](version.json)、[unpack-manifest.json](unpack-manifest.json) 和 runtime probe 共同证明。命令、literal output、exit status 和 doctor 字段逐项解释见 [精确二进制运行证据指南](runtime-probe-index.md)。

本地 bundle 能证明 update/doctor command surface、配置迁移和错误文案。下载服务、release channel 后端、签名发布流水线和 updater 服务端策略不在客户端快照内；它们需要独立网络捕获或官方发布基础设施证据。
