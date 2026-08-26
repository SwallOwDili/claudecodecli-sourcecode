---
name: interactive-tutorial-labs
description: Add input-driven, step-by-step interactive teaching labs to stateful technical tutorials while preserving source accuracy, evidence boundaries, static prose, and no-JavaScript readability. Use for Claude Code mechanism tutorials; do not use for lookup references, machine inventories, or decorative animation.
---

# Interactive Tutorial Labs

把状态型技术教程变成可输入、可分步检查、可切换失败条件的交互实验。

这里的“动画”不是预设时间轴。读者改变输入或控制项后，工具参数、消息、状态、文件、Diff、证据或失败边界必须真实变化。

## Claude Code 快速指令

```text
读取 skill/interactive-tutorial-labs/SKILL.md。

为以下机制教程批量增加交互实验：
<ARTICLE_PATHS>

每篇教程独立完成：
- site/labs/src/scenarios/<id>.ts
- site/labs/tests/<id>.test.ts
- 文章中的 cc-agent-lab 嵌入和静态回退
- 必要的 SVG 绑定

复用现有 runtime，不调用 Claude API，不修改真实工作区。
每个 worker 只负责一篇文章；公共 runtime、validator、package 和 workflow
只由最后的 integrator 修改一次。
```

## 按需读取

- 涉及 Agent Loop、Compact、Permissions、Hooks、Sandbox、消息协议或证据 owner 时，读取 [references/claude-code-accuracy.md](references/claude-code-accuracy.md)。
- 涉及 SVG、移动端、深浅色、可访问性、无 JavaScript、懒加载、Pages 或线上验收时，读取 [references/browser-and-release-qa.md](references/browser-and-release-qa.md)。

## 当前仓库入口

- 组件：`site/labs/src/cc-agent-lab.ts`
- 场景协议：`site/labs/src/runtime/types.ts`
- 回放：`site/labs/src/runtime/machine.ts`
- 虚拟文件/Diff：`site/labs/src/runtime/files.ts`
- 自动注册：`site/labs/src/main.ts`
- 场景：`site/labs/src/scenarios/`
- 测试：`site/labs/tests/`
- 构建：`site/prepare_site.py`
- 验证：`site/validate_site.py`

`main.ts` 已自动发现 `./scenarios/*.ts`。新增场景不需要手工注册。

共享 runtime 默认冻结。只有多个教程共同缺少同一种能力时，才由 integrator 扩展。

## 判断是否需要实验

适合：

- 教程解释有顺序的状态变化；
- 输入、策略、阈值、失败或恢复条件可以改变；
- 读者需要理解 owner、消息边界、副作用或恢复边界；
- 静态图容易把“何时可见、谁执行、是否已落盘”讲错。

不适合：

- 命令、字段、事件查询手册；
- 机器生成 inventory；
- 没有可操作状态变化的文章；
- 必须捏造远端成功才能运行的场景。

参考手册继续使用静态 SVG 和检索，不制造假交互。

## 单篇实施流程

### 1. 先闭合事实

```text
ARTICLE: 目标文章
QUESTION: 读者操作后要看懂什么
INPUT: 可改变的输入
STATE: 初始状态和 owner
ORDINARY: 普通路径
FAILURE: 至少一个机制不同的失败路径
EVIDENCE: Exact Probe / Static source / Teaching fixture
BOUNDARY: 目标版本不能证明什么
```

事实未闭合，不写 UI。

### 2. 只选一条因果主线

```text
input
-> action
-> observable result
-> next decision
-> state change
-> failure/recovery
-> evidence boundary
```

不要把整篇文章所有功能塞进一个场景。

### 3. 输入必须改变 trace

可以改变：

- 路径、搜索词、旧值和新值；
- 教学夹具模拟的工具选择；
- 历史组、保留范围、附件；
- permission、Hook、sandbox；
- 缓存命中、重试、失败和恢复模式。

解析必须 fail closed：

- unsupported 输入显示错误；
- 缺少 old/new 不执行修改；
- `old == new` 拒绝；
- `replace_all=false` 时 old 必须唯一；
- 不得静默播放默认成功 trace。

### 4. 生成完整 LabTrace

```ts
{
  id,
  title,
  actor,
  kind,
  summary,
  input,
  output,
  before,
  after,
  files,
  effects,
  evidence,
  visualTarget,
  status,
}
```

要求：

- `actor` 是当前动作 owner；
- evidence detail 单独写 evidence owner；
- `before/after` 展示状态变化；
- `files` 是该步后的完整虚拟文件快照；
- 已发生的外部/持久副作用使用 `reversible:false`；
- `visualTarget` 命中 SVG node id 或直接子 `<title>`。

### 5. 不污染协议字段

```ts
{
  wireBlock: {
    type: "tool_result",
    tool_use_id: "toolu_...",
    content: "...",
    is_error: true,
  },
  clientMetadata: {
    decision_source: "sandbox",
    fixtureUnifiedDiff: "...",
  },
}
```

真实 wire block、客户端旁路状态和教学投影必须分开。

### 6. 保证调用配对

- 每个 `tool_use.id` 只出现一次；
- 每个调用只有一个同 ID `tool_result`；
- result 位于 use 之后；
- success、deny、sandbox 和 tool failure 都保持配对；
- 测试数量和顺序，不只比较 Set。

## 文章嵌入

先在正文解释输入、普通路径和关键失败，再嵌入：

```html
<div class="cc-agent-lab-embed">
<cc-agent-lab scenario="SCENARIO_ID" heading-level="3"><div class="cc-agent-lab-fallback"><strong>静态回退：</strong>用完整句子说明触发、动作、结果、失败和副作用边界。</div></cc-agent-lab>
</div>
```

必须满足：

- fallback 是 custom element 的直接 child；
- custom element 不被 Markdown 包进 `<p>`；
- upgrade 后 fallback 隐藏；
- 禁用 JavaScript 后 fallback 可读；
- 静态文章、字段、阈值、失败和证据不能被删掉；
- `heading-level` 与文章层级一致。

## Worker 测试

每个新场景使用独立文件：

```text
site/labs/tests/<scenario-id>.test.ts
```

最低覆盖：

- 默认成功路径；
- 输入改变参数或状态；
- 一个机制不同的失败路径；
- 副作用发生在正确边界；
- 后续失败不抹掉已完成副作用；
- tool use/result 数量和顺序；
- unsupported、missing pair、same value、ambiguous replace；
- 控件默认值与首屏显示一致；
- 版本字段和 owner 不被 fixture 污染。

Worker 运行：

```bash
npm run typecheck:labs
npm run test:labs
npm run build:labs
```

## 并行加速

每个 scenario worker 只修改：

1. 一篇文章；
2. 一个 `site/labs/src/scenarios/<id>.ts`；
3. 一个 `site/labs/tests/<id>.test.ts`；
4. 必要的独立 SVG source/output。

Worker 不修改：

- `cc-agent-lab.ts`；
- runtime types/machine/files/registry；
- package/lockfile；
- prepare/validator；
- Pages workflow；
- 共享 Skill。

Integrator 最后只做一次：

1. 审查 scenario id、evidence owner、article heading；
2. 合并 validator expected scenarios；
3. 只在多个场景共同需要时扩展 runtime；
4. 运行完整测试与浏览器矩阵；
5. 修正跨场景一致性；
6. 构建、提交、推送和线上验证。

推荐：

- 3-5 个 scenario worker；
- 1 个 evidence reviewer；
- 1 个 integrator；
- 公共文件只允许 integrator 修改。

优先扩展 execution、context、session、permission、settings、model、cost、update、MCP 和 subagent 等状态型教程。Reference/manual/inventory 保持静态。

## Integrator 验证

```bash
npm ci --no-audit --no-fund
npm run check:labs
python3 site/prepare_site.py
mkdocs build --strict
python3 site/postprocess_site.py .site-output
python3 site/validate_site.py .site-output
python3 skill/claude-code-version-diff/scripts/validate_snapshot.py .
git diff --check
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/pages.yml
```

推送后验证 Workflow、deployment SHA、线上 bundle SHA、代表场景和非 Lab 页懒加载。

## 完成定义

一篇教程只有同时满足以下条件才算完成：

- 输入改变真实 trace 数据；
- 普通路径完整；
- 失败路径改变状态或副作用，不只是换文案；
- owner、wire block、client metadata、evidence class 分开；
- 静态技术细节完整；
- no-JS fallback 有效；
- 单元测试通过；
- 桌面、390px、深浅色、reduced motion 通过；
- 非 Lab 页不增加运行成本；
- 目标版本事实没有被官网、其他版本或 fixture 倒灌。

只增加会播放的组件、按钮或高亮图，不算完成。
