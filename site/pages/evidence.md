---
title: 证据与复核
description: 解释 2.1.235 逆向快照的原始层、派生层、运行探针、兼容重建和不可证明边界。
section: 研究方法
order: 8
---

# 证据与复核

这套材料的目标不是让文章“听起来像源码”，而是让每个重要判断能回到确定版本、确定对象和确定证据。最基本的纪律是：**看见、推导、运行验证和外部未知必须分开写。**

## 仓库保存了四层不同产物

| 层 | 主要内容 | 可以证明 | 不能冒充 |
| --- | --- | --- | --- |
| 发布字节 | `extracted/` 中的 packed 文件和 `.node` | 目标程序确实携带这些字节 | 内部原始工程结构 |
| 派生分析 | readable JS、JSC bytecode、符号、反汇编、稳定 inventory | 调用形状、常量、分支、协议与跨版本语义变化 | Anthropic 原始 TypeScript/C++/Swift 文件 |
| 兼容重建 | Rust/Swift 实现与行为合同 | 在已验证输入上满足公开导出和可观察行为 | 原模块源码身份或未测行为等价 |
| 人类解释 | 机制文章、版本结论和问题导向路线 | 把证据连接成状态、顺序、失败和用户影响 | 新的独立证据来源 |

项目身份、原始二进制哈希、模块数量和验证命令集中在 [项目与快照说明](project.html)。

## 五个证据标签

![从发布字节和公开资料，经静态分析与运行探针形成有边界的机制结论](assets/visuals/evidence-surface-lifecycle.svg)

**Static** 表示 `2.1.235` 发布物中能定位到字段、consumer、分支或调用链。一个字符串、schema 或 help 条目若没有可达 consumer，只能证明 surface/declaration。

**Probe** 表示固定哈希的精确二进制真实走过指定路径，并保存输入、literal output、请求形状、exit status 和断言。Probe 证明的是这条环境和输入，不自动覆盖所有平台、账号或服务端状态。

**Public** 表示固定 URL、抓取时间、响应 hash 和原文摘录的一方公开主张。它帮助提出正确问题；要归属于 `2.1.235`，还需本版 Static 或 Probe。

**Compatible** 表示重建 artifact 满足已声明的接口与行为合同。它不把逆向实现升级成 Anthropic 原文件。

**Boundary** 表示客户端发布物不能独立证明，例如服务端 entitlement、远端保留策略、真实 IDE extension 内部实现或目标机 OS 行为。

## 从字段到结论要跨过四道门

1. **身份。** 证据是否来自目标分支和目标二进制，而不是 PATH 中另一个 Claude 版本。
2. **所有权。** 字段属于产品代码、打包依赖、混合路径还是仍未解析；AST callsite 不自动等于一方产品能力。
3. **可达性。** 声明是否有真实 consumer、gate、状态变化和失败分支；必要时用 Probe 推进。
4. **边界。** 客户端观察到了什么，外部系统是否接受、保存或执行了什么，必须分开陈述。

缺少其中任意一层，都只能保留为候选或待验证事实，不能用更确定的语气补齐。

## 机器清单负责防漏，不负责讲故事

确定性 inventory 会完整抽取命令、设置、工具、Hook、模型、API、事件、错误、环境变量和原生表面，并为跨版本提供稳定的 `comparisonKey` / `comparisonValue`。它适合回答“集合里增删了什么”，不直接回答“用户为何看到这个行为”。

机制文章需要另外补齐 owner、入口、顺序、gate/default、成功、失败/恢复、持久化、副作用、用户影响和证据边界。一个目录中有上千事件或错误调用点，不等于有上千个独立产品功能，也不构成文章深度。

## 运行探针怎样避免假阳性

高价值 Probe 固定四件事：目标 binary hash、受控输入、可观察输出和否定条件。例如 Agent Loop Probe 不只看到最终成功文本，还验证第一次请求有 `Read` 声明、第二次请求包含同 ID 的 `tool_use/tool_result`、结果含文件 marker。

权限 Probe 不能只看“没有弹窗”，还要检查文件是否改变、第二次同类动作是否仍需审批；sandbox Probe 不能只看 CLI exit code，还要观察目标文件和网络端点是否产生副作用。负向证据同样要明确它排除了什么。

## 公开资料怎样进入旧版本研究

当前官方文档会更新，发布时间和实现版本不一定与 `2.1.235` 对齐。公开材料只用于解释设计目的、建立候选机制和核对官方声明。版本归属必须回到固定 changelog 段落、本版 bundle 或精确 Probe。

同样，当前服务端接受某个 beta、model 或 account feature，不能倒推旧客户端在发布时已经获得相同 entitlement。客户端能证明请求字段和 fallback 分支，服务端采用与保留仍是外部状态。

## 怎样复核一篇文章

先读文章的普通路径，确认每个节点有 owner 和状态变化；再检查失败分支是否说明副作用已经发生到哪一步；随后沿源码锚点或 Probe 找输入、结果和版本身份；最后检查 Boundary 是否把服务端、宿主或缺失源码明确留在外面。

如果文章只有名词和数字，没有一条完整输入 -> 转换 -> 结果链，它最多是索引。如果文章只有顺畅叙事，没有目标版证据，它最多是解释性假设。

## 推荐阅读顺序

1. [全面性审计](articles/completeness-audit.html)：当前覆盖合同、已验证能力和仍保留的边界。
2. [公开主张与目标版证据](articles/public-claims-validation.html)：官方原理怎样被本版 Static/Probe 接住。
3. [精确二进制 Probe 索引](articles/runtime-probe-index.html)：逐项查看命令、输入、输出和断言。
4. [机器清单字段阅读指南](articles/inventory-field-guide.html)：理解稳定语义 diff 与 immediate consumer 的限度。
5. [产品表面机器证据索引](articles/product-surface-inventory-index.html)：需要全量复核时再进入确定性清单。

站内关联：[参考手册](reference.html) · [项目与快照说明](project.html) · [返回首页](index.html)
