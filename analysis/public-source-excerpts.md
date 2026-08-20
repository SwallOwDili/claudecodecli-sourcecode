# 官方来源固定摘录

这些摘录只用于保存 2026-08-20 调研时实际看到的公开主张。响应正文哈希、字节数、HTTP 状态和 URL 见 [public-sources/manifest.json](public-sources/manifest.json)。公开资料解释设计目标；`2.1.235` 是否实现仍由 `Static` 或 `Probe` 证据决定。

## `public-agentic-loop-phases`

Source: `claude-how-it-works`

> When you give Claude a task, it works through three phases: gather context, take action, and verify results. These phases blend together. Claude uses tools throughout, whether searching files to understand your code, editing to make changes, or running tests to check its work.

## `public-tool-results-feedback`

Source: `claude-agent-loop`

> Execute tools. The SDK runs each requested tool and collects the results. Each set of tool results feeds back to Claude for the next decision. You can use hooks to intercept, modify, or block tool calls before they run.

## `public-context-auto-compaction`

Source: `claude-context-window`

> The point where automatic compaction runs depends on your model and configuration.

## `public-cache-invalidation`

Source: `claude-prompt-caching`

> Actions that invalidate the cache include switching models, changing effort level, turning on fast mode, connecting or disconnecting an MCP server, and enabling or disabling a plugin.

## `public-session-fork-identity`

Source: `claude-sessions`

> Sessions created with /branch or --fork-session get their own session IDs and appear as separate rows.

## `public-checkpoint-limitations`

Source: `claude-checkpointing`

> Limitations include Bash command changes not tracked, subagent edits not restored, external changes not tracked, and symlinked and hard-linked paths not restored. Checkpointing is not a replacement for version control.

## `public-memory-entry-budget`

Source: `claude-memory`

> Auto memory is loaded into every session (first 200 lines or 25KB).

## `public-permission-precedence`

Source: `claude-permissions`

> Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome, and rule specificity doesn't change the order.

## `public-sandbox-layers`

Source: `claude-sandboxing`

> How sandboxing works: filesystem isolation, protected paths, network isolation, IPv6 addresses in domain lists, and OS-level enforcement.

## `public-hook-events`

Source: `claude-hooks`

> The hook reference includes PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, PostToolBatch, PermissionDenied, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, and Stop lifecycle events.

## `public-mcp-roots-change`

Source: `claude-mcp`

> Claude Code sends notifications/roots/list_changed when the working-directory set changes.

## `public-subagent-own-context`

Source: `claude-subagents`

> Each subagent runs in its own context window with a custom system prompt, specific tool access, and independent permissions.

## `public-workflow-agent-distinction`

Source: `anthropic-effective-agents`

> Workflows are systems where LLMs and tools are orchestrated through predefined code paths. Agents, on the other hand, are systems where LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks.

## `public-context-high-signal`

Source: `anthropic-context-engineering`

> Given that LLMs are constrained by a finite attention budget, good context engineering means finding the smallest possible set of high-signal tokens that maximize the likelihood of some desired outcome.

## `public-compaction-definition`

Source: `anthropic-context-engineering`

> Compaction is the practice of taking a conversation nearing the context window limit, summarizing its contents, and reinitiating a new context window with the summary.

## `public-tool-token-efficiency`

Source: `anthropic-writing-tools`

> You can directly encourage agents to pursue more token-efficient strategies, like making many small and targeted searches instead of a single, broad search for a knowledge retrieval task.

## `public-tool-response-format`

Source: `anthropic-writing-tools`

> You can enable both by exposing a simple response_format enum parameter in your tool, allowing your agent to control whether tools return "concise" or "detailed" responses.

## `public-multiagent-compression`

Source: `anthropic-multi-agent`

> Subagents facilitate compression by operating in parallel with their own context windows, exploring different aspects of the question simultaneously before condensing the most important tokens for the lead research agent.
