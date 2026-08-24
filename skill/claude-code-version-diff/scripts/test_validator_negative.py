#!/usr/bin/env python3
"""Prove that the snapshot validator rejects publication regressions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from typing import Callable


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_validator(
    repo: Path,
    validator: Path,
    *,
    fast: bool = False,
    expected: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(validator), str(repo)]
    environment = os.environ.copy()
    if fast:
        command.append("--negative-test-fast")
        environment["CLAUDE_VALIDATOR_NEGATIVE_TEST"] = "1"
    if expected is not None:
        command.extend(["--negative-test-expect", expected])
    return subprocess.run(
        command,
        cwd=repo,
        text=True,
        capture_output=True,
        env=environment,
    )


def text_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def expect_rejection(
    repo: Path,
    validator: Path,
    relative: str,
    mutate: Callable[[bytes], bytes],
    expected: str,
    *,
    fast: bool = True,
) -> None:
    path = repo / relative
    original = path.read_bytes()
    original_hash = sha256(original)
    changed = mutate(original)
    if changed == original:
        raise RuntimeError(f"negative mutation did not change {relative}")
    try:
        path.write_bytes(changed)
        result = run_validator(
            repo,
            validator,
            fast=fast,
            expected=expected if fast else None,
        )
        output = text_output(result)
        if result.returncode == 0:
            raise RuntimeError(f"validator accepted negative case for {relative}")
        if expected not in output:
            raise RuntimeError(
                f"validator rejected {relative} for an unexpected reason:\n{output}"
            )
    finally:
        path.write_bytes(original)
    if sha256(path.read_bytes()) != original_hash:
        raise RuntimeError(f"failed to restore {relative}")


def expect_missing_rejection(
    repo: Path,
    validator: Path,
    relative: str,
    expected: str,
) -> None:
    path = repo / relative
    original = path.read_bytes()
    original_hash = sha256(original)
    displaced = path.with_name(path.name + ".negative-test-missing")
    if displaced.exists():
        raise RuntimeError(f"negative-test displacement already exists: {displaced}")
    try:
        path.replace(displaced)
        result = run_validator(repo, validator, fast=True, expected=expected)
        output = text_output(result)
        if result.returncode == 0:
            raise RuntimeError(f"validator accepted missing file for {relative}")
        if expected not in output:
            raise RuntimeError(
                f"validator rejected missing {relative} for an unexpected reason:\n{output}"
            )
    finally:
        if displaced.exists():
            displaced.replace(path)
    if sha256(path.read_bytes()) != original_hash:
        raise RuntimeError(f"failed to restore missing-file case for {relative}")


def replace_once(original: bytes, old: bytes, new: bytes) -> bytes:
    if old not in original:
        raise RuntimeError(f"negative-test anchor is missing: {old!r}")
    return original.replace(old, new, 1)


def replace_in_h2_section(
    original: bytes,
    heading_prefix: str,
    old: str,
    new: str,
    *,
    replace_all: bool = False,
) -> bytes:
    content = original.decode("utf-8")
    heading = content.find(f"## {heading_prefix}")
    if heading < 0:
        raise RuntimeError(
            f"negative-test section heading is missing: {heading_prefix!r}"
        )
    following = content.find("\n## ", heading + 3)
    end = len(content) if following < 0 else following
    section = content[heading:end]
    if old not in section:
        raise RuntimeError(
            f"negative-test section anchor is missing: {heading_prefix!r} / {old!r}"
        )
    changed = section.replace(old, new) if replace_all else section.replace(old, new, 1)
    return (content[:heading] + changed + content[end:]).encode("utf-8")


def insert_product_first_screen_table(original: bytes) -> bytes:
    content = original.decode("utf-8")
    first_h2 = content.find("\n## ")
    if first_h2 < 0:
        raise RuntimeError("negative-test product first H2 is missing")
    table = (
        "\n\n| 文件 | 数量 |\n"
        "| --- | ---: |\n"
        "| lexical inventory | 71 |\n"
    )
    return (content[:first_h2] + table + content[first_h2:]).encode("utf-8")


def confuse_product_version_and_baseline(original: bytes) -> bytes:
    return replace_once(
        original,
        "这些是**版本特征**".encode(),
        "这些是**架构特征**".encode(),
    )


def swap_product_h2_sections(
    original: bytes,
    first_heading: str,
    second_heading: str,
) -> bytes:
    content = original.decode("utf-8")
    first_start = content.find(f"## {first_heading}")
    second_start = content.find(f"## {second_heading}")
    if first_start < 0 or second_start < 0 or first_start >= second_start:
        raise RuntimeError("negative-test product chapter order anchors are missing")
    first_end = second_start
    following = content.find("\n## ", second_start + 3)
    second_end = len(content) if following < 0 else following + 1
    first = content[first_start:first_end]
    second = content[second_start:second_end]
    return (
        content[:first_start] + second + first + content[second_end:]
    ).encode("utf-8")


def pile_product_source_links(original: bytes) -> bytes:
    anchor = "用户还没有提交“改端口”"
    links = (
        " [证据一](../reverse/javascript/cli.readable.js#L1)"
        " [证据二](../reverse/javascript/cli.readable.js#L2)"
        " [证据三](../reverse/javascript/cli.readable.js#L3)"
    )
    return replace_once(original, anchor.encode(), (anchor + links).encode())


def replace_product_extension_prose_with_table(original: bytes) -> bytes:
    content = original.decode("utf-8")
    heading = "## 扩展与委派："
    start = content.find(heading)
    if start < 0:
        raise RuntimeError("negative-test product extension heading is missing")
    body_start = content.find("\n", start) + 1
    details = content.find("<details>", body_start)
    if body_start <= 0 or details < 0:
        raise RuntimeError("negative-test product extension prose/details boundary is missing")
    prose = content[body_start:details].strip()
    paragraphs = [value.strip() for value in re.split(r"\n\s*\n", prose) if value.strip()]
    rows = ["| 审计项 | 原正文 |", "| --- | --- |"]
    for index, paragraph in enumerate(paragraphs, 1):
        flattened = re.sub(r"\s+", " ", paragraph).replace("|", "\\|")
        rows.append(f"| {index} | {flattened} |")
    table = "\n".join(rows) + "\n\n"
    return (content[:body_start] + table + content[details:]).encode("utf-8")


def append_product_repeated_ending(original: bytes) -> bytes:
    content = original.decode("utf-8")
    navigation = content.find("## 按问题继续阅读")
    if navigation < 0:
        raise RuntimeError("negative-test product navigation heading is missing")
    repeated = (
        "## 第二个结论\n\n"
        "这是另一个独立结尾，把恢复再总结一次，破坏唯一综合判断。\n\n"
    )
    return (content[:navigation] + repeated + content[navigation:]).encode("utf-8")


def invert_product_concurrency_contract(original: bytes) -> bytes:
    changed = replace_in_h2_section(
        original,
        "从提议到副作用：一轮 Agent 工作怎样交接所有权",
        "不会回头重算并发分类",
        "会回头重算并发分类",
    )
    return replace_in_h2_section(
        changed,
        "从提议到副作用：一轮 Agent 工作怎样交接所有权",
        "不重算 concurrency class",
        "重算 concurrency class",
    )


def replace_release_notes_mechanism_row(original: bytes, row_number: int) -> bytes:
    content = original.decode("utf-8")
    section_start = content.find("## 逐项机制回填")
    section_end = content.find("## 这 19 条合起来说明了什么", section_start)
    if section_start < 0 or section_end < 0:
        raise RuntimeError("negative-test release notes mechanism table is missing")
    section = content[section_start:section_end]
    match = re.search(rf"(?m)^\|\s*{row_number}\s*\|[^\n]*$", section)
    if match is None:
        raise RuntimeError(
            f"negative-test release notes mechanism row is missing: {row_number}"
        )
    cells = [cell.strip() for cell in match.group(0).strip().strip("|").split("|")]
    if len(cells) != 5:
        raise RuntimeError(
            f"negative-test release notes mechanism row {row_number} is malformed"
        )
    cells[1:4] = [
        "这是一段长度足够但与该版本机制无关的通用失败状态说明",
        "这是一段长度足够但与该版本机制无关的通用状态变化说明",
        "用户只得到一段长度足够但与该版本机制无关的通用结果说明",
    ]
    replacement = "| " + " | ".join(cells) + " |"
    changed_section = section[: match.start()] + replacement + section[match.end() :]
    return (content[:section_start] + changed_section + content[section_end:]).encode(
        "utf-8"
    )


def remove_numbered_lifecycle(original: bytes, heading_prefix: str) -> bytes:
    content = original.decode("utf-8")
    heading = content.find(f"## {heading_prefix}")
    if heading < 0:
        raise RuntimeError(
            f"negative-test lifecycle heading is missing: {heading_prefix!r}"
        )
    following = content.find("\n## ", heading + 3)
    end = len(content) if following < 0 else following
    section = content[heading:end]
    changed, count = re.subn(
        r"(?m)^(\s*)(\d+)\.\s+",
        r"\1步骤 \2：",
        section,
    )
    if count == 0:
        raise RuntimeError(
            f"negative-test lifecycle has no numbered steps: {heading_prefix!r}"
        )
    return (content[:heading] + changed + content[end:]).encode("utf-8")


def remove_labeled_dot_edges(original: bytes) -> bytes:
    lines = original.splitlines(keepends=True)
    changed = 0
    for index, line in enumerate(lines):
        if b"->" in line and b"[label=" in line:
            lines[index] = line.replace(b"[label=", b"[xlabel=", 1)
            changed += 1
    if changed == 0:
        raise RuntimeError("negative-test DOT has no labeled edges")
    return b"".join(lines)


def corrupt_discovered_symbol(original: bytes) -> bytes:
    document = json.loads(original)
    roles = document["discoveredSymbols"]["roles"]
    roles["firstPartyEventAsync"] = roles["firstPartyEventAsync"] + "_WRONG"
    return (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode()


def downgrade_first_capability(original: bytes) -> bytes:
    return downgrade_capability(original, 1)


def downgrade_capability(original: bytes, capability: int) -> bytes:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(f"| {capability} |".encode()) and b"| Deep |" in line:
            lines[index] = line.replace(b"| Deep |", b"| Documented |", 1)
            return b"".join(lines)
    raise RuntimeError(f"negative-test capability {capability} row is missing")


def replace_capability_state(
    original: bytes,
    capability: int,
    old: bytes,
    new: bytes,
) -> bytes:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(f"| {capability} |".encode()) and old in line:
            lines[index] = line.replace(old, new, 1)
            return b"".join(lines)
    raise RuntimeError(
        f"negative-test capability {capability} state {old!r} is missing"
    )


def replace_in_capability_row(
    original: bytes,
    capability: int,
    old: bytes,
    new: bytes,
) -> bytes:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(f"| {capability} |".encode()) and old in line:
            lines[index] = line.replace(old, new, 1)
            return b"".join(lines)
    raise RuntimeError(
        f"negative-test capability {capability} row anchor {old!r} is missing"
    )


def remove_capability_row(original: bytes, capability: int) -> bytes:
    prefix = f"| {capability} |".encode()
    lines = original.splitlines(keepends=True)
    remaining = [line for line in lines if not line.startswith(prefix)]
    if len(remaining) == len(lines):
        raise RuntimeError(f"negative-test capability {capability} row is missing")
    return b"".join(remaining)


def truncate_mechanism_topic_claims(
    original: bytes,
    topic: str,
    retain: int,
) -> bytes:
    lines = original.splitlines(keepends=True)
    remaining: list[bytes] = []
    topic_count = 0
    removed_count = 0
    for line in lines:
        if line.strip():
            record = json.loads(line)
            if record.get("topic") == topic:
                topic_count += 1
                if topic_count > retain:
                    removed_count += 1
                    continue
        remaining.append(line)
    if topic_count <= retain or removed_count == 0:
        raise RuntimeError(
            f"negative-test mechanism topic {topic!r} has only {topic_count} claims"
        )
    return b"".join(remaining)


def remove_mechanism_claim(original: bytes, claim_id: str) -> bytes:
    lines = original.splitlines(keepends=True)
    remaining: list[bytes] = []
    removed = 0
    for line in lines:
        if line.strip() and json.loads(line).get("claimId") == claim_id:
            removed += 1
            continue
        remaining.append(line)
    if removed != 1:
        raise RuntimeError(
            f"negative-test mechanism claim {claim_id!r} count is {removed}, expected 1"
        )
    return b"".join(remaining)


def encode_jsonl_record(record: dict) -> bytes:
    return (
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode()


def remove_tool_registration(original: bytes, name: str) -> bytes:
    lines = original.splitlines(keepends=True)
    remaining: list[bytes] = []
    removed = 0
    for line in lines:
        record = json.loads(line)
        if record.get("name") == name:
            removed += 1
            continue
        remaining.append(line)
    if removed != 1:
        raise RuntimeError(
            f"negative-test tool registration {name!r} count is {removed}"
        )
    return b"".join(remaining)


def set_first_dynamic_tool_name(original: bytes) -> bytes:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        record = json.loads(line)
        if record.get("name") is None:
            record["name"] = "NegativeDynamicTool"
            lines[index] = encode_jsonl_record(record)
            return b"".join(lines)
    raise RuntimeError("negative-test dynamic tool registration is missing")


def corrupt_first_tool_factory(original: bytes) -> bytes:
    lines = original.splitlines(keepends=True)
    if not lines:
        raise RuntimeError("negative-test tool registration inventory is empty")
    record = json.loads(lines[0])
    record["factorySymbol"] = "Xi"
    lines[0] = encode_jsonl_record(record)
    return b"".join(lines)


def decode_first_tool_comparison_value(original: bytes) -> bytes:
    lines = original.splitlines(keepends=True)
    if not lines:
        raise RuntimeError("negative-test tool registration inventory is empty")
    record = json.loads(lines[0])
    comparison_value = record.get("comparisonValue")
    if not isinstance(comparison_value, str):
        raise RuntimeError("negative-test comparisonValue is not a string")
    record["comparisonValue"] = json.loads(comparison_value)
    lines[0] = encode_jsonl_record(record)
    return b"".join(lines)


def corrupt_brief_comparison_alias(original: bytes) -> bytes:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        record = json.loads(line)
        if record.get("name") != "SendUserMessage":
            continue
        comparison_value = record.get("comparisonValue")
        if not isinstance(comparison_value, str):
            raise RuntimeError("negative-test Brief comparisonValue is not a string")
        comparison = json.loads(comparison_value)
        comparison["aliases"] = []
        record["comparisonValue"] = json.dumps(
            comparison,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        lines[index] = encode_jsonl_record(record)
        return b"".join(lines)
    raise RuntimeError("negative-test SendUserMessage registration is missing")


def remove_brief_alias(original: bytes) -> bytes:
    lines = original.splitlines(keepends=True)
    for index, line in enumerate(lines):
        record = json.loads(line)
        if record.get("name") == "SendUserMessage":
            aliases = record.get("aliases", [])
            if "Brief" not in aliases:
                raise RuntimeError("negative-test Brief alias is already missing")
            record["aliases"] = [alias for alias in aliases if alias != "Brief"]
            lines[index] = encode_jsonl_record(record)
            return b"".join(lines)
    raise RuntimeError("negative-test SendUserMessage registration is missing")


def remove_internal_entrypoint_protocol(original: bytes) -> bytes:
    document = json.loads(original)
    entrypoints = document.get("internalEntrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        raise RuntimeError("negative-test internal entrypoint inventory is empty")
    entry = entrypoints[0]
    if not isinstance(entry, dict) or "inputProtocol" not in entry:
        raise RuntimeError("negative-test internal entrypoint inputProtocol is missing")
    del entry["inputProtocol"]
    return (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument(
        "--start-case",
        type=int,
        default=1,
        help="resume at the 1-based negative-case number",
    )
    parser.add_argument(
        "--end-case",
        type=int,
        help="stop after this 1-based negative-case number",
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="skip the positive baseline when resuming a previously verified run",
    )
    args = parser.parse_args()
    if args.start_case < 1:
        parser.error("--start-case must be at least 1")
    if args.end_case is not None and args.end_case < args.start_case:
        parser.error("--end-case must be greater than or equal to --start-case")
    if args.skip_baseline and args.start_case == 1:
        parser.error("--skip-baseline requires --start-case greater than 1")
    repo = Path(args.repo).resolve()
    validator = repo / "skill/claude-code-version-diff/scripts/validate_snapshot.py"
    snapshot_version = (repo / "VERSION").read_text(encoding="utf-8").strip().encode()
    version_metadata = json.loads((repo / "analysis/version.json").read_text())
    binary_sha = version_metadata["binary"]["sha256"].encode()
    inventory_summary = json.loads(
        (repo / "analysis/source-inventory/summary.json").read_text()
    )
    datadog_count = str(inventory_summary["counts"]["datadog-forwarded-events"]).encode()

    if not args.skip_baseline:
        baseline = run_validator(repo, validator)
        if baseline.returncode != 0:
            raise RuntimeError(f"baseline validator failed:\n{text_output(baseline)}")

    personal_path = ("/" + "Users" + "/validator-fixture/private.txt").encode()
    cases: list[tuple[str, Callable[[bytes], bytes], str]] = [
        (
            "README.md",
            lambda data: data + b"\nnegative privacy fixture: " + personal_path + b"\n",
            "private capture data found in publishable files",
        ),
        (
            "README.md",
            lambda data: replace_once(
                data,
                b"# Claude Code CLI " + snapshot_version,
                b"# Claude Code CLI 0.0.0",
            ),
            "README title does not match VERSION",
        ),
        (
            "README.md",
            lambda data: replace_once(data, binary_sha, b"0" * 64),
            "README binary SHA-256 does not match analysis/version.json",
        ),
        (
            "analysis/risk-control-surface.txt",
            lambda data: replace_once(
                data,
                b"# Version: " + snapshot_version,
                b"# Version: 0.0.0",
            ),
            "risk-control surface version does not match VERSION",
        ),
        (
            "analysis/public-claims-validation.md",
            lambda data: data + b"\nCommand: $CLAUDE_9_9_9 --version\n",
            "version-specific Claude binary placeholder found",
        ),
        (
            "analysis/source-surface.md",
            lambda data: replace_once(
                data,
                b"datadog-forwarded-events.txt) | " + datadog_count + b" |",
                b"datadog-forwarded-events.txt) | 999 |",
            ),
            "human source-surface count mismatch for datadog-forwarded-events",
        ),
        (
            "README.md",
            lambda data: data + b"\n" + b"[fixture](fixture)\n" * 60,
            "README front door has too many links",
        ),
        (
            "analysis/public-source-excerpts.md",
            lambda data: replace_once(
                data,
                b"When you give Claude a task",
                b"When you give Claude a task now",
            ),
            "hash differs from manifest",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_once(
                data,
                b"whole-prompt-cache invalidation",
                b"prompt-cache invalidation",
            ),
            "release notes upstream verbatim block mismatch",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_once(
                data,
                b"mcp-agents-background.md",
                b"mcp-agents-background-missing.md",
            ),
            "release notes mechanism row 17 lacks required binding mcp-agents-background.md",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_release_notes_mechanism_row(data, 7),
            "release notes mechanism row 7 lacks semantic marker notebook in mechanism",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_release_notes_mechanism_row(data, 9),
            "release notes mechanism row 9 lacks semantic marker background-updater in mechanism",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_release_notes_mechanism_row(data, 10),
            "release notes mechanism row 10 lacks semantic marker open-tasks in mechanism",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_release_notes_mechanism_row(data, 13),
            "release notes mechanism row 13 lacks semantic marker pathological-pattern in mechanism",
        ),
        (
            "analysis/release-notes.md",
            lambda data: replace_release_notes_mechanism_row(data, 19),
            "release notes mechanism row 19 lacks semantic marker vscode in mechanism",
        ),
        (
            "analysis/runtime-probe-index.md",
            lambda data: data.replace(
                b"`probe.agent-loop-tool-feedback`",
                b"probe.agent-loop-tool-feedback",
            ),
            "Probe claim is missing from runtime probe index",
        ),
        (
            "analysis/runtime-probes/runtime-controls.json",
            lambda data: replace_once(
                data,
                b'"exactVersion": true',
                b'"exactVersion": false',
            ),
            "required probe check failed: exactVersion",
        ),
        (
            "analysis/runtime-probes/embedded-grep.json",
            lambda data: replace_once(
                data,
                b'"pathologicalPeakRssBounded": true',
                b'"pathologicalPeakRssBounded": false',
            ),
            "required probe check failed: pathologicalPeakRssBounded",
        ),
        (
            "analysis/runtime-probes/telemetry-otlp.json",
            lambda data: replace_once(
                data,
                b'"rawInlineContainsRequestMarker": true',
                b'"rawInlineContainsRequestMarker": false',
            ),
            "required probe check failed: rawInlineContainsRequestMarker",
        ),
        (
            "analysis/runtime-probes/otlp-tls.json",
            lambda data: replace_once(
                data,
                b'"mtlsClientAuthorized": true',
                b'"mtlsClientAuthorized": false',
            ),
            "OTLP TLS probe: required check failed: mtlsClientAuthorized",
        ),
        (
            "analysis/runtime-probes/tui-regressions.json",
            lambda data: replace_once(
                data,
                b'"shiftTabDidNotSettlePrompt": true',
                b'"shiftTabDidNotSettlePrompt": false',
            ),
            "required probe check failed: shiftTabDidNotSettlePrompt",
        ),
        (
            "analysis/runtime-probes/native-reconstruction-x86.json",
            lambda data: replace_once(
                data,
                b'"x86RuntimeCoverage": true',
                b'"x86RuntimeCoverage": false',
            ),
            "x86_64 native reconstruction required check failed: x86RuntimeCoverage",
        ),
        (
            "analysis/runtime-probes/native-reconstruction-x86.json",
            lambda data: replace_once(
                data,
                b'"fileKind": "regular-file"',
                b'"fileKind": "symlink"',
            ),
            "x86_64 original artifact provenance mismatch",
        ),
        (
            "analysis/runtime-probes/native-reconstruction-x86.json",
            lambda data: replace_once(
                data,
                b'"method": "validated-artifacts-and-runtime"',
                b'"method": "build-and-runtime"',
            ),
            "x86_64 native attestation scope overclaims build provenance",
        ),
        (
            "analysis/runtime-probes/native-reconstruction-x86.json",
            lambda data: replace_once(
                data,
                b'"commands": {\n    "behavior":',
                b'"commands": {\n    "rustBuild": "unobserved",\n    "behavior":',
            ),
            "x86_64 native report must record only its behavior command",
        ),
        (
            "analysis/runtime-probes/project-data-lifecycle.json",
            lambda data: replace_once(
                data,
                b'"zipMismatchKeepsTranscript": true',
                b'"zipMismatchKeepsTranscript": false',
            ),
            "required probe check failed: zipMismatchKeepsTranscript",
        ),
        (
            "analysis/runtime-probes/network-proxy-tls.json",
            lambda data: replace_once(
                data,
                b'"mtlsClientCertificateObserved": true',
                b'"mtlsClientCertificateObserved": false',
            ),
            "network proxy/TLS probe: required check failed: mtlsClientCertificateObserved",
        ),
        (
            "analysis/runtime-probes/plugin-evaluation.json",
            lambda data: replace_once(
                data,
                b'"withoutRequestOmitsPluginHookContext": true',
                b'"withoutRequestOmitsPluginHookContext": false',
            ),
            "Plugin Evaluation probe: required check failed: withoutRequestOmitsPluginHookContext",
        ),
        (
            "analysis/network-proxy-ca-and-mtls.md",
            lambda data: replace_once(
                data,
                b"7. TLS handshake",
                b"7. Secure connection",
            ),
            "deep topic contract network-proxy-mtls lifecycle is missing TLS handshake",
        ),
        (
            "analysis/visuals/network-proxy-ca-mtls.dot",
            lambda data: replace_once(
                data,
                b"NO_PROXY match?",
                b"Bypass match?",
            ),
            "deep topic visual network-proxy-mtls is missing state anchor: NO_PROXY match?",
        ),
        (
            "analysis/plugin-evaluation-harness.md",
            lambda data: replace_once(
                data,
                b"5. ablation planner",
                b"5. experiment planner",
            ),
            "deep topic contract plugin-evaluation lifecycle is missing ablation planner",
        ),
        (
            "analysis/visuals/plugin-evaluation-lifecycle.dot",
            lambda data: replace_once(
                data,
                b"Ablation planner",
                b"Experiment planner",
            ),
            "deep topic visual plugin-evaluation is missing state anchor: Ablation planner",
        ),
        (
            "analysis/source-inventory/summary.json",
            corrupt_discovered_symbol,
            "callsite symbol mismatch for firstPartyEventAsync",
        ),
        (
            "analysis/source-inventory/environment-schema.jsonl",
            lambda data: b"",
            "source inventory line count mismatch",
        ),
        (
            "analysis/source-inventory/claude-storage-namespaces.txt",
            lambda data: replace_once(data, b"transcript\n", b""),
            "source inventory line count mismatch",
        ),
        (
            "analysis/source-inventory/tool-registrations.jsonl",
            lambda data: remove_tool_registration(data, "StructuredOutput"),
            "tool registration row count mismatch: expected=80, actual=79",
        ),
        (
            "analysis/source-inventory/tool-registrations.jsonl",
            set_first_dynamic_tool_name,
            "static tool registration count mismatch: expected=77, actual=78",
        ),
        (
            "analysis/source-inventory/tool-registrations.jsonl",
            corrupt_first_tool_factory,
            "tool registration rows use unexpected factory symbols",
        ),
        (
            "analysis/source-inventory/tool-registrations.jsonl",
            decode_first_tool_comparison_value,
            "tool registration comparisonValue must be a JSON string",
        ),
        (
            "analysis/source-inventory/tool-registrations.jsonl",
            corrupt_brief_comparison_alias,
            "tool registration comparison aliases mismatch",
        ),
        (
            "analysis/source-inventory/tool-registrations.jsonl",
            remove_brief_alias,
            "tool registration SendUserMessage legacy alias mismatch",
        ),
        (
            "analysis/agent-loop.md",
            lambda data: replace_once(
                data,
                b"## 60 \xe7\xa7\x92\xe7\x90\x86\xe8\xa7\xa3 Agent Loop",
                b"## Agent Loop overview",
            ),
            "reader-first human document is missing 60-second section",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_once(
                data,
                "![一次用户任务包含模型迭代、API attempt 与工具批次，结果回灌后才决定是否继续](visuals/agent-loop-lifecycle.svg)".encode(),
                "![Agent Loop 流程图](visuals/agent-loop-lifecycle.svg)".encode(),
            ),
            "product surface Agent Loop visual must expose user task, model iteration",
        ),
        (
            "analysis/auto-mode-classifier.md",
            lambda data: replace_once(
                data,
                b"twoStageClassifier",
                b"stageClassifierMissing",
            ),
            "human analysis document analysis/auto-mode-classifier.md does not cover 'twoStageClassifier'",
        ),
        (
            "analysis/plugin-evaluation-harness.md",
            lambda data: replace_once(
                data,
                "六类 grader".encode(),
                "五类 grader".encode(),
            ),
            "human analysis document analysis/plugin-evaluation-harness.md does not cover '六类 grader'",
        ),
        (
            "analysis/runtime-supervision-and-processes.md",
            lambda data: replace_once(
                data,
                "launcher exit 0 但 Claude 尚未 ready".encode(),
                "launcher 已退出".encode(),
            ),
            "human analysis document analysis/runtime-supervision-and-processes.md does not cover 'launcher exit 0 但 Claude 尚未 ready'",
        ),
        (
            "analysis/enterprise-gateway-runtime.md",
            lambda data: replace_once(
                data,
                "`x-api-key` 一旦出现，就不再回退 bearer".encode(),
                "`x-api-key` 校验失败后回退 bearer".encode(),
            ),
            "human analysis document analysis/enterprise-gateway-runtime.md does not cover '`x-api-key` 一旦出现，就不再回退 bearer'",
        ),
        (
            "analysis/auth-account-and-subscription-lifecycle.md",
            lambda data: replace_once(
                data,
                b"preserveInProcessTokens",
                b"preserveCurrentProcessTokens",
            ),
            "human analysis document analysis/auth-account-and-subscription-lifecycle.md does not cover 'preserveInProcessTokens'",
        ),
        (
            "analysis/tool-registration-and-host-surfaces.md",
            lambda data: replace_once(data, b"77 + 3", b"77 and 3"),
            "human analysis document analysis/tool-registration-and-host-surfaces.md does not cover '77 + 3'",
        ),
        (
            "analysis/brief-mode-and-user-visible-output.md",
            lambda data: replace_once(
                data,
                b"DISABLE_BRIEF_MODE_STOP_HOOK",
                b"BRIEF_MODE_STOP_HOOK_DISABLED",
            ),
            "human analysis document analysis/brief-mode-and-user-visible-output.md does not cover 'DISABLE_BRIEF_MODE_STOP_HOOK'",
        ),
        (
            "analysis/tool-registration-and-host-surfaces.md",
            lambda data: replace_once(
                data,
                b"toolRegistration:SendUserMessage:1",
                b"toolRegistration:SendUserMessageMissing:1",
            ),
            "human tool registration coverage mismatch",
        ),
        (
            "analysis/tool-registration-and-host-surfaces.md",
            lambda data: replace_once(
                data,
                b"| `toolRegistration:SendUserMessage:1` | `SendUserMessage`; alias `Brief` | `Conditional CLI` |",
                b"| `toolRegistration:SendUserMessage:1` | `SendUserMessage`; alias `Brief` | `Core terminal` |",
            ),
            "human tool registration classification mismatch",
        ),
        (
            "analysis/builtin-tools-reference.md",
            lambda data: replace_once(
                data,
                b"| `Artifact` |",
                b"| `ArtifactMissing` |",
            ),
            "human built-in tool coverage mismatch",
        ),
        (
            "analysis/settings-reference.md",
            lambda data: replace_once(
                data,
                b"001 $schema",
                b"001 schema_missing",
            ),
            "human direct root setting coverage mismatch",
        ),
        (
            "analysis/cli-sdk-output-protocol.md",
            lambda data: replace_once(
                data,
                b"| `initialize` | client -> loop |",
                b"| `initialize_missing` | client -> loop |",
            ),
            "human SDK subtype coverage mismatch",
        ),
        (
            "analysis/cli-sdk-output-protocol.md",
            lambda data: replace_once(
                data,
                b"`add-dir`, `autocompact`",
                b"`add-dir-missing`, `autocompact`",
            ),
            "human slash-command coverage mismatch",
        ),
        (
            "analysis/slash-command-reference.md",
            lambda data: replace_once(
                data,
                b"001 add-dir",
                b"001 add-dir-missing",
            ),
            "human slash-command reference coverage mismatch",
        ),
        (
            "analysis/hooks-event-reference.md",
            lambda data: replace_once(
                data,
                b"<!-- hook-event:ConfigChange -->",
                b"<!-- hook-event:ConfigChangeMissing -->",
            ),
            "human Hook event coverage mismatch",
        ),
        (
            "analysis/hooks-event-reference.md",
            lambda data: replace_once(
                data,
                "不自动重新请求模型".encode(),
                "不再请求模型".encode(),
            ),
            "human analysis document analysis/hooks-event-reference.md does not cover '不自动重新请求模型'",
        ),
        (
            "analysis/tools-permissions-hooks.md",
            lambda data: replace_once(
                data,
                "不会像 Stop hook 一样自动重入模型".encode(),
                "会自动重入模型".encode(),
            ),
            "human analysis document analysis/tools-permissions-hooks.md does not cover '不会像 Stop hook 一样自动重入模型'",
        ),
        (
            "analysis/storage-v5-reference.md",
            lambda data: replace_once(
                data,
                b"<!-- storage-namespace:transcript -->",
                b"<!-- storage-namespace:transcriptMissing -->",
            ),
            "human Claude storage namespace coverage mismatch",
        ),
        (
            "analysis/storage-v5-reference.md",
            lambda data: data.replace(b"tornTailBytes", b"tornTailMissing"),
            "human analysis document analysis/storage-v5-reference.md does not cover 'tornTailBytes'",
        ),
        (
            "analysis/cli-command-inventory.json",
            remove_internal_entrypoint_protocol,
            "CLI internal entrypoint 1 has invalid inputProtocol",
        ),
        (
            "analysis/sessions-checkpoints-memory.md",
            lambda data: data.replace(b"SharedInode", b"SharedLinkGuardMissing"),
            "human analysis document analysis/sessions-checkpoints-memory.md does not cover 'SharedInode'",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`tool-registrations.jsonl`]",
                b"[`tool-registrations-missing.jsonl`]",
            ),
            "product surface inventory coverage mismatch",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`api-path-templates.jsonl`](source-inventory/api-path-templates.jsonl) | `Template-prefix projection` | `Mixed` | `Candidate`",
                b"[`api-path-templates.jsonl`](source-inventory/api-path-templates.jsonl) | `Targeted AST` | `Product` | `Callsite`",
            ),
            "product surface inventory api-path-templates.jsonl must use axes",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`environment-access-callsites.jsonl`](source-inventory/environment-access-callsites.jsonl) | `Whole-bundle AST` | `Mixed` | `Callsite`",
                b"[`environment-access-callsites.jsonl`](source-inventory/environment-access-callsites.jsonl) | `Whole-bundle AST` | `Product` | `Callsite`",
            ),
            "product surface environment inventory environment-access-callsites.jsonl ownership must be Mixed",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`dynamic-process-environment-callsites.jsonl`](source-inventory/dynamic-process-environment-callsites.jsonl) | `Whole-bundle AST` | `Mixed` | `Callsite`",
                b"[`dynamic-process-environment-callsites.jsonl`](source-inventory/dynamic-process-environment-callsites.jsonl) | `Whole-bundle AST` | `Product` | `Callsite`",
            ),
            "product surface environment inventory dynamic-process-environment-callsites.jsonl ownership must be Mixed",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`otel-environment-variables.txt`](source-inventory/otel-environment-variables.txt) | `Prefix-filtered environment union` | `Mixed` | `Candidate`",
                b"[`otel-environment-variables.txt`](source-inventory/otel-environment-variables.txt) | `Prefix-filtered environment union` | `Product` | `Candidate`",
            ),
            "product surface environment inventory otel-environment-variables.txt ownership must be Mixed",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`environment-schema.jsonl`](source-inventory/environment-schema.jsonl) | `Environment-builder extraction` | `Mixed` | `Declaration`",
                b"[`environment-schema.jsonl`](source-inventory/environment-schema.jsonl) | `Environment-builder extraction` | `Product` | `Declaration`",
            ),
            "product surface environment inventory environment-schema.jsonl ownership must be Mixed",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`observability-environment-defaults.jsonl`](source-inventory/observability-environment-defaults.jsonl) | `Observability-filtered environment callsites` | `Mixed` | `Callsite`",
                b"[`observability-environment-defaults.jsonl`](source-inventory/observability-environment-defaults.jsonl) | `Observability-filtered environment callsites` | `Product` | `Callsite`",
            ),
            "product surface environment inventory observability-environment-defaults.jsonl ownership must be Mixed",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                b"[`observability-environment-schema.jsonl`](source-inventory/observability-environment-schema.jsonl) | `Observability regex projection` | `Mixed` | `Declaration`",
                b"[`observability-environment-schema.jsonl`](source-inventory/observability-environment-schema.jsonl) | `Observability regex projection` | `Product` | `Declaration`",
            ),
            "product surface environment inventory observability-environment-schema.jsonl ownership must be Mixed",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            insert_product_first_screen_table,
            "product surface reader-first first screen must not contain tables or lists",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            confuse_product_version_and_baseline,
            "product surface version delta must remain separate from baseline architecture",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: swap_product_h2_sections(
                data,
                "能力编译：模型看到什么，也不是模型决定的",
                "从提议到副作用：一轮 Agent 工作怎样交接所有权",
            ),
            "product surface reader-first core chapter order is invalid",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            pile_product_source_links,
            "product surface reader-first prose paragraph has too many source links: capability",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            replace_product_extension_prose_with_table,
            "product surface reader-first ordinary path must start in prose: extension",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            append_product_repeated_ending,
            "product surface reader-first must have one synthesis and no repeated ending",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "折叠证据附录",
                "C/Q/E/S/O 是本文从最终决定权归纳的 Derived 阅读框架，不是源码目录，也不是 Anthropic 官方命名",
                "这是源码原生架构，不是本文归纳模型",
            ),
            "product surface five-plane model must be labeled as a Derived reading model",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "折叠证据附录",
                "它不拥有真实文件、子进程和远端对象",
                "它拥有真实文件、子进程和远端对象",
            ),
            "product surface state plane must own local records",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "从提议到副作用：一轮 Agent 工作怎样交接所有权",
                "| API attempt |",
                "| API request |",
            ),
            "product surface Agent Loop accounting must distinguish user turn",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "能力编译：模型看到什么，也不是模型决定的",
                "advertised",
                "visible-in-bundle-only",
                replace_all=True,
            ),
            "product surface capability compilation must connect trust, settings merge",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "扩展与委派：连接、启动和产生增益是三件事",
                "async_launched",
                "task_started",
                replace_all=True,
            ),
            "product surface dynamic-extension chapter must trace MCP generation",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "从提议到副作用：一轮 Agent 工作怎样交接所有权",
                "| `server_tool_use` | Anthropic 服务端工具生命周期 | 服务端工具及后端 | 不进入 |",
                "| `server_tool_use` | Anthropic 服务端工具生命周期 | 服务端工具及后端 | 进入 |",
            ),
            "product surface execution semantics must distinguish client tool_use from server_tool_use",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            invert_product_concurrency_contract,
            "product surface Bash semantics must classify concurrency on the original input",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "历史变短，现实不变：compact 与 resume 改的是表示",
                "预计算 hit 不发送新 summary request",
                "预计算 hit 仍发送新 summary request",
            ),
            "product surface compact explanation must teach the ordinary miss prompt",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "远端结果未知：Artifact timeout 后，Telemetry 也不能替你下结论",
                "不做 local-version equality",
                "强制做 local-version equality",
            ),
            "product surface Artifact semantics must separate response-schema and target-slug validation",
        ),
        (
            "analysis/visuals/artifact-direct-publish-outcomes.dot",
            lambda data: replace_once(
                data,
                "没有可信提交回执".encode(),
                "普通网络失败".encode(),
            ),
            "product surface Artifact direct-publish visual is missing edge request -> unknown",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "Native 尾声：同一权力边界怎样跨过 ABI",
                "`validated-artifacts-and-runtime`",
                "`build-and-runtime`",
            ),
            "product surface native explanation must trace the Voice lifecycle",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "远端结果未知：Artifact timeout 后，Telemetry 也不能替你下结论",
                "Telemetry 能否证明提交？不能",
                "Telemetry 能否证明提交？能",
            ),
            "product surface telemetry semantics must distinguish first-party, Datadog",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "历史变短，现实不变：compact 与 resume 改的是表示",
                "Artifact reference",
                "Unified transaction handle",
            ),
            "product surface recovery semantics must separate message graph",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_once(
                data,
                "三个不等价的世界".encode(),
                "一个统一世界".encode(),
            ),
            "product surface version delta must remain separate from baseline architecture",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "从提议到副作用：一轮 Agent 工作怎样交接所有权",
                "acceptEdits",
                "acceptAllEdits",
                replace_all=True,
            ),
            "product surface tool authority must separate discovery",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "历史变短，现实不变：compact 与 resume 改的是表示",
                "| Context Hint |",
                "| Context Hint / microcompaction |",
            ),
            "product surface must not collapse the server context-hint protocol",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "远端结果未知：Artifact timeout 后，Telemetry 也不能替你下结论",
                "即使 `OTEL_LOG_USER_PROMPTS` 没开",
                "仅当 `OTEL_LOG_USER_PROMPTS` 已开",
            ),
            "product surface telemetry privacy explanation must cover disabled, inline, and file",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "远端结果未知：Artifact timeout 后，Telemetry 也不能替你下结论",
                "event、exact caller identity 与 comparison fingerprint",
                "wide source range",
            ),
            "product surface telemetry explanation must teach why exact caller identity is required",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_in_h2_section(
                data,
                "三个工程选择",
                "局部恢复",
                "统一恢复控制器",
            ),
            "product surface must derive the version's technical character",
        ),
        (
            "analysis/product-surface-inventory-index.md",
            lambda data: replace_once(
                data,
                "## 全部 71 类机器清单".encode(),
                "## 全部 71/71 精确归属".encode(),
            ),
            "product surface inventory index must say 71 classes are classified",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_once(
                data,
                "Untraced/Inventory only".encode(),
                "Boundary-only".encode(),
            ),
            "product surface evidence must keep Untraced work distinct from Boundary",
        ),
        (
            "analysis/visuals/evidence-surface-lifecycle.dot",
            lambda data: replace_once(
                data,
                b'candidate -> untraced [label="',
                b'candidate -> boundary [label="',
            ),
            "product surface evidence lifecycle is missing edge candidate -> untraced",
        ),
        (
            "analysis/visuals/runtime-authority-lifecycle.dot",
            lambda data: replace_once(
                data,
                b'gate -> effects [label="',
                b'model -> effects [label="',
            ),
            "product surface runtime-authority visual is missing edge gate -> effects",
        ),
        (
            "analysis/visuals/product-surface-runtime-planes.dot",
            lambda data: replace_once(
                data,
                b'loop -> execute [label="',
                b'loop -> state [label="',
            ),
            "product surface runtime-plane visual is missing edge loop -> execute",
        ),
        (
            "analysis/visuals/product-surface-runtime-planes.dot",
            lambda data: replace_once(
                data,
                b'remote -> server_tools [label="',
                b'remote -> execute [label="',
            ),
            "product surface runtime-plane visual is missing edge remote -> server_tools",
        ),
        (
            "analysis/visuals/product-surface-runtime-planes.dot",
            lambda data: replace_once(
                data,
                b"\n}\n",
                b'\n  observe -> request [label="controls retry"];\n}\n',
            ),
            "product surface runtime-plane visual must keep observability as an inbound-only sink",
        ),
        (
            "analysis/visuals/product-surface-runtime-planes.dot",
            lambda data: replace_once(
                data,
                b"\n}\n",
                b'\n  recovery [label="central recovery manager"];\n}\n',
            ),
            "product surface runtime-plane visual must not invent a centralized recovery node",
        ),
        (
            "analysis/visuals/product-surface-runtime-planes.svg",
            lambda data: replace_once(
                data,
                b"<!-- Generated by graphviz version",
                b"<!-- Stale render from graphviz version",
            ),
            "product surface runtime-plane visual rendered SVG differs from DOT regeneration",
        ),
        (
            "analysis/visuals/telemetry-pipeline.dot",
            lambda data: replace_once(
                data,
                b'privacy -> datadog [label="',
                b'privacy -> first [label="',
            ),
            "product surface telemetry visual is missing edge privacy -> datadog",
        ),
        (
            "analysis/environment-variable-reference.md",
            lambda data: replace_once(data, b"str / none", b"bool / none"),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/environment-variable-reference.md",
            lambda data: replace_once(
                data,
                b"\nAGENT_PROXY_AUTH_TOKEN\n",
                b"\nAGENT_PROXY_AUTH_TOKEN_MISSING\n",
            ),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/environment-variable-reference.md",
            lambda data: replace_once(
                data,
                "Static consumer 人工合同：owner=".encode(),
                "Static consumer 人工合同：owner-missing=".encode(),
            ),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/source-inventory/environment-access-callsites.jsonl",
            lambda data: replace_once(
                data,
                b'"accessMode":"read"',
                b'"accessMode":"invalid"',
            ),
            "environment context row has invalid access mode",
        ),
        (
            "analysis/source-inventory/environment-access-callsites.jsonl",
            lambda data: replace_once(
                data,
                b'"resolvedFiniteValues":["OTEL_METRICS_INCLUDE_ACCOUNT_UUID"',
                b'"resolvedFiniteValues":["invalid-name!"',
            ),
            "resolved dynamic environment row has invalid finite names",
        ),
        (
            "analysis/source-inventory/environment-access-callsites.jsonl",
            lambda data: replace_once(
                data,
                b'"primaryReason":"assignment-does-not-dominate-function-executions"',
                b'"primaryReason":"invented-reason"',
            ),
            "unresolved dynamic environment row has invalid reason evidence",
        ),
        (
            "analysis/source-inventory/feature-flag-callsites.jsonl",
            lambda data: replace_once(
                data,
                b'"role":"binary"',
                b'"role":"invalid"',
            ),
            "consumer context row has invalid role",
        ),
        (
            "analysis/feature-flag-reference.md",
            lambda data: replace_once(data, b"361/361", b"360/361"),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/feature-flag-reference.md",
            lambda data: replace_once(
                data,
                b"fallback/precedence=",
                b"fallback/precedence-missing=",
            ),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: data.replace(
                b'"topic":"artifact-watch"',
                b'"topic":"artifact-watch-disabled"',
            ),
            "mechanism topic 'artifact-watch' has 0 claims; minimum is 3",
        ),
        (
            "analysis/feature-flag-reference.md",
            lambda data: replace_once(
                data,
                "Opaque name / Static immediate consumer：codename 本身不可解释".encode(),
                "Opaque name / Static consumer：codename 本身不可解释".encode(),
            ),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/artifact-watch-comment-autoreact.md",
            lambda data: data.replace(b"--watch-artifact", b"--artifact-watch-disabled"),
            "human analysis document analysis/artifact-watch-comment-autoreact.md does not cover '--watch-artifact'",
        ),
        (
            "analysis/insights-history-analysis-pipeline.md",
            lambda data: data.replace(b"270,336", b"270,335"),
            "human analysis document analysis/insights-history-analysis-pipeline.md does not cover '270,336'",
        ),
        (
            "analysis/cli-startup-files-plugins-deeplinks.md",
            lambda data: data.replace(b"--file", b"--startup-file-missing"),
            "human analysis document analysis/cli-startup-files-plugins-deeplinks.md does not cover '--file'",
        ),
        (
            "analysis/complex-slash-command-lifecycles.md",
            lambda data: data.replace(
                b"/install-github-app", b"/github-setup-disabled"
            ),
            "human analysis document analysis/complex-slash-command-lifecycles.md does not cover '/install-github-app'",
        ),
        (
            "analysis/telemetry-event-catalog.md",
            lambda data: replace_once(
                data,
                b"first-party-events:1441",
                b"first-party-events:1440",
            ),
            "telemetry event catalog differs from deterministic regeneration",
        ),
        (
            "analysis/telemetry-event-catalog.md",
            lambda data: replace_once(
                data,
                b"TELEMETRY_EVENT_CATALOG_BEGIN",
                b"TELEMETRY_EVENT_CATALOG_BROKEN",
            ),
            "telemetry event catalog differs from deterministic regeneration",
        ),
        (
            "analysis/telemetry-event-catalog.md",
            lambda data: replace_once(
                data,
                b"TELEMETRY_SCENARIO_SEMANTIC_INDEX",
                b"TELEMETRY_SCENARIO_INDEX_REMOVED",
            ),
            "telemetry event catalog differs from deterministic regeneration",
        ),
        (
            "analysis/api-beta-route-ownership.md",
            lambda data: replace_once(
                data,
                b"Bundled gateway admin handler",
                b"Provider organization consumer",
            ),
            "API/error reference generation check failed",
        ),
        (
            "analysis/api-beta-route-ownership.md",
            lambda data: replace_once(
                data,
                b"<!-- API_PATH_CATALOG_START -->",
                b"<!-- API_PATH_CATALOG_BROKEN -->",
            ),
            "API/error reference generation check failed",
        ),
        (
            "analysis/api-beta-route-ownership.md",
            lambda data: replace_once(
                data,
                b"<!-- BETA_IDENTIFIER_CATALOG_START -->",
                b"<!-- BETA_IDENTIFIER_CATALOG_BROKEN -->",
            ),
            "API/error reference generation check failed",
        ),
        (
            "analysis/error-diagnostic-atlas.md",
            lambda data: replace_once(
                data,
                "五层状态归属".encode(),
                "错误状态归属".encode(),
            ),
            "API/error reference generation check failed",
        ),
        (
            "analysis/error-diagnostic-atlas.md",
            lambda data: replace_once(
                data,
                "constructor callsites 共 **4,831**".encode(),
                "constructor callsites 共 **4,830**".encode(),
            ),
            "API/error reference generation check failed",
        ),
        (
            "analysis/error-diagnostic-atlas.md",
            lambda data: replace_once(
                data,
                b"<!-- ERROR_DIAGNOSTIC_METRICS_START -->",
                b"<!-- ERROR_DIAGNOSTIC_METRICS_BROKEN -->",
            ),
            "API/error reference generation check failed",
        ),
        (
            "analysis/visuals/artifact-watch-autoreact-lifecycle.dot",
            remove_labeled_dot_edges,
            "deep topic visual is too shallow: artifact-watch",
        ),
        (
            "analysis/visuals/insights-history-analysis-lifecycle.svg",
            lambda data: replace_once(data, b" viewBox=", b" data-viewBox="),
            "deep topic rendered visual lacks SVG viewport: insights-pipeline",
        ),
        (
            "analysis/visuals/cli-startup-assets-lifecycle.dot",
            lambda data: replace_once(
                data,
                b"digraph cli_startup_assets_lifecycle {",
                b"digraph cli_startup_assets_lifecycle",
            ),
            "deep topic visual DOT structure is invalid: cli-startup-assets",
        ),
        (
            "analysis/visuals/complex-slash-commands-lifecycle.svg",
            lambda data: replace_once(data, b" viewBox=", b" data-viewBox="),
            "deep topic rendered visual lacks SVG viewport: complex-slash-commands",
        ),
        (
            "analysis/visuals/telemetry-event-catalog-lifecycle.dot",
            remove_labeled_dot_edges,
            "deep topic visual is too shallow: telemetry-event-catalog",
        ),
        (
            "analysis/visuals/api-beta-route-ownership-lifecycle.svg",
            lambda data: replace_once(data, b" viewBox=", b" data-viewBox="),
            "deep topic rendered visual lacks SVG viewport: api-beta-route-ownership",
        ),
        (
            "analysis/visuals/error-diagnostic-atlas-lifecycle.dot",
            remove_labeled_dot_edges,
            "deep topic visual is too shallow: error-diagnostic-atlas",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                2,
                b"api-beta-route-ownership.md",
                b"api-beta-route-ownership-missing.md",
            ),
            "completeness capability 2 does not bind deep topic api-beta-route-ownership",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                11,
                b"error-diagnostic-atlas.md",
                b"error-diagnostic-atlas-missing.md",
            ),
            "completeness capability 11 does not bind deep topic error-diagnostic-atlas",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                12,
                b"telemetry-event-catalog.md",
                b"telemetry-event-catalog-missing.md",
            ),
            "completeness capability 12 does not bind deep topic telemetry-event-catalog",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                54,
                b"artifact-watch-comment-autoreact.md",
                b"artifact-watch-comment-autoreact-missing.md",
            ),
            "completeness capability 54 does not bind deep topic artifact-watch",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                55,
                b"insights-history-analysis-pipeline.md",
                b"insights-history-analysis-pipeline-missing.md",
            ),
            "completeness capability 55 does not bind deep topic insights-pipeline",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                56,
                b"cli-startup-files-plugins-deeplinks.md",
                b"cli-startup-files-plugins-deeplinks-missing.md",
            ),
            "completeness capability 56 does not bind deep topic cli-startup-assets",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                57,
                b"complex-slash-command-lifecycles.md",
                b"complex-slash-command-lifecycles-missing.md",
            ),
            "completeness capability 57 does not bind deep topic complex-slash-commands",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: remove_capability_row(data, 51),
            "completeness capability coverage mismatch: expected=58, actual=57",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data, 27, "尚缺".encode(), "已经".encode()
            ),
            "completeness capability 27 is Documented but does not name the exact missing in-scope fact",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                27,
                "尚缺目标二进制对受控 IDE socket 的正向 auth/context/selection/diagnostic 往返 Probe".encode(),
                "尚缺一些细节".encode(),
            ),
            "completeness capability 27 missing-fact contract lacks controlled IDE socket",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_capability_state(
                data, 33, b"| Deep |", b"| Documented |"
            ),
            "deep topic contract install-update-doctor is not Deep in completeness capability 33: Documented",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_capability_state(
                data, 58, b"| Boundary |", b"| Deep |"
            ),
            "last completeness capability 58 must remain Boundary: Deep",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(data, "auth-account", 2),
            "mechanism topic 'auth-account' has 2 claims; minimum is 3",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(
                data, "install-update-doctor", 13
            ),
            "mechanism topic 'install-update-doctor' has 13 claims; minimum is 14",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: remove_mechanism_claim(
                data, "native-update.download-integrity"
            ),
            "mechanism topic 'install-update-doctor' is missing required claim: native-update.download-integrity",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: remove_mechanism_claim(
                data, "boundary.native-update-manifest-authenticity"
            ),
            "mechanism topic 'install-update-doctor' is missing required claim: boundary.native-update-manifest-authenticity",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(
                data, "tool-registration-hosts", 5
            ),
            "mechanism topic 'tool-registration-hosts' has 5 claims; minimum is 6",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(data, "brief-output", 8),
            "mechanism topic 'brief-output' has 8 claims; minimum is 9",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(
                data, "plan-mode-approval", 5
            ),
            "mechanism topic 'plan-mode-approval' has 5 claims; minimum is 6",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(data, "structured-output", 5),
            "mechanism topic 'structured-output' has 5 claims; minimum is 6",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(
                data, "claude-design-projects", 7
            ),
            "mechanism topic 'claude-design-projects' has 7 claims; minimum is 8",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(data, "repl-runtime", 5),
            "mechanism topic 'repl-runtime' has 5 claims; minimum is 6",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(data, "end-conversation", 5),
            "mechanism topic 'end-conversation' has 5 claims; minimum is 6",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(data, "remote-ops", 5),
            "mechanism topic 'remote-ops' has 5 claims; minimum is 6",
        ),
        (
            "analysis/mechanism-evidence.jsonl",
            lambda data: truncate_mechanism_topic_claims(
                data, "connector-catalog-mcp", 5
            ),
            "mechanism topic 'connector-catalog-mcp' has 5 claims; minimum is 6",
        ),
        (
            "analysis/install-update-doctor-lifecycle.md",
            lambda data: replace_in_h2_section(
                data,
                "完整生命周期",
                "manifest.json",
                "release-index.json",
                replace_all=True,
            ),
            "deep topic contract install-update-doctor lifecycle is missing platform manifest",
        ),
        (
            "analysis/install-update-doctor-lifecycle.md",
            lambda data: replace_in_h2_section(
                data,
                "失败、部分成功与恢复",
                "activationFailed",
                "activationFailure",
                replace_all=True,
            ),
            "deep topic contract install-update-doctor failure/recovery is missing partial activation",
        ),
        (
            "analysis/install-update-doctor-lifecycle.md",
            lambda data: replace_in_h2_section(
                data,
                "证据与边界",
                "reverse/javascript/cli.readable.js",
                "reverse/javascript/cli.missing.js",
                replace_all=True,
            ),
            "deep topic contract install-update-doctor has 0 source references; minimum is 12",
        ),
        (
            "analysis/install-update-doctor-lifecycle.md",
            lambda data: replace_once(
                data,
                "独立 GPG/Ed25519 签名".encode(),
                "额外完整性字段".encode(),
            ),
            "deep topic contract install-update-doctor gates are missing manifest authenticity boundary",
        ),
        (
            "analysis/visuals/release-lifecycle.dot",
            lambda data: replace_once(
                data,
                b"activationRefused / Failed",
                b"activation outcome",
            ),
            "deep topic visual install-update-doctor is missing state anchor: activationRefused / Failed",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_once(
                data,
                "## 先分清四个责任对象".encode(),
                "## 四个相关对象".encode(),
            ),
            "deep topic contract plan-mode is missing state ownership section",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_once(
                data,
                "## Phase 6".encode(),
                "## Missing Phase 6".encode(),
            ),
            "deep topic contract plan-mode lifecycle phases are not contiguous",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_in_h2_section(
                data,
                "Plan Mode 不是单层提示词",
                "Plan Mode",
                "Planning Mode",
            ),
            "deep topic contract plan-mode is missing gates and thresholds section",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: data.replace(
                b"useAutoModeDuringPlan", b"autoDuringPlanningMissing"
            ),
            "deep topic contract plan-mode gates are missing useAutoModeDuringPlan",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_once(
                data,
                "## 完整失败矩阵".encode(),
                "## 异常列表".encode(),
            ),
            "deep topic contract plan-mode is missing failure and recovery section",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_in_h2_section(
                data,
                "Token、延迟、成本、隐私与副作用",
                "| Privacy |",
                "| Data scope |",
            ),
            "deep topic contract plan-mode user impact is missing privacy",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_in_h2_section(
                data,
                "证据等级与明确边界",
                "../reverse/javascript/cli.readable.js#L",
                "../reverse/javascript/cli.missing.js#L",
                replace_all=True,
            ),
            "deep topic contract plan-mode has 0 source references; minimum is 5",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            lambda data: replace_once(
                data,
                "### Boundary".encode(),
                "### 未验证范围".encode(),
            ),
            "deep topic contract plan-mode is missing boundary section",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            lambda data: replace_once(
                data,
                "**读者问题：**".encode(),
                "**核心问题：**".encode(),
            ),
            "deep topic contract structured-output is missing reader question",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            lambda data: remove_numbered_lifecycle(data, "完整调用顺序"),
            "deep topic contract structured-output ordered lifecycle has 0 steps",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            lambda data: replace_in_h2_section(
                data,
                "完整调用顺序",
                "StructuredOutput",
                "StructuredResultTool",
                replace_all=True,
            ),
            "deep topic contract structured-output lifecycle is missing StructuredOutput injection",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            lambda data: replace_in_h2_section(
                data,
                "Gate、优先级与阈值",
                "additionalProperties",
                "closedPropertiesMissing",
                replace_all=True,
            ),
            "deep topic contract structured-output gates are missing additionalProperties",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            lambda data: replace_once(
                data,
                "## 失败与恢复".encode(),
                "## 错误列表".encode(),
            ),
            "deep topic contract structured-output is missing failure and recovery section",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            lambda data: replace_in_h2_section(
                data,
                "证据索引",
                "reverse/javascript/cli.readable.js:",
                "reverse/javascript/cli.missing.js:",
                replace_all=True,
            ),
            "deep topic contract structured-output has 0 source references; minimum is 5",
        ),
        (
            "ARTICLES.md",
            lambda data: data.replace(
                b"analysis/plan-mode-and-human-approval.md",
                b"analysis/plan-mode-and-human-approval-missing.md",
            ),
            "deep topic contract plan-mode is not linked from ARTICLES.md",
        ),
        (
            "ARTICLES.md",
            lambda data: data.replace(
                b"analysis/structured-output-and-schema-contract.md",
                b"analysis/structured-output-and-schema-contract-missing.md",
            ),
            "deep topic contract structured-output is not linked from ARTICLES.md",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_once(
                data,
                b"plan-mode-and-human-approval.md",
                b"plan-mode-and-human-approval-missing.md",
            ),
            "completeness capability 52 does not bind deep topic plan-mode",
        ),
        (
            "skill/claude-code-version-diff/SKILL.md",
            lambda data: data.replace(
                b"analysis/structured-output-and-schema-contract.md",
                b"analysis/structured-output-and-schema-contract-missing.md",
            ),
            "deep topic contract structured-output is not bound in Skill",
        ),
        (
            "analysis/visuals/plan-mode-lifecycle.dot",
            remove_labeled_dot_edges,
            "deep topic visual is too shallow: plan-mode",
        ),
        (
            "analysis/visuals/plan-mode-lifecycle.dot",
            lambda data: replace_once(
                data,
                b"digraph PlanModeLifecycle {",
                b"digraph PlanModeLifecycle",
            ),
            "deep topic visual DOT structure is invalid: plan-mode",
        ),
        (
            "analysis/visuals/structured-output-lifecycle.svg",
            lambda data: replace_once(data, b" viewBox=", b" data-viewBox="),
            "deep topic rendered visual lacks SVG viewport: structured-output",
        ),
        (
            "analysis/claude-design-and-projects.md",
            lambda data: replace_in_h2_section(
                data,
                "完整调用顺序",
                "catalog hash",
                "catalog fingerprint missing",
                replace_all=True,
            ),
            "deep topic contract claude-design-projects lifecycle is missing catalog hash",
        ),
        (
            "analysis/visuals/claude-design-projects-lifecycle.dot",
            remove_labeled_dot_edges,
            "deep topic visual is too shallow: claude-design-projects",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                23,
                b"claude-design-and-projects.md",
                b"claude-design-and-projects-missing.md",
            ),
            "completeness capability 23 does not bind deep topic claude-design-projects",
        ),
        (
            "analysis/repl-programmatic-tool-runtime.md",
            lambda data: replace_in_h2_section(
                data,
                "完整执行顺序",
                "watchdog",
                "execution guard missing",
                replace_all=True,
            ),
            "deep topic contract repl-runtime lifecycle is missing watchdog",
        ),
        (
            "analysis/end-conversation-risk-control.md",
            lambda data: replace_in_h2_section(
                data,
                "Gate、优先级与精确阈值",
                "tengu_umber_kestrel",
                "feature_config_missing",
                replace_all=True,
            ),
            "deep topic contract end-conversation gates are missing feature config",
        ),
        (
            "analysis/connectors-catalog-and-mcp-operators.md",
            lambda data: replace_in_h2_section(
                data,
                "证据索引",
                "reverse/javascript/cli.readable.js:",
                "reverse/javascript/cli.missing.js:",
                replace_all=True,
            ),
            "deep topic contract connector-catalog-mcp has 0 source references; minimum is 6",
        ),
        (
            "analysis/visuals/remote-routines-runner-notifications-lifecycle.dot",
            remove_labeled_dot_edges,
            "deep topic visual is too shallow: remote-ops",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                7,
                b"repl-programmatic-tool-runtime.md",
                b"repl-programmatic-tool-runtime-missing.md",
            ),
            "completeness capability 7 does not bind deep topic repl-runtime",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                35,
                b"end-conversation-risk-control.md",
                b"end-conversation-risk-control-missing.md",
            ),
            "completeness capability 35 does not bind deep topic end-conversation",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                29,
                b"remote-routines-runner-and-notifications.md",
                b"remote-routines-runner-and-notifications-missing.md",
            ),
            "completeness capability 29 does not bind deep topic remote-ops",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                31,
                b"remote-routines-runner-and-notifications.md",
                b"remote-routines-runner-and-notifications-missing.md",
            ),
            "completeness capability 31 does not bind deep topic remote-ops",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_in_capability_row(
                data,
                9,
                b"connectors-catalog-and-mcp-operators.md",
                b"connectors-catalog-and-mcp-operators-missing.md",
            ),
            "completeness capability 9 does not bind deep topic connector-catalog-mcp",
        ),
    ]

    full_regeneration_cases = {
        "analysis/source-inventory/summary.json",
        "analysis/source-inventory/environment-schema.jsonl",
        "analysis/source-inventory/claude-storage-namespaces.txt",
    }
    for case_number, (relative, mutate, expected) in enumerate(cases, 1):
        if case_number < args.start_case:
            continue
        if args.end_case is not None and case_number > args.end_case:
            break
        print(
            f"negative case {case_number}: {relative}",
            flush=True,
        )
        expect_rejection(
            repo,
            validator,
            relative,
            mutate,
            expected,
            fast=relative not in full_regeneration_cases,
        )
        print(f"negative case {case_number}: PASS", flush=True)

    missing_cases = [
        (
            "skill/claude-code-version-diff/scripts/probe_plugin_evaluation.mjs",
            "Plugin Evaluation probe: missing probe script",
        ),
        (
            "analysis/runtime-probes/plugin-evaluation.json",
            "Plugin Evaluation probe: missing report",
        ),
        (
            "skill/claude-code-version-diff/scripts/test_plugin_evaluation_validator.py",
            "missing Plugin Evaluation validator forgery test",
        ),
        (
            "skill/claude-code-version-diff/scripts/probe_network_proxy_tls.mjs",
            "network proxy/TLS probe: missing probe script",
        ),
        (
            "analysis/runtime-probes/network-proxy-tls.json",
            "network proxy/TLS probe: missing report",
        ),
        (
            "skill/claude-code-version-diff/scripts/test_network_proxy_tls_validator.py",
            "missing network proxy/TLS validator forgery test",
        ),
        (
            "skill/claude-code-version-diff/scripts/probe_otlp_tls.mjs",
            "OTLP TLS probe: missing probe script",
        ),
        (
            "analysis/runtime-probes/otlp-tls.json",
            "OTLP TLS probe: missing report",
        ),
        (
            "skill/claude-code-version-diff/scripts/test_otlp_tls_validator.py",
            "missing OTLP TLS validator forgery test",
        ),
        (
            "analysis/runtime-probes/native-reconstruction-x86.json",
            "missing x86_64 native reconstruction behavior report",
        ),
        (
            "analysis/runtime-probes/project-data-lifecycle.json",
            "probe report is missing",
        ),
        (
            "skill/claude-code-version-diff/scripts/test_project_data_lifecycle_validator.py",
            "missing project data lifecycle validator forgery test",
        ),
        (
            "skill/claude-code-version-diff/scripts/test_dynamic_environment_resolver.mjs",
            "missing dynamic environment resolver fixture test",
        ),
        (
            "skill/claude-code-version-diff/scripts/test_telemetry_caller_owner_projection.py",
            "missing telemetry caller-owner projection test",
        ),
        (
            "reconstructed/scripts/test_x86_provenance.mjs",
            "missing native x86 provenance forgery test",
        ),
        (
            "analysis/feature-flags-remote-config.md",
            "missing human analysis document: analysis/feature-flags-remote-config.md",
        ),
        (
            "analysis/visuals/advisor-dual-model.svg",
            "reader-first rendered visual is missing: analysis/visuals/advisor-dual-model.svg",
        ),
        (
            "analysis/tool-registration-and-host-surfaces.md",
            "missing human analysis document: analysis/tool-registration-and-host-surfaces.md",
        ),
        (
            "analysis/brief-mode-and-user-visible-output.md",
            "missing human analysis document: analysis/brief-mode-and-user-visible-output.md",
        ),
        (
            "analysis/visuals/tool-registration-host-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/tool-registration-host-lifecycle.dot",
        ),
        (
            "analysis/visuals/brief-user-output-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/brief-user-output-lifecycle.svg",
        ),
        (
            "analysis/plan-mode-and-human-approval.md",
            "missing human analysis document: analysis/plan-mode-and-human-approval.md",
        ),
        (
            "analysis/structured-output-and-schema-contract.md",
            "missing human analysis document: analysis/structured-output-and-schema-contract.md",
        ),
        (
            "analysis/visuals/plan-mode-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/plan-mode-lifecycle.dot",
        ),
        (
            "analysis/visuals/structured-output-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/structured-output-lifecycle.svg",
        ),
        (
            "analysis/visuals/artifact-watch-autoreact-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/artifact-watch-autoreact-lifecycle.svg",
        ),
        (
            "analysis/visuals/insights-history-analysis-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/insights-history-analysis-lifecycle.dot",
        ),
        (
            "analysis/visuals/cli-startup-assets-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/cli-startup-assets-lifecycle.svg",
        ),
        (
            "analysis/visuals/complex-slash-commands-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/complex-slash-commands-lifecycle.dot",
        ),
        (
            "analysis/visuals/telemetry-event-catalog-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/telemetry-event-catalog-lifecycle.svg",
        ),
        (
            "analysis/visuals/api-beta-route-ownership-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/api-beta-route-ownership-lifecycle.dot",
        ),
        (
            "analysis/visuals/error-diagnostic-atlas-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/error-diagnostic-atlas-lifecycle.svg",
        ),
        (
            "analysis/claude-design-and-projects.md",
            "missing human analysis document: analysis/claude-design-and-projects.md",
        ),
        (
            "analysis/visuals/claude-design-projects-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/claude-design-projects-lifecycle.svg",
        ),
        (
            "analysis/repl-programmatic-tool-runtime.md",
            "missing human analysis document: analysis/repl-programmatic-tool-runtime.md",
        ),
        (
            "analysis/end-conversation-risk-control.md",
            "missing human analysis document: analysis/end-conversation-risk-control.md",
        ),
        (
            "analysis/remote-routines-runner-and-notifications.md",
            "missing human analysis document: analysis/remote-routines-runner-and-notifications.md",
        ),
        (
            "analysis/connectors-catalog-and-mcp-operators.md",
            "missing human analysis document: analysis/connectors-catalog-and-mcp-operators.md",
        ),
        (
            "analysis/visuals/repl-programmatic-tool-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/repl-programmatic-tool-lifecycle.dot",
        ),
        (
            "analysis/visuals/end-conversation-risk-control.svg",
            "reader-first rendered visual is missing: analysis/visuals/end-conversation-risk-control.svg",
        ),
        (
            "analysis/visuals/remote-routines-runner-notifications-lifecycle.dot",
            "reader-first visual source is missing: analysis/visuals/remote-routines-runner-notifications-lifecycle.dot",
        ),
        (
            "analysis/visuals/connectors-catalog-mcp-operators-lifecycle.svg",
            "reader-first rendered visual is missing: analysis/visuals/connectors-catalog-mcp-operators-lifecycle.svg",
        ),
    ]
    total_cases = len(cases) + len(missing_cases)
    if args.start_case > total_cases:
        parser.error(
            f"--start-case exceeds available cases ({total_cases})"
        )
    if args.end_case is not None and args.end_case > total_cases:
        parser.error(f"--end-case exceeds available cases ({total_cases})")
    for case_number, (relative, expected) in enumerate(
        missing_cases,
        len(cases) + 1,
    ):
        if case_number < args.start_case:
            continue
        if args.end_case is not None and case_number > args.end_case:
            break
        print(
            f"negative case {case_number}: missing {relative}",
            flush=True,
        )
        expect_missing_rejection(repo, validator, relative, expected)
        print(f"negative case {case_number}: PASS", flush=True)

    print("validator negative tests: PASS")
    end_case = args.end_case if args.end_case is not None else total_cases
    print(f"cases checked: {end_case - args.start_case + 1}")
    print(f"case range: {args.start_case}-{end_case}")
    print("restoration: PASS")


if __name__ == "__main__":
    main()
