#!/usr/bin/env python3
"""Extract deterministic, cross-version inventories from the packed CLI bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
ENV_PROCESS_RE = re.compile(
    rb"process\.env(?:\.([A-Z][A-Z0-9_]{2,})|\[['\"]([A-Z][A-Z0-9_]{2,})['\"]\])"
)
ENV_PROXY_RE = re.compile(rb"\bK\.([A-Z][A-Z0-9_]{2,})\b")
ENV_PREFIX_RE = re.compile(
    rb"\b(?:ANTHROPIC|CLAUDE|OTEL|AWS|GOOGLE|VERTEX|MCP|BASH|SWE_BENCH|"
    rb"DISABLE|ENABLE|FORCE|USE|MAX|DEBUG|DD|DATADOG|SENTRY|HTTP|HTTPS|NO_PROXY)"
    rb"_[A-Z][A-Z0-9_]{1,}\b"
)
STATIC_ASSIGNMENT_RE = re.compile(
    rb"\b[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*['\"]([A-Za-z][A-Za-z0-9_.:-]{1,80})['\"]"
)
NAMED_COMPONENT_RE = re.compile(
    rb"\bname\s*:\s*['\"]([^'\"\r\n]{1,100})['\"]\s*,\s*"
    rb"(?:title\s*:\s*['\"][^'\"\r\n]{1,200}['\"]\s*,\s*)?description\s*:"
)
SLASH_COMMAND_RE = re.compile(
    rb"\{(?=[^{}]{0,800}\btype:['\"](?:local|local-jsx|prompt)['\"])"
    rb"(?=[^{}]{0,800}\bname:['\"]([a-z][a-z0-9-]*)['\"])[^{}]{0,800}"
)
SCHEMA_PROPERTY_RE = re.compile(
    rb"\b([A-Za-z_$][A-Za-z0-9_$]{0,100})\s*:\s*"
    rb"(?:N|rt|jt|mt|ye|li|Nr|js|ao|wt|lv|SEn|tct|K0)\("
)
STORAGE_NAMESPACE_RE = re.compile(
    rb"\bnamespace\s*:\s*['\"]([A-Za-z][A-Za-z0-9_-]{0,80})['\"]"
)
CLAUDE_STORAGE_FACTORY_START_RE = re.compile(
    rb"\btranscript\s*:\s*[A-Za-z_$][A-Za-z0-9_$]*\s*,\s*"
    rb"journal\s*:\s*.{0,500}?\bnamespace\s*:\s*['\"]transcript['\"]"
    rb".{0,500}?\bhistory\s*:\s*.{0,200}?\bnamespace\s*:\s*['\"]history['\"]"
    rb".{0,300}?\blog\s*:",
    re.DOTALL,
)
CLAUDE_STORAGE_FACTORY_END_RE = re.compile(rb"\bsessionAliases\s*:")
BETA_IDENTIFIER_RE = re.compile(rb"\b[a-z][a-z0-9-]{2,}-\d{4}-\d{2}-\d{2}\b")
PROTOCOL_EVENT_RE = re.compile(
    rb"\b(?:"
    rb"user\.(?:message|interrupt|tool_confirmation|tool_result|custom_tool_result|define_outcome)"
    rb"|agent\.(?:custom_tool_use|mcp_tool_result|mcp_tool_use|message|thinking|tool_result|tool_use|(?:session_)?thread_[a-z_]+)"
    rb"|session\.(?:archived|created|deleted|error|updated|usage|status_[a-z_]+|thread_[a-z_]+|outcome_evaluation_[a-z_]+)"
    rb"|span\.(?:model_request_[a-z_]+|outcome_evaluation_[a-z_]+)"
    rb")\b"
)
STATIC_ENUM_RE = re.compile(
    rb"\bNr\(\[((?:\s*['\"](?:\\.|[^'\"]){1,160}['\"]\s*,?)+)\]\)"
)
STATIC_EVENT_OBJECT_RE = re.compile(
    rb"\b(?P<function>H|Fv|Nd)\(\s*['\"](?P<event>[a-z][a-z0-9_.:-]+)['\"]\s*,\s*\{"
)
HOOK_EVENT_NAME_RE = re.compile(
    rb"\b(?:hook_event_name|hookEvent|hook_event)\s*:\s*['\"]([A-Za-z][A-Za-z0-9]+)['\"]"
)
TENGU_RE = re.compile(rb"\btengu_[a-z0-9_]+\b")
FIRST_PARTY_EVENT_RE = re.compile(
    rb"\b(?:H|Fv)\(\s*['\"]([a-z][a-z0-9_.:-]+)['\"]"
)
FIRST_PARTY_TEMPLATE_RE = re.compile(rb"\b(?:H|Fv)\(\s*`([^`]{1,300})`")
OTEL_EVENT_RE = re.compile(rb"\bNd\(\s*['\"]([a-z][a-z0-9_.:-]+)['\"]")
SPAN_RE = re.compile(
    rb"(?:startSpan|MIn|k9o)\(\s*['\"](claude_code\.[a-z0-9_.-]+)['\"]"
)
METRIC_RE = re.compile(
    rb'[A-Za-z_$][A-Za-z0-9_$]*\(\s*"(?P<name>claude_code\.[a-z0-9_.-]+)"\s*,\s*\{'
    rb'\s*description:\s*"(?P<description>(?:\\.|[^"])+)"'
    rb'(?:\s*,\s*unit:\s*[A-Za-z_$][A-Za-z0-9_$]*\("(?P<unit>[^"]+)"\))?'
)
FEATURE_FLAG_RE = re.compile(rb"\bet\(\s*['\"]([a-zA-Z0-9_.:-]+)['\"]")
GROWTHBOOK_KEY_RE = re.compile(rb"\bCB\(\s*['\"]([a-zA-Z0-9_.:-]+)['\"]")
MODEL_RE = re.compile(
    rb"\bclaude-(?:opus|sonnet|haiku|fable|mythos)(?:-[a-z0-9]+){1,8}\b"
)
CONTROL_SUBTYPE_RE = re.compile(rb"subtype:\s*wt\(\s*['\"]([a-z0-9_.:-]+)['\"]\s*\)")
HOOK_EVENT_RE = re.compile(
    rb"['\"](?:PreToolUse|PostToolUse|PostToolUseFailure|PermissionRequest|"
    rb"UserPromptSubmit|SessionStart|SessionEnd|Stop|SubagentStart|SubagentStop|"
    rb"PreCompact|Notification|ConfigChange|WorktreeCreate|WorktreeRemove|"
    rb"TeammateIdle|TaskCompleted)['\"]"
)
API_PATH_RE = re.compile(
    rb"['\"](/(?:api|v1|v2|oauth|mcp-registry|worker|managed|sessions|\.well-known)/"
    rb"[A-Za-z0-9_./{}:\[\]-]+)['\"]"
)
HTTP_ROUTE_RE = re.compile(
    rb"['\"]((?:GET|POST|PUT|PATCH|DELETE) /[A-Za-z0-9_./{}:\[\]-]+)['\"]"
)
REQUIRE_RE = re.compile(rb"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)")
SCHEMA_DESCRIPTION_RE = re.compile(
    rb"\.describe\(\s*['\"](?P<description>(?:\\.|[^'\"]){1,2000})['\"]\s*\)"
)
ERROR_MESSAGE_RE = re.compile(
    rb"(?:throw\s+)?(?:new\s+)?(?:Error|TypeError|RangeError)\(\s*"
    rb"['\"](?P<message>(?:\\.|[^'\"]){1,1000})['\"]"
)
DIAGNOSTIC_MESSAGE_RE = re.compile(
    rb"\bT\(\s*['\"](?P<message>(?:\\.|[^'\"]){1,1000})['\"]"
)
PERSONAL_PATH_RE = re.compile(
    rb"(?:/" + rb"Users/[^/\x00\r\n]+(?:/|$)|/" + rb"home/[^/\x00\r\n]+(?:/|$)|"
    rb"[A-Za-z]:\\Users\\[^\\\x00\r\n]+(?:\\|$))"
)
SECRET_RE = re.compile(
    rb"(?:sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    rb"AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,})"
)
IDENTIFIER_RE = re.compile(rb"^[A-Za-z_$][A-Za-z0-9_$]*$")
OBSERVABILITY_NAME_RE = re.compile(
    r"(?:OTEL|TELEMETR|DATADOG|DD_ERROR|DEBUG|DIAGNOSTIC|PROFILE|PERFETTO|"
    r"FRAME_TIMING|SESSION_LOG|TRANSCRIPT|TERMINAL_RECORDING|PTY_RECORD|"
    r"BENCH_LIVE_COUNTS|ANT_CLAUDE_CODE_METRICS_ENDPOINT)",
    re.IGNORECASE,
)
API_TEMPLATE_PREFIXES = (
    "/api/",
    "/v1/",
    "/v2/",
    "/oauth/",
    "/mcp-registry/",
    "/worker/",
    "/managed/",
    "/sessions/",
    "/.well-known/",
)

BUILTIN_TOOL_NAMES = {
    "Artifact",
    "AskUserQuestion",
    "Bash",
    "CronCreate",
    "CronDelete",
    "CronList",
    "Edit",
    "EnterPlanMode",
    "EnterWorktree",
    "ExitPlanMode",
    "ExitWorktree",
    "Glob",
    "Grep",
    "LSP",
    "NotebookEdit",
    "Read",
    "SendMessage",
    "Skill",
    "Task",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskUpdate",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Workflow",
    "Write",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode(value: bytes) -> str:
    text = value.decode("utf-8", errors="replace").replace("\r", "\\r").replace("\n", "\\n")
    trailing = re.search(r"[ \t]+$", text)
    if trailing:
        escaped = "".join("\\x20" if char == " " else "\\t" for char in trailing.group())
        text = text[: trailing.start()] + escaped
    return text


def write_lines(path: Path, values: set[str] | list[str]) -> int:
    ordered = sorted(set(values))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{value}\n" for value in ordered), encoding="utf-8")
    return len(ordered)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return len(rows)


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_identifier_start(value: int) -> bool:
    return chr(value).isalpha() or value in (36, 95)


def is_identifier_part(value: int) -> bool:
    return chr(value).isalnum() or value in (36, 95)


def skip_space(source: bytes, index: int, end: int | None = None) -> int:
    limit = len(source) if end is None else end
    while index < limit and source[index] in b" \t\r\n":
        index += 1
    return index


def trim_range(source: bytes, start: int, end: int) -> tuple[int, int]:
    while start < end and source[start] in b" \t\r\n":
        start += 1
    while end > start and source[end - 1] in b" \t\r\n":
        end -= 1
    return start, end


class LineLocator:
    def __init__(self, source: bytes):
        self.starts = [0]
        self.starts.extend(match.end() for match in re.finditer(rb"\n", source))

    def locate(self, offset: int) -> tuple[int, int]:
        line_index = bisect_right(self.starts, offset) - 1
        return line_index + 1, offset - self.starts[line_index] + 1


def safe_source_text(value: bytes, limit: int = 8192) -> dict[str, Any]:
    record: dict[str, Any] = {
        "length": len(value),
        "sha256": bytes_sha256(value),
    }
    if len(value) > limit:
        record["omitted"] = "length"
    elif PERSONAL_PATH_RE.search(value):
        record["omitted"] = "personal-path-shaped"
    elif SECRET_RE.search(value):
        record["omitted"] = "credential-shaped"
    else:
        record["text"] = decode(value)
    return record


def sanitize_human_text(value: str) -> str:
    value = re.sub(r"/" + r"Users/[^/\s]+", "$HOME", value)
    value = re.sub(r"/" + r"home/[^/\s]+", "$HOME", value)
    value = re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+", "$HOME", value)
    return value


def _unique_symbol(
    source: bytes,
    pattern: bytes,
    label: str,
    group: int = 1,
    flags: int = 0,
) -> str:
    matches = {
        decode(match.group(group))
        for match in re.finditer(pattern, source, flags)
    }
    if len(matches) != 1:
        raise ValueError(
            f"semantic symbol discovery for {label} expected one match, "
            f"found {sorted(matches)!r}"
        )
    return next(iter(matches))


def _nearest_symbol(
    source: bytes,
    pattern: bytes,
    label: str,
    anchor_offset: int,
    group: int = 1,
    flags: int = 0,
) -> str:
    matches = list(re.finditer(pattern, source, flags))
    if not matches:
        raise ValueError(f"semantic symbol discovery could not locate {label}")
    ranked = sorted(
        (abs(match.start() - anchor_offset), match.start(), decode(match.group(group)))
        for match in matches
    )
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        raise ValueError(
            f"semantic symbol discovery for {label} was ambiguous: {ranked[:5]!r}"
        )
    return ranked[0][2]


def discover_semantic_symbols(source: bytes) -> dict[str, Any]:
    identifier = rb"[A-Za-z_$][A-Za-z0-9_$]*"

    analytics = list(
        re.finditer(
            rb"logEvent:\(\)=>((?:" + identifier + rb")),"
            rb"logEventAsync:\(\)=>((?:" + identifier + rb"))",
            source,
        )
    )
    analytics_pairs = {
        (decode(match.group(1)), decode(match.group(2))) for match in analytics
    }
    if len(analytics_pairs) != 1:
        raise ValueError(
            "semantic symbol discovery for first-party analytics expected one "
            f"logEvent/logEventAsync pair, found {sorted(analytics_pairs)!r}"
        )
    first_party_event, first_party_event_async = next(iter(analytics_pairs))

    otel_event = _unique_symbol(
        source,
        rb"async function (" + identifier + rb")\(e,t=\{\},r\)\{"
        rb".{0,3000}?body:`claude_code\.\$\{e\}`",
        "third-party OTEL structured event",
        flags=re.DOTALL,
    )
    feature_value = _unique_symbol(
        source,
        rb"getFeatureValue_CACHED_MAY_BE_STALE:\(\)=>(" + identifier + rb")",
        "cached feature value",
    )
    dynamic_config = _unique_symbol(
        source,
        rb"getDynamicConfig_CACHED_MAY_BE_STALE:\(\)=>(" + identifier + rb")",
        "cached dynamic config",
    )
    diagnostic = _unique_symbol(
        source,
        rb"function (" + identifier + rb")\(e,t=\{level:\"debug\"\}\)\{"
        + identifier
        + rb"\(\)\.log\(e,t\)\}",
        "diagnostic logger",
    )
    environment_proxy = _unique_symbol(
        source,
        rb"readEnvironmentOverrides:\(\)=>(" + identifier + rb")\."
        rb"CLAUDE_INTERNAL_FC_OVERRIDES",
        "environment proxy",
    )

    export_variables: dict[str, set[str]] = defaultdict(set)
    for match in re.finditer(
        rb"\b([A-Z][A-Z0-9_]{2,}):\(\)=>(" + identifier + rb")",
        source,
    ):
        export_variables[decode(match.group(2))].add(decode(match.group(1)))
    environment_builder_matches: dict[str, set[str]] = defaultdict(set)
    for match in re.finditer(
        rb"\b(" + identifier + rb")\s*=\s*(" + identifier + rb")\."
        rb"(?:str|bool|triBool|int|enum)\(",
        source,
    ):
        variable = decode(match.group(1))
        builder = decode(match.group(2))
        if variable in export_variables:
            environment_builder_matches[builder].update(export_variables[variable])
    ranked_environment_builders = sorted(
        (
            (len(names), builder)
            for builder, names in environment_builder_matches.items()
        ),
        reverse=True,
    )
    if (
        not ranked_environment_builders
        or ranked_environment_builders[0][0] < 100
        or (
            len(ranked_environment_builders) > 1
            and ranked_environment_builders[0][0]
            == ranked_environment_builders[1][0]
        )
    ):
        raise ValueError(
            "semantic symbol discovery for environment schema builder was "
            f"ambiguous: {ranked_environment_builders[:5]!r}"
        )
    environment_schema_join_count, environment_builder = ranked_environment_builders[0]

    root_match = re.search(
        rb"function (" + identifier + rb")\(e,\{strictPolicyHelperKeys:[^)]*"
        rb"\}=\{\}\)\{.{0,5000}?return (" + identifier + rb")\(\{\$schema:",
        source,
        re.DOTALL,
    )
    if root_match is None:
        raise ValueError("semantic symbol discovery could not locate the root settings schema")
    root_settings_function = decode(root_match.group(1))
    object_builder = decode(root_match.group(2))
    object_builder_offset = source.find(f"function {object_builder}(".encode())
    if object_builder_offset < 0:
        raise ValueError("semantic symbol discovery could not locate object builder definition")

    enum_builder = _nearest_symbol(
        source,
        rb"function (" + identifier + rb")\(e,t\)\{let r=Array\.isArray\(e\)\?"
        rb"Object\.fromEntries\(e\.map\(\(n\)=>\[n,n\]\)\):e;return new "
        + identifier
        + rb"\(\{type:\"enum\",entries:r",
        "schema enum builder",
        object_builder_offset,
    )
    literal_builder = _nearest_symbol(
        source,
        rb"function (" + identifier + rb")\(e,t\)\{return new "
        + identifier
        + rb"\(\{type:\"literal\",values:Array\.isArray\(e\)\?e:\[e\]",
        "schema literal builder",
        object_builder_offset,
    )
    model_catalog = _unique_symbol(
        source,
        rb"\b(" + identifier + rb")=\{\"//\":\"Hand-maintained baked-in model catalog",
        "baked model catalog",
    )

    datadog_match = re.search(
        rb"(" + identifier + rb")=new Set\(\[\"tengu_feature_ok\""
        rb".{0,20000}?\]\),(" + identifier + rb")=\[\"arch\""
        rb".{0,5000}?\];(" + identifier + rb")=\[\"mcpServerName\""
        rb".{0,5000}?\],(" + identifier + rb")=new Set\(\3\.map",
        source,
        re.DOTALL,
    )
    if datadog_match is None:
        raise ValueError("semantic symbol discovery could not locate Datadog allowlists")
    datadog_allowlist = decode(datadog_match.group(1))
    datadog_tag_fields = decode(datadog_match.group(2))
    datadog_redacted_fields = decode(datadog_match.group(3))
    datadog_redacted_set = decode(datadog_match.group(4))

    user_config_match = re.search(
        rb"(" + identifier + rb")=\[(?:\"commands\",\"agents\"|"
        rb"\"agents\",\"commands\").{0,1000}?\],(" + identifier + rb")="
        rb"new Set\(\1\)",
        source,
        re.DOTALL,
    )
    if user_config_match is None:
        raise ValueError("semantic symbol discovery could not locate user config directories")
    user_config_directories_variable = decode(user_config_match.group(1))

    schema_window_start = max(0, object_builder_offset - 30000)
    schema_window_end = min(len(source), schema_window_start + 80000)
    schema_window = source[schema_window_start:schema_window_end]
    schema_builders: set[str] = {object_builder, enum_builder, literal_builder}
    for match in re.finditer(
        rb"function (" + identifier + rb")\([^)]*\)\{.{0,1600}?"
        rb"type:\"(?:array|bigint|boolean|date|enum|intersection|literal|number|object|"
        rb"optional|record|string|tuple|union)\"",
        schema_window,
        re.DOTALL,
    ):
        schema_builders.add(decode(match.group(1)))
    wrapper_edges = [
        (decode(match.group(1)), decode(match.group(2)))
        for match in re.finditer(
            rb"function ("
            + identifier
            + rb")\([^)]*\)\{return ("
            + identifier
            + rb")\(",
            schema_window,
        )
    ]
    changed = True
    while changed:
        changed = False
        for wrapper, callee in wrapper_edges:
            if callee in schema_builders and wrapper not in schema_builders:
                schema_builders.add(wrapper)
                changed = True

    role_symbols = {
        "firstPartyEvent": first_party_event,
        "firstPartyEventAsync": first_party_event_async,
        "otelStructuredEvent": otel_event,
        "featureValue": feature_value,
        "dynamicConfig": dynamic_config,
        "diagnostic": diagnostic,
    }
    if len(set(role_symbols.values())) != len(role_symbols):
        raise ValueError(f"semantic target symbols are not unique: {role_symbols!r}")

    return {
        "roles": role_symbols,
        "environmentProxy": environment_proxy,
        "environmentBuilder": environment_builder,
        "environmentSchemaJoinCount": environment_schema_join_count,
        "rootSettingsFunction": root_settings_function,
        "objectBuilder": object_builder,
        "enumBuilder": enum_builder,
        "literalBuilder": literal_builder,
        "modelCatalog": model_catalog,
        "datadogAllowlist": datadog_allowlist,
        "datadogTagFields": datadog_tag_fields,
        "datadogRedactedFields": datadog_redacted_fields,
        "datadogRedactedSet": datadog_redacted_set,
        "userConfigDirectoriesVariable": user_config_directories_variable,
        "schemaBuilders": sorted(schema_builders),
    }


def load_javascript_surface(
    source_path: Path, discovered: dict[str, Any]
) -> dict[str, Any]:
    helper = Path(__file__).with_name("parse_javascript_surface.mjs")
    node = shutil.which("node")
    bun = shutil.which("bun")
    if node:
        command = [
            node,
            "--max-old-space-size=4096",
            str(helper),
            str(source_path),
            json.dumps(
                {
                    "targetCallees": sorted(set(discovered["roles"].values())),
                    "environmentProxies": [discovered["environmentProxy"]],
                },
                separators=(",", ":"),
            ),
        ]
    elif bun:
        command = [
            bun,
            str(helper),
            str(source_path),
            json.dumps(
                {
                    "targetCallees": sorted(set(discovered["roles"].values())),
                    "environmentProxies": [discovered["environmentProxy"]],
                },
                separators=(",", ":"),
            ),
        ]
    else:
        raise RuntimeError("source inventory v3 requires node or bun for the vendored Acorn parser")
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "Acorn source parser failed: "
            + process.stderr.decode("utf-8", errors="replace").strip()
        )
    result = json.loads(process.stdout)
    parser = result.get("parser", {})
    if parser.get("name") != "acorn" or parser.get("version") != "8.15.0":
        raise RuntimeError(f"unexpected JavaScript parser metadata: {parser!r}")
    return result


def template_expression_ranges(
    source: bytes, opening: int
) -> tuple[int, list[tuple[int, int]]]:
    expressions: list[tuple[int, int]] = []
    index = opening + 1
    while index < len(source):
        current = source[index]
        if current == 92:
            index += 2
            continue
        if current == 96:
            return index + 1, expressions
        if current == 36 and index + 1 < len(source) and source[index + 1] == 123:
            closing = find_matching(source, index + 1)
            if closing < 0:
                return len(source), expressions
            expressions.append((index + 2, closing))
            index = closing + 1
            continue
        index += 1
    return len(source), expressions


def skip_template(source: bytes, index: int) -> int:
    end, _ = template_expression_ranges(source, index)
    return end


def static_values(pattern: re.Pattern[bytes], source: bytes, group: str | int = 1) -> set[str]:
    return {decode(match.group(group)) for match in pattern.finditer(source)}


def skip_quoted(source: bytes, index: int, quote: int) -> int:
    if quote == 96:
        return skip_template(source, index)
    index += 1
    while index < len(source):
        current = source[index]
        if current == 92:
            index += 2
            continue
        if current == quote:
            return index + 1
        index += 1
    return index


def split_top_level_ranges(
    source: bytes, start: int, end: int
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    item_start = start
    paren_depth = 0
    brace_depth = 0
    bracket_depth = 0
    index = start
    while index < end:
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < end:
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if current == 40:
            paren_depth += 1
        elif current == 41:
            paren_depth = max(0, paren_depth - 1)
        elif current == 123:
            brace_depth += 1
        elif current == 125:
            brace_depth = max(0, brace_depth - 1)
        elif current == 91:
            bracket_depth += 1
        elif current == 93:
            bracket_depth = max(0, bracket_depth - 1)
        elif (
            current == 44
            and paren_depth == 0
            and brace_depth == 0
            and bracket_depth == 0
        ):
            item = trim_range(source, item_start, index)
            if item[0] < item[1]:
                ranges.append(item)
            item_start = index + 1
        index += 1
    item = trim_range(source, item_start, end)
    if item[0] < item[1]:
        ranges.append(item)
    return ranges


def find_top_level_byte(source: bytes, start: int, end: int, target: int) -> int:
    paren_depth = 0
    brace_depth = 0
    bracket_depth = 0
    index = start
    while index < end:
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < end:
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if current == 40:
            paren_depth += 1
        elif current == 41:
            paren_depth = max(0, paren_depth - 1)
        elif current == 123:
            brace_depth += 1
        elif current == 125:
            brace_depth = max(0, brace_depth - 1)
        elif current == 91:
            bracket_depth += 1
        elif current == 93:
            bracket_depth = max(0, bracket_depth - 1)
        elif (
            current == target
            and paren_depth == 0
            and brace_depth == 0
            and bracket_depth == 0
        ):
            return index
        index += 1
    return -1


def scan_expression_end(source: bytes, start: int) -> int:
    paren_depth = 0
    brace_depth = 0
    bracket_depth = 0
    index = start
    while index < len(source):
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < len(source):
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if current == 40:
            paren_depth += 1
        elif current == 123:
            brace_depth += 1
        elif current == 91:
            bracket_depth += 1
        elif current == 41:
            if paren_depth == 0 and brace_depth == 0 and bracket_depth == 0:
                return trim_range(source, start, index)[1]
            paren_depth -= 1
        elif current == 125:
            if brace_depth == 0 and paren_depth == 0 and bracket_depth == 0:
                return trim_range(source, start, index)[1]
            brace_depth -= 1
        elif current == 93:
            if bracket_depth == 0 and paren_depth == 0 and brace_depth == 0:
                return trim_range(source, start, index)[1]
            bracket_depth -= 1
        elif (
            current in (44, 59)
            and paren_depth == 0
            and brace_depth == 0
            and bracket_depth == 0
        ):
            return trim_range(source, start, index)[1]
        index += 1
    return trim_range(source, start, len(source))[1]


def direct_call_identifiers(source: bytes) -> set[str]:
    values: set[str] = set()
    index = 0
    while index < len(source):
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < len(source):
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if not is_identifier_start(current):
            index += 1
            continue
        end = index + 1
        while end < len(source) and is_identifier_part(source[end]):
            end += 1
        cursor = skip_space(source, end)
        previous = index - 1
        while previous >= 0 and source[previous] in b" \t\r\n":
            previous -= 1
        if cursor < len(source) and source[cursor] == 40 and (
            previous < 0 or source[previous] not in (46, 63)
        ):
            values.add(decode(source[index:end]))
        index = end
    return values


def expression_kind(source: bytes, start: int, end: int) -> str:
    start, end = trim_range(source, start, end)
    if start >= end:
        return "empty"
    value = source[start:end]
    if value[0] in (34, 39):
        return "string"
    if value[0] == 96:
        return "template"
    if value[0] == 123:
        return "object"
    if value[0] == 91:
        return "array"
    if IDENTIFIER_RE.fullmatch(value):
        return "identifier"
    if re.fullmatch(rb"(?:!0|!1|true|false|null|undefined|void\s+0)", value):
        return "primitive"
    if re.fullmatch(rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?", value, re.I):
        return "number"
    if re.match(rb"^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+", value):
        return "member-or-call"
    if re.match(rb"^(?:new\s+)?[A-Za-z_$][A-Za-z0-9_$]*\s*\(", value):
        return "call"
    if b"=>" in value:
        return "function"
    if b"?" in value:
        return "conditional"
    return "expression"


def static_string_value(source: bytes, start: int, end: int) -> str | None:
    start, end = trim_range(source, start, end)
    if end - start < 2 or source[start] not in (34, 39):
        return None
    closing = skip_quoted(source, start, source[start])
    if closing != end:
        return None
    return decode(source[start + 1 : end - 1])


def normalize_template(source: bytes, start: int, end: int) -> str | None:
    start, end = trim_range(source, start, end)
    if end - start < 2 or source[start] != 96:
        return None
    closing, expressions = template_expression_ranges(source, start)
    if closing != end:
        return None
    parts: list[bytes] = []
    cursor = start + 1
    for expression_start, expression_end in expressions:
        marker_start = expression_start - 2
        parts.append(source[cursor:marker_start])
        parts.append(b"${}")
        cursor = expression_end + 1
    parts.append(source[cursor : end - 1])
    return decode(b"".join(parts))


def expression_record(source: bytes, start: int, end: int) -> dict[str, Any]:
    start, end = trim_range(source, start, end)
    source_record = safe_source_text(source[start:end])
    record = {
        "kind": expression_kind(source, start, end),
        "source": source_record,
    }
    value = static_string_value(source, start, end)
    if value is not None:
        record["staticValue"] = value
    shape = normalize_template(source, start, end)
    if shape is not None:
        if "text" in source_record:
            record["templateShape"] = sanitize_human_text(shape)
        else:
            record["templateShapeSha256"] = hashlib.sha256(shape.encode()).hexdigest()
        _, expressions = template_expression_ranges(source, start)
        record["templateExpressions"] = [
            safe_source_text(source[item_start:item_end])
            for item_start, item_end in expressions
        ]
    return record


def skip_line_comment(source: bytes, index: int) -> int:
    end = source.find(b"\n", index + 2)
    return len(source) if end < 0 else end + 1


def skip_block_comment(source: bytes, index: int) -> int:
    end = source.find(b"*/", index + 2)
    return len(source) if end < 0 else end + 2


def skip_regex(source: bytes, index: int) -> int:
    index += 1
    in_class = False
    while index < len(source):
        current = source[index]
        if current == 92:
            index += 2
            continue
        if current == 91:
            in_class = True
        elif current == 93:
            in_class = False
        elif current == 47 and not in_class:
            index += 1
            while index < len(source) and chr(source[index]).isalpha():
                index += 1
            return index
        elif current in (10, 13):
            return index
        index += 1
    return index


def regex_can_start(source: bytes, index: int) -> bool:
    previous = index - 1
    while previous >= 0 and source[previous] in b" \t\r\n":
        previous -= 1
    if previous < 0:
        return True
    return source[previous] in b"([{=,:;!?&|+-*%^~<>"


def find_matching(source: bytes, opening: int, open_byte: int = 123, close_byte: int = 125) -> int:
    depth = 0
    index = opening
    while index < len(source):
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < len(source):
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if current == open_byte:
            depth += 1
        elif current == close_byte:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def object_keys(source: bytes, opening: int) -> set[str]:
    closing = find_matching(source, opening)
    if closing < 0:
        return set()
    keys: set[str] = set()
    depth = 1
    paren_depth = 0
    bracket_depth = 0
    index = opening + 1
    while index < closing:
        current = source[index]
        if current in (34, 39, 96):
            previous = index - 1
            while previous > opening and source[previous] in b" \t\r\n":
                previous -= 1
            at_member_start = source[previous] in (44, 123)
            if (
                depth == 1
                and paren_depth == 0
                and bracket_depth == 0
                and at_member_start
                and current in (34, 39)
            ):
                end = skip_quoted(source, index, current)
                cursor = end
                while cursor < closing and source[cursor] in b" \t\r\n":
                    cursor += 1
                if cursor < closing and source[cursor] == 58:
                    keys.add(decode(source[index + 1 : end - 1]))
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < closing:
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if current == 123:
            depth += 1
            index += 1
            continue
        if current == 125:
            depth -= 1
            index += 1
            continue
        if current == 40:
            paren_depth += 1
            index += 1
            continue
        if current == 41:
            paren_depth = max(0, paren_depth - 1)
            index += 1
            continue
        if current == 91:
            bracket_depth += 1
            index += 1
            continue
        if current == 93:
            bracket_depth = max(0, bracket_depth - 1)
            index += 1
            continue
        previous = index - 1
        while previous > opening and source[previous] in b" \t\r\n":
            previous -= 1
        at_member_start = source[previous] in (44, 123)
        if (
            depth == 1
            and paren_depth == 0
            and bracket_depth == 0
            and at_member_start
            and (chr(current).isalpha() or current in (36, 95))
        ):
            end = index + 1
            while end < closing and (chr(source[end]).isalnum() or source[end] in (36, 95)):
                end += 1
            cursor = end
            while cursor < closing and source[cursor] in b" \t\r\n":
                cursor += 1
            if cursor < closing and source[cursor] == 58:
                keys.add(decode(source[index:end]))
            index = end
            continue
        index += 1
    return keys


def scan_function_ranges(source: bytes) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    index = 0
    while index < len(source):
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < len(source):
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if is_identifier_start(current):
            token_end = index + 1
            while token_end < len(source) and is_identifier_part(source[token_end]):
                token_end += 1
            if source[index:token_end] == b"function":
                cursor = skip_space(source, token_end)
                if cursor < len(source) and source[cursor] == 42:
                    cursor = skip_space(source, cursor + 1)
                name: str | None = None
                if cursor < len(source) and is_identifier_start(source[cursor]):
                    name_end = cursor + 1
                    while name_end < len(source) and is_identifier_part(source[name_end]):
                        name_end += 1
                    name = decode(source[cursor:name_end])
                    cursor = skip_space(source, name_end)
                if cursor < len(source) and source[cursor] == 40:
                    params_end = find_matching(source, cursor, 40, 41)
                    if params_end >= 0:
                        body_open = skip_space(source, params_end + 1)
                        if body_open < len(source) and source[body_open] == 123:
                            body_close = find_matching(source, body_open)
                            if body_close >= 0:
                                ranges.append(
                                    {
                                        "start": body_open,
                                        "end": body_close,
                                        "name": name,
                                    }
                                )
            index = token_end
            continue
        index += 1

    ranges.sort(key=lambda item: (item["start"], -item["end"]))
    stack: list[dict[str, Any]] = []
    for identifier, item in enumerate(ranges):
        while stack and item["start"] > stack[-1]["end"]:
            stack.pop()
        item["id"] = identifier
        item["parent"] = stack[-1]["id"] if stack else None
        stack.append(item)
    return ranges


def contexts_for_offsets(
    offsets: set[int], ranges: list[dict[str, Any]]
) -> dict[int, int | None]:
    result: dict[int, int | None] = {}
    stack: list[dict[str, Any]] = []
    range_index = 0
    for offset in sorted(offsets):
        while range_index < len(ranges) and ranges[range_index]["start"] <= offset:
            item = ranges[range_index]
            while stack and item["start"] > stack[-1]["end"]:
                stack.pop()
            stack.append(item)
            range_index += 1
        while stack and offset > stack[-1]["end"]:
            stack.pop()
        result[offset] = stack[-1]["id"] if stack else None
    return result


def function_ancestors(
    function_id: int | None, ranges_by_id: dict[int, dict[str, Any]]
) -> set[int | None]:
    ancestors: set[int | None] = {None}
    current = function_id
    while current is not None:
        ancestors.add(current)
        current = ranges_by_id[current]["parent"]
    return ancestors


def scan_named_calls(source: bytes, names: set[str]) -> list[dict[str, Any]]:
    encoded_names = {name.encode(): name for name in names}
    calls: list[dict[str, Any]] = []

    def scan_segment(start: int, end: int) -> None:
        index = start
        last_identifier: bytes | None = None
        while index < end:
            current = source[index]
            if current in (34, 39):
                index = skip_quoted(source, index, current)
                continue
            if current == 96:
                template_end, expressions = template_expression_ranges(source, index)
                for expression_start, expression_end in expressions:
                    scan_segment(expression_start, expression_end)
                index = template_end
                continue
            if current == 47 and index + 1 < end:
                following = source[index + 1]
                if following == 47:
                    index = skip_line_comment(source, index)
                    continue
                if following == 42:
                    index = skip_block_comment(source, index)
                    continue
                if regex_can_start(source, index):
                    index = skip_regex(source, index)
                    continue
            if is_identifier_start(current):
                token_end = index + 1
                while token_end < end and is_identifier_part(source[token_end]):
                    token_end += 1
                token = source[index:token_end]
                name = encoded_names.get(token)
                if name is not None:
                    cursor = skip_space(source, token_end, end)
                    previous = index - 1
                    while previous >= start and source[previous] in b" \t\r\n":
                        previous -= 1
                    is_member = previous >= start and source[previous] == 46
                    if (
                        cursor < end
                        and source[cursor] == 40
                        and last_identifier != b"function"
                        and not is_member
                    ):
                        closing = find_matching(source, cursor, 40, 41)
                        if closing >= 0:
                            calls.append(
                                {
                                    "callee": name,
                                    "offset": index,
                                    "opening": cursor,
                                    "closing": closing,
                                    "arguments": split_top_level_ranges(
                                        source, cursor + 1, closing
                                    ),
                                }
                            )
                last_identifier = token
                index = token_end
                continue
            if current not in b" \t\r\n":
                if current not in (46,):
                    last_identifier = None
            index += 1

    scan_segment(0, len(source))
    calls.sort(key=lambda item: item["offset"])
    return calls


def scan_assignments(
    source: bytes, names: set[str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    encoded_names = None if names is None else {name.encode(): name for name in names}
    assignments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    index = 0
    while index < len(source):
        current = source[index]
        if current in (34, 39, 96):
            index = skip_quoted(source, index, current)
            continue
        if current == 47 and index + 1 < len(source):
            following = source[index + 1]
            if following == 47:
                index = skip_line_comment(source, index)
                continue
            if following == 42:
                index = skip_block_comment(source, index)
                continue
            if regex_can_start(source, index):
                index = skip_regex(source, index)
                continue
        if is_identifier_start(current):
            token_end = index + 1
            while token_end < len(source) and is_identifier_part(source[token_end]):
                token_end += 1
            token = source[index:token_end]
            name = decode(token) if encoded_names is None else encoded_names.get(token)
            if name is not None:
                previous = index - 1
                while previous >= 0 and source[previous] in b" \t\r\n":
                    previous -= 1
                cursor = skip_space(source, token_end)
                if (
                    cursor < len(source)
                    and source[cursor] == 61
                    and (cursor + 1 >= len(source) or source[cursor + 1] not in (61, 62))
                    and (previous < 0 or source[previous] not in (33, 46, 60, 61, 62))
                ):
                    value_start = skip_space(source, cursor + 1)
                    value_end = scan_expression_end(source, value_start)
                    if value_start < value_end:
                        assignments[name].append(
                            {
                                "offset": index,
                                "start": value_start,
                                "end": value_end,
                            }
                        )
            index = token_end
            continue
        index += 1
    return assignments


def object_entries(source: bytes, start: int, end: int) -> list[dict[str, Any]]:
    start, end = trim_range(source, start, end)
    if start >= end or source[start] != 123:
        return []
    closing = find_matching(source, start)
    if closing < 0 or closing + 1 != end:
        return []
    entries: list[dict[str, Any]] = []
    for entry_start, entry_end in split_top_level_ranges(source, start + 1, closing):
        if source[entry_start:entry_start + 3] == b"...":
            spread_start, spread_end = trim_range(source, entry_start + 3, entry_end)
            entries.append(
                {
                    "kind": "spread",
                    "start": spread_start,
                    "end": spread_end,
                }
            )
            continue
        colon = find_top_level_byte(source, entry_start, entry_end, 58)
        if colon >= 0:
            key_start, key_end = trim_range(source, entry_start, colon)
            value_start, value_end = trim_range(source, colon + 1, entry_end)
            if key_start < key_end and source[key_start] in (34, 39):
                key = static_string_value(source, key_start, key_end)
                kind = "property"
            elif IDENTIFIER_RE.fullmatch(source[key_start:key_end]):
                key = decode(source[key_start:key_end])
                kind = "property"
            elif key_start < key_end and source[key_start] == 91:
                key = None
                kind = "computed-property"
            else:
                key = None
                kind = "property-expression"
            entries.append(
                {
                    "kind": kind,
                    "key": key,
                    "keyStart": key_start,
                    "keyEnd": key_end,
                    "start": value_start,
                    "end": value_end,
                }
            )
            continue
        value = source[entry_start:entry_end]
        if IDENTIFIER_RE.fullmatch(value):
            entries.append(
                {
                    "kind": "shorthand",
                    "key": decode(value),
                    "start": entry_start,
                    "end": entry_end,
                }
            )
        else:
            method_match = re.match(rb"(?:get\s+|set\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", value)
            entries.append(
                {
                    "kind": "method" if method_match else "unknown",
                    "key": decode(method_match.group(1)) if method_match else None,
                    "start": entry_start,
                    "end": entry_end,
                }
            )
    return entries


class AssignmentResolver:
    def __init__(
        self,
        source: bytes,
        assignments: dict[str, list[dict[str, Any]]],
    ):
        self.source = source
        self.assignments = assignments
        self.positions = {
            name: [item["offset"] for item in values]
            for name, values in assignments.items()
        }

    def resolve(
        self, name: str, before: int, scope_path: list[int]
    ) -> dict[str, Any] | None:
        values = self.assignments.get(name, [])
        positions = self.positions.get(name, [])
        index = bisect_right(positions, before - 1) - 1
        while index >= 0:
            candidate = values[index]
            candidate_path = candidate.get("scopePath", [])
            if scope_path[: len(candidate_path)] == candidate_path:
                return candidate
            index -= 1
        return None


def analyze_payload(
    source: bytes,
    start: int,
    end: int,
    call_offset: int,
    scope_path: list[int],
    resolver: AssignmentResolver,
    seen: set[str] | None = None,
) -> dict[str, Any]:
    seen = set() if seen is None else set(seen)
    start, end = trim_range(source, start, end)
    result: dict[str, Any] = {"argument": expression_record(source, start, end)}
    identifier = decode(source[start:end]) if IDENTIFIER_RE.fullmatch(source[start:end]) else None
    if identifier is not None and identifier not in seen:
        seen.add(identifier)
        assignment = resolver.resolve(identifier, call_offset, scope_path)
        if assignment is not None:
            result["resolution"] = {
                "identifier": identifier,
                "assignmentOffset": assignment["offset"],
                "expression": expression_record(
                    source, assignment["start"], assignment["end"]
                ),
            }
            start, end = assignment["start"], assignment["end"]
        else:
            result["resolution"] = {
                "identifier": identifier,
                "status": "unresolved",
            }

    entries = object_entries(source, start, end)
    if not entries:
        result["objectStatus"] = "not-static-object"
        return result

    direct_keys: set[str] = set()
    shorthand_keys: set[str] = set()
    computed_keys: list[dict[str, Any]] = []
    spreads: list[dict[str, Any]] = []
    expanded_keys: set[str] = set()
    unresolved_spreads: list[dict[str, Any]] = []
    for entry in entries:
        kind = entry["kind"]
        key = entry.get("key")
        if kind == "property" and key is not None:
            direct_keys.add(key)
            expanded_keys.add(key)
        elif kind == "shorthand" and key is not None:
            shorthand_keys.add(key)
            expanded_keys.add(key)
        elif kind.startswith("computed"):
            computed_keys.append(
                expression_record(source, entry["keyStart"], entry["keyEnd"])
            )
        elif kind == "spread":
            spread_record = expression_record(source, entry["start"], entry["end"])
            spread_identifier = (
                decode(source[entry["start"]:entry["end"]])
                if IDENTIFIER_RE.fullmatch(source[entry["start"]:entry["end"]])
                else None
            )
            nested: dict[str, Any] | None = None
            if spread_identifier is not None and spread_identifier not in seen:
                assignment = resolver.resolve(spread_identifier, call_offset, scope_path)
                if assignment is not None:
                    nested = analyze_payload(
                        source,
                        assignment["start"],
                        assignment["end"],
                        call_offset,
                        scope_path,
                        resolver,
                        seen | {spread_identifier},
                    )
                    spread_record["resolution"] = {
                        "identifier": spread_identifier,
                        "assignmentOffset": assignment["offset"],
                    }
            elif expression_kind(source, entry["start"], entry["end"]) == "object":
                nested = analyze_payload(
                    source,
                    entry["start"],
                    entry["end"],
                    call_offset,
                    scope_path,
                    resolver,
                    seen,
                )
            if nested is not None and nested.get("objectStatus") == "static-object":
                nested_keys = set(nested.get("expandedKeys", []))
                expanded_keys.update(nested_keys)
                spread_record["expandedKeys"] = sorted(nested_keys)
            else:
                unresolved_spreads.append(spread_record)
            spreads.append(spread_record)

    result.update(
        {
            "objectStatus": "static-object",
            "directKeys": sorted(direct_keys),
            "shorthandKeys": sorted(shorthand_keys),
            "computedKeys": computed_keys,
            "spreads": spreads,
            "expandedKeys": sorted(expanded_keys),
            "unresolvedSpreads": unresolved_spreads,
        }
    )
    return result


class JsLiteralParser:
    def __init__(self, source: bytes, start: int, end: int):
        self.source = source
        self.index = start
        self.end = end

    def space(self) -> None:
        self.index = skip_space(self.source, self.index, self.end)

    def parse(self) -> Any:
        self.space()
        if self.index >= self.end:
            raise ValueError("unexpected end of literal")
        current = self.source[self.index]
        if current == 123:
            return self.parse_object()
        if current == 91:
            return self.parse_array()
        if current in (34, 39):
            return self.parse_string()
        if self.source.startswith(b"!0", self.index):
            self.index += 2
            return True
        if self.source.startswith(b"!1", self.index):
            self.index += 2
            return False
        if self.source.startswith(b"null", self.index):
            self.index += 4
            return None
        number = re.match(
            rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?",
            self.source[self.index : self.end],
            re.I,
        )
        if number:
            raw = number.group(0).decode("ascii")
            self.index += len(number.group(0))
            if any(char in raw.lower() for char in ".e"):
                value = float(raw)
                return int(value) if value.is_integer() else value
            return int(raw)
        identifier = re.match(
            rb"[A-Za-z_$][A-Za-z0-9_$]*", self.source[self.index : self.end]
        )
        if identifier:
            value = decode(identifier.group(0))
            self.index += len(identifier.group(0))
            return {"$expression": value}
        raise ValueError(f"unsupported literal at offset {self.index}")

    def parse_string(self) -> str:
        quote = self.source[self.index]
        closing = skip_quoted(self.source, self.index, quote)
        raw = self.source[self.index + 1 : closing - 1]
        self.index = closing
        if quote == 34:
            return json.loads(b'"' + raw + b'"')
        escaped = raw.replace(b"\\", b"\\\\").replace(b'"', b'\\"')
        return json.loads(b'"' + escaped + b'"')

    def parse_key(self) -> str:
        self.space()
        if self.source[self.index] in (34, 39):
            return self.parse_string()
        match = re.match(
            rb"[A-Za-z_$][A-Za-z0-9_$]*", self.source[self.index : self.end]
        )
        if not match:
            raise ValueError(f"invalid object key at offset {self.index}")
        self.index += len(match.group(0))
        return decode(match.group(0))

    def parse_object(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        self.index += 1
        while True:
            self.space()
            if self.index < self.end and self.source[self.index] == 125:
                self.index += 1
                return result
            key = self.parse_key()
            self.space()
            if self.index >= self.end or self.source[self.index] != 58:
                raise ValueError(f"missing object colon at offset {self.index}")
            self.index += 1
            result[key] = self.parse()
            self.space()
            if self.index < self.end and self.source[self.index] == 44:
                self.index += 1
                continue
            if self.index < self.end and self.source[self.index] == 125:
                self.index += 1
                return result
            raise ValueError(f"missing object delimiter at offset {self.index}")

    def parse_array(self) -> list[Any]:
        result: list[Any] = []
        self.index += 1
        while True:
            self.space()
            if self.index < self.end and self.source[self.index] == 93:
                self.index += 1
                return result
            result.append(self.parse())
            self.space()
            if self.index < self.end and self.source[self.index] == 44:
                self.index += 1
                continue
            if self.index < self.end and self.source[self.index] == 93:
                self.index += 1
                return result
            raise ValueError(f"missing array delimiter at offset {self.index}")


def static_enum_groups(source: bytes, enum_builder: str) -> set[str]:
    groups: set[str] = set()
    pattern = re.compile(
        rb"\b"
        + re.escape(enum_builder.encode())
        + rb"\(\[((?:\s*['\"](?:\\.|[^'\"]){1,160}['\"]\s*,?)+)\]\)"
    )
    for match in pattern.finditer(source):
        values = [decode(value) for value in re.findall(rb"['\"]((?:\\.|[^'\"]){1,160})['\"]", match.group(1))]
        if values:
            groups.add(" | ".join(values))
    return groups


def callsite_static_values(rows: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for row in rows:
        argument = row.get("nameArgument", {})
        value = argument.get("staticValue") or argument.get("resolvedStaticValue")
        if isinstance(value, str):
            values.add(value)
    return values


def callsite_template_shapes(rows: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for row in rows:
        argument = row.get("nameArgument", {})
        value = argument.get("templateShape") or argument.get("resolvedTemplateShape")
        if isinstance(value, str):
            values.add(value)
    return values


def event_fields_from_callsites(rows: list[dict[str, Any]]) -> list[str]:
    fields: dict[str, set[str]] = {}
    for row in rows:
        argument = row.get("nameArgument", {})
        event = argument.get("staticValue") or argument.get("resolvedStaticValue")
        if not isinstance(event, str):
            continue
        payload = row.get("payload", {})
        fields.setdefault(event, set()).update(payload.get("directKeys", []))
        fields[event].update(payload.get("shorthandKeys", []))
        fields[event].update(payload.get("expandedKeys", []))
    return [
        f"{event}\t{','.join(sorted(values)) if values else '<no-static-fields>'}"
        for event, values in sorted(fields.items())
    ]


def object_keys_after(source: bytes, marker: bytes) -> set[str]:
    opening = source.find(marker)
    if opening < 0:
        return set()
    opening += marker.rfind(b"{")
    return object_keys(source, opening)


def user_config_directories(source: bytes, variable: str) -> set[str]:
    encoded = re.escape(variable.encode())
    match = re.search(
        rb"\b" + encoded + rb"=\[([^\]]+)\],[A-Za-z_$][A-Za-z0-9_$]*="
        rb"new Set\(" + encoded + rb"\)",
        source,
    )
    if not match:
        return set()
    return {decode(value) for value in re.findall(rb"['\"]([^'\"]+)['\"]", match.group(1))}


def tool_catalog(source: bytes) -> set[str]:
    values: set[str] = set()
    patterns = [
        rb'\[("Bash","BashOutput","KillShell","PowerShell".*?)\],'
        rb'[A-Za-z_$][A-Za-z0-9_$]*=\[(.*?)\]',
        rb'BUILTIN_TOOL_NAMES\s*=\s*\[(.*?)\]',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, source, re.DOTALL):
            for group in match.groups():
                values.update(
                    decode(value)
                    for value in re.findall(rb"['\"]([^'\"]+)['\"]", group)
                )
    return values


def schema_property_identifiers(
    source: bytes, schema_builders: list[str]
) -> set[str]:
    if not schema_builders:
        return set()
    alternatives = rb"|".join(
        re.escape(builder.encode()) for builder in schema_builders
    )
    pattern = re.compile(
        rb"\b([A-Za-z_$][A-Za-z0-9_$]{0,100})\s*:\s*(?:"
        + alternatives
        + rb")\("
    )
    return static_values(pattern, source)


def sdk_control_subtypes(source: bytes, literal_builder: str) -> set[str]:
    pattern = re.compile(
        rb"subtype:\s*"
        + re.escape(literal_builder.encode())
        + rb"\(\s*['\"]([a-z0-9_.:-]+)['\"]\s*\)"
    )
    return static_values(pattern, source)


def otel_span_names(source: bytes, metric_names: set[str]) -> set[str]:
    pattern = re.compile(
        rb"\b[A-Za-z_$][A-Za-z0-9_$]*\(\s*['\"]"
        rb"(claude_code\.[a-z0-9_.-]+)['\"]"
    )
    return static_values(pattern, source) - metric_names


def claude_storage_namespaces(source: bytes) -> set[str]:
    start_match = CLAUDE_STORAGE_FACTORY_START_RE.search(source)
    if start_match is None:
        return set()
    end_match = CLAUDE_STORAGE_FACTORY_END_RE.search(source, start_match.start())
    if end_match is None or end_match.start() - start_match.start() > 20000:
        return set()
    end = source.find(b"}", end_match.end())
    if end < 0:
        return set()
    return static_values(STORAGE_NAMESPACE_RE, source[start_match.start() : end + 1])


def template_values(source: bytes) -> set[str]:
    values: set[str] = set()
    for match in FIRST_PARTY_TEMPLATE_RE.finditer(source):
        value = decode(match.group(1))
        if not value.startswith("tengu_"):
            continue
        values.add(re.sub(r"\$\{[^}]+\}", "${}", value))
    return values


def event_family(value: str) -> str:
    parts = value.split("_")
    if len(parts) < 3:
        return value
    if parts[1] in {"bg", "mcp", "api", "sdk", "tool", "auto", "bridge", "daemon", "plugin", "session", "agent", "oauth", "memory", "hook", "remote", "chrome", "artifact", "ultrareview", "worktree", "workflow", "voice", "ide", "lsp", "sandbox", "permission", "prompt", "compact", "config"}:
        return "_".join(parts[:2])
    return "tengu_other"


def extract_datadog_allowlist(
    source: bytes, variable: str, next_variable: str
) -> set[str]:
    match = re.search(
        rb"\b"
        + re.escape(variable.encode())
        + rb"\s*=\s*new Set\(\[(.*?)\]\),\s*"
        + re.escape(next_variable.encode())
        + rb"\s*=",
        source,
        re.DOTALL,
    )
    if not match:
        return set()
    return {
        decode(value)
        for value in re.findall(rb"['\"]([a-z][a-z0-9_.:-]+)['\"]", match.group(1))
    }


def extract_datadog_fields(source: bytes, variable: bytes, next_variable: bytes) -> set[str]:
    pattern = re.compile(
        rb"\b" + variable + rb"\s*=\s*\[(.*?)\]\s*[;,]\s*" + next_variable + rb"\s*=",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return set()
    return {decode(value) for value in re.findall(rb"['\"]([^'\"]+)['\"]", match.group(1))}


def extract_urls(source: bytes) -> set[str]:
    return {
        decode(value).rstrip(".,;)'\"")
        for value in URL_RE.findall(source)
    }


def add_comparison_fields(
    rows: list[dict[str, Any]], semantic_values: list[dict[str, Any]], prefix: str
) -> None:
    seen: Counter[str] = Counter()
    for row, semantic in zip(rows, semantic_values, strict=True):
        canonical = json.dumps(
            semantic, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        seen[digest] += 1
        row["comparisonKey"] = f"{prefix}:{digest}:{seen[digest]}"
        row["comparisonValue"] = canonical


def compact_expression(record: dict[str, Any]) -> Any:
    if "staticValue" in record:
        return {"kind": "string", "value": record["staticValue"]}
    if "templateShape" in record:
        return {
            "kind": "template",
            "shape": record["templateShape"],
            "expressions": [
                item.get("text", f"sha256:{item['sha256']}")
                for item in record.get("templateExpressions", [])
            ],
        }
    source = record["source"]
    return {
        "kind": record["kind"],
        "expression": source.get("text", f"sha256:{source['sha256']}"),
    }


def resolved_argument_record(
    source: bytes,
    start: int,
    end: int,
    call_offset: int,
    scope_path: list[int],
    resolver: AssignmentResolver,
) -> dict[str, Any]:
    result = expression_record(source, start, end)
    start, end = trim_range(source, start, end)
    if IDENTIFIER_RE.fullmatch(source[start:end]):
        identifier = decode(source[start:end])
        assignment = resolver.resolve(identifier, call_offset, scope_path)
        if assignment is None:
            result["resolution"] = {"identifier": identifier, "status": "unresolved"}
        else:
            resolved = expression_record(source, assignment["start"], assignment["end"])
            result["resolution"] = {
                "identifier": identifier,
                "assignmentOffset": assignment["offset"],
                "expression": resolved,
            }
            if "staticValue" in resolved:
                result["resolvedStaticValue"] = resolved["staticValue"]
            if "templateShape" in resolved:
                result["resolvedTemplateShape"] = resolved["templateShape"]
    return result


def resolve_static_string_expression(
    source: bytes,
    start: int,
    end: int,
    before: int,
    scope_path: list[int],
    resolver: AssignmentResolver,
    seen: set[str] | None = None,
) -> str | None:
    start, end = trim_range(source, start, end)
    direct = static_string_value(source, start, end)
    if direct is not None:
        return direct
    if start < end and source[start] == 96:
        shape = normalize_template(source, start, end)
        if shape is not None and "${}" not in shape:
            return shape
        return None
    if not IDENTIFIER_RE.fullmatch(source[start:end]):
        return None
    identifier = decode(source[start:end])
    seen = set() if seen is None else set(seen)
    if identifier in seen:
        return None
    assignment = resolver.resolve(identifier, before, scope_path)
    if assignment is None:
        return None
    return resolve_static_string_expression(
        source,
        assignment["start"],
        assignment["end"],
        assignment["offset"],
        assignment.get("scopePath", scope_path),
        resolver,
        seen | {identifier},
    )


def resolve_static_string_array(
    source: bytes,
    start: int,
    end: int,
    before: int,
    scope_path: list[int],
    resolver: AssignmentResolver,
) -> tuple[list[str], list[dict[str, Any]]]:
    start, end = trim_range(source, start, end)
    if IDENTIFIER_RE.fullmatch(source[start:end]):
        assignment = resolver.resolve(decode(source[start:end]), before, scope_path)
        if assignment is not None:
            start, end = trim_range(source, assignment["start"], assignment["end"])
            before = assignment["offset"]
            scope_path = assignment.get("scopePath", scope_path)
    if start >= end or source[start] != 91:
        return [], [expression_record(source, start, end)]
    closing = find_matching(source, start, 91, 93)
    if closing < 0 or closing + 1 != end:
        return [], [expression_record(source, start, end)]
    values: list[str] = []
    unresolved: list[dict[str, Any]] = []
    for item_start, item_end in split_top_level_ranges(source, start + 1, closing):
        value = resolve_static_string_expression(
            source,
            item_start,
            item_end,
            before,
            scope_path,
            resolver,
        )
        if value is None:
            unresolved.append(expression_record(source, item_start, item_end))
        else:
            values.append(value)
    return values, unresolved


def tool_registration_rows(
    source: bytes,
    candidates: list[dict[str, Any]],
    resolver: AssignmentResolver,
) -> tuple[list[dict[str, Any]], str]:
    analyzed: list[dict[str, Any]] = []
    names_by_callee: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        name_start, name_end = candidate["nameExpression"]
        scope_path = candidate.get("scopePath", [])
        name = resolve_static_string_expression(
            source,
            name_start,
            name_end,
            candidate["offset"],
            scope_path,
            resolver,
        )
        item = {**candidate, "resolvedName": name}
        analyzed.append(item)
        if candidate.get("callee") and name is not None:
            names_by_callee[candidate["callee"]].add(name)

    stable_anchors = {"Bash", "Read", "Write", "Edit", "Glob", "Grep"}
    factories = sorted(
        callee
        for callee, names in names_by_callee.items()
        if stable_anchors <= names
    )
    if len(factories) != 1:
        raise ValueError(
            "unable to uniquely discover tool factory from stable core tools: "
            f"{factories!r}"
        )
    factory = factories[0]

    rows: list[dict[str, Any]] = []
    comparison_occurrences: Counter[str] = Counter()
    for candidate in analyzed:
        if candidate.get("callee") != factory:
            continue
        name_start, name_end = candidate["nameExpression"]
        name_record = expression_record(source, name_start, name_end)
        name = candidate["resolvedName"]
        aliases: list[str] = []
        unresolved_aliases: list[dict[str, Any]] = []
        if candidate.get("aliasesExpression") is not None:
            aliases_start, aliases_end = candidate["aliasesExpression"]
            aliases, unresolved_aliases = resolve_static_string_array(
                source,
                aliases_start,
                aliases_end,
                candidate["offset"],
                candidate.get("scopePath", []),
                resolver,
            )
        dynamic_name = compact_expression(name_record)
        semantic_name = name if name is not None else json.dumps(
            dynamic_name, sort_keys=True, separators=(",", ":")
        )
        comparison_occurrences[semantic_name] += 1
        occurrence = comparison_occurrences[semantic_name]
        properties = candidate["properties"]
        row = {
            "name": name,
            "nameExpression": name_record,
            "aliases": aliases,
            "unresolvedAliases": unresolved_aliases,
            "factorySymbol": factory,
            "offset": candidate["offset"],
            "line": candidate["line"],
            "column": candidate["column"],
            "function": candidate.get("function"),
            "functionKind": candidate.get("functionKind", "top-level"),
            "properties": properties,
            "declares": {
                key: key in properties
                for key in (
                    "briefStandalone",
                    "checkPermissions",
                    "isConcurrencySafe",
                    "isEnabled",
                    "isReadOnly",
                    "requiresUserInteraction",
                    "shouldDefer",
                )
            },
            "comparisonKey": f"toolRegistration:{semantic_name}:{occurrence}",
            "comparisonValue": json.dumps(
                {
                    "name": name if name is not None else dynamic_name,
                    "aliases": aliases,
                    "unresolvedAliasCount": len(unresolved_aliases),
                    "properties": properties,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ),
        }
        rows.append(row)
    return rows, factory


def callsite_rows(
    source: bytes,
    calls: list[dict[str, Any]],
    callee_roles: dict[str, str],
    resolver: AssignmentResolver,
    include_payload: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    semantic_values: list[dict[str, Any]] = []
    for call in calls:
        role = callee_roles.get(call["callee"])
        if role is None:
            continue
        arguments = call["arguments"]
        row: dict[str, Any] = {
            "callee": call["callee"],
            "calleeRole": role,
            "offset": call["offset"],
            "line": call["line"],
            "column": call["column"],
            "function": call.get("function"),
            "functionKind": call.get("functionKind", "top-level"),
            "arguments": [expression_record(source, start, end) for start, end in arguments],
        }
        semantic: dict[str, Any] = {"calleeRole": role}
        if arguments:
            event = resolved_argument_record(
                source,
                arguments[0][0],
                arguments[0][1],
                call["offset"],
                call.get("scopePath", []),
                resolver,
            )
            row["nameArgument"] = event
            semantic["nameArgument"] = compact_expression(event)
            if "resolvedStaticValue" in event:
                semantic["resolvedStaticValue"] = event["resolvedStaticValue"]
            elif "resolvedTemplateShape" in event:
                semantic["resolvedTemplateShape"] = event["resolvedTemplateShape"]
        else:
            row["nameArgument"] = {"kind": "missing"}
            semantic["nameArgument"] = {"kind": "missing"}
        if include_payload:
            if len(arguments) >= 2:
                payload = analyze_payload(
                    source,
                    arguments[1][0],
                    arguments[1][1],
                    call["offset"],
                    call.get("scopePath", []),
                    resolver,
                )
            else:
                payload = {"objectStatus": "missing"}
            row["payload"] = payload
            semantic["payload"] = {
                "status": payload.get("objectStatus"),
                "directKeys": payload.get("directKeys", []),
                "shorthandKeys": payload.get("shorthandKeys", []),
                "expandedKeys": payload.get("expandedKeys", []),
                "computedKeys": [compact_expression(item) for item in payload.get("computedKeys", [])],
                "spreads": [compact_expression(item) for item in payload.get("spreads", [])],
            }
        rows.append(row)
        semantic_values.append(semantic)
    rows_and_semantics = sorted(
        zip(rows, semantic_values, strict=True), key=lambda pair: pair[0]["offset"]
    )
    rows = [pair[0] for pair in rows_and_semantics]
    semantic_values = [pair[1] for pair in rows_and_semantics]
    add_comparison_fields(
        rows,
        semantic_values,
        "+".join(sorted(set(callee_roles.values()))),
    )
    return rows


def message_callsite_rows(
    source: bytes,
    calls: list[dict[str, Any]],
    callee_roles: dict[str, str],
    resolver: AssignmentResolver,
) -> list[dict[str, Any]]:
    return callsite_rows(
        source,
        calls,
        callee_roles,
        resolver,
        include_payload=False,
    )


def literal_rows(
    source: bytes,
    string_nodes: list[dict[str, Any]],
    template_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    string_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for node in string_nodes:
        start, end = node["start"], node["end"]
        quote_byte = source[start]
        raw = source[start + 1 : end - 1]
        quote = "double" if quote_byte == 34 else "single"
        key = (quote, bytes_sha256(raw))
        row = string_groups.get(key)
        if row is None:
            decoded = decode(raw)
            classifications: list[str] = []
            if decoded.startswith(("http://", "https://")):
                classifications.append("url")
            if decoded.startswith(API_TEMPLATE_PREFIXES):
                classifications.append("api-path")
            if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", decoded):
                classifications.append("uppercase-identifier")
            row = {
                "quote": quote,
                "value": safe_source_text(raw, 4096),
                "classifications": classifications,
                "occurrenceCount": 0,
                "locations": [],
            }
            string_groups[key] = row
        row["occurrenceCount"] += 1
        row["locations"].append(
            {
                "offset": node["offset"],
                "line": node["line"],
                "column": node["column"],
            }
        )

    template_groups: dict[str, dict[str, Any]] = {}
    for node in template_nodes:
        start, end = node["start"], node["end"]
        raw = source[start + 1 : end - 1]
        key = bytes_sha256(raw)
        row = template_groups.get(key)
        if row is None:
            value = safe_source_text(raw, 4096)
            shape = normalize_template(source, start, end)
            lowered_shape = (shape or "").lower()
            classifications: list[str] = []
            if "http://" in lowered_shape or "https://" in lowered_shape:
                classifications.append("url-template")
            if lowered_shape.startswith(API_TEMPLATE_PREFIXES):
                classifications.append("api-path-template")
            if re.search(
                r"otel|telemetr|event_logging|datadog|growthbook|metrics|traces|logs",
                lowered_shape,
            ):
                classifications.append("observability-template")
            row = {
                "value": value,
                "shape": sanitize_human_text(shape) if shape is not None and "text" in value else None,
                "shapeSha256": hashlib.sha256(shape.encode()).hexdigest()
                if shape is not None
                else None,
                "classifications": classifications,
                "expressions": [
                    safe_source_text(source[item_start:item_end])
                    for item_start, item_end in node.get("expressions", [])
                ],
                "occurrenceCount": 0,
                "locations": [],
            }
            template_groups[key] = row
        row["occurrenceCount"] += 1
        row["locations"].append(
            {
                "offset": node["offset"],
                "line": node["line"],
                "column": node["column"],
            }
        )

    strings = sorted(
        string_groups.values(), key=lambda item: item["locations"][0]["offset"]
    )
    templates = sorted(
        template_groups.values(), key=lambda item: item["locations"][0]["offset"]
    )
    string_semantics = [
        {
            "quote": row["quote"],
            "sha256": row["value"]["sha256"],
            "length": row["value"]["length"],
            "occurrenceCount": row["occurrenceCount"],
        }
        for row in strings
    ]
    template_semantics = [
        {
            "shape": row["shape"],
            "shapeSha256": row["shapeSha256"],
            "sha256": row["value"]["sha256"],
            "occurrenceCount": row["occurrenceCount"],
            "expressions": [
                item.get("text", f"sha256:{item['sha256']}")
                for item in row["expressions"]
            ],
        }
        for row in templates
    ]
    add_comparison_fields(strings, string_semantics, "string")
    add_comparison_fields(templates, template_semantics, "template")
    return strings, templates


def environment_access_rows(
    source: bytes, access_nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    semantics: list[dict[str, Any]] = []
    for node in access_nodes:
        row: dict[str, Any] = {
            "offset": node["offset"],
            "line": node["line"],
            "column": node["column"],
            "accessor": node["accessor"],
            "name": node.get("name"),
        }
        semantic: dict[str, Any] = {
            "accessor": node["accessor"],
            "name": node.get("name"),
        }
        expression_start = node.get("expressionStart")
        expression_end = node.get("expressionEnd")
        if expression_start is not None and expression_end is not None:
            expression = expression_record(source, expression_start, expression_end)
            row["expression"] = expression
            semantic["expression"] = compact_expression(expression)
        fallback_start = node.get("fallbackStart")
        fallback_end = node.get("fallbackEnd")
        if fallback_start is not None and fallback_end is not None:
            fallback = expression_record(source, fallback_start, fallback_end)
            row["fallbackOperator"] = node["fallbackOperator"]
            row["fallbackExpression"] = fallback
            semantic["fallbackOperator"] = node["fallbackOperator"]
            semantic["fallbackExpression"] = compact_expression(fallback)
        rows.append(row)
        semantics.append(semantic)
    rows.sort(key=lambda item: item["offset"])
    add_comparison_fields(rows, semantics, "env-access")
    return rows


def environment_schema_rows(
    source: bytes, locator: LineLocator, builder: str
) -> list[dict[str, Any]]:
    builders: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        rb"\b([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
        + re.escape(builder.encode())
        + rb"\.(str|bool|triBool|int|enum)\("
    )
    for match in pattern.finditer(source):
        opening = match.end() - 1
        closing = find_matching(source, opening, 40, 41)
        if closing < 0:
            continue
        variable = decode(match.group(1))
        options_start, options_end = trim_range(source, opening + 1, closing)
        line, column = locator.locate(match.start())
        builders[variable] = {
            "type": decode(match.group(2)),
            "options": (
                expression_record(source, options_start, options_end)
                if options_start < options_end
                else None
            ),
            "builderOffset": match.start(),
            "builderLine": line,
            "builderColumn": column,
        }

    rows: list[dict[str, Any]] = []
    semantics: list[dict[str, Any]] = []
    export_pattern = re.compile(
        rb"\b([A-Z][A-Z0-9_]{2,})\s*:\s*\(\)\s*=>\s*([A-Za-z_$][A-Za-z0-9_$]*)"
    )
    seen: set[tuple[str, str]] = set()
    for match in export_pattern.finditer(source):
        name = decode(match.group(1))
        variable = decode(match.group(2))
        builder = builders.get(variable)
        if builder is None or (name, variable) in seen:
            continue
        seen.add((name, variable))
        line, column = locator.locate(match.start())
        row = {
            "name": name,
            "minifiedVariable": variable,
            "type": builder["type"],
            "options": builder["options"],
            "exportOffset": match.start(),
            "exportLine": line,
            "exportColumn": column,
            "builderOffset": builder["builderOffset"],
            "builderLine": builder["builderLine"],
            "builderColumn": builder["builderColumn"],
        }
        rows.append(row)
        semantics.append(
            {
                "name": name,
                "type": builder["type"],
                "options": compact_expression(builder["options"])
                if builder["options"]
                else None,
            }
        )
    rows.sort(key=lambda item: item["name"])
    semantics = [
        {
            "name": row["name"],
            "type": row["type"],
            "options": compact_expression(row["options"]) if row["options"] else None,
        }
        for row in rows
    ]
    add_comparison_fields(rows, semantics, "env-schema")
    return rows


def extract_method_arguments(expression: bytes, method: bytes) -> list[bytes]:
    values: list[bytes] = []
    pattern = re.compile(rb"\." + re.escape(method) + rb"\s*\(")
    for match in pattern.finditer(expression):
        opening = match.end() - 1
        closing = find_matching(expression, opening, 40, 41)
        if closing < 0:
            continue
        arguments = split_top_level_ranges(expression, opening + 1, closing)
        if arguments:
            values.append(expression[arguments[0][0] : arguments[0][1]])
    return values


def root_settings_schema_rows(
    source: bytes,
    locator: LineLocator,
    settings_function: str,
    object_builder: str,
    enum_builder: str,
) -> list[dict[str, Any]]:
    marker = source.find(
        f"function {settings_function}(e,{{strictPolicyHelperKeys".encode()
    )
    if marker < 0:
        return []
    return_prefix = f"return {object_builder}(".encode()
    return_marker = source.find(return_prefix + b"{", marker)
    if return_marker < 0:
        return []
    opening = return_marker + len(return_prefix)
    closing = find_matching(source, opening)
    if closing < 0:
        return []
    rows: list[dict[str, Any]] = []
    semantics: list[dict[str, Any]] = []
    for entry in object_entries(source, opening, closing + 1):
        line, column = locator.locate(entry["start"])
        if entry["kind"] == "spread":
            expression = expression_record(source, entry["start"], entry["end"])
            row = {
                "kind": "spread",
                "key": None,
                "offset": entry["start"],
                "line": line,
                "column": column,
                "expression": expression,
            }
            semantic = {"kind": "spread", "expression": compact_expression(expression)}
        else:
            key = entry.get("key")
            expression_bytes = source[entry["start"] : entry["end"]]
            expression = expression_record(source, entry["start"], entry["end"])
            descriptions = [
                sanitize_human_text(decode(value[1:-1]))
                for value in extract_method_arguments(expression_bytes, b"describe")
                if len(value) >= 2 and value[0] in (34, 39) and value[-1] == value[0]
            ]
            defaults = [
                safe_source_text(value)
                for method in (b"default", b"catch")
                for value in extract_method_arguments(expression_bytes, method)
            ]
            enum_values: set[str] = set()
            enum_pattern = re.compile(
                rb"\b" + re.escape(enum_builder.encode()) + rb"\s*\("
            )
            for match in enum_pattern.finditer(expression_bytes):
                enum_open = match.end() - 1
                enum_close = find_matching(expression_bytes, enum_open, 40, 41)
                if enum_close < 0:
                    continue
                enum_args = split_top_level_ranges(
                    expression_bytes, enum_open + 1, enum_close
                )
                if not enum_args:
                    continue
                arg_start, arg_end = enum_args[0]
                if expression_bytes[arg_start:arg_start + 1] == b"[":
                    enum_values.update(
                        decode(value)
                        for value in re.findall(
                            rb"['\"]((?:\\.|[^'\"])*)['\"]",
                            expression_bytes[arg_start:arg_end],
                        )
                    )
            builders = sorted(direct_call_identifiers(expression_bytes))
            row = {
                "kind": entry["kind"],
                "key": key,
                "offset": entry["start"],
                "line": line,
                "column": column,
                "expression": expression,
                "builders": builders,
                "descriptions": descriptions,
                "enumValues": sorted(enum_values),
                "defaultAndCatchExpressions": defaults,
            }
            semantic = {
                "kind": entry["kind"],
                "key": key,
                "expression": compact_expression(expression),
                "builders": builders,
                "descriptions": descriptions,
                "enumValues": sorted(enum_values),
                "defaultAndCatchExpressions": [
                    value.get("text", f"sha256:{value['sha256']}") for value in defaults
                ],
            }
        rows.append(row)
        semantics.append(semantic)
    add_comparison_fields(rows, semantics, "root-setting")
    return rows


def model_catalog_rows(
    source: bytes,
    catalog_symbol: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    marker_prefix = f"{catalog_symbol}=".encode()
    marker = source.find(marker_prefix + b"{")
    if marker < 0:
        return [], [], [], []
    opening = marker + len(marker_prefix)
    closing = find_matching(source, opening)
    if closing < 0:
        return [], [], [], []
    parser = JsLiteralParser(source, opening, closing + 1)
    catalog = parser.parse()
    if not isinstance(catalog, dict):
        raise ValueError("model catalog is not an object")
    pricing_tiers = catalog.get("pricing_tiers", {})
    models: list[dict[str, Any]] = []
    model_semantics: list[dict[str, Any]] = []
    for model in catalog.get("models", []):
        row = dict(model)
        pricing = row.get("pricing")
        row["resolved_pricing"] = (
            pricing_tiers.get(pricing) if isinstance(pricing, str) else pricing
        )
        models.append(row)
        model_semantics.append(row)
    add_comparison_fields(models, model_semantics, "model")

    pricing_rows = [
        {"name": name, "pricing": value}
        for name, value in sorted(pricing_tiers.items())
    ]
    add_comparison_fields(pricing_rows, pricing_rows.copy(), "model-pricing")
    alias_rows = [
        {"name": name, "alias": value}
        for name, value in sorted(catalog.get("aliases", {}).items())
    ]
    add_comparison_fields(alias_rows, alias_rows.copy(), "model-alias")
    metadata_rows = [
        {
            "schema_version": catalog.get("schema_version"),
            "defaults": catalog.get("defaults", {}),
            "best": catalog.get("best"),
            "latest_per_family": catalog.get("latest_per_family", {}),
            "alias_migration": catalog.get("alias_migration", {}),
            "source_note": catalog.get("//"),
        }
    ]
    add_comparison_fields(metadata_rows, metadata_rows.copy(), "model-metadata")
    return models, pricing_rows, alias_rows, metadata_rows


def observability_template_rows(
    templates: list[dict[str, Any]], kind: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in templates:
        classifications = row.get("classifications", [])
        if kind == "url" and "url-template" in classifications:
            rows.append(dict(row))
        elif kind == "api" and "api-path-template" in classifications:
            rows.append(dict(row))
        elif kind == "observability" and "observability-template" in classifications:
            rows.append(dict(row))
    return rows


def call_offsets_with_template_arguments(
    calls: list[dict[str, Any]],
    template_nodes: list[dict[str, Any]],
    callees: set[str],
) -> set[int]:
    template_starts = [node["start"] for node in template_nodes]
    offsets: set[int] = set()
    for call in calls:
        if call["callee"] not in callees or not call["arguments"]:
            continue
        argument_start, argument_end = call["arguments"][0]
        index = bisect_right(template_starts, argument_start - 1)
        if index < len(template_starts) and template_starts[index] < argument_end:
            offsets.add(call["offset"])
    return offsets


def call_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        argument = row.get("nameArgument", {})
        kind = argument.get("kind", "missing")
        if "staticValue" in argument:
            counts["staticString"] += 1
        elif "templateShape" in argument:
            counts["template"] += 1
        elif "resolvedStaticValue" in argument:
            counts["resolvedStaticString"] += 1
        elif "resolvedTemplateShape" in argument:
            counts["resolvedTemplate"] += 1
        else:
            counts["dynamicOrUnresolved"] += 1
        counts[f"argumentKind:{kind}"] += 1
        payload = row.get("payload")
        if payload is not None:
            counts[f"payload:{payload.get('objectStatus', 'unknown')}"] += 1
            counts["unresolvedSpreads"] += len(payload.get("unresolvedSpreads", []))
    counts["total"] = len(rows)
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument(
        "--output",
        help="output directory; defaults to analysis/source-inventory under the repo",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    source_path = repo / "extracted/cli.js"
    if not source_path.is_file():
        raise SystemExit(f"missing canonical bundle: {source_path}")
    source = source_path.read_bytes()
    output = (
        Path(args.output).resolve()
        if args.output
        else repo / "analysis/source-inventory"
    )
    output.mkdir(parents=True, exist_ok=True)

    locator = LineLocator(source)
    discovered = discover_semantic_symbols(source)
    javascript_surface = load_javascript_surface(source_path, discovered)
    environment_like = {decode(value) for value in ENV_PREFIX_RE.findall(source)}
    direct_environment: set[str] = set()
    for match in ENV_PROCESS_RE.finditer(source):
        direct_environment.add(decode(match.group(1) or match.group(2)))
    proxy_pattern = re.compile(
        rb"\b"
        + re.escape(discovered["environmentProxy"].encode())
        + rb"\.([A-Z][A-Z0-9_]{2,})\b"
    )
    proxy_environment = static_values(proxy_pattern, source)
    environment = environment_like | direct_environment | proxy_environment

    first_party_events: set[str] = set()
    first_party_templates: set[str] = set()
    otel_events: set[str] = set()
    tengu_identifiers = static_values(TENGU_RE, source, 0)
    datadog_events = extract_datadog_allowlist(
        source,
        discovered["datadogAllowlist"],
        discovered["datadogTagFields"],
    )
    datadog_tag_fields = extract_datadog_fields(
        source,
        discovered["datadogTagFields"].encode(),
        discovered["datadogRedactedFields"].encode(),
    )
    datadog_redacted_fields = extract_datadog_fields(
        source,
        discovered["datadogRedactedFields"].encode(),
        discovered["datadogRedactedSet"].encode(),
    )
    spans: set[str] = set()
    feature_flags: set[str] = set()
    growthbook_keys: set[str] = set()
    models = static_values(MODEL_RE, source, 0)
    control_subtypes = sdk_control_subtypes(source, discovered["literalBuilder"])
    hook_events = {
        decode(value).strip("'\"") for value in HOOK_EVENT_RE.findall(source)
    }
    hook_events.update(static_values(HOOK_EVENT_NAME_RE, source))
    api_paths = static_values(API_PATH_RE, source)
    http_routes = static_values(HTTP_ROUTE_RE, source)
    runtime_requires = static_values(REQUIRE_RE, source)
    descriptions = static_values(SCHEMA_DESCRIPTION_RE, source, "description")
    errors = static_values(ERROR_MESSAGE_RE, source, "message")
    diagnostics = static_values(DIAGNOSTIC_MESSAGE_RE, source, "message")
    assigned_identifiers = static_values(STATIC_ASSIGNMENT_RE, source)
    builtin_tools = assigned_identifiers & BUILTIN_TOOL_NAMES
    named_components = static_values(NAMED_COMPONENT_RE, source)
    slash_commands = static_values(SLASH_COMMAND_RE, source)
    known_tools = tool_catalog(source)
    schema_properties = schema_property_identifiers(
        source, discovered["schemaBuilders"]
    )
    settings_keys: set[str] = set()
    storage_namespaces = static_values(STORAGE_NAMESPACE_RE, source)
    first_party_storage_namespaces = claude_storage_namespaces(source)
    config_directories = user_config_directories(
        source, discovered["userConfigDirectoriesVariable"]
    )
    beta_identifiers = static_values(BETA_IDENTIFIER_RE, source, 0)
    protocol_events = static_values(PROTOCOL_EVENT_RE, source, 0)
    enum_groups = static_enum_groups(source, discovered["enumBuilder"])
    first_party_event_fields: list[str] = []
    third_party_event_fields: list[str] = []
    first_party_env_fields = object_keys_after(
        source, b'return{platform:"",node_version:"",terminal:""'
    )
    first_party_event_schema_fields = object_keys_after(
        source, b'return{event_name:"",client_timestamp:void 0,model:""'
    )
    growthbook_event_fields = object_keys_after(
        source, b'return{event_id:"",timestamp:void 0,experiment_id:""'
    )
    urls = extract_urls(source)
    hosts: set[str] = set()
    for value in urls:
        try:
            host = urlparse(value).netloc.lower()
        except ValueError:
            continue
        if host:
            hosts.add(host)

    otel_env = {
        value
        for value in environment
        if value.startswith(("OTEL_", "ANT_OTEL_", "CLAUDE_CODE_OTEL_"))
        or value in {
            "CLAUDE_CODE_ENABLE_TELEMETRY",
            "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
            "ENABLE_ENHANCED_TELEMETRY_BETA",
            "DISABLE_TELEMETRY",
            "DISABLE_ERROR_REPORTING",
            "DO_NOT_TRACK",
        }
    }
    metric_rows = [
        "\t".join(
            [
                decode(match.group("name")),
                decode(match.group("unit") or b""),
                decode(match.group("description")),
            ]
        )
        for match in METRIC_RE.finditer(source)
    ]
    calls = javascript_surface["calls"]
    assignments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in javascript_surface["assignments"]:
        assignments[assignment["name"]].append(assignment)
    resolver = AssignmentResolver(source, assignments)
    tool_registrations, tool_factory = tool_registration_rows(
        source,
        javascript_surface.get("toolObjectCalls", []),
        resolver,
    )
    discovered["toolFactory"] = tool_factory

    roles = discovered["roles"]
    first_party_roles = {
        roles["firstPartyEvent"]: "firstPartyEvent",
        roles["firstPartyEventAsync"]: "firstPartyEventAsync",
    }
    first_party_callsites = callsite_rows(
        source,
        calls,
        first_party_roles,
        resolver,
        include_payload=True,
    )
    otel_callsites = callsite_rows(
        source,
        calls,
        {roles["otelStructuredEvent"]: "otelStructuredEvent"},
        resolver,
        include_payload=True,
    )
    feature_callsites = callsite_rows(
        source,
        calls,
        {roles["featureValue"]: "featureValue"},
        resolver,
        include_payload=False,
    )
    growthbook_callsites = callsite_rows(
        source,
        calls,
        {roles["dynamicConfig"]: "dynamicConfig"},
        resolver,
        include_payload=False,
    )
    error_callsites = message_callsite_rows(
        source,
        calls,
        {name: name for name in ("Error", "TypeError", "RangeError")},
        resolver,
    )
    diagnostic_callsites = message_callsite_rows(
        source,
        calls,
        {roles["diagnostic"]: "diagnostic"},
        resolver,
    )
    error_template_offsets = call_offsets_with_template_arguments(
        calls,
        javascript_surface["templates"],
        {"Error", "TypeError", "RangeError"},
    )
    diagnostic_template_offsets = call_offsets_with_template_arguments(
        calls, javascript_surface["templates"], {roles["diagnostic"]}
    )
    error_templates = [
        row for row in error_callsites if row["offset"] in error_template_offsets
    ]
    diagnostic_templates = [
        row
        for row in diagnostic_callsites
        if row["offset"] in diagnostic_template_offsets
    ]

    first_party_events = callsite_static_values(first_party_callsites)
    first_party_templates = {
        value
        for value in callsite_template_shapes(first_party_callsites)
        if value.startswith("tengu_")
    }
    otel_events = callsite_static_values(otel_callsites)
    feature_flags = callsite_static_values(feature_callsites)
    growthbook_keys = callsite_static_values(growthbook_callsites)
    first_party_event_fields = event_fields_from_callsites(first_party_callsites)
    third_party_event_fields = event_fields_from_callsites(otel_callsites)
    family_counts = Counter(event_family(value) for value in first_party_events)
    family_rows = [
        f"{family}\t{count}" for family, count in sorted(family_counts.items())
    ]
    metric_names = {row.split("\t", 1)[0] for row in metric_rows}
    spans = otel_span_names(source, metric_names)

    string_literals, template_literals = literal_rows(
        source, javascript_surface["strings"], javascript_surface["templates"]
    )
    url_templates = observability_template_rows(template_literals, "url")
    api_templates = observability_template_rows(template_literals, "api")
    observability_templates = observability_template_rows(
        template_literals, "observability"
    )
    environment_accesses = environment_access_rows(
        source, javascript_surface["environmentAccesses"]
    )
    dynamic_environment_accesses = [
        row
        for row in environment_accesses
        if row["accessor"] == "process.env.bracket" and row["name"] is None
    ]
    environment_schema = environment_schema_rows(
        source, locator, discovered["environmentBuilder"]
    )
    observability_environment_schema = [
        row for row in environment_schema if OBSERVABILITY_NAME_RE.search(row["name"])
    ]
    observability_environment_defaults = [
        row
        for row in environment_accesses
        if row.get("name")
        and OBSERVABILITY_NAME_RE.search(row["name"])
        and "fallbackExpression" in row
    ]
    settings_schema = root_settings_schema_rows(
        source,
        locator,
        discovered["rootSettingsFunction"],
        discovered["objectBuilder"],
        discovered["enumBuilder"],
    )
    settings_keys = {
        row["key"] for row in settings_schema if isinstance(row.get("key"), str)
    }
    schema_properties = schema_property_identifiers(
        source, discovered["schemaBuilders"]
    )
    schema_properties.update(settings_keys)
    model_catalog, model_pricing, model_aliases, model_metadata = model_catalog_rows(
        source, discovered["modelCatalog"]
    )
    telemetry_endpoints = {
        value
        for value in urls
        if re.search(
            r"otel|telemetr|event_logging|datadog|growthbook|metrics|traces|logs",
            value,
            re.IGNORECASE,
        )
    }
    observability_identifiers = {
        value
        for value in environment | tengu_identifiers | feature_flags | growthbook_keys
        if OBSERVABILITY_NAME_RE.search(value)
        or re.search(r"telemetr|otel|datadog|growthbook", value, re.IGNORECASE)
    }

    text_inventories: dict[str, set[str] | list[str]] = {
        "environment-access-identifiers.txt": environment,
        "direct-process-environment-accesses.txt": direct_environment,
        "environment-proxy-accesses.txt": proxy_environment,
        "environment-like-identifiers.txt": environment_like,
        "otel-environment-variables.txt": otel_env,
        "observability-identifiers.txt": observability_identifiers,
        "telemetry-endpoints.txt": telemetry_endpoints,
        "tengu-identifiers.txt": tengu_identifiers,
        "first-party-events.txt": first_party_events,
        "first-party-event-templates.txt": first_party_templates,
        "first-party-event-fields.tsv": first_party_event_fields,
        "first-party-event-families.tsv": family_rows,
        "first-party-event-schema-fields.txt": first_party_event_schema_fields,
        "first-party-environment-fields.txt": first_party_env_fields,
        "third-party-otel-events.txt": otel_events,
        "third-party-otel-event-fields.tsv": third_party_event_fields,
        "datadog-forwarded-events.txt": datadog_events,
        "datadog-tag-fields.txt": datadog_tag_fields,
        "datadog-redacted-fields.txt": datadog_redacted_fields,
        "otel-metrics.tsv": metric_rows,
        "otel-spans.txt": spans,
        "feature-flags.txt": feature_flags,
        "growthbook-keys.txt": growthbook_keys,
        "growthbook-event-fields.txt": growthbook_event_fields,
        "model-identifiers.txt": models,
        "anthropic-beta-identifiers.txt": beta_identifiers,
        "builtin-tool-identifiers.txt": builtin_tools,
        "known-tool-catalog.txt": known_tools,
        "named-component-identifiers.txt": named_components,
        "slash-command-identifiers.txt": slash_commands,
        "root-settings-keys.txt": settings_keys,
        "schema-property-identifiers.txt": schema_properties,
        "static-enum-groups.tsv": enum_groups,
        "sdk-control-subtypes.txt": control_subtypes,
        "output-protocol-event-identifiers.txt": protocol_events,
        "hook-events.txt": hook_events,
        "storage-namespaces.txt": storage_namespaces,
        "claude-storage-namespaces.txt": first_party_storage_namespaces,
        "user-config-directories.txt": config_directories,
        "api-paths.txt": api_paths,
        "http-route-identifiers.txt": http_routes,
        "runtime-requires.txt": runtime_requires,
        "schema-descriptions.txt": descriptions,
        "error-message-literals.txt": errors,
        "diagnostic-message-literals.txt": diagnostics,
        "urls.txt": urls,
        "endpoint-hosts.txt": hosts,
    }
    jsonl_inventories: dict[str, list[dict[str, Any]]] = {
        "first-party-event-callsites.jsonl": first_party_callsites,
        "otel-event-callsites.jsonl": otel_callsites,
        "feature-flag-callsites.jsonl": feature_callsites,
        "growthbook-callsites.jsonl": growthbook_callsites,
        "error-message-callsites.jsonl": error_callsites,
        "error-message-templates.jsonl": error_templates,
        "diagnostic-message-callsites.jsonl": diagnostic_callsites,
        "diagnostic-message-templates.jsonl": diagnostic_templates,
        "static-string-literals.jsonl": string_literals,
        "template-literals.jsonl": template_literals,
        "url-templates.jsonl": url_templates,
        "api-path-templates.jsonl": api_templates,
        "observability-templates.jsonl": observability_templates,
        "environment-access-callsites.jsonl": environment_accesses,
        "dynamic-process-environment-callsites.jsonl": dynamic_environment_accesses,
        "environment-schema.jsonl": environment_schema,
        "observability-environment-schema.jsonl": observability_environment_schema,
        "observability-environment-defaults.jsonl": observability_environment_defaults,
        "root-settings-schema.jsonl": settings_schema,
        "model-catalog.jsonl": model_catalog,
        "model-pricing-tiers.jsonl": model_pricing,
        "model-aliases.jsonl": model_aliases,
        "model-catalog-metadata.jsonl": model_metadata,
        "tool-registrations.jsonl": tool_registrations,
    }
    inventory_names = set(text_inventories) | set(jsonl_inventories)
    previous_summary = output / "summary.json"
    if previous_summary.is_file():
        try:
            previous = json.loads(previous_summary.read_text(encoding="utf-8"))
            for entry in previous.get("files", []):
                stale = output / Path(entry.get("path", "")).name
                if stale.parent == output and stale.name not in inventory_names:
                    stale.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    counts: dict[str, int] = {}
    for name, values in text_inventories.items():
        counts[Path(name).stem] = write_lines(output / name, values)
    for name, rows in jsonl_inventories.items():
        counts[Path(name).stem] = write_jsonl(output / name, rows)

    files = []
    for path in sorted(output.iterdir()):
        if not path.is_file() or path.name == "summary.json":
            continue
        files.append(
            {
                "path": f"analysis/source-inventory/{path.name}",
                "lines": sum(1 for _ in path.open("r", encoding="utf-8")),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    role_rows = {
        "firstPartyEvent": [
            row
            for row in first_party_callsites
            if row["calleeRole"] == "firstPartyEvent"
        ],
        "firstPartyEventAsync": [
            row
            for row in first_party_callsites
            if row["calleeRole"] == "firstPartyEventAsync"
        ],
        "otelStructuredEvent": otel_callsites,
        "featureValue": feature_callsites,
        "dynamicConfig": growthbook_callsites,
    }
    declaration_counts = Counter(javascript_surface.get("declarations", {}))
    settings_direct = [row for row in settings_schema if row.get("key") is not None]
    settings_spreads = [row for row in settings_schema if row["kind"] == "spread"]
    completion_gaps: list[str] = []
    for label, value in {
        "environment schema": environment_schema,
        "root settings schema": settings_schema,
        "model catalog": model_catalog,
        "model pricing tiers": model_pricing,
        "model aliases": model_aliases,
        "Datadog allowlist": datadog_events,
        "Datadog tag fields": datadog_tag_fields,
        "Datadog redacted fields": datadog_redacted_fields,
        "Claude storage key factory": first_party_storage_namespaces,
        "user config directories": config_directories,
        "schema property identifiers": schema_properties,
        "SDK control subtypes": control_subtypes,
        "first-party event callsites": first_party_callsites,
        "OTEL event callsites": otel_callsites,
        "feature-value callsites": feature_callsites,
        "dynamic-config callsites": growthbook_callsites,
        "tool registrations": tool_registrations,
    }.items():
        if not value:
            completion_gaps.append(f"detected subsystem produced no {label}")
    summary = {
        "formatVersion": 5,
        "version": (repo / "VERSION").read_text(encoding="utf-8").strip(),
        "canonicalSource": {
            "path": "extracted/cli.js",
            "size": source_path.stat().st_size,
            "sha256": sha256(source_path),
        },
        "javascriptParser": javascript_surface["parser"],
        "discoveredSymbols": discovered,
        "methods": {
            "symbolDiscovery": "stable export names, function-body literals, schema constructor shapes, catalog notes, and subsystem-specific field anchors discover release-local minified symbols before AST extraction",
            "callsiteParser": "vendored Acorn 8.15.0 parses the canonical bundle as ECMAScript latest; AST CallExpression/NewExpression nodes provide exact callsites, arguments, lexical function scopes, declaration exclusion, and nearest same-or-ancestor-scope assignment resolution",
            "payloadParser": "top-level object parser records properties, shorthand keys, computed keys, spreads, recursively expanded identifier/object spreads, and unresolved spread expressions for dynamically discovered event callsites",
            "literalSurface": "every Acorn string and template node is grouped by exact raw value with occurrence count and all source locations; long, credential-shaped, or user-home-shaped values keep length and SHA-256 instead of duplicating sensitive or very large text outside canonical extracted evidence",
            "environmentSchema": "joins uppercase export getters to variables assigned through the discovered str/bool/triBool/int/enum builder and records every static/dynamic process.env or discovered environment-proxy access",
            "rootSettingsSchema": "locates the settings function through strictPolicyHelperKeys plus $schema/apiKeyHelper anchors and parses every top-level entry and spread without relying on its minified function or builder name",
            "modelCatalog": "locates the hand-maintained baked catalog through its stable source note and parses complete per-model, pricing-tier, alias, and catalog-metadata JSONL records with resolved pricing",
            "toolRegistrations": "discovers the release-local tool-object factory from the Bash/Read/Write/Edit/Glob/Grep anchor set, then records every qualifying AST callsite to that factory, including statically resolved or retained dynamic name expressions, aliases, object-literal lifecycle properties, source offsets, and comparison fields; factory invocation expansion remains a separate human call-graph step",
            "claudeStorageNamespaces": "locates the product key factory from the stable transcript/journal/history/log prefix through sessionAliases and extracts every namespace in that bounded factory, including stream namespaces declared before globalConfig",
            "broadHeuristics": "environment-shaped identifiers, schema properties, URLs, namespaces, and named components can include bundled dependencies or embedded documentation and are not all user-supported Claude Code settings",
        },
        "coverage": {
            "targetCallsites": {
                role: {
                    "symbol": roles[role],
                    **call_coverage(rows),
                }
                for role, rows in role_rows.items()
            },
            "messageCallsites": {
                "Error+TypeError+RangeError": len(error_callsites),
                "ErrorTemplates": len(error_templates),
                "T": len(diagnostic_callsites),
                "TTemplates": len(diagnostic_templates),
            },
            "declarationsExcluded": dict(sorted(declaration_counts.items())),
            "literalOccurrences": {
                "quotedStrings": len(javascript_surface["strings"]),
                "uniqueQuotedStrings": len(string_literals),
                "templates": len(javascript_surface["templates"]),
                "uniqueTemplates": len(template_literals),
                "urlTemplates": len(url_templates),
                "apiPathTemplates": len(api_templates),
            },
            "environment": {
                "accessCallsites": len(environment_accesses),
                "dynamicProcessEnvCallsites": len(dynamic_environment_accesses),
                "typedSchemaEntries": len(environment_schema),
                "observabilitySchemaEntries": len(observability_environment_schema),
                "observabilityDefaults": len(observability_environment_defaults),
            },
            "settings": {
                "directEntries": len(settings_direct),
                "spreadEntries": len(settings_spreads),
            },
            "models": {
                "catalogEntries": len(model_catalog),
                "pricingTiers": len(model_pricing),
                "aliases": len(model_aliases),
            },
            "toolRegistrations": {
                "factorySymbol": tool_factory,
                "registrationCount": len(tool_registrations),
                "staticNameCount": sum(
                    1 for row in tool_registrations if row["name"] is not None
                ),
                "dynamicNameCount": sum(
                    1 for row in tool_registrations if row["name"] is None
                ),
            },
            "claudeStorage": {
                "namespaceCount": len(first_party_storage_namespaces),
                "requiredStreamNamespaces": sorted(
                    {"transcript", "history", "log"}
                    & first_party_storage_namespaces
                ),
            },
        },
        "completionAudit": {
            "allTargetCallsitesRecorded": all(
                counts.get(filename, -1) == expected
                for filename, expected in {
                    "first-party-event-callsites": len(first_party_callsites),
                    "otel-event-callsites": len(otel_callsites),
                    "feature-flag-callsites": len(feature_callsites),
                    "growthbook-callsites": len(growthbook_callsites),
                    "error-message-callsites": len(error_callsites),
                    "diagnostic-message-callsites": len(diagnostic_callsites),
                }.items()
            ),
            "allLexicalLiteralsRecorded": (
                sum(row["occurrenceCount"] for row in string_literals)
                == len(javascript_surface["strings"])
                and sum(row["occurrenceCount"] for row in template_literals)
                == len(javascript_surface["templates"])
            ),
            "dynamicExpressionsRetained": True,
            "rootSettingsKeysMatchStructuredRows": (
                settings_keys == {row["key"] for row in settings_direct}
            ),
            "modelCatalogParsed": bool(model_catalog and model_metadata),
            "environmentSchemaParsed": bool(environment_schema),
            "datadogSurfaceParsed": bool(
                datadog_events and datadog_tag_fields and datadog_redacted_fields
            ),
            "claudeStorageFactoryParsed": bool(
                first_party_storage_namespaces
                and {"transcript", "history", "log"}
                <= first_party_storage_namespaces
            ),
            "toolFactoryParsed": bool(
                tool_factory
                and tool_registrations
                and {"Bash", "Read", "Write", "Edit", "Glob", "Grep"}
                <= {
                    row["name"]
                    for row in tool_registrations
                    if row["name"] is not None
                }
            ),
            "semanticSymbolsDiscovered": len(discovered["roles"]) == 6,
            "knownStaticExtractionGaps": completion_gaps,
            "nonRecoverableBoundaries": [
                "runtime values returned by remote configuration, APIs, user files, environment variables, or server-side systems are not present as concrete release-bundle values",
                "source removed before shipping by minification, tree shaking, compilation, or absent source maps cannot be reconstructed from the release artifact",
                "retained dynamic expressions are inventoried verbatim but are not executed by the static extractor",
            ],
        },
        "counts": counts,
        "files": files,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    print(
        "source inventory: PASS"
        if not completion_gaps
        else "source inventory: FAIL"
    )
    print(f"inventory format: {summary['formatVersion']}")
    print(f"inventory files: {len(files)}")
    print(f"first-party callsites: {len(first_party_callsites)}")
    print(f"third-party OTEL callsites: {len(otel_callsites)}")
    print(f"feature-flag callsites: {len(feature_callsites)}")
    print(f"GrowthBook callsites: {len(growthbook_callsites)}")
    print(f"error callsites/templates: {len(error_callsites)}/{len(error_templates)}")
    print(
        f"diagnostic callsites/templates: {len(diagnostic_callsites)}/{len(diagnostic_templates)}"
    )
    print(
        "quoted/template literal occurrences: "
        f"{len(javascript_surface['strings'])}/{len(javascript_surface['templates'])}"
    )
    print(f"environment access/schema: {len(environment_accesses)}/{len(environment_schema)}")
    print(f"root settings entries: {len(settings_direct)} + {len(settings_spreads)} spreads")
    print(f"model catalog entries: {len(model_catalog)}")
    if completion_gaps:
        for gap in completion_gaps:
            print(f"gap: {gap}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
