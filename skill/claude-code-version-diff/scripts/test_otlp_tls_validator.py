#!/usr/bin/env python3
"""Prove forged OTLP TLS probe evidence is rejected."""

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


def fake_signal_ca_success(document: dict[str, Any]) -> None:
    document["observed"]["runs"]["signalOtlpCa"]["collectorRequests"] = copy.deepcopy(
        document["observed"]["runs"]["nodeExtraCa"]["collectorRequests"]
    )


def fake_otel_client_success(document: dict[str, Any]) -> None:
    document["observed"]["runs"]["mtlsOtelClient"]["collectorRequests"] = copy.deepcopy(
        document["observed"]["runs"]["mtlsClaudeClient"]["collectorRequests"]
    )


def remove_boundary(document: dict[str, Any]) -> None:
    document["boundaries"].pop()


CASES: list[tuple[str, Mutation]] = [
    ("schema downgrade", set_path("schemaVersion", value=0)),
    ("target version forgery", set_path("target", "version", value="2.1.999")),
    ("target binary forgery", set_path("target", "binarySha256", value="0" * 64)),
    ("root extra field", add_root),
    ("pass false", set_path("pass", value=False)),
    (
        "required check false",
        set_path("checks", "mtlsClientAuthorized", value=False),
    ),
    (
        "required check removed",
        delete_path("checks", "signalCaExportFailsBeforeHttp"),
    ),
    ("unexpected check", add_check),
    (
        "command marker forgery",
        set_path("commands", "nodeExtraCa", value="claude --print WRONG_MARKER"),
    ),
    (
        "command configuration forgery",
        set_path(
            "commands",
            "mtlsClaudeClient",
            value="NODE_EXTRA_CA_CERTS=$CA CLAUDE_CODE_CLIENT_CERT=$CERT claude WRONG",
        ),
    ),
    (
        "normalized endpoint forgery",
        set_path("input", "proxiedCollector", value="https://example.com/v1/logs"),
    ),
    (
        "input marker forgery",
        set_path("input", "markers", "proxyPrecedence", value="WRONG_MARKER"),
    ),
    ("exit status forgery", set_path("exitStatus", "noCa", value=1)),
    (
        "literal result forgery",
        set_path("literalOutput", "nodeExtraCa", "result", value="FORGED"),
    ),
    (
        "fixture sanity forgery",
        set_path("observed", "fixtureSanity", "mtlsStatus", value=500),
    ),
    (
        "Messages marker hidden",
        set_path("observed", "messagesMarkersObserved", "signalOtlpCa", value=False),
    ),
    ("signal CA false success", fake_signal_ca_success),
    (
        "global CA success removed",
        set_path("observed", "runs", "nodeExtraCa", "collectorRequests", value=[]),
    ),
    (
        "signal CA TLS error forged",
        set_path(
            "observed",
            "runs",
            "signalOtlpCa",
            "tlsErrorCodes",
            value=["CERT_HAS_EXPIRED"],
        ),
    ),
    ("OTEL client pair false success", fake_otel_client_success),
    (
        "Claude mTLS authorization forged",
        set_path(
            "observed",
            "runs",
            "mtlsClaudeClient",
            "collectorRequests",
            value=[{
                "method": "POST",
                "path": "/v1/logs",
                "contentType": "application/json",
                "clientAuthorized": False,
                "clientAuthorizationError": None,
                "clientCommonName": "Claude OTLP Probe Client",
            }],
        ),
    ),
    (
        "Claude mTLS common name forged",
        set_path(
            "observed",
            "runs",
            "mtlsClaudeClient",
            "collectorRequests",
            value=[{
                "method": "POST",
                "path": "/v1/logs",
                "contentType": "application/json",
                "clientAuthorized": True,
                "clientAuthorizationError": None,
                "clientCommonName": "Other Client",
            }],
        ),
    ),
    (
        "proxy lower-case relabeled",
        set_path(
            "observed",
            "runs",
            "proxyPrecedence",
            "collectorProxyConnects",
            value=[{
                "proxy": "uppercase",
                "kind": "connect",
                "authority": "collector.invalid:$TLS_PORT",
            }],
        ),
    ),
    (
        "proxy evidence removed",
        set_path(
            "observed", "runs", "proxyPrecedence", "collectorProxyConnects", value=[]
        ),
    ),
    (
        "TLS setup failure hidden",
        set_path("observed", "tlsFixtureSetupExitStatuses", value=[0, 0, 1, 0, 0, 0]),
    ),
    ("boundary removed", remove_boundary),
]


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    validator = repo / "skill/claude-code-version-diff/scripts/validate_otlp_tls.py"
    source = repo / "analysis/runtime-probes/otlp-tls.json"
    original_hash = sha256(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="claude-otlp-tls-negative-") as temporary:
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
        raise RuntimeError("source OTLP TLS report hash changed")
    print(f"OTLP TLS negative validation: PASS ({len(CASES)} forgeries rejected)")
    print(f"source report sha256 preserved: {original_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
