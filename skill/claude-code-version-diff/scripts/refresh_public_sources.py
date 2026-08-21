#!/usr/bin/env python3
"""Refresh first-party research hashes without treating current docs as release evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "svg", "noscript", "template"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript", "template"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def semantic_text(body: bytes) -> str:
    parser = VisibleTextParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return normalize_text(" ".join(parser.parts))


def excerpt_hashes(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    headings = list(re.finditer(r"^## `([^`]+)`\s*$", content, re.MULTILINE))
    output: dict[str, str] = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        block = content[heading.end():end]
        quotes = re.findall(r"^>\s?(.*)$", block, re.MULTILINE)
        normalized = normalize_text(" ".join(quotes))
        output[heading.group(1)] = digest(normalized.encode())
    return output


def fetch(url: str) -> tuple[int, bytes]:
    with tempfile.NamedTemporaryFile() as body_file:
        result = subprocess.run(
            [
                "curl", "-L", "--compressed", "--silent", "--show-error",
                "--output", body_file.name, "--write-out", "%{http_code}", url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(result.stdout.strip()), Path(body_file.name).read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    manifest_path = repo / "analysis/public-sources/manifest.json"
    excerpts_path = repo / "analysis/public-source-excerpts.md"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = excerpt_hashes(excerpts_path)

    for source in manifest["sources"]:
        status, body = fetch(source["url"])
        visible = semantic_text(body).encode()
        source.update(
            status=status,
            bytes=len(body),
            sha256=digest(body),
            semanticTextBytes=len(visible),
            semanticTextSha256=digest(visible),
            excerptSha256={excerpt_id: hashes[excerpt_id] for excerpt_id in source["excerptIds"]},
        )

    manifest["schemaVersion"] = 2
    manifest["retrievedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest["captureMethod"] = (
        "curl HTTP GET with redirects and content decoding; sha256 covers response bytes; "
        "semanticTextSha256 covers whitespace-normalized visible HTML text with script/style/svg/"
        "noscript/template content removed; excerptSha256 covers normalized quoted excerpts"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
