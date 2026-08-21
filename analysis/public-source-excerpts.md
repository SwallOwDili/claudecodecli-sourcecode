# 官方来源固定摘录

这些摘录只用于保存 2026-08-21 刷新时实际看到的公开主张。响应原始哈希、去噪正文哈希、逐摘录哈希、逐句正文命中状态、字节数、HTTP 状态和 URL 见 [public-sources/manifest.json](public-sources/manifest.json)。刷新脚本要求每条引用逐句存在于当次页面的可见正文，防止把分析者概括伪装成官方原话。公开资料解释设计目标；`2.1.235` 是否实现仍由 `Static` 或 `Probe` 证据决定。

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

> These actions cause the next request to miss part or all of the cache.
> Switching models
> Changing effort level
> Turning on fast mode
> Connecting or disconnecting an MCP server
> Enabling or disabling a plugin

## `public-session-fork-identity`

Source: `claude-sessions`

> Sessions created with /branch or --fork-session get their own session IDs and appear as separate rows.

## `public-checkpoint-limitations`

Source: `claude-checkpointing`

> Checkpointing does not track files modified by bash commands.
> Any other subagent: rewinding doesn’t restore the edits.
> Checkpointing only tracks files that have been edited within the current session.
> Checkpointing doesn’t rewind symlinked or hard-linked files.
> Checkpoints are designed for quick, session-level recovery.

## `public-memory-entry-budget`

Source: `claude-memory`

> The first 200 lines of MEMORY.md, or the first 25KB, whichever comes first, are loaded at the start of every conversation.
> Content beyond that threshold is not loaded at session start.

## `public-permission-precedence`

Source: `claude-permissions`

> Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome, and rule specificity doesn't change the order.

## `public-sandbox-layers`

Source: `claude-sandboxing`

> The sandbox has two independent layers: filesystem isolation controls which paths sandboxed commands can read and write, and network isolation controls which domains they can reach.
> Sandboxing provides OS-level enforcement that restricts what Bash commands can access at the filesystem and network level.
> To match an IPv6 address in any of them, write the literal in brackets: "[::1]" matches that address on every port, and "[::1]:443" matches it on port 443 only.

## `public-hook-events`

Source: `claude-hooks`

> PostToolBatch After a full batch of parallel tool calls resolves, before the next model call
> PermissionDenied When auto mode denies a tool call, including denials without a classifier verdict.
> SubagentStart When a subagent is spawned
> TaskCreated When a task is being created via TaskCreate
> TaskCompleted When a task is being marked as completed

## `public-mcp-roots-change`

Source: `claude-mcp`

> Claude Code answers roots/list with the session’s launch directory plus every additional working directory you’ve granted with --add-dir, /add-dir, or the additionalDirectories setting.
> Claude Code sends notifications/roots/list_changed when that set changes.

## `public-subagent-own-context`

Source: `claude-subagents`

> Each subagent runs in its own context window with a custom system prompt, specific tool access, and independent permissions.

## `public-agent-teams-coordination`

Source: `claude-agent-teams`

> Agent teams let you coordinate multiple Claude Code instances working together.
> One session acts as the team lead, coordinating work, assigning tasks, and synthesizing results.
> Teammates work independently, each in its own context window, and communicate directly with each other.
> This page describes agent teams as of v2.1.178.

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

> You can enable both by exposing a simple response_format enum parameter in your tool, allowing your agent to control whether tools return "concise" or "detailed" responses (images below).

## `public-multiagent-compression`

Source: `anthropic-multi-agent`

> Subagents facilitate compression by operating in parallel with their own context windows, exploring different aspects of the question simultaneously before condensing the most important tokens for the lead research agent.

## `public-otel-exporter-precedence`

Source: `claude-monitoring-usage`

> If you set a per-signal endpoint or protocol variable, such as OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, Claude Code uses it instead of the generic variable for that signal. If you set a per-signal headers variable, such as OTEL_EXPORTER_OTLP_METRICS_HEADERS, Claude Code merges it with the generic OTEL_EXPORTER_OTLP_HEADERS for that signal.

## `public-otel-prompt-redaction`

Source: `claude-monitoring-usage`

> Enable logging of user prompt content (default: disabled)
> Prompt text. Value is <REDACTED> unless the gate is set

## `public-settings-precedence`

Source: `claude-settings`

> When the same setting appears in multiple scopes, Claude Code applies them in priority order:
> Managed (highest): can’t be overridden by any other scope, apart from the exceptions to managed settings precedence
> Command line arguments: temporary session overrides
> Local: overrides project and user settings
> Project: overrides user settings
> User (lowest): applies when nothing else specifies the setting
> Permission rules merge across scopes instead, and a few security-sensitive keys are exceptions.

## `public-settings-live-reload`

Source: `claude-settings`

> Claude Code watches your settings files and reloads them when they change, so edits to most keys apply to the running session without a restart.
> The reload covers user, project, local, and managed settings, and the ConfigChange hook fires for each detected change.

## `public-fallback-chain`

Source: `claude-model-config`

> When the primary model is overloaded, unavailable, or returns another non-retryable server error, Claude Code can switch to a fallback model instead of failing the request.
> Authentication, billing, rate-limit, request-size, and transport errors never trigger a switch; those follow their normal retry and error handling.
> The switch lasts for the current turn only, so your next message tries the primary model first again.

## `public-auth-precedence`

Source: `claude-authentication`

> ANTHROPIC_AUTH_TOKEN environment variable. Sent as the Authorization: Bearer header.
> ANTHROPIC_API_KEY environment variable. Sent as the X-Api-Key header.

## `public-background-network-settings`

Source: `claude-network-config`

> Background agents don’t run inside the terminal that dispatched them. A per-user supervisor process starts on demand, outlives your shell, and hosts every claude agents, --bg, and /background session.
> Put the same variables in the env block of ~/.claude/settings.json or managed settings instead.
> Every variable on this page can be set there, and settings are the only configuration that reaches every background session on every machine.

## `public-remote-local-execution`

Source: `claude-remote-control`

> Remote Control sessions run directly on your machine and interact with your local filesystem.
> The web and mobile interfaces are a window into that local session.

## `public-remote-transcript-security`

Source: `claude-remote-control`

> Your local Claude Code session makes outbound HTTPS requests only and never opens inbound ports on your machine.
> While Remote Control is connected, the session transcript, including your messages, Claude’s responses, and tool activity, is stored on Anthropic servers.
> Execution and filesystem access stay on your machine, and stored transcripts are retained under the Data usage policy.

## `public-remote-compact-reconnect`

Source: `claude-remote-control`

> If compaction rewrote the conversation or you switched conversations with /resume in the meantime, Claude Code archives the server session it was using instead of leaving it in the session list.

## `public-ide-loopback-contract`

Source: `claude-ide-integrations`

> The server binds to 127.0.0.1 on a random port in the range 10000–65535, and the port is not configurable.
> Each extension activation generates a fresh random auth token, writes it to a lock file at ~/.claude/ide/<port>.lock, and the CLI must present it as the X-Claude-Code-Ide-Authorization header to connect.
> A matching deny rule prevents both the selected text and the open-file notice for that file from reaching Claude.

## `public-doctor-readonly`

Source: `claude-setup`

> claude doctor prints read-only installation and settings diagnostics without starting a session, including install health, settings-file validation errors, and any warnings with suggested fixes.

## `public-disable-updates`

Source: `claude-setup`

> DISABLE_AUTOUPDATER only stops the background check; claude update and claude install still work. To block all update paths, including manual updates, set DISABLE_UPDATES instead.

## `public-autocompact-thrashing`

Source: `claude-troubleshooting`

> If you see Autocompact is thrashing: the context refilled to the limit..., automatic compaction succeeded but a file or tool output immediately refilled the context window several times in a row.
> Claude Code stops retrying to avoid wasting API calls on a loop that isn’t making progress.
