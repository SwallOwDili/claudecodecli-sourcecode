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
    evidence_records = [
        json.loads(line)
        for line in (repo / "analysis/mechanism-evidence.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    evidence_count = len(evidence_records)
    evidence_topic_count = len({record["topic"] for record in evidence_records})
    evidence_class_counts = {
        evidence_class: sum(
            record.get("evidenceClass") == evidence_class
            for record in evidence_records
        )
        for evidence_class in ("Static", "Probe", "Public", "Boundary")
    }
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
        f"# Claude Code CLI {version}：一台把模型限制在“提案权”里的本地执行系统",
        "",
        f"> 版本：`{version}` | 核心客户端路径：`Static` + `Probe` | C/Q/E/S/O：`Derived` 阅读模型 | 服务端内部：`Boundary`",
        "",
        f"**核心判断：** Claude Code `{version}` 最值得研究的不是“内置了多少工具”，而是它刻意不让模型成为系统里的最终权威。模型只能提出下一步；客户端决定这一轮究竟暴露哪些能力、哪些提议可以执行、结果怎样进入因果链；文件系统、子进程和远端服务则拥有已经发生的真实副作用。它因此获得了 Agent 的自主性，却仍把权限、状态和失败责任留在可检查的本地边界内。",
        "",
        "**一句话模型：** 模型负责提议，客户端负责裁决与记账；历史表示可以重建，外部世界不能假装回滚。",
        "",
        "![模型只提出动作，本地管线裁决并记录因果，真实副作用由外部 owner 持有](visuals/runtime-authority-lifecycle.svg)",
        "",
        "这张图给出整篇文章唯一需要先记住的架构关系。系统同时维护三个不等价的世界：模型世界保存可重新生成的提案，客户端世界保存权限决定和可恢复的因果账本，外部世界保存已经落地的文件、进程、网络和服务端状态。多数容易讲错的技术点，都来自把这三个世界混成一个：把 `tool_use` 当作动作已经执行，把 `/compact` 当作历史已经删除，把 resume 当作进程快照恢复，或者把 telemetry 当作事实账本。",
        "",
        f"下文用一个任务和六个工程矛盾拆开这三个世界。最后才给出 C/Q/E/S/O；它是本文从 `{version}` 调用链归纳的 **Derived 阅读模型**，不是源码中的五个原生模块，也不是 Anthropic 官方架构名称。",
        "",
        "## 60 秒看懂一次真实任务",
        "",
        "**读者问题：** 用户只说“把端口改掉并跑测试”，一句话为什么会变成多轮模型请求、并发屏障、权限询问、状态落盘和恢复分支？",
        "",
        "**贯穿场景：** Claude 先读配置，再编辑端口并执行 Bash 测试；测试失败后，它读取错误继续修复。对话变长时，用户执行 `/compact`，退出后又用 resume 接着工作。",
        "",
        "客户端不会把 bundle 中所有工具一股脑交给模型。它先根据 settings、env、managed policy、workspace trust、host、账号与 feature 状态，在请求发出前临时组装这一轮的 `tools[]`。模型看到的是一张当下可达能力图，不是安装包能力总表。",
        "",
        "模型开始流式返回后，一个完整的 client `tool_use` block 一闭合，本地 executor 就可以入队执行，不必等待整条 assistant message 结束。只读调用可以重叠，Edit 之类的不安全调用形成屏障；权限拒绝、测试失败或 schema 错误则按同一个 `tool_use_id` 变成 `tool_result`，进入下一次模型决策。错误不是异常地“跳出 Agent”，而是 Agent 继续推理所需的新观察。",
        "",
        "当 `/compact` 发生时，客户端没有撤销 Edit，也没有删除已经发生的测试进程。它只用 summary、保留片段、附件和 boundary 替换下一次送模的历史表示。resume 同样不是恢复旧进程，而是从 transcript、UUID/parent、compact boundary 和 checkpoint 中重新构造一条因果合法的工作视图。",
        "",
        "| 对象 | 任务开始前 | 任务推进后 | `/compact` / resume 后 |",
        "| --- | --- | --- | --- |",
        "| 模型可见上下文 | 用户输入和当前有效历史 | 追加 tool proposal 与配对 result | 被重建为 summary + 合法保留段 + 新输入 |",
        "| 客户端因果账本 | session、配置和能力候选 | 追加消息 UUID、permission 决定、tool pair、checkpoint/reference | 保留 boundary，按 leaf 和 parent 重放有效链 |",
        "| 外部世界 | 原项目文件和进程状态 | 文件已修改、测试已启动、远端动作可能已提交 | 不因 compact/resume 自动回滚或复活 |",
        "| 观测记录 | 可能尚无事件 | 各通道按自己的 gate、sampling 和 queue 记录 | 缺失不证明动作未发生，出现也不证明服务端已落库 |",
        "",
        "这就是 2.1.235 的技术主线：它不是让一个模型拥有世界，而是在模型提案、客户端因果状态和真实副作用之间持续做协调。后面所有“微小特性”都应该说明自己改变了哪一个对象，而不是只报一个字段名。",
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
        "工具执行也不是等整个 assistant message 完全结束后才开始。流式 parser 在 `content_block_stop` 把一个完成的 block 产出为 assistant fragment（[L409843-L409906](../reverse/javascript/cli.readable.js#L409843)）；Agent Loop 看到其中的 client `tool_use` 就立刻 `addTool(...)`，随后 `Waf(...)` 在模型流事件和 executor 的 drain tick 之间竞速（[L267292-L267310](../reverse/javascript/cli.readable.js#L267292)、[L272032-L272045](../reverse/javascript/cli.readable.js#L272032)）。这里重叠的是**模型继续流式输出**与**本地工具执行/UI 或 SDK progress**；`tool_result` 不会塞回仍在进行的同一次模型请求。客户端必须等当前 stream 和 executor drain 收尾，才在下一次 model iteration 中把结果送回模型。性能收益来自重叠等待，正确性则依赖完整 block 边界、并发屏障、同 ID 配对和最终 drain，不能简化成一次 `Promise.all`。",
        "",
        "把 `maxTurns=1` 代入贯穿场景就能看清边界：第一轮模型仍可返回 Read、Edit、Bash，三个工具仍按队列规则执行并产生副作用；客户端只是禁止工具结果后的第二轮模型决策，最终给出 `error_max_turns`。精确二进制 Probe 已观察到“工具执行完成、PostToolUse 已发生、服务端只收到一个 Messages 请求”。所以 `maxTurns` 不是工具配额，更不是副作用回滚器；这也是排查“为什么请求次数变多”或“为什么工具做了但没有最终总结”时必须先分清四种计数的原因。完整 Probe 见 [运行证据索引](runtime-probe-index.md) 与 [Agent Loop 专题](agent-loop.md)。",
        "",
        "## 矛盾一：让模型自主，但不把执行权交给模型",
        "",
        f"这是理解 {version} Agent Loop 的第一道权力边界。模型能生成动作意图，却不能靠生成一个名字就取得本机执行权。可读源码在 [L272032-L272038](../reverse/javascript/cli.readable.js#L272032) 只把 assistant content 中的 `tool_use` 收集进本地 `streamingToolExecutor`；流式 parser 也认识 `server_tool_use`，例如 Advisor，但它只组装该 block 和对应 server result（[L409843-L409877](../reverse/javascript/cli.readable.js#L409843)）。",
        "",
        "| 对象 | dispatch / 裁决 owner | 真实 effect owner | 是否进入本地 registry / permission / 适用的 policy-sandbox / `tool.call` | 结果怎样回来 |",
        "| --- | --- | --- | --- | --- |",
        "| client `tool_use` | Claude Code 本地 runtime | 内置工具可直接落到 OS；MCP/Plugin/浏览器/远端 API 仍由各自 host 或服务拥有真实副作用 | **是** | 客户端生成同 `tool_use_id` 的 user `tool_result`，再发起后续模型轮次 |",
        "| `server_tool_use` | Anthropic 服务端工具生命周期 | 服务端工具及其后端 | **否** | server result block 留在 assistant stream；客户端可以显示、记录和规范化，但不会本地 dispatch |",
        "",
        "因此，本地 Agent Loop 只接管 client `tool_use`；`server_tool_use` 是客户端可观察、但不拥有执行权的服务端分支。这种不对称不是协议细枝末节，而是产品的信任架构：云端模型可以决定“想做什么”，工作区一侧的 runtime 才决定“这里允许发生什么”。",
        "",
        "### Bash 的“可调用”为什么不是一个布尔值",
        "",
        "这里要分开三个常被压成“工具存在”的状态：**发现状态**回答 bundle 里有没有候选，**请求可见状态**回答模型本轮能否获得名称或完整 schema，**执行授权状态**回答某组具体参数能否真的产生副作用。三者之间任何一层都可以拒绝、延迟或改写。",
        "",
        "[`known-tool-catalog.txt`](source-inventory/known-tool-catalog.txt) 中出现 `Bash`，只证明 bundle 里有候选名字。[`tool-registrations.jsonl` 第 80 行](source-inventory/tool-registrations.jsonl#L80)恢复出 `toolRegistration:Bash:1`，并定位到真实工厂对象、schema、permission 和 result mapper；可读源码中的对象位于 [L393203](../reverse/javascript/cli.readable.js#L393203)。真正进入请求前，它还要经过 host、feature、session、alias、dynamic registry 和 Tool Search/deferred-loading 选择。即使 HTTP 请求携带 deferred tool declaration，也不能直接等同于模型此刻已经获得完整 schema；更不能等同于一组具体 Bash 参数已经获准执行。",
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
        "### 流式调度用“并发纯度合同”换取延迟",
        "",
        "`addTool()` 先用最初 parsed input 调用 `isConcurrencySafe(input)`，把结果固化在队列项上，再由 `processQueue()` 允许 safe 项重叠、让 unsafe 项等待前序 drain 并阻塞后序启动（[L267124-L267149](../reverse/javascript/cli.readable.js#L267124)）。这不是普通 `Promise.all`，而是工具向调度器声明“这组输入是否会与共享状态冲突”的纯度合同。PreToolUse Hook 和 permission handler 后续可以改写 input（[L316220-L316330](../reverse/javascript/cli.readable.js#L316220)），但调度器不会回头重算。",
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
        "这一时序暴露了 2.1.235 很具体的性能取舍：它愿意根据早期输入尽快建立并发顺序，换取工具与模型流的重叠；代价是扩展不应在 Hook 里把一个原本安全的调用改成具有全新共享副作用的调用，并期待调度器自动重新分类。当前证据是目标 bundle 的可达静态合同，还没有覆盖所有多工具竞态组合的精确二进制 Probe。",
        "",
        "### “允许”也不是一个状态",
        "",
        "一个工具从提案走到副作用，还要依次穿过 registry/schema/custom validation、PreToolUse、permission/rule/managed policy、适用工具内部 sandbox、`tool.call`、PostToolUse 与 output validation。前置层可以阻止动作；后置层只能影响结果展示和下一步控制流，不能撤销已经发生的写入。`bypassPermissions` 绕过普通交互审批，也不会自动关闭适用工具自己的 sandbox。",
        "",
        "精确二进制 TUI Probe 又验证了一个容易被 UI 文案掩盖的状态差异：Shift+Tab 退出 comment input 不会批准 Edit；随后显式 Enter 只批准第一次 Edit，第二次仍会询问。只有用户用 Down+Enter 选中 session-wide `acceptEdits`，第二次 Edit 才不再弹框。也就是说，“关闭输入框”“批准这一次”“本会话批准同类 Edit”是三个独立状态，不应被归纳成一个 permission 布尔值。见 [TUI 权限 Probe](runtime-probes/tui-regressions.json) 与 [工具控制管线](tools-permissions-hooks.md)。",
        "",
        "Bash 一旦启动子进程，文件、进程和网络副作用就归 OS 或远端 owner。后续 tombstone、compact、resume 只能修复消息表示和本地记录，不能自动撤销已经执行的命令。完整机制见 [工具注册与宿主表面](tool-registration-and-host-surfaces.md)、[Agent Loop](agent-loop.md) 和 [工具控制管线](tools-permissions-hooks.md)。",
        "",
        "## 矛盾二：既要忘掉大部分历史，又要让任务继续成立",
        "",
        "![上下文先复用稳定前缀、延迟工具 schema、局部清理旧结果，最后才全局总结并写恢复边界](visuals/context-control-lifecycle.svg)",
        "",
        "同一个长任务会依次遇到五类不同问题：重复前缀太贵、工具 schema 常驻太大、旧 tool result 挤占窗口、服务端希望提示局部清理、完整历史终于接近有效上限。Claude Code 没有用一个万能“缓存层”解决它们，而是分别改变成本、schema 可见性、active message view、协作协议和逻辑历史。",
        "",
        "| 机制 | 它真正改变什么 | 它明确不改变什么 |",
        "| --- | --- | --- |",
        "| Prompt cache | 给稳定 system/message 前缀加 breakpoint 与 5m/1h TTL，命中后降低重复输入成本和 prefill 延迟 | 不缩短逻辑消息，也不负责 resume |",
        "| Tool Search / deferred schema | 请求把候选标为 `defer_loading:true`；模型先得到轻量发现入口，被发现后完整 schema 才进入后续上下文 | 不是把工具缓存到 HTTP body 之外，也不等于未发现工具零 token |",
        "| Context hint | 服务端协作协议提示客户端清理特定工具族旧结果，并对 400/409/422/424/529 与流式错误走不同回退 | 协议启用不等于本地已经清理成功 |",
        "| Local microcompaction | 改写 active message view 中旧的大型 tool result；默认保留最近 5 个相关结果，总节省不足 20k token 时不执行 | 不删除 tool call/ID 因果，也不证明 physical transcript 删除旧事件 |",
        "| Precomputed compact | 在 sidecar/Storage 中提前准备 summary，等真正到 compact line 再校验并交换 | pending/过期/分支不匹配的 summary 不会硬塞进主历史 |",
        "| Full compact | 用 summary、路径相关的 preserved suffix、attachments 与 Hook 结果重写下一次有效 messages | 不撤销文件、进程、Git 或远端 API 副作用 |",
        "| Transcript + boundary | 保存表示替换关系、UUID 和 logical parent，让 resume 能修复消息链 | 不等于 API prompt cache，也不保存旧进程内存 |",
        "",
        "先看最普通的 manual miss。`PreCompact` Hook 放行且没有可复用预计算结果时，客户端在旧对话末尾插入专用虚拟用户消息，以 `CRITICAL` 要求模型停止业务工作、禁止调用工具，并先输出 `<analysis>` 做时序梳理，再输出固定九段 `<summary>` 作为工程交接。客户端随后丢弃前者，只把后者改写成 Summary。这里的 `<analysis>` 是应用层提示词格式，不是模型 API 的原生 thinking；模板和提取路径见 [L261931-L262207](../reverse/javascript/cli.readable.js#L261931)。",
        "",
        "只保存有损 Summary 仍不足以继续编码，所以重建结果由四种互补通道组成：",
        "",
        "| 重建通道 | 保存什么 | 为什么不能由 Summary 单独替代 |",
        "| --- | --- | --- |",
        "| Summary | 远期目标、决定、错误、用户反馈、待办 | 压缩率高，但会丢逐字符材料 |",
        "| Preserved message groups | 最近的完整 tool_use/tool_result 因果组 | 不能机械保留末尾 N 条，否则可能拆断协议配对 |",
        "| Attachments / hooks | 最近相关文件、Plan、Skill/MCP/Agent 状态与 hook 结果 | 用受限的精确重读补偿摘要失真 |",
        "| compact boundary | summary、preserved UUID 与 logical parent 的表示切换关系 | 让 resume/fork 知道哪条逻辑链仍然有效 |",
        "",
        "因此 `/compact` 的本质不是“把 87 条消息缩成 4 条”之类的数组技巧，而是一次**有损语义通道 + 有界精确信息通道 + 因果恢复边界**的表示替换。它用冗余换连续性：Summary 和附件可能重复，但两者分别防范语义遗忘和逐字符失真。",
        "",
        "本地 microcompaction 的 release-local 主路径见 [L263484-L263519](../reverse/javascript/cli.readable.js#L263484)。预计算 sidecar 是 schema version 2，单文件上限 8,000,000 bytes；复用会拒绝超过 7 天、从预计算点又增长超过 150,000 token、缩减过半或关键 UUID 缺失的结果，连续 3 次可计数失败后停止 re-arm。它减少的是临界点上的总结延迟和重复成本，不是把 summary 变成永久真相；校验与 swap 主链见 [L262324-L262680](../reverse/javascript/cli.readable.js#L262324)。完整 5m/1h 成本算例、四条窗口线、Context Hint 回退与 provider 差异见 [上下文治理专题](context-governance-and-caching.md)。",
        "",
        "自动治理也不是“达到一个百分比就总结”。代码先从有效 window 扣除最多 20k 输出预算得到 input budget，再分别计算 precompute、warning、compact 与 blocked 四条线：前 3 条跟随可配置的 auto-compact window，blocked 则来自模型输入 ceiling 再减 3k。以 200k context、20k 输出预留为例，默认算例依次约为 144k 预计算、147k 警告、167k compact、177k 阻塞。把 auto-compact window 调小会让总结更早，不会把底层模型硬阻塞线一起等比例下移。阈值主路径见 [L216096](../reverse/javascript/cli.readable.js#L216096)。",
        "",
        "### 预计算不是另一种总结格式，而是把等待提前",
        "",
        "![compact 先检查预计算结果，命中直接重建，未命中才请求 summary](visuals/compact-lifecycle.svg)",
        "",
        f"理解普通 miss 后，再看 {version} 的性能优化才不会迷路。`/compact` 同时连接命令 gate、PreCompact Hook、预计算 sidecar、group-based compactor、summary request、message graph 和 transcript boundary；hit 与 miss 的差别不是输出格式，而是 summary 工作何时发生、当前任务变化后旧结果还能否被信任。",
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
        "## 矛盾三：既要看见系统，又不能把观测误当成事实",
        "",
        "![同一运行时信号经过关联与内容控制后，分别进入一方事件、Datadog、OTEL 和本地诊断通道](visuals/telemetry-pipeline.svg)",
        "",
        f"“Claude Code 有没有遥测”是一个过于粗糙的问题。{version} 至少要分开 Anthropic 一方事件、Datadog forwarding、用户或管理员配置的 OTEL，以及本地 debug/profile/doctor。它们会观察同一次 query、tool、permission、compact 或 error，但拥有不同 gate、字段、队列、目的地和失败语义。关闭其中一条，不代表其他通道同时关闭。架构上更重要的判断是：运行时先发生状态变化，再把不同投影 best-effort 地送往不同 sink；遥测从来不是那份状态本身。",
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
        "OTEL 本身也不是一个布尔开关。bootstrap 先读取 `CLAUDE_CODE_ENABLE_TELEMETRY`，再分别构造 metrics、logs、traces exporter（[L361612-L361670](../reverse/javascript/cli.readable.js#L361612)）；`OTEL_LOG_USER_PROMPTS` 未开启时，prompt 字段被替换为 `<REDACTED>`（[L93779-L93806](../reverse/javascript/cli.readable.js#L93779)）。精确二进制 Probe 进一步验证了默认 OTLP payload 含 user-prompt event 但正文为 `<REDACTED>`，显式开启后原 marker 才进入 collector。由此可见，出口启用、事件启用和内容启用是三个独立问题。",
        "",
        "更敏感的 raw API body 还有一套独立内容门。`OTEL_LOG_RAW_API_BODIES` 未设置时，collector 收不到 request/response body event；设置为 `1` 后，即使 `OTEL_LOG_USER_PROMPTS` 没开，完整受控 request/response marker 也会进入 collector；设置为 `file:<dir>` 后，正文写成本地 JSON，OTEL event 只带 `body_ref`，collector 不再含正文 marker。file 模式降低了 collector 的正文暴露，却把风险迁移为本地明文文件；它不是“更隐私”的无条件结论。三种模式均由同版精确二进制 Probe 验证，见 [raw-body 报告](runtime-probes/telemetry-otlp.json)。完整 queue、sampling、字段、Probe 与隐私边界见 [遥测专题](telemetry.md) 和 [遥测事件场景索引](telemetry-event-catalog.md)。",
        "",
        "最关键的架构判断是：观测面是有损、分叉、best-effort 的 sink，不是系统事实的唯一账本，更不是 retry/compact/supervisor 的控制器。事件缺失不能证明动作没发生；事件出现也不能证明远端 collector 已确认写入。排障时必须回到真正拥有状态的 request、tool、session 或 recovery controller。",
        "",
        "## 矛盾四：想恢复任务，但系统没有一台时间机器",
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
        "| Remote reference / result | 各子系统保存自己的 slug/version、task ID、URL 或错误结果 | 保住远端对象身份；Artifact、CCR、background task 分别定义可查询、取消、重试或补偿能力 | 不存在统一 remote-reference API；reference 也不是分布式事务句柄 |",
        "",
        "精确二进制 Probe 把这两个恢复面分开证明：fork 生成新的 session ID，只带 compact 后的逻辑状态；file rewind 在不发送任何 Messages 请求的情况下，把受管临时文件从修改值恢复为原始字节。它说明 rewind 是本地 checkpoint 驱动的补偿操作，不需要模型生成反向 Edit，也不涵盖 Git push、Artifact 部署、数据库写或已发送消息。完整恢复矩阵见 [Session/Checkpoint/Memory](sessions-checkpoints-memory.md)。",
        "",
        "所以“状态可续”是一个有类型的承诺：消息图续消息，checkpoint 续文件，各子系统的 remote reference 只续自己明确支持的补偿线索。它的优势是无需保存整个 Bun 进程和远端世界的快照；代价是任何“恢复成功”报告都必须同时说明恢复了哪个对象，以及哪些外部副作用仍然存在。",
        "",
        "## 压力测试五：Artifact 超时后，客户端为什么可能不知道结果",
        "",
        "贯穿场景现在多一步：修改和测试完成后，Claude 发布一份 HTML 报告。Artifact 的完整发布协议还包含本地文件身份、staged upload、commit/version 和 stale guard；这里故意只拿其中的 direct-publish route 做压力测试，因为一次超时足以暴露本地 Agent 无法拥有远端事务真相。",
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
        "超时最麻烦的地方，不是错误文字，而是它发生在请求发送之后：客户端知道自己没有拿到可信响应，却不能仅凭这一事实断言服务端没有提交。如果贸然重试，可能重复写；如果完全不重试，又可能把一次可恢复的传输失败变成用户可见失败。2.1.235 因而按 400/409/429/503 分类采取有界策略，而没有一个笼统的“网络错误重试”开关。",
        "",
        "这揭示了 Agent runtime 的另一条不变量：**恢复是局部控制器和补偿动作的集合，不是全局事务。** CLI 能做的是限制重试、暴露 conflict、在可信响应后更新本地 known version、保留 slug/version/reference，并在结果未知时给出 readback 建议；它不能凭本地 transcript 宣布远端已提交或已回滚。当前结论主要来自 Static 可达路径，没有一条真实远端 Artifact 成功 Probe，因此远端持久化仍是 Boundary。完整 owner 表见 [API/Beta 路由所有权](api-beta-route-ownership.md) 与 [Workflow/Artifact/Design](workflow-artifact-design.md)。",
        "",
        "## 矛盾六：要调用本机原生能力，又不能把 ABI 当成原始源码",
        "",
        "Claude Code 把截图、输入注入、原生文件操作和音频采集装进同进程 `.node` bridge，而不是统一放到外部 helper。这样能降低 IPC、直接复用 N-API 和系统 framework；代价是 ABI mismatch、线程回调、panic/finalizer 或系统权限错误都更靠近 CLI 主进程，且真实键鼠、录音和屏幕副作用不受 transcript 回滚控制。",
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
        "静态证据可以把客户端候选链连起来：native 或 SoX 产生 audio bytes，客户端在 WebSocket ready 前排队，之后发送到远端 STT；interim/final transcript 写入 composer，用户真正提交文本后才进入普通 Agent Loop。但这不是同版真实麦克风和 Voice service 的端到端 Probe，原版 native 内部重采样也仍是 Boundary。原始音频离开本地这一上传路径可由 bundle 证明，服务端留存、训练或删除策略则不能。",
        "",
        "重建层也必须守住同样的边界：当前 5 个 native 模块的兼容实现以导出名、参数、返回/throw/null、生命周期和受控 Probe 对齐 JS consumer 合同；23 项报告里 22 项是 original/compatible 比较，1 项是覆盖审计。compatible runtime 目前只完成 arm64 build/run，x86_64 尚未实跑；“兼容”描述的是已覆盖输入下的外部合同，不是找回 Anthropic 的 C/C++/Rust/Swift 原函数体。详见 [Native Bridge](native-bridge-runtime.md) 与 [TUI/媒体/Voice](tui-input-accessibility-media-ide-chrome.md)。",
        "",
        "## 六个压力测试共同暴露出的技术性格",
        "",
        "把 Bash、compact、telemetry、resume、Artifact 和 Voice 放在一起看，2.1.235 的技术特征不再是六份互不相干的功能说明，而是五条反复出现的设计选择。",
        "",
        "**第一，能力晚绑定。** bundle 只给出候选能力；host、账号、feature、permission mode、Tool Search 和 session 状态共同决定一次请求的可达图。它让同一个二进制服务 TUI、SDK、remote、first-party 与不同 provider，却也要求排障时把“存在”“广告”“授权”“执行”分开。",
        "",
        "**第二，权力不对称。** 模型拥有生成提案的自由，本地 runtime 拥有 client tool 的裁决权，server tool 留在服务端，外部 owner 拥有最终副作用。系统的自主性来自模型可以反复选择下一步，安全边界则来自模型不能通过文本自行越过客户端控制。",
        "",
        "**第三，事实与表示分离。** transcript/message graph、有效送模历史和外部世界是三份不同状态。prompt cache 改成本，microcompaction 改 active view，full compact 改逻辑表示，boundary 记恢复关系；它们都不重写已经发生的外部事实。",
        "",
        "**第四，恢复按对象负责。** request retry、stream fallback、compact、tool tombstone、file rewind、process supervisor 和 Artifact conflict 各自拥有局部状态与预算。没有统一 recovery manager 可以同时倒回 transcript、文件、进程和远端对象；所谓可靠性主要来自幂等前置、有限重试、状态钉住和补偿线索。",
        "",
        "**第五，可观测性有意保持从属。** analytics、Datadog、OTEL 和 debug 读取运行时投影，但不反向拥有 Agent Loop。sampling、redaction、queue 和发送失败会让观测天然有损，这防止业务流程被遥测绑死，也意味着排障不能把事件库当作唯一真相。",
        "",
        "这五条选择共同形成一个很鲜明的工程取舍：Claude Code 愿意接受更多局部状态机和边界条件，来换取低延迟、可扩展能力、跨进程连续性与不同信任域的隔离。复杂度没有消失，只是被分配给真正拥有状态的组件，而不是压进一个无所不能的 Agent Loop。",
        "",
        "## 最后再用 C/Q/E/S/O 作为阅读路由",
        "",
        "C/Q/E/S/O 是本文的 Derived 分析框架，不是源码目录图，也不是 Anthropic 官方架构或命名。它按最终决定权分面，同一功能可以跨多个面；恢复也不是统一的第六层，request retry、stream fallback、compact、tool tombstone 与 process supervisor 都留在各自 owner 的局部回路中。观测面只接收事件，不反向控制请求。",
        "",
        "![Derived 阅读模型：控制约束请求，本地 Agent Loop 执行 client tool_use，server_tool_use 留在服务端，各 owner 在局部回路恢复，观测只接收投影](visuals/product-surface-runtime-planes.svg)",
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
        "## 按问题继续阅读",
        "",
        "- 模型为什么会继续调用工具、并发为什么有屏障：读 [Agent Loop](agent-loop.md) 与 [工具控制管线](tools-permissions-hooks.md)。",
        "- `/compact` 为什么只改变送模历史、不撤销文件：读 [上下文治理](context-governance-and-caching.md)、[图文专题](compact-visual-guide.md) 与 [Session/Checkpoint/Memory](sessions-checkpoints-memory.md)。",
        "- 一个开关为什么写了却不生效：读 [Settings/Policy](settings-feature-flags-policy.md)、[环境变量逐项参考](environment-variable-reference.md) 和 [Feature key 逐项参考](feature-flag-reference.md)。",
        "- 一次权限批准怎样穿过 Hook、policy、sandbox 和 TUI scope：读 [工具控制管线](tools-permissions-hooks.md) 与 [TUI/媒体/IDE](tui-input-accessibility-media-ide-chrome.md)。",
        "- 一个 path/event/error 到底归谁：读 [API/Beta owner](api-beta-route-ownership.md)、[Telemetry 场景索引](telemetry-event-catalog.md) 与 [错误恢复图谱](error-diagnostic-atlas.md)。",
        "- `.node`、Voice 与原生重建到底证明到哪：读 [Native Bridge](native-bridge-runtime.md) 与 [原生重建报告](../reconstructed/README.md)。",
        "- 整个版本还有哪些语义未追完：读 [全面性审计](completeness-audit.md)，不要用机器覆盖代替机制完成度。",
        "",
        "<details>",
        "<summary><strong>证据方法附录：怎样从一个字符串走到可复核的技术结论</strong></summary>",
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
        "</details>",
        "",
        "## 当前到底全面到哪里",
        "",
        f"机器防漏层已经覆盖 `summary.json` 注册的全部 {inventory_count} 类 inventory；这证明文件集合、提取规则和附录顺序没有漏，不证明每个 identifier 都完成 consumer tracing。正文只对已经串起 caller、gate、state delta、failure/recovery 和 Boundary 的机制给出强结论。仍停在 schema、candidate 或 callsite 的条目继续标为 `Untraced/Inventory only`，不能为了显得完整而改写成 Boundary。",
        "",
        f"结构化机制注册表当前有 {evidence_count} 条 claim，覆盖 {evidence_topic_count} 个 topic：{evidence_class_counts['Static']} Static、{evidence_class_counts['Probe']} Probe、{evidence_class_counts['Public']} Public、{evidence_class_counts['Boundary']} Boundary。这个数字证明结论有可定位证据，不证明所有能力达到同样深度。当前明确欠账仍包括：654 个静态环境名称和 211 个 Feature key 的人工语义收口、85 个仍含运行参数的动态环境表达式、911 个 `tengu_other` 事件的逐 caller/owner 分类，以及 error/diagnostic、网络、后台 supervisor、Plugin Evaluation 和 x86_64 native 的正向 Probe。",
        "",
        "机器覆盖、机制证据和语义完成度是三张验收表：第一张防止候选消失，第二张约束强结论必须有证据，第三张才回答每个机制是否真的讲清楚。逐能力状态、未追 consumer 和 topic-depth 合同见 [全面性审计](completeness-audit.md)。",
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
