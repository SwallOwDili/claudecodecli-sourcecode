#!/usr/bin/env python3
"""Build the generated Markdown tree consumed by MkDocs."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from site_identity import repository_url, version


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".site-content"
SEARCH_EXCLUDE_MIN_BYTES = 250_000
LAB_BUNDLE_MAX_GZIP_BYTES = 50 * 1024
MERMAID_VERSION = "11.17.1"
MERMAID_URL = (
    f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
)
MERMAID_SHA256 = "b7a4cda9e88e187d4e1f279b8a14a3df651edd8dc704b9b56ed8e84659735570"
MARKDOWN_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\n]*?\]\()"
    r"(?P<open><)?(?P<url>[^\s)>]+)(?(open)>)"
    r"(?P<suffix>(?:\s+(?:\"[^\"]*\"|'[^']*'))?\))"
)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
TABLE_CODE_IDENTIFIER_RE = re.compile(r"^\|\s*<code>([^<]+)</code>\s*\|")
DETAIL_IDENTIFIER_RE = re.compile(r"^<summary><code>([^:<]+):")
IDENTIFIER_INDEXES = (
    {
        "name": "environment",
        "source": "environment-variable-reference.md",
        "title": "Environment 静态名称索引",
        "start": "## 842 个 typed 环境变量逐项参考",
        "end": None,
        "patterns": (TABLE_CODE_IDENTIFIER_RE,),
        "allowed": re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$"),
        "expected_count": 979,
        "samples": (
            "CLAUDE_CODE_MAX_TURNS",
            "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS",
            "CLAUDE_BG_SOCKET_TOKENS_PATH",
        ),
    },
    {
        "name": "feature",
        "source": "feature-flag-reference.md",
        "title": "Feature Key 标识符索引",
        "start": "## 361 个 static feature key 逐项参考",
        "end": "## 11 个 assignment-resolved",
        "patterns": (TABLE_CODE_IDENTIFIER_RE,),
        "allowed": re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$"),
        "expected_count": 361,
        "samples": ("tengu_amber_packet",),
    },
    {
        "name": "telemetry",
        "source": "telemetry-event-catalog.md",
        "title": "Telemetry Event 标识符索引",
        "start": "## 43 个一方动态事件名调用点",
        "end": "## Datadog forwarding 目录",
        "patterns": (DETAIL_IDENTIFIER_RE, TABLE_CODE_IDENTIFIER_RE),
        "allowed": re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$"),
        "expected_count": 1441,
        "samples": ("tengu_agent_color_set",),
    },
)
SUPPLEMENTAL_ARTICLE_GROUPS = (
    (
        "站点补充机制",
        (
            "prompt-assembly-and-system-reminders.md",
            "client-data-flow-and-privacy.md",
            "settings-resolution-and-reload.md",
        ),
    ),
    (
        "版本与公开证据",
        (
            "release-notes.md",
            "public-source-excerpts.md",
        ),
    ),
)
DETAILS_RE = re.compile(r"<details(?![^>]*\bmarkdown\s*=)([^>]*)>")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_mermaid(output_root: Path) -> dict[str, str]:
    cache_path = REPO_ROOT / ".site-cache" / f"mermaid-{MERMAID_VERSION}.min.js"
    if not cache_path.is_file() or sha256(cache_path) != MERMAID_SHA256:
        request = Request(MERMAID_URL, headers={"User-Agent": "claude-code-pages-builder"})
        with urlopen(request, timeout=60) as response:
            content = response.read()
        actual = hashlib.sha256(content).hexdigest()
        if actual != MERMAID_SHA256:
            raise SystemExit(
                f"Mermaid checksum mismatch: expected {MERMAID_SHA256}, got {actual}"
            )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(cache_path)

    destination = output_root / "assets" / "javascripts" / "mermaid.min.js"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_path, destination)
    return {
        "version": MERMAID_VERSION,
        "source": MERMAID_URL,
        "output": destination.relative_to(output_root).as_posix(),
        "sha256": MERMAID_SHA256,
    }


def install_lab_runtime(output_root: Path) -> dict[str, object]:
    source = REPO_ROOT / ".site-cache" / "labs" / "cc-agent-lab.js"
    if not source.is_file():
        raise SystemExit(
            "Missing interactive lab bundle; run `npm ci` and `npm run build:labs` first"
        )
    content = source.read_bytes()
    gzip_bytes = len(gzip.compress(content, compresslevel=9, mtime=0))
    if gzip_bytes > LAB_BUNDLE_MAX_GZIP_BYTES:
        raise SystemExit(
            f"Interactive lab bundle exceeds gzip budget: "
            f"{gzip_bytes} > {LAB_BUNDLE_MAX_GZIP_BYTES}"
        )

    destination = output_root / "assets" / "labs" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "output": destination.relative_to(output_root).as_posix(),
        "bytes": len(content),
        "gzipBytes": gzip_bytes,
        "sha256": hashlib.sha256(content).hexdigest(),
        "budgetGzipBytes": LAB_BUNDLE_MAX_GZIP_BYTES,
    }


def with_url_path(url: str, path: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def rewrite_target(url: str, document_kind: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc or url.startswith(("#", "/")):
        return url

    path = parsed.path
    if not path:
        return url

    normalized = PurePosixPath(path).as_posix()

    if (
        document_kind == "article"
        and normalized == "product-surface-evidence-map.md"
        and parsed.fragment == "把-cqeso-留作阅读索引"
    ):
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                normalized,
                parsed.query,
                "折叠证据附录",
            )
        )

    if document_kind == "article":
        if normalized.endswith(".svg") and normalized.startswith(
            ("visuals/", "analysis/visuals/", "../analysis/visuals/")
        ):
            name = normalized.split("visuals/", 1)[1]
            return with_url_path(url, f"../assets/visuals/{name}")
        if normalized.startswith("analysis/") and normalized.endswith(".md"):
            return with_url_path(url, normalized.removeprefix("analysis/"))
        if normalized.startswith("../analysis/") and normalized.endswith(".md"):
            return with_url_path(url, normalized.removeprefix("../analysis/"))
        root_name = normalized.removeprefix("../")
        if root_name in {"ARTICLES.md", "README.md"}:
            return with_url_path(url, "../articles.md")
        if root_name == "SNAPSHOT.md":
            return with_url_path(url, "../project.md")
        return url

    if normalized.startswith("analysis/visuals/"):
        return with_url_path(url, normalized.replace("analysis/visuals/", "assets/visuals/", 1))
    if normalized.startswith("analysis/") and normalized.endswith(".md"):
        return with_url_path(url, normalized.replace("analysis/", "articles/", 1))
    if normalized in {"ARTICLES.md", "README.md"}:
        return with_url_path(url, "articles.md")
    if normalized == "SNAPSHOT.md":
        return with_url_path(url, "project.md")
    return url


def rewrite_markdown(text: str, document_kind: str) -> str:
    output: list[str] = []
    active_fence: str | None = None

    for line in text.splitlines(keepends=True):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)[0]
            if active_fence is None:
                active_fence = marker
            elif active_fence == marker:
                active_fence = None
            output.append(line)
            continue

        if active_fence is not None:
            output.append(line)
            continue

        def replace(match: re.Match[str]) -> str:
            rewritten = rewrite_target(match.group("url"), document_kind)
            opening = "<" if match.group("open") else ""
            closing = ">" if match.group("open") else ""
            return f"{match.group('prefix')}{opening}{rewritten}{closing}{match.group('suffix')}"

        output.append(MARKDOWN_LINK_RE.sub(replace, line))

    return "".join(output)


def add_search_exclusion(text: str) -> str:
    front_matter = "---\nsearch:\n  exclude: true\n---\n\n"
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            body = text[4:end]
            if re.search(r"(?m)^search\s*:", body):
                return text
            return f"---\n{body}\nsearch:\n  exclude: true\n---\n{text[end + 5:]}"
    return front_matter + text


def first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ")


def complete_article_index(index_path: Path, article_sources: list[Path]) -> list[str]:
    text = index_path.read_text(encoding="utf-8")
    missing = [
        source
        for source in article_sources
        if f"articles/{source.name}" not in text
    ]
    if not missing:
        return []

    allowed = {
        name
        for _group, names in SUPPLEMENTAL_ARTICLE_GROUPS
        for name in names
    }
    actual = {source.name for source in missing}
    if actual != allowed:
        raise SystemExit(
            "Unclassified article-index drift: "
            f"missing={sorted(actual - allowed)}, stale={sorted(allowed - actual)}"
        )

    lines = [
        "",
        "## 站点补充专题",
        "",
        "这些页面同样来自当前版本分析，但不在历史 `ARTICLES.md` 的原始分组中；站点按明确用途补入，新增页面未分类时构建会失败。",
        "",
    ]
    sources_by_name = {source.name: source for source in missing}
    for group, names in SUPPLEMENTAL_ARTICLE_GROUPS:
        lines.extend((f"### {group}", ""))
        lines.extend(
            f"- [{first_heading(sources_by_name[name])}](articles/{name})"
            for name in names
        )
        lines.append("")
    index_path.write_text(
        text.rstrip() + "\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return [source.name for source in missing]


def extract_identifiers(
    source: Path,
    start: str,
    end: str | None,
    patterns: tuple[re.Pattern[str], ...],
    allowed: re.Pattern[str],
) -> list[str]:
    text = source.read_text(encoding="utf-8")
    start_at = text.find(start)
    if start_at < 0:
        raise SystemExit(f"Identifier index start marker is missing: {source} / {start}")

    end_at = text.find(end, start_at + len(start)) if end else -1
    body = text[start_at:] if end_at < 0 else text[start_at:end_at]

    identifiers: set[str] = set()
    for line in body.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match is None:
                continue
            value = html.unescape(match.group(1)).strip()
            if allowed.fullmatch(value):
                identifiers.add(value)
            break
    return sorted(identifiers, key=str.casefold)


def write_identifier_indexes(output_root: Path) -> list[dict[str, object]]:
    generated: list[dict[str, object]] = []
    for spec in IDENTIFIER_INDEXES:
        source = REPO_ROOT / "analysis" / str(spec["source"])
        identifiers = extract_identifiers(
            source,
            str(spec["start"]),
            str(spec["end"]) if spec["end"] else None,
            spec["patterns"],
            spec["allowed"],
        )
        if len(identifiers) != int(spec["expected_count"]):
            raise SystemExit(
                f"Identifier index {spec['name']} count mismatch: "
                f"{len(identifiers)} != {spec['expected_count']}"
            )
        missing_samples = sorted(set(spec["samples"]) - set(identifiers))
        if missing_samples:
            raise SystemExit(
                f"Identifier index {spec['name']} misses required samples: {missing_samples}"
            )

        destination = output_root / "search" / f"{spec['name']}-identifiers.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        article_target = f"../articles/{spec['source']}"
        lines = [
            "---",
            "hide:",
            "  - toc",
            "---",
            "",
            f"# {spec['title']}",
            "",
            "这是一份用于站内精确搜索的轻量索引。字段语义、consumer、失败路径和证据边界仍以完整参考页为准。",
            "",
            f"[打开完整参考]({article_target})",
            "",
        ]
        current_group = ""
        for identifier in identifiers:
            group = identifier[0].upper() if identifier[0].isalnum() else "其他"
            if group != current_group:
                lines.extend((f"## {group}", ""))
                current_group = group
            lines.extend(
                (
                    f"### `{identifier}`",
                    "",
                    f"[在完整参考中查看]({article_target})",
                    "",
                )
            )
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        generated.append(
            {
                "name": spec["name"],
                "source": source.relative_to(REPO_ROOT).as_posix(),
                "output": destination.relative_to(output_root).as_posix(),
                "count": len(identifiers),
                "samples": list(spec["samples"]),
            }
        )
    return generated


def write_markdown(source: Path, destination: Path, document_kind: str, exclude_search: bool = False) -> None:
    text = source.read_text(encoding="utf-8")
    text = rewrite_markdown(text, document_kind)
    text = DETAILS_RE.sub(r'<details markdown="1"\1>', text)
    if exclude_search:
        text = add_search_exclusion(text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def copy_curated_pages(source_root: Path, output_root: Path) -> list[str]:
    if not source_root.is_dir():
        raise SystemExit(f"Missing curated page directory: {source_root}")

    copied: list[str] = []
    for source in sorted(source_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        destination = output_root / relative
        if destination.exists():
            raise SystemExit(f"Curated page collision: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".md":
            write_markdown(source, destination, "root")
        else:
            shutil.copy2(source, destination)
        copied.append(relative.as_posix())

    if not any(path.endswith(".md") for path in copied):
        raise SystemExit(f"No curated Markdown pages found in {source_root}")
    return copied


def reset_output(output_root: Path) -> None:
    resolved = output_root.resolve()
    repo = REPO_ROOT.resolve()
    if resolved == repo or repo not in resolved.parents:
        raise SystemExit(f"Refusing to clear output outside repository: {resolved}")
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output.resolve()
    reset_output(output_root)

    curated_pages = copy_curated_pages(REPO_ROOT / "site" / "pages", output_root)

    assets_source = REPO_ROOT / "site" / "assets"
    if assets_source.is_dir():
        shutil.copytree(assets_source, output_root / "assets", dirs_exist_ok=True)
    mermaid = install_mermaid(output_root)
    lab_runtime = install_lab_runtime(output_root)

    root_documents = {
        "ARTICLES.md": "articles.md",
        "SNAPSHOT.md": "project.md",
    }
    for source_name, destination_name in root_documents.items():
        source = REPO_ROOT / source_name
        if not source.is_file():
            raise SystemExit(f"Missing root source document: {source}")
        destination = output_root / destination_name
        if destination.exists():
            raise SystemExit(f"Generated root document collides with curated page: {destination_name}")
        write_markdown(source, destination, "root")

    article_sources = sorted((REPO_ROOT / "analysis").glob("*.md"))
    if not article_sources:
        raise SystemExit("No analysis Markdown articles found")

    supplemental_articles = complete_article_index(
        output_root / "articles.md",
        article_sources,
    )
    identifier_indexes = write_identifier_indexes(output_root)

    articles: list[dict[str, object]] = []
    for source in article_sources:
        exclude_search = source.stat().st_size >= SEARCH_EXCLUDE_MIN_BYTES
        destination = output_root / "articles" / source.name
        write_markdown(source, destination, "article", exclude_search=exclude_search)
        articles.append(
            {
                "source": source.relative_to(REPO_ROOT).as_posix(),
                "output": destination.relative_to(output_root).as_posix(),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
                "search_excluded": exclude_search,
            }
        )

    visual_sources = sorted((REPO_ROOT / "analysis" / "visuals").glob("*.svg"))
    if not visual_sources:
        raise SystemExit("No analysis SVG visuals found")

    visual_root = output_root / "assets" / "visuals"
    visual_root.mkdir(parents=True, exist_ok=True)
    visuals: list[dict[str, str]] = []
    for source in visual_sources:
        destination = visual_root / source.name
        if destination.exists():
            raise SystemExit(f"Visual asset collision: {destination}")
        shutil.copy2(source, destination)
        visuals.append(
            {
                "source": source.relative_to(REPO_ROOT).as_posix(),
                "output": destination.relative_to(output_root).as_posix(),
                "sha256": sha256(source),
            }
        )

    manifest = {
        "schema": 1,
        "branch": version(),
        "repository": repository_url(),
        "curated_pages": curated_pages,
        "root_documents": root_documents,
        "supplemental_articles": supplemental_articles,
        "identifier_indexes": identifier_indexes,
        "lab_runtime": lab_runtime,
        "mermaid": mermaid,
        "articles": articles,
        "visuals": visuals,
    }
    (output_root / ".site-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    excluded = sum(bool(article["search_excluded"]) for article in articles)
    print(
        f"Prepared {output_root}: {len(curated_pages)} curated files, "
        f"{len(articles)} articles ({excluded} excluded from search), "
        f"{len(visuals)} SVG visuals"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
