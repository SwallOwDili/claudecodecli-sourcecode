#!/usr/bin/env python3
"""Prove that forged project lifecycle probe evidence is rejected."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable


Mutation = Callable[[dict[str, Any]], None]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_validator(
    repo: Path, validator: Path, report: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(validator), str(repo), "--report", str(report)],
        cwd=repo,
        text=True,
        capture_output=True,
    )


def set_path(*path: str, value: Any) -> Mutation:
    def mutate(document: dict[str, Any]) -> None:
        current: Any = document
        for part in path[:-1]:
            current = current[part]
        current[path[-1]] = value

    return mutate


def delete_path(*path: str) -> Mutation:
    def mutate(document: dict[str, Any]) -> None:
        current: Any = document
        for part in path[:-1]:
            current = current[part]
        del current[path[-1]]

    return mutate


def append_owned_after(document: dict[str, Any]) -> None:
    document["beforeAfter"]["purgePositive"]["ownedAfter"].append(
        copy.deepcopy(document["beforeAfter"]["purgePositive"]["ownedBefore"][0])
    )


def corrupt_dry_after_hash(document: dict[str, Any]) -> None:
    document["beforeAfter"]["purgeDryRun"]["domainAfter"][1]["sha256"] = "0" * 64


def corrupt_excluded_after_hash(document: dict[str, Any]) -> None:
    document["beforeAfter"]["purgePositive"]["excludedFixturesAfter"][0]["sha256"] = (
        "0" * 64
    )


def add_check(document: dict[str, Any]) -> None:
    document["checks"]["forgedCheck"] = True


def scalar_leaves(
    value: Any, path: tuple[Any, ...] = ()
) -> list[tuple[tuple[Any, ...], Any]]:
    if isinstance(value, dict):
        return [
            leaf
            for key, child in value.items()
            for leaf in scalar_leaves(child, path + (key,))
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, child in enumerate(value)
            for leaf in scalar_leaves(child, path + (index,))
        ]
    return [(path, value)]


def forged_scalar(value: Any) -> Any:
    if value is True:
        return False
    if value is False:
        return True
    if value is None:
        return "FORGED"
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "__FORGED"
    return "FORGED"


def audit_every_scalar(
    validator: Path,
    source_document: dict[str, Any],
    version: str,
    binary_sha256: str,
) -> int:
    module_spec = importlib.util.spec_from_file_location(
        "project_data_lifecycle_validator_under_test", validator
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("could not load project lifecycle validator module")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    accepted: list[str] = []
    leaves = scalar_leaves(source_document)
    for path, value in leaves:
        document = copy.deepcopy(source_document)
        current: Any = document
        for part in path[:-1]:
            current = current[part]
        current[path[-1]] = forged_scalar(value)
        failures = module.validate_project_data_lifecycle_document(
            document, version, binary_sha256
        )
        if not failures:
            accepted.append(".".join(str(part) for part in path))
    if accepted:
        raise RuntimeError(
            "validator accepted scalar forgeries:\n" + "\n".join(accepted)
        )
    return len(leaves)


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    validator = (
        repo
        / "skill/claude-code-version-diff/scripts/validate_project_data_lifecycle.py"
    )
    source = repo / "analysis/runtime-probes/project-data-lifecycle.json"
    original_hash = sha256(source)
    baseline = run_validator(repo, validator, source)
    if baseline.returncode != 0:
        raise RuntimeError(
            f"project lifecycle validator baseline failed:\n{baseline.stdout}{baseline.stderr}"
        )

    cases: list[tuple[str, Mutation, str]] = [
        (
            "schema downgrade",
            set_path("schemaVersion", value=1),
            "probe schemaVersion must equal 2",
        ),
        (
            "target version forgery",
            set_path("target", "version", value="2.1.233"),
            "probe target version differs from VERSION",
        ),
        (
            "target binary forgery",
            set_path("target", "binarySha256", value="0" * 64),
            "probe target binary hash differs from analysis/version.json",
        ),
        (
            "failed required check",
            set_path("checks", "zipMismatchKeepsTranscript", value=False),
            "required probe check failed: zipMismatchKeepsTranscript",
        ),
        (
            "missing required check",
            delete_path("checks", "jsonImportTranscriptMode0600"),
            "probe check set/order is not the fixed 69-check contract",
        ),
        (
            "unexpected check",
            add_check,
            "probe has unexpected checks: forgedCheck",
        ),
        (
            "execution argv forgery",
            set_path(
                "executionContracts",
                "purgePositive",
                "argv",
                value=["project", "purge", "--all", "--dry-run"],
            ),
            "execution contract mismatch: purgePositive",
        ),
        (
            "execution cwd forgery",
            set_path("executionContracts", "jsonImport", "cwd", value="$JSON_TARGET"),
            "execution contract mismatch: jsonImport",
        ),
        (
            "execution environment omission",
            delete_path(
                "executionContracts", "zipManifestMismatch", "environment", "HOME"
            ),
            "execution contract mismatch: zipManifestMismatch",
        ),
        (
            "command rendering forgery",
            set_path(
                "commands",
                "jsonDryRun",
                value="env -i $CLAUDE_TARGET import-conversations",
            ),
            "full environment command rendering mismatch: jsonDryRun",
        ),
        (
            "literal output suffix forgery",
            set_path(
                "literalOutput",
                "zipManifestMismatch",
                "stderr",
                value="manifest mismatch:\n  messages: manifest=3 imported=2\n  docs: manifest=2 imported=1\nImport completed with mismatches (IMPORT_MANIFEST_MISMATCH)\nFORGED",
            ),
            "zipManifestMismatch stderr literal output hash mismatch",
        ),
        (
            "dry-run after-state forgery",
            corrupt_dry_after_hash,
            "purge dry-run changed its owned data domain",
        ),
        (
            "positive purge retained target",
            append_owned_after,
            "positive purge left owned rows behind",
        ),
        (
            "positive purge excluded-byte forgery",
            corrupt_excluded_after_hash,
            "positive purge did not preserve excluded fixture metadata and bytes",
        ),
        (
            "JSON transcript mode forgery",
            set_path("observed", "jsonImportTranscript", "mode", value="644"),
            "jsonImport transcript mode is not 0600",
        ),
        (
            "JSON canonical hash forgery",
            set_path(
                "observed",
                "jsonImportTranscript",
                "canonicalContentSha256",
                value="0" * 64,
            ),
            "jsonImport canonical transcript hash mismatch",
        ),
        (
            "manifest mismatch exit forgery",
            set_path("exitStatus", "zipManifestMismatch", value=0),
            "manifest mismatch exit status is not 1",
        ),
        (
            "manifest mismatch after-state deletion",
            set_path("beforeAfter", "zipManifestMismatch", "after", "target", value=[]),
            "zipManifestMismatch target artifact before/after evidence mismatch",
        ),
        (
            "manifest mismatch retained-write forgery",
            set_path("observed", "zipMismatchWritesSurvivedExitOne", value=False),
            "manifest mismatch exit 1 did not retain writes",
        ),
    ]

    source_document = json.loads(source.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="project-lifecycle-validator-") as temp:
        report_path = Path(temp) / "report.json"
        for index, (name, mutate, expected) in enumerate(cases, 1):
            document = copy.deepcopy(source_document)
            mutate(document)
            report_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            result = run_validator(repo, validator, report_path)
            output = result.stdout + result.stderr
            if result.returncode == 0:
                raise RuntimeError(f"negative case {index} was accepted: {name}")
            if expected not in output:
                raise RuntimeError(
                    f"negative case {index} rejected for the wrong reason: {name}\n{output}"
                )
            print(f"negative case {index:02d}: PASS - {name}")

    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    binary_sha256 = json.loads(
        (repo / "analysis/version.json").read_text(encoding="utf-8")
    )["binary"]["sha256"]
    scalar_count = audit_every_scalar(
        validator, source_document, version, binary_sha256
    )
    print(
        "project data lifecycle scalar mutation audit: "
        f"PASS ({scalar_count}/{scalar_count} rejected)"
    )

    if sha256(source) != original_hash:
        raise RuntimeError(
            "project lifecycle source report changed during negative tests"
        )
    print(
        f"project data lifecycle negative validation: PASS ({len(cases)} forgeries rejected)"
    )
    print(f"source report sha256 preserved: {original_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
