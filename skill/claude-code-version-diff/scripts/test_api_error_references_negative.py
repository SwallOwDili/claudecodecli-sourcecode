#!/usr/bin/env python3
"""Prove API/Beta and error/diagnostic reference validation fails closed."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_check(repo: Path) -> subprocess.CompletedProcess[str]:
    script = repo / "skill/claude-code-version-diff/scripts/build_api_error_references.py"
    return subprocess.run(
        [sys.executable, str(script), str(repo), "--check"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def expect_failure(repo: Path, relative: str, old: bytes, new: bytes, label: str) -> None:
    path = repo / relative
    original = path.read_bytes()
    if old not in original:
        raise AssertionError(f"{label}: mutation target not found")
    mutated = original.replace(old, new, 1)
    try:
        path.write_bytes(mutated)
        result = run_check(repo)
        if result.returncode == 0:
            raise AssertionError(f"{label}: validator unexpectedly passed")
    finally:
        path.write_bytes(original)
    restored = path.read_bytes()
    if restored != original:
        raise AssertionError(
            f"{label}: restore mismatch {digest(original)} != {digest(restored)}"
        )
    print(f"PASS: {label} rejected and restored byte-for-byte")


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    baseline = run_check(repo)
    if baseline.returncode != 0:
        print(baseline.stdout, end="")
        print(baseline.stderr, end="", file=sys.stderr)
        raise AssertionError("baseline API/error reference validation failed")
    expect_failure(
        repo,
        "analysis/api-beta-route-ownership.md",
        b"| 1 | `/.well-known/oauth-authorization-server` |",
        b"| 1 | `/.well-known/oauth-authorization-server-REMOVED` |",
        "missing exact API path coverage",
    )
    expect_failure(
        repo,
        "analysis/source-inventory/api-paths.txt",
        b"/api/claude_code/skills\n",
        b"/api/claude_code/skills-v2\n",
        "unclassified first-party API route",
    )
    expect_failure(
        repo,
        "analysis/source-inventory/anthropic-beta-identifiers.txt",
        b"context-1m-2025-08-07\n",
        b"context-2m-2026-08-23\n",
        "unclassified beta identifier",
    )
    expect_failure(
        repo,
        "analysis/api-beta-route-ownership.md",
        b"Bundled gateway admin handler",
        b"Provider organization consumer",
        "stale spend-limit route ownership",
    )
    expect_failure(
        repo,
        "analysis/error-diagnostic-atlas.md",
        b"constructor callsites \xe5\x85\xb1 **4,831**",
        b"constructor callsites \xe5\x85\xb1 **4,830**",
        "stale constructor metric",
    )
    expect_failure(
        repo,
        "analysis/error-diagnostic-atlas.md",
        "**Boundary：**".encode(),
        "**Server-limit：**".encode(),
        "missing explicit Boundary contract",
    )
    final = run_check(repo)
    if final.returncode != 0:
        raise AssertionError("final API/error reference validation failed after restore")
    print("PASS: all API/error negative checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
