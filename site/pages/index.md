---
title: Claude Code CLI 2.1.235 技术解剖
description: 从一次真实请求出发，理解 Claude Code 的 Agent Loop、上下文治理、工具控制、恢复边界与版本变化。
section: 首页
order: 1
---

<div class="home-lead" markdown>

# Claude Code CLI 2.1.235 技术解剖

这不是功能宣传页，也不是把逆向字段换一种顺序再列一遍。这个站点只回答一个问题：**Claude Code 2.1.235 收到任务后，客户端怎样把模型输出变成可控、可恢复、可追踪的真实行动。**

结论绑定 `2.1.235` 实际发布程序。仓库保存发布字节、可读化 JavaScript、JSC bytecode、原生模块静态分析、兼容重建、运行探针和文章；它不等于 Anthropic 内部 TypeScript 原始仓库。

</div>

## 先建立一个模型

<div class="home-system-map" markdown>

![Claude Code 任务在上下文、Agent Loop、工具控制、外部状态和恢复状态之间循环](assets/visuals/system-lifecycle.svg)

</div>

Claude Code 同时面对三个状态世界：

1. **模型世界**保存当前请求里可见的消息、工具定义和动态上下文，并提出文本或 `tool_use`。
2. **客户端世界**装配请求、维护 Agent Loop、裁决权限、执行客户端工具、配对 `tool_result`、写 transcript 和诊断。
3. **外部世界**保存已经发生的文件写入、Shell 进程、Git remote、MCP 服务或云端动作。

这三个世界不能混为一谈。compact 可以重写模型以后看到的历史，resume 可以修复消息图，fallback 可以丢弃失败 attempt 的临时消息；它们都不会自动撤销外部世界里已经完成的副作用。

## 一次请求不是一次 API 调用

![模型提出工具调用，客户端执行并将结果送入下一次模型请求](assets/visuals/request-execution-feedback.svg)

一次用户任务可能包含多个 Agent iteration；一个 iteration 可能因重试或模型 fallback 包含多个 API attempt；一次模型流又可能产生多个工具调用。模型只提出动作，客户端在名称、schema、工具校验、Hook、权限和适用的 sandbox 边界之后才执行动作，再用同一个 `tool_use_id` 把结果送回下一轮。

先读 [从一条真实工具链开始](start.html)，再进入 [Agent Loop 与运行时](runtime.html)。这两页建立后续所有专题共用的词汇。

## 按你遇到的问题进入

| 你想弄清楚什么 | 从这里进入 |
| --- | --- |
| 为什么 Claude 会连续读文件、改代码、运行测试，而不是只回复一次 | [Agent Loop 与运行时](runtime.html) |
| `/compact` 之后到底保留了什么，缓存、Memory、resume 又分别管什么 | [上下文、缓存与压缩](context.html) |
| 一个 `Edit` 或 `Bash` 为什么会被批准、拒绝、改写或隔离 | [工具、权限与扩展](tools.html) |
| 为什么恢复了对话却没有撤销文件或远端动作，数据又会流向哪里 | [状态边界、恢复与数据流](boundaries.html) |
| `2.1.235` 真正新增或修复了什么 | [版本变化](version.html) |
| 已经知道机制，只想查命令、设置、Hook、事件或错误 | [参考手册](reference.html) |
| 想判断一句结论是源码推断、真实探针还是外部边界 | [证据与复核](evidence.html) |

## 推荐阅读顺序

第一次阅读按下面五篇走，不需要先碰机器清单：

<ol class="reading-path">
  <li><a href="start.html">从一条真实工具链开始</a></li>
  <li><a href="runtime.html">Agent Loop 与运行时</a></li>
  <li><a href="context.html">上下文、缓存与压缩</a></li>
  <li><a href="tools.html">工具、权限与扩展</a></li>
  <li><a href="boundaries.html">状态边界、恢复与数据流</a></li>
</ol>

之后按需要读 [2.1.235 版本变化](version.html) 或 [完整文章索引](articles.html)。项目身份、哈希、目录层级和验证命令集中在 [项目与快照说明](project.html)，不挤进这条阅读路径。

想直接进入独立长文，可以从 [技术机制总图](articles/technical-mechanism-atlas.html)、[`/compact` 可视化专题](articles/compact-visual-guide.html) 或 [2.1.235 状态边界修正](articles/product-surface-evidence-map.html) 开始。

## 这套材料怎样使用

教程负责讲清一条状态变化；参考手册负责查字段和入口；证据页负责复核版本归属。遇到数字或结论时，先看它属于 `Static`、`Probe`、`Public`、`Compatible` 还是 `Boundary`，不要把“发布物里出现过一个字符串”误写成“运行时已经执行”。

下一页：[从一条真实工具链开始](start.html)
