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
from pathlib import Path


PERSONAL_PATH_RE = re.compile(
    rb"(?:/" + rb"Users/[^/\x00\r\n]+/|/" + rb"home/[^/\x00\r\n]+/|"
    rb"[A-Za-z]:\\" + rb"Users\\[^\\\x00\r\n]+\\)"
)
SECRET_RE = re.compile(
    rb"(?:sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    rb"AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,})"
)
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
}
HUMAN_ANALYSIS_DOCS = {
    "analysis/product-surface-evidence-map.md": (
        "SOURCE_INVENTORY_COVERAGE_BEGIN",
        "70/70",
        "Product structured",
        "Mixed heuristic",
        "Evidence substrate",
    ),
    "analysis/completeness-audit.md": (
        "36",
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
    ),
    "analysis/settings-reference.md": (
        "SETTINGS_DIRECT_KEYS_START",
        "156",
        "merge",
        "Static consumer",
    ),
    "analysis/cli-sdk-output-protocol.md": (
        "42 个 schema 化 control request",
        "46 个观察型 subtype",
        "44 个 Managed Agents event identifier",
        "103 个 slash command",
        "error_max_structured_output_retries",
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
        "fail closed",
    ),
    "analysis/storage-v5-reference.md": (
        "STORAGE_NAMESPACE_COVERAGE_BEGIN",
        "29",
        "tryCreateV5Backend",
        "updateText",
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
        "外部状态",
    ),
    "analysis/tools-permissions-hooks.md": (
        "updatedInput",
        "PostToolBatch",
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
    "analysis/source-surface.md": (
        "Observed",
        "Derived",
        "Heuristic",
    ),
}
HUMAN_ANALYSIS_MINIMUMS = {
    "analysis/product-surface-evidence-map.md": (18000, 6),
    "analysis/completeness-audit.md": (5000, 6),
    "analysis/builtin-tools-reference.md": (9000, 10),
    "analysis/settings-reference.md": (18000, 10),
    "analysis/cli-sdk-output-protocol.md": (12000, 12),
    "analysis/plugins-skills-commands-lsp.md": (10000, 10),
    "analysis/slash-command-reference.md": (12000, 10),
    "analysis/hooks-event-reference.md": (15000, 10),
    "analysis/storage-v5-reference.md": (18000, 12),
    "analysis/workflow-artifact-design.md": (12000, 10),
    "analysis/feature-flags-remote-config.md": (18000, 12),
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
}
READER_FIRST_ANALYSIS_DOCS = {
    "analysis/product-surface-evidence-map.md": "evidence-surface-lifecycle",
    "analysis/builtin-tools-reference.md": "builtin-tool-lifecycle",
    "analysis/settings-reference.md": "settings-resolution-lifecycle",
    "analysis/cli-sdk-output-protocol.md": "cli-sdk-protocol-lifecycle",
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
    "analysis/inventory-field-guide.md": "inventory-reading-lifecycle",
    "analysis/source-surface.md": "evidence-surface-lifecycle",
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
}
SOURCE_VIEW_PATHS = {
    "canonical-js": "extracted/cli.js",
    "readable-js": "reverse/javascript/cli.readable.js",
}


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

    if summary.get("formatVersion", 0) < 4:
        failures.append("source inventory formatVersion must be at least 4")
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

    completion = summary.get("completionAudit", {})
    for field in (
        "allTargetCallsitesRecorded",
        "allLexicalLiteralsRecorded",
        "dynamicExpressionsRetained",
        "rootSettingsKeysMatchStructuredRows",
        "modelCatalogParsed",
        "environmentSchemaParsed",
        "datadogSurfaceParsed",
        "semanticSymbolsDiscovered",
    ):
        if completion.get(field) is not True:
            failures.append(f"source inventory completion audit failed: {field}")
    if completion.get("knownStaticExtractionGaps") != []:
        failures.append("source inventory reports known static extraction gaps")

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
                        if not isinstance(record.get("comparisonKey"), str) or not isinstance(
                            record.get("comparisonValue"), str
                        ):
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
    block = text_between(
        content,
        "<!-- SOURCE_INVENTORY_COVERAGE_BEGIN -->",
        "<!-- SOURCE_INVENTORY_COVERAGE_END -->",
    )
    rows = re.findall(
        r"^\| \[`([^`]+)`\]\(source-inventory/([^)]+)\) \| `([^`]+)` \| `([^`]+)` \|",
        block,
        re.MULTILINE,
    )
    actual = [row[0] for row in rows]
    if actual != expected or any(label != target for label, target, _, _ in rows):
        failures.append(
            "product surface inventory coverage mismatch: "
            f"expected={len(expected)}, actual={len(actual)}, "
            f"ordered={actual == expected}"
        )
    allowed_domains = {
        "request-model-network",
        "tools-commands-protocol",
        "settings-environment-policy",
        "telemetry-feature",
        "diagnostics-errors",
        "storage-runtime",
        "lexical-evidence",
    }
    allowed_classes = {
        "Product structured",
        "Product callsites",
        "Product broad surface",
        "Mixed heuristic",
        "Dependency surface",
        "Evidence substrate",
    }
    for label, _, domain, classification in rows:
        if domain not in allowed_domains:
            failures.append(f"product surface inventory {label} has invalid domain")
        if classification not in allowed_classes:
            failures.append(f"product surface inventory {label} has invalid classification")

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


def validate_completeness_closure(repo: Path, failures: list[str]) -> None:
    path = repo / "analysis/completeness-audit.md"
    if not path.is_file():
        return
    rows: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        rows[int(cells[0])] = cells[4]
    if sorted(rows) != list(range(1, 37)):
        failures.append(
            "completeness capability coverage mismatch: "
            f"expected=36, actual={len(rows)}"
        )
        return
    for capability, state in sorted(rows.items()):
        if state not in {"Deep", "Boundary"}:
            failures.append(
                f"completeness capability {capability} is not closed: {state}"
            )


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
    for relative in candidate_paths(repo):
        if not relative.endswith(".md"):
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument(
        "--negative-test-fast", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args()

    if (
        args.negative_test_fast
        and os.environ.get("CLAUDE_VALIDATOR_NEGATIVE_TEST") != "1"
    ):
        parser.error("--negative-test-fast is reserved for test_validator_negative.py")

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

    validate_reader_first_analysis(repo, failures)

    private_capture_files = find_private_capture_data(repo)
    if private_capture_files:
        failures.append(
            "private capture data found in publishable files: "
            + ", ".join(private_capture_files)
        )

    if args.negative_test_fast:
        inventory_summary = json.loads(
            (repo / "analysis/source-inventory/summary.json").read_text(
                encoding="utf-8"
            )
        )
        inventory_files = len(inventory_summary.get("files", []))
    else:
        inventory_files = validate_source_inventory(repo, failures)
    validate_product_surface_map(repo, failures)
    validate_completeness_closure(repo, failures)
    validate_human_inventory_facts(repo, failures)
    validate_exhaustive_human_references(repo, failures)
    mechanism_evidence = validate_mechanism_evidence(repo, failures)
    native_behavior_checks = validate_native_reconstruction_report(repo, failures)

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
    print(f"mechanism evidence records checked: {mechanism_evidence}")
    print(f"native behavior checks recorded: {native_behavior_checks}")
    print("capture path privacy: PASS")
    print(f"main source sha256: {sha256(main_source)}")
    if deep_output:
        print(deep_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
