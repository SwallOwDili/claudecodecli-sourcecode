#!/usr/bin/env python3
"""Resolve version and repository identity for the Pages pipeline."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    value = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise RuntimeError(f"Invalid VERSION for Pages publication: {value!r}")
    return value


def normalize_repository_url(value: str) -> str:
    value = value.strip().removesuffix(".git")
    ssh = re.fullmatch(r"git@([^:]+):(.+)", value)
    if ssh:
        return f"https://{ssh.group(1)}/{ssh.group(2)}"
    return value.rstrip("/")


def repository_url() -> str:
    explicit = os.environ.get("GITHUB_REPOSITORY_URL")
    if explicit:
        return normalize_repository_url(explicit)

    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if server and repository:
        return normalize_repository_url(f"{server}/{repository}")

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return normalize_repository_url(result.stdout)
