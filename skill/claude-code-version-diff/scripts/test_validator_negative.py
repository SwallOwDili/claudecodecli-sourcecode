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
    feature_count = str(inventory_summary["counts"]["feature-flag-callsites"]).encode()
    feature_symbol = inventory_summary["discoveredSymbols"]["roles"]["featureValue"].encode()

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
            lambda data: replace_once(
                data,
                b"feature `" + feature_symbol + b"` " + feature_count,
                b"feature `" + feature_symbol + b"` 999",
            ),
            "README inventory fact mismatch for 动态观测调用",
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
            "analysis/native-bridge-runtime.md",
            lambda data: replace_once(
                data,
                b"](visuals/native-bridge-lifecycle.svg)",
                b"](visuals/native-bridge-lifecycle-missing.svg)",
            ),
            "reader-first human document is missing lifecycle image",
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
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_once(
                data,
                b"[`tool-registrations.jsonl`]",
                b"[`tool-registrations-missing.jsonl`]",
            ),
            "product surface inventory coverage mismatch",
        ),
        (
            "analysis/product-surface-evidence-map.md",
            lambda data: replace_once(
                data,
                b"[`api-path-templates.jsonl`](source-inventory/api-path-templates.jsonl) | `request-model-network` | `Derived projection`",
                b"[`api-path-templates.jsonl`](source-inventory/api-path-templates.jsonl) | `request-model-network` | `Product callsites`",
            ),
            "product surface inventory api-path-templates.jsonl must be classified as Derived projection",
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
            "analysis/feature-flag-reference.md",
            lambda data: replace_once(data, b"361/361", b"360/361"),
            "environment/feature reference generation check failed",
        ),
        (
            "analysis/feature-flag-reference.md",
            lambda data: replace_once(
                data,
                "Opaque codename / Inventory only：codename 加 fallback/callsite".encode(),
                "Opaque codename：codename 加 fallback/callsite".encode(),
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
            downgrade_first_capability,
            "completeness capability 1 is not closed: Documented",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: remove_capability_row(data, 51),
            "completeness capability coverage mismatch: expected=58, actual=57",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: downgrade_capability(data, 51),
            "completeness capability 51 is not closed: Documented",
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
            "README.md",
            lambda data: data.replace(
                b"analysis/plan-mode-and-human-approval.md",
                b"analysis/plan-mode-and-human-approval-missing.md",
            ),
            "deep topic contract plan-mode is not linked from README first screen",
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
