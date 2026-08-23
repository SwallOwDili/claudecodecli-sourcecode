#!/usr/bin/env python3
"""Build the human-readable ownership map for every source inventory file."""

from __future__ import annotations

import argparse
import json
import re
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


def read_generated_summary(repo: Path, relative: str, prefix: str) -> dict:
    text = (repo / relative).read_text(encoding="utf-8")
    begin = f"<!-- BEGIN:{prefix}:MACHINE_SUMMARY\n"
    end = f"\nEND:{prefix}:MACHINE_SUMMARY -->"
    if begin not in text or end not in text:
        raise RuntimeError(f"missing generated summary markers: {relative}")
    return json.loads(text.split(begin, 1)[1].split(end, 1)[0])


def read_telemetry_projection(repo: Path) -> dict[str, int]:
    catalog = (repo / "analysis/telemetry-event-catalog.md").read_text(
        encoding="utf-8"
    )
    projection: dict[str, int] = {}
    for name in (
        "target-events",
        "target-callsites",
        "single",
        "cross",
        "partial",
        "unresolved",
        "allowlist-entries",
        "mapped-callsites",
        "unresolved-callsites",
    ):
        match = re.search(rf"<!-- caller-owner-{re.escape(name)}:(\d+) -->", catalog)
        if match is None:
            raise RuntimeError(f"missing telemetry caller-owner marker: {name}")
        projection[name] = int(match.group(1))
    return projection


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
        f"下文只沿一条任务主线展开：能力怎样形成、请求怎样循环、动作怎样受控、上下文怎样治理、会话怎样恢复、扩展怎样接入、远端结果为什么会未知、遥测怎样投影、native 怎样跨越 ABI。C/Q/E/S/O 只在结尾作为索引；它是本文从 `{version}` 调用链归纳的 **Derived 阅读模型**，不是源码中的五个原生模块，也不是 Anthropic 官方架构名称。",
        "",
        "## 60 秒看懂一次真实任务",
        "",
        "**读者问题：** 用户只说“把端口改掉并跑测试”，一句话为什么会变成多轮模型请求、并发屏障、权限询问、状态落盘和恢复分支？",
        "",
        "**贯穿场景：** 用户第一次在一个未信任的 Node 项目中启动 Claude Code，要求先规划，再把端口从 8080 改成 9090 并运行测试。测试失败后，Claude 查询 MCP 文档并让子 Agent 在独立 worktree 复核；长会话触发 `/compact`，用户退出后 resume，最后发布 HTML Artifact，但请求超时。Voice 作为独立输入旁线，不强塞进这条编码任务。",
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
        "## 能力编译：任务还没发给模型，边界已经形成",
        "",
        "![Settings、policy、trust、provider 与 feature 先编译有效能力，再由请求层选择本轮可见工具](visuals/settings-policy-lifecycle.svg)",
        "",
        "第一次在一个陌生 Node 项目里启动 Claude Code，用户还没有输入任何任务，本地 runtime 已经开始做安全和能力编译：这是 TUI、print/SDK 还是内部 worker；当前目录是否可信；哪些 settings 来源可读；managed policy 能否收紧权限；provider 和凭据走哪条路径；Plugin、Skill、MCP 与内置工具的 registry generation 是否可用。最终产物不是一个静态 `config` 对象，而是**这一时刻、这个 session、这次 request 可以到达的能力图**。",
        "",
        "把“bundle 里有 Bash”直接翻译成“模型可以执行 Bash”，中间至少漏掉四次状态转换：",
        "",
        "```text",
        "shipped candidate -> trusted + enabled local registry",
        "                         |",
        "                         +-- advertisement path",
        "                         |     -> request name / full or deferred schema",
        "                         |     -> model discovery and proposal",
        "                         |",
        "                         +-- dispatch path",
        "                               -> complete client tool_use",
        "                               -> local lookup + input-specific authorization",
        "                               -> executed effect",
        "```",
        "",
        "### Workspace trust 不是一个欢迎弹窗",
        "",
        "项目目录可以携带 hooks、MCP、skills、helpers、settings 和命令定义，这些表面都可能扩大执行权。2.1.235 因而先区分 safe/bare startup 与 trusted startup：在信任成立之前，项目可控的可执行配置不应被当作普通能力加载；接受后还要重新发现项目资源，不能沿用信任前的 registry 快照。风险扫描、接受/拒绝与持久化主链位于 [L593436-L593729](../reverse/javascript/cli.readable.js#L593436)，safe/bare 判定见 [L8159-L8171](../reverse/javascript/cli.readable.js#L8159)。这解释了一个用户常见现象：仓库里明明已经提交了 Hook 或 MCP，首次进入时却“看不见”；不是扫描漏了，而是能力还没有跨过 trust boundary。",
        "",
        "### Settings 不是后写覆盖前写",
        "",
        "进程级 settings store 同时持有来源缓存、合并缓存、policy 派生状态和失效 epoch。普通层大致按 `user < project < local < flag < policy` 进入解析，但具体字段并不共享一种 merge：普通数组会拼接去重，`fallbackModel` 高层整组替换，marketplace map 按 key 合并，managed-only 和限制性 policy 又有独立收紧规则。`--setting-sources` 只能筛 user/project/local，不能移除 flag 与 policy。来源顺序见 [L39176-L39215](../reverse/javascript/cli.readable.js#L39176)，通用 merge 例外见 [L41697-L41703](../reverse/javascript/cli.readable.js#L41697)。所以“effective settings 里出现了这个字段”仍不等于已发出的 request、已有 subagent 或正在运行的 Bash 会被热重写。",
        "",
        "配置热更新也只制造一次可信失效事件。watcher 等文件稳定、抑制本进程写回声、运行 `ConfigChange` Hook，再让 settings store 的 epoch 前进并清空派生缓存；sandbox、Plugin、TUI、provider client 等消费者随后按各自生命周期重新读取、重建或保持旧快照。它解决的是异步慢读把旧值倒灌回新状态的竞态，不是一次全进程事务。完整状态机见 [Settings 解析与热重载](settings-resolution-and-reload.md)。",
        "",
        "### Provider 选择会改写后续能力，而不只改 endpoint",
        "",
        "`--model sonnet` 仍不足以确定 wire request。客户端要先按固定 selector 顺序判 provider，再在该认证域选择实际 model ID、endpoint/region 和 OAuth、API key、bearer 或云凭据，最后决定哪些 beta、prompt-cache、Tool Search、thinking 与 fallback 路径可用。provider selector 的分支位于 [L62740-L62743](../reverse/javascript/cli.readable.js#L62740)；Agent Loop 到 [L271832-L271842](../reverse/javascript/cli.readable.js#L271832) 调用模型层时，已经携带治理后的 messages、system prompt、tools、thinking、effort、cache 和 fallback state。自定义 base URL 能让请求改道，却不能自动继承 first-party account entitlement。",
        "",
        "### 同一个版本为什么在两台机器上像两个产品",
        "",
        "版本号只固定 shipped candidates 和客户端分支，实际 surface 还由 workspace trust、host、平台、账号、远端 feature/config、policy、provider、Plugin/MCP generation 与 session mode 共同决定。Feature Evaluation 的 fresh memory、disk last-known-good 和 baked fallback 也会让断网启动与在线刷新走不同值；但远端实时分桶仍属于 Boundary。排障时要分别检查 `候选 -> trusted/enabled -> advertised` 和 `tool_use -> local registry -> authorized -> executed` 两条链。广告/发现是模型正常获得 schema 的路径，不是本地 dispatch 的唯一存在性证明：精确 Probe 已观察到首请求未广告 LSP schema，但模型直接返回有效 LSP `tool_use` 后，本地 registry 仍完成执行与结果回灌。",
        "",
        "**这一设计的收益与代价：** 晚绑定让同一二进制适配 TUI、SDK、remote、企业 policy、不同 provider 和动态扩展；代价是“安装成功”“列表可见”“请求携带”“用户批准”“外部执行成功”成为五个不同的事实。2.1.235 最鲜明的技术性格之一，就是宁愿显式维护这些中间状态，也不把能力存在性压成一个布尔值。",
        "",
        "## Agent Loop：从按下回车到下一次决策",
        "",
        "前面的三段话容易让人形成一个过于平滑的印象，仿佛客户端只是把用户输入交给模型，再顺序执行三个工具。真实路径更像一条不断交接所有权的流水线：每一步只拥有一种状态，而且失败后不是统一回滚，而是把已经形成的事实交给下一位 owner。下面仍用“把端口改成 9090 并跑测试”，把普通成功路径和一次 API retry 放进同一条时间线。",
        "",
        "| 时刻 | 当前 owner 收到什么 | 它真正改变的状态 | 下一位消费者看到什么 |",
        "| --- | --- | --- | --- |",
        "| `t0` 用户提交 | 原始文本、当前 session leaf | transcript 追加 user message，并为它分配 UUID/parent | request builder 获得一条因果合法的新叶子 |",
        "| `t1` 控制面解析 | settings、env、managed policy、workspace trust、host 与账号状态 | 计算本轮 provider、permission 上限、feature gates 和候选能力 | 请求层得到的是 effective state，不是所有配置文件的简单并集 |",
        "| `t2` 请求装配 | system blocks、message view、memory、agent/skill/MCP、工具候选 | 选择有效历史，计算 cache breakpoint，并把本轮可见工具装进 `tools[]` | 模型只看见此刻被广告的能力图 |",
        "| `t3` API attempt 1 | model、headers、messages、tools、thinking/cache 参数 | 发出一次具体 provider 请求 | transport 若在首个有效 block 前失败，可以在同一 model iteration 内重试 |",
        "| `t4` API attempt 2 | 保留同一轮的业务上下文，换用重试/fallback 决策后的 request 状态 | 新 attempt 获得自己的 request identity；`turnCount` 不因此自动增加 | SSE parser 开始接收 assistant content blocks |",
        "| `t5` Read block 闭合 | 完整 `tool_use{id,name,input}` | streaming executor 固化 concurrency-safe 分类并把 Read 入队 | 模型仍可继续流式输出后面的 Edit/Bash |",
        "| `t6` Edit block 闭合 | 编辑提案及原始 input | unsafe 项建立 drain 屏障；schema、Hook、permission、sandbox 尚未全部通过 | 后续 Bash 不能越过这个写屏障去测试旧文件 |",
        "| `t7` 本地执行 | 通过裁决的 Read/Edit 与各自 `tool_use_id` | 文件读取结果和端口写入成为外部事实；PostToolUse 只能记录或影响后续控制流 | executor 保存可配对的 result，transcript/checkpoint 记录相应投影 |",
        "| `t8` Bash 执行 | 已修改后的工作区和测试命令 | 子进程产生退出码、stdout/stderr，失败本身也是一次真实结果 | 失败被编码成同 ID 的 `tool_result`，而不是让整个 Agent 进程异常退出 |",
        "| `t9` batch drain | 当前 stream 结束，所有已入队工具完成或形成错误结果 | 客户端按调用 ID 组装 result，避免并发完成顺序改变因果配对 | 下一次 model iteration 才能看到这些结果 |",
        "| `t10` model iteration 2 | 原请求上下文 + Read/Edit/Bash 的配对结果 + 排队的新用户输入 | `turnCount` 推进，重新执行上下文治理和 request-time 工具装配 | 模型可以根据测试错误提出第二次 Edit，而不是重放第一批工具 |",
        "| `t11` terminal | 无新 client tool、显式 end-turn、受控停止或 typed failure | transcript 写入最终 assistant/system 状态，外层返回 terminal reason | UI/SDK 得到终态；观测面只收到各通道允许记录的投影 |",
        "",
        "这条账本解释了三个常见错觉。第一，API retry 重做的是一次网络/模型尝试，不等于开启了下一轮 Agent 决策；第二，工具可以在 assistant 仍流式输出时启动，但结果只能进入下一次模型请求，不能逆向写回正在进行的 SSE；第三，测试失败不会让循环“崩掉”，它改变的是模型下一轮可见事实。Claude Code 的连续工作能力并不依赖模型一次规划正确，而依赖客户端能把每次提案、裁决、外部结果和下一轮上下文保持为一条合法因果链。",
        "",
        "### 四个嵌套生命周期单位各算各的账",
        "",
        "![一次用户任务包含模型迭代、API attempt 与工具批次，结果回灌后才决定是否继续](visuals/agent-loop-lifecycle.svg)",
        "",
        f"Agent 系统最容易被讲错的地方，是把一次用户任务、一次模型调用、一次 HTTP 请求和一批工具执行都叫成“一个 turn”。{version} 把这四个嵌套生命周期单位分开，因为它们的重试条件、预算和副作用完全不同。外层 turn wrapper（可读符号 `USe`）接收一个用户任务并产出 terminal reason；core loop（可读符号 `tdf`）从 `turnCount=1` 开始；同一模型轮次内部还可以进入多个 API attempt；一个 assistant stream 又可以交付多个 client `tool_use` 给 streaming executor。主链见 [L271491-L272425](../reverse/javascript/cli.readable.js#L271491)。",
        "",
        "| 计数单位 | 它从哪里开始、在哪里结束 | 什么会推进它 | 为什么不能和别的单位混用 |",
        "| --- | --- | --- | --- |",
        "| 用户 turn | 用户提交任务，到 CLI 返回一个 terminal reason | 完成、取消、受控停止或硬失败 | 一个用户 turn 内可以有多轮模型和多批工具 |",
        "| 模型 iteration | 组装一次有效上下文并让模型决定下一步 | 工具结果回灌、Stop Hook 重入或显式 continuation | `maxTurns` 限制的是它，不是 HTTP 次数或工具数量 |",
        "| API attempt | 一次具体 provider/model/stream 请求尝试 | transport retry、流转非流、model/refusal fallback | retry 可以重发请求，但不一定增加 `turnCount` |",
        "| Tool batch | 同一 assistant 响应中完成的 client `tool_use` 集合 | block 完整后入队，按并发安全性执行并 drain | 一轮可以执行多个工具；完成顺序不决定结果配对 |",
        "",
        "工具执行也不是等整个 assistant message 完全结束后才开始。流式 parser 在 `content_block_stop` 把一个完成的 block 产出为 assistant fragment（[L409843-L409906](../reverse/javascript/cli.readable.js#L409843)）；Agent Loop 看到其中的 client `tool_use` 就立刻 `addTool(...)`，随后 stream/executor race helper（可读符号 `Waf`）在模型流事件和 executor 的 drain tick 之间竞速（[L267292-L267310](../reverse/javascript/cli.readable.js#L267292)、[L272032-L272045](../reverse/javascript/cli.readable.js#L272032)）。这里重叠的是**模型继续流式输出**与**本地工具执行/UI 或 SDK progress**；`tool_result` 不会塞回仍在进行的同一次模型请求。客户端必须等当前 stream 和 executor drain 收尾，才在下一次 model iteration 中把结果送回模型。性能收益来自重叠等待，正确性则依赖完整 block 边界、并发屏障、同 ID 配对和最终 drain，不能简化成一次 `Promise.all`。",
        "",
        "把 `maxTurns=1` 代入贯穿场景就能看清边界：第一轮模型仍可返回 Read、Edit、Bash，三个工具仍按队列规则执行并产生副作用；客户端只是禁止工具结果后的第二轮模型决策，最终给出 `error_max_turns`。精确二进制 Probe 已观察到“工具执行完成、PostToolUse 已发生、服务端只收到一个 Messages 请求”。所以 `maxTurns` 不是工具配额，更不是副作用回滚器；这也是排查“为什么请求次数变多”或“为什么工具做了但没有最终总结”时必须先分清四种计数的原因。完整 Probe 见 [运行证据索引](runtime-probe-index.md) 与 [Agent Loop 专题](agent-loop.md)。",
        "",
        "## 执行控制：模型能提出 Bash，不代表 Bash 会执行",
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
        "candidate name -> factory registration -> enabled local registry",
        "                                      |",
        "                                      +-- advertisement:",
        "                                      |     Tool Search / deferred residency",
        "                                      |     -> request-time tools[]",
        "                                      |     -> normal model discovery",
        "                                      |",
        "                                      +-- dispatch:",
        "                                            complete client tool_use",
        "                                            -> local lookup + schema + Hook",
        "                                            -> permission + sandbox + tool.call",
        "                                            -> paired tool_result",
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
        "继续只看 Edit。模型输出 `Edit({file_path, old_string, new_string})` 时，客户端并没有得到一个“已批准动作”，只得到一份待裁决提案。真正的控制链要连续回答：工具是否存在、输入是否可解释、扩展是否改写了动作、规则是否允许、sandbox 是否能执行，以及副作用发生后怎样把结果交回去。把它们压成一个 permission 布尔值，会同时误判安全边界和故障位置。",
        "",
        "| 阶段 | 谁拥有决定权 | 能改变什么 | 失败后下一轮看到什么 | `tool.call` 是否发生 |",
        "| --- | --- | --- | --- | --- |",
        "| registry / alias lookup | 当前 session 的工具 registry | 把请求名解析到唯一实现；deferred tool 还要区分“存在但 schema 未驻留” | unknown/deferred-tool result，模型可以改名或先发现 | 否 |",
        "| parse、coercion、input schema | 工具 schema 与通用 parser | 把流式 JSON 变成 typed input，拒绝缺字段、错类型和不可解析 JSON | 带具体校验错误的 tool result | 否 |",
        "| custom `validateInput` | 工具实现 | 检查路径、参数组合和工具专属前置条件 | 工具专属 validation result | 否 |",
        "| `PreToolUse` Hook | 用户/管理员扩展 runner | 可以 block、defer，或返回 `updatedInput` | block/defer 进入受控结果；updated input 继续走后续校验 | 否 |",
        "| updated-input revalidation | 通用 schema + permission context | 防止 Hook 改写后绕过 schema；但不会回头重算早已固化的 concurrency-safe 分类 | 新输入非法时明确拒绝 | 否 |",
        "| permission / rule / managed policy / Auto Mode | 本地决策引擎和必要时的人类/分类器 | 给出 allow、ask、deny、scope 与 decision reason；受组织 safety floor 约束 | denial 与来源成为模型的新观察；一次拒绝不会伪装成工具异常 | 否 |",
        "| 工具内部 sandbox 与 OS 权限 | 适用工具、sandbox runtime、操作系统 | 约束文件、网络、socket、credential 和平台权限 | sandbox/TCC/OS error 作为真实执行失败返回 | 可能已开始，但目标副作用未必完成 |",
        "| `tool.call` | Edit/Bash/MCP 等具体实现及其外部 owner | 真正改文件、起进程或调用远端服务 | 成功/失败/partial result，外部状态可能已经改变 | 是 |",
        "| PostToolUse / PostToolUseFailure / 条件性 output revalidation | Hook runner、result mapper、输出合同 | 追加诊断或改写反馈；只有 Hook 返回 `updatedToolOutput` 时才用 `outputSchema` 复验改写值 | 后置错误会影响反馈，但不能撤销已经发生的写入 | 已发生或已尝试 |",
        "",
        "这里最值得注意的不是关卡多，而是**前置裁决与后置观察的权力不同**。PreToolUse、permission 和适用的 sandbox 可以阻止动作到达副作用；PostToolUse、对 Hook 改写输出的条件性复验、tombstone、compact 和 resume 最多改变记录与后续决策。原始 `tool.call` 返回会先进入 result mapper，不能把这条条件分支写成所有原始输出都经过同一个通用 `outputSchema`。`bypassPermissions` 只绕过普通交互审批，不会自动关闭工具内部 sandbox，更不会让 OS 或远端服务放弃自己的权限检查。",
        "",
        "批准 scope 也由独立状态持有。一次性批准只消费当前 Edit；`acceptEdits` 是 session permission mode 的变化，后续同类 Edit 才可能不再询问；managed rule 和 sandbox 又分别存于别的 owner。把对话框关掉、批准一次、切换会话模式和修改持久规则看成同一动作，就解释不了为什么下一次仍然弹框。",
        "",
        "精确二进制 TUI Probe 又验证了一个容易被 UI 文案掩盖的状态差异：Shift+Tab 退出 comment input 不会批准 Edit；随后显式 Enter 只批准第一次 Edit，第二次仍会询问。只有用户用 Down+Enter 选中 session-wide `acceptEdits`，第二次 Edit 才不再弹框。也就是说，“关闭输入框”“批准这一次”“本会话批准同类 Edit”是三个独立状态，不应被归纳成一个 permission 布尔值。见 [TUI 权限 Probe](runtime-probes/tui-regressions.json) 与 [工具控制管线](tools-permissions-hooks.md)。",
        "",
        "### Auto Mode 是确定性下限之上的 verdict 层",
        "",
        "开启 Auto Mode 也不是把批准权交给模型。deny/ask rule、工具 safety check、requires-user-interaction、组织 approval ceiling 和 managed floor 先裁决；只有仍可分类的普通 permission ask 才进入本地 fast path 与两阶段 classifier（[L395300-L395501](../reverse/javascript/cli.readable.js#L395300)）。`acceptEdits` 模拟和 safe allowlist 可以节省分类请求；剩余动作才把整理后的 transcript、当前 tool call、可信规则和有限环境事实送入 Stage 1/Stage 2。project/local settings 不能写 classifier rule，只有 user/flag/policy 三类可信来源能够扩展 `allow/soft_deny/hard_deny/environment`。",
        "",
        "分类器无有效 XML verdict、请求 unavailable 或 safeguard refusal 时，普通工具 fail closed；但 **fail closed 不等于已经判定动作危险**。2.1.235 甚至存在一个边缘路径：Stage 1 已有 usage 但没有有效 verdict，随后 Stage 2 请求异常，失败语义可能落入普通 blocked outcome。遥测或审计若只看 `automode-blocked` 就可能夸大真实策略判断。PermissionDenied Hook 的 `retry:true` 也只让下一轮模型重新提议，原工具仍未执行。完整 Stage 1/2 预算、XML 解析与失败编码见 [Auto Mode 分类器](auto-mode-classifier.md)。",
        "",
        "Plan Mode 则在更早的位置改变 permission mode 和可见工具合同：它允许读取、提问和形成计划，却把实施动作留在 `ExitPlanMode` 之后的人类批准分支。退出计划输入框、模型提出计划、用户批准实施和恢复原 permission mode 是不同状态；Plan Mode 不是一段“请先思考”的 system prompt。sandbox 又位于批准之后：安装成功只证明 runtime 可用，某条 Bash 是否真正受到文件/网络限制仍要看该次 enforcement result。",
        "",
        "Bash 一旦启动子进程，文件、进程和网络副作用就归 OS 或远端 owner。后续 tombstone、compact、resume 只能修复消息表示和本地记录，不能自动撤销已经执行的命令。完整机制见 [工具注册与宿主表面](tool-registration-and-host-surfaces.md)、[Agent Loop](agent-loop.md) 和 [工具控制管线](tools-permissions-hooks.md)。",
        "",
        "## 上下文治理：长对话为什么没有一个万能缓存",
        "",
        "![上下文先复用稳定前缀、延迟工具 schema、局部清理旧结果，最后才全局总结并写恢复边界](visuals/context-control-lifecycle.svg)",
        "",
        "同一个长任务会依次遇到五类不同问题：重复前缀太贵、工具 schema 常驻太大、旧 tool result 挤占窗口、服务端希望提示局部清理、完整历史终于接近有效上限。Claude Code 没有用一个万能“缓存层”解决它们，而是分别改变成本、schema 可见性、active message view、协作协议和逻辑历史。",
        "",
        "先把两条路径分开。普通请求每一轮都会重新建立 effective messages、system blocks 和 request-time tools，再决定 cache breakpoint；它不需要等到窗口告急才工作。只有估算后的输入逼近治理线时，客户端才进入清理旧结果、预计算 summary、发警告、执行 full compact 或最终阻断的临界路径。前者解决重复成本和能力常驻，后者解决窗口容量与可恢复性。",
        "",
        "```text",
        "普通 model iteration",
        "  -> 从 transcript/message graph 取有效分支",
        "  -> 拼 system + user/system context + memory/attachments",
        "  -> 选择本轮完整或 deferred tool schema",
        "  -> 标记 cacheable prefix / message breakpoint",
        "  -> 估算当前 input budget",
        "       |",
        "       +-- 余量充足：直接发请求",
        "       |",
        "       +-- 旧 tool result 可清：microcompaction 后重算",
        "       |",
        "       +-- 逼近阈值：预计算 / warning / full compact",
        "       |",
        "       +-- 超过硬线：阻断本轮输入，不假装 compact 已成功",
        "```",
        "",
        "| 机制 | 它真正改变什么 | 它明确不改变什么 |",
        "| --- | --- | --- |",
        "| Prompt cache | 客户端给稳定 system/message 前缀写 `cache_control`；显式 `ttl=1h` 或省略 ttl 的 wire 形状属于 Static，默认 5m、命中后的计费/延迟收益属于 API/Public 合同 | 不缩短逻辑消息，也不负责 resume；本仓库没有 2.1.235 cache-hit 计费 Probe |",
        "| Tool Search / deferred schema | 请求把候选标为 `defer_loading:true`；模型先得到轻量发现入口，被发现后完整 schema 才进入后续上下文 | 不是把工具缓存到 HTTP body 之外，也不等于未发现工具零 token |",
        "| Context hint | 服务端协作协议提示客户端清理特定工具族旧结果，并对 400/409/422/424/529 与流式错误走不同回退 | 协议启用不等于本地已经清理成功 |",
        "| Local microcompaction | 改写 active message view 中旧的大型 tool result；默认保留最近 5 个相关结果，总节省不足 20k token 时不执行 | 不删除 tool call/ID 因果，也不证明 physical transcript 删除旧事件 |",
        "| Precomputed compact | 在 sidecar/Storage 中提前准备 summary，等真正到 compact line 再校验并交换 | pending/过期/分支不匹配的 summary 不会硬塞进主历史 |",
        "| Manual/reactive group compact | 用 summary、条件性 preserved groups/segments、attachments 与 Hook 结果重写下一次有效 messages | 是否保留取决于分组和路径，不能推广到所有 compact |",
        "| Cold/full compact | 对选中的待总结历史生成 summary，`messagesToKeep=[]` | 不保留 suffix，也不撤销文件、进程、Git 或远端 API 副作用 |",
        "| Transcript + boundary | 保存表示替换关系、UUID 和 logical parent，让 resume 能修复消息链 | 不等于 API prompt cache，也不保存旧进程内存 |",
        "",
        "先看最普通的 manual miss。`PreCompact` Hook 放行且没有可复用预计算结果时，客户端在旧对话末尾插入专用虚拟用户消息，以 `CRITICAL` 要求模型停止业务工作、禁止调用工具，并先输出 `<analysis>` 做时序梳理，再输出固定九段 `<summary>` 作为工程交接。对合规双标签返回，extractor 会用正则剥离首个 `<analysis>`，再把找到的 `<summary>` 改写成 Summary；它不是严格双标签 parser，标签外文本可能保留，缺失 `<summary>` 也不会在这一步自动形成一次严格格式拒绝。这里的 `<analysis>` 是应用层提示词格式，不是模型 API 的原生 thinking；模板和提取路径见 [L261931-L262207](../reverse/javascript/cli.readable.js#L261931)。",
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
        "microcompaction 和预计算 summary 也不能混成一个“缓存命中”。microcompaction 只重写当前 active view 里的旧大型 tool result；预计算则在主任务尚未真正 compact 时生成一份候选 summary sidecar，等到临界点再校验它是否仍对应当前分支。一个省 token，一个把可能发生的 summary 延迟前移，它们持有的对象和失效条件完全不同。主路径分别见 [L263484-L263519](../reverse/javascript/cli.readable.js#L263484) 与 [L262324-L262680](../reverse/javascript/cli.readable.js#L262324)。",
        "",
        "| release-local 条件 | 它防的风险 | 命中时改变什么 | 不满足时回到哪里 |",
        "| --- | --- | --- | --- |",
        "| microcompaction 默认保留最近 5 个相关结果，预计总节省不足 20k token 则不做 | 为很小收益破坏近期工具细节 | 旧大型 result 变成有因果 ID 的占位表示 | 保持原 active view，继续预算判断 |",
        "| sidecar 单文件上限 8,000,000 bytes | 预计算缓存无限增长或异常文件占满本地存储 | 超限候选不成为可复用 summary | 下一次走普通 compact miss |",
        "| sidecar 年龄不超过 7 天，且预计算后新增不超过 150,000 token | 陈旧 summary 套到已经大幅变化的任务 | 校验通过才进入 swap/finalize | 拒绝旧候选并重新总结 |",
        "| 当前消息量不能相对预计算点缩减过半，关键 UUID 必须仍存在 | fork、rewind 或分支变化后错误接续 | preserved UUID 与 `messagesSince` 被接到同一有效链 | 缺 anchor 时按 miss 处理 |",
        "| 连续 3 次可计数失败 | 后台反复预计算造成额外 token、延迟和噪声 | 停止继续 re-arm | 保留普通 reactive/manual compact 能力 |",
        "| 200k window 的示例：约 144k precompute、147k warning、167k compact、177k blocked | 把输出预算、可恢复总结和模型硬输入上限混成同一线 | 依次准备、提示、替换表示、最终拒绝超限输入 | 调小 auto-compact window 只前移前三条线，不等比改变硬阻断线 |",
        "",
        "这些数字只有放回风险模型才有意义。代码先从有效 context window 扣除最多 20k 输出预留，再计算 precompute、warning 和 compact；blocked 则来自模型输入 ceiling 再减 3k。也就是说，自动治理不是“达到某个百分比就总结”，而是先保护模型输出空间，再为总结留出可执行区间，最后保留一条不依赖总结成功的硬阻断线。阈值主路径见 [L216096](../reverse/javascript/cli.readable.js#L216096)；5m/1h cache 成本算例、Context Hint 状态码回退和 provider 差异见 [上下文治理专题](context-governance-and-caching.md)。",
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
        "       +-- hit  -> 不发送新的 summary request -> compact finalize（可读符号 Smi）",
        "       |          合并预计算 preserve UUID + messagesSince",
        "       |",
        "       +-- miss -> 选择合法 message groups -> summary request",
        "                  prompt-too-long 时缩短待总结前缀并重试",
        "  -> compact_boundary + summary / preserved messages / attachments",
        "  -> rebuild next request view",
        "```",
        "",
        "源码在 [L331309-L331345](../reverse/javascript/cli.readable.js#L331309) 先检查 precomputed result：`hit` 直接进入 compact finalize（可读符号 `Smi`）；custom instructions、Hook 追加、sidecar 未就绪或 boundary UUID 缺失都会形成 miss，再进入普通 compact 路径。普通 full summary 请求与 prompt-too-long 缩减逻辑见 [L262996-L263036](../reverse/javascript/cli.readable.js#L262996)。",
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
        "## 观测系统：既要看见运行状态，又不能把遥测当成事实",
        "",
        "![同一运行时信号经过关联与内容控制后，分别进入一方事件、Datadog、OTEL 和本地诊断通道](visuals/telemetry-pipeline.svg)",
        "",
        f"“Claude Code 有没有遥测”是一个过于粗糙的问题。{version} 至少要分开 Anthropic 一方事件、Datadog forwarding、用户或管理员配置的 OTEL，以及本地 debug/profile/doctor。它们会观察同一次 query、tool、permission、compact 或 error，但拥有不同 gate、字段、队列、目的地和失败语义。关闭其中一条，不代表其他通道同时关闭。架构上更重要的判断是：运行时先发生状态变化，再把不同投影 best-effort 地送往不同 sink；遥测从来不是那份状态本身。",
        "",
        "仍用测试失败来走一遍真实次序。Bash 子进程先退出并形成 `tool_result`，这是业务链上的事实；随后调用点才构造事件名、duration、outcome 和关联字段。事件先经过通道自己的 enable/sampling/content gate，再进入 queue/exporter。即使 exporter 失败、事件被采样掉或正文被 redaction，Bash 结果仍会回到 Agent Loop，模型照样可以继续修复。反过来，collector 看见一条工具事件，也只能证明某个客户端投影曾被发送，不能替代 transcript、文件状态或远端事务 readback。",
        "",
        "```text",
        "Bash 真实退出",
        "  -> tool_result 写回执行链",
        "  -> event payload 读取 outcome + correlation IDs",
        "  -> enable / sampling / content gate",
        "  -> first-party logger -----+----> optional Datadog allowlist/redaction",
        "  -> OTEL signal pipeline ---+----> user/admin collector",
        "  -> queue / batch / export / retry-or-drop",
        "",
        "Agent Loop 只消费 tool_result，不等待这些观测 sink 成功",
        "```",
        "",
        "先看字段怎样把贯穿场景串起来。`session_id` 标识可恢复会话；`queryChainId/query_chain_id` 把同一次执行链关联起来，`queryDepth/query_depth` 随 model iteration 增加而在同一 iteration 的 API retry 中保持；`request_id` 绑定具体 API 响应尝试；`tool_use_id` 把工具提议和结果配对；`turn_count` 只在需要表达 Agent Loop 轮次的事件中出现。循环状态从 `turnCount=1` 和新的 chain/depth 开始（[L271553-L271643](../reverse/javascript/cli.readable.js#L271553)），终止事件再写 `terminal_reason`，并仅在 max-turns 场景附带 `turn_count`（[L270840-L270845](../reverse/javascript/cli.readable.js#L270840)）。",
        "",
        "<details>",
        "<summary><strong>展开 session/query/request/tool/turn 五类关联字段的边界</strong></summary>",
        "",
        "| 关联字段 | 它回答的问题 | 为什么仍不能当成完整分布式 trace |",
        "| --- | --- | --- |",
        "| `session_id` | 这条记录属于哪份可 resume 的本地会话 | fork 会产生新 session；远端系统未必沿用同一 ID |",
        "| `queryChainId` / `queryDepth` | 同一用户任务里这是第几次模型决策链 | 事件级 sampling、drop 或某通道关闭会造成缺段 |",
        "| `request_id` | 哪一次具体 API attempt/response 出现延迟、拒绝或 fallback | client retry 前后的 request ID 可以不同；服务端内部 span 不在 bundle 中 |",
        "| `tool_use_id` | 哪个 client tool 提议对应哪个 `tool_result` | MCP/远端 effect owner 可能还有自己的事务 ID |",
        "| `turn_count` | maxTurns 等终止判断发生在第几次 model iteration | 并非每个事件都携带，不能拿事件数反算完整轮次 |",
        "",
        "</details>",
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
        "`tengu_other` 只是本仓库按事件名前缀生成的兜底桶，不是客户端里的统一“其他功能”模块；未绑定到确切 caller 的条目继续是 Unresolved，不能从邻近代码或事件名猜业务 owner。完整分类数量和剩余欠账见 [Telemetry 场景索引](telemetry-event-catalog.md)。",
        "",
        "<details>",
        "<summary><strong>展开 caller-owner 纠错为何必须使用 exact identity</strong></summary>",
        "",
        "旧投影曾按巨大源码行区间给 caller 归 owner，导致邻近的 EndConversation、heap dump、update refused 等路径错误继承同一业务标签。当前映射只接受 event + exact caller identity + comparison fingerprint 同时命中。这个研究过程不改变 runtime，但它阻止排障者把一条观测记录送到错误的状态 owner。",
        "",
        "</details>",
        "",
        "最关键的架构判断是：具体 event 的 emit、queue 和 exporter 是有损、分叉、best-effort 的 sink，不是系统事实的唯一账本，也不拥有 retry/compact/supervisor 的控制决定。事件缺失不能证明动作没发生；事件出现也不能证明远端 collector 已确认写入。但共享的 telemetry/nonessential-traffic enablement 同时是控制面的输入：例如关闭相关流量会让在线 GrowthBook Feature Evaluation 不启动，并进入磁盘/本地 fallback。必须区分“出口发送失败不反向支配 Agent Loop”和“流量开关会改变哪些在线控制能力可用”。",
        "",
        "## 恢复语义：Resume 恢复因果视图，不是旧进程",
        "",
        "![消息图和文件检查点分别支持 resume、fork 或 rewind，外部状态留在统一回滚边界之外](visuals/session-recovery-lifecycle.svg)",
        "",
        "继续贯穿场景：Claude 已经编辑配置并启动测试，用户在发布 Artifact 之前退出 CLI。再次启动时，“继续工作”不是把旧进程冻结后解冻，而是由多个 owner 各自恢复自己掌握的对象。resume entry（可读符号 `Bet`）先解析来源、Storage/JSONL 路径与 fork 语义，再把消息交给 interrupted-turn 修复器（[L323373-L323423](../reverse/javascript/cli.readable.js#L323373)）；真正的消息图恢复在另一组函数里完成。",
        "",
        "先用一个六节点的小图理解恢复对象。物理 JSONL 按写入顺序保存事件，但下一次送模必须得到一条逻辑父链：",
        "",
        "```text",
        "U1 用户要求改端口",
        "  -> A1 assistant 同批提出 Read/Edit",
        "       -> R1 Read result",
        "       -> R2 Edit result",
        "            -> B1 compact_boundary(summary, preserve=[A1,R1,R2], anchor=U1)",
        "                 -> U2 compact 后的新问题   <- 当前 leaf",
        "",
        "另一条已放弃分支：A_old -> R_old   （仍可能留在物理 transcript）",
        "```",
        "",
        "恢复分五步，而不是读取末尾 N 行：",
        "",
        "1. transcript graph loader（可读符号 `C6e`）扫描事件，把它们装成 `uuid -> node` 与 parent map，同时收集显式 leaf、last-prompt、rewind 和 session 元数据（[L403569-L403650](../reverse/javascript/cli.readable.js#L403569)）。",
        "2. compact-boundary relinker（可读符号 `H$i`）找最近有效 boundary，把 `preservedMessages/preservedSegment` 接回它声明的 anchor；compact 前但不再属于有效表示的节点不会继续进入 active view（[L402489-L402531](../reverse/javascript/cli.readable.js#L402489)）。",
        "3. ancestor walker（可读符号 `A_t`）从选中 leaf 逆着 `parentUuid` 回走并检测环；父节点缺失时只在受控条件下使用时间戳 fallback，而不是随便拼最后几条（[L402554-L402667](../reverse/javascript/cli.readable.js#L402554)）。",
        "4. 同一次 API message 中并行产生的 assistant fragments 和 tool results 要作为组补回，否则会留下孤立 `tool_use` 或孤立 `tool_result`，违反 Messages 协议。",
        "5. 顶层 resume 再过滤损坏 attachment、已撤回分支和中断残片，才把有效链交给新的 Agent Loop；file rewind 另走 checkpoint 路径（[L194641-L194804](../reverse/javascript/cli.readable.js#L194641)）。",
        "",
        "| 可恢复对象 | owner 与恢复动作 | 恢复后的状态 | 仍然丢失或保留什么 |",
        "| --- | --- | --- | --- |",
        "| Message graph | session ID、message UUID、parent/logical parent、branch leaf | resume/fork 得到一条因果合法的有效消息链 | 不会重新执行历史工具，也不恢复旧 socket/Promise |",
        "| Compact boundary | summary、preserved UUID、logical parent 与相关元数据 | compact 前后表示能在同一逻辑会话中接续 | summary 没写到的细节不能凭空恢复；prompt cache 命中也不保证延续 |",
        "| File checkpoint | file history owner 保存受管文件快照/差异；本版最多保留 100 个 checkpoint | dry-run 可先算 diff，rewind 再恢复被跟踪文件字节 | Bash 改的未跟踪路径、symlink 例外、数据库和远端对象不在合同内 |",
        "| Artifact reference | Artifact owner 保存 slug/version 或错误结果 | 可信响应后可继续查询具体版本 | timeout 后 reference 不证明提交或回滚 |",
        "| Background task | task registry/daemon/remote owner 保存 task/job identity | owner 仍存活时可 attach、stop、poll 或接收通知 | 只有 transcript metadata 不能复活旧进程 Promise |",
        "| MCP/remote result | MCP client 与外部 server 各持连接/事务身份 | 客户端可重新连接、重列能力或读取明确暴露的结果 | 本地 checkpoint 不拥有外部 server 的回滚语义 |",
        "",
        "<details>",
        "<summary><strong>展开 Resume 图损坏与 checkpoint 缺失的恢复矩阵</strong></summary>",
        "",
        "| 恢复异常 | 客户端怎样处理 | 保留下来的状态 | 用户最终风险 |",
        "| --- | --- | --- | --- |",
        "| parent 环或非法自指 | 停止把该链当作合法 ancestor path | 物理事件仍可供诊断 | 该分支不能完整 resume |",
        "| parent 缺失 | 仅按实现允许的 timestamp fallback 尝试修复 | 可证明顺序的节点 | 无法证明的上下文被丢弃，而不是编造父链 |",
        "| 损坏 attachment | 从有效送模视图过滤 | transcript 中其他合法消息 | 精确文件材料可能缺失，需要重新读取 |",
        "| 中断的 tool pair | 按 interrupted-turn/tombstone 规则修复表示 | 已完成外部副作用仍存在 | 模型可能需要先检查文件/远端状态再继续 |",
        "| checkpoint 缺失或路径不受管 | file rewind 无对象可恢复 | 会话消息仍可 resume | 文件、数据库、Git 或远端写入必须单独补偿 |",
        "",
        "</details>",
        "",
        "精确二进制 Probe 把这两个恢复面分开证明：在该受控 compact 样本中，fork 生成新 session ID，请求含 summary 与当前 prompt，不含样本指定的旧 prompt、旧 tool-use ID 和旧 assistant result；这不能外推为所有 preserved-group 路径都只保留相同集合。file rewind 则在不发送任何 Messages 请求的情况下，把受管临时文件从修改值恢复为原始字节。它说明 rewind 是本地 checkpoint 驱动的补偿操作，不需要模型生成反向 Edit，也不涵盖 Git push、Artifact 部署、数据库写或已发送消息。完整恢复矩阵见 [Session/Checkpoint/Memory](sessions-checkpoints-memory.md)。",
        "",
        "所以“状态可续”是一个有类型的承诺：消息图续消息，checkpoint 续文件，各子系统的 remote reference 只续自己明确支持的补偿线索。它的优势是无需保存整个 Bun 进程和远端世界的快照；代价是任何“恢复成功”报告都必须同时说明恢复了哪个对象，以及哪些外部副作用仍然存在。",
        "",
        "## 动态扩展：MCP、Skills 与子 Agent 不是往主循环里塞更多名字",
        "",
        "贯穿任务再加一个真实需求：测试失败后，主 Agent 要查询一个 MCP 文档工具，并让子 Agent 在独立 worktree 复核修复。表面上只是“多两个工具”，底层却新增了三种生命周期：MCP connection/catalog 的 generation、子 Agent 自己的 Agent Loop，以及父子之间的 task/notification 协调。它们不能共享一份巨大 context，否则工具 schema、探索噪声、权限和失败状态会互相污染。",
        "",
        "![MCP 动态目录进入主循环，子 Agent 执行隔离任务，再通过通知回到父循环](visuals/mcp-agent-lifecycle.svg)",
        "",
        "### MCP 的 connected 只证明 transport，不证明模型已经能调用",
        "",
        "MCP 配置先经过来源、workspace trust、strict/managed filter、command/URL/header helper 校验和 OAuth/credential 状态；连接后才列 tools/resources/prompts。server 发出 `tools/list_changed` 或发生重连时，客户端刷新 catalog generation，并让依赖旧 generation 的 Tool Search schema cache 失效。动态列表刷新位于 [L491915-L491964](../reverse/javascript/cli.readable.js#L491915)，Agent Loop 在工具批次收尾进入下一轮前再检查 generation（[L272372-L272382](../reverse/javascript/cli.readable.js#L272372)）。",
        "",
        "这条时序刻意不热改已经发出的 Messages request。若 server 在当前模型流期间新增工具，本轮模型仍按旧能力图完成；下一轮 request assembly 才可能广告新名称，Tool Search 命中后完整 schema 又可能更晚进入上下文。于是 `server connected -> catalog refreshed -> name discoverable -> schema resident -> input authorized -> remote call completed` 是六个不同状态。用 connection 绿灯解释“模型为什么不会用”通常会查错层。",
        "",
        "### 子 Agent 复用循环，不共享父 Agent 的脑内现场",
        "",
        "子 Agent 会创建独立 messages、context window、tools、model/effort/maxTurns、permission context、abort controller，以及可选 cwd/worktree/transcript。2.1.235 的默认 fork 配置是 `maxTurns: 200`、`model: inherit`、`permissionMode: bubble`（[L156505-L156518](../reverse/javascript/cli.readable.js#L156505)）：继承 model 不等于共用一次 API call；bubble 只表示无法本地裁决的审批可以上浮，不等于子 Agent 自动获得父会话全部权限。",
        "",
        "父 Agent 调用异步子任务时，最先收到的 `async_launched` 只是登记成功和 task identity，不是复核结论。子 Agent 完成后，progress/completed notification 进入父队列；父循环在下一次请求前吸收，才把 findings 变成新的模型观察。精确二进制 Probe 已验证子请求不含父 prompt、拥有自己的工具表，父循环先收到 launch ACK，后收到完成通知。这个分离能把大规模搜索噪声留在子 context，但也会重复 system/tool token，并产生结果压缩与协调成本。",
        "",
        "### Task、mailbox 与 worktree 只解决各自那类冲突",
        "",
        "Task registry 的 claim 让一个任务有明确 owner/status/dependency，避免两个 teammate 都以为自己领取成功；team mailbox 负责消息、broadcast、shutdown/request/response 和 ack；worktree 隔离 Git 文件视图。三者都不是全局隔离：两个不同 task 仍可能碰同一数据库、端口、缓存、credential 或远端 API，worktree 也不会复制这些共享资源。claim 主链见 [L202474-L202511](../reverse/javascript/cli.readable.js#L202474)，mailbox 状态机见 [L279171-L279317](../reverse/javascript/cli.readable.js#L279171)。",
        "",
        "后台 Agent 又多一层进程所有权。Agent View 只是展示和控制投影；daemon supervisor、PTY host、Claude worker、rendezvous 与 Storage job record 分别持有进程、终端字节、Agent Loop、控制状态和持久任务元数据。resume 一份 transcript 不会复活旧进程内的 Promise；只有真正 durable 的 owner 仍在，attach/respawn 才有对象可接。完整冷启动、socket auth、ring/backpressure、heartbeat、respawn budget 与 memory-pressure reap 见 [Runtime Supervision](runtime-supervision-and-processes.md)。",
        "",
        "**这一设计为什么不能更简单：** 动态扩展既要随 server/Plugin/Agent 变化，又不能把旧 schema、父级秘密上下文和未经批准的权限无限传播。2.1.235 用 generation 隔离时间，用独立 context 隔离推理，用 permission bubble 隔离授权，用 task/mailbox 隔离协调，用 worktree 隔离文件。收益是可扩展与可并行；代价是更多 token、更多状态 owner，以及“启动成功不等于完成、连接成功不等于可调用、文件隔离不等于资源隔离”的排障复杂度。",
        "",
        "## 远端副作用：Artifact 超时后，客户端为什么只能得到结果未知",
        "",
        "![Artifact direct publish 把兼容重试、容量重试、冲突、可信成功和结果未知分开处理](visuals/artifact-direct-publish-outcomes.svg)",
        "",
        "resume 后，Claude 重新核验文件与测试状态，再发布一份 HTML 报告。Artifact 的完整发布协议还包含本地文件身份、staged upload、commit/version 和 stale guard；这里故意只拿其中的 direct-publish route 做压力测试，因为一次超时足以暴露本地 Agent 无法拥有远端事务真相。",
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
        "| 返回/失败 | 为什么重试或停止 | 本地 known version | 客户端能否确定远端结果 | 用户恢复动作 |",
        "| --- | --- | --- | --- | --- |",
        "| `2xx` + 合法 schema + slug 相等 | 获得可信响应，结束 | 采用服务端返回 version | 只能确认该响应描述的提交；页面渲染仍需另证 | 继续使用返回的 slug/version |",
        "| `400` 且明确拒绝旧 `force/baseVersion` 字段 | 只做一次兼容性降级，删除被拒字段后重发 | 成功前不更新 | 第一次请求是否被服务端部分处理仍取决于远端实现 | 看第二次响应；不能把兼容重试当原子替换 |",
        "| `409` + `liveVersion` | 冲突是业务状态，不盲重试覆盖 | 保留原本地认识，同时返回 live version | 可以确认服务端报告存在并发版本 | 重读/比较后决定是否再次发布 |",
        "| `429` | 读取 `retry-after`，等待上限 30 秒，只重试一次 | 成功前不更新 | rate limit 不说明第一次是否进入后续处理 | 等待有界重试结果 |",
        "| `503` | 按 attempt/backoff 最多 3 次总尝试 | 成功前不更新 | 每次失败都只说明没有可信成功响应 | 预算耗尽后停止自动重发 |",
        "| timeout、relay error、malformed response、slug mismatch | 缺少可采信的提交回执，函数终止 | 不采用未知 version | **未知**；请求可能在客户端放弃等待前已到达远端 | 先 list/readback，再决定是否人工重试 |",
        "",
        "这里必须把四种合同分开。response schema validator（可读符号 `RBa`）校验 slug/version 形状；客户端只对目标 slug 做 equality check；服务端返回的 version 被直接采用并写入本地 known version，不做 local-version equality；timeout、relay error、malformed response 或 slug mismatch 后的“check the artifact list”只是错误合同里的 **advisory**，不是客户端自动强制执行 list/read gate。证据见 [L260784-L260808](../reverse/javascript/cli.readable.js#L260784) 与 [L261085-L261090](../reverse/javascript/cli.readable.js#L261085)。",
        "",
        "超时最麻烦的地方，不是错误文字，而是它发生在请求发送之后：客户端知道自己没有拿到可信响应，却不能仅凭这一事实断言服务端没有提交。如果贸然重试，可能重复写；如果完全不重试，又可能把一次可恢复的传输失败变成用户可见失败。2.1.235 因而按 400/409/429/503 分类采取有界策略，而没有一个笼统的“网络错误重试”开关。在这条 direct-publish request 的可见 body/header 中没有恢复出独立 idempotency key；slug、baseVersion、force 和 conflict 分支提供身份/并发控制，但不能据此宣称所有 timeout 重试天然幂等。",
        "",
        "这揭示了 Agent runtime 的另一条不变量：**恢复是局部控制器和补偿动作的集合，不是全局事务。** CLI 能做的是限制重试、暴露 conflict、在可信响应后更新本地 known version、保留 slug/version/reference，并在结果未知时给出 readback 建议；它不能凭本地 transcript 宣布远端已提交或已回滚。当前结论主要来自 Static 可达路径，没有一条真实远端 Artifact 成功 Probe，因此远端持久化仍是 Boundary。完整 owner 表见 [API/Beta 路由所有权](api-beta-route-ownership.md) 与 [Workflow/Artifact/Design](workflow-artifact-design.md)。",
        "",
        "## Native Bridge：CLI 不只有文本，也不能把 ABI 当成原始源码",
        "",
        "![JavaScript consumer 经 N-API 进入 Rust、Swift 与 macOS framework，再把结果或错误返回客户端](visuals/native-bridge-lifecycle.svg)",
        "",
        "Claude Code 把图像处理/剪贴板、截图与应用发现、键鼠输入、音频采集和 URL event 等 macOS 能力放进 5 个同进程 `.node` bridge，而不是统一交给外部 helper。这样减少 IPC，并能直接复用 N-API 与系统 framework；代价是 ABI mismatch、线程回调、panic/finalizer 和 TCC 错误更靠近 CLI 主进程，真实点击、录音和屏幕读取也不受 transcript 回滚控制。",
        "",
        "[`runtime-requires.txt` 第 1 行](source-inventory/runtime-requires.txt#L1)记录 `/$bunfs/root/audio-capture.node`，可读 JavaScript 也保留 embedded require（[L54](../reverse/javascript/cli.readable.js#L54)）。这只能证明发布物包含装载入口，不能直接推出当前机器加载成功、麦克风已授权、设备可用或 native 内部采用了某种精确重采样算法。",
        "",
        "### 一次 Voice 输入真正经过了什么",
        "",
        "用户按住语音键后，声音不会直接变成一条发给模型的 user message。Voice 是独立于 Agent Loop 的 `本地采集 -> 远端 STT -> composer 文本` 管线；只有转写文字随后被提交，模型才会看到它。普通路径先完成账号/capability、本地音频环境、录音依赖、麦克风权限和 settings 等 gate；无设备的 remote/cloud 环境会在这里失败，而不是先连服务再假装能够录音（[命令与环境 gate](../reverse/javascript/cli.readable.js#L362598)、[设备检查](../reverse/javascript/cli.readable.js#L362522)）。",
        "",
        "开始录音后，客户端并行启动 recorder 与 Voice WebSocket。录音后端优先 lazy-load `audio-capture.node`；JS wrapper 只把 native callback 的 bytes 原样上抛，不能据此断言 native 内部怎样重采样。native 不可用时才退到 SoX `rec`，明确请求 16 kHz、mono、signed 16-bit raw PCM。两条分支共用同一个 chunk callback，所以下游协议不需要知道音频来自 native 还是 SoX（[native bridge](../reverse/javascript/cli.readable.js#L362418)、[SoX 分支](../reverse/javascript/cli.readable.js#L362546)）。",
        "",
        "录音可以早于 WebSocket ready。连接前的 chunk 进入内存 queue；连接成功后，客户端把它们合并为有界 frame 顺序 flush，并周期发送 KeepAlive（[连接协议](../reverse/javascript/cli.readable.js#L362289)、[buffer/flush](../reverse/javascript/cli.readable.js#L525811)）。interim/final 先更新 Voice/composer state；录音结束后，final transcript 进入 composer callback，interim 与 audio buffer 被清空，再回到 idle（[转写累积](../reverse/javascript/cli.readable.js#L525839)、[最终注入](../reverse/javascript/cli.readable.js#L525725)）。取消录音会丢弃本次 buffer；未提交的 composer 文本不会进入普通 Agent Loop。",
        "",
        "### 失败不是统一的 Voice error",
        "",
        "无 transcript 的早期连接错误只做有界重连并保留尚未发送的 queue；检测到音频却 finalize 为 no-data 时，只允许新连接重放缓存一次；已有文字后的中途错误尽量 salvage 当前 transcript，再结束录音，而不是无限重传（[early retry](../reverse/javascript/cli.readable.js#L525875)、[silent-drop replay](../reverse/javascript/cli.readable.js#L525687)、[partial salvage](../reverse/javascript/cli.readable.js#L525884)）。load failure、TCC 拒绝、设备失败、socket 失败和 no-speech 因而属于不同 owner。更严重的是，同进程 native crash 可能带走 CLI 本身；这正是低 IPC 与更大故障半径之间的取舍。",
        "",
        "### 能恢复 ABI 合同，不等于找回原始函数体",
        "",
        "Native 证据必须分层。Mach-O 依赖、符号、字符串、反汇编、JS wrapper、SoX argv 和 WebSocket query 都是 Static artifact；受控 original/compatible 调用才是 Probe；独立重写的 Rust/Swift 只是 Compatible。当前 arm64 报告只对列出的受控输入比较 export、返回/throw/null 和生命周期，不会真的录音、注入键鼠或证明所有平台权限组合。",
        "",
        "x86_64/Rosetta 报告进一步证明：现存的 5 个 compatible artifact 是独立 regular x86_64 Mach-O、不是原版同哈希复用，并能在 x64 Node/Rosetta 下加载和满足导出合同；只有发布物自身带 x86 slice 的 Input/Swift 两模块还能做同输入行为对照。报告里的 Rust/Swift command 目前是 **build recipe**，没有同次 build 的 literal output 和 exit status，因此方法必须写成 `validated-artifacts-and-runtime`，不能宣称这些文件由该次报告运行新鲜编译。audio、image、URL 又没有 original x86 slice，更不能从 compatible-only 结果外推原版 x86 行为。",
        "",
        "bundle 能证明 recorder callback bytes 会进入声明 `linear16/16000/1` 的 Voice WebSocket 合同、文字怎样回到 composer，以及客户端怎样清理和补救；它不能据此证明 native callback 前的原始采样/重采样细节，也不能证明服务端留存、训练或删除策略。缺失源码级调试信息后，同样不能恢复原版 native 的内部滤波/重采样函数。完整模块/架构/受控输入矩阵见 [Native Bridge](native-bridge-runtime.md) 与 [原生重建报告](../reconstructed/README.md)。",
        "",
        "## 这些机制共同暴露出的工程选择",
        "",
        "下面七条是从本版调用链归纳出的 **Derived synthesis**，不是源码原生模块名。每条都必须能回扣到前文至少两个机制，否则就只是任何 Agent 产品都能套用的口号。",
        "",
        "**第一，能力被逐请求编译，而不是随安装包一次确定。** Workspace trust 决定项目扩展能否进入 registry，settings/policy/provider 决定能力上限，MCP generation 与 Tool Search 决定 schema 何时进入请求，permission/sandbox 决定具体 input 能否落地。收益是同一个二进制可以服务 TUI、SDK、remote、企业策略和不同 provider；新增复杂度是一个功能可能处于 candidate、enabled、advertised、authorized、executed 五种状态。排障原则：先问断在哪次状态转换，不要先问“这个版本有没有”。",
        "",
        "**第二，自主性来自反复提案，安全性来自权力不对称。** client `tool_use` 要穿过本地 registry、Hook、policy、permission、Auto Mode 和适用 sandbox；`server_tool_use` 留在服务端生命周期；文件系统、OS、MCP 与 Artifact 服务拥有最终副作用。收益是模型能持续决定下一步，却不能靠生成文本自行获得执行权；代价是“模型说做了”“客户端允许了”“外部系统提交了”必须分别验证。",
        "",
        "**第三，Agent Loop 是带四种时钟的因果反馈器，不是一个 `while(true)`。** 用户 turn、model iteration、API attempt 与 tool batch 有不同的预算、重试和终态；完整 block 可以让工具与模型流重叠，unsafe barrier 又保护文件时序，结果只能进入下一次 iteration。收益是低延迟和持续纠错；代价是 `maxTurns`、请求数、工具数和事件数不能互相替代。排障时必须先确定卡住的是哪只时钟。",
        "",
        "**第四，事实与表示被刻意分开。** prompt cache 改重复输入的服务合同，Tool Search 改 schema 驻留，microcompaction 改 active view，full compact 改逻辑历史表示，transcript/boundary 记录怎样重建；这些机制都不会改写已经发生的文件、子进程或远端提交。收益是上下文可以被压缩、分叉和恢复；风险是 UI 中“历史少了”很容易被误读成“世界回滚了”。",
        "",
        "**第五，恢复按对象负责，可靠性来自有限重试与补偿线索。** request retry、stream fallback、compact、tool tombstone、file rewind、daemon respawn、MCP reconnect 和 Artifact conflict 各自持有局部状态与预算。没有统一 recovery manager 可以同时倒回 transcript、文件、进程和远端对象。收益是每个控制器可以针对自己的错误分类；代价是 timeout 后常见的正确结论是“结果未知”，下一步必须 readback，而不是机械重放。",
        "",
        "**第六，扩展能力靠隔离与 generation，而不是共享一个更大的脑。** MCP catalog 用 generation 避免旧 schema 永久驻留，子 Agent 用独立 context/model/tools/permission，task/mailbox 管协调，worktree 只隔离文件，supervisor 另管跨终端进程。收益是并行探索和动态扩展；代价是额外 token、通知延迟、权限上浮和共享资源冲突。并行前要先判断任务是否真正独立，而不是看到 Agent 工具就拆。",
        "",
        "**第七，观测出口与控制输入相邻但不等价。** analytics、Datadog、OTEL 和 debug 读取运行时投影，单次 emit/export 失败不拥有 Agent Loop；sampling、redaction、queue 和发送失败会让事件天然有损。与此同时，共享的 telemetry/nonessential-traffic gate 会影响在线 Feature Evaluation 等控制面能力。排障既不能把事件库当作唯一真相，也不能假设“关闭遥测”只减少日志而不改变任何在线配置路径。",
        "",
        "这些选择形成了本版很具体的工程取舍：Claude Code 接受更多局部状态机、generation、因果 ID 和边界条件，来换取流式低延迟、动态能力、跨进程连续性与不同信任域的隔离。复杂度没有消失，也没有被模型智能吞掉；它被分配给真正拥有状态的客户端和外部组件。",
        "",
        "## 把 C/Q/E/S/O 留作阅读索引",
        "",
        "C/Q/E/S/O 是本文的 Derived 分析框架，不是源码目录图，也不是 Anthropic 官方架构或命名。它按最终决定权分面，同一功能可以跨多个面；恢复也不是统一的第六层，request retry、stream fallback、compact、tool tombstone 与 process supervisor 都留在各自 owner 的局部回路中。O 面中的 event sink 不拥有业务控制，但 telemetry enablement 本身同时属于 C 面输入，能够改变在线 Feature Evaluation 等路径。",
        "",
        "把贯穿任务代入就够了：C 面先根据 trust/settings/policy/provider 编译能力上限；Q 面把有效历史、cache marker 和本轮 tools 装成一次 request；E 面只执行获准的 client tool，并把结果配回原 ID；S 面把消息图、boundary、checkpoint 和 task reference 持久化；O 面异步记录允许观测的投影；文件、进程和 Artifact 服务仍是外部 effect owner。五个字母只是帮助定位“谁做最终决定”，不是让读者再背一套架构。",
        "",
        "![Derived 阅读模型：控制约束请求，本地 Agent Loop 执行 client tool_use，server_tool_use 留在服务端，各 owner 在局部回路恢复，event sink 接收有损投影](visuals/product-surface-runtime-planes.svg)",
        "",
        "<details>",
        "<summary><strong>展开 C/Q/E/S/O 的 owner、决定权和专题入口</strong></summary>",
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
        "</details>",
        "",
        "外部副作用不属于本地状态面。执行器把动作交给文件系统、子进程、浏览器、MCP、GitHub、Artifact 或其他远端 owner 后，本地最多保存结果、remote ID/reference、checkpoint 与补偿线索。这里不存在一个能同时撤销 transcript、文件和远端对象的全局事务。",
        "",
        "## 按问题继续阅读",
        "",
        "- 模型为什么会继续调用工具、并发为什么有屏障：读 [Agent Loop](agent-loop.md) 与 [工具控制管线](tools-permissions-hooks.md)。",
        "- `/compact` 为什么只改变送模历史、不撤销文件：读 [上下文治理](context-governance-and-caching.md)、[图文专题](compact-visual-guide.md) 与 [Session/Checkpoint/Memory](sessions-checkpoints-memory.md)。",
        "- 一个开关为什么写了却不生效：读 [Settings/Policy](settings-feature-flags-policy.md)、[环境变量逐项参考](environment-variable-reference.md) 和 [Feature key 逐项参考](feature-flag-reference.md)。",
        "- 陌生项目为什么先看不到 Hook/MCP，provider 又怎样改变请求能力：读 [Workspace Trust](onboarding-workspace-trust-and-safe-startup.md)、[Settings 热重载](settings-resolution-and-reload.md) 与 [模型/认证/Provider](models-auth-providers-request.md)。",
        "- 一次权限批准怎样穿过 Hook、policy、sandbox 和 TUI scope：读 [工具控制管线](tools-permissions-hooks.md) 与 [TUI/媒体/IDE](tui-input-accessibility-media-ide-chrome.md)。",
        "- MCP 已连接为何仍不可调用、子 Agent 启动为何不等于已有结果：读 [MCP/Agents/后台协作](mcp-agents-background.md) 与 [Runtime Supervision](runtime-supervision-and-processes.md)。",
        "- 远端发布 timeout 后怎样区分可重试、冲突和结果未知：读 [Workflow/Artifact/Design](workflow-artifact-design.md) 与 [API/Beta 路由所有权](api-beta-route-ownership.md)。",
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
        "## 证据、完成度与机器清单放在哪里",
        "",
        "正文到这里结束。它只负责解释已经串起 caller、gate、state delta、failure/recovery 与 Boundary 的机制，不再用文件数、事件数、flag 数或 claim 数制造“全面”的观感。",
        "",
        "精确的 inventory 文件集合、canonical hash、提取来源、代码所有权、证明层级、C/Q/E/S/O 路由和当前语义欠账，集中放在 [机器证据索引](product-surface-inventory-index.md)。逐能力的 `Deep / Inventory only / Boundary` 状态放在 [全面性审计](completeness-audit.md)。这三层必须分开：机器清单防漏，机制 registry 约束强结论，人工 consumer tracing 才能说明行为真的被理解。",
        "",
        "**最终边界：** 客户端 bundle 能证明 shipped bytes、可达分支、默认值、状态字段和本地协议；精确二进制 Probe 只能证明受控输入触发的路径；服务端实时配置、账号 entitlement、模型内部判断、远端持久化、第三方实现和缺失的原始 TypeScript/Rust/Swift 源码仍是 Boundary。`Untraced/Inventory only` 表示客户端证据仍可继续追，不得为了宣称完成而改写成 Boundary。",
        "",
    ])
    return "\n".join(lines)


def build_inventory_index(repo: Path) -> str:
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    summary = json.loads(
        (repo / "analysis/source-inventory/summary.json").read_text(encoding="utf-8")
    )
    inventory_names = [Path(entry["path"]).name for entry in summary["files"]]
    evidence_records = [
        json.loads(line)
        for line in (repo / "analysis/mechanism-evidence.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    evidence_class_counts = {
        evidence_class: sum(
            record.get("evidenceClass") == evidence_class
            for record in evidence_records
        )
        for evidence_class in ("Static", "Probe", "Public", "Boundary")
    }
    environment_summary = read_generated_summary(
        repo,
        "analysis/environment-variable-reference.md",
        "ENVIRONMENT_VARIABLE_REFERENCE",
    )
    feature_summary = read_generated_summary(
        repo,
        "analysis/feature-flag-reference.md",
        "FEATURE_FLAG_REFERENCE",
    )
    telemetry_projection = read_telemetry_projection(repo)
    lines = [
        f"# Claude Code CLI {version} 机器证据索引",
        "",
        "> 这是一份确定性审计页，不是技术文章。先读 [本地执行系统解剖](product-surface-evidence-map.md)，需要复核覆盖和跨版本差异时再回到这里。",
        "",
        "## 当前语义收口状态",
        "",
        f"[`summary.json`](source-inventory/summary.json) 注册 {len(inventory_names)} 类 inventory；canonical source SHA-256 为 `{summary['canonicalSource']['sha256']}`。[`mechanism-evidence.jsonl`](mechanism-evidence.jsonl) 当前有 {len(evidence_records)} 条 claim，覆盖 {len({record['topic'] for record in evidence_records})} 个 topic：{evidence_class_counts['Static']} Static、{evidence_class_counts['Probe']} Probe、{evidence_class_counts['Public']} Public、{evidence_class_counts['Boundary']} Boundary。",
        "",
        f"仍需人工收口的客户端证据包括：[环境变量参考](environment-variable-reference.md)中的 {environment_summary['semanticFollowupStaticNameCount']} 个静态环境名称和 {environment_summary['unresolvedDynamicCallsiteCount']} 个动态环境表达式、[Feature 参考](feature-flag-reference.md)中的 {feature_summary['callsiteOnlyStaticKeyCount']} 个 Feature key、[Telemetry 场景索引](telemetry-event-catalog.md)中的 {telemetry_projection['unresolved']} 个 `tengu_other` caller-owner，以及 error/diagnostic 逐 callsite owner、遥测运行 gate/动态 payload/远端 delivery 和若干高风险正向 Probe。这些是 `Untraced/Inventory only`，不是服务端 Boundary。",
        "",
        "## 三轴怎样读",
        "",
        "- **提取来源**回答记录怎样从 canonical bundle 得到。",
        "- **所有权**区分 Product、Dependency、Mixed 与 Unresolved。",
        "- **证明层级**只允许 Candidate、Declaration、Callsite、Structured surface 或 Evidence substrate；它们都不会自动升级为运行结论。",
        "",
        "表中的运行面沿用 [主文末尾的 Derived 阅读索引](product-surface-evidence-map.md#把-cqeso-留作阅读索引)：`C` 控制、`Q` 请求与上下文、`E` 本地执行、`S` 持久状态、`O` 观测与诊断。它们是阅读路由，不是源码原生模块。",
        "",
        f"## 全部 {len(inventory_names)} 类机器清单",
        "",
        "<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->",
        "| 机器清单 | 提取来源 | 所有权 | 证明层级 | 运行面 | 当前仍缺什么 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in inventory_names:
        domain, classification = FILE_META[name]
        meta = DOMAIN_META[domain]
        class_meta = CLASS_META[classification]
        evidence_meta = FILE_EVIDENCE_OVERRIDES.get(name, {})
        axes = {**CLASS_AXES[classification], **FILE_AXIS_OVERRIDES.get(name, {})}
        routes = FILE_ROUTE_OVERRIDES.get(name, DOMAIN_ROUTE_IDS[domain])
        limitation = evidence_meta.get(
            "limitation",
            f"{class_meta['authority']}；{meta['boundary']}",
        )
        lines.append(
            f"| {markdown_link(name)} | `{axes['origin']}` | `{axes['ownership']}` | "
            f"`{axes['proof']}` | `{'/'.join(routes)}` | {limitation} |"
        )
    lines.extend(
        [
            "<!-- SOURCE_INVENTORY_COVERAGE_END -->",
            "",
            "机器覆盖只证明候选证据没有从生成物中消失。最终行为结论仍以 [全面性审计](completeness-audit.md)、逐项 reference 和对应机制文章中的 consumer/state-machine 追踪为准。",
            "",
        ]
    )
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
    inventory_content = build_inventory_index(repo)
    output = Path(args.output) if args.output else repo / "analysis/product-surface-evidence-map.md"
    if not output.is_absolute():
        output = repo / output
    inventory_output = output.with_name("product-surface-inventory-index.md")
    if args.check:
        if not output.is_file():
            raise SystemExit(f"missing output: {output}")
        if output.read_text(encoding="utf-8") != content:
            raise SystemExit(f"stale output: {output}")
        if not inventory_output.is_file():
            raise SystemExit(f"missing output: {inventory_output}")
        if inventory_output.read_text(encoding="utf-8") != inventory_content:
            raise SystemExit(f"stale output: {inventory_output}")
        checked = [
            path.relative_to(repo) if path.is_relative_to(repo) else path
            for path in (output, inventory_output)
        ]
        print("checked " + ", ".join(map(str, checked)))
        return
    if args.output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        inventory_output.write_text(inventory_content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
