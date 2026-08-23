#!/usr/bin/env python3
"""Build the human-readable ownership map for every source inventory file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


VERSION_CONTRACTS = {
    "2.1.235": {
        "source": "reverse/javascript/cli.readable.js",
        "anchors": [
            ("streaming tool queue", 267124, 267149, "addTool(e, t2)"),
            ("outer Agent Loop", 271491, 272425, "async function* USe(e)"),
            ("client tool dispatch", 272032, 272045, 'wd.type === "tool_use"'),
            ("precomputed compact hit", 331309, 331345, "d.hit ? Smi"),
            ("microcompaction", 263484, 263519, "function qUa(e, t2)"),
            ("Artifact deploy", 260784, 261090, "/api/frame/deploy/direct"),
            ("resume entry and interrupted-turn repair", 323188, 323443, "async function Bet(e, t2, r2)"),
            ("compact preserved-segment relink", 402483, 402573, "function H$i(e)"),
            ("transcript graph loader", 403569, 403650, "async function C6e(e, t2)"),
            ("first-party telemetry fanout", 90870, 90891, "function Asb(e, t2)"),
            ("OTEL bootstrap", 361612, 361670, "function Rem()"),
            ("native audio wrapper", 362451, 362455, "function M3v(e, t2)"),
            ("server tool stream", 409843, 409906, 'case "server_tool_use"'),
        ],
    },
}


def validate_version_contract(repo: Path, version: str) -> None:
    contract = VERSION_CONTRACTS.get(version)
    if contract is None:
        raise RuntimeError(
            f"no product-surface mechanism contract for {version}; "
            "add target-version anchors and review every hard-coded claim before generating"
        )
    source_path = repo / contract["source"]
    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    for label, start, end, anchor in contract["anchors"]:
        window = "\n".join(source_lines[start - 1 : end])
        if anchor not in window:
            raise RuntimeError(
                f"stale {version} mechanism anchor for {label}: "
                f"{contract['source']}:{start}-{end} missing {anchor!r}"
            )


DOMAIN_META = {
    "request-model-network": {
        "name": "请求、模型与网络地址",
        "question": "哪些值进入 provider/model/header/route 装配，哪些只是 bundle 中出现过的地址？",
        "docs": [
            "models-auth-providers-request.md",
            "api-beta-route-ownership.md",
            "technical-architecture.md",
            "source-surface.md",
        ],
        "boundary": "远端路由、账号 entitlement、服务端实现和 URL 背后的实时内容不在发布物中。",
    },
    "tools-commands-protocol": {
        "name": "工具、命令、Hooks 与协议",
        "question": "哪些是客户端真实注册/dispatch surface，哪些是内嵌 MCP 或兼容标识？",
        "docs": [
            "builtin-tools-reference.md",
            "tool-registration-and-host-surfaces.md",
            "cli-sdk-output-protocol.md",
            "plugins-skills-commands-lsp.md",
            "slash-command-reference.md",
            "hooks-event-reference.md",
            "artifact-watch-comment-autoreact.md",
            "cli-startup-files-plugins-deeplinks.md",
            "complex-slash-command-lifecycles.md",
        ],
        "boundary": "第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。",
    },
    "settings-environment-policy": {
        "name": "Settings、环境变量与 Policy",
        "question": "哪些字段有 typed schema/consumer，哪些名字只来自广义环境或 schema 字符串？",
        "docs": [
            "settings-reference.md",
            "environment-variable-reference.md",
            "settings-feature-flags-policy.md",
            "inventory-field-guide.md",
        ],
        "boundary": "运行时文件、管理员下发值、环境值和远端 policy payload 不包含在固定 bundle 中。",
    },
    "telemetry-feature": {
        "name": "遥测、诊断出口与 Feature Evaluation",
        "question": "事件从哪里产生、走哪条 transport、哪些字段会被采样/脱敏，哪些只是依赖 schema？",
        "docs": [
            "telemetry.md",
            "telemetry-event-catalog.md",
            "feature-flags-remote-config.md",
            "feature-flag-reference.md",
            "public-claims-validation.md",
        ],
        "boundary": "服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。",
    },
    "diagnostics-errors": {
        "name": "错误、诊断与恢复线索",
        "question": "错误文本由哪个 consumer/状态机产生，还是仅作为词法证据存在？",
        "docs": [
            "error-diagnostic-atlas.md",
            "resilience-and-recovery.md",
            "install-update-doctor-lifecycle.md",
            "inventory-field-guide.md",
        ],
        "boundary": "文本出现不能单独证明分支可达、错误分类正确或恢复成功。",
    },
    "storage-runtime": {
        "name": "Storage namespace 与运行依赖",
        "question": "哪些 key 有一方 typed consumer，哪些 namespace/require 来自依赖或可选 runtime？",
        "docs": [
            "storage-v5-reference.md",
            "insights-history-analysis-pipeline.md",
            "native-bridge-runtime.md",
            "source-surface.md",
        ],
        "boundary": "adapter、外部进程和平台依赖是否真实可用需要运行或环境证据。",
    },
    "lexical-evidence": {
        "name": "完整词法证据底座",
        "question": "怎样证明没有因为动态表达式、模板或长字符串而漏检候选证据？",
        "docs": [
            "inventory-field-guide.md",
            "source-surface.md",
            "completeness-audit.md",
        ],
        "boundary": "词法完整不等于产品归属或运行可达，必须回到 AST consumer 和状态机。",
    },
}


MECHANISM_LANES = [
    {
        "id": "C",
        "name": "控制面",
        "owner": "CLI 入口、Settings store、managed policy、workspace trust、环境变量和 Feature Evaluation",
        "decision": "约束 provider、permission mode、能力上限和候选功能；写入配置不等于所有 consumer 已热更新",
        "docs": [
            "settings-resolution-and-reload.md",
            "settings-feature-flags-policy.md",
            "environment-variable-reference.md",
            "feature-flag-reference.md",
        ],
    },
    {
        "id": "Q",
        "name": "请求与上下文面",
        "owner": "model/provider/auth 选择、system/messages、cache、compact、thinking/effort 与请求时 tools[] 装配",
        "decision": "决定某一次 API attempt 真正发送什么；一个用户 turn 可以包含多次 attempt 和多轮模型调用",
        "docs": [
            "models-auth-providers-request.md",
            "context-governance-and-caching.md",
            "technical-architecture.md",
        ],
    },
    {
        "id": "E",
        "name": "本地 Agent Loop 与执行面",
        "owner": "client tool_use parser、工具 registry、Hook、permission/policy、sandbox、tool.call 与 result mapper",
        "decision": "模型提出 client tool_use；客户端决定是否执行、怎样调度，以及如何用同一 tool_use_id 回灌 tool_result。server_tool_use 不进入这条本地管线",
        "docs": [
            "agent-loop.md",
            "tool-registration-and-host-surfaces.md",
            "tools-permissions-hooks.md",
            "cli-sdk-output-protocol.md",
        ],
    },
    {
        "id": "S",
        "name": "本地状态面",
        "owner": "message graph、JSONL transcript、compact boundary、checkpoint、Storage、Memory、后台任务状态、remote ID/reference 与补偿线索",
        "decision": "决定什么能 resume/rewind、什么只能通过引用继续或补偿；它不拥有真实文件、子进程和远端对象",
        "docs": [
            "sessions-checkpoints-memory.md",
            "storage-v5-reference.md",
            "resilience-and-recovery.md",
            "cloud-background-channels.md",
        ],
    },
    {
        "id": "O",
        "name": "观测与诊断面",
        "owner": "first-party analytics、Datadog、OTEL 等事件 sink，以及 debug/profile/doctor 等本地诊断 reader/probe",
        "decision": "解释运行状态但不拥有 retry/fallback/compact/supervisor 的控制决定；关闭一个 exporter 也不等于关闭全部诊断",
        "docs": [
            "error-diagnostic-atlas.md",
            "telemetry.md",
            "telemetry-event-catalog.md",
            "install-update-doctor-lifecycle.md",
        ],
    },
]


FILE_META = {
    "anthropic-beta-identifiers.txt": ("request-model-network", "Product broad surface"),
    "api-path-templates.jsonl": ("request-model-network", "Derived projection"),
    "api-paths.txt": ("request-model-network", "Mixed heuristic"),
    "builtin-tool-identifiers.txt": ("tools-commands-protocol", "Manual reference"),
    "claude-storage-namespaces.txt": ("storage-runtime", "Product structured"),
    "datadog-forwarded-events.txt": ("telemetry-feature", "Product structured"),
    "datadog-redacted-fields.txt": ("telemetry-feature", "Product structured"),
    "datadog-tag-fields.txt": ("telemetry-feature", "Product structured"),
    "diagnostic-message-callsites.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "diagnostic-message-literals.txt": ("diagnostics-errors", "Evidence substrate"),
    "diagnostic-message-templates.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "direct-process-environment-accesses.txt": ("settings-environment-policy", "Derived projection"),
    "dynamic-process-environment-callsites.jsonl": ("settings-environment-policy", "Product callsites"),
    "endpoint-hosts.txt": ("request-model-network", "Mixed heuristic"),
    "environment-access-callsites.jsonl": ("settings-environment-policy", "Product callsites"),
    "environment-access-identifiers.txt": ("settings-environment-policy", "Mixed heuristic"),
    "environment-like-identifiers.txt": ("settings-environment-policy", "Mixed heuristic"),
    "environment-proxy-accesses.txt": ("settings-environment-policy", "Derived projection"),
    "environment-schema.jsonl": ("settings-environment-policy", "Product structured"),
    "error-message-callsites.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "error-message-literals.txt": ("diagnostics-errors", "Evidence substrate"),
    "error-message-templates.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "feature-flag-callsites.jsonl": ("telemetry-feature", "Product callsites"),
    "feature-flags.txt": ("telemetry-feature", "Product structured"),
    "first-party-environment-fields.txt": ("telemetry-feature", "Product structured"),
    "first-party-event-callsites.jsonl": ("telemetry-feature", "Product callsites"),
    "first-party-event-families.tsv": ("telemetry-feature", "Derived projection"),
    "first-party-event-fields.tsv": ("telemetry-feature", "Product structured"),
    "first-party-event-schema-fields.txt": ("telemetry-feature", "Product structured"),
    "first-party-event-templates.txt": ("telemetry-feature", "Product structured"),
    "first-party-events.txt": ("telemetry-feature", "Product structured"),
    "growthbook-callsites.jsonl": ("telemetry-feature", "Product callsites"),
    "growthbook-event-fields.txt": ("telemetry-feature", "Product structured"),
    "growthbook-keys.txt": ("telemetry-feature", "Product structured"),
    "hook-events.txt": ("tools-commands-protocol", "Product structured"),
    "http-route-identifiers.txt": ("request-model-network", "Mixed heuristic"),
    "known-tool-catalog.txt": ("tools-commands-protocol", "Mixed heuristic"),
    "model-aliases.jsonl": ("request-model-network", "Product structured"),
    "model-catalog-metadata.jsonl": ("request-model-network", "Product structured"),
    "model-catalog.jsonl": ("request-model-network", "Product structured"),
    "model-identifiers.txt": ("request-model-network", "Product broad surface"),
    "model-pricing-tiers.jsonl": ("request-model-network", "Product structured"),
    "named-component-identifiers.txt": ("tools-commands-protocol", "Mixed heuristic"),
    "observability-environment-defaults.jsonl": ("telemetry-feature", "Product structured"),
    "observability-environment-schema.jsonl": ("telemetry-feature", "Product structured"),
    "observability-identifiers.txt": ("telemetry-feature", "Mixed heuristic"),
    "observability-templates.jsonl": ("telemetry-feature", "Evidence substrate"),
    "otel-environment-variables.txt": ("telemetry-feature", "Product broad surface"),
    "otel-event-callsites.jsonl": ("telemetry-feature", "Product callsites"),
    "otel-metrics.tsv": ("telemetry-feature", "Product structured"),
    "otel-spans.txt": ("telemetry-feature", "Product structured"),
    "output-protocol-event-identifiers.txt": ("tools-commands-protocol", "Product structured"),
    "root-settings-keys.txt": ("settings-environment-policy", "Product structured"),
    "root-settings-schema.jsonl": ("settings-environment-policy", "Product structured"),
    "runtime-requires.txt": ("storage-runtime", "Mixed product/dependency"),
    "schema-descriptions.txt": ("settings-environment-policy", "Mixed heuristic"),
    "schema-property-identifiers.txt": ("settings-environment-policy", "Mixed heuristic"),
    "sdk-control-subtypes.txt": ("tools-commands-protocol", "Product structured"),
    "slash-command-identifiers.txt": ("tools-commands-protocol", "Product structured"),
    "static-enum-groups.tsv": ("settings-environment-policy", "Mixed heuristic"),
    "static-string-literals.jsonl": ("lexical-evidence", "Evidence substrate"),
    "storage-namespaces.txt": ("storage-runtime", "Mixed heuristic"),
    "telemetry-endpoints.txt": ("telemetry-feature", "Mixed heuristic"),
    "template-literals.jsonl": ("lexical-evidence", "Evidence substrate"),
    "tengu-identifiers.txt": ("telemetry-feature", "Mixed heuristic"),
    "tool-registrations.jsonl": ("tools-commands-protocol", "Product structured"),
    "third-party-otel-event-fields.tsv": ("telemetry-feature", "Dependency surface"),
    "third-party-otel-events.txt": ("telemetry-feature", "Dependency surface"),
    "url-templates.jsonl": ("request-model-network", "Mixed heuristic"),
    "urls.txt": ("request-model-network", "Mixed heuristic"),
    "user-config-directories.txt": ("settings-environment-policy", "Product broad surface"),
}


CLASS_META = {
    "Product structured": {
        "basis": "结构化 parser 或目标 AST 的静态集合",
        "authority": "集合完整；行为仍需 consumer/状态机",
    },
    "Product callsites": {
        "basis": "Acorn AST 目标调用或 member access",
        "authority": "逐行可定位真实调用点；不自动证明分支运行",
    },
    "Product broad surface": {
        "basis": "一方命名规则或较宽的候选集合",
        "authority": "用于发现入口；必须二次绑定 consumer",
    },
    "Mixed heuristic": {
        "basis": "全 bundle 字符串、模板或命名启发式",
        "authority": "无逐项 consumer 权威；产品、依赖、文档可混合",
    },
    "Dependency surface": {
        "basis": "第三方依赖 schema、事件或 runtime contract",
        "authority": "只在一方 consumer 可达时进入产品结论",
    },
    "Evidence substrate": {
        "basis": "完整词法或目标 AST 证据底座",
        "authority": "用于防漏和定位；不单独证明产品归属",
    },
    "Derived projection": {
        "basis": "从另一份完整 inventory 聚合、筛选或分桶",
        "authority": "投影规则可复现；不是新的 consumer 证据",
    },
    "Manual reference": {
        "basis": "人工维护集合与 bundle 候选的交集",
        "authority": "仅作导航；不能替代注册、装配或 dispatch AST",
    },
    "Mixed product/dependency": {
        "basis": "同一字面量集合同时含一方模块和第三方依赖",
        "authority": "必须逐项区分产品 bridge、平台模块与依赖",
    },
}


FILE_EVIDENCE_OVERRIDES = {
    "api-path-templates.jsonl": {
        "basis": "从全部 template literal 按 API/path 前缀筛选",
        "limitation": "不是 fetch/request AST callsite；模板可来自文档或依赖。",
    },
    "builtin-tool-identifiers.txt": {
        "basis": "人工 builtin allowlist 与 assignment 字符串候选求交集",
        "limitation": "不代表完整工具装配、启用结果或发给模型的 schema。",
    },
    "direct-process-environment-accesses.txt": {
        "basis": "从 bundle 文本提取 process.env 的静态名字集合",
        "limitation": "逐调用点、fallback 和动态下标以 environment-access-callsites.jsonl 为准。",
    },
    "dynamic-process-environment-callsites.jsonl": {
        "limitation": "扫描整个 bundle 的动态 process.env 下标；产品代码与依赖混合，必须继续追 lexical function、caller 和可达性。",
    },
    "environment-access-callsites.jsonl": {
        "limitation": "扫描整个 bundle 的 process.env/env-proxy 访问，包含 @grpc/grpc-js 等依赖；Callsite 为真不等于一方产品归属。",
    },
    "environment-proxy-accesses.txt": {
        "basis": "从已发现环境 proxy 的静态 member 名字求集合",
        "limitation": "集合行没有 consumer 位置；AST 权威文件是 environment-access-callsites.jsonl。",
    },
    "environment-schema.jsonl": {
        "basis": "从已发现 environment builder 恢复 typed declarations",
        "limitation": "builder 同时覆盖一方字段、provider/SDK 字段和依赖声明；typed declaration 不等于一方 ownership 或运行 consumer。",
    },
    "first-party-event-families.tsv": {
        "basis": "按提取器硬编码前缀把 first-party-events.txt 计数分桶",
        "limitation": "未命中项进入 tengu_other；family 是分析投影，不是客户端字段。",
    },
    "runtime-requires.txt": {
        "basis": "枚举 require 字面量，混合一方 .node bridge、Node 平台模块和依赖",
        "limitation": "不能把整份清单统一写成依赖，也不能仅凭 require 证明当前平台加载成功。",
    },
    "otel-environment-variables.txt": {
        "limitation": "从 broad environment union 按 OTEL 前缀筛选，混合客户端接线与 OpenTelemetry SDK 自身变量；须逐项绑定 consumer。",
    },
    "observability-environment-defaults.jsonl": {
        "basis": "从 whole-bundle environment access callsites 按 observability 名称筛选带 fallback 的调用点",
        "limitation": "是真实 callsite 投影，但混合产品和依赖；fallback 存在不证明当前运行值或 exporter 已启用。",
    },
    "observability-environment-schema.jsonl": {
        "basis": "从完整 environment schema 按 observability 名称正则投影",
        "limitation": "底层 declaration 可复核，但投影混合一方、provider 和依赖字段；不能统一标为 Product。",
    },
    "telemetry-endpoints.txt": {
        "basis": "从 urls.txt 按 telemetry/OTEL/Datadog/GrowthBook 关键词筛选",
        "limitation": "包含依赖文档地址和示例 URL；真实出口须绑定 transport consumer。",
    },
}


CLASS_AXES = {
    "Product structured": {
        "origin": "Structured extraction",
        "ownership": "Product",
        "proof": "Structured surface",
    },
    "Product callsites": {
        "origin": "Targeted AST",
        "ownership": "Product",
        "proof": "Callsite",
    },
    "Product broad surface": {
        "origin": "Broad static scan",
        "ownership": "Mixed",
        "proof": "Candidate",
    },
    "Mixed heuristic": {
        "origin": "Heuristic scan",
        "ownership": "Mixed",
        "proof": "Candidate",
    },
    "Dependency surface": {
        "origin": "Dependency schema",
        "ownership": "Dependency",
        "proof": "Declaration",
    },
    "Evidence substrate": {
        "origin": "Lexical/AST substrate",
        "ownership": "Unresolved",
        "proof": "Evidence substrate",
    },
    "Derived projection": {
        "origin": "Derived projection",
        "ownership": "Mixed",
        "proof": "Candidate",
    },
    "Manual reference": {
        "origin": "Manual intersection",
        "ownership": "Mixed",
        "proof": "Candidate",
    },
    "Mixed product/dependency": {
        "origin": "Require literal scan",
        "ownership": "Mixed",
        "proof": "Callsite",
    },
}


FILE_AXIS_OVERRIDES = {
    "api-path-templates.jsonl": {
        "origin": "Template-prefix projection",
    },
    "builtin-tool-identifiers.txt": {
        "origin": "Manual allowlist intersection",
    },
    "direct-process-environment-accesses.txt": {
        "origin": "process.env text projection",
    },
    "dynamic-process-environment-callsites.jsonl": {
        "origin": "Whole-bundle AST",
        "ownership": "Mixed",
        "proof": "Callsite",
    },
    "environment-access-callsites.jsonl": {
        "origin": "Whole-bundle AST",
        "ownership": "Mixed",
        "proof": "Callsite",
    },
    "environment-proxy-accesses.txt": {
        "origin": "Env-proxy projection",
    },
    "environment-schema.jsonl": {
        "origin": "Environment-builder extraction",
        "ownership": "Mixed",
        "proof": "Declaration",
    },
    "first-party-event-families.tsv": {
        "origin": "Prefix bucket projection",
    },
    "otel-environment-variables.txt": {
        "origin": "Prefix-filtered environment union",
        "ownership": "Mixed",
        "proof": "Candidate",
    },
    "observability-environment-defaults.jsonl": {
        "origin": "Observability-filtered environment callsites",
        "ownership": "Mixed",
        "proof": "Callsite",
    },
    "observability-environment-schema.jsonl": {
        "origin": "Observability regex projection",
        "ownership": "Mixed",
        "proof": "Declaration",
    },
    "telemetry-endpoints.txt": {
        "origin": "URL keyword projection",
    },
}


DOMAIN_ROUTE_IDS = {
    "request-model-network": ("Q",),
    "tools-commands-protocol": ("E",),
    "settings-environment-policy": ("C",),
    "telemetry-feature": ("O",),
    "diagnostics-errors": ("S", "O"),
    "storage-runtime": ("S",),
    "lexical-evidence": ("C", "Q", "E", "S", "O"),
}


FILE_ROUTE_OVERRIDES = {
    "anthropic-beta-identifiers.txt": ("C", "Q"),
    "api-path-templates.jsonl": ("Q", "E", "S"),
    "api-paths.txt": ("Q", "E", "S"),
    "builtin-tool-identifiers.txt": ("Q", "E"),
    "dynamic-process-environment-callsites.jsonl": ("C", "Q", "E", "S", "O"),
    "environment-access-callsites.jsonl": ("C", "Q", "E", "S", "O"),
    "feature-flag-callsites.jsonl": ("C",),
    "feature-flags.txt": ("C",),
    "growthbook-callsites.jsonl": ("C",),
    "growthbook-keys.txt": ("C",),
    "http-route-identifiers.txt": ("Q", "E", "S"),
    "known-tool-catalog.txt": ("Q", "E"),
    "model-aliases.jsonl": ("C", "Q"),
    "model-catalog-metadata.jsonl": ("C", "Q"),
    "model-catalog.jsonl": ("C", "Q"),
    "model-identifiers.txt": ("C", "Q"),
    "model-pricing-tiers.jsonl": ("C", "Q", "O"),
    "named-component-identifiers.txt": ("C", "Q", "E", "S", "O"),
    "otel-environment-variables.txt": ("C", "O"),
    "output-protocol-event-identifiers.txt": ("Q", "E", "S", "O"),
    "runtime-requires.txt": ("E", "S", "O"),
    "schema-descriptions.txt": ("C", "E", "S"),
    "sdk-control-subtypes.txt": ("Q", "E", "S"),
    "slash-command-identifiers.txt": ("C", "E", "S"),
    "static-enum-groups.tsv": ("C", "E", "S"),
    "storage-namespaces.txt": ("S", "O"),
    "telemetry-endpoints.txt": ("Q", "O"),
    "tengu-identifiers.txt": ("C", "Q", "E", "S", "O"),
    "tool-registrations.jsonl": ("Q", "E"),
    "url-templates.jsonl": ("Q", "E", "O"),
    "urls.txt": ("Q", "E", "O"),
}


def markdown_link(relative: str) -> str:
    return f"[`{relative}`](source-inventory/{relative})"


def build(repo: Path) -> str:
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    validate_version_contract(repo, version)
    summary_path = repo / "analysis/source-inventory/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    inventory_names = [Path(entry["path"]).name for entry in summary["files"]]
    inventory_count = len(inventory_names)
    expected = set(inventory_names)
    classified = set(FILE_META)
    missing = sorted(expected - classified)
    stale = sorted(classified - expected)
    if missing or stale or len(inventory_names) != len(expected):
        raise RuntimeError(
            f"inventory classification mismatch: missing={missing}, stale={stale}, "
            f"duplicates={len(inventory_names) - len(expected)}"
        )

    required_docs = {
        doc
        for lane in MECHANISM_LANES
        for doc in lane["docs"]
    } | {
        "workflow-artifact-design.md",
        "native-bridge-runtime.md",
        "tui-input-accessibility-media-ide-chrome.md",
        "completeness-audit.md",
    }
    missing_docs = sorted(
        doc for doc in required_docs if not (repo / "analysis" / doc).is_file()
    )
    if missing_docs:
        raise RuntimeError(f"missing routed mechanism documents: {missing_docs}")

    lane_ids = {lane["id"] for lane in MECHANISM_LANES}
    invalid_routes: dict[str, list[str]] = {}
    for name in inventory_names:
        domain, _ = FILE_META[name]
        routes = FILE_ROUTE_OVERRIDES.get(name, DOMAIN_ROUTE_IDS[domain])
        unknown = sorted(set(routes) - lane_ids)
        if not routes or unknown:
            invalid_routes[name] = unknown
    if invalid_routes:
        raise RuntimeError(f"invalid mechanism routes: {invalid_routes}")

    lines = [
        f"# Claude Code CLI {version} 产品运行时：模型提议，本地裁决，状态可续",
        "",
        f"> 版本：`{version}` | 核心客户端路径：`Static` + `Probe` | C/Q/E/S/O：`Derived` 阅读模型 | 服务端内部：`Boundary`",
        "",
        f"**结论：** Claude Code `{version}` 不是把模型输出直接接到 Shell 的聊天壳。它更像一个本地编排内核：客户端按当前配置和会话状态装配每次请求，远端模型提出下一步；本地 runtime 只 dispatch 完整的 client `tool_use`，并在真正调用前执行适用于该工具的 schema、Hook、permission、policy 与 sandbox 控制，再把结果按协议写回消息图。已经落到文件系统、子进程或远端服务的副作用，不会因为重试、`/compact`、resume 或 rewind 自动消失。",
        "",
        "**一句话模型：** 模型负责提议，客户端负责裁决与记账；上下文可以重建，外部世界不能假装回滚。",
        "",
        f"下文的 C/Q/E/S/O 是本文从 `{version}` 调用链归纳出的 **Derived 阅读模型**，不是源码中的五个原生模块，也不是 Anthropic 官方架构名称。它的用途只有一个：追清每个决定由谁拥有、改变了什么状态、失败后谁接管。",
        "",
        "先记住最短图例：`C` 约束能力，`Q` 组装本次请求，`E` 裁决并执行 client tool，`S` 保存可恢复状态，`O` 观察和诊断；真实文件、进程和远端对象仍由外部 owner 持有。",
        "",
        "## 60 秒看懂一次真实任务",
        "",
        "**读者问题：** 用户只说“把端口改掉并跑测试”，为什么 CLI 内部会出现多轮模型请求、并发屏障、权限询问、状态落盘和恢复分支？",
        "",
        "**贯穿场景：** Claude 先读配置，再编辑端口，执行 Bash 测试；测试失败后读取错误继续修复，最后用户执行 `/compact` 再接着工作。",
        "",
        "| 阶段 | 真正作决定的组件 | 输入怎样变成输出 | 技术后果 |",
        "| --- | --- | --- | --- |",
        "| 启动 | 控制面 | 合并 settings、env、managed policy、workspace trust 与 feature evaluation | 配置只确定上限，不等于所有能力已经进入本次请求 |",
        "| 第一次送模 | 请求与上下文面 | 选择 provider/model/auth，构造 system、messages、beta/cache 与本次 `tools[]` | 一个用户 turn 可以包含多次 API attempt 和多轮模型调用 |",
        "| 模型返回 | 流式 parser | 区分文本、client `tool_use`、`server_tool_use`、thinking 与 stop state | 并非所有“工具块”都交给本地执行器 |",
        "| Read/Edit/Bash | 本地 Agent Loop | client `tool_use` 入队，经过 schema、Hook、permission、policy、sandbox，再进入 `tool.call` | 模型提出动作不等于动作已经发生 |",
        "| 测试失败 | 消息图与下一轮请求 | error `tool_result` 按原 `tool_use_id` 回灌，模型把失败当成新观察 | 工具失败通常推进 Agent Loop，不会自动回滚整个 turn |",
        "| `/compact` | compact controller + 本地状态 | 命中预计算就直接交换表示；未命中才生成 summary；随后写 boundary 并重建送模视图 | 历史表示缩短，但文件修改和远端副作用保留 |",
        "| 退出与 resume | session loader + 状态面 | 读取 JSONL、UUID/parent、compact boundary 与 checkpoint，选择有效 leaf 并修复逻辑链 | 对话和受管文件可按各自合同恢复；旧进程与远端动作不会复活或撤销 |",
        "| 诊断 | 各 owner + 观测 sink | retry/fallback/compact/supervisor 各自控制恢复；analytics、Datadog、OTEL、debug 只记录 | 观测缺失不能反推动作未发生，telemetry 也不是恢复控制器 |",
        "",
        "## 关键不是流程很长，而是四个嵌套生命周期单位各算各的账",
        "",
        "![一次用户任务包含模型迭代、API attempt 与工具批次，结果回灌后才决定是否继续](visuals/agent-loop-lifecycle.svg)",
        "",
        f"Agent 系统最容易被讲错的地方，是把一次用户任务、一次模型调用、一次 HTTP 请求和一批工具执行都叫成“一个 turn”。{version} 把这四个嵌套生命周期单位分开，因为它们的重试条件、预算和副作用完全不同。外层 `USe` 收一个用户任务并产出 terminal reason；`tdf` 的循环状态从 `turnCount=1` 开始；同一模型轮次内部还可以进入多个 API attempt；一个 assistant stream 又可以交付多个 client `tool_use` 给 streaming executor。主链见 [L271491-L272425](../reverse/javascript/cli.readable.js#L271491)。",
        "",
        "| 计数单位 | 它从哪里开始、在哪里结束 | 什么会推进它 | 为什么不能和别的单位混用 |",
        "| --- | --- | --- | --- |",
        "| 用户 turn | 用户提交任务，到 CLI 返回一个 terminal reason | 完成、取消、受控停止或硬失败 | 一个用户 turn 内可以有多轮模型和多批工具 |",
        "| 模型 iteration | 组装一次有效上下文并让模型决定下一步 | 工具结果回灌、Stop Hook 重入或显式 continuation | `maxTurns` 限制的是它，不是 HTTP 次数或工具数量 |",
        "| API attempt | 一次具体 provider/model/stream 请求尝试 | transport retry、流转非流、model/refusal fallback | retry 可以重发请求，但不一定增加 `turnCount` |",
        "| Tool batch | 同一 assistant 响应中完成的 client `tool_use` 集合 | block 完整后入队，按并发安全性执行并 drain | 一轮可以执行多个工具；完成顺序不决定结果配对 |",
        "",
        "工具执行也不是等整个 assistant message 完全结束后才开始。流式 parser 在 `content_block_stop` 把一个完成的 block 产出为 assistant fragment（[L409843-L409906](../reverse/javascript/cli.readable.js#L409843)）；Agent Loop 看到其中的 client `tool_use` 就立刻 `addTool(...)`，随后 `Waf(...)` 在模型流事件和 executor 的 drain tick 之间竞速，因此工具 progress/result 可以和后续 assistant blocks 交错上送（[L267292-L267310](../reverse/javascript/cli.readable.js#L267292)、[L272032-L272045](../reverse/javascript/cli.readable.js#L272032)）。流结束后，executor 还会 drain 未完成结果，再由 queue、`endsTurn`、Stop Hook、`maxTurns` 和 terminal reason 决定是继续 model iteration 还是结束。这里的性能收益来自流式重叠，正确性则依赖 block 完整边界、并发屏障和最终 drain，不能简化成一次 `Promise.all`。",
        "",
        "把 `maxTurns=1` 代入贯穿场景就能看清边界：第一轮模型仍可返回 Read、Edit、Bash，三个工具仍按队列规则执行并产生副作用；客户端只是禁止工具结果后的第二轮模型决策，最终给出 `error_max_turns`。精确二进制 Probe 已观察到“工具执行完成、PostToolUse 已发生、服务端只收到一个 Messages 请求”。所以 `maxTurns` 不是工具配额，更不是副作用回滚器；这也是排查“为什么请求次数变多”或“为什么工具做了但没有最终总结”时必须先分清四种计数的原因。完整 Probe 见 [运行证据索引](runtime-probe-index.md) 与 [Agent Loop 专题](agent-loop.md)。",
        "",
        "## 这个版本最鲜明的七个技术特征",
        "",
        "| 技术特征 | 代码层面的机制 | 为什么这样设计 | 用户或调试者真正会感受到什么 |",
        "| --- | --- | --- | --- |",
        "| **生命周期计数分离** | user turn、model iteration、API attempt 与 tool batch 分别拥有推进条件、预算和终止状态 | 网络恢复、模型决策和工具并发不能共享一个粗糙计数器 | `maxTurns=1` 仍可能执行多个工具；API retry 也不必消耗新的模型轮次 |",
        "| **权力分离** | 模型生成意图，本地 client tool pipeline 决定能否执行；`server_tool_use` 走服务端生命周期 | 工作区、凭据和 OS 副作用必须留在本地信任边界内 | 看到工具名、schema 或流式 block 都不能直接等同于本地动作 |",
        "| **请求时晚绑定** | provider、model、beta、cache、system、messages 和 `tools[]` 每次 attempt 重新装配 | host、账号、feature、permission mode 与 Tool Search 会随会话变化 | “源码里有工具”与“这轮模型拿到工具”是两件事 |",
        "| **事件事实与送模视图分离** | transcript/message graph 保存事实；compact、resume、fork、tombstone 构造不同的有效视图 | 上下文窗口有限，但恢复与审计又不能只靠一份有损 summary | `/compact` 改的是下一次请求看到什么，不是把真实副作用擦掉 |",
        "| **按对象恢复** | message graph、transcript、compact boundary、file checkpoint 与 remote reference 分别恢复不同对象 | 对话、文件、进程和远端服务不共享一个快照或事务 owner | resume 可以重建历史，rewind 可以恢复部分文件，但二者都不会自动撤销远端动作 |",
        f"| **先调度、后改写输入** | queue 在最初 schema 成功后计算并发安全；Hook/permission 后续仍可改写 input | 调度器需要在工具真正执行前建立顺序和屏障 | {version} 的 input 改写不会触发重新并发分类，这是扩展作者必须理解的版本合同 |",
        "| **局部恢复、非全局事务** | request retry、stream fallback、compact、supervisor、Artifact conflict 各自处理自己的失败 | 文件、进程、网络与服务端对象不存在统一事务管理器 | 重试前必须判断副作用是否已经发生；“恢复成功”不等于“回到原世界” |",
        "",
        "## 先分清两种工具：client `tool_use` 与 `server_tool_use`",
        "",
        f"这是理解 {version} Agent Loop 的第一道分界。可读源码在 [L272032-L272038](../reverse/javascript/cli.readable.js#L272032) 只把 assistant content 中的 `tool_use` 收集进本地 `streamingToolExecutor`；流式 parser 也认识 `server_tool_use`，例如 Advisor，但它只组装该 block 和对应 server result（[L409843-L409877](../reverse/javascript/cli.readable.js#L409843)）。",
        "",
        "| 对象 | dispatch / 裁决 owner | 真实 effect owner | 是否进入本地 registry / permission / 适用的 policy-sandbox / `tool.call` | 结果怎样回来 |",
        "| --- | --- | --- | --- | --- |",
        "| client `tool_use` | Claude Code 本地 runtime | 内置工具可直接落到 OS；MCP/Plugin/浏览器/远端 API 仍由各自 host 或服务拥有真实副作用 | **是** | 客户端生成同 `tool_use_id` 的 user `tool_result`，再发起后续模型轮次 |",
        "| `server_tool_use` | Anthropic 服务端工具生命周期 | 服务端工具及其后端 | **否** | server result block 留在 assistant stream；客户端可以显示、记录和规范化，但不会本地 dispatch |",
        "",
        "因此，“Agent Loop 会执行所有 tool block”是错误模型。更准确的说法是：本地 Agent Loop 只接管 client `tool_use`；`server_tool_use` 是客户端可观察、但不拥有执行权的服务端分支。",
        "",
        "## 案例一：Bash 的“可调用”不是一个布尔值",
        "",
        "[`known-tool-catalog.txt`](source-inventory/known-tool-catalog.txt) 中出现 `Bash`，最多证明 bundle 里有候选名字。[`tool-registrations.jsonl` 第 80 行](source-inventory/tool-registrations.jsonl#L80)恢复出 `toolRegistration:Bash:1`，并定位到真实工厂对象、schema、permission 和 result mapper。可读源码中的对象位于 [L393203](../reverse/javascript/cli.readable.js#L393203)。这些证据仍不能证明本轮请求把 Bash 发给了模型。",
        "",
        "```text",
        "candidate name",
        "  -> factory registration",
        "  -> host / feature / session gates",
        "  -> alias + dynamic registry merge",
        "  -> Tool Search / deferred schema residency",
        "  -> request-time tools[]",
        "  -> complete client tool_use",
        "  -> queue + schema + Hook + permission + sandbox + tool.call",
        "  -> paired tool_result with the same tool_use_id",
        "```",
        "",
        "### 真正有技术含量的是调度时序",
        "",
        "`addTool()` 先用最初 parsed input 调用 `isConcurrencySafe(input)`，把结果固化在队列项上，再由 `processQueue()` 根据安全项并行、非安全项阻塞后续队列（[L267124-L267149](../reverse/javascript/cli.readable.js#L267124)）。PreToolUse Hook 和 permission handler 后续可以改写 input（[L316220-L316330](../reverse/javascript/cli.readable.js#L316220)），但调度器不会回头重算。",
        "",
        "**版本级细节：** Bash 的 `isConcurrencySafe(original input)` 在 Hook/permission 改写前计算；改写后不会重新计算 `isConcurrencySafe`。这不等于改写后的 input 完全不校验：schema 与 permission 仍会复验；它只说明并发分类沿用最初输入的判断。",
        "",
        "| 机制 | 保证了什么 | 没保证什么 |",
        "| --- | --- | --- |",
        "| safe 项可重叠 | 多个只读或可并发调用不必串行等待 | 不代表所有 Bash 命令都可并发 |",
        "| unsafe 项形成 drain 屏障 | 后面的 Bash 不能越过 Edit 去测试旧文件 | 不代表已经开始的外部副作用能被取消并回滚 |",
        "| 同 ID 配对 | 完成顺序变化时仍能把结果交回正确调用 | 不代表错误结果会终止整个 Agent Loop |",
        "| Hook/permission 可改写 input | 扩展可以在执行前收紧或替换参数 | 不会触发重新并发分类，也不会自动重跑工具自定义 `validateInput` |",
        "",
        "Bash 一旦启动子进程，文件、进程和网络副作用就归 OS 或远端 owner。后续 tombstone、compact、resume 只能修复消息表示和本地记录，不能自动撤销已经执行的命令。完整机制见 [工具注册与宿主表面](tool-registration-and-host-surfaces.md)、[Agent Loop](agent-loop.md) 和 [工具控制管线](tools-permissions-hooks.md)。",
        "",
        "## 案例二：上下文治理不是一个 `/compact` 按钮",
        "",
        "![上下文先复用稳定前缀、延迟工具 schema、局部清理旧结果，最后才全局总结并写恢复边界](visuals/context-control-lifecycle.svg)",
        "",
        "同一个长任务会依次遇到四类不同问题：重复前缀太贵、工具 schema 常驻太大、旧 tool result 挤占窗口、完整历史终于接近有效上限。Claude Code 用不同机制处理它们，不能全部叫成“缓存”或“自动总结”。",
        "",
        "| 机制 | 它真正改变什么 | 它明确不改变什么 |",
        "| --- | --- | --- |",
        "| Prompt cache | 给稳定 system/message 前缀加 breakpoint 与 5m/1h TTL，命中后降低重复输入成本和 prefill 延迟 | 不缩短逻辑消息，也不负责 resume |",
        "| Tool Search / deferred schema | 让未使用工具只保留轻量发现入口，需要时才把完整 schema 放进本次 `tools[]` | 不是工具结果缓存，也不证明某个候选工具本轮可用 |",
        "| Context hint / microcompaction | 在 active message view 中清理旧的大型 tool result，默认保留最近 5 个相关结果，且总节省不足 20k token 时不执行 | 不删除 tool call 因果关系，也不能证明 physical transcript 已删除旧事件 |",
        "| Precomputed compact | 在 sidecar/Storage 中提前准备 summary，等真正到 compact line 再校验并交换 | pending/过期/分支不匹配的 summary 不会硬塞进主历史 |",
        "| Full compact | 用 summary、路径相关的 preserved suffix、attachments 与 Hook 结果重写下一次有效 messages | 不撤销文件、进程、Git 或远端 API 副作用 |",
        "| Transcript + boundary | 保存表示替换关系、UUID 和 logical parent，让 resume 能修复消息链 | 不等于 API prompt cache，也不保存旧进程内存 |",
        "",
        "本地 microcompaction 的 release-local 主路径见 [L263484-L263519](../reverse/javascript/cli.readable.js#L263484)。预计算 sidecar 是 schema version 2，单文件上限 8,000,000 bytes；复用会拒绝超过 7 天、从预计算点又增长超过 150,000 token、缩减过半或关键 UUID 缺失的结果，连续 3 次可计数失败后停止 re-arm。它减少的是临界点上的总结延迟和重复成本，不是把 summary 变成永久真相；校验与 swap 主链见 [L262324-L262680](../reverse/javascript/cli.readable.js#L262324)。完整 5m/1h 成本算例、窗口线与 provider 差异见 [上下文治理专题](context-governance-and-caching.md)。",
        "",
        "### `/compact` 仍然有一条容易漏掉的 hit/miss 分支",
        "",
        "![compact 先检查预计算结果，命中直接重建，未命中才请求 summary](visuals/compact-lifecycle.svg)",
        "",
        f"`/compact` 同时连接命令 gate、PreCompact Hook、预计算 sidecar、group-based compactor、summary request、message graph 和 transcript boundary。把它写成一条固定流水线，会漏掉 {version} 最关键的 hit/miss 分支。",
        "",
        "```text",
        "/compact",
        "  -> command / env / setting gate",
        "  -> PreCompact Hook",
        "  -> lookup precomputed result",
        "       |",
        "       +-- hit  -> 不发送新的 summary request -> Smi finalize",
        "       |          合并预计算 preserve UUID + messagesSince",
        "       |",
        "       +-- miss -> 选择合法 message groups -> summary request",
        "                  prompt-too-long 时缩短待总结前缀并重试",
        "  -> compact_boundary + summary / preserved messages / attachments",
        "  -> rebuild next request view",
        "```",
        "",
        "源码在 [L331309-L331345](../reverse/javascript/cli.readable.js#L331309) 先检查 precomputed result：`hit` 直接进入 `Smi(...)` finalize；custom instructions、Hook 追加、sidecar 未就绪或 boundary UUID 缺失都会形成 miss，再进入普通 compact 路径。普通 full summary 请求与 prompt-too-long 缩减逻辑见 [L262996-L263036](../reverse/javascript/cli.readable.js#L262996)。",
        "",
        "| 状态对象 | compact 前 | compact 后 | 它解决的问题 |",
        "| --- | --- | --- | --- |",
        "| Precomputed compact | sidecar 可能 ready、pending、failed 或不存在 | hit 被交换进主历史；miss 不被采用 | 把总结延迟前移 |",
        "| Effective messages | 长历史直接送模 | summary + 条件性 preserved suffix + attachments/hooks | 释放有效上下文窗口 |",
        "| Physical transcript | 保存旧事件 | 继续追加 boundary 与新事件 | resume/fork 仍能重建逻辑历史 |",
        "| 文件与远端副作用 | 已经发生 | 原样保留 | compact 从来不是事务回滚 |",
        "",
        "精确二进制 Probe 在一个主动执行 `/compact` 的小样本里观察到 `system:compact_boundary`，`trigger=manual`、`preTokens=104`；`104` 只是该受控输入的 compact 前计数，**不是自动 compact 阈值**。随后 fork 的请求保留 summary 和当前 prompt，不再发送 compact 前 prompt、旧 tool-use ID 与旧 assistant result。这证明的是**下一次送模视图改变**，不是旧 transcript、磁盘文件、Memory 或远端副作用被删除。完整阈值和 manual/reactive/precomputed/cold 差异见 [上下文治理](context-governance-and-caching.md)。",
        "",
        "## 案例三：遥测不是一个总开关，而是并行的观测产品",
        "",
        "![同一运行时信号经过关联与内容控制后，分别进入一方事件、Datadog、OTEL 和本地诊断通道](visuals/telemetry-pipeline.svg)",
        "",
        f"“Claude Code 有没有遥测”是一个过于粗糙的问题。{version} 至少要分开 Anthropic 一方事件、Datadog forwarding、用户或管理员配置的 OTEL，以及本地 debug/profile/doctor。它们会观察同一次 query、tool、permission、compact 或 error，但拥有不同 gate、字段、队列、目的地和失败语义。关闭其中一条，不代表其他通道同时关闭。",
        "",
        "先看字段怎样把贯穿场景串起来。`session_id` 标识可恢复会话；`queryChainId/query_chain_id` 把同一次执行链关联起来，`queryDepth/query_depth` 随 model iteration 增加而在同一 iteration 的 API retry 中保持；`request_id` 绑定具体 API 响应尝试；`tool_use_id` 把工具提议和结果配对；`turn_count` 只在需要表达 Agent Loop 轮次的事件中出现。循环状态从 `turnCount=1` 和新的 chain/depth 开始（[L271553-L271643](../reverse/javascript/cli.readable.js#L271553)），终止事件再写 `terminal_reason`，并仅在 max-turns 场景附带 `turn_count`（[L270840-L270845](../reverse/javascript/cli.readable.js#L270840)）。",
        "",
        "| 关联字段 | 它回答的问题 | 为什么仍不能当成完整分布式 trace |",
        "| --- | --- | --- |",
        "| `session_id` | 这条记录属于哪份可 resume 的本地会话 | fork 会产生新 session；远端系统未必沿用同一 ID |",
        "| `queryChainId` / `queryDepth` | 同一用户任务里这是第几次模型决策链 | 事件级 sampling、drop 或某通道关闭会造成缺段 |",
        "| `request_id` | 哪一次具体 API attempt/response 出现延迟、拒绝或 fallback | client retry 前后的 request ID 可以不同；服务端内部 span 不在 bundle 中 |",
        "| `tool_use_id` | 哪个 client tool 提议对应哪个 `tool_result` | MCP/远端 effect owner 可能还有自己的事务 ID |",
        "| `turn_count` | maxTurns 等终止判断发生在第几次 model iteration | 并非每个事件都携带，不能拿事件数反算完整轮次 |",
        "",
        "一方事件入口先按事件名取一次 sampling 结果，再把同一个采样后的 payload 分给可选 Datadog 分支和一方 logger（[L90870-L90891](../reverse/javascript/cli.readable.js#L90870)）。这是一处重要的共享点，但不是两条管道等价：Datadog 随后还要求 first-party provider、feature gate 和 allowlist，并执行自己的字段删除、名称折叠、batch 与 timeout（[L90790-L90868](../reverse/javascript/cli.readable.js#L90790)）；一方 logger 则拥有独立的 pre-init queue 与 batch/queue 配置（[L77977-L78097](../reverse/javascript/cli.readable.js#L77977)），失败 batch 的落盘、重放和 backoff 又由 exporter 自己管理（[L77550-L77944](../reverse/javascript/cli.readable.js#L77550)）。",
        "",
        "| 通道 | 谁决定是否启用 | 内容与可靠性合同 | 不能从它推出什么 |",
        "| --- | --- | --- | --- |",
        "| 一方事件 | provider、nonessential-traffic / telemetry gate、killswitch、sampling | 事件先排队、批量发送，失败 batch 可持久化后重试；记录失败被隔离，不接管 Agent Loop | 某个调用点存在不等于事件一定发出或服务端已经接收、保留 |",
        "| Datadog forwarding | first-party provider + feature + 固定 allowlist | 复用前置 sampling，再做分支专属字段删除、tag 归一化、batch 和 peer rate bound | 26 个删除字段只约束此分支，不是全局隐私合同 |",
        "| 第三方 OTEL | `CLAUDE_CODE_ENABLE_TELEMETRY` + signal-specific exporter/protocol | metrics、logs、traces 分别初始化；prompt、assistant、tool、raw API body 各有内容 gate | 关闭一方事件不自动关闭管理员配置的 OTEL；打开 OTEL 也不等于默认上传 prompt 正文 |",
        "| 本地诊断 | debug/profile/doctor/Perfetto 各自入口 | 写 stderr、本地文件或进程内 profile，生命周期和格式彼此独立 | 本地日志缺失不能证明远端出口未发送，反之亦然 |",
        "",
        "OTEL 本身也不是一个布尔开关。bootstrap 先读取 `CLAUDE_CODE_ENABLE_TELEMETRY`，再分别构造 metrics、logs、traces exporter（[L361612-L361670](../reverse/javascript/cli.readable.js#L361612)）；`OTEL_LOG_USER_PROMPTS` 未开启时，prompt 字段被替换为 `<REDACTED>`（[L93779-L93806](../reverse/javascript/cli.readable.js#L93779)）。精确二进制 Probe 进一步验证了默认 OTLP payload 含 user-prompt event 但正文为 `<REDACTED>`，显式开启后原 marker 才进入 collector。由此可见，出口启用、事件启用和内容启用是三个独立问题。完整 queue、sampling、字段、Probe 与隐私边界见 [遥测专题](telemetry.md) 和 [遥测事件场景索引](telemetry-event-catalog.md)。",
        "",
        "最关键的架构判断是：观测面是有损、分叉、best-effort 的 sink，不是系统事实的唯一账本，更不是 retry/compact/supervisor 的控制器。事件缺失不能证明动作没发生；事件出现也不能证明远端 collector 已确认写入。排障时必须回到真正拥有状态的 request、tool、session 或 recovery controller。",
        "",
        "## 案例四：状态可续，是按对象恢复，不是整机快照",
        "",
        "![消息图和文件检查点分别支持 resume、fork 或 rewind，外部状态留在统一回滚边界之外](visuals/session-recovery-lifecycle.svg)",
        "",
        "继续贯穿场景：Claude 已经编辑配置、启动测试进程并尝试发布 Artifact，用户此时退出 CLI。再次启动时，“继续工作”不是把旧进程冻结后解冻，而是由多个 owner 各自恢复自己掌握的对象。顶层 `Bet(...)` 先解析 resume 来源、Storage/JSONL 路径与 fork 语义，再把消息交给 interrupted-turn 修复器（[L323373-L323423](../reverse/javascript/cli.readable.js#L323373)）；真正的消息图恢复在另一组函数里完成。",
        "",
        "这组恢复算法不是简单地取 JSONL 最后 N 行。`C6e(...)` 把 transcript 事件装入 UUID/parent map，并维护显式 `last-prompt`、leaf、rewind 与 session 元数据（[L403569-L403650](../reverse/javascript/cli.readable.js#L403569)）；`H$i(...)` 检查最近 compact boundary 的 `preservedMessages/preservedSegment`，把保留段重新接回 anchor，并删除不再属于有效表示的 compact 前节点（[L402489-L402531](../reverse/javascript/cli.readable.js#L402489)）；`A_t(...)` 再从选中的 leaf 反向遍历 `parentUuid`，检测环、处理缺失父节点的时间戳 fallback，并补回同一 API message 的并行 assistant/tool-result 片段（[L402554-L402667](../reverse/javascript/cli.readable.js#L402554)）。最后才由顶层 resume 逻辑过滤损坏 attachment、撤回分支和中断残片，构造下一次 Agent Loop 使用的有效消息链。file rewind 则走独立的 checkpoint 路径（[L194641-L194804](../reverse/javascript/cli.readable.js#L194641)）。",
        "",
        "| 可恢复对象 | owner 与恢复动作 | 恢复后的状态 | 仍然丢失或保留什么 |",
        "| --- | --- | --- | --- |",
        "| Message graph | session ID、message UUID、parent/logical parent、branch leaf | resume/fork 得到一条因果合法的有效消息链 | 不会重新执行历史工具，也不恢复旧 socket/Promise |",
        "| Compact boundary | summary、preserved UUID、logical parent 与相关元数据 | compact 前后表示能在同一逻辑会话中接续 | summary 没写到的细节不能凭空恢复；prompt cache 命中也不保证延续 |",
        "| File checkpoint | file history owner 保存受管文件快照/差异；本版最多保留 100 个 checkpoint | dry-run 可先算 diff，rewind 再恢复被跟踪文件字节 | Bash 改的未跟踪路径、symlink 例外、数据库和远端对象不在合同内 |",
        "| Remote reference / result | session 保存 slug、version、task ID、URL 或错误结果 | 后续可以查询、取消、重试或执行补偿动作 | reference 不是分布式事务句柄，不能自动撤销已提交远端效果 |",
        "",
        "精确二进制 Probe 把这两个恢复面分开证明：fork 生成新的 session ID，只带 compact 后的逻辑状态；file rewind 在不发送任何 Messages 请求的情况下，把受管临时文件从修改值恢复为原始字节。它说明 rewind 是本地 checkpoint 驱动的补偿操作，不需要模型生成反向 Edit，也不涵盖 Git push、Artifact 部署、数据库写或已发送消息。完整恢复矩阵见 [Session/Checkpoint/Memory](sessions-checkpoints-memory.md)。",
        "",
        "所以“状态可续”是一个有类型的承诺：消息图续消息，checkpoint 续文件，remote reference 续补偿线索。任何恢复成功报告都必须同时说明恢复了哪个对象，以及哪些外部副作用仍然存在。",
        "",
        "## 案例五：Artifact 发布暴露了“结果未知”与补偿式恢复",
        "",
        "[`api-paths.txt` 第 17 行](source-inventory/api-paths.txt#L17)出现 `/api/frame/deploy/direct`，只说明发布物里有这个 path。把它绑定到 POST consumer、60 秒 timeout、body 上限、auth/header、兼容重试、响应 schema 和本地已知版本更新后，才出现真正的产品语义。",
        "",
        "```text",
        "POST /api/frame/deploy/direct",
        "  -> 400 compatibility relaxation (bounded)",
        "  -> 409 conflict exposes liveVersion",
        "  -> 429 waits and retries once",
        "  -> 503 retries up to 3 total attempts",
        "  -> 2xx response schema validation",
        "  -> target slug equality check",
        "  -> adopt server-returned version and update local known reference",
        "```",
        "",
        "这里必须把四种合同分开。`RBa().safeParse` 校验响应里的 slug/version 形状；客户端只对目标 slug 做 equality check；服务端返回的 version 被直接采用并写入本地 known version，不做 local-version equality；timeout、relay error、malformed response 或 slug mismatch 后的“check the artifact list”只是错误合同里的 **advisory**，不是客户端自动强制执行 list/read gate。证据见 [L260784-L260808](../reverse/javascript/cli.readable.js#L260784) 与 [L261085-L261090](../reverse/javascript/cli.readable.js#L261085)。",
        "",
        "这个案例体现了 Agent runtime 最现实的一面：网络请求失败时，本地可能不知道远端是否已经提交。CLI 能做的是限制重试、暴露 conflict、保留 slug/version/reference 和给出补偿建议，而不是假装拥有跨客户端与远端服务的原子事务。完整 owner 表见 [API/Beta 路由所有权](api-beta-route-ownership.md) 与 [Workflow/Artifact/Design](workflow-artifact-design.md)。",
        "",
        "## 案例六：`audio-capture.node` 要按证据等级拆开讲",
        "",
        "[`runtime-requires.txt` 第 1 行](source-inventory/runtime-requires.txt#L1)记录 `/$bunfs/root/audio-capture.node`，可读 JavaScript 也保留 embedded require（[L54](../reverse/javascript/cli.readable.js#L54)）。这只能证明发布物包含装载入口，不能直接推出当前机器加载成功、麦克风已授权、设备可用或 native 内部采用了某种精确重采样算法。",
        "",
        f"| 结论 | 证据等级 | {version} 能证明什么 |",
        "| --- | --- | --- |",
        "| Rust/CPAL/CoreAudio 与 AVFoundation 授权 | **Observed** | 原生二进制依赖、符号、字符串和反汇编可证 |",
        "| JS native wrapper | **Observed** | `startRecording` callback 收到 bytes 后原样上抛；wrapper 不声明采样率转换（[L362451-L362455](../reverse/javascript/cli.readable.js#L362451)） |",
        "| SoX fallback | **Observed** | 命令参数明确指定 `-r 16000 -e signed -b 16 -c 1`（[L362559-L362580](../reverse/javascript/cli.readable.js#L362559)） |",
        "| Voice WebSocket contract | **Observed** | query 参数声明 `encoding=linear16&sample_rate=16000&channels=1`，音频在连接前可先排队 |",
        "| 原版 native 内部 16 kHz/mono/s16 重采样细节 | **Boundary / 未恢复** | JS 只透传 bytes；当前静态证据不能确认原函数体怎样转换 |",
        "| 重建版 native 的 16 kHz 转换与 buffer policy | **Derived / Compatible** | 为匹配 wire/SoX 消费合同独立实现，测试通过也不升级成原始源码事实 |",
        "",
        "Voice 的完整产品链仍然可以确认：native 或 SoX 产生音频 bytes，客户端在 WebSocket ready 前缓存，之后发送到远端 STT；interim/final transcript 写入 composer，用户提交后才进入普通 Agent Loop。隐私边界也很明确：原始音频离开本地进入 STT，bundle 能证明上传和本地清理路径，不能证明服务端留存、训练或删除策略。详见 [Native Bridge](native-bridge-runtime.md) 与 [TUI/媒体/Voice](tui-input-accessibility-media-ide-chrome.md)。",
        "",
        "## 从六个案例归纳出的五个阅读面",
        "",
        "再次强调：这是 Derived 分析框架，不是源码目录图。它按最终决定权分面，同一功能可以同时跨多个面。恢复也不是统一的第六层：request retry、stream fallback、compact、tool tombstone 与 process supervisor 分别归各自 controller；观测面只接收事件，不反向控制请求。",
        "",
        "![Derived 阅读模型：控制约束请求，本地 Agent Loop 执行 client tool_use，server_tool_use 留在服务端，恢复控制器与观测诊断分离](visuals/product-surface-runtime-planes.svg)",
        "",
        "| ID | Derived 阅读面 | owner 与技术特征 | 关键阅读入口 |",
        "| --- | --- | --- | --- |",
    ]
    for lane in MECHANISM_LANES:
        docs = "、".join(f"[{doc}]({doc})" for doc in lane["docs"])
        lines.append(
            f"| `{lane['id']}` | **{lane['name']}** | {lane['owner']}。{lane['decision']} | {docs} |"
        )

    lines.extend([
        "",
        "外部副作用不属于本地状态面。执行器把动作交给文件系统、子进程、浏览器、MCP、GitHub、Artifact 或其他远端 owner 后，本地最多保存结果、remote ID/reference、checkpoint 与补偿线索。这里不存在一个能同时撤销 transcript、文件和远端对象的全局事务。",
        "",
        "## 读代码时最容易犯的十个归因错误",
        "",
        "| 静态表面 | 错误结论 | 正确的下一步 |",
        "| --- | --- | --- |",
        "| 核心工具参考集合 | 本轮模型一定拿到这些工具 | 查 host/gate/alias/defer 与 request-time `tools[]` |",
        "| 工厂注册调用点 | 默认启用同样数量的工具 | 展开 factory caller、dynamic registry 与 `isEnabled` |",
        "| Feature key | 每个 key 都对应已知用户功能 | 追 lexical consumer、fallback、二次 gate、state delta 与服务端 rollout |",
        "| API path | 客户端一定向该地址发请求 | 绑定 method、caller、base URL、auth、成功/失败合同 |",
        "| 一方事件名 | 每个事件都是稳定上报指标 | 查 payload、sampling、queue、exporter eligibility 与服务端 Boundary |",
        "| Error callsite | 每条错误都有独立恢复策略 | 找 typed classifier、retry budget、partial state 与用户 surface |",
        "| `process.env` AST read | 一定是一方产品逻辑 | whole-bundle AST 同时包含依赖，必须追 caller ownership |",
        "| `.node` require | native 能力已经可用且内部算法已知 | 查 ABI、平台、load、OS permission、设备、Probe 与重建证据等级 |",
        "| `compact_boundary` | 旧历史和文件都删除了 | 区分 physical transcript、effective messages 与外部副作用 |",
        "| telemetry 开关 | 所有记录、诊断和恢复都一起关闭 | 分开 first-party、Datadog、OTEL、debug、error reporting 与各恢复 controller |",
        "",
        "## 从发布物到技术结论：三条证据链",
        "",
        "![从 canonical bytes 到结构化清单、待追 consumer、机制、Probe 与真实 Boundary](visuals/evidence-surface-lifecycle.svg)",
        "",
        "### 配置、环境变量或 Feature key",
        "",
        "`schema/key -> named read -> lexical function -> caller -> secondary gate -> state delta`。只有 schema 时是 declaration；出现 AST callsite 后仍要回答谁读取、fallback 是什么、值怎样进入状态机。客户端 consumer 尚未追完时必须标 `Untraced/Inventory only`。**Untraced/Inventory only 不是 Boundary**：前者是仍可继续做的逆向工作，后者才是发布物确实不携带的服务端值、第三方内部或构建前源码。",
        "",
        "### 工具",
        "",
        "`name candidate -> factory callsite -> factory invocation -> enable/host gate -> request-time tools[] -> client tool_use -> controlled execution -> tool_result`。这条链每一层的统计单位不同；`server_tool_use` 必须单列，不能伪装成本地 registry 的一个成员。",
        "",
        "### 错误与恢复",
        "",
        "`string/template -> constructor/diagnostic callsite -> typed classifier -> retry/fallback/tombstone -> user surface -> post-side-effect boundary`。错误文本只是导航；真正决定行为的是 owner、预算、partial assistant/tool state 和副作用是否已经发生。",
        "",
        "## 判断一条清单能否支持技术结论",
        "",
        "```text",
        "发现 identifier / string / path",
        "  |",
        "  +-- 只有词法命中 -----------------> origin=Heuristic/Substrate",
        "  |                                      ownership=Mixed/Unresolved",
        "  |                                      proof=Candidate/Evidence substrate",
        "  |",
        "  +-- 有结构化 schema/catalog -------> origin=Structured extraction",
        "  |                                      proof=Declaration/Structured surface",
        "  |                                      仍需检查 ownership 与 consumer",
        "  |",
        "  +-- 有 AST callsite ---------------> proof=Callsite；先判 whole-bundle ownership",
        "                                         再找 lexical function 与 caller",
        "                                         |",
        "                                         +-- consumer 尚未追完 -> Untraced/Inventory only",
        "                                         |                       这是待办，不是 Boundary",
        "                                         |",
        "                                         +-- consumer + gate + state delta 已清楚",
        "                                                |",
        "                                                +-- Static 机制结论",
        "                                                +-- exact-binary Probe 提升运行证据",
        "",
        "consumer 仍在 bundle、只是尚未追完 -> Untraced/Inventory only",
        "server/runtime value、第三方内部、其他平台状态或构建前已删除源码 -> Boundary",
        "```",
        "",
        "## 三轴证据坐标：不要再用一个标签混合三件事",
        "",
        "旧写法把 `Product structured`、`Mixed heuristic`、`Evidence substrate` 放在同一列，实际混合了提取方法、代码所有权和证明强度。附录改为三个正交维度：",
        "",
        "| 轴 | 回答什么 | 典型值 |",
        "| --- | --- | --- |",
        "| 提取来源 | 这行怎样从 bundle 得到 | Targeted AST、Structured extraction、Heuristic scan、Derived projection、Manual intersection |",
        "| 所有权 | 候选属于谁 | Product、Dependency、Mixed、Unresolved |",
        "| 证明层级 | 当前最多能推出什么 | Candidate、Declaration、Callsite、Structured surface、Evidence substrate |",
        "",
        "`environment-access-callsites.jsonl` 是最典型的纠错：它确实是 AST callsite，但扫描的是整个 bundle，包含 `@grpc/grpc-js` 等依赖读取，所以所有权必须是 `Mixed`，不能因为“调用点是真的”就写成“一方 Product callsites”。`otel-environment-variables.txt` 同样来自 broad environment union 的前缀筛选，混有 OTEL SDK 自身变量，也不能统一归到产品。",
        "",
        "## 当前到底全面到哪里",
        "",
        f"机器防漏层已经覆盖 `summary.json` 注册的全部 {inventory_count} 类 inventory；这证明文件集合、提取规则和附录顺序没有漏，不证明每个 identifier 都完成 consumer tracing。正文只对已经串起 caller、gate、state delta、failure/recovery 和 Boundary 的机制给出强结论。仍停在 schema、candidate 或 callsite 的条目继续标为 `Untraced/Inventory only`，不能为了显得完整而改写成 Boundary。",
        "",
        "机器覆盖与语义完成度是两张验收表。前者防止文件和候选消失；后者回答机制是否真的讲清楚。逐能力的完成状态、仍待追 consumer 和 topic-depth 合同见 [全面性审计](completeness-audit.md)。",
        "",
        f"## 机器附录：{inventory_count} 类机器清单的证据分类与阅读路由",
        "",
        "下面的表只服务复核与跨版本比较，默认折叠。顺序和文件集合必须与 `analysis/source-inventory/summary.json` 完全一致；它按提取来源、所有权、证明层级和 Derived 阅读面分类，不宣称每一行已经拥有完整运行语义。",
        "",
        "<details>",
        f"<summary><strong>展开全部 {inventory_count} 类机器清单的提取来源、所有权、证明层级与阅读面</strong></summary>",
        "",
        "<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->",
        "| 机器清单 | 提取来源 | 所有权 | 证明层级 | 运行面 | 当前仍缺什么 |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for name in inventory_names:
        domain, classification = FILE_META[name]
        meta = DOMAIN_META[domain]
        class_meta = CLASS_META[classification]
        evidence_meta = FILE_EVIDENCE_OVERRIDES.get(name, {})
        axes = {**CLASS_AXES[classification], **FILE_AXIS_OVERRIDES.get(name, {})}
        routes = FILE_ROUTE_OVERRIDES.get(name, DOMAIN_ROUTE_IDS[domain])
        route_text = "/".join(routes)
        limitation = evidence_meta.get(
            "limitation",
            f"{class_meta['authority']}；{meta['boundary']}",
        )
        lines.append(
            f"| {markdown_link(name)} | `{axes['origin']}` | `{axes['ownership']}` | "
            f"`{axes['proof']}` | `{route_text}` | {limitation} |"
        )
    lines.extend([
        "<!-- SOURCE_INVENTORY_COVERAGE_END -->",
        "",
        "</details>",
        "",
        "## 按问题继续阅读",
        "",
        "- 模型为什么会继续调用工具、并发为什么有屏障：读 [Agent Loop](agent-loop.md) 与 [工具控制管线](tools-permissions-hooks.md)。",
        "- `/compact` 为什么只改变送模历史、不撤销文件：读 [上下文治理](context-governance-and-caching.md) 与 [Session/Checkpoint/Memory](sessions-checkpoints-memory.md)。",
        "- 一个开关为什么写了却不生效：读 [Settings/Policy](settings-feature-flags-policy.md)、[环境变量逐项参考](environment-variable-reference.md) 和 [Feature key 逐项参考](feature-flag-reference.md)。",
        "- 一个 path/event/error 到底归谁：读 [API/Beta owner](api-beta-route-ownership.md)、[Telemetry 场景索引](telemetry-event-catalog.md) 与 [错误恢复图谱](error-diagnostic-atlas.md)。",
        "- `.node` 文件、Voice、TUI 与系统权限怎样接起来：读 [Native Bridge](native-bridge-runtime.md) 与 [TUI/媒体/IDE](tui-input-accessibility-media-ide-chrome.md)。",
        "- 整个版本还有哪些语义未追完：读 [全面性审计](completeness-audit.md)，不要用本附录的机器覆盖代替机制完成度。",
        "",
        "## 这张地图能证明到哪里",
        "",
        f"机器层面，本图完成 `summary.json` 全部 {inventory_count} 个注册文件的证据分类、阅读面路由和边界声明，canonical source SHA-256 为 `{summary['canonicalSource']['sha256']}`。技术层面，它给出六条可复核的真实机制链和一个明确标注为 Derived 的五面阅读模型。它不把 inventory、事件、flag、path 或 error 数量包装成“已经理解全部行为”；最终状态仍以 [全面性审计](completeness-audit.md) 和逐项参考中的 consumer 追踪为准。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--output")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the existing output differs instead of writing it",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    content = build(repo)
    if args.check:
        output = Path(args.output) if args.output else repo / "analysis/product-surface-evidence-map.md"
        if not output.is_absolute():
            output = repo / output
        if not output.is_file():
            raise SystemExit(f"missing output: {output}")
        if output.read_text(encoding="utf-8") != content:
            raise SystemExit(f"stale output: {output}")
        print(f"checked {output.relative_to(repo) if output.is_relative_to(repo) else output}")
        return
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
