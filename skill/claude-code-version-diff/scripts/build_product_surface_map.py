#!/usr/bin/env python3
"""Build the human-readable ownership map for every source inventory file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DOMAIN_META = {
    "request-model-network": {
        "name": "请求、模型与网络地址",
        "question": "哪些值进入 provider/model/header/route 装配，哪些只是 bundle 中出现过的地址？",
        "docs": [
            "models-auth-providers-request.md",
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
            "cli-sdk-output-protocol.md",
            "plugins-skills-commands-lsp.md",
            "slash-command-reference.md",
            "hooks-event-reference.md",
        ],
        "boundary": "第三方 host、MCP server、Plugin 和 Hook 程序自身行为仍属于外部实现。",
    },
    "settings-environment-policy": {
        "name": "Settings、环境变量与 Policy",
        "question": "哪些字段有 typed schema/consumer，哪些名字只来自广义环境或 schema 字符串？",
        "docs": [
            "settings-reference.md",
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
            "feature-flags-remote-config.md",
            "public-claims-validation.md",
        ],
        "boundary": "服务端留存、实验分桶、实时 flag 值和第三方 collector 行为不由客户端 bundle 决定。",
    },
    "diagnostics-errors": {
        "name": "错误、诊断与恢复线索",
        "question": "错误文本由哪个 consumer/状态机产生，还是仅作为词法证据存在？",
        "docs": [
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


FILE_META = {
    "anthropic-beta-identifiers.txt": ("request-model-network", "Product broad surface"),
    "api-path-templates.jsonl": ("request-model-network", "Product callsites"),
    "api-paths.txt": ("request-model-network", "Mixed heuristic"),
    "builtin-tool-identifiers.txt": ("tools-commands-protocol", "Product structured"),
    "claude-storage-namespaces.txt": ("storage-runtime", "Product structured"),
    "datadog-forwarded-events.txt": ("telemetry-feature", "Product structured"),
    "datadog-redacted-fields.txt": ("telemetry-feature", "Product structured"),
    "datadog-tag-fields.txt": ("telemetry-feature", "Product structured"),
    "diagnostic-message-callsites.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "diagnostic-message-literals.txt": ("diagnostics-errors", "Evidence substrate"),
    "diagnostic-message-templates.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "direct-process-environment-accesses.txt": ("settings-environment-policy", "Product callsites"),
    "dynamic-process-environment-callsites.jsonl": ("settings-environment-policy", "Product callsites"),
    "endpoint-hosts.txt": ("request-model-network", "Mixed heuristic"),
    "environment-access-callsites.jsonl": ("settings-environment-policy", "Product callsites"),
    "environment-access-identifiers.txt": ("settings-environment-policy", "Mixed heuristic"),
    "environment-like-identifiers.txt": ("settings-environment-policy", "Mixed heuristic"),
    "environment-proxy-accesses.txt": ("settings-environment-policy", "Product callsites"),
    "environment-schema.jsonl": ("settings-environment-policy", "Product structured"),
    "error-message-callsites.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "error-message-literals.txt": ("diagnostics-errors", "Evidence substrate"),
    "error-message-templates.jsonl": ("diagnostics-errors", "Evidence substrate"),
    "feature-flag-callsites.jsonl": ("telemetry-feature", "Product callsites"),
    "feature-flags.txt": ("telemetry-feature", "Product structured"),
    "first-party-environment-fields.txt": ("telemetry-feature", "Product structured"),
    "first-party-event-callsites.jsonl": ("telemetry-feature", "Product callsites"),
    "first-party-event-families.tsv": ("telemetry-feature", "Product structured"),
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
    "runtime-requires.txt": ("storage-runtime", "Dependency surface"),
    "schema-descriptions.txt": ("settings-environment-policy", "Mixed heuristic"),
    "schema-property-identifiers.txt": ("settings-environment-policy", "Mixed heuristic"),
    "sdk-control-subtypes.txt": ("tools-commands-protocol", "Product structured"),
    "slash-command-identifiers.txt": ("tools-commands-protocol", "Product structured"),
    "static-enum-groups.tsv": ("settings-environment-policy", "Mixed heuristic"),
    "static-string-literals.jsonl": ("lexical-evidence", "Evidence substrate"),
    "storage-namespaces.txt": ("storage-runtime", "Mixed heuristic"),
    "telemetry-endpoints.txt": ("telemetry-feature", "Product broad surface"),
    "template-literals.jsonl": ("lexical-evidence", "Evidence substrate"),
    "tengu-identifiers.txt": ("telemetry-feature", "Mixed heuristic"),
    "third-party-otel-event-fields.tsv": ("telemetry-feature", "Dependency surface"),
    "third-party-otel-events.txt": ("telemetry-feature", "Dependency surface"),
    "url-templates.jsonl": ("request-model-network", "Mixed heuristic"),
    "urls.txt": ("request-model-network", "Mixed heuristic"),
    "user-config-directories.txt": ("settings-environment-policy", "Product broad surface"),
}


def markdown_link(relative: str) -> str:
    return f"[`{relative}`](source-inventory/{relative})"


def build(repo: Path) -> str:
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    summary_path = repo / "analysis/source-inventory/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    inventory_names = [Path(entry["path"]).name for entry in summary["files"]]
    expected = set(inventory_names)
    classified = set(FILE_META)
    missing = sorted(expected - classified)
    stale = sorted(classified - expected)
    if missing or stale or len(inventory_names) != len(expected):
        raise RuntimeError(
            f"inventory classification mismatch: missing={missing}, stale={stale}, "
            f"duplicates={len(inventory_names) - len(expected)}"
        )

    counts: dict[str, int] = {domain: 0 for domain in DOMAIN_META}
    for name in inventory_names:
        counts[FILE_META[name][0]] += 1

    lines = [
        f"# Claude Code CLI {version} 产品表面与 70 类证据归属地图",
        "",
        "这篇不是把 70 个文件重新堆成目录，而是回答：每类机器清单为什么存在、能证明哪一层、应该回到哪篇人类专题，以及什么时候必须停止推断。",
        "",
        "## 60 秒理解这张地图",
        "",
        "**读者问题：** `summary.json` 已经注册 70 类清单，为什么仍可能不全面？",
        "",
        "**一句话模型：** 清单解决“候选证据有没有漏”，专题解决“消费者和状态机讲没讲清”，Probe 解决“发布二进制是否真的走过该分支”，Boundary 解决“发布物根本不携带什么”；四层缺一都不能用数量代替。",
        "",
        "![从 canonical bytes 到结构化清单、人类机制、运行 Probe 与 Boundary 的证据分层](visuals/evidence-surface-lifecycle.svg)",
        "",
        "贯穿场景：读者在 `urls.txt` 看到一个远端地址，在 `feature-flags.txt` 看到一个开关，在 `error-message-literals.txt` 看到一条失败文案。地址可能来自依赖，flag 只有 consumer 才能说明 gate，错误文本只有进入可达分支才说明运行语义。地图先给三者定归属，再把读者送到请求、Feature 或恢复专题，而不是让名字自行生成结论。",
        "",
        "| 层 | 它拥有的事实 | 不能替代什么 |",
        "| --- | --- | --- |",
        "| Canonical/AST inventory | packed bytes、完整目标调用点、动态表达式和词法候选 | 产品归属、可达性、状态机 |",
        "| Human mechanism | consumer、owner、调用顺序、gate、失败、恢复和用户影响 | 精确二进制实际走过分支 |",
        "| Exact-binary Probe | 固定输入下的 request/result/exit/副作用 | 真实账号、第三方服务、其他平台 |",
        "| Boundary | 明确发布物缺少的实现和值 | 不能用猜测补空白 |",
        "",
        "## 七个证据域怎样分工",
        "",
        "| 证据域 | 清单数 | 先问什么 | 主要阅读入口 |",
        "| --- | ---: | --- | --- |",
    ]
    for domain, meta in DOMAIN_META.items():
        docs = "、".join(f"[{doc}]({doc})" for doc in meta["docs"])
        lines.append(
            f"| {meta['name']} | {counts[domain]} | {meta['question']} | {docs} |"
        )

    lines.extend([
        "",
        "## 六种归属标签怎么读",
        "",
        "| 标签 | 结论强度 | 正确用法 |",
        "| --- | --- | --- |",
        "| `Product structured` | 一方结构化集合或完整 catalog/schema | 可作为穷举入口，仍需 consumer/状态机 |",
        "| `Product callsites` | AST 确认的一方调用点 | 可定位真实消费者和动态参数 |",
        "| `Product broad surface` | 一方相关但粒度较宽的 identifier 集合 | 用于发现入口，不能直接声称默认启用 |",
        "| `Mixed heuristic` | 产品、依赖、内嵌文档可能混合 | 必须二次归属，不能按名字计功能数 |",
        "| `Dependency surface` | 第三方依赖或 runtime contract | 只在一方 consumer 可达时进入产品机制 |",
        "| `Evidence substrate` | 完整词法/错误/模板证据底座 | 用于防漏和定位，不单独证明可达行为 |",
        "",
        "## 70/70 精确归属",
        "",
        "下面是机器核对附录。顺序和文件集合必须与 `analysis/source-inventory/summary.json` 完全一致；新增版本出现新类别时，生成器会拒绝继续，直到维护者明确归属和阅读路由。",
        "",
        "<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->",
        "| 机器清单 | 证据域 | 归属 | 人类阅读入口 | 不能越过的边界 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for name in inventory_names:
        domain, classification = FILE_META[name]
        meta = DOMAIN_META[domain]
        docs = "、".join(f"[{doc}]({doc})" for doc in meta["docs"])
        lines.append(
            f"| {markdown_link(name)} | `{domain}` | `{classification}` | {docs} | {meta['boundary']} |"
        )
    lines.extend([
        "<!-- SOURCE_INVENTORY_COVERAGE_END -->",
        "",
        "## 怎样从一行清单追到结论",
        "",
        "1. 先读归属标签；`Mixed heuristic` 和 `Evidence substrate` 不允许直接写产品功能。",
        "2. 打开主要专题，找到 consumer、owned state、gate、失败与恢复；只有 schema/help 时维持 declaration/surface。",
        "3. 需要运行结论时检查 `mechanism-evidence.jsonl` 和 `runtime-probe-index.md`，联合读取 command、input、literal output、exit status 和 required checks。",
        "4. 真实账号、远端服务、第三方程序、其他平台或构建前删除源码不在本版证据中，写成 Boundary。",
        "",
        "## 完整性结论",
        "",
        f"本图覆盖 `summary.json` 的全部 {len(inventory_names)} 个注册文件，canonical source SHA-256 为 `{summary['canonicalSource']['sha256']}`。它证明所有确定性 inventory 类别都有产品归属、证据强度和人类阅读路由；它不把 70/70 自动解释为所有运行分支都经过 Probe。最终状态仍以 `completeness-audit.md` 的逐能力合同为准。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    content = build(repo)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
