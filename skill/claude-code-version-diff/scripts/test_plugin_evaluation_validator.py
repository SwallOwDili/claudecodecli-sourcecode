#!/usr/bin/env python3
"""Prove forged Plugin Evaluation smoke evidence is rejected."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable


Mutation = Callable[[dict[str, Any]], None]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def add_root(document: dict[str, Any]) -> None:
    document["forged"] = True


def add_check(document: dict[str, Any]) -> None:
    document["checks"]["forgedCheck"] = True


def remove_boundary(document: dict[str, Any]) -> None:
    document["boundaries"].pop()


CASES: list[tuple[str, Mutation]] = [
    ("schema downgrade", set_path("schemaVersion", value=0)),
    ("target version forgery", set_path("target", "version", value="2.1.999")),
    ("target binary forgery", set_path("target", "binarySha256", value="0" * 64)),
    ("root extra field", add_root),
    ("pass false", set_path("pass", value=False)),
    ("required check false", set_path("checks", "bothArmsPresent", value=False)),
    ("required check removed", delete_path("checks", "deltaZero")),
    ("unexpected check", add_check),
    ("command ablation forgery", set_path("command", value="plugin eval --ablation none")),
    ("plugin identity forgery", set_path("input", "pluginManifest", "name", value="other")),
    ("case runs forgery", set_path("input", "case", "runs", value=3)),
    ("grader forgery", set_path("input", "case", "grader", "pattern", value="WRONG")),
    ("hook marker forgery", set_path("input", "hookMarker", value="WRONG")),
    ("exit status forgery", set_path("exitStatus", value=1)),
    ("literal path leak", set_path("literalOutput", "stdout", value="Wrote /tmp/result.json")),
    ("without arm removed", set_path("observed", "arms", value=["with"])),
    ("without score changed", set_path("observed", "withoutScores", value=[0])),
    ("delta forged", set_path("observed", "delta", value=1)),
    ("partial hidden", set_path("observed", "partial", value=True)),
    (
        "with hook context hidden",
        set_path("observed", "withRequestHasPluginHookContext", value=False),
    ),
    (
        "without hook context forged",
        set_path("observed", "withoutRequestHasPluginHookContext", value=True),
    ),
    ("plugin problem hidden", set_path("observed", "pluginProblemCount", value=1)),
    ("boundary removed", remove_boundary),
]


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    validator = repo / "skill/claude-code-version-diff/scripts/validate_plugin_evaluation.py"
    source = repo / "analysis/runtime-probes/plugin-evaluation.json"
    original_hash = sha256(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="claude-plugin-eval-negative-") as temporary:
        report = Path(temporary) / "report.json"
        for index, (label, mutate) in enumerate(CASES, 1):
            forged = copy.deepcopy(document)
            mutate(forged)
            report.write_text(json.dumps(forged, indent=2) + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(validator), str(repo), "--report", str(report)],
                cwd=repo,
                text=True,
                capture_output=True,
            )
            if result.returncode == 0:
                raise RuntimeError(f"negative case {index} was accepted: {label}")
            print(f"negative case {index:02d}: PASS - {label}")
    if sha256(source) != original_hash:
        raise RuntimeError("source Plugin Evaluation report hash changed")
    print(f"Plugin Evaluation negative validation: PASS ({len(CASES)} forgeries rejected)")
    print(f"source report sha256 preserved: {original_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
