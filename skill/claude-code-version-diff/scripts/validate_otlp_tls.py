#!/usr/bin/env python3
"""Validate the exact-binary OTLP TLS, mTLS, and proxy probe report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_RELATIVE = "analysis/runtime-probes/otlp-tls.json"
EXPECTED_VERSION = "2.1.235"
EXPECTED_BINARY_SHA256 = (
    "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748"
)
RUNS = (
    "noCa",
    "signalOtlpCa",
    "commonOtlpCa",
    "signalOtlpCaProtobuf",
    "signalOtlpCaTls12",
    "nodeExtraCa",
    "signalOtlpCaIp",
    "tlsVerificationDisabled",
    "signalOtlpCaWithWrongCommon",
    "mtlsMissingClient",
    "mtlsOtelClient",
    "mtlsClaudeCertOnly",
    "mtlsClaudeClient",
    "mtlsOtelClientProtobuf",
    "proxyPrecedence",
)
MARKERS = {
    "noCa": "OTLP_TLS_NO_CA_MARKER",
    "signalOtlpCa": "OTLP_TLS_SIGNAL_OTLP_CA_MARKER",
    "commonOtlpCa": "OTLP_TLS_COMMON_OTLP_CA_MARKER",
    "signalOtlpCaProtobuf": "OTLP_TLS_SIGNAL_OTLP_CA_PROTOBUF_MARKER",
    "signalOtlpCaTls12": "OTLP_TLS_SIGNAL_OTLP_CA_TLS12_MARKER",
    "nodeExtraCa": "OTLP_TLS_NODE_EXTRA_CA_MARKER",
    "signalOtlpCaIp": "OTLP_TLS_SIGNAL_OTLP_CA_IP_MARKER",
    "tlsVerificationDisabled": "OTLP_TLS_TLS_VERIFICATION_DISABLED_MARKER",
    "signalOtlpCaWithWrongCommon": "OTLP_TLS_SIGNAL_OTLP_CA_WITH_WRONG_COMMON_MARKER",
    "mtlsMissingClient": "OTLP_TLS_MTLS_MISSING_CLIENT_MARKER",
    "mtlsOtelClient": "OTLP_TLS_MTLS_OTEL_CLIENT_MARKER",
    "mtlsClaudeCertOnly": "OTLP_TLS_MTLS_CLAUDE_CERT_ONLY_MARKER",
    "mtlsClaudeClient": "OTLP_TLS_MTLS_CLAUDE_CLIENT_MARKER",
    "mtlsOtelClientProtobuf": "OTLP_TLS_MTLS_OTEL_CLIENT_PROTOBUF_MARKER",
    "proxyPrecedence": "OTLP_TLS_PROXY_PRECEDENCE_MARKER",
}
EXPECTED_CHECKS = {
    "exactVersion",
    "exactBinarySha256",
    "fixtureSanityPasses",
    "everyRunReachedMessagesApi",
    "allAgentRunsSucceed",
    "noCaProducesNoHttpRequest",
    "noCaTlsHandshakeErrorObserved",
    "signalCaExportFailsBeforeHttp",
    "commonOtlpCaExportFailsBeforeHttp",
    "protobufSignalCaExportFailsBeforeHttp",
    "tls12SignalCaExportFailsBeforeHttp",
    "nodeExtraCaAllowsExport",
    "ipSanSignalCaExportFailsBeforeHttp",
    "disabledVerificationAllowsExport",
    "signalSpecificCaDoesNotRestoreExport",
    "missingClientCertificateRejectsExport",
    "missingClientCertificateTlsErrorObserved",
    "certWithoutKeyRejectsExport",
    "certWithoutKeyTlsErrorObserved",
    "otelClientPairNotForwarded",
    "mtlsExportObserved",
    "mtlsClientAuthorized",
    "mtlsClientCommonNameObserved",
    "protobufOtelClientPairNotForwarded",
    "proxyRunExportObserved",
    "collectorEndpointUsesLowercaseProxy",
    "collectorEndpointNotSentToUppercaseProxy",
    "otlpHttpJsonUsesGenericHttpsProxy",
    "successfulExportsUseJsonContentType",
    "telemetryTransportFailureDoesNotFailAgentTask",
}
SUCCESSFUL_EXPORTS = {
    "nodeExtraCa",
    "tlsVerificationDisabled",
    "mtlsClaudeClient",
    "proxyPrecedence",
}
TLS_ERROR_CODES = {
    "noCa": "ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
    "signalOtlpCa": "ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
    "commonOtlpCa": "ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
    "signalOtlpCaProtobuf": "ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
    "signalOtlpCaTls12": "ECONNRESET",
    "signalOtlpCaIp": "ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
    "signalOtlpCaWithWrongCommon": "ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
    "mtlsMissingClient": "ERR_SSL_PEER_DID_NOT_RETURN_A_CERTIFICATE",
    "mtlsOtelClient": "ERR_SSL_PEER_DID_NOT_RETURN_A_CERTIFICATE",
    "mtlsClaudeCertOnly": "ERR_SSL_PEER_DID_NOT_RETURN_A_CERTIFICATE",
    "mtlsOtelClientProtobuf": "ERR_SSL_PEER_DID_NOT_RETURN_A_CERTIFICATE",
}


def add_failure(failures: list[str], message: str) -> None:
    failures.append(f"OTLP TLS probe: {message}")


def exact_object(
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


def validate_collector_record(
    name: str, records: Any, failures: list[str]
) -> None:
    expected_count = 1 if name in SUCCESSFUL_EXPORTS else 0
    if not isinstance(records, list) or len(records) != expected_count:
        add_failure(
            failures,
            f"observed.runs.{name}.collectorRequests count expected={expected_count}, "
            f"actual={len(records) if isinstance(records, list) else 'non-list'}",
        )
        return
    if not records:
        return
    record = exact_object(
        records[0],
        {
            "method",
            "path",
            "contentType",
            "clientAuthorized",
            "clientAuthorizationError",
            "clientCommonName",
        },
        f"observed.runs.{name}.collectorRequests[0]",
        failures,
    )
    if record.get("method") != "POST" or record.get("path") != "/v1/logs":
        add_failure(failures, f"{name} collector method/path mismatch")
    if record.get("contentType") != "application/json":
        add_failure(failures, f"{name} collector content type mismatch")
    if name == "mtlsClaudeClient":
        if record.get("clientAuthorized") is not True:
            add_failure(failures, "Claude global mTLS client was not authorized")
        if record.get("clientAuthorizationError") is not None:
            add_failure(failures, "Claude global mTLS client has authorization error")
        if record.get("clientCommonName") != "Claude OTLP Probe Client":
            add_failure(failures, "Claude global mTLS client common name mismatch")
    else:
        if record.get("clientAuthorized") is not False:
            add_failure(failures, f"{name} unexpectedly used an authorized client cert")
        if record.get("clientCommonName") is not None:
            add_failure(failures, f"{name} unexpectedly exposed a client common name")


def validate_otlp_tls_report(
    repo: Path,
    version: str,
    metadata: dict[str, Any],
    failures: list[str],
    report_path: Path | None = None,
) -> int:
    script = repo / "skill/claude-code-version-diff/scripts/probe_otlp_tls.mjs"
    if not script.is_file():
        add_failure(failures, "missing probe script")
    elif script.stat().st_mode & 0o111 == 0:
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
        add_failure(failures, "capturedAt is not ISO-like")
    if report.get("pass") is not True:
        add_failure(failures, "pass is not true")

    target = exact_object(
        report.get("target"), {"version", "binarySha256"}, "target", failures
    )
    metadata_sha = metadata.get("binary", {}).get("sha256")
    if version != EXPECTED_VERSION or target.get("version") != version:
        add_failure(failures, "target version mismatch")
    if metadata_sha != EXPECTED_BINARY_SHA256:
        add_failure(failures, "analysis/version.json binary SHA mismatch")
    if target.get("binarySha256") != metadata_sha:
        add_failure(failures, "target binary SHA mismatch")

    environment = exact_object(
        report.get("environment"),
        {"platform", "arch", "nodeVersion", "opensslVersion"},
        "environment",
        failures,
    )
    for field in environment:
        if not isinstance(environment.get(field), str) or not environment[field]:
            add_failure(failures, f"environment.{field} is empty")

    commands = exact_object(report.get("commands"), set(RUNS), "commands", failures)
    for name in RUNS:
        command = commands.get(name)
        if not isinstance(command, str) or MARKERS[name] not in command:
            add_failure(failures, f"commands.{name} does not bind its marker")
    command_terms = {
        "signalOtlpCa": "OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE=$CA",
        "commonOtlpCa": "OTEL_EXPORTER_OTLP_CERTIFICATE=$CA",
        "nodeExtraCa": "NODE_EXTRA_CA_CERTS=$CA",
        "mtlsOtelClient": "OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY=$KEY",
        "mtlsClaudeCertOnly": "CLAUDE_CODE_CLIENT_CERT=$CERT",
        "mtlsClaudeClient": "CLAUDE_CODE_CLIENT_KEY=$KEY",
        "proxyPrecedence": "https_proxy=$LOWERCASE HTTPS_PROXY=$UPPERCASE",
    }
    for name, term in command_terms.items():
        if term not in str(commands.get(name)):
            add_failure(failures, f"commands.{name} is missing {term}")

    input_value = exact_object(
        report.get("input"),
        {
            "messagesBaseUrl",
            "tlsCollector",
            "mtlsCollector",
            "tls12Collector",
            "proxiedCollector",
            "lowercaseProxy",
            "uppercaseProxy",
            "markers",
            "tls",
        },
        "input",
        failures,
    )
    expected_endpoints = {
        "messagesBaseUrl": "http://127.0.0.1:$MESSAGES_PORT",
        "tlsCollector": "https://localhost:$TLS_PORT/v1/logs",
        "mtlsCollector": "https://localhost:$MTLS_PORT/v1/logs",
        "tls12Collector": "https://localhost:$TLS12_PORT/v1/logs",
        "proxiedCollector": "https://collector.invalid:$TLS_PORT/v1/logs",
        "lowercaseProxy": "http://127.0.0.1:$LOWERCASE_PROXY_PORT",
        "uppercaseProxy": "http://127.0.0.1:$UPPERCASE_PROXY_PORT",
    }
    for field, expected in expected_endpoints.items():
        if input_value.get(field) != expected:
            add_failure(failures, f"input.{field} mismatch")
    if input_value.get("markers") != MARKERS:
        add_failure(failures, "input.markers mismatch")
    tls_input = exact_object(
        input_value.get("tls"),
        {"serverCommonName", "clientCommonName", "generatedForProbeOnly"},
        "input.tls",
        failures,
    )
    if tls_input != {
        "serverCommonName": "localhost / collector.invalid",
        "clientCommonName": "Claude OTLP Probe Client",
        "generatedForProbeOnly": True,
    }:
        add_failure(failures, "input.tls mismatch")

    literal = exact_object(
        report.get("literalOutput"), {"version", *RUNS}, "literalOutput", failures
    )
    if literal.get("version") != "2.1.235 (Claude Code)":
        add_failure(failures, "literalOutput.version mismatch")
    exit_status = exact_object(
        report.get("exitStatus"), {"version", *RUNS}, "exitStatus", failures
    )
    if any(exit_status.get(name) != 0 for name in ("version", *RUNS)):
        add_failure(failures, "one or more exit statuses are nonzero")
    for name in RUNS:
        item = exact_object(
            literal.get(name),
            {"exitStatus", "signal", "subtype", "isError", "result", "stderrClass"},
            f"literalOutput.{name}",
            failures,
        )
        if item.get("exitStatus") != 0 or item.get("signal") is not None:
            add_failure(failures, f"literalOutput.{name} process status mismatch")
        if item.get("subtype") != "success" or item.get("isError") is not False:
            add_failure(failures, f"literalOutput.{name} result envelope mismatch")
        if item.get("result") != "OTLP_TLS_MODEL_OK":
            add_failure(failures, f"literalOutput.{name}.result mismatch")

    checks = exact_object(report.get("checks"), EXPECTED_CHECKS, "checks", failures)
    for name in EXPECTED_CHECKS:
        if checks.get(name) is not True:
            add_failure(failures, f"required check failed: {name}")

    observed = exact_object(
        report.get("observed"),
        {"runs", "fixtureSanity", "messagesMarkersObserved", "tlsFixtureSetupExitStatuses"},
        "observed",
        failures,
    )
    if observed.get("fixtureSanity") != {
        "tlsStatus": 200,
        "tls12Status": 200,
        "mtlsStatus": 200,
    }:
        add_failure(failures, "fixture sanity mismatch")
    if observed.get("messagesMarkersObserved") != {name: True for name in RUNS}:
        add_failure(failures, "Messages API marker coverage mismatch")
    if observed.get("tlsFixtureSetupExitStatuses") != [0, 0, 0, 0, 0, 0]:
        add_failure(failures, "TLS fixture setup statuses mismatch")

    observed_runs = exact_object(observed.get("runs"), set(RUNS), "observed.runs", failures)
    for name in RUNS:
        item = exact_object(
            observed_runs.get(name),
            {"collectorRequests", "tlsErrorCodes", "tlsErrorClasses", "collectorProxyConnects"},
            f"observed.runs.{name}",
            failures,
        )
        validate_collector_record(name, item.get("collectorRequests"), failures)
        expected_code = TLS_ERROR_CODES.get(name)
        expected_codes = [expected_code] if expected_code else []
        if item.get("tlsErrorCodes") != expected_codes:
            add_failure(failures, f"{name} TLS error codes mismatch")
        expected_class = (
            "client-certificate-required"
            if expected_code == "ERR_SSL_PEER_DID_NOT_RETURN_A_CERTIFICATE"
            else "tls-other" if expected_code else None
        )
        if item.get("tlsErrorClasses") != ([expected_class] if expected_class else []):
            add_failure(failures, f"{name} TLS error classes mismatch")
        proxy_connects = item.get("collectorProxyConnects")
        if name == "proxyPrecedence":
            if proxy_connects != [{
                "proxy": "lowercase",
                "kind": "connect",
                "authority": "collector.invalid:$TLS_PORT",
            }]:
                add_failure(failures, "proxyPrecedence collector CONNECT mismatch")
        elif proxy_connects != []:
            add_failure(failures, f"{name} unexpectedly used the collector proxy")

    boundaries = report.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != 5:
        add_failure(failures, "boundaries must contain exactly five statements")
    else:
        text = "\n".join(str(item) for item in boundaries)
        for term in (
            "exact 2.1.235 OTLP HTTP logs exporter",
            "does not prove OTLP gRPC",
            "local CONNECT proxy",
            "local one-day test fixtures",
            "diagnostic control only",
        ):
            if term not in text:
                add_failure(failures, f"boundary missing {term!r}")

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
    count = validate_otlp_tls_report(
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
    print("OTLP TLS validation: PASS")
    print(f"checks validated: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
