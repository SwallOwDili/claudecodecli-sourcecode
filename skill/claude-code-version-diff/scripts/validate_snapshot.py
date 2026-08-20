#!/usr/bin/env python3
"""Validate a Claude Code version snapshot and its packed-file hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
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
}
EVIDENCE_CLASSES = {"Static", "Probe", "Public", "Boundary"}
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

    if summary.get("formatVersion", 0) < 3:
        failures.append("source inventory formatVersion must be at least 3")
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
    ):
        if completion.get(field) is not True:
            failures.append(f"source inventory completion audit failed: {field}")
    if completion.get("knownStaticExtractionGaps") != []:
        failures.append("source inventory reports known static extraction gaps")

    target_coverage = summary.get("coverage", {}).get("targetCallsites", {})
    expected_target_files = {
        "H": "first-party-event-callsites",
        "Fv": "first-party-event-callsites",
        "Nd": "otel-event-callsites",
        "et": "feature-flag-callsites",
        "CB": "growthbook-callsites",
    }
    for callee, inventory_name in expected_target_files.items():
        total = target_coverage.get(callee, {}).get("total")
        if not isinstance(total, int) or total < 1:
            failures.append(f"source inventory callsite coverage missing for {callee}")
    first_party_total = sum(
        target_coverage.get(callee, {}).get("total", 0) for callee in ("H", "Fv")
    )
    if first_party_total != counts.get("first-party-event-callsites"):
        failures.append("first-party callsite coverage does not match JSONL count")
    for callee in ("Nd", "et", "CB"):
        if target_coverage.get(callee, {}).get("total") != counts.get(
            expected_target_files[callee]
        ):
            failures.append(f"{callee} callsite coverage does not match JSONL count")

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
    if manifest.get("schemaVersion") != 1:
        failures.append("public source manifest schemaVersion must equal 1")
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
    excerpts = excerpts_path.read_text(encoding="utf-8")
    heading_matches = list(re.finditer(r"^## `([^`]+)`\s*$", excerpts, re.MULTILINE))
    excerpt_ids = {match.group(1) for match in heading_matches}
    if len(excerpt_ids) != len(heading_matches):
        failures.append("public source excerpt file contains duplicate headings")
    excerpt_owners: dict[str, str] = {}
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

        if evidence_class == "Static":
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

    validate_markdown_source_references(repo, failures)
    return len(records)


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

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

    readme = (repo / "README.md").read_text(encoding="utf-8")
    readme_first_screen = readme.split("## 快照信息", 1)[0]
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

    private_capture_files = find_private_capture_data(repo)
    if private_capture_files:
        failures.append(
            "private capture data found in publishable files: "
            + ", ".join(private_capture_files)
        )

    inventory_files = validate_source_inventory(repo, failures)
    mechanism_evidence = validate_mechanism_evidence(repo, failures)

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
    if reverse.is_dir():
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
    print("capture path privacy: PASS")
    print(f"main source sha256: {sha256(main_source)}")
    if deep_output:
        print(deep_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
