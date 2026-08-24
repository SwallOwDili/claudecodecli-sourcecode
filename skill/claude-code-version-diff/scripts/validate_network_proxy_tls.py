#!/usr/bin/env python3
"""Validate the exact-binary network proxy, CA, and mTLS probe report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_RELATIVE = "analysis/runtime-probes/network-proxy-tls.json"
EXPECTED_VERSION = "2.1.235"
EXPECTED_BINARY_SHA256 = (
    "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748"
)
EXPECTED_CHECKS = {
    "exactVersion",
    "exactBinarySha256",
    "caFailureRejectedBeforeHttp",
    "caFailureClassifiedAsTls",
    "extraCaAllowsMessagesRequest",
    "lowercaseProxyWinsPrecedence",
    "uppercaseProxyNotUsed",
    "proxiedMessagesRequestSucceeds",
    "noProxyBypassesBothProxies",
    "noProxyDirectRequestSucceeds",
    "invalidProxyFailsClosed",
    "invalidProxyDiagnostic",
    "mtlsRequestSucceeds",
    "mtlsClientCertificateObserved",
}
EXPECTED_RUNS = {
    "caFailure": (1, True, None),
    "caSuccess": (0, False, "NETWORK_OK"),
    "proxyPrecedence": (0, False, "NETWORK_OK"),
    "noProxy": (0, False, "NETWORK_OK"),
    "invalidProxy": (1, None, None),
    "mtls": (0, False, "MTLS_OK"),
}
EXPECTED_MARKERS = {
    "caFailure": "NETWORK_CA_FAILURE_MARKER",
    "caSuccess": "NETWORK_CA_SUCCESS_MARKER",
    "proxyPrecedence": "NETWORK_PROXY_PRECEDENCE_MARKER",
    "noProxy": "NETWORK_NO_PROXY_MARKER",
    "invalidProxy": "NETWORK_INVALID_PROXY_MARKER",
    "mtls": "NETWORK_MTLS_MARKER",
}


def add_failure(failures: list[str], message: str) -> None:
    failures.append(f"network proxy/TLS probe: {message}")


def require_exact_keys(
    value: Any, expected: set[str], label: str, failures: list[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        add_failure(failures, f"{label} is not an object")
        return {}
    actual = set(value)
    if actual != expected:
        add_failure(
            failures,
            f"{label} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}",
        )
    return value


def validate_api_record(
    name: str, records: Any, marker: str, failures: list[str]
) -> None:
    expected_count = 0 if name in {"caFailure", "invalidProxy"} else 1
    if not isinstance(records, list) or len(records) != expected_count:
        add_failure(
            failures,
            f"apiRequestsByMarker.{name} count expected={expected_count}, "
            f"actual={len(records) if isinstance(records, list) else 'non-list'}",
        )
        return
    if not records:
        return
    record = records[0]
    if not isinstance(record, dict):
        add_failure(failures, f"apiRequestsByMarker.{name}[0] is not an object")
        return
    required = {
        "marker",
        "method",
        "path",
        "clientAuthorized",
        "clientAuthorizationError",
        "clientCommonName",
    }
    if set(record) != required:
        add_failure(failures, f"apiRequestsByMarker.{name}[0] keys differ")
    if record.get("marker") != marker:
        add_failure(failures, f"apiRequestsByMarker.{name} marker mismatch")
    if record.get("method") != "POST":
        add_failure(failures, f"apiRequestsByMarker.{name} method is not POST")
    if not isinstance(record.get("path"), str) or not record["path"].startswith(
        "/v1/messages"
    ):
        add_failure(failures, f"apiRequestsByMarker.{name} path mismatch")
    if name == "mtls":
        if record.get("clientAuthorized") is not True:
            add_failure(failures, "mTLS client was not authorized")
        if record.get("clientAuthorizationError") is not None:
            add_failure(failures, "mTLS record has an authorization error")
        if record.get("clientCommonName") != "Claude Probe Client":
            add_failure(failures, "mTLS client common name mismatch")
    else:
        if record.get("clientAuthorized") is not False:
            add_failure(failures, f"{name} unexpectedly had an authorized client cert")
        if record.get("clientCommonName") is not None:
            add_failure(failures, f"{name} unexpectedly had a client common name")


def validate_network_proxy_tls_report(
    repo: Path,
    version: str,
    metadata: dict[str, Any],
    failures: list[str],
    report_path: Path | None = None,
) -> int:
    probe_script = (
        repo
        / "skill/claude-code-version-diff/scripts/probe_network_proxy_tls.mjs"
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
        add_failure(failures, "report root is not an object")
        return 0

    expected_root = {
        "schemaVersion",
        "capturedAt",
        "target",
        "environment",
        "commands",
        "input",
        "literalOutput",
        "exitStatus",
        "observed",
        "checks",
        "boundaries",
        "pass",
    }
    if set(report) != expected_root:
        add_failure(failures, "root keys differ")
    if report.get("schemaVersion") != 1:
        add_failure(failures, "schemaVersion is not 1")
    if not isinstance(report.get("capturedAt"), str) or "T" not in report["capturedAt"]:
        add_failure(failures, "capturedAt is not an ISO-like timestamp")
    if report.get("pass") is not True:
        add_failure(failures, "pass is not true")

    target = require_exact_keys(
        report.get("target"), {"version", "binarySha256"}, "target", failures
    )
    metadata_sha = metadata.get("binary", {}).get("sha256")
    if version != EXPECTED_VERSION or target.get("version") != version:
        add_failure(failures, "target version mismatch")
    if metadata_sha != EXPECTED_BINARY_SHA256:
        add_failure(failures, "analysis/version.json binary SHA mismatch")
    if target.get("binarySha256") != metadata_sha:
        add_failure(failures, "target binary SHA mismatch")

    environment = require_exact_keys(
        report.get("environment"),
        {"platform", "arch", "nodeVersion", "opensslVersion"},
        "environment",
        failures,
    )
    for field in ("platform", "arch", "nodeVersion", "opensslVersion"):
        if not isinstance(environment.get(field), str) or not environment[field]:
            add_failure(failures, f"environment.{field} is empty")

    commands = require_exact_keys(
        report.get("commands"), set(EXPECTED_RUNS), "commands", failures
    )
    for name, marker in EXPECTED_MARKERS.items():
        if not isinstance(commands.get(name), str) or marker not in commands[name]:
            add_failure(failures, f"commands.{name} does not bind its marker")

    input_value = require_exact_keys(
        report.get("input"), {"baseUrl", "proxyA", "proxyB", "markers", "tls"},
        "input", failures,
    )
    if input_value.get("baseUrl") != "https://localhost:$PORT":
        add_failure(failures, "input.baseUrl is not normalized")
    if input_value.get("proxyA") != "http://127.0.0.1:$PROXY_A_PORT":
        add_failure(failures, "input.proxyA is not normalized")
    if input_value.get("proxyB") != "http://127.0.0.1:$PROXY_B_PORT":
        add_failure(failures, "input.proxyB is not normalized")
    if input_value.get("markers") != EXPECTED_MARKERS:
        add_failure(failures, "input.markers mismatch")
    tls_input = require_exact_keys(
        input_value.get("tls"),
        {"serverCommonName", "clientCommonName", "generatedForProbeOnly"},
        "input.tls",
        failures,
    )
    if tls_input != {
        "serverCommonName": "localhost",
        "clientCommonName": "Claude Probe Client",
        "generatedForProbeOnly": True,
    }:
        add_failure(failures, "input.tls mismatch")

    exit_status = require_exact_keys(
        report.get("exitStatus"), set(EXPECTED_RUNS), "exitStatus", failures
    )
    literal = require_exact_keys(
        report.get("literalOutput"), set(EXPECTED_RUNS), "literalOutput", failures
    )
    for name, (expected_exit, expected_error, expected_result) in EXPECTED_RUNS.items():
        if exit_status.get(name) != expected_exit:
            add_failure(failures, f"exitStatus.{name} mismatch")
        item = require_exact_keys(
            literal.get(name),
            {"exitStatus", "signal", "subtype", "isError", "result", "stderrClass"},
            f"literalOutput.{name}",
            failures,
        )
        if item.get("exitStatus") != expected_exit or item.get("signal") is not None:
            add_failure(failures, f"literalOutput.{name} process result mismatch")
        if item.get("isError") is not expected_error:
            add_failure(failures, f"literalOutput.{name}.isError mismatch")
        if name == "caFailure":
            if not isinstance(item.get("result"), str) or "certificate" not in item[
                "result"
            ].lower():
                add_failure(failures, "caFailure literal result lacks certificate error")
        elif item.get("result") != expected_result:
            add_failure(failures, f"literalOutput.{name}.result mismatch")
        if name == "invalidProxy" and item.get("stderrClass") != "proxy":
            add_failure(failures, "invalidProxy stderrClass mismatch")

    checks = require_exact_keys(report.get("checks"), EXPECTED_CHECKS, "checks", failures)
    for name in EXPECTED_CHECKS:
        if checks.get(name) is not True:
            add_failure(failures, f"required check failed: {name}")

    observed = require_exact_keys(
        report.get("observed"),
        {"apiRequestsByMarker", "proxyConnects", "tlsFixtureSetupExitStatuses"},
        "observed",
        failures,
    )
    api_by_marker = require_exact_keys(
        observed.get("apiRequestsByMarker"),
        set(EXPECTED_RUNS),
        "observed.apiRequestsByMarker",
        failures,
    )
    for name, marker in EXPECTED_MARKERS.items():
        validate_api_record(name, api_by_marker.get(name), marker, failures)

    proxy_connects = observed.get("proxyConnects")
    if not isinstance(proxy_connects, list) or not proxy_connects:
        add_failure(failures, "proxyConnects is empty")
    else:
        for index, record in enumerate(proxy_connects):
            if not isinstance(record, dict) or set(record) != {
                "proxy", "kind", "authority", "proxyAuthorizationPresent"
            }:
                add_failure(failures, f"proxyConnects[{index}] shape mismatch")
                continue
            if record.get("proxy") != "lowercase" or record.get("kind") != "connect":
                add_failure(failures, f"proxyConnects[{index}] used the wrong proxy")
            if record.get("authority") != "localhost:$PORT":
                add_failure(failures, f"proxyConnects[{index}] authority mismatch")
            if record.get("proxyAuthorizationPresent") is not False:
                add_failure(failures, f"proxyConnects[{index}] auth presence mismatch")
    if isinstance(proxy_connects, list) and any(
        isinstance(record, dict) and record.get("proxy") == "uppercase"
        for record in proxy_connects
    ):
        add_failure(failures, "uppercase proxy was unexpectedly used")
    if observed.get("tlsFixtureSetupExitStatuses") != [0, 0, 0, 0, 0]:
        add_failure(failures, "TLS fixture setup statuses mismatch")

    boundaries = report.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != 4:
        add_failure(failures, "boundaries must contain exactly four statements")
    else:
        boundary_text = "\n".join(str(item) for item in boundaries)
        for term in (
            "exact 2.1.235 main Messages HTTPS transport only",
            "does not prove Axios",
            "local one-day test fixtures",
            "not enterprise certificate issuance",
        ):
            if term not in boundary_text:
                add_failure(failures, f"boundary is missing {term!r}")

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
    count = validate_network_proxy_tls_report(
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
    print("network proxy/TLS validation: PASS")
    print(f"checks validated: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
