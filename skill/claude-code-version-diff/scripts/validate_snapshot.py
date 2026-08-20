#!/usr/bin/env python3
"""Validate a Claude Code version snapshot and its packed-file hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


PERSONAL_PATH_RE = re.compile(
    rb"(?:"
    rb"/Users/[^/\x00]+/(?:Documents|Desktop|Downloads|Library|\.(?:codex|local|config|cache))(?:/|$)"
    rb"|/home/[^/\x00]+/(?:Documents|Desktop|Downloads|\.(?:codex|local|config|cache))(?:/|$)"
    rb"|[A-Za-z]:\\Users\\[^\\\x00]+\\(?:Documents|Desktop|Downloads|AppData|\.codex)(?:\\|$)"
    rb")"
)


def find_personal_paths(repo: Path) -> list[str]:
    failures: list[str] = []
    text_suffixes = {
        ".json",
        ".md",
        ".mjs",
        ".py",
        ".sh",
        ".txt",
        ".toml",
        ".yaml",
        ".yml",
    }
    for relative in git(repo, "ls-files").splitlines():
        if relative.startswith(("extracted/", "reverse/")):
            continue
        path = repo / relative
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        if PERSONAL_PATH_RE.search(path.read_bytes()):
            failures.append(relative)
    return failures


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    failures: list[str] = []

    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    branch = git(repo, "branch", "--show-current")
    if branch and branch != version:
        failures.append(f"branch {branch!r} does not equal VERSION {version!r}")

    metadata = json.loads((repo / "analysis/version.json").read_text(encoding="utf-8"))
    if metadata.get("version") != version:
        failures.append("analysis/version.json version does not equal VERSION")
    if metadata.get("branch") != version:
        failures.append("analysis/version.json branch does not equal VERSION")
    for key in ("sourcePath", "entrypointPath"):
        value = metadata.get("binary", {}).get(key, "")
        if not isinstance(value, str) or not value.startswith("$"):
            failures.append(f"analysis/version.json binary.{key} is not symbolic/redacted")

    personal_path_files = find_personal_paths(repo)
    if personal_path_files:
        failures.append(
            "machine-specific home/workspace paths found in: "
            + ", ".join(personal_path_files)
        )

    risk_surface = repo / "analysis/risk-control-surface.txt"
    risk_entries = 0
    if not risk_surface.is_file():
        failures.append("missing analysis/risk-control-surface.txt")
    else:
        risk_lines = risk_surface.read_text(encoding="utf-8").splitlines()
        required_sections = {
            "[permission-modes]",
            "[safety-circuit-breakers]",
            "[sandbox-network]",
            "[credential-controls]",
            "[enterprise-governance]",
            "[boundaries]",
        }
        missing_sections = required_sections - set(risk_lines)
        if missing_sections:
            failures.append(
                "risk-control surface missing sections: "
                + ", ".join(sorted(missing_sections))
            )
        risk_entries = sum(
            1
            for line in risk_lines
            if line.strip() and not line.startswith("#") and not line.startswith("[")
        )

    manifest = json.loads(
        (repo / "analysis/unpack-manifest.json").read_text(encoding="utf-8")
    )
    files = manifest.get("files", [])
    checked = 0
    for entry in files:
        packed_path = entry["path"]
        repo_path = repo / "extracted" / ("cli.js" if packed_path == "cli" else packed_path)
        if not repo_path.is_file():
            failures.append(f"missing extracted file: {repo_path.relative_to(repo)}")
            continue
        actual = sha256(repo_path)
        expected = entry.get("sha256Packed") or entry.get("sha256")
        if actual != expected:
            failures.append(
                f"hash mismatch for {repo_path.relative_to(repo)}: {actual} != {expected}"
            )
        checked += 1

    main_source = repo / "extracted/cli.js"
    prefix = main_source.read_bytes()[:64]
    if not prefix.startswith(b"// @bun @bytecode @bun-cjs"):
        failures.append("extracted/cli.js does not have the expected Bun bytecode banner")
    source_bytes = main_source.read_bytes()
    if version.encode("ascii") not in source_bytes:
        failures.append("VERSION string is absent from extracted/cli.js")

    if failures:
        print("snapshot validation: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    reverse = repo / "reverse"
    deep_output = ""
    if reverse.is_dir():
        deep_validator = repo / "skill/claude-code-version-diff/scripts/validate_deep_reverse.py"
        if not deep_validator.is_file():
            print("snapshot validation: FAIL")
            print("- reverse directory exists but deep reverse validator is missing")
            return 1
        process = subprocess.run(
            [sys.executable, str(deep_validator), str(repo)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deep_output = process.stdout.strip()
        if process.returncode != 0:
            print("snapshot validation: FAIL")
            print(deep_output)
            return process.returncode

    print(f"snapshot validation: PASS")
    print(f"version: {version}")
    print(f"branch: {branch}")
    print(f"files checked: {checked}")
    print(f"risk controls checked: {risk_entries}")
    print("capture path privacy: PASS")
    print(f"main source sha256: {sha256(main_source)}")
    if deep_output:
        print(deep_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
