#!/usr/bin/env python3
"""Validate a Claude Code version snapshot and its packed-file hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


PERSONAL_PATH_RE = re.compile(
    rb"(?:/" + rb"Users/[^/\x00\r\n]+/|/" + rb"home/[^/\x00\r\n]+/|"
    rb"[A-Za-z]:\\" + rb"Users\\[^\\\x00\r\n]+\\)"
)
SECRET_RE = re.compile(
    rb"(?:sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    rb"AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,})"
)
EXPECTED_SOURCE_INVENTORY_COUNT = 71
EXPECTED_TOOL_REGISTRATION_COUNT = 80
EXPECTED_STATIC_TOOL_REGISTRATION_COUNT = 77
EXPECTED_DYNAMIC_TOOL_REGISTRATION_COUNT = 3
EXPECTED_TOOL_FACTORY = "Yi"
TOOL_FACTORY_ANCHORS = {"Bash", "Read", "Write", "Edit", "Glob", "Grep"}
EXPECTED_TOOL_REGISTRATION_CLASSES = {
    "Core terminal": 29,
    "Conditional CLI": 28,
    "Hosted/product": 16,
    "Internal/eval": 4,
    "Dynamic factory": 3,
}
CLAUDE_STORAGE_NAMESPACE_RE = re.compile(
    rb"\bnamespace\s*:\s*['\"]([A-Za-z][A-Za-z0-9_-]{0,80})['\"]"
)
CLAUDE_STORAGE_FACTORY_START_RE = re.compile(
    rb"\btranscript\s*:\s*[A-Za-z_$][A-Za-z0-9_$]*\s*,\s*"
    rb"journal\s*:\s*.{0,500}?\bnamespace\s*:\s*['\"]transcript['\"]"
    rb".{0,500}?\bhistory\s*:\s*.{0,200}?\bnamespace\s*:\s*['\"]history['\"]"
    rb".{0,300}?\blog\s*:",
    re.DOTALL,
)
CLAUDE_STORAGE_FACTORY_END_RE = re.compile(rb"\bsessionAliases\s*:")
RELEASE_NOTES_COMMIT = "16440d0f6ee8c47f34169687044b89eafa8b0f8d"
RELEASE_NOTES_FULL_SHA256 = (
    "ca5698c578b3e3a97b8ff8388a08f4095a64c69696709dd07337605fe5f30fe3"
)
RELEASE_NOTES_SECTION_SHA256 = (
    "04943db50acf834556450fc580d0e3617ae0de7a7b62a5aed9444013420c5d17"
)
RELEASE_NOTES_ITEMS_SHA256 = (
    "4e63bcf44076b4482193e496be340699579bcb2360ded401b4f930d043255fff"
)
RELEASE_NOTES_ROW_SEMANTIC_MARKERS = {
    7: (
        ("mechanism", "notebook", ("notebook",)),
        ("mechanism", "cell", ("cell",)),
        ("mechanism", "read-failure", ("无法读", "读取失败", "read failure")),
        ("mechanism", "persistent-grant", ("持久授权", "persistent grant")),
        ("mechanism", "grant-narrowing", ("收缩", "缩限", "withheld")),
    ),
    9: (
        (
            "mechanism",
            "background-updater",
            ("background updater", "background auto-update"),
        ),
        ("mechanism", "update-installed", ("update installed",)),
        ("mechanism", "restart", ("restart", "重启")),
        ("mechanism", "old-bytes", ("旧 bytes", "old bytes")),
    ),
    10: (
        ("mechanism", "open-tasks", ("open tasks",)),
        ("mechanism", "resume-relaunch", ("resume/relaunch",)),
        ("mechanism", "expanded", ("expanded",)),
        ("mechanism", "collapsed", ("collapsed",)),
        ("mechanism", "state-owner", ("重新绑定", "state owner", "ownership")),
    ),
    13: (
        (
            "mechanism",
            "pathological-pattern",
            ("病态 pattern", "pathological pattern"),
        ),
        ("mechanism", "fast-fail", ("fast-fail", "fail fast")),
        ("mechanism", "match-cap", ("-m n",)),
        ("mechanism", "context-flags", ("-a/-c",)),
        ("evidence", "exact-binary-probe", ("exact-binary probe",)),
        ("evidence", "runtime-report", ("embedded-grep.json",)),
        ("evidence", "resource-measurement", ("rss",)),
        ("evidence", "schema-boundary", ("schema", "-m")),
    ),
    19: (
        ("mechanism", "vscode", ("vs code", "vscode")),
        (
            "mechanism",
            "multi-panel",
            ("多个 claude panel", "多 panel", "multi-panel"),
        ),
        ("mechanism", "focus", ("focus", "焦点")),
        ("evidence", "extension", ("extension",)),
        ("evidence", "boundary", ("boundary",)),
        ("evidence", "probe-boundary", ("probe", "真实多 panel")),
    ),
}
SOURCE_INVENTORY_MINIMUMS = {
    "environment-access-identifiers": 1,
    "first-party-events": 1,
    "first-party-event-fields": 1,
    "third-party-otel-events": 1,
    "datadog-forwarded-events": 1,
    "otel-metrics": 1,
    "otel-spans": 1,
    "feature-flags": 1,
    "root-settings-keys": 1,
    "known-tool-catalog": 1,
    "slash-command-identifiers": 1,
    "hook-events": 1,
    "sdk-control-subtypes": 1,
    "api-paths": 1,
    "schema-property-identifiers": 1,
    "error-message-literals": 1,
    "endpoint-hosts": 1,
    "first-party-event-callsites": 1,
    "otel-event-callsites": 1,
    "feature-flag-callsites": 1,
    "growthbook-callsites": 1,
    "error-message-callsites": 1,
    "error-message-templates": 1,
    "diagnostic-message-callsites": 1,
    "diagnostic-message-templates": 1,
    "static-string-literals": 1,
    "template-literals": 1,
    "environment-access-callsites": 1,
    "dynamic-process-environment-callsites": 1,
    "environment-schema": 1,
    "observability-environment-schema": 1,
    "observability-environment-defaults": 1,
    "root-settings-schema": 1,
    "model-catalog": 1,
    "model-pricing-tiers": 1,
    "model-aliases": 1,
    "tool-registrations": 80,
}
HUMAN_ANALYSIS_DOCS = {
    "analysis/product-surface-evidence-map.md": (
        "SOURCE_INVENTORY_COVERAGE_BEGIN",
        "机器附录：71 类机器清单的证据分类与阅读路由",
        "Derived 阅读模型",
        "矛盾一：让模型自主，但不把执行权交给模型",
        "矛盾二：既要忘掉大部分历史，又要让任务继续成立",
        "矛盾三：既要看见系统，又不能把观测误当成事实",
        "矛盾四：想恢复任务，但系统没有一台时间机器",
        "压力测试五：Artifact 超时后",
        "矛盾六：要调用本机原生能力，又不能把 ABI 当成原始源码",
        "六个压力测试共同暴露出的技术性格",
        "关键不是流程很长，而是四个嵌套生命周期单位各算各的账",
        "Untraced/Inventory only 不是 Boundary",
        "三轴证据坐标",
        "Whole-bundle AST",
        "Prefix-filtered environment union",
        "runtime-authority-lifecycle.svg",
        "product-surface-runtime-planes.svg",
        "evidence-surface-lifecycle.svg",
    ),
    "analysis/completeness-audit.md": (
        "58",
        "57 个客户端能力面",
        "Deep",
        "Inventory only",
        "Boundary",
    ),
    "analysis/builtin-tools-reference.md": (
        "BUILTIN_TOOL_COVERAGE_BEGIN",
        "Workflow",
        "Artifact",
        "CronCreate",
        "LSP",
        "embedded-grep.json",
        "104857600",
        "argv0=rg",
    ),
    "analysis/tool-registration-and-host-surfaces.md": (
        "TOOL_REGISTRATION_COVERAGE_BEGIN",
        "80/80",
        "77 + 3",
        "AST 注册调用点",
        "人工维护",
        "ListPlugins",
        "SearchPlugins",
        "SendUserMessage",
        "Dynamic factory",
        "Boundary",
    ),
    "analysis/brief-mode-and-user-visible-output.md": (
        "Brief Mode",
        "SendUserMessage",
        "DISABLE_BRIEF_MODE_STOP_HOOK",
        "rendered_locally",
        "/api/oauth/file_upload",
        "file_uuid",
        "uploadBriefAttachment",
        "proactive",
        "Boundary",
    ),
    "analysis/plan-mode-and-human-approval.md": (
        "EnterPlanMode",
        "AskUserQuestion",
        "ExitPlanMode",
        "permissionMode",
        "--plan-mode-instructions",
        "AFK",
        "Boundary",
    ),
    "analysis/structured-output-and-schema-contract.md": (
        "StructuredOutput",
        "AJV",
        "additionalProperties",
        "required",
        "validateFormats",
        "endsTurn",
        "error_max_structured_output_retries",
        "Boundary",
    ),
    "analysis/artifact-watch-comment-autoreact.md": (
        "--watch-artifact",
        "permission probe",
        "maxTurns=6",
        "60",
        "30 s",
        "Boundary",
    ),
    "analysis/insights-history-analysis-pipeline.md": (
        "270,336",
        "500",
        "300",
        "30,000",
        "transcript mtime",
        "Boundary",
    ),
    "analysis/cli-startup-files-plugins-deeplinks.md": (
        "--file",
        "--plugin-url",
        "--handle-uri",
        "256 MiB",
        "50:1",
        "prefill",
        "Boundary",
    ),
    "analysis/complex-slash-command-lifecycles.md": (
        "/install-github-app",
        "/team-onboarding",
        "/privacy-settings",
        "/web-setup",
        "/terminal-setup",
        "Boundary",
    ),
    "analysis/claude-design-and-projects.md": (
        "ClaudeDesign",
        "Projects",
        "Mcp-Session-Id",
        "plan_token",
        "durable grant",
        "CLAUDE_PROJECT_UUID",
        "TOCTOU",
        "Boundary",
    ),
    "analysis/repl-programmatic-tool-runtime.md": (
        "CLAUDE_CODE_REPL",
        "tengu_slate_harbor",
        "S_a()",
        "registerTool",
        "600,000",
        "52,428,800",
        "replay drift",
        "Boundary",
    ),
    "analysis/end-conversation-risk-control.md": (
        "EndConversation",
        "tengu_umber_kestrel",
        "model floor",
        "两次调用",
        "background fork",
        "ended-by-model",
        "abort",
        "Boundary",
    ),
    "analysis/remote-routines-runner-and-notifications.md": (
        "RemoteTrigger",
        "ReadNotifications",
        "requeue_session",
        "20,000 ms",
        "90,000",
        "spawn_local",
        "pending",
        "Boundary",
    ),
    "analysis/connectors-catalog-and-mcp-operators.md": (
        "SearchMcpRegistry",
        "SuggestConnectors",
        "enabledInChat",
        "WaitForMcpServers",
        "RefreshMcpTools",
        "kept-previous",
        "user:plugins",
        "Boundary",
    ),
    "analysis/settings-reference.md": (
        "SETTINGS_DIRECT_KEYS_START",
        "156",
        "merge",
        "Static consumer",
    ),
    "analysis/environment-variable-reference.md": (
        "842/842",
        "2161",
        "74 个无静态 consumer",
        "6 个仅通过动态下标",
        "137/137",
        "145 个动态下标调用点",
        "60 个名称可证明",
        "triBool",
        "Opaque/Boundary",
    ),
    "analysis/cli-sdk-output-protocol.md": (
        "42 个 schema 化 control request",
        "46 个观察型 subtype",
        "44 个 Managed Agents event identifier",
        "103 个 slash command",
        "error_max_structured_output_retries",
    ),
    "analysis/cli-command-reference.md": (
        "`90` 个命令路径",
        "`59` 次显式",
        "`65` 组 help/usage case",
        "fast path",
        "handlerOwner",
        "Remote Control",
    ),
    "analysis/plugins-skills-commands-lsp.md": (
        "marketplaceCache",
        "skillListingBudgetFraction",
        "local-jsx",
        "reload-plugins",
        "diagnostics",
    ),
    "analysis/slash-command-reference.md": (
        "SLASH_COMMAND_COVERAGE_BEGIN",
        "103/103",
        "local-jsx",
        "thinClientDispatch",
        "isEnabled:false",
    ),
    "analysis/hooks-event-reference.md": (
        "HOOK_EVENT_COVERAGE_BEGIN",
        "31",
        "PreToolUse",
        "PostToolBatch",
        "不自动重新请求模型",
        "fail closed",
    ),
    "analysis/storage-v5-reference.md": (
        "STORAGE_NAMESPACE_COVERAGE_BEGIN",
        "32 个 namespace",
        "tryCreateV5Backend",
        "updateText",
        "ifUnchangedThrough",
        "tornTailBytes",
        "SharedInode",
        "并发尾追加",
        "Boundary",
    ),
    "analysis/workflow-artifact-design.md": (
        "Workflow",
        "Artifact",
        "Design Sync",
        "TOCTOU",
        "sidecar",
    ),
    "analysis/feature-flags-remote-config.md": (
        "remoteEvalFeatureValues",
        "cachedGrowthBookFeatures",
        "CLAUDE_INTERNAL_FC_OVERRIDES",
        "pendingExposures",
        "360",
    ),
    "analysis/feature-flag-reference.md": (
        "361/361",
        "455/455",
        "444",
        "assignment-resolved",
        "43 个 truly dynamic unresolved",
        "6 个静态 key / 12 个调用点",
        "Opaque name / Static immediate consumer",
        "Static callsite context / key Boundary",
    ),
    "analysis/tui-input-accessibility-media-ide-chrome.md": (
        "Screen reader",
        "Spellcheck",
        "Voice",
        "IDE integration",
        "Claude in Chrome",
    ),
    "analysis/cloud-background-channels.md": (
        "Background Agent",
        "Cron",
        "Channel",
        "Remote Control",
        "self-hosted runner",
    ),
    "analysis/technical-mechanism-atlas.md": (
        "三条必须同时理解的闭环",
        "外部状态",
        "公开原理与本版本实现",
    ),
    "analysis/public-claims-validation.md": (
        "Public",
        "Static",
        "Probe",
        "Boundary",
    ),
    "analysis/runtime-probe-index.md": (
        "literalOutput",
        "exitStatus",
        "状态变化",
        "仍然保留的边界",
    ),
    "analysis/technical-architecture.md": (
        "request",
        "context",
        "telemetry",
    ),
    "analysis/agent-loop.md": (
        "tool_use_id",
        "concurrency-safe",
        "maxTurns",
        "Stop hook",
        "不自动重跑工具自定义",
        "terminal reason",
    ),
    "analysis/context-governance-and-caching.md": (
        "prompt cache",
        "microcompaction",
        "auto-compact",
        "compact boundary",
    ),
    "analysis/sessions-checkpoints-memory.md": (
        "message graph",
        "compact boundary",
        "file checkpoint",
        "MEMORY.md",
        "ifUnchangedThrough",
        "tornTailBytes",
        "SharedInode",
        "并发尾追加",
        "外部状态",
    ),
    "analysis/tools-permissions-hooks.md": (
        "updatedInput",
        "PostToolBatch",
        "不自动重跑 custom validation",
        "不会像 Stop hook 一样自动重入模型",
        "bypassPermissions",
        "fail closed",
        "tool.call",
    ),
    "analysis/mcp-agents-background.md": (
        "defer_loading",
        "generation",
        "maxTurns: 200",
        "permissionMode: bubble",
        "task claim",
        "mailbox",
    ),
    "analysis/resilience-and-recovery.md": (
        "HTTP/API retry",
        "tombstone",
        "reactive compact",
        "terminal reason",
        "副作用",
    ),
    "analysis/models-auth-providers-request.md": (
        "Provider selector",
        "ANTHROPIC_BASE_URL",
        "apiKeyHelper",
        "Request construction",
        "tool_use_id",
    ),
    "analysis/settings-feature-flags-policy.md": (
        "userSettings",
        "policySettings",
        "managed policy",
        "Feature flag",
        "failIfUnavailable",
    ),
    "analysis/tui-ide-remote-cloud.md": (
        "Remote Control",
        "teleport",
        "IDE integration",
        "reconnect",
        "attachment",
    ),
    "analysis/install-update-doctor-lifecycle.md": (
        "Auto-update",
        "DISABLE_AUTOUPDATER",
        "doctor",
        "rollback",
        "SHA-256",
    ),
    "analysis/native-bridge-runtime.md": (
        "N-API",
        "ImageProcessor",
        "ScreenCaptureKit",
        "waitForUrlEvent",
        "Compatible",
    ),
    "analysis/auto-mode-classifier.md": (
        "twoStageClassifier",
        "classifyAllShell",
        "$defaults",
        "PermissionDenied",
        "fail closed",
        "Boundary",
    ),
    "analysis/plugin-evaluation-harness.md": (
        "with-without",
        "六类 grader",
        "3 次独立 judge",
        "scaffold_script",
        "partial_reason",
        "Boundary",
    ),
    "analysis/runtime-supervision-and-processes.md": (
        "processWrapper",
        "Rendezvous",
        "256 KiB",
        "respawn",
        "asyncRewake",
        "launcher exit 0 但 Claude 尚未 ready",
        "Boundary",
    ),
    "analysis/enterprise-gateway-runtime.md": (
        "Gateway session",
        "CRI",
        "JWKS",
        "Postgres",
        "OTLP",
        "failover",
        "`x-api-key` 一旦出现，就不再回退 bearer",
        "Boundary",
    ),
    "analysis/auth-account-and-subscription-lifecycle.md": (
        "forceLoginMethod",
        "forceLoginOrgUUID",
        "preserveInProcessTokens",
        "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
        "`setup-token`",
        "performLogout",
    ),
    "analysis/onboarding-workspace-trust-and-safe-startup.md": (
        "hasCompletedOnboarding",
        "hasTrustDialogAccepted",
        "gated_grants_backstop_declined",
        "`--safe-mode`",
        "`--bare`",
        "post-trust",
    ),
    "analysis/thinking-effort-and-fast-mode.md": (
        "set_max_thinking_tokens",
        "effort_cost_index",
        "adaptive",
        "effortLevel",
        "Fast Mode",
        "429/529",
    ),
    "analysis/usage-cost-credits-and-limits.md": (
        "modelUsage",
        "get_usage",
        "resetAt",
        "Usage Credits",
        "auto-resume",
        "rearm",
    ),
    "analysis/project-purge-import-and-data-lifecycle.md": (
        "Project purge",
        "TOCTOU",
        "prompt history",
        "Preview digest",
        "manifest mismatch",
        "best-effort",
    ),
    "analysis/sandbox-install-and-runtime-enforcement.md": (
        "dangerouslyDisableSandbox",
        "single promise",
        "`installed: true`",
        "UAC",
        "ACL",
        "sandbox install",
    ),
    "analysis/network-proxy-ca-and-mtls.md": (
        "NO_PROXY",
        "proxyAuthHelper",
        "NODE_EXTRA_CA_CERTS",
        "HTTPS CONNECT",
        "NodeHttpHandler",
        "mTLS",
    ),
    "analysis/active-goal-and-stop-loop.md": (
        "activeGoal",
        "goal_status",
        "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP",
        "maxTurns",
        "active_goal",
        "Stop hook block discarded",
    ),
    "analysis/background-model-tasks-and-memory-consolidation.md": (
        "Auto Dream",
        "Away Summary",
        "Post-turn Summary",
        "Prompt Suggestion",
        "Feedback Draft",
        "skipTranscript",
        "skipCacheWrite",
        "consolidate-lock",
    ),
    "analysis/advisor-dual-model-runtime.md": (
        "advisor_rank",
        "advisor_20260301",
        "server_tool_use",
        "advisor_tool_result",
        "retry:advisor-strip",
        "advisorModel",
    ),
    "analysis/ultrareview-cloud-review.md": (
        "allow_remote_sessions",
        "remote_agent",
        "preflight",
        "add_issue_comment",
        "poll_connection_lost",
        "postReviewTo",
    ),
    "analysis/inventory-field-guide.md": (
        "comparisonKey",
        "comparisonValue",
        "unresolvedSpreads",
    ),
    "analysis/telemetry.md": (
        "OpenTelemetry",
        "Datadog",
        "GrowthBook",
    ),
    "analysis/telemetry-event-catalog.md": (
        "TELEMETRY_EVENT_CATALOG_BEGIN",
        "TELEMETRY_SCENARIO_SEMANTIC_INDEX",
        "first-party-events:1441",
        "dynamic-callsites:43",
        "datadog-allowlist:181",
        "otel-events:26",
        "otel-metrics:8",
        "tengu_api_query",
        "tengu_tool_use_show_permission_request",
        "tengu_reactive_compact_succeeded",
        "tengu_transcript_writer_recovered",
        "tengu_other` 不能当作",
        "Boundary",
    ),
    "analysis/api-beta-route-ownership.md": (
        "API_PATH_CATALOG_START",
        "BETA_IDENTIFIER_CATALOG_START",
        "99 条",
        "53 个",
        "fallback beta",
        "bundled gateway handler",
        "128",
        "1 MiB",
        "Boundary",
    ),
    "analysis/error-diagnostic-atlas.md": (
        "ERROR_DIAGNOSTIC_METRICS_START",
        "4,831",
        "5,403",
        "AbortError",
        "tool_expected_error",
        "10,485,760",
        "4,000",
        "Boundary",
    ),
    "analysis/source-surface.md": (
        "Observed",
        "Derived",
        "Heuristic",
    ),
}
HUMAN_ANALYSIS_MINIMUMS = {
    "analysis/product-surface-evidence-map.md": (27000, 14),
    "analysis/completeness-audit.md": (5000, 6),
    "analysis/builtin-tools-reference.md": (9000, 10),
    "analysis/tool-registration-and-host-surfaces.md": (20000, 10),
    "analysis/brief-mode-and-user-visible-output.md": (14000, 12),
    "analysis/plan-mode-and-human-approval.md": (10000, 10),
    "analysis/structured-output-and-schema-contract.md": (10000, 10),
    "analysis/artifact-watch-comment-autoreact.md": (8500, 12),
    "analysis/insights-history-analysis-pipeline.md": (8750, 14),
    "analysis/cli-startup-files-plugins-deeplinks.md": (10500, 16),
    "analysis/complex-slash-command-lifecycles.md": (11000, 20),
    "analysis/claude-design-and-projects.md": (18000, 12),
    "analysis/repl-programmatic-tool-runtime.md": (14000, 10),
    "analysis/end-conversation-risk-control.md": (14000, 10),
    "analysis/remote-routines-runner-and-notifications.md": (20000, 12),
    "analysis/connectors-catalog-and-mcp-operators.md": (18000, 12),
    "analysis/settings-reference.md": (18000, 10),
    "analysis/environment-variable-reference.md": (100000, 10),
    "analysis/cli-sdk-output-protocol.md": (12000, 12),
    "analysis/cli-command-reference.md": (15000, 18),
    "analysis/plugins-skills-commands-lsp.md": (10000, 10),
    "analysis/slash-command-reference.md": (12000, 10),
    "analysis/hooks-event-reference.md": (15000, 10),
    "analysis/storage-v5-reference.md": (18000, 12),
    "analysis/workflow-artifact-design.md": (12000, 10),
    "analysis/feature-flags-remote-config.md": (18000, 12),
    "analysis/feature-flag-reference.md": (80000, 10),
    "analysis/tui-input-accessibility-media-ide-chrome.md": (24000, 15),
    "analysis/cloud-background-channels.md": (24000, 15),
    "analysis/technical-mechanism-atlas.md": (6000, 8),
    "analysis/public-claims-validation.md": (6000, 8),
    "analysis/sessions-checkpoints-memory.md": (6000, 10),
    "analysis/tools-permissions-hooks.md": (6000, 10),
    "analysis/mcp-agents-background.md": (6000, 10),
    "analysis/resilience-and-recovery.md": (6000, 10),
    "analysis/models-auth-providers-request.md": (6000, 10),
    "analysis/settings-feature-flags-policy.md": (6000, 10),
    "analysis/tui-ide-remote-cloud.md": (6000, 10),
    "analysis/install-update-doctor-lifecycle.md": (5000, 8),
    "analysis/native-bridge-runtime.md": (6000, 10),
    "analysis/runtime-probe-index.md": (9000, 10),
    "analysis/auto-mode-classifier.md": (14000, 15),
    "analysis/plugin-evaluation-harness.md": (11000, 12),
    "analysis/runtime-supervision-and-processes.md": (11500, 12),
    "analysis/enterprise-gateway-runtime.md": (45000, 30),
    "analysis/auth-account-and-subscription-lifecycle.md": (12000, 18),
    "analysis/onboarding-workspace-trust-and-safe-startup.md": (10500, 17),
    "analysis/thinking-effort-and-fast-mode.md": (14500, 22),
    "analysis/usage-cost-credits-and-limits.md": (15500, 28),
    "analysis/project-purge-import-and-data-lifecycle.md": (12500, 20),
    "analysis/sandbox-install-and-runtime-enforcement.md": (14500, 20),
    "analysis/network-proxy-ca-and-mtls.md": (16000, 28),
    "analysis/active-goal-and-stop-loop.md": (8000, 11),
    "analysis/background-model-tasks-and-memory-consolidation.md": (9000, 12),
    "analysis/advisor-dual-model-runtime.md": (6500, 10),
    "analysis/ultrareview-cloud-review.md": (9000, 12),
    "analysis/telemetry-event-catalog.md": (1000000, 20),
    "analysis/api-beta-route-ownership.md": (68000, 10),
    "analysis/error-diagnostic-atlas.md": (15000, 16),
}
READER_FIRST_ANALYSIS_DOCS = {
    "analysis/product-surface-evidence-map.md": "agent-loop-lifecycle",
    "analysis/builtin-tools-reference.md": "builtin-tool-lifecycle",
    "analysis/tool-registration-and-host-surfaces.md": "tool-registration-host-lifecycle",
    "analysis/brief-mode-and-user-visible-output.md": "brief-user-output-lifecycle",
    "analysis/plan-mode-and-human-approval.md": "plan-mode-lifecycle",
    "analysis/structured-output-and-schema-contract.md": "structured-output-lifecycle",
    "analysis/artifact-watch-comment-autoreact.md": "artifact-watch-autoreact-lifecycle",
    "analysis/insights-history-analysis-pipeline.md": "insights-history-analysis-lifecycle",
    "analysis/cli-startup-files-plugins-deeplinks.md": "cli-startup-assets-lifecycle",
    "analysis/complex-slash-command-lifecycles.md": "complex-slash-commands-lifecycle",
    "analysis/claude-design-and-projects.md": "claude-design-projects-lifecycle",
    "analysis/repl-programmatic-tool-runtime.md": "repl-programmatic-tool-lifecycle",
    "analysis/end-conversation-risk-control.md": "end-conversation-risk-control",
    "analysis/remote-routines-runner-and-notifications.md": "remote-routines-runner-notifications-lifecycle",
    "analysis/connectors-catalog-and-mcp-operators.md": "connectors-catalog-mcp-operators-lifecycle",
    "analysis/settings-reference.md": "settings-resolution-lifecycle",
    "analysis/cli-sdk-output-protocol.md": "cli-sdk-protocol-lifecycle",
    "analysis/cli-command-reference.md": "cli-command-routing",
    "analysis/plugins-skills-commands-lsp.md": "plugin-skill-lsp-lifecycle",
    "analysis/slash-command-reference.md": "slash-command-lifecycle",
    "analysis/hooks-event-reference.md": "hooks-event-lifecycle",
    "analysis/storage-v5-reference.md": "storage-v5-lifecycle",
    "analysis/workflow-artifact-design.md": "workflow-artifact-design-lifecycle",
    "analysis/feature-flags-remote-config.md": "feature-flags-remote-config-lifecycle",
    "analysis/tui-input-accessibility-media-ide-chrome.md": "tui-media-ide-chrome-lifecycle",
    "analysis/cloud-background-channels.md": "cloud-background-channels",
    "analysis/technical-mechanism-atlas.md": "system-lifecycle",
    "analysis/technical-architecture.md": "runtime-layers",
    "analysis/agent-loop.md": "agent-loop-lifecycle",
    "analysis/context-governance-and-caching.md": "context-control-lifecycle",
    "analysis/sessions-checkpoints-memory.md": "session-recovery-lifecycle",
    "analysis/tools-permissions-hooks.md": "tool-control-lifecycle",
    "analysis/mcp-agents-background.md": "mcp-agent-lifecycle",
    "analysis/resilience-and-recovery.md": "recovery-layers",
    "analysis/models-auth-providers-request.md": "request-assembly-lifecycle",
    "analysis/settings-feature-flags-policy.md": "settings-policy-lifecycle",
    "analysis/tui-ide-remote-cloud.md": "interface-ownership-lifecycle",
    "analysis/install-update-doctor-lifecycle.md": "release-lifecycle",
    "analysis/native-bridge-runtime.md": "native-bridge-lifecycle",
    "analysis/telemetry.md": "telemetry-pipeline",
    "analysis/telemetry-event-catalog.md": "telemetry-event-catalog-lifecycle",
    "analysis/api-beta-route-ownership.md": "api-beta-route-ownership-lifecycle",
    "analysis/error-diagnostic-atlas.md": "error-diagnostic-atlas-lifecycle",
    "analysis/inventory-field-guide.md": "inventory-reading-lifecycle",
    "analysis/source-surface.md": "evidence-surface-lifecycle",
    "analysis/auto-mode-classifier.md": "auto-mode-classifier",
    "analysis/plugin-evaluation-harness.md": "plugin-evaluation-lifecycle",
    "analysis/runtime-supervision-and-processes.md": "runtime-supervision-lifecycle",
    "analysis/enterprise-gateway-runtime.md": "enterprise-gateway-runtime",
    "analysis/auth-account-and-subscription-lifecycle.md": "auth-account-lifecycle",
    "analysis/onboarding-workspace-trust-and-safe-startup.md": "onboarding-trust-lifecycle",
    "analysis/thinking-effort-and-fast-mode.md": "thinking-effort-fast-mode",
    "analysis/usage-cost-credits-and-limits.md": "usage-cost-credits-limits",
    "analysis/project-purge-import-and-data-lifecycle.md": "project-data-lifecycle",
    "analysis/sandbox-install-and-runtime-enforcement.md": "sandbox-install-runtime",
    "analysis/network-proxy-ca-and-mtls.md": "network-proxy-ca-mtls",
    "analysis/active-goal-and-stop-loop.md": "active-goal-stop-loop",
    "analysis/background-model-tasks-and-memory-consolidation.md": "background-model-tasks",
    "analysis/advisor-dual-model-runtime.md": "advisor-dual-model",
    "analysis/ultrareview-cloud-review.md": "ultrareview-cloud-review",
}
TOPIC_DEPTH_CONTRACTS = {
    "plan-mode": {
        "document": "analysis/plan-mode-and-human-approval.md",
        "visual_stem": "plan-mode-lifecycle",
        "capability": 52,
        "capability_markers": (r"\bPlan Mode\b", r"计划模式"),
        "lifecycle_anchors": (
            ("EnterPlanMode", r"\bEnterPlanMode\b"),
            ("permission mode", r"(?:permissionMode|permission mode|权限模式)"),
            ("AskUserQuestion", r"\bAskUserQuestion\b"),
            ("ExitPlanMode", r"\bExitPlanMode\b"),
            ("human approval outcome", r"(?:批准|拒绝|approve|reject|approval)"),
            ("mode restoration", r"(?:恢复|restore)"),
            ("implementation continuation", r"(?:实施|implement)"),
        ),
        "gate_markers": (
            ("useAutoModeDuringPlan", r"\buseAutoModeDuringPlan\b"),
            ("custom plan instructions", r"--plan-mode-instructions"),
            ("question count range", r"1\s*[-–—]\s*4"),
            ("option count range", r"2\s*[-–—]\s*4"),
        ),
        "failure_markers": (
            ("AFK timeout", r"\bAFK\b|超时"),
            ("rejection or feedback", r"拒绝|反馈|reject|feedback"),
            ("permission restoration", r"恢复|restore"),
        ),
        "visual_anchors": (
            "EnterPlanMode",
            "AskUserQuestion",
            "ExitPlanMode",
        ),
        "minimum_lifecycle_steps": 6,
        "minimum_evidence_references": 5,
        "lifecycle_phase_pattern": r"Phase\s+(\d+)",
        "gate_scope": "document",
        "section_patterns": {
            "state ownership": r".*(?:状态所有权|状态归属|先分清.*责任对象).*",
            "gates and thresholds": r".*Plan Mode 不是单层提示词.*",
            "failure and recovery": r".*完整失败矩阵.*",
            "user impact": r".*(?:用户影响|Token、延迟、成本、隐私与副作用).*",
            "evidence": r".*证据等级与明确边界.*",
            "boundary": r"Boundary",
        },
    },
    "structured-output": {
        "document": "analysis/structured-output-and-schema-contract.md",
        "visual_stem": "structured-output-lifecycle",
        "capability": 53,
        "capability_markers": (r"\bStructured Output\b", r"结构化输出"),
        "lifecycle_anchors": (
            ("JSON Schema input", r"JSON Schema|jsonSchema"),
            ("normalization and AJV", r"(?:规范化|normaliz).{0,100}(?:AJV|strict)|(?:AJV|strict).{0,100}(?:规范化|normaliz)"),
            ("StructuredOutput injection", r"\bStructuredOutput\b"),
            ("tool input validation", r"(?:tool_use|工具调用).{0,120}(?:校验|validat)|(?:校验|validat).{0,120}(?:tool_use|工具调用)"),
            ("retry or terminal error", r"(?:错误链反馈|修正轮次|重试|retry|error_max_structured_output_retries)"),
            ("structured result end-turn", r"(?:structured_output|endsTurn)"),
        ),
        "gate_markers": (
            ("additionalProperties", r"\badditionalProperties\b"),
            ("required", r"\brequired\b"),
            ("validateFormats", r"\bvalidateFormats\b"),
            ("strict fallback", r"strict.{0,100}(?:回退|fallback)|(?:回退|fallback).{0,100}strict"),
        ),
        "failure_markers": (
            ("schema validation failure", r"schema.{0,100}(?:失败|错误|invalid)|(?:失败|错误|invalid).{0,100}schema"),
            ("retry exhaustion", r"(?:重试耗尽|retry.{0,40}(?:exhaust|limit)|error_max_structured_output_retries)"),
            ("terminal result", r"(?:终态|terminal|endsTurn|is_error)"),
        ),
        "visual_anchors": (
            "JSON Schema",
            "StructuredOutput",
            "structured_output",
        ),
        "minimum_lifecycle_steps": 6,
        "minimum_evidence_references": 5,
    },
    "claude-design-projects": {
        "document": "analysis/claude-design-and-projects.md",
        "visual_stem": "claude-design-projects-lifecycle",
        "capability": 23,
        "capability_markers": (
            r"\bDesignSync\b",
            r"\bClaudeDesign\b",
            r"\bProjects\b",
            r"文件传输",
        ),
        "lifecycle_anchors": (
            ("Design assembly gate", r"装配 gate"),
            ("MCP initialize", r"\binitialize\b"),
            ("dynamic tools list", r"tools/list"),
            ("local safety schema", r"本地 schema"),
            ("catalog hash", r"catalog hash"),
            ("first-party JSON transport", r"first-party JSON"),
            ("Design consent", r"\bconsent\b"),
            ("path plan token", r"plan_token"),
            ("durable project grant", r"durable project grant"),
            ("bounded result mapping", r"result.{0,100}(?:三层|受限|cap)"),
            ("Projects dispatcher", r"(?:固定五方法|五个 method)"),
            ("Projects scope expansion", r"(?:扩展 OAuth scope|scope expansion)"),
            ("Projects dual transport", r"session-JWT.{0,100}teleport-org"),
            ("project read", r"project_read"),
            ("RAG fallback", r"project_search.{0,100}403 fallback"),
            ("TOCTOU upload", r"local_path.{0,100}(?:TOCTOU|路径替换)"),
            ("knowledge budget", r"knowledge budget|知识预算"),
            ("external data boundary", r"(?:data|数据).{0,100}(?:instructions|指令)"),
        ),
        "gate_markers": (
            ("Design policy", r"\ballow_design_sync\b"),
            ("Design feature", r"\btengu_omelette_fouet\b"),
            ("path-plan TTL", r"900,000 ms"),
            ("Projects policy", r"\ballow_projects_tool\b"),
            ("attached project", r"\bCLAUDE_PROJECT_UUID\b"),
            ("local upload cap", r"26,214,400 bytes"),
        ),
        "failure_markers": (
            ("MCP 404 reinitialize", r"404.{0,220}(?:re-initialize|重试一次)"),
            ("401 refresh", r"401.{0,100}(?:刷新|refresh)"),
            (
                "consent or grant retry",
                r"needs_consent|needs_project_grant",
            ),
            ("RAG 403 fallback", r"RAG 403|403.{0,80}fallback"),
            ("TOCTOU rejection", r"local_path.{0,100}(?:替换|replaced)"),
            (
                "non-atomic remote replace",
                r"remote-session replace.{0,120}(?:无通用 rollback|不是原子事务)",
            ),
        ),
        "visual_anchors": (
            "Normal Agent tool pipeline",
            "initialize",
            "Permission decision",
            "Projects: attached project",
            "Write path",
            "External state persists",
        ),
        "minimum_lifecycle_steps": 17,
        "minimum_evidence_references": 8,
        "evidence_scope": "document",
        "lifecycle_phase_pattern": r"(\d+)\.",
        "lifecycle_phase_heading_level": 4,
        "section_patterns": {
            "evidence": r"证据",
        },
    },
    "repl-runtime": {
        "document": "analysis/repl-programmatic-tool-runtime.md",
        "visual_stem": "repl-programmatic-tool-lifecycle",
        "capabilities": (7,),
        "capability_markers_by_number": {
            7: (r"核心终端", r"条件工具", r"宿主注册"),
        },
        "lifecycle_anchors": (
            ("outer execution budget", r"(?:执行预算|timeout)"),
            ("context selection", r"(?:复用、恢复还是新建 context|context key)"),
            ("sealed VM", r"sealed VM|受控全局"),
            ("transpile and evaluate", r"Transpiler|transpile"),
            ("inner tool pipeline", r"内层工具.{0,80}(?:管线|pipeline)"),
            ("watchdog", r"watchdog"),
            ("result envelope", r"(?:结果|Result).{0,80}(?:表示|envelope)"),
            ("replay log", r"replay log|重放日志"),
            ("replay drift", r"(?:replay )?drift|非确定性"),
        ),
        "gate_markers": (
            ("CLAUDE_CODE_REPL", r"\bCLAUDE_CODE_REPL\b"),
            ("entrypoint", r"\bentrypoint\b"),
            ("tengu_slate_harbor", r"\btengu_slate_harbor\b"),
            ("dormant async gate", r"S_a\(\)"),
        ),
        "failure_markers": (
            ("permission denial", r"Hook/permission|权限拒绝|permission拒绝"),
            ("timeout and watchdog", r"timeout|时间用尽|watchdog"),
            ("replay drift", r"replay drift|drift"),
            ("side-effect recovery", r"副作用.{0,120}(?:保留|补偿|回滚|重跑)"),
        ),
        "visual_anchors": (
            "REPL tool_use",
            "Sealed VM context",
            "Inner tool pipeline",
            "Replay log",
        ),
        "minimum_lifecycle_steps": 9,
        "minimum_evidence_references": 6,
        "section_patterns": {
            "ordered lifecycle": r".*完整执行顺序.*",
            "gates and thresholds": r".*Gate、默认值与本版实际可达分支.*",
            "boundary": r"Boundary",
        },
    },
    "end-conversation": {
        "document": "analysis/end-conversation-risk-control.md",
        "visual_stem": "end-conversation-risk-control",
        "capabilities": (35,),
        "capability_markers_by_number": {
            35: (r"本地风控", r"企业治理", r"风险"),
        },
        "lifecycle_anchors": (
            ("eligibility assembly", r"(?:装配|资格判断|isEnabled)"),
            ("model receives rules", r"(?:完整规则|Prompt|guidance)"),
            ("first reflection call", r"第一次.{0,80}(?:反思|reflection)"),
            ("history confirmation", r"history.{0,80}(?:验证|扫描|确认)"),
            ("background fork stop", r"background fork|fork"),
            ("marker persistence", r"ended-by-model|marker"),
            ("abort and terminal", r"abort.{0,100}(?:终态|terminal|TUI|print)"),
            ("resume terminal restoration", r"resume.{0,100}(?:恢复|终态|endedByModel)"),
        ),
        "gate_markers": (
            ("entrypoint scope", r"\bentrypoint\b"),
            ("model floor", r"model floor|模型族与版本"),
            ("feature config", r"\btengu_umber_kestrel\b"),
            ("runtime blocker", r"WGo\(\)"),
        ),
        "failure_markers": (
            ("first-call reflection", r"第一次误调用|reflection"),
            ("new-user boundary", r"普通user消息|user boundary"),
            ("marker persistence failure", r"marker append失败|marker.{0,80}失败"),
            ("irreversible side effects", r"副作用.{0,100}(?:补偿|回滚|保留)"),
        ),
        "visual_anchors": (
            "Eligible main session",
            "First EndConversation call",
            "Second call history check",
            "Transcript marker",
            "Abort controller",
        ),
        "minimum_lifecycle_steps": 8,
        "minimum_evidence_references": 6,
    },
    "remote-ops": {
        "document": "analysis/remote-routines-runner-and-notifications.md",
        "visual_stem": "remote-routines-runner-notifications-lifecycle",
        "capabilities": (29, 31),
        "capability_markers_by_number": {
            29: (r"Cron", r"loops", r"channels", r"主动通知"),
            31: (r"CCR", r"BYOC", r"runner", r"cloud workflow"),
        },
        "lifecycle_anchors": (
            ("tool assembly", r"工具装配"),
            ("RemoteTrigger routing", r"\bRemoteTrigger\b"),
            ("OAuth request timeout", r"OAuth.{0,100}(?:20 秒|20,000 ms|timeout)"),
            ("server-parsed schedule", r"服务端解释后的时间|next_run_at"),
            ("run listing", r"\blist_runs\b"),
            ("run log", r"\bget_run_log\b"),
            ("runner authentication", r"Runner.{0,100}(?:认证|OAuth-only|first-party)"),
            ("runner operator tools", r"runner 工具|runner tools"),
            ("detached spawn", r"\bspawn_local\b"),
            ("health metrics log", r"Health、metrics 和 log|health.{0,80}metrics.{0,80}log"),
            ("requeue approval", r"\brequeue_session\b"),
            ("notification validation", r"Notification.{0,100}(?:校验|去重)"),
            ("nudge", r"\bNudge\b|提醒模型"),
            ("notification drain", r"\bReadNotifications\b"),
            ("Agent Loop feedback", r"Agent Loop|下一轮"),
        ),
        "gate_markers": (
            ("RemoteTrigger actions", r"\bRemoteTrigger\b"),
            ("remote timeout", r"20,000 ms"),
            (
                "runner local probe timeout",
                r"Local health/metrics timeout.{0,80}2,000 ms",
            ),
            ("pending backpressure", r"pending cap|Pending 满 100|`100`"),
            ("drain budget", r"90,000"),
        ),
        "failure_markers": (
            ("write timeout observation", r"20s timeout|先.{0,60}(?:get|list).{0,60}查状态"),
            ("assignment conflict", r"assignment stale|HTTP 409|conflict"),
            ("notification backpressure", r"Pending 满 100|buffer cap|不 ack"),
            ("subagent drain rejection", r"Subagent.{0,80}ReadNotifications|agentId"),
        ),
        "visual_anchors": (
            "RemoteTrigger 控制面",
            "Runner 承载与运维",
            "notification queue",
            "主 Agent Loop",
        ),
        "minimum_lifecycle_steps": 15,
        "minimum_evidence_references": 6,
    },
    "connector-catalog-mcp": {
        "document": "analysis/connectors-catalog-and-mcp-operators.md",
        "visual_stem": "connectors-catalog-mcp-operators-lifecycle",
        "capabilities": (9,),
        "capability_markers_by_number": {
            9: (r"MCP", r"Tool Search", r"动态刷新"),
        },
        "lifecycle_anchors": (
            ("connector host assembly", r"Connector registry tools|first-party remote host"),
            ("registry search", r"\bSearchMcpRegistry\b"),
            ("connector suggestion", r"\bSuggestConnectors\b"),
            ("installed connector list", r"\bListConnectors\b"),
            ("connector route contract", r"opt-in|错误合同"),
            ("catalog OAuth scope", r"OAuth scope|user:plugins"),
            ("dynamic catalog factories", r"SearchPlugins.{0,80}SearchSkills|动态 factory"),
            ("account catalog lists", r"ListPlugins.{0,100}ListSkills"),
            ("suggestion cards", r"Suggestion tool|卡片"),
            ("bounded MCP wait", r"\bWaitForMcpServers\b"),
            ("MCP tool refresh", r"\bRefreshMcpTools\b"),
            ("MCP resources", r"resource.{0,80}(?:discovery|read|读取)|List/Read resource"),
            ("request tool pool", r"下一次 request.{0,100}工具池|真实工具池"),
        ),
        "gate_markers": (
            ("remote first-party host", r"CLAUDE_CODE_REMOTE.{0,40}firstParty"),
            ("connector timeout", r"15,000 ms"),
            ("bounded server wait", r"WaitForMcpServers.{0,80}5,000 ms"),
            ("refresh fallback", r"previous tools|保留 previous tools"),
            ("catalog pagination", r"page cap|20"),
        ),
        "failure_markers": (
            ("connector opt-in", r"opt-in required|opt_in_required"),
            ("catalog entitlement ambiguity", r"Catalog 403|not_entitled|entitlement"),
            ("MCP auth or pending", r"still pending|needs auth|needsAuth"),
            ("refresh keeps previous", r"kept-previous|旧 tools 保留"),
            ("resource invalidation", r"Resource read 404|invalidate list cache"),
        ),
        "visual_anchors": (
            "Connector / Plugin / Skill Catalog",
            "当前 Chat MCP clients",
            "MCP operators",
            "真实工具池",
        ),
        "minimum_lifecycle_steps": 13,
        "minimum_evidence_references": 6,
    },
    "artifact-watch": {
        "document": "analysis/artifact-watch-comment-autoreact.md",
        "visual_stem": "artifact-watch-autoreact-lifecycle",
        "capability": 54,
        "capability_markers": (r"Artifact Watch", r"评论自动响应"),
        "lifecycle_anchors": (
            ("local interactive watch gate", r"--watch-artifact"),
            ("baseline and digest", r"baseline|baselined"),
            ("untrusted triage", r"triage"),
            ("read-only analyst", r"comment-thread-analyst|只读 analyst"),
            ("permission probe", r"permission probe"),
            ("acknowledgment and full work", r"acknowledgment"),
        ),
        "gate_markers": (
            ("coalesce window", r"5(?:,000)?\s*(?:ms|秒|s)"),
            ("confirm dwell", r"2(?:,000)?\s*(?:ms|秒|s)"),
            ("hourly cap", r"60"),
            ("loop breaker window", r"30\s*(?:s|秒)"),
            ("breaker count", r"达到\s*`?3`?|>=\s*3"),
        ),
        "failure_markers": (
            ("comment read failure", r"评论读取失败|Artifact read"),
            ("triage fallback", r"Triage 异常|pipeline"),
            ("permission refusal", r"Permission ask/deny|probe 非 `allow`"),
            ("loop breaker", r"回复回路|breaker"),
        ),
        "visual_anchors": (
            "外部 Artifact 评论",
            "本地 watch 扫描",
            "无工具 triage",
            "单线程只读 analyst",
            "写入前控制",
            "受约束 composer",
            "远端 Artifact 状态",
        ),
        "minimum_lifecycle_steps": 5,
        "minimum_evidence_references": 8,
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"普通成功路径",
            "gates and thresholds": r"Gate、默认值与断路器",
            "user impact": r"Token、延迟、费用、隐私、安全和恢复影响",
            "boundary": r"Static 与 Boundary",
        },
    },
    "insights-pipeline": {
        "document": "analysis/insights-history-analysis-pipeline.md",
        "visual_stem": "insights-history-analysis-lifecycle",
        "capability": 55,
        "capability_markers": (r"/insights", r"历史分析"),
        "lifecycle_anchors": (
            ("transcript scan", r"扫描 transcript"),
            ("metadata cache", r"metadata"),
            ("bounded refresh", r"200"),
            ("session text reduction", r"session text|500.{0,60}300"),
            ("facet extraction", r"facet"),
            ("seven plus one analysis", r"7\+1|7 个专题"),
            ("HTML persistence", r"HTML"),
        ),
        "gate_markers": (
            ("metadata refresh caps", r"200"),
            ("facet cap", r"50"),
            ("message truncation", r"500.{0,80}300"),
            ("long session chunks", r"30,?000.{0,100}25,?000"),
            ("facet output cap", r"4,?096"),
            ("section output cap", r"8,?192"),
        ),
        "failure_markers": (
            ("chunk summary fallback", r"2,?000"),
            ("stale facet", r"facet.{0,120}(?:mtime|过期|陈旧)"),
            ("partial section failure", r"section 为空|专题失败"),
            ("report write failure", r"HTML 写入失败|写文件失败|report write"),
        ),
        "visual_anchors": (
            "本地 transcripts",
            "session metadata",
            "模型输入缩减",
            "facet cache",
            "全局聚合",
            "7 个并行专题 + 1 个总览",
            "本地 HTML",
            "陈旧语义风险",
        ),
        "minimum_lifecycle_steps": 6,
        "minimum_evidence_references": 8,
        "gate_scope": "document",
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"完整成功路径",
            "user impact": r"Token、延迟、费用、隐私、安全和恢复影响",
            "boundary": r"Static 与 Boundary",
        },
    },
    "cli-startup-assets": {
        "document": "analysis/cli-startup-files-plugins-deeplinks.md",
        "visual_stem": "cli-startup-assets-lifecycle",
        "capability": 56,
        "capability_markers": (r"CLI 启动", r"--file", r"Deep Link"),
        "lifecycle_anchors": (
            ("entry classification", r"识别入口"),
            ("dedicated gates", r"专属 gate"),
            ("download or decode", r"获取或解码"),
            ("local state", r"本地状态"),
            ("session mounting", r"挂载到会话"),
            ("explicit model submission", r"显式提交才进入模型"),
        ),
        "gate_markers": (
            ("file retry and timeout", r"3 次.{0,80}60s|60s.{0,80}3 次"),
            ("file concurrency", r"并发 5|5 个文件并发"),
            ("plugin download cap", r"256\s*MiB"),
            ("zip total cap", r"1\s*GiB"),
            ("zip file count", r"100,?000"),
            ("zip ratio", r"50:1"),
            ("deep link failure latch", r"24\s*h"),
        ),
        "failure_markers": (
            ("file auth or missing", r"404/401/403|token 缺失"),
            (
                "zip rejection",
                r"ZIP.{0,100}(?:拒绝|超限|超阈值|防护|bomb|path traversal)",
            ),
            ("cached plugin fallback", r"复用 session cache|cache"),
            ("deep link injection rejection", r"argument injection|argv 注入"),
        ),
        "visual_anchors": (
            "启动外部输入",
            "入口校验",
            "受限网络获取",
            "本地资源",
            "会话运行时",
            "输入框状态",
            "Messages 请求",
        ),
        "minimum_lifecycle_steps": 6,
        "minimum_evidence_references": 10,
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"端到端状态机",
            "gates and thresholds": r"Gate、默认值与状态归属",
            "user impact": r"Token、延迟、费用、隐私、安全和恢复影响",
            "boundary": r"Static 与 Boundary",
        },
    },
    "complex-slash-commands": {
        "document": "analysis/complex-slash-command-lifecycles.md",
        "visual_stem": "complex-slash-commands-lifecycle",
        "capability": 57,
        "capability_markers": (r"复杂 Slash Command", r"/install-github-app"),
        "lifecycle_anchors": (
            ("entry gates", r"入口与可用性 gate"),
            ("state discovery", r"现状发现"),
            ("user confirmation", r"用户确认"),
            ("side-effect commit", r"提交副作用"),
            ("verification", r"验证与结果"),
        ),
        "gate_markers": (
            ("GitHub setup", r"/install-github-app"),
            ("onboarding scan days", r"30 天"),
            ("transcript size cap", r"50\s*MiB"),
            ("session descriptor cap", r"descriptor.{0,20}60|60 条"),
            ("privacy retention copy", r"30\s*天.{0,80}5\s*年"),
        ),
        "failure_markers": (
            ("GitHub partial failure", r"GitHub 流程中途失败|422"),
            ("privacy refresh failure", r"privacy 写后重读失败"),
            ("environment partial success", r"environment 创建失败"),
            ("terminal backup restore", r"backup 恢复|Terminal\.app 写失败"),
        ),
        "visual_anchors": (
            "复杂 slash command",
            "入口 gate",
            "发现当前状态",
            "用户确认",
            "提交副作用",
            "重新读取或验证",
            "外部持久状态",
        ),
        "minimum_lifecycle_steps": 5,
        "minimum_evidence_references": 8,
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"共同生命周期",
            "user impact": r"Token、延迟、费用、隐私、安全和恢复影响",
            "boundary": r"Static 与 Boundary",
        },
    },
    "telemetry-event-catalog": {
        "document": "analysis/telemetry-event-catalog.md",
        "visual_stem": "telemetry-event-catalog-lifecycle",
        "capabilities": (12,),
        "capability_markers_by_number": {
            12: (r"Telemetry", r"OTEL", r"Datadog", r"诊断"),
        },
        "lifecycle_anchors": (
            ("business callsite", r"H\(name, payload\)|Fv\(name, payload\)|Nd\(name, attributes\)"),
            ("global sink", r"一方全局 sink"),
            ("provider queue", r"一方 logger provider"),
            ("sampling", r"共享流量门与远程采样"),
            ("envelope", r"envelope builder"),
            ("batch exporter", r"batch exporter"),
            ("401 fallback", r"401"),
            ("failed batch recovery", r"失败恢复"),
            ("Datadog", r"Datadog forwarding"),
            ("OTEL", r"OTEL `Nd`"),
            ("shutdown", r"flush / shutdown"),
        ),
        "gate_markers": (
            ("sink FIFO", r"1,000"),
            ("pre-init queue", r"1,024"),
            ("provider queue", r"8,192"),
            ("Datadog allowlist", r"181"),
            ("dynamic event callsites", r"43"),
            ("scenario semantic index", r"TELEMETRY_SCENARIO_SEMANTIC_INDEX"),
            ("API semantic chain", r"tengu_api_query.{0,160}tengu_api_retry"),
            ("tool semantic chain", r"tengu_tool_use_show_permission_request"),
            ("compact semantic chain", r"tengu_reactive_compact_succeeded"),
            ("persistence semantic chain", r"tengu_transcript_writer_recovered"),
        ),
        "failure_markers": (
            ("export attempts", r"8 attempts"),
            ("backoff range", r"500 ms.{0,80}30 s"),
            ("401 auth fallback", r"401"),
            ("local failed batch", r"失败 batch|telemetry storage"),
            ("flush timeout", r"flush timeout 5 s"),
        ),
        "visual_anchors": (
            "业务调用点",
            "一方全局 sink",
            "一方 provider",
            "共享流量门与采样",
            "一方 batch exporter",
            "Datadog 分支",
            "管理员 OTEL 分支",
            "服务端或 collector",
        ),
        "minimum_lifecycle_steps": 11,
        "minimum_evidence_references": 8,
        "gate_scope": "document",
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"从事件产生到各出口的有序生命周期",
            "gates and thresholds": r"隐私、采样、批处理、失败和服务端边界",
            "failure and recovery": r"隐私、采样、批处理、失败和服务端边界",
            "user impact": r"Token、成本、延迟、隐私和副作用",
            "evidence": r"可读源码证据锚点",
            "boundary": r"最终边界",
        },
    },
    "api-beta-route-ownership": {
        "document": "analysis/api-beta-route-ownership.md",
        "visual_stem": "api-beta-route-ownership-lifecycle",
        "capabilities": (2,),
        "capability_markers_by_number": {
            2: (r"API", r"Beta", r"请求装配"),
        },
        "lifecycle_anchors": (
            ("caller selection", r"入口选择调用者"),
            ("host and identity", r"host 与身份分流"),
            ("path instantiation", r"路径实例化"),
            ("beta computation", r"Beta descriptor 计算"),
            ("provider rewrite", r"provider 过滤和改写"),
            ("receiver ownership", r"判定接收者"),
            ("request send or forward", r"发出或转发请求"),
            ("failure interpretation", r"解释失败"),
            ("remote boundary", r"远端 Boundary"),
        ),
        "gate_markers": (
            ("custom beta allowlist", r"自定义 Beta.{0,160}allowlist"),
            ("organization timeouts", r"5\s*s.{0,100}30\s*s"),
            ("remote trigger timeout", r"20\s*s"),
            ("fallback beta 400", r"fallback beta.{0,120}400|400.{0,120}fallback beta"),
            ("gateway in-flight cap", r"128"),
            ("gateway circuit breaker", r"5.{0,80}30\s*s"),
            ("runner body cap", r"1\s*MiB"),
        ),
        "failure_markers": (
            ("unsupported custom beta", r"自定义 beta 不在 allowlist"),
            ("beta strip retry", r"fallback beta.{0,120}400"),
            ("credential refresh", r"401.{0,80}刷新"),
            ("capacity retry", r"429/529/5xx"),
            ("abort uncertainty", r"abort/timeout.{0,160}未必"),
        ),
        "visual_anchors": (
            "静态候选",
            "客户端 consumer",
            "Host + Auth",
            "请求组装",
            "Provider 过滤/改写",
            "发布物内 handler",
            "本地恢复",
            "远端服务 Boundary",
        ),
        "minimum_lifecycle_steps": 9,
        "minimum_evidence_references": 8,
        "gate_scope": "document",
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"请求生命周期",
            "gates and thresholds": r"Gate、协议选择与精确阈值",
            "failure and recovery": r"失败、恢复与用户影响",
            "user impact": r"Token、延迟、成本、隐私与副作用",
            "evidence": r"证据与边界",
            "boundary": r"证据与边界",
        },
    },
    "error-diagnostic-atlas": {
        "document": "analysis/error-diagnostic-atlas.md",
        "visual_stem": "error-diagnostic-atlas-lifecycle",
        "capabilities": (11,),
        "capability_markers_by_number": {
            11: (r"Error", r"Diagnostic", r"错误", r"诊断"),
        },
        "lifecycle_anchors": (
            ("exception construction", r"触发点构造异常"),
            ("local cleanup", r"立即清理局部资源"),
            ("control-flow classification", r"判断是否属于控制流"),
            ("subsystem classification", r"按子系统分类"),
            ("local recovery", r"执行局部恢复"),
            ("user result", r"生成用户结果"),
            ("observation lanes", r"复制到观察面"),
            ("side-effect boundary", r"保留副作用边界"),
        ),
        "gate_markers": (
            ("single unsandboxed retry", r"unsandboxed retry.{0,120}一次"),
            ("LSP warning threshold", r"连续\s*3\s*次"),
            ("debug drain rounds", r"3\s*轮"),
            ("error ring cap", r"100\s*条"),
            ("debug rotation cap", r"10,485,760\s*bytes"),
            ("LSP attachment cap", r"4,000\s*字符"),
        ),
        "failure_markers": (
            ("sandbox retry owner", r"sandbox violation"),
            ("request retry owner", r"429/5xx/backoff"),
            ("LSP failure threshold", r"3 次"),
            ("debug drain", r"3 轮"),
            ("ring eviction", r"100 条"),
        ),
        "visual_anchors": (
            "触发点",
            "局部 cleanup",
            "语义分类",
            "局部恢复器",
            "产品结果",
            "本地 debug T()",
            "Hook / LSP diagnostics",
            "1P / OTEL / Datadog",
            "副作用 Boundary",
        ),
        "minimum_lifecycle_steps": 8,
        "minimum_evidence_references": 8,
        "gate_scope": "document",
        "evidence_scope": "document",
        "section_patterns": {
            "state ownership": r"60 秒看懂",
            "ordered lifecycle": r"生命周期：错误不是终点",
            "gates and thresholds": r"恢复预算与.*只试一次.*边界",
            "failure and recovery": r"恢复预算与.*只试一次.*边界",
            "user impact": r"Token、延迟、成本、隐私与副作用",
            "evidence": r"证据与边界",
            "boundary": r"证据与边界",
        },
    },
}
EVIDENCE_CLASSES = {"Static", "Probe", "Public", "Boundary"}
STATIC_EVIDENCE_KINDS = {
    "runtime",
    "constant",
    "consumer",
    "surface",
    "declaration",
}
MECHANISM_TOPIC_MINIMUMS = {
    "agent-loop": 8,
    "context-governance": 6,
    "sessions-memory": 6,
    "tools-permissions": 6,
    "tools-mcp": 5,
    "agents": 6,
    "resilience": 6,
    "models-auth-providers": 5,
    "settings-policy": 5,
    "feature-flags-remote-config": 8,
    "tui-ide-remote-cloud": 5,
    "install-update-doctor": 4,
    "native-bridge": 6,
    "telemetry": 8,
    "risk-controls": 1,
    "auto-mode-classifier": 3,
    "plugin-evaluation": 3,
    "runtime-supervision": 3,
    "enterprise-gateway": 3,
    "auth-account": 3,
    "onboarding-trust": 3,
    "thinking-effort-fast": 3,
    "usage-cost-limits": 3,
    "project-data-lifecycle": 3,
    "sandbox-runtime": 3,
    "network-proxy-mtls": 3,
    "active-goal": 3,
    "background-model-tasks": 3,
    "advisor": 3,
    "ultrareview": 3,
    "tool-registration-hosts": 6,
    "brief-output": 9,
    "plan-mode-approval": 6,
    "structured-output": 6,
    "claude-design-projects": 8,
    "repl-runtime": 6,
    "end-conversation": 6,
    "remote-ops": 6,
    "connector-catalog-mcp": 6,
    "artifact-watch": 3,
    "insights-pipeline": 3,
    "cli-startup-assets": 3,
    "complex-slash-commands": 3,
    "telemetry-event-catalog": 3,
    "api-beta-route-ownership": 3,
    "error-diagnostic-atlas": 3,
}
SOURCE_VIEW_PATHS = {
    "canonical-js": "extracted/cli.js",
    "readable-js": "reverse/javascript/cli.readable.js",
}


def topic_contract_capabilities(contract: dict) -> tuple[int, ...]:
    capabilities = contract.get("capabilities")
    if capabilities is not None:
        return tuple(capabilities)
    return (contract["capability"],)


def candidate_paths(repo: Path) -> list[str]:
    return sorted(
        set(
            git(repo, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
        )
    )


def find_private_capture_data(repo: Path) -> list[str]:
    failures: list[str] = []
    home = str(Path.home()).encode()
    workspace = str(repo).encode()
    for relative in candidate_paths(repo):
        if relative.startswith(("extracted/", "reverse/")):
            continue
        path = repo / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            continue
        reasons = []
        if home and home in data:
            reasons.append("capture home path")
        if workspace and workspace in data:
            reasons.append("capture workspace path")
        if PERSONAL_PATH_RE.search(data):
            reasons.append("concrete user-home path")
        if SECRET_RE.search(data):
            reasons.append("credential-shaped value")
        if reasons:
            failures.append(f"{relative} ({', '.join(sorted(set(reasons)))})")
    return failures


def validate_tool_registration_inventory(
    repo: Path,
    summary: dict,
    failures: list[str],
) -> None:
    counts = summary.get("counts", {})
    if counts.get("tool-registrations") != EXPECTED_TOOL_REGISTRATION_COUNT:
        failures.append(
            "tool registration inventory count mismatch: "
            f"expected={EXPECTED_TOOL_REGISTRATION_COUNT}, "
            f"actual={counts.get('tool-registrations')}"
        )

    coverage = summary.get("coverage", {}).get("toolRegistrations", {})
    expected_coverage = {
        "factorySymbol": EXPECTED_TOOL_FACTORY,
        "registrationCount": EXPECTED_TOOL_REGISTRATION_COUNT,
        "staticNameCount": EXPECTED_STATIC_TOOL_REGISTRATION_COUNT,
        "dynamicNameCount": EXPECTED_DYNAMIC_TOOL_REGISTRATION_COUNT,
    }
    for field, expected in expected_coverage.items():
        if coverage.get(field) != expected:
            failures.append(
                f"tool registration coverage {field} mismatch: "
                f"expected={expected!r}, actual={coverage.get(field)!r}"
            )

    discovered = summary.get("discoveredSymbols", {})
    if discovered.get("toolFactory") != EXPECTED_TOOL_FACTORY:
        failures.append(
            "tool registration factory discovery mismatch: "
            f"expected={EXPECTED_TOOL_FACTORY!r}, "
            f"actual={discovered.get('toolFactory')!r}"
        )
    if summary.get("completionAudit", {}).get("toolFactoryParsed") is not True:
        failures.append("source inventory completion audit failed: toolFactoryParsed")

    path = repo / "analysis/source-inventory/tool-registrations.jsonl"
    if not path.is_file():
        failures.append(
            "missing tool registration inventory: "
            "analysis/source-inventory/tool-registrations.jsonl"
        )
        return

    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    failures.append(
                        f"blank tool registration record: {path.relative_to(repo)}:{line_number}"
                    )
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    failures.append(
                        f"non-object tool registration record: "
                        f"{path.relative_to(repo)}:{line_number}"
                    )
                    continue
                rows.append(record)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        failures.append(f"invalid tool registration inventory: {error}")
        return

    if len(rows) != EXPECTED_TOOL_REGISTRATION_COUNT:
        failures.append(
            "tool registration row count mismatch: "
            f"expected={EXPECTED_TOOL_REGISTRATION_COUNT}, actual={len(rows)}"
        )

    comparison_keys = [row.get("comparisonKey") for row in rows]
    if any(not isinstance(key, str) or not key for key in comparison_keys):
        failures.append("tool registration inventory has missing comparisonKey values")
    elif len(set(comparison_keys)) != len(comparison_keys):
        failures.append("tool registration inventory has duplicate comparisonKey values")

    parsed_comparisons: dict[str, dict] = {}
    for line_number, row in enumerate(rows, 1):
        comparison_value = row.get("comparisonValue")
        if not isinstance(comparison_value, str):
            failures.append(
                "tool registration comparisonValue must be a JSON string: "
                f"{line_number}"
            )
            continue
        try:
            parsed_comparison = json.loads(comparison_value)
        except json.JSONDecodeError as error:
            failures.append(
                f"tool registration comparisonValue is invalid JSON: "
                f"{line_number}: {error}"
            )
            continue
        if not isinstance(parsed_comparison, dict):
            failures.append(
                "tool registration comparisonValue must decode to an object: "
                f"{line_number}"
            )
            continue
        normalized_comparison = json.dumps(
            parsed_comparison,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        if comparison_value != normalized_comparison:
            failures.append(
                "tool registration comparisonValue is not normalized: "
                f"{line_number}"
            )
        if parsed_comparison.get("aliases") != row.get("aliases"):
            failures.append(
                "tool registration comparison aliases mismatch: "
                f"{line_number}"
            )
        if isinstance(row.get("name"), str):
            if parsed_comparison.get("name") != row["name"]:
                failures.append(
                    "tool registration comparison name mismatch: "
                    f"{line_number}"
                )
        elif not isinstance(parsed_comparison.get("name"), dict):
            failures.append(
                "dynamic tool registration comparison name is not structured: "
                f"{line_number}"
            )
        comparison_key = row.get("comparisonKey")
        if isinstance(comparison_key, str):
            parsed_comparisons[comparison_key] = parsed_comparison

    factory_symbols = {row.get("factorySymbol") for row in rows}
    if factory_symbols != {EXPECTED_TOOL_FACTORY}:
        failures.append(
            "tool registration rows use unexpected factory symbols: "
            f"{sorted(repr(symbol) for symbol in factory_symbols)}"
        )

    static_rows = [row for row in rows if isinstance(row.get("name"), str)]
    dynamic_rows = [row for row in rows if row.get("name") is None]
    if len(static_rows) != EXPECTED_STATIC_TOOL_REGISTRATION_COUNT:
        failures.append(
            "static tool registration count mismatch: "
            f"expected={EXPECTED_STATIC_TOOL_REGISTRATION_COUNT}, "
            f"actual={len(static_rows)}"
        )
    if len(dynamic_rows) != EXPECTED_DYNAMIC_TOOL_REGISTRATION_COUNT:
        failures.append(
            "dynamic tool registration count mismatch: "
            f"expected={EXPECTED_DYNAMIC_TOOL_REGISTRATION_COUNT}, "
            f"actual={len(dynamic_rows)}"
        )

    static_names = [row["name"] for row in static_rows]
    missing_anchors = sorted(TOOL_FACTORY_ANCHORS - set(static_names))
    duplicate_anchors = sorted(
        name for name in TOOL_FACTORY_ANCHORS if static_names.count(name) > 1
    )
    if missing_anchors or duplicate_anchors:
        failures.append(
            "tool registration core anchor mismatch: "
            f"missing={missing_anchors}, non_unique={duplicate_anchors}"
        )

    brief_rows = [row for row in rows if row.get("name") == "SendUserMessage"]
    if len(brief_rows) != 1:
        failures.append(
            "tool registration SendUserMessage row count mismatch: "
            f"expected=1, actual={len(brief_rows)}"
        )
        return
    brief = brief_rows[0]
    if brief.get("aliases") != ["Brief"]:
        failures.append("tool registration SendUserMessage legacy alias mismatch")
    brief_comparison = parsed_comparisons.get(brief.get("comparisonKey", ""))
    if not isinstance(brief_comparison, dict) or (
        brief_comparison.get("name") != "SendUserMessage"
        or brief_comparison.get("aliases") != ["Brief"]
    ):
        failures.append("tool registration SendUserMessage comparison contract mismatch")
    if brief.get("declares", {}).get("briefStandalone") is not True:
        failures.append("tool registration SendUserMessage lost briefStandalone")
    required_properties = {
        "call",
        "description",
        "inputSchema",
        "isEnabled",
        "mapToolResultToToolResultBlockParam",
        "prompt",
    }
    properties = set(brief.get("properties", []))
    if not required_properties <= properties:
        failures.append(
            "tool registration SendUserMessage contract is incomplete: "
            f"missing={sorted(required_properties - properties)}"
        )


def validate_source_inventory(repo: Path, failures: list[str]) -> int:
    inventory = repo / "analysis/source-inventory"
    summary_path = inventory / "summary.json"
    extractor = (
        repo
        / "skill/claude-code-version-diff/scripts/extract_source_inventory.py"
    )
    if not summary_path.is_file():
        failures.append("missing analysis/source-inventory/summary.json")
        return 0
    if not extractor.is_file():
        failures.append("missing source inventory extractor")
        return 0
    parser_helper = extractor.with_name("parse_javascript_surface.mjs")
    acorn = extractor.parent.parent / "vendor/acorn/acorn.mjs"
    acorn_license = extractor.parent.parent / "vendor/acorn/LICENSE"
    for required in (parser_helper, acorn, acorn_license):
        if not required.is_file():
            failures.append(f"missing source inventory parser dependency: {required.name}")

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        failures.append(f"invalid source inventory summary: {error}")
        return 0

    if summary.get("formatVersion", 0) < 6:
        failures.append("source inventory formatVersion must be at least 6")
    parser = summary.get("javascriptParser", {})
    if parser.get("name") != "acorn" or parser.get("version") != "8.15.0":
        failures.append("source inventory must use vendored Acorn 8.15.0")
    source = repo / "extracted/cli.js"
    canonical = summary.get("canonicalSource", {})
    if canonical.get("path") != "extracted/cli.js":
        failures.append("source inventory canonical source path is incorrect")
    if canonical.get("size") != source.stat().st_size:
        failures.append("source inventory canonical source size is stale")
    if canonical.get("sha256") != sha256(source):
        failures.append("source inventory canonical source hash is stale")

    counts = summary.get("counts", {})
    for name, minimum in SOURCE_INVENTORY_MINIMUMS.items():
        value = counts.get(name)
        if not isinstance(value, int) or value < minimum:
            failures.append(
                f"source inventory {name!r} count is missing or below {minimum}"
            )
    validate_tool_registration_inventory(repo, summary, failures)

    completion = summary.get("completionAudit", {})
    for field in (
        "allTargetCallsitesRecorded",
        "allLexicalLiteralsRecorded",
        "dynamicExpressionsRetained",
        "rootSettingsKeysMatchStructuredRows",
        "modelCatalogParsed",
        "environmentSchemaParsed",
        "datadogSurfaceParsed",
        "claudeStorageFactoryParsed",
        "semanticSymbolsDiscovered",
    ):
        if completion.get(field) is not True:
            failures.append(f"source inventory completion audit failed: {field}")
    if completion.get("knownStaticExtractionGaps") != []:
        failures.append("source inventory reports known static extraction gaps")

    storage_coverage = summary.get("coverage", {}).get("claudeStorage", {})
    if storage_coverage.get("namespaceCount") != counts.get(
        "claude-storage-namespaces"
    ):
        failures.append("Claude storage coverage count does not match inventory count")
    if storage_coverage.get("requiredStreamNamespaces") != [
        "history",
        "log",
        "transcript",
    ]:
        failures.append("Claude storage coverage is missing required stream namespaces")

    discovered = summary.get("discoveredSymbols", {})
    roles = discovered.get("roles", {}) if isinstance(discovered, dict) else {}
    required_roles = {
        "firstPartyEvent",
        "firstPartyEventAsync",
        "otelStructuredEvent",
        "featureValue",
        "dynamicConfig",
        "diagnostic",
    }
    if set(roles) != required_roles or not all(
        isinstance(value, str) and value for value in roles.values()
    ):
        failures.append("source inventory semantic role discovery is incomplete")
    elif len(set(roles.values())) != len(roles):
        failures.append("source inventory semantic role symbols are not unique")
    for field in (
        "environmentProxy",
        "environmentBuilder",
        "rootSettingsFunction",
        "objectBuilder",
        "enumBuilder",
        "literalBuilder",
        "modelCatalog",
        "datadogAllowlist",
        "datadogTagFields",
        "datadogRedactedFields",
        "datadogRedactedSet",
        "userConfigDirectoriesVariable",
    ):
        if not isinstance(discovered.get(field), str) or not discovered[field]:
            failures.append(f"source inventory discovered symbol missing: {field}")

    target_coverage = summary.get("coverage", {}).get("targetCallsites", {})
    expected_target_files = {
        "firstPartyEvent": "first-party-event-callsites",
        "firstPartyEventAsync": "first-party-event-callsites",
        "otelStructuredEvent": "otel-event-callsites",
        "featureValue": "feature-flag-callsites",
        "dynamicConfig": "growthbook-callsites",
    }
    for role, inventory_name in expected_target_files.items():
        coverage = target_coverage.get(role, {})
        total = coverage.get("total")
        if not isinstance(total, int) or total < 1:
            failures.append(f"source inventory callsite coverage missing for {role}")
        if coverage.get("symbol") != roles.get(role):
            failures.append(f"source inventory callsite symbol mismatch for {role}")
    first_party_total = sum(
        target_coverage.get(role, {}).get("total", 0)
        for role in ("firstPartyEvent", "firstPartyEventAsync")
    )
    if first_party_total != counts.get("first-party-event-callsites"):
        failures.append("first-party callsite coverage does not match JSONL count")
    for role in ("otelStructuredEvent", "featureValue", "dynamicConfig"):
        if target_coverage.get(role, {}).get("total") != counts.get(
            expected_target_files[role]
        ):
            failures.append(f"{role} callsite coverage does not match JSONL count")

    entries = summary.get("files", [])
    expected_names: set[str] = set()
    for entry in entries:
        relative = entry.get("path", "")
        path = repo / relative
        if not relative.startswith("analysis/source-inventory/"):
            failures.append(f"invalid source inventory path: {relative!r}")
            continue
        expected_names.add(Path(relative).name)
        if not path.is_file():
            failures.append(f"missing source inventory file: {relative}")
            continue
        actual_lines = sum(1 for _ in path.open("r", encoding="utf-8"))
        if entry.get("lines") != actual_lines:
            failures.append(f"source inventory line count mismatch: {relative}")
        if entry.get("size") != path.stat().st_size:
            failures.append(f"source inventory size mismatch: {relative}")
        if entry.get("sha256") != sha256(path):
            failures.append(f"source inventory hash mismatch: {relative}")
        if path.suffix == ".jsonl":
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, 1):
                        if not line.strip():
                            failures.append(
                                f"blank JSONL record: {relative}:{line_number}"
                            )
                            continue
                        record = json.loads(line)
                        if not isinstance(record, dict):
                            failures.append(
                                f"non-object JSONL record: {relative}:{line_number}"
                            )
                            continue
                        if not isinstance(
                            record.get("comparisonKey"), str
                        ) or not isinstance(record.get("comparisonValue"), str):
                            failures.append(
                                f"missing comparison fields: {relative}:{line_number}"
                            )
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                failures.append(f"invalid JSONL inventory {relative}: {error}")

    committed_names = {
        path.name
        for path in inventory.iterdir()
        if path.is_file() and path.name != "summary.json"
    }
    if committed_names != expected_names:
        failures.append(
            "source inventory file set differs from summary: "
            f"extra={sorted(committed_names - expected_names)}, "
            f"missing={sorted(expected_names - committed_names)}"
        )

    with tempfile.TemporaryDirectory(prefix="claude-source-inventory-") as temporary:
        process = subprocess.run(
            [sys.executable, str(extractor), str(repo), "--output", temporary],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if process.returncode != 0:
            failures.append(
                "source inventory regeneration failed: " + process.stdout.strip()
            )
        else:
            generated = Path(temporary)
            generated_names = {path.name for path in generated.iterdir() if path.is_file()}
            committed_all = committed_names | {"summary.json"}
            if generated_names != committed_all:
                failures.append(
                    "regenerated source inventory file set differs: "
                    f"extra={sorted(generated_names - committed_all)}, "
                    f"missing={sorted(committed_all - generated_names)}"
                )
            for name in sorted(generated_names & committed_all):
                if (generated / name).read_bytes() != (inventory / name).read_bytes():
                    failures.append(f"stale or edited source inventory artifact: {name}")

    return len(entries)


DOT_EDGE_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*->\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*?)\]\s*;",
    re.MULTILINE | re.DOTALL,
)
DOT_LABEL_RE = re.compile(r'\blabel\s*=\s*"((?:\\.|[^"\\])*)"')


def dot_edges(dot_text: str) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    for source, target, attributes in DOT_EDGE_RE.findall(dot_text):
        label_match = DOT_LABEL_RE.search(attributes)
        if label_match is None:
            continue
        label = label_match.group(1).replace(r"\n", "\n").replace(r'\"', '"')
        edges.append((source, target, label))
    return edges


def require_dot_edge(
    dot_text: str,
    *,
    source: str,
    target: str,
    label_terms: tuple[str, ...],
    visual_name: str,
    failures: list[str],
) -> None:
    for edge_source, edge_target, label in dot_edges(dot_text):
        if (
            edge_source == source
            and edge_target == target
            and all(term in label for term in label_terms)
        ):
            return
    failures.append(
        f"{visual_name} is missing edge {source} -> {target} "
        f"with label terms {label_terms!r}"
    )


def validate_dot_svg_regeneration(
    dot_path: Path,
    svg_path: Path,
    visual_name: str,
    failures: list[str],
) -> None:
    with tempfile.TemporaryDirectory(prefix="claude-dot-render-") as temporary:
        regenerated = Path(temporary) / svg_path.name
        try:
            process = subprocess.run(
                ["dot", "-Tsvg", str(dot_path), "-o", str(regenerated)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as error:
            failures.append(
                f"{visual_name} DOT regeneration could not start: {error}"
            )
            return
        if process.returncode != 0:
            failures.append(
                f"{visual_name} DOT regeneration failed: {process.stdout.strip()}"
            )
            return
        if regenerated.read_bytes() != svg_path.read_bytes():
            failures.append(
                f"{visual_name} rendered SVG differs from DOT regeneration"
            )


def validate_product_surface_map(repo: Path, failures: list[str]) -> None:
    relative = "analysis/product-surface-evidence-map.md"
    path = repo / relative
    generator = repo / "skill/claude-code-version-diff/scripts/build_product_surface_map.py"
    if not path.is_file():
        failures.append(f"missing product surface evidence map: {relative}")
        return
    if not generator.is_file():
        failures.append("missing product surface evidence map generator")
        return

    summary = json.loads(
        (repo / "analysis/source-inventory/summary.json").read_text(encoding="utf-8")
    )
    expected = [Path(entry["path"]).name for entry in summary.get("files", [])]
    content = path.read_text(encoding="utf-8")
    if len(expected) != EXPECTED_SOURCE_INVENTORY_COUNT:
        failures.append(
            "product surface source inventory count mismatch: "
            f"expected={EXPECTED_SOURCE_INVENTORY_COUNT}, actual={len(expected)}"
        )
    if "tool-registrations.jsonl" not in expected:
        failures.append("product surface source inventory is missing tool-registrations.jsonl")
    expected_marker = f"全部 {EXPECTED_SOURCE_INVENTORY_COUNT} 类机器清单"
    if expected_marker not in content:
        failures.append(
            f"product surface evidence map is missing {expected_marker} coverage marker"
        )
    block = text_between(
        content,
        "<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->",
        "<!-- SOURCE_INVENTORY_COVERAGE_END -->",
    )
    rows = re.findall(
        r"^\| \[`([^`]+)`\]\(source-inventory/([^)]+)\) \| `([^`]+)` \| "
        r"`([^`]+)` \| `([^`]+)` \| `([^`]+)` \| ([^|]+) \|$",
        block,
        re.MULTILINE,
    )
    actual = [row[0] for row in rows]
    if actual != expected or any(label != target for label, target, *_ in rows):
        failures.append(
            "product surface inventory coverage mismatch: "
            f"expected={len(expected)}, actual={len(actual)}, "
            f"ordered={actual == expected}"
        )
    allowed_origins = {
        "Structured extraction",
        "Targeted AST",
        "Broad static scan",
        "Heuristic scan",
        "Dependency schema",
        "Lexical/AST substrate",
        "Derived projection",
        "Manual intersection",
        "Require literal scan",
        "Whole-bundle AST",
        "Prefix-filtered environment union",
        "Template-prefix projection",
        "Manual allowlist intersection",
        "process.env text projection",
        "Env-proxy projection",
        "Prefix bucket projection",
        "URL keyword projection",
        "Environment-builder extraction",
        "Observability-filtered environment callsites",
        "Observability regex projection",
    }
    allowed_ownership = {"Product", "Dependency", "Mixed", "Unresolved"}
    allowed_proof = {
        "Candidate",
        "Declaration",
        "Callsite",
        "Structured surface",
        "Evidence substrate",
    }
    allowed_routes = {"C", "Q", "E", "S", "O"}
    for label, _, origin, ownership, proof, routes, limitation in rows:
        if origin not in allowed_origins:
            failures.append(f"product surface inventory {label} has invalid extraction origin")
        if ownership not in allowed_ownership:
            failures.append(f"product surface inventory {label} has invalid ownership")
        if proof not in allowed_proof:
            failures.append(f"product surface inventory {label} has invalid proof level")
        route_ids = routes.split("/")
        if not route_ids or any(route not in allowed_routes for route in route_ids):
            failures.append(f"product surface inventory {label} has invalid mechanism routes")
        if not limitation.strip():
            failures.append(f"product surface inventory {label} has no evidence limitation")

    expected_axes = {
        "api-path-templates.jsonl": ("Template-prefix projection", "Mixed", "Candidate"),
        "builtin-tool-identifiers.txt": ("Manual allowlist intersection", "Mixed", "Candidate"),
        "direct-process-environment-accesses.txt": ("process.env text projection", "Mixed", "Candidate"),
        "dynamic-process-environment-callsites.jsonl": ("Whole-bundle AST", "Mixed", "Callsite"),
        "environment-access-callsites.jsonl": ("Whole-bundle AST", "Mixed", "Callsite"),
        "environment-proxy-accesses.txt": ("Env-proxy projection", "Mixed", "Candidate"),
        "environment-schema.jsonl": ("Environment-builder extraction", "Mixed", "Declaration"),
        "first-party-event-families.tsv": ("Prefix bucket projection", "Mixed", "Candidate"),
        "observability-environment-defaults.jsonl": (
            "Observability-filtered environment callsites",
            "Mixed",
            "Callsite",
        ),
        "observability-environment-schema.jsonl": (
            "Observability regex projection",
            "Mixed",
            "Declaration",
        ),
        "otel-environment-variables.txt": ("Prefix-filtered environment union", "Mixed", "Candidate"),
        "runtime-requires.txt": ("Require literal scan", "Mixed", "Callsite"),
        "static-string-literals.jsonl": ("Lexical/AST substrate", "Unresolved", "Evidence substrate"),
        "telemetry-endpoints.txt": ("URL keyword projection", "Mixed", "Candidate"),
        "third-party-otel-events.txt": ("Dependency schema", "Dependency", "Declaration"),
        "tool-registrations.jsonl": ("Structured extraction", "Product", "Structured surface"),
    }
    actual_axes = {row[0]: row[2:5] for row in rows}
    for label, axes in expected_axes.items():
        if actual_axes.get(label) != axes:
            failures.append(
                f"product surface inventory {label} must use axes "
                f"origin={axes[0]}, ownership={axes[1]}, proof={axes[2]}"
            )

    for label in (
        "dynamic-process-environment-callsites.jsonl",
        "environment-access-callsites.jsonl",
        "environment-schema.jsonl",
        "observability-environment-defaults.jsonl",
        "observability-environment-schema.jsonl",
        "otel-environment-variables.txt",
    ):
        axes = actual_axes.get(label)
        if axes is None or axes[1] != "Mixed":
            failures.append(
                f"product surface environment inventory {label} ownership must be Mixed"
            )

    appendix_start = content.find("<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->")
    narrative_markers = (
        "## 关键不是流程很长，而是四个嵌套生命周期单位各算各的账",
        "## 矛盾一：让模型自主，但不把执行权交给模型",
        "## 矛盾二：既要忘掉大部分历史，又要让任务继续成立",
        "## 矛盾三：既要看见系统，又不能把观测误当成事实",
        "## 矛盾四：想恢复任务，但系统没有一台时间机器",
        "## 压力测试五：Artifact 超时后",
        "## 矛盾六：要调用本机原生能力，又不能把 ABI 当成原始源码",
        "## 六个压力测试共同暴露出的技术性格",
        "## 最后再用 C/Q/E/S/O 作为阅读路由",
        "<summary><strong>证据方法附录",
        "## 判断一条清单能否支持技术结论",
        "## 三轴证据坐标",
    )
    for marker in narrative_markers:
        position = content.find(marker)
        if position < 0 or position >= appendix_start:
            failures.append(
                f"product surface reader-first narrative must place {marker!r} before appendix"
            )
    inventory_details_open = content.rfind("<details>", 0, appendix_start)
    inventory_details_close = content.find("</details>", appendix_start)
    if not (
        0 <= inventory_details_open < appendix_start < inventory_details_close
    ):
        failures.append("product surface inventory appendix must be collapsed with details")

    required_case_anchors = (
        "tool-registrations.jsonl#L80",
        "cli.readable.js#L393203",
        "api-paths.txt#L17",
        "runtime-requires.txt#L1",
        "cli.readable.js#L54",
        "cli.readable.js#L271491",
        "cli.readable.js#L271553",
        "cli.readable.js#L270840",
        "cli.readable.js#L272032",
        "cli.readable.js#L409843",
        "cli.readable.js#L267124",
        "cli.readable.js#L316220",
        "cli.readable.js#L331309",
        "cli.readable.js#L262996",
        "cli.readable.js#L261931",
        "cli.readable.js#L216096",
        "cli.readable.js#L260784",
        "cli.readable.js#L261085",
        "cli.readable.js#L362451",
        "cli.readable.js#L362559",
        "cli.readable.js#L90870",
        "cli.readable.js#L90790",
        "cli.readable.js#L77977",
        "cli.readable.js#L77550",
        "cli.readable.js#L361612",
        "cli.readable.js#L93779",
        "cli.readable.js#L323373",
        "cli.readable.js#L403569",
        "cli.readable.js#L402489",
        "cli.readable.js#L402554",
        "cli.readable.js#L194641",
    )
    for anchor in required_case_anchors:
        if anchor not in content:
            failures.append(f"product surface reader-first case is missing source anchor {anchor}")
    for lane in ("C", "Q", "E", "S", "O"):
        if f"| `{lane}` |" not in content:
            failures.append(f"product surface runtime plane {lane} is missing")

    narrative = content[:appendix_start] if appendix_start >= 0 else content
    if not all(
        marker in content[:5000]
        for marker in (
            "模型负责提议，客户端负责裁决与记账",
            "三个不等价的世界",
            "模型世界",
            "客户端世界",
            "外部世界",
            "历史表示可以重建，外部世界不能假装回滚",
        )
    ):
        failures.append(
            "product surface opening must teach proposal authority, client causal state, "
            "and irreversible external effects before introducing inventories"
        )
    if "## 这个版本最鲜明的七个技术特征" in narrative:
        failures.append(
            "product surface must derive technical characteristics after the mechanism "
            "pressure tests instead of front-loading a repetitive feature table"
        )
    evidence_details = content.find(
        "<summary><strong>证据方法附录：怎样从一个字符串走到可复核的技术结论"
    )
    evidence_method = content.find("## 读代码时最容易犯的十个归因错误")
    evidence_close = content.find("</details>", evidence_method)
    completeness_heading = content.find("## 当前到底全面到哪里")
    if not (
        0 <= evidence_details < evidence_method < evidence_close < completeness_heading < appendix_start
    ):
        failures.append(
            "product surface evidence methodology must be collapsed after the reader "
            "navigation and before the explicit completeness debt"
        )
    authority_visual = re.search(
        r"!\[([^\]]+)\]\(visuals/runtime-authority-lifecycle\.svg\)",
        content[:3000],
    )
    if not (
        authority_visual
        and all(
            marker in authority_visual.group(1)
            for marker in ("模型", "本地管线", "因果", "真实副作用", "外部 owner")
        )
    ):
        failures.append(
            "product surface first screen must visualize model proposals, local authority, "
            "the causal ledger, and external effects"
        )
    agent_loop_visual = re.search(
        r"!\[([^\]]+)\]\(visuals/agent-loop-lifecycle\.svg\)",
        content[:8000],
    )
    if not (
        agent_loop_visual
        and all(
            marker in agent_loop_visual.group(1)
            for marker in (
                "用户任务",
                "模型迭代",
                "API attempt",
                "工具批次",
                "结果回灌",
            )
        )
    ):
        failures.append(
            "product surface Agent Loop visual must expose user task, model iteration, "
            "API attempt, tool batch, and result-feedback semantics"
        )
    five_plane_section = markdown_h2_section(
        content, r"最后再用 C/Q/E/S/O 作为阅读路由"
    ) or ""
    if not (
        "Derived 阅读模型" in content[:2000]
        and "Derived" in five_plane_section
        and "分析框架" in five_plane_section
        and re.search(
            r"(?:不是|并非).{0,100}(?:源码|bundle).{0,100}(?:模块|架构)",
            content[:2500],
            re.DOTALL,
        )
        and re.search(
            r"(?:不是|并非).{0,100}(?:Anthropic\s*)?官方.{0,80}(?:架构|命名|术语)",
            content[:2500],
            re.DOTALL,
        )
    ):
        failures.append(
            "product surface five-plane model must be labeled as a Derived reading model, "
            "not source-native modules or an Anthropic official architecture"
        )

    state_plane_row = next(
        (line for line in five_plane_section.splitlines() if line.startswith("| `S` |")),
        "",
    )
    if not (
        all(
            term in state_plane_row
            for term in (
                "本地状态面",
                "checkpoint",
                "remote ID/reference",
                "补偿线索",
                "不拥有真实文件",
                "远端对象",
            )
        )
        and "文件和远端对象" not in state_plane_row
    ):
        failures.append(
            "product surface state plane must own local records, checkpoints, remote "
            "references, and compensation clues rather than real files or remote objects"
        )

    tool_kind_section = markdown_h2_section(
        content, r"矛盾一：让模型自主，但不把执行权交给模型"
    ) or ""
    client_tool_row = next(
        (
            line
            for line in tool_kind_section.splitlines()
            if line.startswith("| client `tool_use` |")
        ),
        "",
    )
    server_tool_row = next(
        (
            line
            for line in tool_kind_section.splitlines()
            if line.startswith("| `server_tool_use` |")
        ),
        "",
    )
    if not (
        client_tool_row
        and server_tool_row
        and all(
            term in tool_kind_section
            for term in ("registry", "permission", "sandbox", "tool.call")
        )
        and "**是**" in client_tool_row
        and "**否**" in server_tool_row
        and "不会本地 dispatch" in server_tool_row
        and "本地 Agent Loop 只接管 client `tool_use`" in tool_kind_section
    ):
        failures.append(
            "product surface execution semantics must distinguish client tool_use from "
            "server_tool_use and keep server tools out of the local execution pipeline"
        )

    loop_units_section = markdown_h2_section(
        content, r"关键不是流程很长，而是四个嵌套生命周期单位各算各的账"
    ) or ""
    if not (
        all(
            marker in loop_units_section
            for marker in (
                "| 用户 turn |",
                "| 模型 iteration |",
                "| API attempt |",
                "| Tool batch |",
                "maxTurns=1",
                "error_max_turns",
            )
        )
        and "retry 可以重发请求，但不一定增加 `turnCount`" in loop_units_section
    ):
        failures.append(
            "product surface Agent Loop accounting must distinguish user turn, model "
            "iteration, API attempt, and tool batch"
        )

    bash_section = markdown_h2_section(
        content, r"矛盾一：让模型自主，但不把执行权交给模型"
    ) or ""
    bash_classification = re.search(
        r"isConcurrencySafe.{0,260}(?:最初|原始|original).{0,40}input",
        bash_section,
        re.IGNORECASE | re.DOTALL,
    )
    bash_rewrite = re.search(
        r"(?:PreToolUse|Hook).{0,180}permission.{0,220}(?:改写|rewrite)",
        bash_section,
        re.IGNORECASE | re.DOTALL,
    )
    bash_no_recompute = re.search(
        r"(?:不|不会|并不).{0,40}(?:重算|重新计算|recompute)",
        bash_section,
        re.IGNORECASE | re.DOTALL,
    )
    if not (
        bash_classification
        and bash_rewrite
        and bash_no_recompute
        and "改写后不会重新计算 `isConcurrencySafe`" in bash_section
        and "改写后会重新计算 `isConcurrencySafe`" not in bash_section
    ):
        failures.append(
            "product surface Bash semantics must classify concurrency on the original input "
            "before Hook/permission rewrites and must not recompute it"
        )
    if not all(
        marker in bash_section
        for marker in (
            "发现状态",
            "请求可见状态",
            "执行授权状态",
            "bypassPermissions",
            "Shift+Tab",
            "Down+Enter",
            "acceptEdits",
            "关闭输入框",
            "批准这一次",
            "本会话批准同类 Edit",
        )
    ):
        failures.append(
            "product surface tool authority must separate discovery, request visibility, "
            "execution authorization, sandbox enforcement, and TUI permission scope"
        )

    compact_section = markdown_h2_section(
        content, r"矛盾二：既要忘掉大部分历史，又要让任务继续成立"
    ) or ""
    compact_hit = compact_section.lower().find("+-- hit")
    compact_miss = compact_section.lower().find("+-- miss")
    hit_window = (
        compact_section[compact_hit : compact_hit + 900]
        if compact_hit >= 0
        else ""
    )
    miss_window = (
        compact_section[compact_miss : compact_miss + 900]
        if compact_miss >= 0
        else ""
    )
    hit_skips_request = re.search(
        r"(?:不发送|不会发送|不发起|不会发起|无需|跳过).{0,100}"
        r"(?:summary\s*request|summary\s*请求|总结请求)",
        hit_window,
        re.IGNORECASE | re.DOTALL,
    )
    miss_requests_summary = (
        re.search(r"(?:message\s*groups?|分组)", miss_window, re.IGNORECASE)
        and re.search(
            r"(?:summary\s*request|summary\s*请求|总结请求)",
            miss_window,
            re.IGNORECASE,
        )
    )
    if not (
        compact_hit >= 0
        and "smi finalize" in hit_window.lower()
        and hit_skips_request
        and compact_miss >= 0
        and miss_requests_summary
        and "| `/compact` | 请求 + 状态平面 | 生成 summary" not in narrative
    ):
        failures.append(
            "product surface compact semantics must separate precomputed hit/finalize without "
            "a summary request from miss/grouping/summary request"
        )
    compact_teaching_markers = (
        "CRITICAL",
        "禁止调用工具",
        "<analysis>",
        "<summary>",
        "固定九段",
        "客户端随后丢弃前者",
        "| Summary |",
        "| Preserved message groups |",
        "| Attachments / hooks |",
        "| compact boundary |",
        "defer_loading:true",
        "| Context hint |",
        "| Local microcompaction |",
        "144k 预计算",
        "147k 警告",
        "167k compact",
        "177k 阻塞",
    )
    if not all(marker in compact_section for marker in compact_teaching_markers):
        failures.append(
            "product surface compact explanation must teach the ordinary miss prompt, "
            "four rebuilt-context channels, Tool Search visibility, separate context-hint "
            "and microcompaction paths, and the four window lines"
        )
    if "Context hint / microcompaction" in compact_section:
        failures.append(
            "product surface must not collapse the server context-hint protocol and local "
            "microcompaction action into one mechanism"
        )

    artifact_section = markdown_h2_section(
        content, r"压力测试五：Artifact 超时后"
    ) or ""
    artifact_schema = re.search(
        r"(?:response|响应)\s*schema", artifact_section, re.IGNORECASE
    )
    artifact_slug = re.search(
        r"(?:目标|target).{0,60}`?slug`?.{0,100}(?:相等|一致|equality)",
        artifact_section,
        re.IGNORECASE | re.DOTALL,
    )
    artifact_server_version = re.search(
        r"(?:服务端|server).{0,60}`?version`?.{0,100}"
        r"(?:采用|接受|接纳|adopt)",
        artifact_section,
        re.IGNORECASE | re.DOTALL,
    )
    artifact_no_local_equality = re.search(
        r"(?:不|不会|并非).{0,80}(?:本地|local).{0,60}`?version`?.{0,120}"
        r"(?:相等|一致|equality)",
        artifact_section,
        re.IGNORECASE | re.DOTALL,
    )
    artifact_advisory = (
        "advisory" in artifact_section.lower()
        and re.search(r"(?:artifact\s*)?list|列表", artifact_section, re.IGNORECASE)
        and re.search(
            r"(?:不是|并非|不会).{0,120}(?:自动|强制).{0,80}(?:查询|调用|list)",
            artifact_section,
            re.IGNORECASE | re.DOTALL,
        )
    )
    artifact_overclaims = (
        "校验服务端回显的 slug/version" in artifact_section
        or "客户端要求先查 artifact list" in artifact_section
    )
    if not (
        artifact_schema
        and artifact_slug
        and artifact_server_version
        and artifact_no_local_equality
        and artifact_advisory
        and not artifact_overclaims
    ):
        failures.append(
            "product surface Artifact semantics must separate response-schema and target-slug "
            "validation, server-version acceptance, and list advisory from automatic enforcement"
        )

    voice_section = markdown_h2_section(
        content, r"矛盾六：要调用本机原生能力，又不能把 ABI 当成原始源码"
    ) or ""
    voice_wrapper = re.search(
        r"(?:JavaScript|JS)(?:\s+native)?\s*wrapper.{0,180}"
        r"(?:透传|传递|pass|原样上抛).{0,80}bytes|"
        r"(?:JavaScript|JS)(?:\s+native)?\s*wrapper.{0,180}bytes.{0,80}"
        r"(?:透传|传递|pass|原样上抛)",
        voice_section,
        re.IGNORECASE | re.DOTALL,
    )
    voice_sox = all(
        term in voice_section
        for term in ("SoX fallback", "-r 16000", "-e signed", "-b 16", "-c 1")
    )
    voice_compatible = re.search(
        r"(?:重建版\s*native.{0,260}Compatible|"
        r"Compatible.{0,260}(?:native|重建|重采样|16\s*k))",
        voice_section,
        re.IGNORECASE | re.DOTALL,
    )
    voice_original_limit = (
        "原版 native 内部 16 kHz/mono/s16 重采样细节" in voice_section
        and "Boundary / 未恢复" in voice_section
        and "不能直接推出" in voice_section
    )
    if not (
        all(term in voice_section for term in ("Observed", "Derived", "Compatible"))
        and voice_wrapper
        and voice_sox
        and voice_compatible
        and voice_original_limit
        and "native CPAL/CoreAudio 线程产生 16kHz" not in voice_section
    ):
        failures.append(
            "product surface Voice semantics must separate Observed wrapper/SoX evidence, "
            "Derived behavior, and Compatible native reconstruction"
        )
    if not all(
        marker in voice_section
        for marker in (
            "真实麦克风和 Voice service 的端到端 Probe",
            "5 个 native 模块",
            "23 项报告",
            "x86_64 尚未实跑",
            "不是找回 Anthropic 的 C/C++/Rust/Swift 原函数体",
        )
    ):
        failures.append(
            "product surface native explanation must state the end-to-end Voice, architecture, "
            "and original-source reconstruction boundaries"
        )

    telemetry_section = markdown_h2_section(
        content, r"矛盾三：既要看见系统，又不能把观测误当成事实"
    ) or ""
    if not (
        all(
            marker in telemetry_section
            for marker in (
                "| 一方事件 |",
                "| Datadog forwarding |",
                "| 第三方 OTEL |",
                "| 本地诊断 |",
                "CLAUDE_CODE_ENABLE_TELEMETRY",
                "OTEL_LOG_USER_PROMPTS",
                "<REDACTED>",
                "session_id",
                "queryChainId",
                "queryDepth",
                "request_id",
                "tool_use_id",
                "turn_count",
                "terminal_reason",
                "关闭其中一条，不代表其他通道同时关闭",
                "不是系统事实的唯一账本",
                "不是 retry/compact/supervisor 的控制器",
                "best-effort",
            )
        )
        and "共享点" in telemetry_section
        and "不是两条管道等价" in telemetry_section
    ):
        failures.append(
            "product surface telemetry semantics must distinguish first-party, Datadog, "
            "OTEL, and local diagnostic pipelines from recovery control"
        )
    if not all(
        marker in telemetry_section
        for marker in (
            "OTEL_LOG_RAW_API_BODIES",
            "设置为 `1`",
            "file:<dir>",
            "body_ref",
            "本地明文文件",
            "即使 `OTEL_LOG_USER_PROMPTS` 没开",
        )
    ):
        failures.append(
            "product surface telemetry privacy explanation must cover disabled, inline, and "
            "file raw-body modes independently from prompt redaction"
        )

    recovery_section = markdown_h2_section(
        content, r"矛盾四：想恢复任务，但系统没有一台时间机器"
    ) or ""
    if not (
        all(
            marker in recovery_section
            for marker in (
                "| Message graph |",
                "| Compact boundary |",
                "| File checkpoint |",
                "| Remote reference / result |",
                "不会重新执行历史工具",
                "不恢复旧 socket/Promise",
                "reference 也不是分布式事务句柄",
                "消息图续消息",
                "checkpoint 续文件",
                "各子系统的 remote reference",
                "补偿线索",
            )
        )
    ):
        failures.append(
            "product surface recovery semantics must separate message graph, compact "
            "boundary, file checkpoint, and remote-reference recovery objects"
        )

    synthesis_section = markdown_h2_section(
        content, r"六个压力测试共同暴露出的技术性格"
    ) or ""
    if not all(
        marker in synthesis_section
        for marker in (
            "第一，能力晚绑定",
            "第二，权力不对称",
            "第三，事实与表示分离",
            "第四，恢复按对象负责",
            "第五，可观测性有意保持从属",
            "复杂度没有消失",
            "真正拥有状态的组件",
        )
    ):
        failures.append(
            "product surface must derive the version's technical character from the six "
            "mechanism pressure tests instead of ending with disconnected case summaries"
        )

    evidence_records = [
        json.loads(line)
        for line in (repo / "analysis/mechanism-evidence.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    evidence_counts = Counter(
        record.get("evidenceClass") for record in evidence_records
    )
    expected_evidence_summary = (
        f"结构化机制注册表当前有 {len(evidence_records)} 条 claim，覆盖 "
        f"{len({record['topic'] for record in evidence_records})} 个 topic："
        f"{evidence_counts['Static']} Static、{evidence_counts['Probe']} Probe、"
        f"{evidence_counts['Public']} Public、{evidence_counts['Boundary']} Boundary"
    )
    if expected_evidence_summary not in content:
        failures.append(
            "product surface completeness statement does not match the mechanism evidence registry"
        )
    for debt in (
        "654 个静态环境名称",
        "211 个 Feature key",
        "85 个仍含运行参数的动态环境表达式",
        "911 个 `tengu_other`",
        "x86_64 native",
    ):
        if debt not in content:
            failures.append(
                f"product surface completeness debt is missing {debt!r}"
            )

    if (
        "71/71 精确归属" in content
        or "机器附录：71 类机器清单的证据分类与阅读路由" not in content
    ):
        failures.append(
            "product surface inventory appendix must say 71 classes are classified, "
            "not claim 71/71 exact ownership"
        )

    authority_dot = repo / "analysis/visuals/runtime-authority-lifecycle.dot"
    authority_svg = repo / "analysis/visuals/runtime-authority-lifecycle.svg"
    if not authority_dot.is_file() or not authority_svg.is_file():
        failures.append("product surface runtime-authority DOT/SVG is missing")
    else:
        dot_text = authority_dot.read_text(encoding="utf-8")
        for source, target, label_terms in (
            ("request", "assemble", ("user turn",)),
            ("assemble", "model", ("API attempt",)),
            ("model", "gate", ("client tool_use",)),
            ("gate", "effects", ("批准后", "真实动作")),
            ("effects", "ledger", ("不可逆事实",)),
            ("ledger", "assemble", ("下一轮", "有效视图")),
        ):
            require_dot_edge(
                dot_text,
                source=source,
                target=target,
                label_terms=label_terms,
                visual_name="product surface runtime-authority visual",
                failures=failures,
            )
        outbound_observe = [
            (source, target, label)
            for source, target, label in dot_edges(dot_text)
            if source == "observe"
        ]
        if outbound_observe:
            failures.append(
                "product surface runtime-authority visual must keep observability inbound-only"
            )
        validate_dot_svg_regeneration(
            authority_dot,
            authority_svg,
            "product surface runtime-authority visual",
            failures,
        )

    evidence_dot = repo / "analysis/visuals/evidence-surface-lifecycle.dot"
    evidence_svg = repo / "analysis/visuals/evidence-surface-lifecycle.svg"
    if not evidence_dot.is_file() or not evidence_svg.is_file():
        failures.append("product surface evidence lifecycle DOT/SVG is missing")
    else:
        dot_text = evidence_dot.read_text(encoding="utf-8")
        for source, target, label_terms in (
            ("candidate", "untraced", ("先登记待追",)),
            ("untraced", "mechanism", ("caller", "gate", "state")),
            (
                "candidate",
                "boundary",
                ("server/runtime/build-time unavailable",),
            ),
        ):
            require_dot_edge(
                dot_text,
                source=source,
                target=target,
                label_terms=label_terms,
                visual_name="product surface evidence lifecycle",
                failures=failures,
            )
        if "证据不足时降级" in dot_text:
            failures.append(
                "product surface evidence lifecycle incorrectly maps incomplete tracing to Boundary"
            )
        validate_dot_svg_regeneration(
            evidence_dot,
            evidence_svg,
            "product surface evidence lifecycle",
            failures,
        )

    runtime_dot = repo / "analysis/visuals/product-surface-runtime-planes.dot"
    runtime_svg = repo / "analysis/visuals/product-surface-runtime-planes.svg"
    if not runtime_dot.is_file() or not runtime_svg.is_file():
        failures.append("product surface runtime-plane DOT/SVG is missing")
    else:
        dot_text = runtime_dot.read_text(encoding="utf-8")
        for required in (
            "CLI / TUI / SDK",
            "Streaming Agent Loop",
            "paired tool_result",
            "resume / fork / compact feedback",
            "外部 owner 与真实副作用",
            "服务端工具 Boundary",
            "请求 owner 的局部回路",
            "loop owner 重建 attempt",
            "各子系统写 reference / status",
            "O 观测与诊断",
        ):
            if required not in dot_text:
                failures.append(
                    f"product surface runtime-plane visual is missing {required!r}"
                )
        for source, target, label_terms in (
            ("input", "control", ("加载入口", "当前环境")),
            ("control", "request", ("约束能力", "请求参数")),
            ("request", "remote", ("API attempt",)),
            ("remote", "loop", ("assistant blocks",)),
            ("remote", "server_tools", ("server_tool_use", "服务端内部执行")),
            ("server_tools", "remote", ("server result block",)),
            ("loop", "execute", ("client tool_use",)),
            ("execute", "loop", ("paired tool_result", "tool_use_id")),
            ("execute", "effects", ("实际动作",)),
            ("state", "request", ("resume / fork / compact feedback",)),
            ("request", "request", ("transport retry", "model fallback", "局部回路")),
            ("loop", "request", ("stream fallback", "tombstone", "重建 attempt")),
            ("effects", "state", ("partial", "unknown outcome", "reference", "status")),
        ):
            require_dot_edge(
                dot_text,
                source=source,
                target=target,
                label_terms=label_terms,
                visual_name="product surface runtime-plane visual",
                failures=failures,
            )
        if re.search(r"^\s*recovery\s*\[", dot_text, re.MULTILINE):
            failures.append(
                "product surface runtime-plane visual must not invent a centralized recovery node"
            )
        outbound_observe = [
            (source, target, label)
            for source, target, label in dot_edges(dot_text)
            if source == "observe"
        ]
        if outbound_observe:
            failures.append(
                "product surface runtime-plane visual must keep observability as an inbound-only sink"
            )
        validate_dot_svg_regeneration(
            runtime_dot,
            runtime_svg,
            "product surface runtime-plane visual",
            failures,
        )

    telemetry_dot = repo / "analysis/visuals/telemetry-pipeline.dot"
    telemetry_svg = repo / "analysis/visuals/telemetry-pipeline.svg"
    if not telemetry_dot.is_file() or not telemetry_svg.is_file():
        failures.append("product surface telemetry DOT/SVG is missing")
    else:
        dot_text = telemetry_dot.read_text(encoding="utf-8")
        for source, target, label_terms in (
            ("events", "enrich", ("结构化记录",)),
            ("enrich", "privacy", ("字段", "流量门")),
            ("privacy", "first", ("一方发送", "best-effort")),
            ("privacy", "datadog", ("sampling", "分支 gate")),
            ("privacy", "otel", ("第三方出口", "signal/content")),
            ("privacy", "local", ("本地诊断",)),
        ):
            require_dot_edge(
                dot_text,
                source=source,
                target=target,
                label_terms=label_terms,
                visual_name="product surface telemetry visual",
                failures=failures,
            )
        validate_dot_svg_regeneration(
            telemetry_dot,
            telemetry_svg,
            "product surface telemetry visual",
            failures,
        )

    with tempfile.TemporaryDirectory(prefix="claude-product-surface-") as temporary:
        regenerated = Path(temporary) / "product-surface-evidence-map.md"
        process = subprocess.run(
            [sys.executable, str(generator), str(repo), "--output", str(regenerated)],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if process.returncode != 0:
            failures.append(
                "product surface evidence map regeneration failed: "
                + process.stdout.strip()
            )
        elif regenerated.read_bytes() != path.read_bytes():
            failures.append(
                "product surface evidence map differs from deterministic regeneration"
            )


def validate_generated_control_references(repo: Path, failures: list[str]) -> None:
    generator = (
        repo
        / "skill/claude-code-version-diff/scripts/"
        "build_environment_feature_references.py"
    )
    if not generator.is_file():
        failures.append("missing environment/feature reference generator")
        return

    process = subprocess.run(
        [sys.executable, str(generator), str(repo), "--check"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if process.returncode != 0:
        failures.append(
            "environment/feature reference generation check failed: "
            + process.stdout.strip()
        )

    consumer_roles = {
        "if",
        "test",
        "return",
        "variable",
        "assignment",
        "assignment-target",
        "call-argument",
        "binary",
        "logical",
        "conditional",
        "object-property",
        "member",
        "delete",
        "unary",
        "update",
        "other",
    }
    context_inventories = {
        "analysis/source-inventory/environment-access-callsites.jsonl": (
            2548,
            True,
        ),
        "analysis/source-inventory/feature-flag-callsites.jsonl": (498, False),
    }
    for relative, (expected_count, needs_access_mode) in context_inventories.items():
        rows = read_jsonl(repo / relative, failures)
        if len(rows) != expected_count:
            failures.append(
                f"consumer context inventory count mismatch: {relative}: "
                f"{len(rows)} != {expected_count}"
            )
        for index, row in enumerate(rows, 1):
            if row.get("functionKind") not in {"top-level", "named", "anonymous"}:
                failures.append(
                    f"consumer context row has invalid function kind: {relative}:{index}"
                )
            scope_path = row.get("scopePath")
            if not isinstance(scope_path, list) or not all(
                isinstance(item, int) and item > 0 for item in scope_path
            ):
                failures.append(
                    f"consumer context row has invalid scope path: {relative}:{index}"
                )
            consumer = row.get("consumer")
            if not isinstance(consumer, dict):
                failures.append(
                    f"consumer context row is missing consumer object: {relative}:{index}"
                )
                continue
            if consumer.get("role") not in consumer_roles:
                failures.append(
                    f"consumer context row has invalid role: {relative}:{index}"
                )
            for range_field in ("consumerRange", "valueRange"):
                value = consumer.get(range_field)
                if not (
                    isinstance(value, list)
                    and len(value) == 2
                    and all(isinstance(item, int) and item >= 0 for item in value)
                    and value[0] <= value[1]
                ):
                    failures.append(
                        f"consumer context row has invalid {range_field}: "
                        f"{relative}:{index}"
                    )
            if needs_access_mode and row.get("accessMode") not in {
                "read",
                "write",
                "read-write",
                "delete",
            }:
                failures.append(
                    f"environment context row has invalid access mode: {relative}:{index}"
                )
        if needs_access_mode:
            dynamic_rows = [row for row in rows if row.get("name") is None]
            resolved_rows = [
                row
                for row in dynamic_rows
                if "resolvedStaticValue" in row or "resolvedFiniteValues" in row
            ]
            unresolved_rows = [
                row
                for row in dynamic_rows
                if "resolvedStaticValue" not in row
                and "resolvedFiniteValues" not in row
            ]
            if (len(dynamic_rows), len(resolved_rows), len(unresolved_rows)) != (
                145,
                60,
                85,
            ):
                failures.append(
                    "dynamic environment resolution coverage mismatch: "
                    f"{len(dynamic_rows)}/{len(resolved_rows)}/{len(unresolved_rows)}"
                )
            for row in resolved_rows:
                values = (
                    [row["resolvedStaticValue"]]
                    if "resolvedStaticValue" in row
                    else row.get("resolvedFiniteValues")
                )
                if not (
                    isinstance(values, list)
                    and values
                    and len(values) <= 64
                    and len(values) == len(set(values))
                    and all(
                        isinstance(value, str)
                        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
                        for value in values
                    )
                ):
                    failures.append(
                        "resolved dynamic environment row has invalid finite names: "
                        f"{row.get('comparisonKey')}"
                    )
                resolution = row.get("resolutionEvidence")
                if not (
                    isinstance(resolution, dict)
                    and resolution.get("complete") is True
                    and resolution.get("valueCount") == len(values or [])
                    and isinstance(resolution.get("strategy"), str)
                    and resolution["strategy"]
                ):
                    failures.append(
                        "resolved dynamic environment row has invalid evidence: "
                        f"{row.get('comparisonKey')}"
                    )

    inventory_summary = json.loads(
        (repo / "analysis/source-inventory/summary.json").read_text(encoding="utf-8")
    )
    expected_environment_coverage = {
        "dynamicBracketCallsites": 145,
        "resolvedDynamicBracketCallsites": 60,
        "unresolvedDynamicBracketCallsites": 85,
        "unresolvedDynamicExpressionKinds": {
            "call": 2,
            "expression": 3,
            "identifier": 55,
            "member-or-call": 25,
        },
    }
    environment_coverage = inventory_summary.get("coverage", {}).get(
        "environment", {}
    )
    for field, expected_value in expected_environment_coverage.items():
        if environment_coverage.get(field) != expected_value:
            failures.append(
                "dynamic environment summary mismatch: "
                f"{field} expected={expected_value!r}, "
                f"actual={environment_coverage.get(field)!r}"
            )

    expected = {
        "analysis/environment-variable-reference.md": (
            "ENVIRONMENT_VARIABLE_REFERENCE",
            {
                "environment_schema": 842,
                "environment_callsites": 2548,
                "typed_named_callsites": 2161,
                "typed_used_names": 762,
                "typed_declaration_only": 80,
                "untyped_named_names": 137,
                "untyped_named_callsites": 242,
                "dynamic_environment_callsites": 145,
                "resolved_dynamic_environment_callsites": 60,
                "unresolved_dynamic_environment_callsites": 85,
                "resolved_dynamic_environment_names": 105,
                "resolved_dynamic_only_typed_names": 6,
                "typed_no_static_consumer": 74,
            },
        ),
        "analysis/feature-flag-reference.md": (
            "FEATURE_FLAG_REFERENCE",
            {
                "feature_keys": 361,
                "feature_callsites": 498,
                "feature_resolvable_static_callsites": 455,
                "feature_direct_literal_callsites": 444,
                "feature_resolved_nonliteral_callsites": 11,
                "feature_unresolved_dynamic_callsites": 43,
                "dynamic_config_static_keys": 6,
                "dynamic_config_callsites": 12,
            },
        ),
    }
    consumer_contracts = {
        "analysis/environment-variable-reference.md": {
            "marker": "ENVIRONMENT_VARIABLE_REFERENCE:CONSUMER_CONTRACT_NAMES",
            "countField": "consumerContractCount",
            "hashField": "consumerContractNamesSha256",
            "minimumCount": 313,
            "callsiteOnlyField": "callsiteOnlyNamedReadCount",
            "expectedCallsiteOnly": 592,
            "summaryCounts": {
                "lexicalContextCallsiteCount": 2548,
                "consumerContextCallsiteCount": 2548,
                "accessModeCallsiteCount": 2548,
                "directConsumerContractCount": 307,
                "resolvedDynamicOnlyConsumerContractCount": 6,
                "semanticFollowupStaticNameCount": 654,
                "resolvedDynamicCallsiteCount": 60,
                "unresolvedDynamicCallsiteCount": 85,
                "resolvedDynamicOnlyTypedNameCount": 6,
                "noStaticConsumerTypedNameCount": 74,
            },
            "required": {
                "ALL_PROXY",
                "ANTHROPIC_BEDROCK_SERVICE_TIER",
                "ANTHROPIC_CONFIG_DIR",
                "AWS_SHARED_CREDENTIALS_FILE",
                "BASH_MAX_OUTPUT_LENGTH",
                "CLAUDE_AGENT_SDK_VERSION",
                "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
                "CLAUDE_CODE_BRIEF",
                "CLAUDE_CODE_CERT_STORE",
                "CLAUDE_CODE_DISABLE_ADVISOR_TOOL",
                "CLAUDE_CODE_DISABLE_AGENT_VIEW",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
                "CLAUDE_CODE_ENABLE_AWAY_SUMMARY",
                "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS",
                "CLAUDE_CODE_PERFETTO_TRACE",
                "CLAUDE_CODE_SESSION_LOG",
                "DISABLE_BRIEF_MODE_STOP_HOOK",
                "OTEL_LOG_RAW_API_BODIES",
                "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
                "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
                "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
                "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
                "CLAUDE_PTY_HEARTBEAT_MS",
                "CLAUDE_PTY_ORPHAN_CHECK_MS",
                "CLAUDE_BG_CLAIM_AUTH",
                "CLAUDE_BG_SOCKET_TOKENS_PATH",
                "MCP_CONNECT_TIMEOUT_MS",
            },
        },
        "analysis/feature-flag-reference.md": {
            "marker": "FEATURE_FLAG_REFERENCE:CONSUMER_CONTRACT_KEYS",
            "countField": "consumerContractCount",
            "hashField": "consumerContractKeysSha256",
            "minimumCount": 150,
            "callsiteOnlyField": "callsiteOnlyStaticKeyCount",
            "expectedCallsiteOnly": 211,
            "summaryCounts": {
                "lexicalContextCallsiteCount": 498,
                "consumerContextCallsiteCount": 498,
            },
            "required": {
                "tengu_amber_packet",
                "tengu_bg_attach_upgrade",
                "tengu_ccr_idle_heartbeat",
                "tengu_cobalt_plinth_reader_persist",
                "tengu_copper_thistle",
                "tengu_flint_harbor_prompt",
                "tengu_gb_refresh_interval_minutes",
                "tengu_harbor_moth",
                "tengu_hazel_osprey",
                "tengu_hover_rest",
                "tengu_kairos_brief",
                "tengu_kairos_brief_config",
                "tengu_import",
                "tengu_keybinding_customization_release",
                "tengu_mcp_listen_reopen_park",
                "tengu_mcp_proxy_needs_approval_retry",
                "tengu_remote_backend",
                "tengu_sedge_lantern_config",
                "tengu_slate_harbor",
                "tengu_surreal_dali",
                "tengu_umber_kestrel",
            },
        },
    }
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    for relative, (prefix, expected_metrics) in expected.items():
        path = repo / relative
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        summary_text = text_between(
            content,
            f"<!-- BEGIN:{prefix}:MACHINE_SUMMARY",
            f"END:{prefix}:MACHINE_SUMMARY -->",
        ).strip()
        try:
            summary = json.loads(summary_text)
        except json.JSONDecodeError as error:
            failures.append(f"generated reference summary is invalid: {relative}: {error}")
            continue
        if summary.get("artifact") != relative:
            failures.append(f"generated reference artifact mismatch: {relative}")
        if summary.get("version") != version:
            failures.append(f"generated reference version mismatch: {relative}")
        metrics = summary.get("metrics")
        if not isinstance(metrics, dict):
            failures.append(f"generated reference metrics are missing: {relative}")
            continue
        for key, expected_value in expected_metrics.items():
            if metrics.get(key) != expected_value:
                failures.append(
                    f"generated reference metric mismatch: {relative}: "
                    f"{key} expected={expected_value}, actual={metrics.get(key)}"
                )
        contract = consumer_contracts.get(relative)
        if contract is None:
            continue
        marker = str(contract["marker"])
        contract_names = [
            line.strip()
            for line in text_between(
                content,
                f"<!-- BEGIN:{marker}",
                f"END:{marker} -->",
            ).splitlines()
            if line.strip()
        ]
        if len(contract_names) != len(set(contract_names)):
            failures.append(f"consumer contract marker contains duplicates: {relative}")
        minimum_count = int(contract["minimumCount"])
        if len(contract_names) < minimum_count:
            failures.append(
                f"consumer contract coverage regressed: {relative}: "
                f"minimum={minimum_count}, actual={len(contract_names)}"
            )
        if summary.get(str(contract["countField"])) != len(contract_names):
            failures.append(f"consumer contract count mismatch: {relative}")
        observed_hash = hashlib.sha256(
            "".join(f"{name}\n" for name in sorted(contract_names)).encode("utf-8")
        ).hexdigest()
        if summary.get(str(contract["hashField"])) != observed_hash:
            failures.append(f"consumer contract hash mismatch: {relative}")
        if summary.get(str(contract["callsiteOnlyField"])) != int(
            contract["expectedCallsiteOnly"]
        ):
            failures.append(f"callsite-only coverage mismatch: {relative}")
        for field, expected_count in contract.get("summaryCounts", {}).items():
            if summary.get(field) != expected_count:
                failures.append(
                    f"consumer context coverage mismatch: {relative}: "
                    f"{field} expected={expected_count}, actual={summary.get(field)}"
                )
        missing_required = sorted(set(contract["required"]) - set(contract_names))
        if missing_required:
            failures.append(
                f"required consumer contracts missing: {relative}: "
                + ", ".join(missing_required)
            )

    telemetry_generator = (
        repo
        / "skill/claude-code-version-diff/scripts/"
        "build_telemetry_event_catalog.py"
    )
    telemetry_catalog = repo / "analysis/telemetry-event-catalog.md"
    if not telemetry_generator.is_file():
        failures.append("missing telemetry event catalog generator")
    elif not telemetry_catalog.is_file():
        failures.append("missing telemetry event catalog")
    else:
        with tempfile.TemporaryDirectory(
            prefix="claude-telemetry-event-catalog-"
        ) as temporary:
            regenerated = Path(temporary) / "telemetry-event-catalog.md"
            telemetry_process = subprocess.run(
                [
                    sys.executable,
                    str(telemetry_generator),
                    str(repo),
                    "--output",
                    str(regenerated),
                ],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if telemetry_process.returncode != 0:
                failures.append(
                    "telemetry event catalog regeneration failed: "
                    + telemetry_process.stdout.strip()
                )
            elif regenerated.read_bytes() != telemetry_catalog.read_bytes():
                failures.append(
                    "telemetry event catalog differs from deterministic regeneration"
                )

    api_error_generator = (
        repo
        / "skill/claude-code-version-diff/scripts/"
        "build_api_error_references.py"
    )
    if not api_error_generator.is_file():
        failures.append("missing API/error reference generator")
    else:
        api_error_process = subprocess.run(
            [sys.executable, str(api_error_generator), str(repo), "--check"],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if api_error_process.returncode != 0:
            failures.append(
                "API/error reference generation check failed: "
                + api_error_process.stdout.strip()
            )


def validate_completeness_closure(
    repo: Path, failures: list[str]
) -> dict[int, list[str]]:
    path = repo / "analysis/completeness-audit.md"
    if not path.is_file():
        return {}
    rows: dict[int, list[str]] = {}
    row_order: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        capability = int(cells[0])
        row_order.append(capability)
        rows[capability] = cells
    expected_last_capability = max(
        capability
        for contract in TOPIC_DEPTH_CONTRACTS.values()
        for capability in topic_contract_capabilities(contract)
    ) + 1
    expected_order = list(range(1, expected_last_capability + 1))
    if row_order != expected_order:
        missing = sorted(set(expected_order) - set(row_order))
        failures.append(
            "completeness capability coverage mismatch: "
            f"expected={expected_last_capability}, actual={len(row_order)}, "
            f"missing={missing}, ordered={row_order == expected_order}"
        )

    for capability in range(1, expected_last_capability):
        if capability not in rows:
            continue
        state = rows[capability][4]
        if state != "Deep":
            failures.append(
                f"completeness capability {capability} is not closed: {state}"
            )
    boundary_row = rows.get(expected_last_capability)
    if boundary_row is not None and boundary_row[4] != "Boundary":
        failures.append(
            f"last completeness capability {expected_last_capability} "
            "must remain Boundary: "
            f"{boundary_row[4]}"
        )

    tool_documents = rows.get(7, ["", "", "", ""])[3]
    if rows.get(7) is not None and "tool-registration-and-host-surfaces.md" not in tool_documents:
        failures.append(
            "completeness capability 7 does not bind the tool registration guide"
        )

    brief_capability = rows.get(51)
    if brief_capability is not None:
        if (
            "Brief" not in brief_capability[1]
            and "SendUserMessage" not in brief_capability[1]
        ):
            failures.append("completeness capability 51 is not the Brief capability")
        if "brief-mode-and-user-visible-output.md" not in brief_capability[3]:
            failures.append(
                "completeness capability 51 does not bind the Brief output guide"
            )

    return rows


def nested_value(document: object, dotted_path: str) -> object:
    value = document
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted_path)
        value = value[part]
    return value


def read_jsonl(path: Path, failures: list[str]) -> list[dict]:
    records: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    failures.append(f"blank JSONL record: {path.name}:{line_number}")
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    failures.append(f"non-object JSONL record: {path.name}:{line_number}")
                    continue
                records.append(record)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"invalid JSONL {path.name}: {error}")
    return records


def normalize_public_text(value: str) -> str:
    normalized = value.translate(
        str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", normalized)


def validate_public_sources(repo: Path, failures: list[str]) -> tuple[dict[str, dict], set[str]]:
    manifest_path = repo / "analysis/public-sources/manifest.json"
    excerpts_path = repo / "analysis/public-source-excerpts.md"
    if not manifest_path.is_file():
        failures.append("missing analysis/public-sources/manifest.json")
        return {}, set()
    if not excerpts_path.is_file():
        failures.append("missing analysis/public-source-excerpts.md")
        return {}, set()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"invalid public source manifest: {error}")
        return {}, set()
    if manifest.get("schemaVersion") != 2:
        failures.append("public source manifest schemaVersion must equal 2")
    if not isinstance(manifest.get("retrievedAt"), str) or not manifest["retrievedAt"]:
        failures.append("public source manifest missing retrievedAt")
    if not isinstance(manifest.get("captureMethod"), str) or not manifest["captureMethod"]:
        failures.append("public source manifest missing captureMethod")
    sources: dict[str, dict] = {}
    declared_owners: dict[str, str] = {}
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            failures.append("public source manifest contains a non-object source")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            failures.append("public source manifest source missing id")
            continue
        if source_id in sources:
            failures.append(f"duplicate public source id: {source_id}")
        sources[source_id] = source
        if not str(source.get("url", "")).startswith("https://"):
            failures.append(f"public source {source_id} must use an https URL")
        if source.get("status") != 200:
            failures.append(f"public source {source_id} status is not 200")
        if not isinstance(source.get("bytes"), int) or source["bytes"] < 1:
            failures.append(f"public source {source_id} has invalid byte count")
        if not re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))):
            failures.append(f"public source {source_id} has invalid sha256")
        if not isinstance(source.get("semanticTextBytes"), int) or source["semanticTextBytes"] < 1:
            failures.append(f"public source {source_id} has invalid semanticTextBytes")
        if not re.fullmatch(r"[0-9a-f]{64}", str(source.get("semanticTextSha256", ""))):
            failures.append(f"public source {source_id} has invalid semanticTextSha256")
        excerpt_ids = source.get("excerptIds")
        if not isinstance(excerpt_ids, list) or not excerpt_ids:
            failures.append(f"public source {source_id} has no excerptIds")
            continue
        for excerpt_id in excerpt_ids:
            if not isinstance(excerpt_id, str) or not excerpt_id:
                failures.append(f"public source {source_id} has an invalid excerptId")
                continue
            previous_owner = declared_owners.get(excerpt_id)
            if previous_owner is not None:
                failures.append(
                    f"public excerpt {excerpt_id} has multiple owners: "
                    f"{previous_owner}, {source_id}"
                )
            declared_owners[excerpt_id] = source_id
        excerpt_hashes = source.get("excerptSha256")
        if not isinstance(excerpt_hashes, dict) or set(excerpt_hashes) != set(excerpt_ids):
            failures.append(f"public source {source_id} excerptSha256 keys differ from excerptIds")
        elif not all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in excerpt_hashes.values()):
            failures.append(f"public source {source_id} has invalid excerptSha256")
        source_verified = source.get("excerptSourceVerified")
        if not isinstance(source_verified, dict) or set(source_verified) != set(excerpt_ids):
            failures.append(
                f"public source {source_id} excerptSourceVerified keys differ from excerptIds"
            )
        elif not all(value is True for value in source_verified.values()):
            failures.append(f"public source {source_id} has unverified quoted excerpts")
    excerpts = excerpts_path.read_text(encoding="utf-8")
    heading_matches = list(re.finditer(r"^## `([^`]+)`\s*$", excerpts, re.MULTILINE))
    excerpt_ids = {match.group(1) for match in heading_matches}
    if len(excerpt_ids) != len(heading_matches):
        failures.append("public source excerpt file contains duplicate headings")
    excerpt_owners: dict[str, str] = {}
    observed_excerpt_hashes: dict[str, str] = {}
    for index, match in enumerate(heading_matches):
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(excerpts)
        block = excerpts[match.end():end]
        source_match = re.search(r"^Source: `([^`]+)`\s*$", block, re.MULTILINE)
        if source_match is None:
            failures.append(f"public excerpt {match.group(1)} has no Source line")
        else:
            excerpt_owners[match.group(1)] = source_match.group(1)
        if not re.search(r"^>\s+\S", block, re.MULTILINE):
            failures.append(f"public excerpt {match.group(1)} has no quoted content")
        quotes = re.findall(r"^>\s?(.*)$", block, re.MULTILINE)
        normalized = normalize_public_text(" ".join(quotes))
        observed_excerpt_hashes[match.group(1)] = hashlib.sha256(normalized.encode()).hexdigest()
    declared = set(declared_owners)
    if excerpt_ids != declared:
        failures.append(
            "public source excerpt set differs from manifest: "
            f"extra={sorted(excerpt_ids - declared)}, missing={sorted(declared - excerpt_ids)}"
        )
    for excerpt_id in sorted(excerpt_ids & declared):
        if excerpt_owners.get(excerpt_id) != declared_owners.get(excerpt_id):
            failures.append(
                f"public excerpt {excerpt_id} source mismatch: "
                f"{excerpt_owners.get(excerpt_id)!r} != {declared_owners.get(excerpt_id)!r}"
            )
        source = sources[declared_owners[excerpt_id]]
        if source.get("excerptSha256", {}).get(excerpt_id) != observed_excerpt_hashes[excerpt_id]:
            failures.append(f"public excerpt {excerpt_id} hash differs from manifest")

    declared_urls = {source.get("url") for source in sources.values()}
    official_url = re.compile(
        r"https://(?:code\.claude\.com/docs/[A-Za-z0-9_./?#=&%-]+|"
        r"www\.anthropic\.com/(?:engineering|research)/[A-Za-z0-9_./?#=&%-]+)"
    )
    referenced_urls: set[str] = set()
    generated_bundle_references = {
        "analysis/environment-variable-reference.md",
        "analysis/feature-flag-reference.md",
        "analysis/telemetry-event-catalog.md",
    }
    for relative in candidate_paths(repo):
        if not relative.endswith(".md"):
            continue
        if relative in generated_bundle_references:
            # These deterministic catalogs render literal bundle expressions.
            # A URL inside such a row is shipped-artifact evidence, not an
            # editorial citation or a current public-documentation claim.
            continue
        if relative.startswith("analysis/comparison-"):
            # Deterministic comparison reports quote inventory payloads from both
            # releases. Embedded URLs there are bundle evidence, not public claims.
            continue
        try:
            referenced_urls.update(
                url.rstrip(".,;:!?")
                for url in official_url.findall(
                    (repo / relative).read_text(encoding="utf-8")
                )
            )
        except (OSError, UnicodeDecodeError):
            continue
    missing_urls = sorted(referenced_urls - declared_urls)
    if missing_urls:
        failures.append(f"official Markdown URLs missing from public manifest: {missing_urls}")
    return sources, excerpt_ids


def validate_markdown_source_references(repo: Path, failures: list[str]) -> None:
    line_counts = {
        relative: sum(1 for _ in (repo / relative).open("r", encoding="utf-8"))
        for relative in SOURCE_VIEW_PATHS.values()
    }
    for relative in candidate_paths(repo):
        if not relative.endswith(".md"):
            continue
        path = repo / relative
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for markdown_line, content in enumerate(lines, 1):
            for source_path, source_lines in line_counts.items():
                marker = f"`{source_path}`"
                start = content.find(marker)
                if start < 0:
                    continue
                suffix = content[start + len(marker):]
                for referenced_line in re.findall(r"(?<![.\d])\d{4,6}(?![.\d])", suffix):
                    value = int(referenced_line)
                    if value > source_lines:
                        failures.append(
                            f"out-of-range source reference: {relative}:{markdown_line} "
                            f"{source_path}:{value} > {source_lines}"
                        )


def validate_mechanism_evidence(repo: Path, failures: list[str]) -> int:
    path = repo / "analysis/mechanism-evidence.jsonl"
    if not path.is_file():
        failures.append("missing analysis/mechanism-evidence.jsonl")
        return 0
    records = read_jsonl(path, failures)
    sources, excerpt_ids = validate_public_sources(repo, failures)
    source_cache: dict[str, list[str]] = {}
    claim_ids: set[str] = set()
    probe_claim_ids: set[str] = set()
    topic_counts: dict[str, int] = {}
    for index, record in enumerate(records, 1):
        claim_id = record.get("claimId")
        evidence_class = record.get("evidenceClass")
        if not isinstance(claim_id, str) or not claim_id:
            failures.append(f"mechanism evidence record {index} missing claimId")
            continue
        if claim_id in claim_ids:
            failures.append(f"duplicate mechanism evidence claimId: {claim_id}")
        claim_ids.add(claim_id)
        if evidence_class not in EVIDENCE_CLASSES:
            failures.append(f"mechanism evidence {claim_id} has invalid evidenceClass")
            continue
        if not isinstance(record.get("claim"), str) or not record["claim"]:
            failures.append(f"mechanism evidence {claim_id} missing claim text")
        topic = record.get("topic")
        if not isinstance(topic, str) or not topic:
            failures.append(f"mechanism evidence {claim_id} missing topic")
        else:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        if evidence_class == "Static":
            static_kind = record.get("staticEvidenceKind")
            if static_kind not in STATIC_EVIDENCE_KINDS:
                failures.append(
                    f"mechanism evidence {claim_id} has invalid staticEvidenceKind"
                )
            if static_kind in {"surface", "declaration"} and not isinstance(
                record.get("evidenceLimitation"), str
            ):
                failures.append(
                    f"mechanism evidence {claim_id} must state evidenceLimitation "
                    f"for {static_kind} evidence"
                )
            source_view = record.get("sourceView")
            relative = record.get("path")
            if SOURCE_VIEW_PATHS.get(source_view) != relative:
                failures.append(
                    f"mechanism evidence {claim_id} sourceView/path mismatch: "
                    f"{source_view!r} -> {relative!r}"
                )
                continue
            source_path = repo / str(relative)
            if not source_path.is_file():
                failures.append(f"mechanism evidence {claim_id} source file is missing")
                continue
            lines = source_cache.setdefault(
                str(relative), source_path.read_text(encoding="utf-8").split("\n")
            )
            start_line = record.get("startLine")
            end_line = record.get("endLine")
            if (
                not isinstance(start_line, int)
                or not isinstance(end_line, int)
                or start_line < 1
                or end_line < start_line
                or end_line > len(lines)
            ):
                failures.append(
                    f"mechanism evidence {claim_id} has invalid line range "
                    f"{start_line}-{end_line} for {len(lines)} lines"
                )
                continue
            anchors = record.get("anchors")
            if not isinstance(anchors, list) or not anchors or not all(
                isinstance(anchor, str) and anchor for anchor in anchors
            ):
                failures.append(f"mechanism evidence {claim_id} has invalid anchors")
                continue
            evidence_text = "\n".join(lines[start_line - 1:end_line])
            for anchor in anchors:
                if anchor not in evidence_text:
                    failures.append(
                        f"mechanism evidence {claim_id} anchor absent from range: {anchor!r}"
                    )

        elif evidence_class == "Probe":
            probe_claim_ids.add(claim_id)
            report_relative = record.get("reportPath")
            if (
                not isinstance(report_relative, str)
                or not report_relative.startswith("analysis/runtime-probes/")
                or ".." in Path(report_relative).parts
            ):
                failures.append(f"mechanism evidence {claim_id} has invalid probe reportPath")
                continue
            report_path = repo / str(report_relative)
            if not report_path.is_file():
                failures.append(f"mechanism evidence {claim_id} probe report is missing")
                continue
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                failures.append(f"mechanism evidence {claim_id} has invalid probe report: {error}")
                continue
            target = report.get("target", {})
            captured_at = report.get("capturedAt")
            if not isinstance(captured_at, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", captured_at
            ):
                failures.append(
                    f"mechanism evidence {claim_id} probe report has invalid capturedAt"
                )
            environment = report.get("environment", {})
            for metadata_field in ("platform", "arch", "nodeVersion"):
                if not isinstance(environment.get(metadata_field), str) or not environment[metadata_field]:
                    failures.append(
                        f"mechanism evidence {claim_id} probe environment missing {metadata_field}"
                    )
            if not isinstance(target.get("version"), str) or not target["version"]:
                failures.append(f"mechanism evidence {claim_id} probe target missing version")
            if not re.fullmatch(r"[0-9a-f]{64}", str(target.get("binarySha256", ""))):
                failures.append(f"mechanism evidence {claim_id} probe target has invalid binarySha256")
            for field_name in (
                "commandField",
                "inputField",
                "literalOutputField",
                "exitStatusField",
            ):
                field = record.get(field_name)
                if not isinstance(field, str):
                    failures.append(f"mechanism evidence {claim_id} missing {field_name}")
                    continue
                try:
                    value = nested_value(report, field)
                except KeyError:
                    failures.append(
                        f"mechanism evidence {claim_id} probe report missing field {field}"
                    )
                    continue
                if field_name != "exitStatusField" and value in (None, "", [], {}):
                    failures.append(
                        f"mechanism evidence {claim_id} probe field {field} is empty"
                    )
                if field_name == "commandField" and not isinstance(value, str):
                    failures.append(
                        f"mechanism evidence {claim_id} probe command field {field} is not text"
                    )
                if field_name == "exitStatusField" and not isinstance(value, int):
                    failures.append(
                        f"mechanism evidence {claim_id} probe exit field {field} is not an integer"
                    )
            try:
                exit_status = nested_value(report, str(record.get("exitStatusField")))
            except KeyError:
                exit_status = None
            if exit_status != record.get("expectedExitStatus"):
                failures.append(
                    f"mechanism evidence {claim_id} probe exit status mismatch: "
                    f"{exit_status!r} != {record.get('expectedExitStatus')!r}"
                )
            if report.get("pass") is not True:
                failures.append(f"mechanism evidence {claim_id} probe report did not pass")
            required_checks = record.get("requiredChecks")
            if (
                not isinstance(required_checks, list)
                or not required_checks
                or not all(isinstance(check, str) and check for check in required_checks)
                or len(set(required_checks)) != len(required_checks)
            ):
                failures.append(f"mechanism evidence {claim_id} has invalid requiredChecks")
                required_checks = []
            for check in required_checks:
                if report.get("checks", {}).get(check) is not True:
                    failures.append(
                        f"mechanism evidence {claim_id} required probe check failed: {check}"
                    )

        elif evidence_class == "Public":
            source_id = record.get("sourceId")
            excerpt_id = record.get("excerptId")
            source = sources.get(str(source_id))
            if source is None:
                failures.append(f"mechanism evidence {claim_id} has unknown public source")
            if excerpt_id not in excerpt_ids:
                failures.append(f"mechanism evidence {claim_id} has unknown excerptId")
            if source is not None and excerpt_id not in source.get("excerptIds", []):
                failures.append(
                    f"mechanism evidence {claim_id} excerpt is not owned by source {source_id}"
                )

        elif not isinstance(record.get("boundaryReason"), str) or not record["boundaryReason"]:
            failures.append(f"mechanism evidence {claim_id} missing boundaryReason")

    for topic, minimum in MECHANISM_TOPIC_MINIMUMS.items():
        if topic_counts.get(topic, 0) < minimum:
            failures.append(
                f"mechanism topic {topic!r} has {topic_counts.get(topic, 0)} claims; minimum is {minimum}"
            )
    if len(records) < 90:
        failures.append(f"mechanism evidence has {len(records)} records; minimum is 90")
    probe_index_path = repo / "analysis/runtime-probe-index.md"
    if not probe_index_path.is_file():
        failures.append("missing analysis/runtime-probe-index.md")
    else:
        probe_index = probe_index_path.read_text(encoding="utf-8")
        for probe_claim_id in sorted(probe_claim_ids):
            if f"`{probe_claim_id}`" not in probe_index:
                failures.append(f"Probe claim is missing from runtime probe index: {probe_claim_id}")
    validate_markdown_source_references(repo, failures)
    return len(records)


def validate_native_reconstruction_report(repo: Path, failures: list[str]) -> int:
    path = repo / "analysis/runtime-probes/native-reconstruction.json"
    if not path.is_file():
        failures.append("missing native reconstruction behavior coverage report")
        return 0
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        version = json.loads((repo / "analysis/version.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"invalid native reconstruction behavior report: {error}")
        return 0
    if report.get("schemaVersion") != 1 or report.get("pass") is not True:
        failures.append("native reconstruction behavior report did not pass schema 1")
    captured_at = report.get("capturedAt")
    if not isinstance(captured_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", captured_at
    ):
        failures.append("native reconstruction report has invalid capturedAt")
    environment = report.get("environment", {})
    for metadata_field in ("platform", "arch", "nodeVersion"):
        if not isinstance(environment.get(metadata_field), str) or not environment[metadata_field]:
            failures.append(
                f"native reconstruction environment missing {metadata_field}"
            )
    if report.get("target", {}).get("version") != version.get("version"):
        failures.append("native reconstruction report version differs from snapshot")
    if report.get("target", {}).get("binarySha256") != version.get("binary", {}).get("sha256"):
        failures.append("native reconstruction report binary hash differs from snapshot")
    checks = report.get("checkResults")
    if not isinstance(checks, list) or len(checks) < 23:
        failures.append("native reconstruction report has fewer than 23 checks")
        checks = []
    if any(check.get("status") != "pass" for check in checks if isinstance(check, dict)):
        failures.append("native reconstruction report contains a failed check")
    required_checks = report.get("checks", {})
    for name in (
        "originalContract",
        "compatibleContract",
        "behaviorChecksPassed",
        "arm64RuntimeCoverage",
        "x86StaticBoundaryExplicit",
    ):
        if required_checks.get(name) is not True:
            failures.append(f"native reconstruction required check failed: {name}")
    coverage = report.get("architectureCoverage", {})
    if coverage.get("original", {}).get("arm64", {}).get("method") != "runtime-and-static":
        failures.append("original arm64 native coverage is not runtime-and-static")
    if coverage.get("original", {}).get("x86_64", {}).get("method") != "static-only":
        failures.append("original x86_64 native coverage is not static-only")
    if coverage.get("compatible", {}).get("arm64", {}).get("method") != "build-and-runtime":
        failures.append("compatible arm64 native coverage is not build-and-runtime")
    if coverage.get("compatible", {}).get("x86_64", {}).get("method") != "not-built-or-run":
        failures.append("compatible x86_64 native boundary is not explicit")
    return len(checks)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cli_command_tree(
    repo: Path, version: str, metadata: dict, failures: list[str]
) -> tuple[int, int]:
    inventory_path = repo / "analysis/cli-command-inventory.json"
    probe_path = repo / "analysis/runtime-probes/cli-command-tree.json"
    missing = [
        path.relative_to(repo)
        for path in (inventory_path, probe_path)
        if not path.is_file()
    ]
    if missing:
        failures.extend(f"missing CLI command-tree artifact: {path}" for path in missing)
        return 0, 0

    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"invalid CLI command-tree artifact: {error}")
        return 0, 0

    expected_binary_sha = metadata.get("binary", {}).get("sha256")
    if inventory.get("schemaVersion") != 1:
        failures.append("CLI command inventory schemaVersion must equal 1")
    if inventory.get("version") != version:
        failures.append("CLI command inventory version does not equal VERSION")
    if inventory.get("binarySha256") != expected_binary_sha:
        failures.append(
            "CLI command inventory binarySha256 does not match analysis/version.json"
        )

    source = inventory.get("source")
    if not isinstance(source, dict):
        failures.append("CLI command inventory source metadata is missing")
        source = {}
    readable_relative = source.get("path")
    if readable_relative != "reverse/javascript/cli.readable.js":
        failures.append("CLI command inventory readable-JS path is incorrect")
    readable_path = repo / "reverse/javascript/cli.readable.js"
    readable_text = ""
    readable_line_count = 0
    registration_specs: list[str] = []
    if not readable_path.is_file():
        failures.append("CLI command inventory readable-JS source is missing")
    else:
        readable_text = readable_path.read_text(encoding="utf-8")
        readable_line_count = readable_text.count("\n") + 1
        if source.get("sha256") != sha256(readable_path):
            failures.append("CLI command inventory readable-JS hash is stale")
        registration_specs = re.findall(r'\.command\("([^"]+)"', readable_text)

    recorded_specs = source.get("explicitCommanderRegistrationSpecs")
    if not isinstance(recorded_specs, list) or not all(
        isinstance(spec, str) and spec for spec in recorded_specs
    ):
        failures.append("CLI command inventory registration specs are invalid")
        recorded_specs = []
    if source.get("explicitCommanderRegistrationCount") != 59:
        failures.append("CLI command inventory must record 59 Commander registrations")
    if len(recorded_specs) != 59:
        failures.append("CLI command inventory must contain 59 registration specs")
    if len(registration_specs) != 59:
        failures.append(
            f"readable JS has {len(registration_specs)} explicit Commander registrations; expected 59"
        )
    if registration_specs and recorded_specs != registration_specs:
        failures.append(
            "CLI command inventory registration specs differ from readable JavaScript"
        )

    counts = inventory.get("counts")
    if not isinstance(counts, dict):
        failures.append("CLI command inventory counts are missing")
        counts = {}
    expected_counts = {
        "commandRows": 90,
        "commanderRows": 60,
        "manualFastPathRows": 30,
        "internalEntrypoints": 8,
        "exactBinaryHelpCases": 65,
    }
    for field, expected in expected_counts.items():
        if counts.get(field) != expected:
            failures.append(
                f"CLI command inventory count {field} is {counts.get(field)!r}; "
                f"expected {expected}"
            )
    if counts.get("commanderRows", 0) + counts.get("manualFastPathRows", 0) != 90:
        failures.append("CLI command inventory parser row counts do not sum to 90")

    families = inventory.get("families")
    if not isinstance(families, dict) or not families:
        failures.append("CLI command inventory families are missing")
        families = {}
    commands = inventory.get("commands")
    if not isinstance(commands, list):
        failures.append("CLI command inventory commands must be a list")
        commands = []
    if len(commands) != 90:
        failures.append(f"CLI command inventory has {len(commands)} rows; expected 90")

    command_paths: list[str] = []
    command_by_path: dict[str, dict] = {}
    required_text_fields = (
        "path",
        "family",
        "parser",
        "visibility",
        "gate",
        "syntax",
        "handlerOwner",
        "sideEffects",
        "failureBehavior",
    )
    required_list_fields = (
        "aliases",
        "arguments",
        "observedOptions",
        "hiddenOrStaticOptions",
        "observedChildren",
    )
    for index, row in enumerate(commands, 1):
        if not isinstance(row, dict):
            failures.append(f"CLI command inventory row {index} is not an object")
            continue
        path = row.get("path")
        if isinstance(path, str) and path:
            command_paths.append(path)
            command_by_path.setdefault(path, row)
        for field in required_text_fields:
            if not isinstance(row.get(field), str) or not row[field]:
                failures.append(
                    f"CLI command inventory row {index} has invalid {field}"
                )
        for field in required_list_fields:
            value = row.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item for item in value
            ):
                failures.append(
                    f"CLI command inventory row {index} has invalid {field}"
                )
        aliases = row.get("aliases")
        if isinstance(aliases, list) and len(set(aliases)) != len(aliases):
            failures.append(f"CLI command inventory row {index} has duplicate aliases")

        family = families.get(row.get("family"))
        if not isinstance(family, dict):
            failures.append(f"CLI command inventory row {index} has unknown family")
        else:
            expected_family_fields = {
                "handlerOwner": "owner",
                "sideEffects": "sideEffects",
                "failureBehavior": "failure",
            }
            for row_field, family_field in expected_family_fields.items():
                if row.get(row_field) != family.get(family_field):
                    failures.append(
                        f"CLI command inventory row {index} {row_field} "
                        "does not match its family contract"
                    )

        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            failures.append(f"CLI command inventory row {index} has invalid evidence")
            continue
        static_evidence = evidence.get("static")
        match = re.fullmatch(
            r"reverse/javascript/cli\.readable\.js:([1-9][0-9]*)",
            str(static_evidence),
        )
        if match is None:
            failures.append(
                f"CLI command inventory row {index} has invalid static evidence"
            )
        elif readable_line_count and int(match.group(1)) > readable_line_count:
            failures.append(
                f"CLI command inventory row {index} static evidence is out of range"
            )
        if not isinstance(evidence.get("limitation"), str) or not evidence["limitation"]:
            failures.append(
                f"CLI command inventory row {index} has no evidence limitation"
            )
        if evidence.get("probeCase") is not None and not isinstance(
            evidence.get("probeCase"), str
        ):
            failures.append(
                f"CLI command inventory row {index} has invalid probeCase"
            )

    if len(set(command_paths)) != 90:
        failures.append(
            f"CLI command inventory has {len(set(command_paths))} unique command paths; "
            "expected 90"
        )

    required_command_paths = {
        "claude mcp xaa",
        "claude mcp xaa setup",
        "claude mcp xaa login",
        "claude mcp xaa show",
        "claude mcp xaa clear",
        "claude remote-control",
        "claude daemon",
        "claude daemon run",
        "claude daemon status",
        "claude daemon logs",
        "claude daemon install",
        "claude daemon start",
        "claude daemon restart",
        "claude daemon uninstall",
        "claude daemon stop",
        "claude daemon list",
        "claude daemon scheduled",
        "claude daemon scheduled add",
        "claude daemon scheduled remove",
        "claude daemon scheduled list",
        "claude daemon remote-control",
        "claude daemon remote-control add",
        "claude daemon remote-control remove",
        "claude daemon remote-control list",
        "claude daemon hub",
        "claude self-hosted-runner",
        "claude self-hosted-runner orchestrator",
        "claude self-hosted-runner setup",
        "claude self-hosted-runner doctor",
        "claude self-hosted-runner code-sign",
        "claude self-hosted-runner decode-token",
        "claude logs",
        "claude attach",
        "claude stop",
        "claude respawn",
        "claude rm",
    }
    missing_commands = sorted(required_command_paths - set(command_paths))
    if missing_commands:
        failures.append(
            "CLI command inventory misses gated/manual command paths: "
            + ", ".join(missing_commands)
        )
    required_aliases = {
        "claude remote-control": {"rc", "remote", "sync", "bridge"},
        "claude daemon logs": {"log"},
        "claude stop": {"kill"},
    }
    for path, aliases in required_aliases.items():
        actual = set(command_by_path.get(path, {}).get("aliases", []))
        if not aliases.issubset(actual):
            failures.append(
                f"CLI command inventory aliases are incomplete for {path}: "
                f"missing={sorted(aliases - actual)}"
            )

    internal = inventory.get("internalEntrypoints")
    if not isinstance(internal, list):
        failures.append("CLI command inventory internalEntrypoints must be a list")
        internal = []
    if len(internal) != 8:
        failures.append(
            f"CLI command inventory has {len(internal)} internal entrypoints; expected 8"
        )
    internal_argvs: list[str] = []
    for index, entry in enumerate(internal, 1):
        if not isinstance(entry, dict):
            failures.append(f"CLI internal entrypoint {index} is not an object")
            continue
        for field in (
            "argv",
            "visibility",
            "owner",
            "source",
            "handlerSource",
            "inputProtocol",
            "successState",
            "failureBoundary",
            "externalSideEffects",
        ):
            if not isinstance(entry.get(field), str) or not entry[field]:
                failures.append(f"CLI internal entrypoint {index} has invalid {field}")
        lifecycle = entry.get("orderedLifecycle")
        if (
            not isinstance(lifecycle, list)
            or len(lifecycle) < 3
            or not all(isinstance(step, str) and step for step in lifecycle)
        ):
            failures.append(
                f"CLI internal entrypoint {index} has invalid orderedLifecycle"
            )
        if entry.get("visibility") != "internal":
            failures.append(f"CLI internal entrypoint {index} is not marked internal")
        argv = entry.get("argv")
        if isinstance(argv, str) and argv:
            internal_argvs.append(argv)
        for source_field in ("source", "handlerSource"):
            source_match = re.fullmatch(
                r"reverse/javascript/cli\.readable\.js:([1-9][0-9]*)",
                str(entry.get(source_field)),
            )
            if source_match is None:
                failures.append(
                    f"CLI internal entrypoint {index} has invalid {source_field}"
                )
            elif readable_line_count and int(source_match.group(1)) > readable_line_count:
                failures.append(
                    f"CLI internal entrypoint {index} {source_field} is out of range"
                )
    required_internal_argvs = {
        "--handle-uri <uri>",
        "--claude-in-chrome-mcp",
        "--chrome-native-host",
        "--computer-use-mcp",
        "--daemon-worker <kind>",
        "--bg-pty-host",
        "--bg-spare",
        "--preload",
    }
    if set(internal_argvs) != required_internal_argvs:
        failures.append(
            "CLI internal entrypoint coverage mismatch: "
            f"missing={sorted(required_internal_argvs - set(internal_argvs))}, "
            f"extra={sorted(set(internal_argvs) - required_internal_argvs)}"
        )
    if len(set(internal_argvs)) != len(internal_argvs):
        failures.append("CLI command inventory has duplicate internal entrypoints")

    if probe.get("schemaVersion") != 1:
        failures.append("CLI command-tree probe schemaVersion must equal 1")
    target = probe.get("target")
    if not isinstance(target, dict):
        failures.append("CLI command-tree probe target is missing")
        target = {}
    if target.get("version") != version:
        failures.append("CLI command-tree probe target version does not equal VERSION")
    if target.get("binarySha256") != expected_binary_sha:
        failures.append(
            "CLI command-tree probe binarySha256 does not match analysis/version.json"
        )
    if probe.get("pass") is not True:
        failures.append("CLI command-tree probe did not pass")
    required_probe_checks = {
        "exactVersion",
        "exactBinarySha256",
        "explicitCommanderRegistrationCount59",
        "allHelpCasesExitZeroWithExpectedUsage",
        "nonexistentStatusFallsBackToRootAtExitZero",
        "remoteControlFastPathPreemptsCommanderHelp",
        "codeSignIsHelperNotHelpCommand",
        "everyCommandHasOwnerSideEffectsAndFailure",
    }
    probe_checks = probe.get("checks")
    if not isinstance(probe_checks, dict):
        failures.append("CLI command-tree probe checks are missing")
        probe_checks = {}
    missing_checks = sorted(required_probe_checks - set(probe_checks))
    if missing_checks:
        failures.append(
            "CLI command-tree probe misses required checks: " + ", ".join(missing_checks)
        )
    failed_checks = sorted(
        name for name, value in probe_checks.items() if value is not True
    )
    if failed_checks:
        failures.append(
            "CLI command-tree probe has failed checks: " + ", ".join(failed_checks)
        )

    observed = probe.get("observed")
    if not isinstance(observed, dict):
        failures.append("CLI command-tree probe observed data is missing")
        observed = {}
    observed_counts = {
        "explicitCommanderRegistrationCount": 59,
        "structuredCommandRows": 90,
        "internalEntrypoints": 8,
    }
    for field, expected in observed_counts.items():
        if observed.get(field) != expected:
            failures.append(
                f"CLI command-tree probe observed {field} is {observed.get(field)!r}; "
                f"expected {expected}"
            )

    help_cases = observed.get("helpCases")
    if not isinstance(help_cases, list):
        failures.append("CLI command-tree probe helpCases must be a list")
        help_cases = []
    if len(help_cases) != 65:
        failures.append(
            f"CLI command-tree probe has {len(help_cases)} help cases; expected 65"
        )
    probe_input = probe.get("input")
    if not isinstance(probe_input, dict):
        failures.append("CLI command-tree probe input is missing")
        probe_input = {}
    if probe_input.get("helpCases") != 65:
        failures.append("CLI command-tree probe input.helpCases must equal 65")
    help_ids: list[str] = []
    help_commands: list[str] = []
    expected_exit_statuses: dict[str, int] = {}
    for index, case in enumerate(help_cases, 1):
        if not isinstance(case, dict):
            failures.append(f"CLI command-tree help case {index} is not an object")
            continue
        case_id = case.get("id")
        command = case.get("command")
        if not isinstance(case_id, str) or not case_id:
            failures.append(f"CLI command-tree help case {index} has invalid id")
        else:
            help_ids.append(case_id)
        if not isinstance(command, str) or not command:
            failures.append(f"CLI command-tree help case {index} has invalid command")
        else:
            help_commands.append(command)
            row = command_by_path.get(command)
            if row is None:
                failures.append(
                    f"CLI command-tree help case {case_id!r} has no inventory row"
                )
            else:
                row_evidence = row.get("evidence")
                paired_probe = (
                    row_evidence.get("probeCase")
                    if isinstance(row_evidence, dict)
                    else None
                )
                if paired_probe != case_id:
                    failures.append(
                        f"CLI command-tree help case {case_id!r} is not paired to its inventory row"
                    )
        if not isinstance(case.get("argv"), str) or not case["argv"]:
            failures.append(f"CLI command-tree help case {index} has invalid argv")
        if not isinstance(case.get("input"), dict) or not case["input"]:
            failures.append(f"CLI command-tree help case {index} has invalid input")
        literal_output = case.get("literalOutput")
        if not isinstance(literal_output, dict) or not all(
            isinstance(literal_output.get(stream), str) for stream in ("stdout", "stderr")
        ):
            failures.append(
                f"CLI command-tree help case {index} has invalid literalOutput"
            )
        else:
            for stream in ("stdout", "stderr"):
                actual_hash = hashlib.sha256(
                    literal_output[stream].encode("utf-8")
                ).hexdigest()
                if case.get(f"{stream}Sha256") != actual_hash:
                    failures.append(
                        f"CLI command-tree help case {index} has stale {stream} hash"
                    )
        if case.get("exitStatus") != 0:
            failures.append(f"CLI command-tree help case {index} did not exit zero")
        elif isinstance(case_id, str) and case_id:
            expected_exit_statuses[case_id] = 0
        if case.get("timedOut") is not False or case.get("signal") is not None:
            failures.append(
                f"CLI command-tree help case {index} timed out or received a signal"
            )
        parsed = case.get("parsed")
        if not isinstance(parsed, dict) or not isinstance(parsed.get("usage"), str):
            failures.append(f"CLI command-tree help case {index} has invalid parsed usage")
        case_checks = case.get("checks")
        if not isinstance(case_checks, dict) or not case_checks or not all(
            value is True for value in case_checks.values()
        ):
            failures.append(f"CLI command-tree help case {index} has failed checks")

    if len(set(help_ids)) != 65:
        failures.append(
            f"CLI command-tree probe has {len(set(help_ids))} unique help IDs; expected 65"
        )
    if len(set(help_commands)) != 65:
        failures.append(
            "CLI command-tree probe help command paths are not unique and complete"
        )
    probe_exit_status = probe.get("exitStatus")
    if not isinstance(probe_exit_status, dict):
        failures.append("CLI command-tree probe exitStatus is missing")
        probe_exit_status = {}
    recorded_exit_statuses = probe_exit_status.get("helpCases")
    if recorded_exit_statuses != expected_exit_statuses:
        failures.append("CLI command-tree probe help-case exit status index is stale")

    return len(commands), len(help_cases)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def format_count(value: int) -> str:
    return f"{value:,}"


def validate_human_snapshot_identity(
    repo: Path, version: str, metadata: dict, failures: list[str]
) -> None:
    readme = (repo / "README.md").read_text(encoding="utf-8")
    expected_title = f"# Claude Code CLI {version} 深度逆向快照"
    if readme.splitlines()[0] != expected_title:
        failures.append("README title does not match VERSION")

    binary_sha = metadata.get("binary", {}).get("sha256")
    readme_sha = re.search(
        r"^\| 原始程序 SHA-256 \| `([0-9a-f]{64})` \|$", readme, re.MULTILINE
    )
    if readme_sha is None or readme_sha.group(1) != binary_sha:
        failures.append("README binary SHA-256 does not match analysis/version.json")

    for relative in HUMAN_ANALYSIS_DOCS:
        path = repo / relative
        if not path.is_file():
            continue
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        if version not in first_line:
            failures.append(
                f"human analysis document title does not match VERSION: {relative}"
            )

    risk_surface_path = repo / "analysis/risk-control-surface.txt"
    if risk_surface_path.is_file():
        risk_surface = risk_surface_path.read_text(encoding="utf-8")
        if f"# Version: {version}" not in risk_surface.splitlines()[:3]:
            failures.append("risk-control surface version does not match VERSION")

    probe_placeholder_paths = {"README.md", *HUMAN_ANALYSIS_DOCS}
    versioned_probe = re.compile(r"\$CLAUDE_\d+_\d+_\d+")
    for relative in sorted(probe_placeholder_paths):
        path = repo / relative
        if path.is_file() and versioned_probe.search(path.read_text(encoding="utf-8")):
            failures.append(
                f"version-specific Claude binary placeholder found in {relative}; use $CLAUDE_TARGET"
            )


def validate_reader_first_analysis(repo: Path, failures: list[str]) -> None:
    for relative, visual_stem in READER_FIRST_ANALYSIS_DOCS.items():
        path = repo / relative
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        first_screen = content[:7000]
        required_markers = {
            "60-second section": "## 60 秒",
            "reader question": "**读者问题：**",
            "mental model": "**一句话模型：**",
            "scenario": "场景",
            "state table": "| --- |",
            "lifecycle image": f"](visuals/{visual_stem}.svg)",
        }
        for label, marker in required_markers.items():
            if marker not in first_screen:
                failures.append(
                    f"reader-first human document is missing {label}: {relative}"
                )

        dot_path = repo / f"analysis/visuals/{visual_stem}.dot"
        svg_path = repo / f"analysis/visuals/{visual_stem}.svg"
        if not dot_path.is_file():
            failures.append(f"reader-first visual source is missing: {dot_path.relative_to(repo)}")
        else:
            dot = dot_path.read_text(encoding="utf-8")
            if "digraph " not in dot or not re.search(r"->.*\[label=", dot):
                failures.append(
                    f"reader-first visual source lacks labeled state transitions: "
                    f"{dot_path.relative_to(repo)}"
                )
        if not svg_path.is_file():
            failures.append(f"reader-first rendered visual is missing: {svg_path.relative_to(repo)}")
        elif "<svg" not in svg_path.read_text(encoding="utf-8"):
            failures.append(
                f"reader-first rendered visual is invalid: {svg_path.relative_to(repo)}"
            )


def markdown_h2_section(content: str, heading_pattern: str) -> str | None:
    heading = re.search(
        rf"^(##|###)\s+(?:{heading_pattern})[^\n]*$",
        content,
        re.MULTILINE | re.IGNORECASE,
    )
    if heading is None:
        return None
    level = len(heading.group(1))
    following = re.search(
        rf"^#{{1,{level}}}\s+",
        content[heading.end() :],
        re.MULTILINE,
    )
    end = len(content) if following is None else heading.end() + following.start()
    return content[heading.start() : end]


def numbered_phase_lifecycle(
    content: str,
    phase_pattern: str,
    heading_level: int = 2,
) -> tuple[str | None, list[int]]:
    matches = list(
        re.finditer(
            rf"^#{{{heading_level}}}\s+(?:{phase_pattern})[^\n]*$",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
    )
    if not matches:
        return None, []
    phase_numbers = [int(match.group(1)) for match in matches]
    following = re.search(
        rf"^#{{1,{heading_level}}}\s+",
        content[matches[-1].end() :],
        re.MULTILINE,
    )
    end = (
        len(content)
        if following is None
        else matches[-1].end() + following.start()
    )
    return content[matches[0].start() : end], phase_numbers


def validate_topic_visual(
    repo: Path,
    topic: str,
    contract: dict,
    failures: list[str],
) -> None:
    visual_stem = contract["visual_stem"]
    dot_path = repo / f"analysis/visuals/{visual_stem}.dot"
    svg_path = repo / f"analysis/visuals/{visual_stem}.svg"
    if not dot_path.is_file() or not svg_path.is_file():
        return

    dot = dot_path.read_text(encoding="utf-8")
    dot_nodes = re.findall(
        r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\[\s*label\s*=",
        dot,
        re.MULTILINE,
    )
    dot_edges = re.findall(r"^\s*[^\n]+?->[^\n]+?\[\s*label\s*=", dot, re.MULTILINE)
    if len(dot_nodes) < 6 or len(dot_edges) < 6:
        failures.append(
            f"deep topic visual is too shallow: {topic} "
            f"(nodes={len(dot_nodes)}, labeled_edges={len(dot_edges)})"
        )
    for anchor in contract["visual_anchors"]:
        if anchor not in dot:
            failures.append(f"deep topic visual {topic} is missing state anchor: {anchor}")
    if (
        re.search(r"^\s*digraph\s+[A-Za-z_][A-Za-z0-9_]*\s*\{", dot) is None
        or dot.count("{") != dot.count("}")
        or dot.count('"') % 2 != 0
    ):
        failures.append(f"deep topic visual DOT structure is invalid: {topic}")

    try:
        svg_root = ET.parse(svg_path).getroot()
    except (ET.ParseError, OSError) as error:
        failures.append(f"deep topic rendered visual is invalid XML: {topic}: {error}")
        return
    if not svg_root.tag.endswith("svg") or "viewBox" not in svg_root.attrib:
        failures.append(f"deep topic rendered visual lacks SVG viewport: {topic}")
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    svg_nodes = svg_root.findall(".//svg:g[@class='node']", namespace)
    svg_edges = svg_root.findall(".//svg:g[@class='edge']", namespace)
    if len(svg_nodes) < 6 or len(svg_edges) < 6:
        failures.append(
            f"deep topic rendered visual is too shallow: {topic} "
            f"(nodes={len(svg_nodes)}, edges={len(svg_edges)})"
        )
    svg = svg_path.read_text(encoding="utf-8")
    for anchor in contract["visual_anchors"]:
        if anchor not in svg:
            failures.append(
                f"deep topic rendered visual {topic} is missing state anchor: {anchor}"
            )


def validate_topic_depth_contracts(
    repo: Path,
    completeness_rows: dict[int, list[str]],
    failures: list[str],
) -> None:
    readme = (repo / "README.md").read_text(encoding="utf-8")
    readme_first_screen = readme.split("## 快照信息", 1)[0]
    articles_path = repo / "ARTICLES.md"
    articles = articles_path.read_text(encoding="utf-8") if articles_path.is_file() else ""
    skill_path = repo / "skill/claude-code-version-diff/SKILL.md"
    skill = skill_path.read_text(encoding="utf-8") if skill_path.is_file() else ""

    section_contracts = {
        "state ownership": (r".*(?:状态所有权|状态归属|谁拥有状态).*", 400),
        "ordered lifecycle": (r".*(?:完整调用顺序|完整生命周期|端到端状态机).*", 900),
        "gates and thresholds": (
            r".*(?:Gate|门控).*(?:优先级|阈值)|.*(?:优先级|阈值).*(?:Gate|门控).*",
            600,
        ),
        "failure and recovery": (
            r".*(?:失败|错误).*(?:恢复|回退|重试)|.*(?:恢复|回退|重试).*(?:失败|错误).*",
            500,
        ),
        "user impact": (r".*用户影响.*", 400),
        "evidence": (r".*证据(?:索引|地图|矩阵|与).*", 400),
        "boundary": (r".*(?:Boundary|边界).*", 200),
    }

    for topic, contract in TOPIC_DEPTH_CONTRACTS.items():
        relative = contract["document"]
        path = repo / relative
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        first_screen = content[:7000]

        first_screen_markers = {
            "60-second model": r"^##\s+60\s*秒",
            "reader question": r"\*\*读者问题：\*\*",
            "one-sentence mental model": r"\*\*一句话模型：\*\*",
            "scenario": r"(?:贯穿)?场景[：:]",
            "lifecycle image": re.escape(
                f"](visuals/{contract['visual_stem']}.svg)"
            ),
        }
        for label, pattern in first_screen_markers.items():
            if re.search(pattern, first_screen, re.MULTILINE | re.IGNORECASE) is None:
                failures.append(f"deep topic contract {topic} is missing {label}")

        sections: dict[str, str] = {}
        section_patterns = contract.get("section_patterns", {})
        lifecycle_phase_numbers: list[int] = []
        for label, (default_heading_pattern, minimum_length) in section_contracts.items():
            if label == "ordered lifecycle" and "lifecycle_phase_pattern" in contract:
                section, lifecycle_phase_numbers = numbered_phase_lifecycle(
                    content,
                    contract["lifecycle_phase_pattern"],
                    contract.get("lifecycle_phase_heading_level", 2),
                )
                expected_phases = list(range(1, len(lifecycle_phase_numbers) + 1))
                if lifecycle_phase_numbers and lifecycle_phase_numbers != expected_phases:
                    failures.append(
                        f"deep topic contract {topic} lifecycle phases are not contiguous: "
                        f"{lifecycle_phase_numbers}"
                    )
            else:
                heading_pattern = section_patterns.get(label, default_heading_pattern)
                section = markdown_h2_section(content, heading_pattern)
            if section is None:
                failures.append(f"deep topic contract {topic} is missing {label} section")
                continue
            sections[label] = section
            if len(section) < minimum_length:
                failures.append(
                    f"deep topic contract {topic} has a shallow {label} section "
                    f"({len(section)} < {minimum_length})"
                )

        state_section = sections.get("state ownership", "")
        if state_section and re.search(
            r"^\|[^\n]*(?:谁拥有|owner|所有者|状态归属)[^\n]*\|$",
            state_section,
            re.MULTILINE | re.IGNORECASE,
        ) is None:
            failures.append(f"deep topic contract {topic} lacks an owned-state table")

        lifecycle = sections.get("ordered lifecycle", "")
        if lifecycle:
            numbered_steps = re.findall(r"^\s*\d+\.\s+\S", lifecycle, re.MULTILINE)
            phase_headings = re.findall(
                r"^###\s+(?:阶段\s*)?\d+(?:[：:、.\s])",
                lifecycle,
                re.MULTILINE | re.IGNORECASE,
            )
            table_phase_rows = re.findall(
                r"^\|\s*\d+\s*\|",
                lifecycle,
                re.MULTILINE,
            )
            step_count = max(
                len(numbered_steps),
                len(phase_headings),
                len(table_phase_rows),
                len(lifecycle_phase_numbers),
            )
            if step_count < contract["minimum_lifecycle_steps"]:
                failures.append(
                    f"deep topic contract {topic} ordered lifecycle has {step_count} steps; "
                    f"minimum is {contract['minimum_lifecycle_steps']}"
                )
            search_position = 0
            for label, pattern in contract["lifecycle_anchors"]:
                match = re.search(
                    pattern,
                    lifecycle[search_position:],
                    re.IGNORECASE | re.DOTALL,
                )
                if match is None:
                    failures.append(
                        f"deep topic contract {topic} lifecycle is missing {label}"
                    )
                    continue
                search_position += match.end()

        gates = (
            content
            if contract.get("gate_scope") == "document"
            else sections.get("gates and thresholds", "")
        )
        if gates:
            threshold = re.search(
                r"(?:\d+\s*[-–—]\s*\d+|\d+(?:\.\d+)?\s*"
                r"(?:次|秒|分钟|字符|节点|深度|层|项|个|KiB|MiB|MB|bytes?|tokens?))",
                gates,
                re.IGNORECASE,
            )
            if threshold is None:
                failures.append(f"deep topic contract {topic} lacks an exact threshold")
            for label, pattern in contract["gate_markers"]:
                if re.search(pattern, gates, re.IGNORECASE | re.DOTALL) is None:
                    failures.append(
                        f"deep topic contract {topic} gates are missing {label}"
                    )

        failure_section = sections.get("failure and recovery", "")
        if failure_section:
            for label, pattern in contract["failure_markers"]:
                if re.search(
                    pattern, failure_section, re.IGNORECASE | re.DOTALL
                ) is None:
                    failures.append(
                        f"deep topic contract {topic} failure/recovery is missing {label}"
                    )

        impact = sections.get("user impact", "")
        impact_markers = {
            "token": r"token",
            "cost": r"成本|费用|cost",
            "privacy": r"隐私|privacy",
            "side effects": r"副作用|side effect",
        }
        impact_body = impact.split("\n", 1)[1] if "\n" in impact else ""
        for label, pattern in impact_markers.items():
            if impact and re.search(pattern, impact_body, re.IGNORECASE) is None:
                failures.append(
                    f"deep topic contract {topic} user impact is missing {label}"
                )

        evidence = (
            content
            if contract.get("evidence_scope") == "document"
            else sections.get("evidence", "")
        )
        if evidence:
            source_references = re.findall(
                r"(?:\.\./)?reverse/javascript/cli\.readable\.js"
                r"(?:#L|[:：]\s*)\d+",
                evidence,
                re.IGNORECASE,
            )
            if len(source_references) < contract["minimum_evidence_references"]:
                failures.append(
                    f"deep topic contract {topic} has {len(source_references)} source "
                    f"references; minimum is {contract['minimum_evidence_references']}"
                )
            if "Static" not in evidence:
                failures.append(f"deep topic contract {topic} evidence lacks Static class")

        boundary = sections.get("boundary", "")
        if boundary and re.search(
            r"不能证明|不证明|未验证|不携带|服务端|模型内部|运行时",
            boundary,
        ) is None:
            failures.append(f"deep topic contract {topic} lacks a concrete Boundary")

        if relative not in readme_first_screen:
            failures.append(f"deep topic contract {topic} is not linked from README first screen")
        if relative not in articles:
            failures.append(f"deep topic contract {topic} is not linked from ARTICLES.md")
        if relative not in skill:
            failures.append(f"deep topic contract {topic} is not bound in Skill")

        markers_by_number = contract.get("capability_markers_by_number", {})
        for capability_number in topic_contract_capabilities(contract):
            capability_row = completeness_rows.get(capability_number)
            if capability_row is None:
                failures.append(
                    f"deep topic contract {topic} has no completeness capability "
                    f"{capability_number}"
                )
                continue

            capability_markers = markers_by_number.get(
                capability_number,
                contract.get("capability_markers", ()),
            )
            if not any(
                re.search(pattern, capability_row[1], re.IGNORECASE)
                for pattern in capability_markers
            ):
                failures.append(
                    f"completeness capability {capability_number} does not identify "
                    f"deep topic {topic}"
                )
            if Path(relative).name not in capability_row[3]:
                failures.append(
                    f"completeness capability {capability_number} does not bind "
                    f"deep topic {topic}"
                )
            if capability_row[4] != "Deep":
                failures.append(
                    f"deep topic contract {topic} is not Deep in completeness capability "
                    f"{capability_number}: {capability_row[4]}"
                )

        validate_topic_visual(repo, topic, contract, failures)


def validate_human_inventory_facts(repo: Path, failures: list[str]) -> None:
    summary = json.loads(
        (repo / "analysis/source-inventory/summary.json").read_text(encoding="utf-8")
    )
    counts = summary.get("counts", {})
    surface = (repo / "analysis/source-surface.md").read_text(encoding="utf-8")
    table_rows: dict[str, int] = {}
    for match in re.finditer(
        r"^\| \[([^]]+)\]\(source-inventory/[^)]+\) \| ([0-9,]+) \|",
        surface,
        re.MULTILINE,
    ):
        name = match.group(1)
        if name in table_rows:
            failures.append(f"duplicate human source-surface row: {name}")
            continue
        table_rows[name] = int(match.group(2).replace(",", ""))

    missing = sorted(set(counts) - set(table_rows))
    extra = sorted(set(table_rows) - set(counts))
    if missing or extra:
        failures.append(
            "human source-surface inventory set mismatch: "
            f"missing={missing}, extra={extra}"
        )
    for name, expected in counts.items():
        actual = table_rows.get(name)
        if actual is not None and actual != expected:
            failures.append(
                f"human source-surface count mismatch for {name}: "
                f"{actual} != {expected}"
            )

    readme = (repo / "README.md").read_text(encoding="utf-8")
    readme_rows: dict[str, str] = {}
    for line in readme.splitlines():
        match = re.match(r"^\| ([^|]+?) \| (.+) \|", line)
        if match:
            readme_rows[match.group(1).strip()] = match.group(2)

    roles = summary.get("discoveredSymbols", {}).get("roles", {})
    coverage = summary.get("coverage", {}).get("targetCallsites", {})
    literal_coverage = summary.get("coverage", {}).get("literalOccurrences", {})
    expected_rows = {
        "环境访问": [
            format_count(counts["environment-access-identifiers"]),
            format_count(counts["environment-access-callsites"]),
            format_count(counts["dynamic-process-environment-callsites"]),
            format_count(counts["environment-schema"]),
            format_count(counts["observability-environment-schema"]),
            format_count(counts["observability-environment-defaults"]),
        ],
        "一方遥测": [
            f"`{roles['firstPartyEvent']}` {format_count(coverage['firstPartyEvent']['total'])}",
            f"`{roles['firstPartyEventAsync']}` {format_count(coverage['firstPartyEventAsync']['total'])}",
            format_count(counts["first-party-event-callsites"]),
            format_count(counts["first-party-events"]),
            format_count(counts["first-party-event-fields"]),
        ],
        "第三方观测": [
            f"Datadog allowlist {format_count(counts['datadog-forwarded-events'])}",
            f"tag {format_count(counts['datadog-tag-fields'])}",
            f"删除字段 {format_count(counts['datadog-redacted-fields'])}",
        ],
        "动态观测调用": [
            f"`{roles['otelStructuredEvent']}` {format_count(counts['otel-event-callsites'])}",
            f"feature `{roles['featureValue']}` {format_count(counts['feature-flag-callsites'])}",
            f"GrowthBook `{roles['dynamicConfig']}` {format_count(counts['growthbook-callsites'])}",
        ],
        "Settings/schema": [
            f"根 settings {format_count(counts['root-settings-keys'])}",
            f"{format_count(counts['root-settings-schema'])} 条结构化 schema",
            f"typed env {format_count(counts['environment-schema'])}",
            f"schema property {format_count(counts['schema-property-identifiers'])}",
            f"description {format_count(counts['schema-descriptions'])}",
            f"enum group {format_count(counts['static-enum-groups'])}",
        ],
        "工具与命令": [
            f"built-in tool {format_count(counts['builtin-tool-identifiers'])}",
            f"known-tool catalog {format_count(counts['known-tool-catalog'])}",
            f"named component {format_count(counts['named-component-identifiers'])}",
            f"slash command {format_count(counts['slash-command-identifiers'])}",
        ],
        "协议与 hooks": [
            f"SDK control subtype {format_count(counts['sdk-control-subtypes'])}",
            f"output protocol event {format_count(counts['output-protocol-event-identifiers'])}",
            f"hook event {format_count(counts['hook-events'])}",
        ],
        "模型与 beta": [
            f"完整 model catalog {format_count(counts['model-catalog'])}",
            f"pricing tier {format_count(counts['model-pricing-tiers'])}",
            f"alias {format_count(counts['model-aliases'])}",
            f"model literal {format_count(counts['model-identifiers'])}",
            f"date-suffixed beta/API version {format_count(counts['anthropic-beta-identifiers'])}",
        ],
        "API/runtime": [
            f"API path {format_count(counts['api-paths'])}",
            f"API/path template {format_count(counts['api-path-templates'])}",
            f"HTTP method route {format_count(counts['http-route-identifiers'])}",
            f"runtime require {format_count(counts['runtime-requires'])}",
        ],
        "存储": [
            f"Claude storage namespace {format_count(counts['claude-storage-namespaces'])}",
            f"全 bundle namespace {format_count(counts['storage-namespaces'])}",
            f"用户配置目录名 {format_count(counts['user-config-directories'])}",
        ],
        "错误与诊断": [
            f"调用 {format_count(counts['error-message-callsites'])}",
            f"模板/表达式 {format_count(counts['error-message-templates'])}",
            f"调用 {format_count(counts['diagnostic-message-callsites'])}",
            f"模板/表达式 {format_count(counts['diagnostic-message-templates'])}",
        ],
        "全词法表面": [
            f"quoted string {format_count(literal_coverage['quotedStrings'])}",
            f"{format_count(counts['static-string-literals'])} 个唯一值",
            f"template {format_count(literal_coverage['templates'])}",
            f"{format_count(counts['template-literals'])} 个唯一值",
        ],
        "网络": [
            f"URL {format_count(counts['urls'])}",
            f"URL template {format_count(counts['url-templates'])}",
            f"API/path template {format_count(counts['api-path-templates'])}",
            f"归一化 endpoint host {format_count(counts['endpoint-hosts'])}",
        ],
    }
    for label, fragments in expected_rows.items():
        row = readme_rows.get(label)
        if row is None:
            failures.append(f"README inventory fact row is missing: {label}")
            continue
        for fragment in fragments:
            if fragment not in row:
                failures.append(
                    f"README inventory fact mismatch for {label}: missing {fragment!r}"
                )


def text_between(content: str, start: str, end: str) -> str:
    start_index = content.find(start)
    if start_index < 0:
        return ""
    start_index += len(start)
    end_index = content.find(end, start_index)
    if end_index < 0:
        return ""
    return content[start_index:end_index]


def validate_release_notes(repo: Path, failures: list[str]) -> None:
    path = repo / "analysis/release-notes.md"
    if not path.is_file():
        failures.append("missing pinned upstream release notes")
        return

    content = path.read_text(encoding="utf-8")
    required_metadata = (
        f"Commit：`{RELEASE_NOTES_COMMIT}`",
        "https://raw.githubusercontent.com/anthropics/claude-code/"
        f"{RELEASE_NOTES_COMMIT}/CHANGELOG.md",
        f"SHA-256 `{RELEASE_NOTES_FULL_SHA256}`",
        f"SHA-256 `{RELEASE_NOTES_SECTION_SHA256}`",
        "## 上游原文（19/19）",
        "## 逐项机制回填",
    )
    for marker in required_metadata:
        if marker not in content:
            failures.append(f"release notes missing pinned metadata: {marker}")

    try:
        verbatim = text_between(
            content,
            "## 上游原文（19/19）",
            "## 逐项机制回填",
        )
    except ValueError:
        failures.append("release notes upstream verbatim block is missing")
        return

    item_lines = [line for line in verbatim.splitlines() if line.startswith("- ")]
    if len(item_lines) != 19:
        failures.append(
            f"release notes upstream item count mismatch: {len(item_lines)} != 19"
        )
        return
    item_bytes = ("\n".join(item_lines) + "\n").encode("utf-8")
    if hashlib.sha256(item_bytes).hexdigest() != RELEASE_NOTES_ITEMS_SHA256:
        failures.append("release notes upstream verbatim block mismatch")

    mechanism = text_between(
        content,
        "## 逐项机制回填",
        "## 这 19 条合起来说明了什么",
    )
    mechanism_rows: dict[int, list[str]] = {}
    mechanism_order: list[int] = []
    for line in mechanism.splitlines():
        match = re.match(r"^\|\s*([0-9]+)\s*\|", line)
        if match is None:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        number = int(match.group(1))
        mechanism_order.append(number)
        mechanism_rows[number] = cells
    if mechanism_order != list(range(1, 20)):
        failures.append(
            "release notes mechanism row coverage mismatch: "
            f"expected=1..19, actual={mechanism_order}"
        )
        return

    required_bindings = {
        1: "tui-input-accessibility-media-ide-chrome.md",
        2: "plugins-skills-commands-lsp.md",
        3: "reverse/javascript/cli.readable.js",
        4: "reverse/javascript/cli.readable.js",
        5: "reverse/javascript/cli.readable.js",
        6: "builtin-tools-reference.md",
        7: "tools-permissions-hooks.md",
        8: "tui-input-accessibility-media-ide-chrome.md",
        9: "install-update-doctor-lifecycle.md",
        10: "tui-input-accessibility-media-ide-chrome.md",
        11: "cloud-background-channels.md",
        12: "tui-input-accessibility-media-ide-chrome.md",
        13: "embedded-grep.json",
        14: "context-governance-and-caching.md",
        15: "reverse/javascript/cli.readable.js",
        16: "reverse/javascript/cli.readable.js",
        17: "mcp-agents-background.md",
        18: "cloud-background-channels.md",
        19: "tui-input-accessibility-media-ide-chrome.md",
    }
    for number in range(1, 20):
        cells = mechanism_rows[number]
        if len(cells) != 5:
            failures.append(
                f"release notes mechanism row {number} has {len(cells)} cells; expected 5"
            )
            continue
        for column, minimum in zip(cells[1:4], (12, 12, 8)):
            if len(re.sub(r"[`*_]", "", column)) < minimum:
                failures.append(
                    f"release notes mechanism row {number} has shallow mechanism text"
                )
                break
        evidence = cells[4]
        if "Release" not in evidence:
            failures.append(
                f"release notes mechanism row {number} lacks Release evidence class"
            )
        if not any(level in evidence for level in ("Static", "Probe", "Boundary")):
            failures.append(
                f"release notes mechanism row {number} lacks Static/Probe/Boundary scope"
            )
        binding = required_bindings[number]
        if binding not in evidence:
            failures.append(
                f"release notes mechanism row {number} lacks required binding {binding}"
            )
        semantic_texts = {
            "mechanism": " ".join(cells[1:4]).casefold(),
            "evidence": evidence.casefold(),
        }
        for scope, label, alternatives in RELEASE_NOTES_ROW_SEMANTIC_MARKERS.get(
            number, ()
        ):
            haystack = semantic_texts[scope]
            if not any(marker.casefold() in haystack for marker in alternatives):
                failures.append(
                    f"release notes mechanism row {number} lacks semantic marker "
                    f"{label} in {scope}"
                )


def canonical_claude_storage_namespaces(source: bytes) -> list[str]:
    """Recover the product key-factory set independently of the inventory script."""
    start_match = CLAUDE_STORAGE_FACTORY_START_RE.search(source)
    if start_match is None:
        return []
    end_match = CLAUDE_STORAGE_FACTORY_END_RE.search(source, start_match.start())
    if end_match is None or end_match.start() - start_match.start() > 20000:
        return []
    end = source.find(b"}", end_match.end())
    if end < 0:
        return []
    factory = source[start_match.start() : end + 1]
    return sorted(
        {value.decode("utf-8") for value in CLAUDE_STORAGE_NAMESPACE_RE.findall(factory)}
    )


def report_exact_coverage(
    label: str,
    expected: list[str],
    actual: list[str],
    failures: list[str],
    *,
    require_order: bool = False,
) -> None:
    expected_set = set(expected)
    actual_set = set(actual)
    duplicates = sorted({item for item in actual if actual.count(item) > 1})
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing or extra or duplicates or len(actual) != len(expected):
        failures.append(
            f"human {label} coverage mismatch: expected={len(expected)}, "
            f"actual={len(actual)}, unique={len(actual_set)}, missing={missing}, "
            f"extra={extra}, duplicates={duplicates}"
        )
        return
    if require_order and actual != expected:
        failures.append(f"human {label} coverage order mismatch")


def validate_exhaustive_human_references(repo: Path, failures: list[str]) -> None:
    inventory_dir = repo / "analysis/source-inventory"

    expected_tools = (
        inventory_dir / "builtin-tool-identifiers.txt"
    ).read_text(encoding="utf-8").splitlines()
    tool_doc = (repo / "analysis/builtin-tools-reference.md").read_text(
        encoding="utf-8"
    )
    tool_block = text_between(
        tool_doc,
        "<!-- BUILTIN_TOOL_COVERAGE_BEGIN -->",
        "<!-- BUILTIN_TOOL_COVERAGE_END -->",
    )
    actual_tools = re.findall(r"^\| `([^`]+)` \|", tool_block, re.MULTILINE)
    report_exact_coverage(
        "built-in tool", expected_tools, actual_tools, failures, require_order=True
    )

    tool_registration_path = inventory_dir / "tool-registrations.jsonl"
    tool_registration_doc_path = (
        repo / "analysis/tool-registration-and-host-surfaces.md"
    )
    if tool_registration_path.is_file() and tool_registration_doc_path.is_file():
        try:
            expected_tool_registrations = [
                json.loads(line)["comparisonKey"]
                for line in tool_registration_path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            tool_registration_block = text_between(
                tool_registration_doc_path.read_text(encoding="utf-8"),
                "<!-- TOOL_REGISTRATION_COVERAGE_BEGIN -->",
                "<!-- TOOL_REGISTRATION_COVERAGE_END -->",
            )
        except (json.JSONDecodeError, KeyError, ValueError) as error:
            failures.append(f"tool registration human coverage is invalid: {error}")
        else:
            actual_tool_registrations: list[str] = []
            actual_tool_registration_classes: list[str] = []
            for line in tool_registration_block.splitlines():
                if not line.startswith("| `"):
                    continue
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                if len(cells) < 5:
                    continue
                key_match = re.fullmatch(r"`([^`]+)`", cells[0])
                class_match = re.fullmatch(r"`([^`]+)`", cells[2])
                if key_match is None or class_match is None:
                    continue
                actual_tool_registrations.append(key_match.group(1))
                actual_tool_registration_classes.append(class_match.group(1))
            report_exact_coverage(
                "tool registration",
                expected_tool_registrations,
                actual_tool_registrations,
                failures,
                require_order=True,
            )
            actual_class_counts = Counter(actual_tool_registration_classes)
            if actual_class_counts != Counter(EXPECTED_TOOL_REGISTRATION_CLASSES):
                failures.append(
                    "human tool registration classification mismatch: "
                    f"expected={EXPECTED_TOOL_REGISTRATION_CLASSES}, "
                    f"actual={dict(actual_class_counts)}"
                )

    expected_settings: list[str] = []
    for line in (inventory_dir / "root-settings-schema.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        row = json.loads(line)
        if row.get("kind") == "property":
            expected_settings.append(row["key"])
    settings_doc = (repo / "analysis/settings-reference.md").read_text(
        encoding="utf-8"
    )
    settings_block = text_between(
        settings_doc,
        "<!-- SETTINGS_DIRECT_KEYS_START -->",
        "<!-- SETTINGS_DIRECT_KEYS_END -->",
    )
    actual_settings = re.findall(r"^\d{3} (.+)$", settings_block, re.MULTILINE)
    report_exact_coverage(
        "direct root setting",
        expected_settings,
        actual_settings,
        failures,
        require_order=True,
    )

    protocol_doc = (repo / "analysis/cli-sdk-output-protocol.md").read_text(
        encoding="utf-8"
    )
    expected_sdk = (
        inventory_dir / "sdk-control-subtypes.txt"
    ).read_text(encoding="utf-8").splitlines()
    request_block = text_between(
        protocol_doc,
        "<!-- SDK_CONTROL_REQUESTS_START -->",
        "<!-- SDK_CONTROL_REQUESTS_END -->",
    )
    actual_requests = re.findall(r"^\| `([^`]+)` \|", request_block, re.MULTILINE)
    if (
        len(actual_requests) != 42
        or len(set(actual_requests)) != 42
        or not set(actual_requests).issubset(set(expected_sdk))
    ):
        failures.append(
            "human SDK control-request coverage mismatch: "
            f"expected=42, actual={len(actual_requests)}, unique={len(set(actual_requests))}"
        )

    observation_block = text_between(
        protocol_doc,
        "### 46 个观察型 subtype",
        "## 44 个 Managed Agents event identifier",
    )
    expected_sdk_set = set(expected_sdk)
    actual_observations = sorted(
        set(re.findall(r"`([^`]+)`", observation_block)) & expected_sdk_set
    )
    actual_observations = [item for item in actual_observations if item != "error"]
    if len(actual_observations) != 46:
        failures.append(
            "human SDK observation-subtype coverage mismatch: "
            f"expected=46, actual={len(actual_observations)}"
        )
    combined_sdk = sorted(
        set(actual_requests) | set(actual_observations) | {"success", "error"}
    )
    report_exact_coverage(
        "SDK subtype",
        sorted(expected_sdk),
        combined_sdk,
        failures,
    )

    expected_events = (
        inventory_dir / "output-protocol-event-identifiers.txt"
    ).read_text(encoding="utf-8").splitlines()
    event_block = text_between(
        protocol_doc,
        "## 44 个 Managed Agents event identifier",
        "## 103 个 slash command 的协议归属",
    )
    actual_events = sorted(
        set(re.findall(r"`([^`]+)`", event_block)) & set(expected_events)
    )
    report_exact_coverage(
        "output protocol event", sorted(expected_events), actual_events, failures
    )

    expected_commands = (
        inventory_dir / "slash-command-identifiers.txt"
    ).read_text(encoding="utf-8").splitlines()
    command_block = text_between(
        protocol_doc,
        "## 103 个 slash command 的协议归属",
        "## 失败恢复与诊断顺序",
    )
    actual_commands = sorted(
        set(re.findall(r"`([^`]+)`", command_block)) & set(expected_commands)
    )
    report_exact_coverage(
        "slash-command", sorted(expected_commands), actual_commands, failures
    )

    slash_reference = (repo / "analysis/slash-command-reference.md").read_text(
        encoding="utf-8"
    )
    slash_marker_block = text_between(
        slash_reference,
        "<!-- SLASH_COMMAND_COVERAGE_BEGIN -->",
        "<!-- SLASH_COMMAND_COVERAGE_END -->",
    )
    actual_slash_markers = re.findall(
        r"^\d{3} (.+)$", slash_marker_block, re.MULTILINE
    )
    report_exact_coverage(
        "slash-command reference",
        expected_commands,
        actual_slash_markers,
        failures,
        require_order=True,
    )

    expected_hooks = (
        inventory_dir / "hook-events.txt"
    ).read_text(encoding="utf-8").splitlines()
    hook_reference = (repo / "analysis/hooks-event-reference.md").read_text(
        encoding="utf-8"
    )
    hook_marker_block = text_between(
        hook_reference,
        "<!-- HOOK_EVENT_COVERAGE_BEGIN -->",
        "<!-- HOOK_EVENT_COVERAGE_END -->",
    )
    actual_hook_markers = re.findall(
        r"^<!-- hook-event:([^>]+) -->$", hook_marker_block, re.MULTILINE
    )
    report_exact_coverage(
        "Hook event",
        expected_hooks,
        actual_hook_markers,
        failures,
        require_order=True,
    )

    expected_storage_namespaces = (
        inventory_dir / "claude-storage-namespaces.txt"
    ).read_text(encoding="utf-8").splitlines()
    canonical_storage_namespaces = canonical_claude_storage_namespaces(
        (repo / "extracted/cli.js").read_bytes()
    )
    if not canonical_storage_namespaces:
        failures.append("canonical Claude storage key factory was not found")
    elif expected_storage_namespaces != canonical_storage_namespaces:
        failures.append(
            "Claude storage namespace inventory does not match canonical key factory: "
            f"expected={canonical_storage_namespaces}, actual={expected_storage_namespaces}"
        )
    missing_stream_namespaces = sorted(
        {"transcript", "history", "log"} - set(canonical_storage_namespaces)
    )
    if missing_stream_namespaces:
        failures.append(
            "canonical Claude storage key factory is missing stream namespaces: "
            + ", ".join(missing_stream_namespaces)
        )
    storage_reference = (repo / "analysis/storage-v5-reference.md").read_text(
        encoding="utf-8"
    )
    storage_marker_block = text_between(
        storage_reference,
        "<!-- STORAGE_NAMESPACE_COVERAGE_BEGIN -->",
        "<!-- STORAGE_NAMESPACE_COVERAGE_END -->",
    )
    actual_storage_markers = re.findall(
        r"^<!-- storage-namespace:([^>]+) -->$",
        storage_marker_block,
        re.MULTILINE,
    )
    report_exact_coverage(
        "Claude storage namespace",
        expected_storage_namespaces,
        actual_storage_markers,
        failures,
        require_order=True,
    )


def finish_expected_negative_failure(
    failures: list[str], expected: str | None
) -> bool:
    if expected is None or not any(expected in failure for failure in failures):
        return False
    print("snapshot validation: FAIL")
    for failure in failures:
        print(f"- {failure}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument(
        "--negative-test-fast", action="store_true", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--negative-test-expect", help=argparse.SUPPRESS
    )
    args = parser.parse_args()

    if (
        (args.negative_test_fast or args.negative_test_expect is not None)
        and os.environ.get("CLAUDE_VALIDATOR_NEGATIVE_TEST") != "1"
    ):
        parser.error("negative-test options are reserved for test_validator_negative.py")
    if args.negative_test_expect is not None and not args.negative_test_fast:
        parser.error("--negative-test-expect requires --negative-test-fast")

    repo = Path(args.repo).resolve()
    failures: list[str] = []

    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    branch = git(repo, "branch", "--show-current")
    if branch and branch != version:
        failures.append(f"branch {branch!r} does not equal VERSION {version!r}")

    metadata = json.loads((repo / "analysis/version.json").read_text(encoding="utf-8"))
    if metadata.get("version") != version:
        failures.append("analysis/version.json version does not equal VERSION")
    if metadata.get("branch") != version:
        failures.append("analysis/version.json branch does not equal VERSION")
    for key in ("sourcePath", "entrypointPath"):
        value = metadata.get("binary", {}).get(key, "")
        if not isinstance(value, str) or not value.startswith("$"):
            failures.append(f"analysis/version.json binary.{key} is not symbolic/redacted")

    validate_human_snapshot_identity(repo, version, metadata, failures)
    validate_release_notes(repo, failures)
    if finish_expected_negative_failure(failures, args.negative_test_expect):
        return 1

    readme = (repo / "README.md").read_text(encoding="utf-8")
    readme_first_screen = readme.split("## 快照信息", 1)[0]
    articles_path = repo / "ARTICLES.md"
    if "[技术文章总入口](ARTICLES.md)" not in readme[:3000]:
        failures.append("README first screen does not expose ARTICLES.md")
    if not articles_path.is_file():
        failures.append("missing root technical article index: ARTICLES.md")
    else:
        articles = articles_path.read_text(encoding="utf-8")
        for relative in READER_FIRST_ANALYSIS_DOCS:
            if relative not in articles:
                failures.append(
                    f"ARTICLES.md does not link reader-first document: {relative}"
                )
    for relative, required_terms in HUMAN_ANALYSIS_DOCS.items():
        path = repo / relative
        if not path.is_file():
            failures.append(f"missing human analysis document: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        minimum_length, minimum_headings = HUMAN_ANALYSIS_MINIMUMS.get(
            relative, (1000, 1)
        )
        if len(content) < minimum_length:
            failures.append(f"human analysis document is too small: {relative}")
        heading_count = len(re.findall(r"^#{2,4}\s+\S", content, re.MULTILINE))
        if heading_count < minimum_headings:
            failures.append(
                f"human analysis document has too few sections: {relative} "
                f"({heading_count} < {minimum_headings})"
            )
        for term in required_terms:
            if term not in content:
                failures.append(
                    f"human analysis document {relative} does not cover {term!r}"
                )
        if relative not in readme_first_screen:
            failures.append(
                f"README first screen does not link human analysis document: {relative}"
            )

    if (
        args.negative_test_expect is not None
        and args.negative_test_expect.startswith("product surface")
    ):
        validate_product_surface_map(repo, failures)
        if finish_expected_negative_failure(failures, args.negative_test_expect):
            return 1

    validate_reader_first_analysis(repo, failures)
    if finish_expected_negative_failure(failures, args.negative_test_expect):
        return 1
    cli_command_rows, cli_help_cases = validate_cli_command_tree(
        repo, version, metadata, failures
    )

    private_capture_files = find_private_capture_data(repo)
    if private_capture_files:
        failures.append(
            "private capture data found in publishable files: "
            + ", ".join(private_capture_files)
        )
    if finish_expected_negative_failure(failures, args.negative_test_expect):
        return 1

    if args.negative_test_fast:
        inventory_summary = json.loads(
            (repo / "analysis/source-inventory/summary.json").read_text(
                encoding="utf-8"
            )
        )
        inventory_files = len(inventory_summary.get("files", []))
        validate_tool_registration_inventory(repo, inventory_summary, failures)
    else:
        inventory_files = validate_source_inventory(repo, failures)
    validate_product_surface_map(repo, failures)
    validate_generated_control_references(repo, failures)
    completeness_rows = validate_completeness_closure(repo, failures)
    validate_topic_depth_contracts(repo, completeness_rows, failures)
    if finish_expected_negative_failure(failures, args.negative_test_expect):
        return 1
    validate_human_inventory_facts(repo, failures)
    validate_exhaustive_human_references(repo, failures)
    if finish_expected_negative_failure(failures, args.negative_test_expect):
        return 1
    mechanism_evidence = validate_mechanism_evidence(repo, failures)
    native_behavior_checks = validate_native_reconstruction_report(repo, failures)
    if finish_expected_negative_failure(failures, args.negative_test_expect):
        return 1

    risk_surface = repo / "analysis/risk-control-surface.txt"
    risk_entries = 0
    if not risk_surface.is_file():
        failures.append("missing analysis/risk-control-surface.txt")
    else:
        risk_lines = risk_surface.read_text(encoding="utf-8").splitlines()
        required_sections = {
            "[permission-modes]",
            "[safety-circuit-breakers]",
            "[sandbox-network]",
            "[credential-controls]",
            "[enterprise-governance]",
            "[boundaries]",
        }
        missing_sections = required_sections - set(risk_lines)
        if missing_sections:
            failures.append(
                "risk-control surface missing sections: "
                + ", ".join(sorted(missing_sections))
            )
        risk_entries = sum(
            1
            for line in risk_lines
            if line.strip() and not line.startswith("#") and not line.startswith("[")
        )

    manifest = json.loads(
        (repo / "analysis/unpack-manifest.json").read_text(encoding="utf-8")
    )
    files = manifest.get("files", [])
    checked = 0
    for entry in files:
        packed_path = entry["path"]
        repo_path = repo / "extracted" / ("cli.js" if packed_path == "cli" else packed_path)
        if not repo_path.is_file():
            failures.append(f"missing extracted file: {repo_path.relative_to(repo)}")
            continue
        actual = sha256(repo_path)
        expected = entry.get("sha256Packed") or entry.get("sha256")
        if actual != expected:
            failures.append(
                f"hash mismatch for {repo_path.relative_to(repo)}: {actual} != {expected}"
            )
        checked += 1

    main_source = repo / "extracted/cli.js"
    prefix = main_source.read_bytes()[:64]
    if not prefix.startswith(b"// @bun @bytecode @bun-cjs"):
        failures.append("extracted/cli.js does not have the expected Bun bytecode banner")
    source_bytes = main_source.read_bytes()
    if version.encode("ascii") not in source_bytes:
        failures.append("VERSION string is absent from extracted/cli.js")

    if failures:
        print("snapshot validation: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    reverse = repo / "reverse"
    deep_output = ""
    if reverse.is_dir() and not args.negative_test_fast:
        deep_validator = repo / "skill/claude-code-version-diff/scripts/validate_deep_reverse.py"
        if not deep_validator.is_file():
            print("snapshot validation: FAIL")
            print("- reverse directory exists but deep reverse validator is missing")
            return 1
        process = subprocess.run(
            [sys.executable, str(deep_validator), str(repo)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deep_output = process.stdout.strip()
        if process.returncode != 0:
            print("snapshot validation: FAIL")
            print(deep_output)
            return process.returncode

    print(f"snapshot validation: PASS")
    print(f"version: {version}")
    print(f"branch: {branch}")
    print(f"files checked: {checked}")
    print(f"risk controls checked: {risk_entries}")
    print(f"source inventory files checked: {inventory_files}")
    print(f"CLI command rows checked: {cli_command_rows}")
    print(f"CLI exact-binary help cases checked: {cli_help_cases}")
    print(f"mechanism evidence records checked: {mechanism_evidence}")
    print(f"native behavior checks recorded: {native_behavior_checks}")
    print("capture path privacy: PASS")
    print(f"main source sha256: {sha256(main_source)}")
    if deep_output:
        print(deep_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
