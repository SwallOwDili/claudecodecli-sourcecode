# 安装、更新、Doctor 与版本生命周期

版本归档不能只保存 `claude --version`。Claude Code 的安装生命周期决定“正在运行的到底是哪一个字节文件”、更新能否原子切换、旧版本是否仍可回退、native module 与主 bundle 是否匹配，以及 doctor 看到的是 PATH、symlink、签名、权限还是 provider 配置问题。

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

- `DISABLE_AUTOUPDATER` 面向自动安装/自动切换；
- `DISABLE_UPDATES` 更可能抑制更新检查或更新相关流量/surface；
- `DISABLE_UPGRADE_COMMAND`、`DISABLE_DOCTOR_COMMAND` 控制命令 surface；
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 还可能间接关闭更新检查。

具体版本必须检查调用点后再描述。不能看到一个“disable update”字符串，就写成所有 update 行为都停止。面向企业部署时还要区分“客户端不自动更新”和“IT 有自己的强制分发”。

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

结构化证据条目：`update.settings-migration`、`native.bundle-entrypoints`。发布物身份由 [version.json](version.json)、[unpack-manifest.json](unpack-manifest.json) 和 runtime probe 共同证明。

本地 bundle 能证明 update/doctor command surface、配置迁移和错误文案。下载服务、release channel 后端、签名发布流水线和 updater 服务端策略不在客户端快照内；它们需要独立网络捕获或官方发布基础设施证据。
