#!/usr/bin/env python3
"""Validate the built multi-page Claude Code research site."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from site_identity import version


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTENT = REPO_ROOT / ".site-content"
LOCAL_PATH_PATTERNS = {
    "macOS user path": re.compile(r"(?:file://)?/Users/[A-Za-z0-9._-]+"),
    "macOS temporary path": re.compile(r"/(?:private/)?var/folders/[A-Za-z0-9_./-]+"),
    "Windows user path": re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s<>'\"]+", re.IGNORECASE),
    "encoded macOS user path": re.compile(r"%2fUsers%2f[^%\s<>'\"]+", re.IGNORECASE),
}
INTERNAL_ATTRIBUTES = {
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
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".map", ".svg", ".txt", ".xml"}


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks = 0

    def require(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_page(site_root: Path, relative_without_suffix: PurePosixPath) -> Path | None:
    direct = site_root / f"{relative_without_suffix.as_posix()}.html"
    if direct.is_file():
        return direct
    index = site_root / relative_without_suffix / "index.html"
    if index.is_file():
        return index
    return None


def normalize_site_path(site_root: Path, html_file: Path, url_path: str) -> Path | None:
    decoded = unquote(url_path)
    if decoded.startswith("/"):
        candidates = [site_root / decoded.lstrip("/")]
        parts = [part for part in PurePosixPath(decoded).parts if part not in {"/", ""}]
        if parts and parts[0] == "claudecodecli-sourcecode":
            candidates.append(site_root.joinpath(*parts[1:]))
    else:
        candidates = [html_file.parent / decoded]

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(site_root.resolve())
        except (OSError, ValueError):
            continue
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


def load_manifest(content_root: Path, validation: Validation) -> dict[str, object]:
    manifest_path = content_root / ".site-manifest.json"
    validation.require(manifest_path.is_file(), f"Missing generated manifest: {manifest_path}")
    if not manifest_path.is_file():
        return {"articles": [], "visuals": [], "curated_pages": []}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        validation.errors.append(f"Invalid generated manifest: {error}")
        return {"articles": [], "visuals": [], "curated_pages": []}
    validation.require(manifest.get("schema") == 1, "Unsupported generated manifest schema")
    return manifest


def validate_pages(
    site_root: Path,
    content_root: Path,
    manifest: dict[str, object],
    validation: Validation,
) -> tuple[list[Path], dict[str, Path]]:
    html_files = sorted(site_root.rglob("*.html"))
    articles = list(manifest.get("articles", []))
    validation.require(bool(html_files), "Built site has no HTML pages")
    validation.require(
        len(html_files) >= len(articles) + 5,
        f"Expected a real multi-page site with at least {len(articles) + 5} HTML pages, found {len(html_files)}",
    )
    validation.require((site_root / "index.html").is_file(), "Missing site homepage index.html")

    for page_name in ("articles", "project"):
        validation.require(find_page(site_root, PurePosixPath(page_name)) is not None, f"Missing {page_name} page")

    for item in manifest.get("identifier_indexes", []):
        relative = PurePosixPath(str(item["output"])).with_suffix("")
        validation.require(
            find_page(site_root, relative) is not None,
            f"Missing identifier search page: {relative}",
        )

    article_pages: dict[str, Path] = {}
    for item in articles:
        source = Path(str(item["source"]))
        stem = source.stem
        page = find_page(site_root, PurePosixPath("articles") / stem)
        validation.require(page is not None, f"Missing rendered article HTML: articles/{stem}")
        if page is None:
            continue
        article_pages[stem] = page
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        main = soup.find("main") or soup.find("article")
        validation.require(main is not None, f"Article has no semantic main region: {page.relative_to(site_root)}")
        validation.require(soup.find("h1") is not None, f"Article has no H1: {page.relative_to(site_root)}")
        readable = main.get_text(" ", strip=True) if main else ""
        validation.require(len(readable) >= 200, f"Article rendered too little readable text: {page.relative_to(site_root)}")

    index_page = find_page(site_root, PurePosixPath("articles"))
    if index_page is not None:
        soup = BeautifulSoup(index_page.read_text(encoding="utf-8"), "html.parser")
        main = soup.find("main") or soup.find("article")
        hrefs = {
            str(tag.get("href", ""))
            for tag in (main.find_all("a") if main is not None else [])
        }
        generated_index = (content_root / "articles.md").read_text(encoding="utf-8")
        indexed_stems = set(
            re.findall(
                r"\]\(articles/([^/#?]+)\.md(?:[#?][^)]*)?\)",
                generated_index,
            )
        )
        validation.require(
            indexed_stems == set(article_pages),
            "Article index coverage differs from rendered articles: "
            f"missing={sorted(set(article_pages) - indexed_stems)}, "
            f"extra={sorted(indexed_stems - set(article_pages))}",
        )
        for stem in indexed_stems:
            validation.require(stem in article_pages, f"Article index points to an unpublished article: {stem}")
            validation.require(
                any(f"articles/{stem}" in href or f"{stem}.html" in href for href in hrefs),
                f"Article index does not link to articles/{stem}",
            )

    return html_files, article_pages


def validate_links(
    site_root: Path,
    html_files: list[Path],
    validation: Validation,
    branch: str,
    repository: str,
    tracked_files: set[PurePosixPath],
    tracked_directories: set[PurePosixPath],
) -> None:
    anchor_cache: dict[Path, set[str]] = {}
    evidence_links = 0

    for html_file in html_files:
        soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
        for tag_name, attributes in INTERNAL_ATTRIBUTES.items():
            for tag in soup.find_all(tag_name):
                for attribute in attributes:
                    value = tag.get(attribute)
                    if not isinstance(value, str) or not value or value.startswith(("data:", "mailto:", "tel:", "javascript:")):
                        continue
                    parsed = urlsplit(value)
                    if parsed.scheme in {"http", "https"} or parsed.netloc:
                        if f"{repository.rstrip('/')}/" in value and any(
                            f"/{root}/" in value for root in ("analysis", "extracted", "reconstructed", "reverse", "skill")
                        ):
                            evidence_links += 1
                            validation.require(
                                f"/{branch}/" in parsed.path and ("/blob/" in parsed.path or "/tree/" in parsed.path),
                                f"Evidence link is not version-pinned: {value}",
                            )
                            marker = f"/{branch}/"
                            if marker in parsed.path:
                                repository_path = unquote(parsed.path.split(marker, 1)[1])
                                validation.require(
                                    PurePosixPath(repository_path) in tracked_files
                                    or PurePosixPath(repository_path) in tracked_directories,
                                    f"Evidence link target is absent from repository: {value}",
                                )
                        continue

                    target = normalize_site_path(site_root, html_file, parsed.path) if parsed.path else html_file
                    validation.require(
                        target is not None,
                        f"Broken internal {attribute}: {html_file.relative_to(site_root)} -> {value}",
                    )
                    if target is None or not parsed.fragment or target.suffix.lower() != ".html":
                        continue
                    if target not in anchor_cache:
                        target_soup = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
                        anchor_cache[target] = {
                            str(node.get("id")) for node in target_soup.find_all(attrs={"id": True})
                        }
                    fragment = unquote(parsed.fragment)
                    if fragment not in anchor_cache[target]:
                        validation.warn(f"Stale source anchor: {html_file.relative_to(site_root)} -> {value}")

    validation.require(evidence_links > 100, f"Expected version-pinned repository evidence links, found {evidence_links}")


def validate_visuals(site_root: Path, manifest: dict[str, object], validation: Validation) -> None:
    visuals = list(manifest.get("visuals", []))
    validation.require(len(visuals) >= 50, f"Expected at least 50 visual assets, found {len(visuals)}")
    for item in visuals:
        deployed = site_root / str(item["output"])
        validation.require(deployed.is_file(), f"Missing deployed SVG: {item['output']}")
        if deployed.is_file():
            validation.require(
                sha256(deployed) == str(item["sha256"]),
                f"Deployed SVG differs from source: {item['output']}",
            )

    mermaid = manifest.get("mermaid", {})
    mermaid_path = site_root / str(mermaid.get("output", ""))
    validation.require(mermaid_path.is_file(), "Missing deployed Mermaid runtime")
    if mermaid_path.is_file():
        validation.require(
            sha256(mermaid_path) == str(mermaid.get("sha256", "")),
            "Deployed Mermaid runtime checksum differs from the pinned asset",
        )

    external_scripts: list[str] = []
    csp_documents = 0
    for html_file in site_root.rglob("*.html"):
        soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
        csp = soup.find(
            "meta",
            attrs={"http-equiv": re.compile(r"^content-security-policy$", re.IGNORECASE)},
        )
        if csp is not None:
            csp_documents += 1
            policy = str(csp.get("content", ""))
            validation.require(
                "script-src 'self'" in policy and "https:" not in policy and "http:" not in policy,
                f"Page CSP does not keep runtime scripts local: {html_file.relative_to(site_root)}",
            )
        external_scripts.extend(
            str(script.get("src"))
            for script in soup.find_all("script", src=True)
            if str(script.get("src")).startswith(("http://", "https://"))
        )
    validation.require(
        not external_scripts,
        f"Site contains runtime third-party scripts: {sorted(set(external_scripts))}",
    )
    validation.require(
        csp_documents == len(list(site_root.rglob("*.html"))),
        "Content Security Policy is missing from one or more HTML pages",
    )


def validate_search(
    site_root: Path,
    manifest: dict[str, object],
    article_pages: dict[str, Path],
    validation: Validation,
) -> None:
    search_path = site_root / "search" / "search_index.json"
    validation.require(search_path.is_file(), "Missing search/search_index.json")
    if not search_path.is_file():
        return
    try:
        payload = json.loads(search_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        validation.errors.append(f"Invalid search index JSON: {error}")
        return

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    validation.require(isinstance(docs, list) and len(docs) > 20, "Search index contains too few documents")
    locations = [str(doc.get("location", "")) for doc in docs if isinstance(doc, dict)]
    searchable_text = json.dumps(payload, ensure_ascii=False)

    for item in manifest.get("articles", []):
        stem = Path(str(item["source"])).stem
        if stem not in article_pages:
            continue
        present = any(f"articles/{stem}" in location for location in locations)
        if bool(item.get("search_excluded")):
            validation.require(not present, f"Oversized reference leaked into search index: {stem}")
        else:
            validation.require(present, f"Article missing from search index: {stem}")

    for item in manifest.get("identifier_indexes", []):
        stem = Path(str(item["output"])).stem
        validation.require(
            any(f"search/{stem}" in location for location in locations),
            f"Identifier index is missing from search: {stem}",
        )
        for sample in item.get("samples", []):
            validation.require(
                str(sample) in searchable_text,
                f"Search index is missing identifier sample: {sample}",
            )


def validate_privacy(site_root: Path, validation: Validation) -> None:
    for path in sorted(site_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in LOCAL_PATH_PATTERNS.items():
            match = pattern.search(text)
            validation.require(
                match is None,
                f"Private {label} leaked into {path.relative_to(site_root)}: {match.group(0) if match else ''}",
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--branch")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    site_root = args.site_dir.resolve()
    validation = Validation()
    validation.require(site_root.is_dir(), f"Built site directory does not exist: {site_root}")
    if not site_root.is_dir():
        for error in validation.errors:
            print(f"ERROR: {error}")
        return 1

    manifest = load_manifest(args.content.resolve(), validation)
    branch = args.branch or str(manifest.get("branch") or version())
    repository = str(manifest.get("repository", ""))
    validation.require(bool(repository), "Generated manifest is missing repository identity")
    tracked_files, tracked_directories = tracked_repository_paths()
    html_files, article_pages = validate_pages(site_root, args.content.resolve(), manifest, validation)
    validate_links(
        site_root,
        html_files,
        validation,
        branch,
        repository,
        tracked_files,
        tracked_directories,
    )
    validate_visuals(site_root, manifest, validation)
    validate_search(site_root, manifest, article_pages, validation)
    validate_privacy(site_root, validation)

    if validation.errors:
        print(f"Site validation failed: {len(validation.errors)} errors across {validation.checks} checks")
        for error in validation.errors:
            print(f"ERROR: {error}")
        return 1

    if validation.warnings:
        print(f"Site validation warnings: {len(validation.warnings)}")
        for warning in validation.warnings[:20]:
            print(f"WARNING: {warning}")
        if len(validation.warnings) > 20:
            print(f"WARNING: {len(validation.warnings) - 20} additional warnings omitted")
    print(
        f"Site validation passed: {len(html_files)} HTML pages, "
        f"{len(article_pages)} articles, {validation.checks} checks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
