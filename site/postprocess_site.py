#!/usr/bin/env python3
"""Rewrite unpublished repository evidence links in built HTML."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from site_identity import repository_url as default_repository_url
from site_identity import version


REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_EVIDENCE_ROOTS = {"analysis", "extracted", "reconstructed", "reverse", "skill"}
URL_ATTRIBUTES = {
    "a": ("href",),
    "audio": ("src",),
    "embed": ("src",),
    "iframe": ("src",),
    "img": ("src",),
    "link": ("href",),
    "object": ("data",),
    "script": ("src",),
    "source": ("src",),
    "video": ("src", "poster"),
}


def tracked_repository_paths() -> tuple[set[PurePosixPath], set[PurePosixPath]]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    files = {PurePosixPath(line) for line in result.stdout.splitlines() if line}
    directories: set[PurePosixPath] = set()
    for path in files:
        directories.update(path.parents)
    directories.discard(PurePosixPath("."))
    return files, directories


def public_target(site_root: Path, html_file: Path, path: str) -> Path | None:
    decoded = unquote(path)
    if decoded.startswith("/"):
        target = site_root / decoded.lstrip("/")
    else:
        target = html_file.parent / decoded
    try:
        resolved = target.resolve()
        resolved.relative_to(site_root.resolve())
    except (OSError, ValueError):
        return None

    if resolved.is_dir():
        resolved = resolved / "index.html"
    if resolved.exists():
        return resolved
    if resolved.suffix == "":
        html_target = resolved.with_suffix(".html")
        if html_target.exists():
            return html_target
        index_target = resolved / "index.html"
        if index_target.exists():
            return index_target
    return None


def relative_output_path(site_root: Path, html_file: Path, path: str) -> PurePosixPath | None:
    decoded = unquote(path)
    target = site_root / decoded.lstrip("/") if decoded.startswith("/") else html_file.parent / decoded
    try:
        relative = target.resolve().relative_to(site_root.resolve())
    except (OSError, ValueError):
        return None
    return PurePosixPath(relative.as_posix())


def repository_candidate(
    site_root: Path,
    html_file: Path,
    path: str,
    tracked_files: set[PurePosixPath],
    tracked_directories: set[PurePosixPath],
) -> tuple[PurePosixPath, bool] | None:
    relative = relative_output_path(site_root, html_file, path)
    if relative is None or not relative.parts:
        return None

    candidate: PurePosixPath | None = None
    if relative.parts[0] in REPOSITORY_EVIDENCE_ROOTS:
        candidate = relative
    elif relative.parts[0] == "articles":
        analysis_relative = relative.relative_to("articles")
        candidate = PurePosixPath("analysis") / analysis_relative

    if candidate in tracked_files:
        return candidate, False
    if candidate in tracked_directories:
        return candidate, True
    return None


def repository_url(
    repository: str,
    branch: str,
    candidate: PurePosixPath,
    is_directory: bool,
    query: str,
    fragment: str,
) -> str:
    view = "tree" if is_directory else "blob"
    path = f"{repository.rstrip('/')}/{view}/{quote(branch, safe='')}/{quote(candidate.as_posix(), safe='/')}"
    return urlunsplit(("https", urlsplit(path).netloc, urlsplit(path).path, query, fragment))


def rewrite_url(
    site_root: Path,
    html_file: Path,
    value: str,
    repository: str,
    branch: str,
    tracked_files: set[PurePosixPath],
    tracked_directories: set[PurePosixPath],
) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith(("#", "//")) or not parsed.path:
        return None
    if public_target(site_root, html_file, parsed.path) is not None:
        return None

    candidate = repository_candidate(
        site_root,
        html_file,
        parsed.path,
        tracked_files,
        tracked_directories,
    )
    if candidate is None:
        return None
    repository_path, is_directory = candidate
    return repository_url(
        repository,
        branch,
        repository_path,
        is_directory,
        parsed.query,
        parsed.fragment,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_dir", type=Path)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY_URL") or default_repository_url(),
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("SITE_VERSION_BRANCH") or version(),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    site_root = args.site_dir.resolve()
    if not site_root.is_dir():
        raise SystemExit(f"Built site directory does not exist: {site_root}")

    html_files = sorted(site_root.rglob("*.html"))
    if not html_files:
        raise SystemExit(f"No HTML files found under {site_root}")
    tracked_files, tracked_directories = tracked_repository_paths()

    rewritten = 0
    touched = 0
    for html_file in html_files:
        original = html_file.read_text(encoding="utf-8")
        soup = BeautifulSoup(original, "html.parser")
        file_rewrites = 0
        for tag_name, attributes in URL_ATTRIBUTES.items():
            for tag in soup.find_all(tag_name):
                for attribute in attributes:
                    value = tag.get(attribute)
                    if not isinstance(value, str):
                        continue
                    replacement = rewrite_url(
                        site_root,
                        html_file,
                        value,
                        args.repository,
                        args.branch,
                        tracked_files,
                        tracked_directories,
                    )
                    if replacement is None:
                        continue
                    tag[attribute] = replacement
                    if tag_name == "a":
                        classes = list(tag.get("class", []))
                        if "repo-evidence" not in classes:
                            classes.append("repo-evidence")
                        tag["class"] = classes
                        tag["rel"] = "noopener"
                    rewritten += 1
                    file_rewrites += 1
        if file_rewrites:
            html_file.write_text(str(soup), encoding="utf-8")
            touched += 1

    print(f"Postprocessed {len(html_files)} HTML files: {rewritten} evidence links in {touched} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
