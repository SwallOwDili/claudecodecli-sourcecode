#!/usr/bin/env python3
"""Compare two Claude Code snapshot branches and emit a Markdown report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ENV_RE = re.compile(rb"\b(?:ANTHROPIC|CLAUDE_CODE)_[A-Z][A-Z0-9_]{2,}\b")
FEATURE_RE = re.compile(rb"\bENABLE_[A-Z][A-Z0-9_]{2,}\b")
URL_RE = re.compile(rb"https?://[A-Za-z0-9._:-]+")
HUMAN_ANALYSIS_PATHS = (
    "README.md",
    "analysis/technical-mechanism-atlas.md",
    "analysis/public-claims-validation.md",
    "analysis/runtime-probe-index.md",
    "analysis/technical-architecture.md",
    "analysis/agent-loop.md",
    "analysis/context-governance-and-caching.md",
    "analysis/sessions-checkpoints-memory.md",
    "analysis/tools-permissions-hooks.md",
    "analysis/mcp-agents-background.md",
    "analysis/resilience-and-recovery.md",
    "analysis/models-auth-providers-request.md",
    "analysis/settings-feature-flags-policy.md",
    "analysis/tui-ide-remote-cloud.md",
    "analysis/install-update-doctor-lifecycle.md",
    "analysis/native-bridge-runtime.md",
    "analysis/inventory-field-guide.md",
    "analysis/telemetry.md",
    "analysis/source-surface.md",
)


def git(repo: Path, *args: str, text: bool = True):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.STDOUT, text=text
    )


def show(repo: Path, branch: str, path: str, text: bool = False):
    return git(repo, "show", f"{branch}:{path}", text=text)


def has_path(repo: Path, branch: str, path: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{branch}:{path}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def read_json(repo: Path, branch: str, path: str) -> dict:
    return json.loads(show(repo, branch, path, text=True))


def read_jsonl(repo: Path, branch: str, path: str) -> list[dict]:
    return [
        json.loads(line)
        for line in show(repo, branch, path, text=True).splitlines()
        if line.strip()
    ]


def read_public_excerpts(repo: Path, branch: str) -> dict[str, str]:
    path = "analysis/public-source-excerpts.md"
    if not has_path(repo, branch, path):
        return {}
    document = show(repo, branch, path, text=True)
    headings = list(re.finditer(r"^## `([^`]+)`\s*$", document, re.MULTILINE))
    excerpts: dict[str, str] = {}
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(document)
        excerpts[match.group(1)] = document[match.end():end].strip()
    return excerpts


def read_lines(repo: Path, branch: str, path: str) -> set[str]:
    return {
        line.strip()
        for line in show(repo, branch, path, text=True).splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("[")
    }


def read_inventory_lines(repo: Path, branch: str, path: str) -> set[str]:
    lines = [
        line.rstrip()
        for line in show(repo, branch, path, text=True).splitlines()
        if line.rstrip()
    ]
    if not path.endswith(".jsonl"):
        return set(lines)
    values: set[str] = set()
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            values.add(line)
            continue
        comparison_key = record.get("comparisonKey")
        comparison_value = record.get("comparisonValue")
        if isinstance(comparison_key, str) and isinstance(comparison_value, str):
            values.add(f"{comparison_key}\t{comparison_value}")
        else:
            for field in (
                "offset",
                "line",
                "column",
                "locations",
                "exportOffset",
                "exportLine",
                "exportColumn",
                "builderOffset",
                "builderLine",
                "builderColumn",
            ):
                record.pop(field, None)
            values.add(
                json.dumps(
                    record,
                    sort_keys=True,
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
            )
    return values


def tree_paths(repo: Path, branch: str, prefix: str) -> set[str]:
    output = git(repo, "ls-tree", "-r", "--name-only", branch, "--", prefix, text=True)
    return {line.strip() for line in output.splitlines() if line.strip()}


def markdown_headings(repo: Path, branch: str, path: str) -> set[str]:
    return {
        line.strip()
        for line in show(repo, branch, path, text=True).splitlines()
        if re.match(r"^#{1,4}\s+\S", line)
    }


def human_analysis_report(repo: Path, old_branch: str, new_branch: str) -> list[str]:
    lines = [
        "## Human explanation layer",
        "",
        "Machine inventory deltas are evidence, not the final explanation. The following documents must be reviewed for public-claim validation, owned state, lifecycle, field semantics, fallback, cost, and user impact.",
        "",
        "| Document | Old lines | New lines | Changed |",
        "| --- | ---: | ---: | --- |",
    ]
    changed_paths: list[str] = []
    for path in HUMAN_ANALYSIS_PATHS:
        old_exists = has_path(repo, old_branch, path)
        new_exists = has_path(repo, new_branch, path)
        old_lines = len(show(repo, old_branch, path, text=True).splitlines()) if old_exists else 0
        new_lines = len(show(repo, new_branch, path, text=True).splitlines()) if new_exists else 0
        if old_exists and new_exists:
            changed = subprocess.run(
                ["git", "-C", str(repo), "diff", "--quiet", old_branch, new_branch, "--", path]
            ).returncode != 0
            changed_label = "yes" if changed else "no"
        elif new_exists:
            changed = True
            changed_label = "added"
        elif old_exists:
            changed = True
            changed_label = "removed"
        else:
            changed = False
            changed_label = "missing"
        lines.append(f"| `{path}` | {old_lines} | {new_lines} | {changed_label} |")
        if changed:
            changed_paths.append(path)
    lines.append("")

    for path in changed_paths:
        if not has_path(repo, old_branch, path) or not has_path(repo, new_branch, path):
            continue
        lines.extend(
            bullet_diff(
                f"Human document headings: {path}",
                markdown_headings(repo, old_branch, path),
                markdown_headings(repo, new_branch, path),
            )
        )

    lines.extend(
        [
            "### Required interpretation",
            "",
            "For each material machine delta, complete the human comparison with:",
            "",
            "- old and new reachable call paths/state transitions;",
            "- current first-party public claim, retrieval date, target-version Static/Probe evidence, and any Boundary/version drift;",
            "- Agent Loop turn/API-attempt boundaries, streaming tool start, concurrency barriers, tool pipeline order, max-turn/Stop-hook behavior, terminal reasons, and fallback side-effect boundaries;",
            "- message graph/transcript/compact-boundary repair, checkpoint cap/rewind, memory budgets, and durable-versus-process state;",
            "- tool schema/permission/hook/sandbox/policy ordering, whether tool.call occurred on each failure, and fail-closed behavior;",
            "- MCP generation/Tool Search invalidation, subagent defaults/isolation, background durability, task claim/mailbox, and coordination cost;",
            "- request/stream/model/output/context/tool/hook/MCP/session recovery differences, including retained/discarded state and repeated-side-effect risk;",
            "- trigger, precedence, default, threshold, cap, TTL, or queue/retry value;",
            "- failure, strip, retry, fallback, invalidation, and persistence behavior;",
            "- user-visible quality, token, latency, cost, privacy, and security impact;",
            "- field meanings and the exact source/inventory evidence;",
            "- unchanged behavior and server/runtime-only boundaries.",
            "",
        ]
    )
    return lines


def contract_inventory(value, prefix: str = "") -> set[str]:
    inventory: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            inventory.update(contract_inventory(child, child_prefix))
    elif isinstance(value, list):
        inventory.update(f"{prefix}: {item}" for item in value)
    else:
        inventory.add(f"{prefix}: {value}")
    return inventory


def source_inventory(source: bytes) -> dict[str, set[str]]:
    env = {match.decode("ascii") for match in ENV_RE.findall(source)}
    features = {match.decode("ascii") for match in FEATURE_RE.findall(source)}
    hosts = set()
    for match in URL_RE.findall(source):
        try:
            host = urlparse(match.decode("ascii")).netloc.lower()
        except ValueError:
            continue
        if host:
            hosts.add(host)
    return {"environment": env, "features": features, "hosts": hosts}


def code_span(value: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * (longest + 1)
    return f"{fence}{value}{fence}"


def bullet_diff(title: str, old: set[str], new: set[str]) -> list[str]:
    added = sorted(new - old)
    removed = sorted(old - new)
    lines = [f"## {title}", ""]
    lines.append(f"Added: {len(added)}; removed: {len(removed)}.")
    lines.append("")
    if added:
        lines.append("### Added")
        lines.append("")
        lines.extend(f"- {code_span(item)}" for item in added)
        lines.append("")
    if removed:
        lines.append("### Removed")
        lines.append("")
        lines.extend(f"- {code_span(item)}" for item in removed)
        lines.append("")
    if not added and not removed:
        lines.extend(["No changes.", ""])
    return lines


def mechanism_evidence_report(repo: Path, old_branch: str, new_branch: str) -> list[str]:
    evidence_path = "analysis/mechanism-evidence.jsonl"
    old_exists = has_path(repo, old_branch, evidence_path)
    new_exists = has_path(repo, new_branch, evidence_path)
    lines = ["## Mechanism evidence contract", ""]
    if not old_exists or not new_exists:
        if new_exists:
            return lines + ["Structured mechanism evidence was added in the new branch.", ""]
        if old_exists:
            return lines + ["Structured mechanism evidence is absent from the new branch.", ""]
        return lines + ["Neither branch contains structured mechanism evidence.", ""]

    old_records = {record["claimId"]: record for record in read_jsonl(repo, old_branch, evidence_path)}
    new_records = {record["claimId"]: record for record in read_jsonl(repo, new_branch, evidence_path)}
    old_ids = set(old_records)
    new_ids = set(new_records)

    def semantics(record: dict) -> str:
        return json.dumps(
            {
                key: record.get(key)
                for key in (
                    "topic",
                    "claim",
                    "evidenceClass",
                    "boundaryReason",
                )
                if key in record
            },
            ensure_ascii=True,
            sort_keys=True,
        )

    def evidence_shape(record: dict) -> str:
        ignored = {"claim", "startLine", "endLine"}
        return json.dumps(
            {key: value for key, value in record.items() if key not in ignored},
            ensure_ascii=True,
            sort_keys=True,
        )

    changed_semantics = sorted(
        claim_id
        for claim_id in old_ids & new_ids
        if semantics(old_records[claim_id]) != semantics(new_records[claim_id])
    )
    changed_evidence = sorted(
        claim_id
        for claim_id in old_ids & new_ids
        if evidence_shape(old_records[claim_id]) != evidence_shape(new_records[claim_id])
    )
    class_changes = sorted(
        claim_id
        for claim_id in old_ids & new_ids
        if old_records[claim_id].get("evidenceClass")
        != new_records[claim_id].get("evidenceClass")
    )
    lines.extend(
        [
            "| Metric | Count |",
            "| --- | ---: |",
            f"| Old claims | {len(old_ids)} |",
            f"| New claims | {len(new_ids)} |",
            f"| Added claims | {len(new_ids - old_ids)} |",
            f"| Removed claims | {len(old_ids - new_ids)} |",
            f"| Changed claim semantics | {len(changed_semantics)} |",
            f"| Changed evidence shape | {len(changed_evidence)} |",
            f"| Evidence-class changes | {len(class_changes)} |",
            "",
        ]
    )
    for title, claim_ids in (
        ("Added claims", sorted(new_ids - old_ids)),
        ("Removed claims", sorted(old_ids - new_ids)),
        ("Changed claim semantics", changed_semantics),
        ("Changed evidence shape", changed_evidence),
        ("Evidence-class changes", class_changes),
    ):
        if claim_ids:
            lines.extend([f"### {title}", ""])
            for claim_id in claim_ids:
                old_class = old_records.get(claim_id, {}).get("evidenceClass", "-")
                new_class = new_records.get(claim_id, {}).get("evidenceClass", "-")
                lines.append(f"- `{claim_id}`: `{old_class}` -> `{new_class}`")
            lines.append("")

    public_path = "analysis/public-sources/manifest.json"
    if has_path(repo, old_branch, public_path) and has_path(repo, new_branch, public_path):
        old_sources = {
            source["id"]: source
            for source in read_json(repo, old_branch, public_path).get("sources", [])
        }
        new_sources = {
            source["id"]: source
            for source in read_json(repo, new_branch, public_path).get("sources", [])
        }
        changed_sources = sorted(
            source_id
            for source_id in set(old_sources) & set(new_sources)
            if (
                old_sources[source_id].get("status"),
                old_sources[source_id].get("sha256"),
                old_sources[source_id].get("semanticTextSha256"),
                old_sources[source_id].get("bytes"),
                old_sources[source_id].get("url"),
                old_sources[source_id].get("excerptIds"),
                old_sources[source_id].get("excerptSha256"),
                old_sources[source_id].get("excerptSourceVerified"),
            )
            != (
                new_sources[source_id].get("status"),
                new_sources[source_id].get("sha256"),
                new_sources[source_id].get("semanticTextSha256"),
                new_sources[source_id].get("bytes"),
                new_sources[source_id].get("url"),
                new_sources[source_id].get("excerptIds"),
                new_sources[source_id].get("excerptSha256"),
                new_sources[source_id].get("excerptSourceVerified"),
            )
        )
        lines.extend(
            [
                "### Public-source response drift",
                "",
                f"Added: {len(set(new_sources) - set(old_sources))}; removed: {len(set(old_sources) - set(new_sources))}; changed response/url: {len(changed_sources)}.",
                "",
            ]
        )
        lines.extend(f"- `{source_id}`" for source_id in changed_sources)
        if changed_sources:
            lines.append("")

        old_excerpts = read_public_excerpts(repo, old_branch)
        new_excerpts = read_public_excerpts(repo, new_branch)
        changed_excerpts = sorted(
            excerpt_id
            for excerpt_id in set(old_excerpts) & set(new_excerpts)
            if old_excerpts[excerpt_id] != new_excerpts[excerpt_id]
        )
        lines.extend(
            [
                "### Public-source excerpt drift",
                "",
                f"Added: {len(set(new_excerpts) - set(old_excerpts))}; removed: {len(set(old_excerpts) - set(new_excerpts))}; changed: {len(changed_excerpts)}.",
                "",
            ]
        )
        lines.extend(f"- `{excerpt_id}`" for excerpt_id in changed_excerpts)
        if changed_excerpts:
            lines.append("")

    def probe_observations(branch: str, records: dict[str, dict]) -> dict[str, str]:
        observations: dict[str, str] = {}
        for claim_id, record in records.items():
            report_path = record.get("reportPath")
            if record.get("evidenceClass") != "Probe" or not isinstance(report_path, str):
                continue
            if not has_path(repo, branch, report_path):
                observations[claim_id] = "missing report"
                continue
            report = read_json(repo, branch, report_path)
            observations[claim_id] = json.dumps(
                {
                    "target": report.get("target"),
                    "environment": report.get("environment"),
                    "commands": report.get("commands"),
                    "input": report.get("input"),
                    "pass": report.get("pass"),
                    "literalOutput": report.get("literalOutput"),
                    "exitStatus": report.get("exitStatus"),
                    "observed": report.get("observed"),
                    "observedRequestCount": report.get("observedRequestCount"),
                    "checks": report.get("checks"),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        return observations

    old_probes = probe_observations(old_branch, old_records)
    new_probes = probe_observations(new_branch, new_records)
    changed_probes = sorted(
        claim_id
        for claim_id in set(old_probes) | set(new_probes)
        if old_probes.get(claim_id) != new_probes.get(claim_id)
    )
    lines.extend(["### Runtime probe outcome changes", ""])
    if changed_probes:
        lines.extend(f"- `{claim_id}`" for claim_id in changed_probes)
    else:
        lines.append("No normalized probe outcome changes.")
    lines.append("")
    return lines


def manifest_map(document: dict) -> dict[str, dict]:
    return {entry["path"]: entry for entry in document.get("files", [])}


def source_inventory_report(
    repo: Path, old_branch: str, new_branch: str
) -> tuple[list[str], bool]:
    summary_path = "analysis/source-inventory/summary.json"
    old_exists = has_path(repo, old_branch, summary_path)
    new_exists = has_path(repo, new_branch, summary_path)
    lines = ["## Exhaustive source inventory", ""]
    if not old_exists or not new_exists:
        if new_exists and not old_exists:
            lines.extend(["Machine-readable source inventory coverage was added in the new branch.", ""])
        elif old_exists and not new_exists:
            lines.extend(["Machine-readable source inventory coverage is absent from the new branch.", ""])
        else:
            lines.extend(["Neither branch contains a machine-readable source inventory.", ""])
        return lines, False

    old_summary = read_json(repo, old_branch, summary_path)
    new_summary = read_json(repo, new_branch, summary_path)
    old_counts = old_summary.get("counts", {})
    new_counts = new_summary.get("counts", {})
    lines.extend(
        [
            f"Inventory format: `{old_summary.get('formatVersion')}` -> `{new_summary.get('formatVersion')}`.",
            "",
            "| Inventory | Old | New | Delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name in sorted(set(old_counts) | set(new_counts)):
        old_value = old_counts.get(name, 0)
        new_value = new_counts.get(name, 0)
        lines.append(f"| `{name}` | {old_value} | {new_value} | {new_value - old_value:+d} |")
    lines.append("")

    old_files = {
        Path(entry["path"]).name: entry for entry in old_summary.get("files", [])
    }
    new_files = {
        Path(entry["path"]).name: entry for entry in new_summary.get("files", [])
    }
    added_files = sorted(set(new_files) - set(old_files))
    removed_files = sorted(set(old_files) - set(new_files))
    lines.extend(
        [
            f"Inventory artifacts added: {len(added_files)}; removed: {len(removed_files)}.",
            "",
        ]
    )
    if added_files:
        lines.extend(["### Added inventory artifacts", ""])
        lines.extend(f"- `{name}`" for name in added_files)
        lines.append("")
    if removed_files:
        lines.extend(["### Removed inventory artifacts", ""])
        lines.extend(f"- `{name}`" for name in removed_files)
        lines.append("")

    for name in sorted(set(old_files) & set(new_files)):
        path = f"analysis/source-inventory/{name}"
        title = "Source inventory: " + name.rsplit(".", 1)[0].replace("-", " ")
        lines.extend(
            bullet_diff(
                title,
                read_inventory_lines(repo, old_branch, path),
                read_inventory_lines(repo, new_branch, path),
            )
        )
    return lines, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("old_branch")
    parser.add_argument("new_branch")
    parser.add_argument("--output")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    old_meta = read_json(repo, args.old_branch, "analysis/version.json")
    new_meta = read_json(repo, args.new_branch, "analysis/version.json")
    old_manifest = manifest_map(
        read_json(repo, args.old_branch, "analysis/unpack-manifest.json")
    )
    new_manifest = manifest_map(
        read_json(repo, args.new_branch, "analysis/unpack-manifest.json")
    )
    old_cli = read_lines(repo, args.old_branch, "analysis/cli-surface.txt")
    new_cli = read_lines(repo, args.new_branch, "analysis/cli-surface.txt")
    old_source = show(repo, args.old_branch, "extracted/cli.js")
    new_source = show(repo, args.new_branch, "extracted/cli.js")
    old_inventory = source_inventory(old_source)
    new_inventory = source_inventory(new_source)

    lines = [
        f"# Claude Code {old_meta['version']} -> {new_meta['version']}",
        "",
        "## Snapshot delta",
        "",
        "| Metric | Old | New | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, path in [
        ("Binary bytes", ("binary", "size")),
        ("Payload bytes", ("extraction", "payloadSize")),
        ("Extracted files", ("extraction", "fileCount")),
        ("Main source bytes", ("mainSource", "size")),
        ("Main source lines", ("mainSource", "lines")),
    ]:
        old_value = old_meta[path[0]][path[1]]
        new_value = new_meta[path[0]][path[1]]
        lines.append(f"| {label} | {old_value} | {new_value} | {new_value - old_value:+d} |")
    lines.append("")

    old_paths = set(old_manifest)
    new_paths = set(new_manifest)
    changed = sorted(
        path
        for path in old_paths & new_paths
        if old_manifest[path].get("sha256Packed") != new_manifest[path].get("sha256Packed")
    )
    lines.extend(["## Embedded files", ""])
    lines.append(f"Added: {len(new_paths - old_paths)}; removed: {len(old_paths - new_paths)}; changed: {len(changed)}.")
    lines.append("")
    for status, paths in [
        ("Added", sorted(new_paths - old_paths)),
        ("Removed", sorted(old_paths - new_paths)),
        ("Changed", changed),
    ]:
        if paths:
            lines.append(f"### {status}")
            lines.append("")
            for path in paths:
                if status == "Changed":
                    old_size = old_manifest[path]["size"]
                    new_size = new_manifest[path]["size"]
                    lines.append(f"- `{path}`: {old_size} -> {new_size} bytes ({new_size - old_size:+d})")
                else:
                    entry = new_manifest[path] if status == "Added" else old_manifest[path]
                    lines.append(f"- `{path}`: {entry['size']} bytes, {entry['kind']}")
            lines.append("")

    lines.extend(bullet_diff("CLI surface", old_cli, new_cli))
    old_risk = has_path(repo, args.old_branch, "analysis/risk-control-surface.txt")
    new_risk = has_path(repo, args.new_branch, "analysis/risk-control-surface.txt")
    if old_risk and new_risk:
        lines.extend(
            bullet_diff(
                "Risk-control surface",
                read_lines(repo, args.old_branch, "analysis/risk-control-surface.txt"),
                read_lines(repo, args.new_branch, "analysis/risk-control-surface.txt"),
            )
        )
    elif new_risk:
        lines.extend(
            ["## Risk-control surface", "", "Risk-control coverage was added in the new branch.", ""]
        )
    elif old_risk:
        lines.extend(
            ["## Risk-control surface", "", "Risk-control coverage is absent from the new branch.", ""]
        )
    else:
        lines.extend(
            ["## Risk-control surface", "", "Neither branch contains a normalized risk-control surface.", ""]
        )
    source_inventory_lines, exhaustive_inventory = source_inventory_report(
        repo, args.old_branch, args.new_branch
    )
    lines.extend(source_inventory_lines)
    if not exhaustive_inventory:
        lines.extend(
            bullet_diff(
                "Fallback environment identifiers",
                old_inventory["environment"],
                new_inventory["environment"],
            )
        )
        lines.extend(
            bullet_diff(
                "Fallback feature identifiers",
                old_inventory["features"],
                new_inventory["features"],
            )
        )
        lines.extend(
            bullet_diff(
                "Fallback endpoint hosts",
                old_inventory["hosts"],
                new_inventory["hosts"],
            )
        )

    lines.extend(mechanism_evidence_report(repo, args.old_branch, args.new_branch))
    lines.extend(human_analysis_report(repo, args.old_branch, args.new_branch))

    old_deep = has_path(repo, args.old_branch, "reverse/summary.json")
    new_deep = has_path(repo, args.new_branch, "reverse/summary.json")
    lines.extend(["## Deep reverse", ""])
    if old_deep and new_deep:
        old_reverse = read_json(repo, args.old_branch, "reverse/summary.json")
        new_reverse = read_json(repo, args.new_branch, "reverse/summary.json")
        old_bytecode = old_reverse["bytecode"]
        new_bytecode = new_reverse["bytecode"]
        lines.extend(
            [
                "| Metric | Old | New | Delta |",
                "| --- | ---: | ---: | ---: |",
                f"| JSC bytecode bytes | {old_bytecode['uncompressedSize']} | {new_bytecode['uncompressedSize']} | {new_bytecode['uncompressedSize'] - old_bytecode['uncompressedSize']:+d} |",
                f"| Readable JavaScript bytes | {old_reverse['readableJavaScript']['size']} | {new_reverse['readableJavaScript']['size']} | {new_reverse['readableJavaScript']['size'] - old_reverse['readableJavaScript']['size']:+d} |",
                f"| Native modules | {len(old_reverse['nativeModules'])} | {len(new_reverse['nativeModules'])} | {len(new_reverse['nativeModules']) - len(old_reverse['nativeModules']):+d} |",
                "",
                f"Bytecode changed: `{old_bytecode['uncompressedSha256'] != new_bytecode['uncompressedSha256']}`.",
                "",
            ]
        )
        for title, path in [
            ("Probable config keys", "reverse/index/probable-config-keys.txt"),
            ("Embedded source paths", "reverse/index/embedded-source-paths.txt"),
            ("Native architectures", "reverse/index/native-architectures.txt"),
            ("Native dependencies", "reverse/index/native-dependencies.txt"),
            ("Native exports", "reverse/index/native-exports.txt"),
            ("Native imports", "reverse/index/native-imports.txt"),
            ("Native Swift project symbols", "reverse/index/native-swift-project-symbols.txt"),
        ]:
            if has_path(repo, args.old_branch, path) and has_path(repo, args.new_branch, path):
                lines.extend(
                    bullet_diff(
                        title,
                        read_lines(repo, args.old_branch, path),
                        read_lines(repo, args.new_branch, path),
                    )
                )
    elif new_deep:
        lines.extend(["Deep-reverse coverage was added in the new branch.", ""])
    elif old_deep:
        lines.extend(["Deep-reverse coverage is absent from the new branch.", ""])
    else:
        lines.extend(["Neither branch contains deep-reverse artifacts.", ""])

    old_reconstructed = has_path(repo, args.old_branch, "reconstructed/README.md")
    new_reconstructed = has_path(repo, args.new_branch, "reconstructed/README.md")
    lines.extend(["## Native source reconstruction", ""])
    if old_reconstructed and new_reconstructed:
        old_files = tree_paths(repo, args.old_branch, "reconstructed")
        new_files = tree_paths(repo, args.new_branch, "reconstructed")
        changed_files = {
            line.strip()
            for line in git(
                repo,
                "diff",
                "--name-only",
                args.old_branch,
                args.new_branch,
                "--",
                "reconstructed",
                text=True,
            ).splitlines()
            if line.strip()
        }
        lines.extend(
            [
                f"Files: {len(old_files)} -> {len(new_files)}; added: {len(new_files - old_files)}; removed: {len(old_files - new_files)}; changed: {len(changed_files)}.",
                "",
            ]
        )
        if has_path(repo, args.old_branch, "reconstructed/contracts/module-exports.json") and has_path(
            repo, args.new_branch, "reconstructed/contracts/module-exports.json"
        ):
            lines.extend(
                bullet_diff(
                    "Reconstructed native contracts",
                    contract_inventory(
                        read_json(repo, args.old_branch, "reconstructed/contracts/module-exports.json")
                    ),
                    contract_inventory(
                        read_json(repo, args.new_branch, "reconstructed/contracts/module-exports.json")
                    ),
                )
            )
        if changed_files:
            lines.extend(["### Changed reconstruction files", ""])
            lines.extend(f"- `{path}`" for path in sorted(changed_files))
            lines.append("")
    elif new_reconstructed:
        lines.extend(["Native source reconstruction coverage was added in the new branch.", ""])
    elif old_reconstructed:
        lines.extend(["Native source reconstruction coverage is absent from the new branch.", ""])
    else:
        lines.extend(["Neither branch contains native source reconstruction.", ""])

    numstat = git(
        repo,
        "diff",
        "--numstat",
        args.old_branch,
        args.new_branch,
        "--",
        "extracted",
        "analysis",
        "reverse",
        "reconstructed",
        text=True,
    ).strip()
    lines.extend(["## Git churn", "", "```text", numstat or "no changes", "```", ""])

    output = "\n".join(lines)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(args.output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
