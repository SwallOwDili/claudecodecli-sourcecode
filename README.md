# Claude Code CLI 2.1.235 深度逆向快照

本分支是 Claude Code CLI `2.1.235` 的完整发布产物逆向快照。它不是 Anthropic 内部原始 TypeScript 仓库的镜像，而是从实际发布的签名 Mach-O 可执行文件中，把仍然存在的内容最大化恢复并分类保存：逐字节 Bun 模块图、完整 JSC bytecode、可读化 JavaScript 分析视图、5 个原生模块的多架构静态分析、稳定字符串/配置/端点/风控索引，以及可长期复用的跨版本对比 skill。

`extracted/` 永远保存未格式化、未改名的原始打包字节；`reverse/` 保存从这些字节生成的分析视图。两者不能互相替代。

## 先读什么

这个仓库同时服务两类读者：人需要理解系统为什么这样设计，比较器需要稳定、无遗漏地逐版本 diff。不要从 70 个 JSONL/TXT 文件开始读，也不要把字段数量当成技术分析。

| 入口 | 解决的问题 |
| --- | --- |
| [`analysis/technical-mechanism-atlas.md`](analysis/technical-mechanism-atlas.md) | **首选入口**：一次请求跨越的九个子系统、三条闭环、状态归属、故障表现和专题阅读路由 |
| [`analysis/public-claims-validation.md`](analysis/public-claims-validation.md) | 官方 Claude Code/Agent SDK/Engineering 原理与 `2.1.235` bundle、精确二进制探针逐项对照，防止版本倒灌 |
| [`analysis/technical-architecture.md`](analysis/technical-architecture.md) | 从用户输入到 system prompt、工具、API、权限、compact、transcript 和遥测的完整架构图 |
| [`analysis/agent-loop.md`](analysis/agent-loop.md) | Agent Loop 状态机、流中工具执行、并发屏障、工具结果反馈、Stop hook、maxTurns、fallback 和子 Agent |
| [`analysis/context-governance-and-caching.md`](analysis/context-governance-and-caching.md) | 上下文装配、多层缓存、5m/1h TTL、tool search、microcompaction、auto-compact、resume 和成本算例 |
| [`analysis/sessions-checkpoints-memory.md`](analysis/sessions-checkpoints-memory.md) | message graph、JSONL、compact boundary、resume/fork、100 个 file checkpoint、rewind 与 `MEMORY.md` 边界 |
| [`analysis/tools-permissions-hooks.md`](analysis/tools-permissions-hooks.md) | 工具从 schema 到 call 的完整控制管线，六种 permission mode、hooks、sandbox、凭据与企业 policy |
| [`analysis/mcp-agents-background.md`](analysis/mcp-agents-background.md) | MCP 动态工具表、Tool Search、子 Agent 独立上下文、后台任务、task claim、mailbox 与 worktree |
| [`analysis/resilience-and-recovery.md`](analysis/resilience-and-recovery.md) | API retry、流式降级、模型 fallback、输出修复、reactive compact、resume、rewind 与副作用边界 |
| [`analysis/telemetry.md`](analysis/telemetry.md) | 一方事件、OTEL、Datadog、GrowthBook、错误上报、本地日志、队列、重试和隐私门 |
| [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md) | `comparisonKey`、payload spread、settings/env/model/遥测字段分别是什么意思 |
| [`analysis/source-surface.md`](analysis/source-surface.md) | 按全产品能力面查证据，区分 Observed、Derived、Compatible 和 Heuristic |

一次主线程请求的实际路径可以概括为：

```text
输入/resume JSONL
  -> 恢复会话消息图
  -> 装配固定 system prompt + 动态机器/项目上下文
  -> 装配内置工具、MCP、skills、commands、agents
  -> 延迟不需要的工具 schema
  -> 规范化消息并执行 permission/policy/hook/sandbox 门控
  -> 切分 stable/org system 前缀并插入消息 cache breakpoint
  -> 构造 model/beta/thinking/tools/context-management 请求
  -> Agent Loop 流式解析 content block
  -> tool_use block 完成即进入并发/串行执行器
  -> schema、hook、permission、sandbox 门控后执行
  -> tool_result 按 ID 回灌，决定结束或下一轮模型请求
  -> 写 usage、telemetry、JSONL transcript
  -> 需要时清理旧 tool result、预计算或执行 compact
  -> 写 compact boundary，供下次 resume 修复逻辑消息链
```

这里的“多层缓存”不是一个模糊名词：进程内工具 schema/model config cache 降低本地重复计算；API prompt cache 复用 system/message 前缀；tool search 避免未使用 schema 常驻；precomputed compact cache 提前准备摘要。Transcript 和 memory 是持久状态，不是 prompt cache。每层的命中、失效和费用影响见上下文专题。

每个重要机制都按同一合同解释：它解决什么问题，拥有哪份状态，从哪里进入，调用链按什么顺序执行，受哪些 gate/优先级控制，默认值和阈值是什么，成功与失败各留下什么，什么时候失效，用户在质量、延迟、token、费用、隐私、安全和恢复上会感受到什么，以及哪些结论仍属于服务端或版本边界。公开资料只用于提出假设；本版本结论必须回到 `2.1.235` bundle 或同哈希二进制探针。

## 快照信息

| 项目 | 值 |
| --- | --- |
| Git 分支 | `2.1.235` |
| 本机 CLI 输出 | `2.1.235 (Claude Code)` |
| 原始程序 | arm64 Mach-O，`313,334,608` 字节 |
| 原始程序 SHA-256 | `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748` |
| 代码签名 | Anthropic PBC，Team ID `Q6L2SF6YDW` |
| Bun 载荷 | 从文件偏移 `69,107,720` 开始，共 `243,390,734` 字节 |
| 模块表 | 15 个文件，每项 52 字节 |
| 实际解包内容 | `38,648,719` 字节 |
| 主 JavaScript | `27,305,344` 字节，65,943 行 |
| 主源码 SHA-256 | `22642ddc2aa33ff16a5ee3c5a5bffb14f03c270f0047b4e5e40ba6a22efbeb8e` |
| JSC bytecode | `204,740,576` 字节，SHA-256 `7b21c8166859f877db611d1aa3b22754b1777faa878b4ab58bb752f0f432da59` |
| bytecode 提交形式 | gzip `47,461,235` 字节，SHA-256 `8f846bf9698cb7d998e951d18b10b36e2ee8ea0d85d136a7b5d671926192d611` |
| 可读化 JavaScript | `34,418,467` 字节，638,179 行，SHA-256 `99c8608118d643802dbca7bf86b031bb3f565fb78bad093494a841de3e6783b4` |
| 原生模块逆向 | 5 个 `.node`，共 7 个架构 slice |
| 解包工具 | `bun-unpacker 0.10.1`，提交 `a1bdf5488e16b41792062d60bb52d72c1c5326ea` |
| 解包模式 | `--path-patching false`，不改写打包字节 |

完整机器可读记录见 [`analysis/version.json`](analysis/version.json)。所有内嵌文件的偏移、大小、类型和哈希见 [`analysis/unpack-manifest.json`](analysis/unpack-manifest.json)。

## 目录结构

```text
.
|-- VERSION
|-- README.md
|-- extracted/
|   |-- cli.js                         Claude Code 主应用 bundle
|   |-- *-processor.js / *-capture.js 原生模块加载器
|   |-- *.node                         图像、音频、URL、Computer Use 原生桥接
|   |-- chart.umd.min.js               Chart.js 渲染运行时
|   |-- hljsBundle.generated.min.js    Highlight.js 语法高亮运行时
|   |-- mermaid.min.js                 Mermaid 渲染运行时
|   `-- payload.template.html.asset    Artifact/报告使用的 HTML 载荷
|-- analysis/
|   |-- version.json                   二进制与解包元数据
|   |-- unpack-manifest.json           每个文件的偏移和哈希
|   |-- release-notes.md               2.1.235 官方变更记录
|   |-- cli-surface.txt                用于 diff 的标准化 CLI 表面
|   |-- risk-control-surface.txt        权限、沙箱、凭据和企业策略风控表面
|   |-- technical-mechanism-atlas.md    九层运行机制总图与问题导向阅读路由
|   |-- public-claims-validation.md     官方原理、bundle 证据和运行探针对照
|   |-- technical-architecture.md       面向人的完整技术架构导读
|   |-- agent-loop.md                   Agent Loop 状态机、工具调度和终止语义
|   |-- context-governance-and-caching.md 上下文治理、多层缓存、压缩与恢复
|   |-- sessions-checkpoints-memory.md  会话图、JSONL、checkpoint、rewind、memory
|   |-- tools-permissions-hooks.md       工具合同、权限、hooks、sandbox、policy
|   |-- mcp-agents-background.md        MCP、Tool Search、Agents、task 与 mailbox
|   |-- resilience-and-recovery.md      retry/fallback/compact/resume/副作用恢复
|   |-- telemetry.md                   遥测、日志、重试、隐私和诊断架构
|   |-- inventory-field-guide.md        JSONL/settings/env/model/遥测字段字典
|   |-- source-surface.md              全产品能力面和证据边界
|   `-- source-inventory/              70 类确定性机器清单及逐文件哈希
|-- reverse/
|   |-- summary.json                   深度逆向机器摘要
|   |-- manifest.json                  全部派生产物的大小与 SHA-256
|   |-- bytecode/                      完整 JSC bytecode 与字符串
|   |-- javascript/                    可读化 JS 分析视图
|   |-- index/                         稳定标识符和原生 API 对比索引
|   `-- native/<module>.node/<arch>/   符号、依赖、段表和反汇编
|-- reconstructed/                    5 个原生模块的可编译 Rust/Swift 兼容重建
`-- skill/claude-code-version-diff/    可复用的快照、深度逆向与版本对比 skill
```

## 机器证据层：一次性全量静态提取

下面的计数表是完整性索引，不是阅读入口。字段含义先看 [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md)，系统行为先看上面的机制总图和专题文档。

除 packed bytes、bytecode、native reverse 和人工能力说明外，本分支还从 canonical `extracted/cli.js` 确定性生成 70 类机器清单。清单不是挑选出来的“亮点”，而是后续每个版本必须重跑和逐项 diff 的归档合同。

| 能力面 | 本版本计数 | 机器证据 |
| --- | --- | --- |
| 环境访问 | 并集 1,300；2,548 个逐调用点记录；dynamic `process.env[...]` 143；typed schema 842；观测 schema 71、默认表达式 23 | [`environment-access-callsites.jsonl`](analysis/source-inventory/environment-access-callsites.jsonl)、[`environment-schema.jsonl`](analysis/source-inventory/environment-schema.jsonl) |
| 一方遥测 | `H` 2,162、`Fv` 32，共 2,194 个调用点；静态事件 1,436；动态模板 3；event-field 1,411；`tengu_*` 1,939 | [`first-party-event-callsites.jsonl`](analysis/source-inventory/first-party-event-callsites.jsonl)、[`first-party-events.txt`](analysis/source-inventory/first-party-events.txt) |
| 第三方观测 | OTEL event 26、metric 8、span 10；Datadog allowlist 181、tag 34、删除字段 26 | [`third-party-otel-events.txt`](analysis/source-inventory/third-party-otel-events.txt)、[`otel-metrics.tsv`](analysis/source-inventory/otel-metrics.tsv)、[`datadog-forwarded-events.txt`](analysis/source-inventory/datadog-forwarded-events.txt) |
| 动态观测调用 | `Nd` 52；feature `et` 498；GrowthBook `CB` 12；动态/变量参数和 unresolved spread 全部保留 | [`otel-event-callsites.jsonl`](analysis/source-inventory/otel-event-callsites.jsonl)、[`feature-flag-callsites.jsonl`](analysis/source-inventory/feature-flag-callsites.jsonl)、[`growthbook-callsites.jsonl`](analysis/source-inventory/growthbook-callsites.jsonl) |
| Settings/schema | 根 settings 156 direct + 4 spread；typed env 842；schema property 1,971；description 1,150；enum group 201 | [`root-settings-schema.jsonl`](analysis/source-inventory/root-settings-schema.jsonl)、[`environment-schema.jsonl`](analysis/source-inventory/environment-schema.jsonl) |
| 工具与命令 | built-in tool 29；known-tool catalog 188；named component 182；slash command 103 | [`known-tool-catalog.txt`](analysis/source-inventory/known-tool-catalog.txt)、[`slash-command-identifiers.txt`](analysis/source-inventory/slash-command-identifiers.txt) |
| 协议与 hooks | SDK control subtype 89；output protocol event 44；hook event 31 | [`sdk-control-subtypes.txt`](analysis/source-inventory/sdk-control-subtypes.txt)、[`hook-events.txt`](analysis/source-inventory/hook-events.txt) |
| 模型与 beta | 完整 model catalog 17；pricing tier 6；alias 4；model literal 37；date-suffixed beta/API version 53 | [`model-catalog.jsonl`](analysis/source-inventory/model-catalog.jsonl)、[`model-pricing-tiers.jsonl`](analysis/source-inventory/model-pricing-tiers.jsonl) |
| API/runtime | API path 99；API/path template 119；HTTP method route 19；runtime require 54 | [`api-paths.txt`](analysis/source-inventory/api-paths.txt)、[`api-path-templates.jsonl`](analysis/source-inventory/api-path-templates.jsonl) |
| 存储 | Claude storage namespace 29；全 bundle namespace 41；用户配置目录名 13 | [`claude-storage-namespaces.txt`](analysis/source-inventory/claude-storage-namespaces.txt)、[`storage-namespaces.txt`](analysis/source-inventory/storage-namespaces.txt) |
| 错误与诊断 | Error/TypeError/RangeError 调用 4,831，其中模板参数 1,526；`T()` 调用 5,403，其中模板参数 4,438 | [`error-message-callsites.jsonl`](analysis/source-inventory/error-message-callsites.jsonl)、[`diagnostic-message-callsites.jsonl`](analysis/source-inventory/diagnostic-message-callsites.jsonl) |
| 全词法表面 | quoted string 260,838 次、85,095 个唯一值；template 30,114 次、25,187 个唯一值 | [`static-string-literals.jsonl`](analysis/source-inventory/static-string-literals.jsonl)、[`template-literals.jsonl`](analysis/source-inventory/template-literals.jsonl) |
| 网络 | URL 557；URL template 236；API/path template 119；归一化 endpoint host 179 | [`urls.txt`](analysis/source-inventory/urls.txt)、[`url-templates.jsonl`](analysis/source-inventory/url-templates.jsonl)、[`endpoint-hosts.txt`](analysis/source-inventory/endpoint-hosts.txt) |

70 类清单的逐项表、定义和证据等级见 [`analysis/source-surface.md`](analysis/source-surface.md)，字段逐项解释见 [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md)。v3 提取器固定使用仓库内置 Acorn `8.15.0` 解析整个 canonical bundle，精确定位调用、参数、词法作用域、赋值、字符串、模板和环境访问；JSONL 用稳定的 `comparisonKey` / `comparisonValue` 做跨版本语义比较，offset/line 只作定位证据。环境、schema、namespace、named component 等广义集合会混入依赖和内嵌文档，因此仍明确标为 heuristic/candidate。

`summary.json` 的完成审计确认：目标调用点全部记录、全部词法字符串/模板均计数、动态表达式保留、根 settings 的 key 与结构化行一致、模型目录完整解析，`knownStaticExtractionGaps` 为空。这里的“完成”指发布 bundle 中仍存在的静态信息；远程配置返回值、用户文件/环境的运行时值、服务端规则，以及构建前已经删除的源码不在发布产物中。

校验器会在临时目录重新执行提取器，比较 `summary.json`、canonical source hash、文件集合、每个文件内容、行数、大小和 SHA-256。手改清单、漏跑生成器或 source 变化后未更新清单都会失败。

## 完整逆向包含什么

### 1. 原始 Bun 模块图

`extracted/` 是最重要的保真基线。15 个文件全部按可执行文件中的 packed bytes 保存，清单哈希逐项一致：主应用 bundle、5 个原生 loader、5 个 `.node`、Chart.js、Highlight.js、Mermaid 和 HTML payload。主模块没有经过 prettier、变量改名或人工拆分。

### 2. 完整 JSC bytecode

`reverse/bytecode/cli.jsc.gz` 是可执行文件偏移 `69,107,840` 处、长度 `204,740,576` 的完整 JavaScriptCore bytecode cache，使用 gzip level 9、mtime 0 确定性压缩。校验器会流式解压并重新计算原始 SHA-256，证明提交文件可以无损恢复原 bytecode。

同时保存 `strings.txt.gz`，用于搜索 JSC 中保留的函数名、配置键、错误消息和运行时标识符。bytecode 是和 Bun/JSC 版本、CPU 架构绑定的执行缓存，不是另一份 TypeScript 源码，但它是发布程序实际携带内容的一部分，现已完整纳入快照。

### 3. 可读化 JavaScript

`reverse/javascript/cli.readable.js` 使用 `esbuild 0.25.10` 对原始 bundle 重新解析并展开为 638,179 行，便于定位调用链、分支和常量。它的角色是分析视图，原始比较基线仍然是 `extracted/cli.js`。

解析验证确认可读版和原始版的 538 个 `ANTHROPIC_*`/`CLAUDE_CODE_*` 标识符集合一致，endpoint host 集合一致。esbuild 可重新解析生成文件，并保留了原 bundle 的 3 个静态警告：一个永远不成立的 `typeof x === "null"` 分支、两个重复的 DOM class member。stock Node 的语法检查不适用于 bundle 中 Bun 支持的 `using` 语法。

### 4. 五个原生模块

每个 `.node` 都保存了文件类型、UUID、签名状态、Mach-O header/load commands、动态库依赖、导入/导出符号、完整符号表、字符串、Objective-C runtime 数据、间接符号和 text section 反汇编。universal 文件分别分析 x86-64 和 arm64：

- `audio-capture.node`：arm64 Rust/N-API 模块。字符串恢复出录音、播放、状态查询、写入播放数据和麦克风授权接口，并能看到 CoreAudio/AudioUnit 调用。
- `image-processor.node`：arm64 Rust/N-API 模块。恢复出 `process_image`、`ImageProcessor`、剪贴板图像读取/探测、resize/fit/withoutEnlargement、JPEG/PNG/GIF/TIFF/WebP 等格式路径和 CoreGraphics/ImageIO 依赖。
- `url-handler.node`：arm64 Rust/N-API 模块。恢复出 `wait_for_url_event` / `waitForUrlEvent` 和 macOS Apple Event handler 路径。
- `computer-use-input.node`：x86-64 + arm64 Rust/N-API 模块。恢复出文本输入、按键按下/释放/组合键、鼠标移动/按钮/滚轮/位置和辅助功能权限处理，底层直接导入 `CGEvent*`。
- `computer-use-swift.node`：x86-64 + arm64 Swift/N-API 模块。每个 slice 保留 1,237 个 Swift 符号；demangle 后可以看到屏幕区域捕获、窗口/显示器选择、允许应用过滤、JPEG 质量、缩放结果、已安装应用、ESC event tap 和 bundle ID 解析等实现结构。

### 5. 可跨版本稳定索引

`reverse/index/` 不是简单的全文字符串 dump，而是用于版本差异的归一化集合：

- 环境变量和 feature identifiers；
- 完整 URL 与 endpoint host；
- probable dotted config keys（启发式集合，单独标明，不冒充 schema）；
- 打包残留的源码/构建路径；
- 原生架构、依赖、全部 import/export、N-API import；
- 仅属于 `ComputerUseSwift` 的 demangled project symbols；
- 标准化 CLI option/command surface。

地址变化和整块反汇编变化噪声很大；长期对比优先使用这些索引，再回到压缩的完整报告确认实现细节。

### 6. 可编译的原生源码重建

[`reconstructed/`](reconstructed/) 在静态逆向证据之上，提供 5 个 `.node` 模块的可编译 Rust/Swift 重建：4 个 Rust crate 和 1 个 Swift Package。它们不是从调试信息直接导出的原文件，而是按 `Observed`、`Derived`、`Compatible` 三类证据编写，并用原版模块做接口与行为双跑。

已经恢复和验证的细节包括：

- 5 个模块的完整 N-API 导出和 `computerUse` 嵌套对象树；
- 图像链式 API、一次性消费错误，以及固定输入 JPEG/PNG/WebP 的逐字节一致输出；
- 输入模块空组合键、非法 key/action/button/axis 的原版错误文本；
- AVFoundation 麦克风授权查询、NSWorkspace 前台应用、GURL Apple Event 超时；
- Spotlight 本地化应用列表、重复项保留、64x64 PNG 图标、窗口命中和隐藏预览；
- ScreenCaptureKit 全屏/区域截图的 Promise、字段、尺寸和裸 JPEG base64。

验证脚本每次创建新的 `.node` 加载目录，不覆盖已映射的 Mach-O：

```bash
reconstructed/scripts/build_and_validate.sh extracted /tmp
```

当前 arm64 macOS 实测为 5 个模块契约通过、23 项行为双跑通过。详细源码边界和逐模块证据见 [`reconstructed/EVIDENCE.md`](reconstructed/EVIDENCE.md)。

## 2.1.235 的版本变化

### 输入框拼写检查

本版本增加了可选的实时拼写检查。实现可在 [`extracted/cli.js`](extracted/cli.js) 中检索 `spellcheck`、`aspell`、`hunspell` 和 `ispell`：

- 自动按 `aspell`、`hunspell`、`ispell` 顺序探测，也支持显式指定检查器。
- 配置包含 `spellcheck.enabled`、`spellcheck.checker`、`spellcheck.language` 和 `spellcheck.color`。
- `language` 只接受普通词典名称，并分别传给 `aspell --lang`、`hunspell -d` 或 `ispell -d`。
- 拼错的单词会显示下划线，颜色支持终端颜色名、RGB/hex、ANSI-256 和 ANSI 命名颜色。
- 检查器以长驻子进程运行，使用 Ispell `-a` 协议，不会为每个单词启动一个新进程。
- 对响应设置超时；慢批次会被跳过；进程失败后重启一次；连续失败后只关闭本次会话的拼写检查。
- 项目级和 local 级 `spellcheck` 配置会被忽略，这项配置被限定为用户级设置。

### Prompt Cache 与 LSP

语言服务器在会话中途断开或重连时，不再让整个 prompt cache 失效。LSP 在线状态属于机器动态状态，而长会话中稳定、昂贵的 prompt 前缀可以继续复用。

### 终端渲染与输入正确性

- Markdown 列表在第 3 层及更深层级时能够正确对齐。
- 自动换行的列表项使用悬挂缩进。
- 多行输入中的 slash command、关键词和 mention 高亮不再发生字符偏移。
- 快速按方向键后紧接 Enter，会选择屏幕上当前高亮项，不再选择旧状态。
- Vim NORMAL 模式和光标位置在切换详细 transcript 或关闭面板后保持不变。
- Claude 回复过程中执行 slash command 时，HTML entity 会被还原成实际字符。

### 权限与审批

- 在权限弹窗的备注输入框中按 Shift+Tab，只关闭输入框，不再误触发编辑批准并授予整次会话编辑权限。
- 权限弹窗的说明文字、授权范围和 `don't ask again` 选项保持一致。
- 当提议内容无法完整展示时，不提供持久授权选项。
- Notebook 单元格删除/替换审批无法读取旧内容时，会明确说明原因，不再静默省略旧内容。

### Agent、云任务与跨会话消息

- 当会话中不存在通用默认 Agent 时，省略 `subagent_type` 会明确报错并列出可用 Agent。
- `/ultrareview`、`/autofix-pr` 等后台云任务不再在每次更新时重新扫描和渲染完整事件流，降低长任务的 CPU 和内存增长。
- `SendMessage` 在发送前检查跨会话消息大小，超限时返回可见错误，不再静默丢弃。
- `claude rc` 与交互式 Remote Control 启动使用同一套企业网关可用性检查。

### 原生工具与细节修复

- 内嵌 `grep` 遇到病态模式时会快速失败，不再持续耗尽内存。
- `grep -m N` 与 `-A`/`-C` 组合时能够返回正确的上下文。
- 达到上下文上限且 auto-compact 被关闭时，错误会明确说明并提示到 `/config` 重新启用。
- 后台自动更新完成后，输入框底部会保留 `Update installed` 重启提示。
- 恢复仍有未完成任务的会话时，`ctrl+t` 任务列表会恢复之前的展开状态。
- VS Code 恢复多个 Claude 面板时，不再在标签页之间自动抢焦点。

官方原始条目保存在 [`analysis/release-notes.md`](analysis/release-notes.md)。

## 本版本的完整能力面

### 会话与 Agent 生命周期

- 支持交互式终端会话和非交互 `--print` 模式。
- 支持按 ID resume、继续当前目录最近会话、resume 时 fork、显式 session ID，以及关闭会话持久化。
- 支持会话命名、后台 Agent、可脚本化的 `agents --json`、Git worktree 隔离，以及 tmux/iTerm2 worktree 窗格。
- 支持自定义 Agent、指定当前 Agent、在 stream JSON 中转发子 Agent 文本/思考块，以及跨会话通信。
- 支持 cloud session、自托管环境、teleport/resume、Remote Control、从 PR 恢复会话，以及云端多 Agent `ultrareview`。

### Agent Loop 执行引擎

- 主执行链是异步生成器 `USe -> HGS -> tdf`。一次用户请求可以包含多次模型轮次、API retry/fallback 和多个工具批次，它们不是同一个“turn”概念。
- `tool_use` 不必等整个 assistant message 结束：单个 content block 完成且 JSON 可解析后就进入 streaming tool executor；模型继续流式输出时，工具 progress/result 可以同步回到 UI/SDK。
- 多个 `concurrency-safe` 工具可以重叠执行；非并发安全工具形成顺序屏障，后续工具不能越过它。并发资格由工具和本次 input 共同判断。
- 单工具必须经过工具/alias 查找、isolation latch、JSON/schema、自定义 validate、PreToolUse、permission/policy/classifier、updatedInput 复验、tool.call、PostToolUse 和 output schema 复验。
- 工具异常、拒绝、取消和不存在都会生成带原 `tool_use_id` 的 error `tool_result`，保证下一轮消息仍能正确配对。
- `maxTurns` 从第一次模型请求的 1 开始，只在工具结果或 blocking Stop hook 准备触发下一次模型调用时增加；API retry、流转非流和同轮纠错不等于增加 turn。
- Stop/SubagentStop hook 可以阻止结束并让模型继续；连续阻止默认超过 8 次时客户端覆盖 hook，避免永久循环。
- fallback 会 tombstone 当前消息、abort 未完成工具并清理 UI 状态，但无法自动撤销已经完成的文件、Git 或远端副作用。
- custom/subagent 使用同一个核心循环，但拥有独立 model/effort/maxTurns、工具、权限上下文、abort controller、worktree 和 transcript。

完整状态字段、时序图、终止原因和一个 Read/Edit/Bash 的执行例子见 [`analysis/agent-loop.md`](analysis/agent-loop.md)；与官方 Agent SDK 原理的逐项验证见 [`analysis/public-claims-validation.md`](analysis/public-claims-validation.md)。

### 模型与上下文控制

- 支持模型别名或完整模型 ID、print 模式下的 fallback model 链，以及 `low` 到 `max` 的 effort 级别。
- System prompt 不是单块字符串：客户端将 billing/identity、global 稳定前缀和 org 动态后缀分段，并分别决定是否写 `cache_control`。
- 消息 cache breakpoint 会向后寻找合法 user/assistant/api-system block；fork 可额外 pin 分叉点，`skipCacheWrite` 会主动退后，避免错误写入本轮尾部。
- Prompt cache 默认 5 分钟；1 小时 TTL 受强制开关、provider、订阅/overage 和 query-source allowlist 控制。Sonnet 4.6 的 baked 价格为普通输入 `$3/MTok`、5m 写入 `$3.75/MTok`、1h 写入 `$6/MTok`、读取 `$0.30/MTok`。
- Tool Search 将大工具目录标记为 `defer_loading`，初始只驻留工具名，需要时再追加完整 schema；旧 Vertex/不支持的 Foundry/model 会明确关闭并记录原因。
- Context hint 在潜在可清理旧工具结果达到 20k token 时才发送；本地 microcompaction 默认保留最近 5 个结果，旧结果可持久化到文件后替换为短引用。
- Auto-compact 支持自动模式或显式 100k-1M token 窗口。以 200k 模型为例，输出预留后默认约在 144k 预计算、147k warning、167k compact、177k blocked，而不是等到 200k 才处理。
- compact boundary 保存 pre/post token、摘要消息数、保留 UUID、logical parent 和是否预计算；resume 会据此修复消息图，不是简单拼接 JSONL 文本。
- 可将 cwd、环境、memory path、Git 状态等机器动态段从 system prompt 移到第一条 user message，提高跨用户 prompt cache 复用率。
- 支持替换或追加 system prompt、JSON Schema 结构化输出、美元预算上限、prompt suggestion 和 partial message streaming。

完整调用链、优先级、失败回退、设置/环境变量和成本算例见 [`analysis/context-governance-and-caching.md`](analysis/context-governance-and-caching.md)。消息图、transcript、checkpoint、rewind 和 memory 的恢复边界见 [`analysis/sessions-checkpoints-memory.md`](analysis/sessions-checkpoints-memory.md)。

### 工具、权限与隔离

- 支持 tool allow/deny、内置工具选择，以及 `default`、`acceptEdits`、`auto`、`bypassPermissions`、`dontAsk`、`plan` 六种权限模式。
- Safe mode 会关闭 `CLAUDE.md`、skills、plugins、hooks、MCP、custom commands、agents、主题等自定义内容，但保留认证、模型、内置工具和权限系统。
- Bare mode 会跳过 hooks、LSP、plugin sync、attribution、auto-memory、后台预取、keychain 和自动 `CLAUDE.md` 发现，但仍接受显式传入的配置。
- 支持额外可读目录、隔离 worktree、strict MCP config 和企业托管设置。

单工具从查找、input schema、PreToolUse、permission/policy 到 output schema 的完整顺序，以及 hook、sandbox、凭据和 managed settings 的失败语义见 [`analysis/tools-permissions-hooks.md`](analysis/tools-permissions-hooks.md)。

### 风控、安全与企业治理

这里的“风控”是 CLI 在本机执行 Agent、工具、Shell、MCP 和扩展时实施的风险控制，不等于 Anthropic 服务端的账号风控、滥用检测或封禁评分。发布 bundle 能直接证实以下控制面：

| 控制层 | 已恢复的能力 | 微小但重要的行为 |
| --- | --- | --- |
| 工具审批 | `--allowed-tools`、`--disallowed-tools`、工具级 allow/ask/deny 规则，以及 `default`、`acceptEdits`、`auto`、`dontAsk`、`plan`、`bypassPermissions` 六种模式 | `dontAsk` 遇到未授权操作会拒绝而不是弹窗；`bypassPermissions` 有单独的危险开关，帮助文本只建议在无外网沙箱中使用 |
| Auto 风险判定 | Auto mode 会把待执行动作交给 classifier；决策原因区分 rule、mode、hook、sandbox、safety check、classifier 等来源 | 无法评估时使用 `blocking it for safety` 路径；对话超过 classifier 窗口时回退人工审批；`dangerousRemoval`、`isolatePeerMachines` 等 circuit breaker 中存在不受 bypass 影响的类别 |
| Shell/Git 防护 | Bash command clamp、只读命令识别、复合命令拆分检查、工作目录和 Git 元数据检查 | 权限检查崩溃走 fail-closed；`cd` 后执行 Git、可植入的 `.git` 文件/符号链接、bare-repo 指示物和可能触发不可信 hook 的路径会重新要求审批 |
| 文件与进程沙箱 | `allowWrite`、`denyWrite`、`denyRead`、`allowRead`，并支持 `failIfUnavailable`、禁止 unsandboxed command、Linux seccomp/bwrap、macOS sandbox 和 Windows 隔离用户路径 | 管理策略一旦配置文件限制，用户可写设置不能关闭它；Apple Events 和 weaker network isolation 被显式标为降低隔离强度的选项 |
| 网络出口 | 域名 allow/deny、strict allowlist、managed-domain-only、Unix socket、本地监听和 macOS Mach/XPC service allowlist | denied domain 优先；strict allowlist 未匹配时直接拒绝；managed-domain-only 会忽略用户、项目和 CLI 临时放宽的域名，只接受策略层许可 |
| 凭据防泄漏 | 对文件和环境变量支持 `deny` 或 `mask`；可用 regex 只遮蔽捕获片段，也可识别 JWT、按 claim 遮蔽、处理重复 secret，并用 `injectHosts` 限定真实凭据注入目标 | Agent/命令看到 sentinel 或假 JWT，宿主代理只在许可出口替换为真实值；macOS/Windows 的文件 `mask` 当前会降级为 `deny`；配置可选择 no-match 时 warn、deny 或 error |
| Workspace 与扩展信任 | workspace trust、`--strict-mcp-config`、safe mode、bare mode、MCP tool permission、PreToolUse hook 的 allow/deny/ask/defer | MCP `headersHelper` 在 workspace trust 确认前会被阻止；hook 改写后的 tool input 会重新进入权限检查；HTTP hook 只有 `allowedEnvVars` 列出的变量可以进入 header |
| 企业治理 | managed/policy settings、`policyHelper(s)`、`allowManagedPermissionRulesOnly`、`allowedMcpServers`、`availableModels`、`forceLoginOrgUUID`、`processWrapper` | admin policy 可以锁定权限来源、MCP、模型、组织登录、文件读取范围和网络域名；Safe mode 仍保留 policy 层，不会绕过管理员配置 |

此外还存在两个启动前输入防护：凭据文件若 group/world 可读或可写会拒绝使用并要求修正为 `0600`；`--handle-uri` 后出现额外参数会按 URL 参数注入处理并拒绝启动。

结构化清单保存在 [`analysis/risk-control-surface.txt`](analysis/risk-control-surface.txt)。它用于长期版本对比，记录稳定的权限模式、circuit breaker、sandbox 设置、凭据控制、信任门和企业策略键；不把 bundle 中没有证据的服务端账号评分、关联检测或滥用规则写成已恢复能力。

### 扩展与集成

- 支持 skills/slash commands、目录/ZIP/URL 插件、MCP server 配置和 setting source 选择。
- 支持 IDE 自动连接、Chrome 集成、终端 screen reader 模式和 VS Code 会话。
- 支持 Anthropic API、Claude 订阅、Bedrock、Vertex AI、Foundry 和企业 gateway 路径。
- 顶层命令包含 gateway、project purge、auth、install/update、setup-token、plugin、MCP、import、auto-mode 和 doctor。

### 输入输出协议

- 输出支持文本、单个 JSON 结果或实时 stream JSON。
- 输入支持文本或 stream JSON，并可回放用户消息用于确认。
- Stream 模式可以输出 hook 生命周期、partial assistant chunk、子 Agent 转发内容和结构化任务进度。

标准化后的完整顶层选项和命令保存在 [`analysis/cli-surface.txt`](analysis/cli-surface.txt)。后续版本对比不会受到帮助文本换行或终端宽度影响。

### 遥测、日志、实验和性能诊断

完整数据流、字段和隐私控制见 [`analysis/telemetry.md`](analysis/telemetry.md)，字段的人类解释见 [`analysis/inventory-field-guide.md`](analysis/inventory-field-guide.md)。本版本不是只有一个“是否有遥测”的布尔开关，而是多条独立链路：

- 一方 analytics 在 sink 安装前保留 1,000 条全局事件，在一方 provider 初始化前再保留 1,024 条；provider 默认 queue 为 8,192。
- Acorn AST 找到一方 `H` 2,162 次、`Fv` 32 次、OTEL `Nd` 52 次、feature `et` 498 次和 GrowthBook `CB` 12 次；静态名、模板、变量/条件表达式、完整参数、函数作用域、payload property/spread 和 unresolved spread 都写入 JSONL。
- `DISABLE_TELEMETRY`、`DO_NOT_TRACK`、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 进入共享非必要流量/遥测门；error reporting 另有 `DISABLE_ERROR_REPORTING` 和组织 policy/compliance 门。
- 一方采样由 `tengu_event_sampling_config` 按事件控制；被采中事件会把实际 `sample_rate` 写入 metadata。
- 一方 batch config 为 `tengu_1p_event_batch_config`；默认 10 s flush、200 batch、10 s request timeout、100 ms batch delay、8 attempts、500 ms 到 30 s 二次 backoff。
- 默认一方 endpoint 为 `https://api.anthropic.com/api/event_logging/v2/batch`。失败事件保存为 `1p_failed_events.<session>.<run>.json` 或 v5 `log/telemetry` stream，后续启动会重试遗留 batch。
- 带 auth 的一方请求收到 401 时，会用基础 headers、不带 auth 再试一次。
- 一方 envelope 可承载 event/session/model、device/email/account/org、platform/runtime/CI/remote、process memory/CPU、skill/plugin/MCP/team/head SHA 和 event-specific metadata；不是每个事件都会填满全部字段。
- 第三方 OTEL 由 `CLAUDE_CODE_ENABLE_TELEMETRY` 显式启用。metrics 支持 console/OTLP/Prometheus，logs 支持 console/OTLP，traces 支持 console/OTLP；OTLP 支持 grpc、http/json、http/protobuf。
- OTEL 支持 global 和 signal-specific endpoint/header/protocol/cert/key/compression。metrics temporality 未显式设置时强制为 `delta`；默认 flush timeout 5 s、shutdown timeout 2 s。
- 静态恢复出 8 个 metric、10 个 span 和 26 个 structured event，名称和逐事件字段已全部生成清单。
- 环境解析覆盖 2,548 个访问点、143 个 dynamic `process.env[...]`、842 个 typed schema entry、71 个观测相关 schema entry 和 23 个观测默认/fallback 表达式。
- OTEL user prompt 默认 `<REDACTED>`；assistant、tool content/details、raw API bodies 均需对应开关。内容长度受 Claude Code limit 和 OTEL 各类 attribute limit 的最小值约束。
- Datadog 只运行于 first-party provider，受 `tengu_log_datadog_events` 和 181 项 allowlist 控制；默认 15 s flush、100 batch、5 s timeout。
- Datadog 发送前删除 26 个字段，选择 34 个 tag，折叠 MCP/skill tool name，归一化 Claude model/version/HTTP status，并对 peer 事件做每 event/server 每分钟 10 条限制。
- GrowthBook experiment 复用一方批量 transport，包含 experiment/variation、device/session、account/org 和序列化 attributes/metadata。
- 还恢复出 error reporting、secret scrubber、Perfetto、startup/query profiling、debug logs、diagnostics file、frame timing、session/JSONL/PTY recording 等观测面；对应 4,831 个 error callsite、5,403 个 diagnostic callsite 及全部动态模板均可逐点检索。本地 debug/profile 文件不能自动等同为网络上报。

### 其余完整系统面

[`analysis/technical-architecture.md`](analysis/technical-architecture.md) 先把这些系统串成一条可读调用链；[`analysis/source-surface.md`](analysis/source-surface.md) 再逐层整理 build/runtime、CLI/protocol、settings/env/schema、models/providers/auth、session/transcript/memory/cache/storage、agent/team/worktree/background、MCP/hooks/plugins/skills/LSP、IDE/Chrome/Computer Use、cloud/remote/CCR/BYOC/workflow/artifacts、install/update/doctor、UI/accessibility/voice，以及 API/error/retry/rate-limit/compact。每一层都区分 Observed、Derived、Compatible 和 Heuristic。

## 打包与技术细节

### Bun standalone 格式

本机安装包是签名的 arm64 Mach-O 文件，包含 `__BUN.__bun` 段。Bun 在这里保存序列化的 standalone module graph，同时保留 bundle 后的 JavaScript 和 JavaScriptCore bytecode cache。

主模块开头为：

```js
// @bun @bytecode @bun-cjs
```

含义如下：

- `@bun`：这是 Bun 打包模块。
- `@bytecode`：可执行文件还包含 JSC bytecode cache，用于缩短启动时间。
- `@bun-cjs`：源码依赖 Bun 内部 CommonJS wrapper 约定。

本分支同时提交 bytecode cache 的无损 gzip 形式和可读化 JavaScript，但两者都不会覆盖逐字节 JavaScript 基线。跨版本源码级比较以 `extracted/cli.js` 和 `reverse/index/` 为主；bytecode 哈希用于确认运行时生成物是否变化。

### 解出的模块图

15 个内嵌文件并不是 Anthropic 原始源码目录，而是产品构建完成后实际写入可执行文件的 bundle：

- 1 个 26.0 MB 主应用 bundle。
- 5 个约 2.1 KB 的原生能力 JavaScript loader。
- 5 个 `.node` 原生模块，负责图像处理、音频采集、URL handling、Swift Computer Use 和输入注入。
- Chart.js、Highlight.js、Mermaid 浏览器运行时。
- 1 个 2.13 MB 的 Artifact/报告 HTML 模板。

图像、音频和 URL 原生模块是 arm64 Mach-O；两个 Computer Use 模块是同时包含 x86-64 和 arm64 slice 的 universal Mach-O。

### 保真度与可运行性

解包时使用 `--path-patching false`。清单中每个文件的 `sha256` 都等于 `sha256Packed`，证明仓库内容与本机可执行文件内的原始打包字节一致。

主 bundle 可用于全文检索和跨分支对比，但不是普通独立 `cli.js`。直接交给 stock Bun 运行，会在 Bun 内部 CommonJS wrapper 边界报错。已验证的运行行为仍来自原始签名程序；本仓库是分析快照。

主 bundle 没有内嵌 source map，5 个原生模块也没有可用的源码级 debug information。生产构建已经丢弃的原始 TypeScript 文件名、注释、格式、bundle 前模块边界、被压缩改写的局部变量名，以及 tree shaking 删除的代码，无法从发布可执行文件精确反推出原值。

因此，本仓库的“完整”定义是：发布可执行文件中仍存在的 packed 文件和 bytecode 全量保留，对 JavaScript 和所有原生模块生成可复现的最大静态分析视图，并为 5 个原生模块提供可编译、双跑验证的兼容源码重建；不把重建目录冒充 Anthropic 原始源码仓库。

## 长期版本对比

可复用 skill 位于 [`skill/claude-code-version-diff`](skill/claude-code-version-diff)，并已安装到本机，可通过 `$claude-code-version-diff` 使用。

从本版本开始，skill 的交付合同分成两层：

- **机器证据层**：packed bytes、bytecode、native reports、结构化 inventory 和稳定语义 diff，保证没有靠人工挑选遗漏字段。
- **人类解释层**：机制总图、公开主张验证、技术架构、Agent Loop、上下文治理/缓存、会话/checkpoint/memory、工具/权限/hooks、MCP/Agents/后台协作、韧性恢复、遥测、风控、字段字典和版本专题。每个机制必须解释 purpose、owned state、call chain、gate/precedence、threshold、failure、lifecycle、user impact、evidence 和 boundary。

后续版本不能只更新 count table。任何新增 settings/env/model/event 字段都要说明字段语义、来源、默认/约束、谁读取、何时生效、如何失效、用户怎样观察；任何上下文/cache/compact 变化都要给出旧版和新版的状态机与成本影响。官方当前文档或 Engineering 文章只用于提出验证假设，必须标明调研日期，并分别标注目标版本的静态证据、运行 probe 和未证实边界。

验证任意版本分支：

```bash
python3 skill/claude-code-version-diff/scripts/validate_snapshot.py .
```

单独验证深度逆向，包括流式解压 bytecode 后重新计算哈希：

```bash
python3 skill/claude-code-version-diff/scripts/validate_deep_reverse.py .
```

对比两个版本分支并输出 Markdown 报告：

```bash
python3 skill/claude-code-version-diff/scripts/compare_versions.py \
  . 2.1.234 2.1.235 --output comparison-2.1.234-to-2.1.235.md
```

对比器会输出：

- 版本元数据、二进制大小和载荷大小变化；
- 新增、删除和内容变化的内嵌文件；
- 新增或删除的 CLI option/command；
- 新增或删除的权限模式、风控 circuit breaker、沙箱/凭据/信任和企业治理控制；
- `analysis/source-inventory/summary.json` 中全部 70 类清单的 count delta、added 和 removed，包括调用点、动态表达式、事件/payload、OTEL、Datadog、typed env、settings schema、模型目录/pricing/alias、全部字符串/模板、tools/commands、hooks/protocol、storage、API、errors、URLs/hosts；
- 人类解释层的章节级变化：完整请求机制、公开主张验证状态、请求装配、上下文预算、cache scope/TTL/breakpoint、tool deferral、microcompaction、auto-compact、session/checkpoint/memory、MCP/Agent/task/mailbox、retry/fallback/resume/rewind、遥测 transport/privacy、风险控制与字段语义；
- Agent Loop 的主状态字段、流中工具启动点、并发屏障、tool pipeline、Stop hook、maxTurns、fallback sweep、terminal reason 和子 Agent 隔离变化；
- 老分支没有全量 inventory 时，才回退到 `ANTHROPIC_*`、`CLAUDE_CODE_*`、`ENABLE_*` 和 endpoint host 的旧式扫描；
- JSC bytecode 与可读化 JavaScript 大小/哈希变化；
- 原生架构、动态库、import/export、N-API 和 Swift 项目符号变化；
- 主 bundle 与分析文件的 Git 行数变化。

## 验证结论

快照校验器检查分支/版本约定、15 个解包文件哈希、93 个归一化风控条目、70 类 source inventory 的确定性重生成和逐文件哈希、Acorn 版本、JSONL 比较字段、调用点覆盖、完成审计、主源码 Bun banner、bundle 内版本号、深度逆向 manifest、完整 bytecode 解压哈希、可读版稳定标识符集合，以及 5 个原生源文件哈希。原生重建另外通过 Rust/Swift 发布构建、5 模块导出契约和 23 项原版/重建版行为双跑。原始本机程序在全部逆向和重建完成后 SHA-256 仍为 `83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748`。

本分支只排除 298.8 MB 的原始签名可执行文件本体，因为其中可分离的 Bun packed 内容与 bytecode 已经逐项保存；需要验证实际运行行为时仍使用本机原始签名程序。

仓库元数据使用 `$CLAUDE_INSTALL_ROOT` 和 `$CLAUDE_ENTRYPOINT` 表示本机安装位置，不提交用户名、home 目录或 Codex 工作区绝对路径。隐私校验覆盖 Git 已跟踪文件和待提交的未跟踪文件，拒绝采集机 home/workspace 路径和 credential-shaped value。`extracted/` 与 `reverse/` 中由发布二进制自身携带的上游构建路径属于原始证据，不属于采集机器信息。
