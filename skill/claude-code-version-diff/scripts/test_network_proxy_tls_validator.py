#!/usr/bin/env python3
"""Prove forged network proxy/TLS probe evidence is rejected."""

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


def add_uppercase_proxy(document: dict[str, Any]) -> None:
    document["observed"]["proxyConnects"].append(
        {
            "proxy": "uppercase",
            "kind": "connect",
            "authority": "localhost:443",
            "proxyAuthorizationPresent": False,
        }
    )


def clear_proxy_records(document: dict[str, Any]) -> None:
    document["observed"]["proxyConnects"] = []


def remove_boundary(document: dict[str, Any]) -> None:
    document["boundaries"].pop()


CASES: list[tuple[str, Mutation]] = [
    ("schema downgrade", set_path("schemaVersion", value=0)),
    ("target version forgery", set_path("target", "version", value="2.1.999")),
    ("target binary forgery", set_path("target", "binarySha256", value="0" * 64)),
    ("root extra field", add_root),
    ("pass false", set_path("pass", value=False)),
    ("required check false", set_path("checks", "mtlsRequestSucceeds", value=False)),
    ("required check removed", delete_path("checks", "noProxyBypassesBothProxies")),
    ("unexpected check", add_check),
    (
        "command marker forgery",
        set_path("commands", "proxyPrecedence", value="claude --print WRONG_MARKER"),
    ),
    ("normalized base URL forgery", set_path("input", "baseUrl", value="https://example.com")),
    (
        "input marker forgery",
        set_path("input", "markers", "mtls", value="NETWORK_WRONG_MARKER"),
    ),
    ("exit status forgery", set_path("exitStatus", "invalidProxy", value=0)),
    (
        "literal result forgery",
        set_path("literalOutput", "proxyPrecedence", "result", value="FORGED"),
    ),
    (
        "CA failure result forgery",
        set_path("literalOutput", "caFailure", "result", value="ordinary error"),
    ),
    (
        "API request marker forgery",
        set_path(
            "observed", "apiRequestsByMarker", "caSuccess", value=[]
        ),
    ),
    (
        "mTLS authorization forgery",
        set_path(
            "observed", "apiRequestsByMarker", "mtls", value=[{
                "marker": "NETWORK_MTLS_MARKER",
                "method": "POST",
                "path": "/v1/messages?beta=true",
                "clientAuthorized": False,
                "clientAuthorizationError": None,
                "clientCommonName": "Claude Probe Client",
            }]
        ),
    ),
    (
        "mTLS common name forgery",
        set_path(
            "observed", "apiRequestsByMarker", "mtls", value=[{
                "marker": "NETWORK_MTLS_MARKER",
                "method": "POST",
                "path": "/v1/messages?beta=true",
                "clientAuthorized": True,
                "clientAuthorizationError": None,
                "clientCommonName": "Other Client",
            }]
        ),
    ),
    (
        "lowercase proxy relabeled",
        set_path("observed", "proxyConnects", value=[{
            "proxy": "uppercase",
            "kind": "connect",
            "authority": "localhost:443",
            "proxyAuthorizationPresent": False,
        }]),
    ),
    ("uppercase proxy added", add_uppercase_proxy),
    ("proxy evidence removed", clear_proxy_records),
    (
        "TLS fixture setup failure hidden",
        set_path("observed", "tlsFixtureSetupExitStatuses", value=[0, 0, 1, 0, 0]),
    ),
    ("boundary removed", remove_boundary),
]


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    validator = repo / "skill/claude-code-version-diff/scripts/validate_network_proxy_tls.py"
    source = repo / "analysis/runtime-probes/network-proxy-tls.json"
    original_hash = sha256(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="claude-network-proxy-tls-negative-") as temporary:
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
        raise RuntimeError("source network proxy/TLS report hash changed")
    print(f"network proxy/TLS negative validation: PASS ({len(CASES)} forgeries rejected)")
    print(f"source report sha256 preserved: {original_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
