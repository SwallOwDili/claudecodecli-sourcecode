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


def replace_once(original: bytes, old: bytes, new: bytes) -> bytes:
    if old not in original:
        raise RuntimeError(f"negative-test anchor is missing: {old!r}")
    return original.replace(old, new, 1)


def corrupt_discovered_symbol(original: bytes) -> bytes:
    document = json.loads(original)
    roles = document["discoveredSymbols"]["roles"]
    roles["firstPartyEventAsync"] = roles["firstPartyEventAsync"] + "_WRONG"
    return (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()
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
    ]

    full_regeneration_cases = {
        "analysis/source-inventory/summary.json",
        "analysis/source-inventory/environment-schema.jsonl",
    }
    for relative, mutate, expected in cases:
        expect_rejection(
            repo,
            validator,
            relative,
            mutate,
            expected,
            fast=relative not in full_regeneration_cases,
        )

    print("validator negative tests: PASS")
    print(f"cases checked: {len(cases)}")
    print("restoration: PASS")


if __name__ == "__main__":
    main()
