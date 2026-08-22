#!/usr/bin/env python3
"""Prove that the snapshot validator rejects publication regressions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(validator), str(repo)]
    environment = os.environ.copy()
    if fast:
        command.append("--negative-test-fast")
        environment["CLAUDE_VALIDATOR_NEGATIVE_TEST"] = "1"
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
        result = run_validator(repo, validator, fast=fast)
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
        result = run_validator(repo, validator, fast=True)
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
        "--skip-baseline",
        action="store_true",
        help="skip the positive baseline when resuming a previously verified run",
    )
    args = parser.parse_args()
    if args.start_case < 1:
        parser.error("--start-case must be at least 1")
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
            "analysis/completeness-audit.md",
            downgrade_first_capability,
            "completeness capability 1 is not closed: Documented",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: remove_capability_row(data, 51),
            "completeness capability coverage mismatch: expected=52, actual=51",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: downgrade_capability(data, 51),
            "completeness capability 51 is not closed: Documented",
        ),
        (
            "analysis/completeness-audit.md",
            lambda data: replace_capability_state(
                data, 52, b"| Boundary |", b"| Deep |"
            ),
            "completeness capability 52 must remain Boundary: Deep",
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
    ]

    full_regeneration_cases = {
        "analysis/source-inventory/summary.json",
        "analysis/source-inventory/environment-schema.jsonl",
        "analysis/source-inventory/claude-storage-namespaces.txt",
    }
    for case_number, (relative, mutate, expected) in enumerate(cases, 1):
        if case_number < args.start_case:
            continue
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
    ]
    total_cases = len(cases) + len(missing_cases)
    if args.start_case > total_cases:
        parser.error(
            f"--start-case exceeds available cases ({total_cases})"
        )
    for case_number, (relative, expected) in enumerate(
        missing_cases,
        len(cases) + 1,
    ):
        if case_number < args.start_case:
            continue
        print(
            f"negative case {case_number}: missing {relative}",
            flush=True,
        )
        expect_missing_rejection(repo, validator, relative, expected)
        print(f"negative case {case_number}: PASS", flush=True)

    print("validator negative tests: PASS")
    print(f"cases checked: {total_cases - args.start_case + 1}")
    print(f"case range: {args.start_case}-{total_cases}")
    print("restoration: PASS")


if __name__ == "__main__":
    main()
