#!/usr/bin/env python3
"""Validate hashes and invariants of generated deep-reverse artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    reverse = repo / "reverse"
    failures: list[str] = []

    summary = json.loads((reverse / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((reverse / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = reverse / entry["path"]
        if not path.is_file():
            failures.append(f"missing reverse artifact: {entry['path']}")
            continue
        actual = sha256(path)
        if actual != entry["sha256"]:
            failures.append(f"hash mismatch: {entry['path']}: {actual} != {entry['sha256']}")

    bytecode = summary["bytecode"]
    unpacked_hash, unpacked_size = gzip_sha256(repo / bytecode["gzipPath"])
    if unpacked_hash != bytecode["uncompressedSha256"]:
        failures.append("decompressed bytecode SHA-256 does not match metadata")
    if unpacked_size != bytecode["uncompressedSize"]:
        failures.append("decompressed bytecode size does not match metadata")

    bundle = repo / summary["canonicalBundle"]["path"]
    if sha256(bundle) != summary["canonicalBundle"]["sha256"]:
        failures.append("canonical bundle SHA-256 does not match reverse summary")
    readable = summary["readableJavaScript"]
    if sha256(repo / readable["path"]) != readable["sha256"]:
        failures.append("readable JavaScript SHA-256 does not match metadata")
    semantic = readable["semanticInventoryCheck"]
    if not semantic["environmentIdentifiersEqual"] or not semantic["endpointHostsEqual"]:
        failures.append("readable JavaScript stable inventory differs from canonical bundle")

    for module in summary["nativeModules"]:
        source = repo / module["sourcePath"]
        if sha256(source) != module["sha256"]:
            failures.append(f"native source hash mismatch: {module['name']}")

    if failures:
        print("deep reverse validation: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("deep reverse validation: PASS")
    print(f"manifest files checked: {len(manifest['files'])}")
    print(f"bytecode bytes checked: {unpacked_size}")
    print(f"bytecode sha256: {unpacked_hash}")
    print(f"readable JavaScript sha256: {readable['sha256']}")
    print(f"native modules checked: {len(summary['nativeModules'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
