#!/usr/bin/env python3
"""Validate the exact-binary Plugin Evaluation smoke report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_RELATIVE = "analysis/runtime-probes/plugin-evaluation.json"
EXPECTED_VERSION = "2.1.235"
EXPECTED_BINARY_SHA256 = (
    "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748"
)
EXPECTED_CHECKS = {
    "exactVersion",
    "exactBinarySha256",
    "commandExitZero",
    "jsonResultWritten",
    "htmlReportWritten",
    "htmlContainsCaseName",
    "htmlContainsResultMarker",
    "bothArmsPresent",
    "scoresAllPerfect",
    "deltaZero",
    "resultNotPartial",
    "noPluginLoadProblem",
    "twoAgentRequestsObserved",
    "withRequestHasPluginHookContext",
    "withoutRequestOmitsPluginHookContext",
    "modelPinned",
    "schemaVersionOne",
}


def add_failure(failures: list[str], message: str) -> None:
    failures.append(f"Plugin Evaluation probe: {message}")


def exact_object(
    value: Any, expected_keys: set[str], label: str, failures: list[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        add_failure(failures, f"{label} is not an object")
        return {}
    if set(value) != expected_keys:
        add_failure(failures, f"{label} keys differ")
    return value


def validate_plugin_evaluation_report(
    repo: Path,
    version: str,
    metadata: dict[str, Any],
    failures: list[str],
    report_path: Path | None = None,
) -> int:
    probe_script = (
        repo / "skill/claude-code-version-diff/scripts/probe_plugin_evaluation.mjs"
    )
    if not probe_script.is_file():
        add_failure(failures, "missing probe script")
    elif probe_script.stat().st_mode & 0o111 == 0:
        add_failure(failures, "probe script is not executable")

    path = report_path or repo / REPORT_RELATIVE
    if not path.is_file():
        add_failure(failures, f"missing report: {path}")
        return 0
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        add_failure(failures, f"invalid JSON: {error}")
        return 0
    if not isinstance(report, dict):
        add_failure(failures, "root is not an object")
        return 0
    if set(report) != {
        "schemaVersion",
        "capturedAt",
        "target",
        "environment",
        "command",
        "input",
        "literalOutput",
        "exitStatus",
        "observed",
        "checks",
        "boundaries",
        "pass",
    }:
        add_failure(failures, "root keys differ")
    if report.get("schemaVersion") != 1:
        add_failure(failures, "schemaVersion is not 1")
    if not isinstance(report.get("capturedAt"), str) or "T" not in report["capturedAt"]:
        add_failure(failures, "capturedAt is not ISO-like")
    if report.get("pass") is not True:
        add_failure(failures, "pass is not true")

    target = exact_object(report.get("target"), {"version", "binarySha256"}, "target", failures)
    metadata_sha = metadata.get("binary", {}).get("sha256")
    if version != EXPECTED_VERSION or target.get("version") != version:
        add_failure(failures, "target version mismatch")
    if metadata_sha != EXPECTED_BINARY_SHA256 or target.get("binarySha256") != metadata_sha:
        add_failure(failures, "target binary SHA mismatch")

    environment = exact_object(
        report.get("environment"),
        {"platform", "arch", "nodeVersion"},
        "environment",
        failures,
    )
    for field in ("platform", "arch", "nodeVersion"):
        if not isinstance(environment.get(field), str) or not environment[field]:
            add_failure(failures, f"environment.{field} is empty")

    command = report.get("command")
    if not isinstance(command, str) or not all(
        term in command
        for term in (
            "plugin eval $PLUGIN",
            "--runs 1",
            "--ablation with-without",
            "--threshold 1",
            "--no-publish",
            "--no-scaffold",
        )
    ):
        add_failure(failures, "command contract mismatch")

    input_value = exact_object(
        report.get("input"),
        {"pluginManifest", "case", "promptMarker", "resultMarker", "hookMarker"},
        "input",
        failures,
    )
    if input_value.get("pluginManifest") != {
        "name": "eval-probe-plugin",
        "version": "1.0.0",
    }:
        add_failure(failures, "plugin manifest input mismatch")
    if input_value.get("promptMarker") != "PLUGIN_EVAL_PROMPT_MARKER":
        add_failure(failures, "prompt marker mismatch")
    if input_value.get("resultMarker") != "PLUGIN_EVAL_RESULT_OK":
        add_failure(failures, "result marker mismatch")
    if input_value.get("hookMarker") != "PLUGIN_EVAL_WITH_ARM_HOOK_MARKER":
        add_failure(failures, "hook marker mismatch")
    case = exact_object(
        input_value.get("case"),
        {"schemaVersion", "name", "runs", "maxTurns", "timeoutSeconds", "grader"},
        "input.case",
        failures,
    )
    if case.get("schemaVersion") != "1.0" or case.get("name") != "exact-binary-smoke":
        add_failure(failures, "case identity mismatch")
    if (case.get("runs"), case.get("maxTurns"), case.get("timeoutSeconds")) != (1, 1, 30):
        add_failure(failures, "case execution limits mismatch")
    if case.get("grader") != {
        "type": "regex",
        "target": "last_message",
        "pattern": "PLUGIN_EVAL_RESULT_OK",
        "weight": 1,
    }:
        add_failure(failures, "case grader mismatch")

    literal = exact_object(
        report.get("literalOutput"),
        {"exitStatus", "signal", "stdout", "stderr"},
        "literalOutput",
        failures,
    )
    if report.get("exitStatus") != 0 or literal != {
        "exitStatus": 0,
        "signal": None,
        "stdout": "Wrote $RESULT_JSON",
        "stderr": "Report: $HTML_REPORT",
    }:
        add_failure(failures, "literal process result mismatch")

    observed = exact_object(
        report.get("observed"),
        {
            "requestCount",
            "arms",
            "withScores",
            "withoutScores",
            "caseScore",
            "scoreWithout",
            "delta",
            "partial",
            "schemaVersion",
            "withRequestHasPluginHookContext",
            "withoutRequestHasPluginHookContext",
            "pluginProblemCount",
            "jsonNonempty",
            "htmlNonempty",
            "resultFileMode",
            "reportFileMode",
        },
        "observed",
        failures,
    )
    expected_observed = {
        "requestCount": 2,
        "arms": ["with", "without"],
        "withScores": [1],
        "withoutScores": [1],
        "caseScore": 1,
        "scoreWithout": 1,
        "delta": 0,
        "partial": False,
        "schemaVersion": 1,
        "withRequestHasPluginHookContext": True,
        "withoutRequestHasPluginHookContext": False,
        "pluginProblemCount": 0,
        "jsonNonempty": True,
        "htmlNonempty": True,
        "resultFileMode": 0o644,
        "reportFileMode": 0o644,
    }
    if observed != expected_observed:
        add_failure(failures, "observed ablation/result contract mismatch")

    checks = exact_object(report.get("checks"), EXPECTED_CHECKS, "checks", failures)
    for name in EXPECTED_CHECKS:
        if checks.get(name) is not True:
            add_failure(failures, f"required check failed: {name}")

    boundaries = report.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != 4:
        add_failure(failures, "boundaries must contain exactly four statements")
    else:
        text = "\n".join(str(item) for item in boundaries)
        for term in (
            "does not measure model or plugin quality",
            "free regex grader",
            "not claude.ai report publication",
            "not OS or network isolation",
        ):
            if term not in text:
                add_failure(failures, f"boundary is missing {term!r}")

    serialized = json.dumps(report)
    personal_home_prefix = "/" + "Users/"
    if (
        personal_home_prefix in serialized
        or "/private/var/" in serialized
        or "/tmp/" in serialized
    ):
        add_failure(failures, "report contains a concrete probe path")
    return len(EXPECTED_CHECKS) if not failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--report")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    metadata = json.loads((repo / "analysis/version.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    count = validate_plugin_evaluation_report(
        repo,
        version,
        metadata,
        failures,
        Path(args.report).resolve() if args.report else None,
    )
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print("Plugin Evaluation validation: PASS")
    print(f"checks validated: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
