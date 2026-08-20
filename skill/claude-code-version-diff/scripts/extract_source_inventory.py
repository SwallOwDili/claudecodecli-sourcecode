#!/usr/bin/env python3
"""Extract deterministic, cross-version inventories from the packed CLI bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
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


def static_values(pattern: re.Pattern[bytes], source: bytes, group: str | int = 1) -> set[str]:
    return {decode(match.group(group)) for match in pattern.finditer(source)}


def skip_quoted(source: bytes, index: int, quote: int) -> int:
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


def root_settings_keys(source: bytes) -> set[str]:
    marker = source.find(b"function M7t(e,{strictPolicyHelperKeys")
    if marker < 0:
        return set()
    opening = source.find(b"return ye({", marker)
    if opening < 0:
        return set()
    return object_keys(source, opening + len(b"return ye("))


def static_enum_groups(source: bytes) -> set[str]:
    groups: set[str] = set()
    for match in STATIC_ENUM_RE.finditer(source):
        values = [decode(value) for value in re.findall(rb"['\"]((?:\\.|[^'\"]){1,160})['\"]", match.group(1))]
        if values:
            groups.add(" | ".join(values))
    return groups


def static_event_fields(source: bytes, functions: set[str]) -> list[str]:
    fields: dict[str, set[str]] = {}
    for match in STATIC_EVENT_OBJECT_RE.finditer(source):
        function = decode(match.group("function"))
        if function not in functions:
            continue
        event = decode(match.group("event"))
        opening = match.end() - 1
        fields.setdefault(event, set()).update(object_keys(source, opening))
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


def user_config_directories(source: bytes) -> set[str]:
    match = re.search(rb'_Fd=\[([^\]]+)\],bFd=new Set\(_Fd\)', source)
    if not match:
        return set()
    return {decode(value) for value in re.findall(rb"['\"]([^'\"]+)['\"]", match.group(1))}


def tool_catalog(source: bytes) -> set[str]:
    values: set[str] = set()
    patterns = [
        rb'\[("Bash","BashOutput","KillShell","PowerShell".*?)\],imS=\[(.*?)\]',
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


def claude_storage_namespaces(source: bytes) -> set[str]:
    start = source.find(b'globalConfig:()=>({namespace:"globalConfig"})')
    if start < 0:
        return set()
    end = source.find(b'sessionAliases:', start)
    if end < 0:
        return set()
    end = source.find(b"}", end)
    return static_values(STORAGE_NAMESPACE_RE, source[start:end])


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


def extract_datadog_allowlist(source: bytes) -> set[str]:
    match = re.search(rb"LCd\s*=.*?new Set\(\[(.*?)\]\),\s*hsb\s*=", source, re.DOTALL)
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

    environment_like = {decode(value) for value in ENV_PREFIX_RE.findall(source)}
    direct_environment: set[str] = set()
    for match in ENV_PROCESS_RE.finditer(source):
        direct_environment.add(decode(match.group(1) or match.group(2)))
    proxy_environment = {decode(value) for value in ENV_PROXY_RE.findall(source)}
    environment = environment_like | direct_environment | proxy_environment

    first_party_events = static_values(FIRST_PARTY_EVENT_RE, source)
    first_party_templates = template_values(source)
    otel_events = static_values(OTEL_EVENT_RE, source)
    tengu_identifiers = static_values(TENGU_RE, source, 0)
    datadog_events = extract_datadog_allowlist(source)
    datadog_tag_fields = extract_datadog_fields(source, b"hsb", b"gsb")
    datadog_redacted_fields = extract_datadog_fields(source, b"gsb", b"ysb")
    spans = static_values(SPAN_RE, source)
    feature_flags = static_values(FEATURE_FLAG_RE, source)
    growthbook_keys = static_values(GROWTHBOOK_KEY_RE, source)
    models = static_values(MODEL_RE, source, 0)
    control_subtypes = static_values(CONTROL_SUBTYPE_RE, source)
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
    schema_properties = static_values(SCHEMA_PROPERTY_RE, source)
    settings_keys = root_settings_keys(source)
    storage_namespaces = static_values(STORAGE_NAMESPACE_RE, source)
    first_party_storage_namespaces = claude_storage_namespaces(source)
    config_directories = user_config_directories(source)
    beta_identifiers = static_values(BETA_IDENTIFIER_RE, source, 0)
    protocol_events = static_values(PROTOCOL_EVENT_RE, source, 0)
    enum_groups = static_enum_groups(source)
    first_party_event_fields = static_event_fields(source, {"H", "Fv"})
    third_party_event_fields = static_event_fields(source, {"Nd"})
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

    metric_rows = []
    for match in METRIC_RE.finditer(source):
        metric_rows.append(
            "\t".join(
                [
                    decode(match.group("name")),
                    decode(match.group("unit") or b""),
                    decode(match.group("description")),
                ]
            )
        )

    family_counts = Counter(event_family(value) for value in first_party_events)
    family_rows = [f"{family}\t{count}" for family, count in sorted(family_counts.items())]

    inventories: dict[str, set[str] | list[str]] = {
        "environment-access-identifiers.txt": environment,
        "direct-process-environment-accesses.txt": direct_environment,
        "environment-proxy-accesses.txt": proxy_environment,
        "environment-like-identifiers.txt": environment_like,
        "otel-environment-variables.txt": otel_env,
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

    previous_summary = output / "summary.json"
    if previous_summary.is_file():
        try:
            previous = json.loads(previous_summary.read_text(encoding="utf-8"))
            for entry in previous.get("files", []):
                stale = output / Path(entry.get("path", "")).name
                if stale.parent == output and stale.name not in inventories:
                    stale.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    counts = {
        name.removesuffix(".txt").removesuffix(".tsv"): write_lines(output / name, values)
        for name, values in inventories.items()
    }
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
    summary = {
        "formatVersion": 2,
        "version": (repo / "VERSION").read_text(encoding="utf-8").strip(),
        "canonicalSource": {
            "path": "extracted/cli.js",
            "size": source_path.stat().st_size,
            "sha256": sha256(source_path),
        },
        "methods": {
            "environmentAccessIdentifiers": "union of direct process.env accesses, the bundle's environment proxy property accesses, and environment-shaped static identifiers; this is not a claim that every identifier is a user-supported Claude Code setting",
            "directProcessEnvironmentAccesses": "static property and bracket accesses on process.env",
            "environmentProxyAccesses": "static uppercase properties read from the minified environment proxy object K; dependency and application accesses may both be present",
            "environmentLikeIdentifiers": "uppercase static tokens with selected environment prefixes; intentionally broad and may include dependency constants and dynamic prefixes",
            "firstPartyEvents": "static string first arguments to H/Fv analytics calls",
            "firstPartyEventTemplates": "template-literal first arguments to H/Fv with expressions normalized to ${}",
            "firstPartyEventFields": "union of explicit top-level object keys at static H/Fv event callsites; rows with no explicit keys use <no-static-fields>, while computed spreads and variable payloads are not expanded",
            "firstPartySchemas": "static top-level fields from the bundled first-party environment, internal event, and GrowthBook protobuf-compatible object schemas",
            "thirdPartyOtelEvents": "static string first arguments to Nd structured event calls",
            "thirdPartyOtelEventFields": "union of explicit top-level object keys at static Nd callsites; computed spreads are not expanded",
            "featureFlags": "static string first arguments to et feature checks",
            "growthbookKeys": "static string first arguments to CB GrowthBook config reads",
            "builtinTools": "known first-party tool names recovered from static variable assignments; dynamic MCP/plugin tools are outside this set",
            "knownToolCatalog": "union of the bundled tool normalization catalog and exported BUILTIN_TOOL_NAMES arrays; includes internal, hosted, and selected static MCP tool identifiers",
            "namedComponents": "static name fields immediately followed by a description field; includes built-in commands/tools plus named bundled dependency components",
            "slashCommands": "static name fields in command objects whose type is local, local-jsx, or prompt",
            "rootSettingsKeys": "top-level static keys in the M7t Claude Code settings schema object",
            "schemaProperties": "static property identifiers whose value begins with a recognized bundled schema-builder call; includes Claude Code and bundled dependency schemas",
            "staticEnumGroups": "static string arrays passed to the bundled Nr enum schema helper",
            "storageNamespaces": "static namespace field literals; includes Claude Code storage plus bundled dependency namespaces",
            "claudeStorageNamespaces": "namespace literals in the Claude Code storage key factory from globalConfig through sessionAliases",
            "apiPathsAndRoutes": "static API path literals plus separately listed METHOD /path route identifiers; dynamic path templates remain in canonical source",
            "protocolEvents": "known user/agent/session/span domain event identifiers found as static strings; documentation strings embedded in the bundle may contribute identifiers",
            "anthropicBetas": "date-suffixed lowercase identifiers embedded in the bundle; includes Anthropic API beta identifiers and provider API-version identifiers",
            "schemaDescriptions": "unique static .describe() literals; includes settings and protocol schemas",
            "errorsAndDiagnostics": "unique static Error/TypeError/RangeError and T() message literals; dynamic templates remain in canonical source",
        },
        "counts": counts,
        "files": files,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("source inventory: PASS")
    print(f"first-party events: {len(first_party_events)}")
    print(f"first-party event templates: {len(first_party_templates)}")
    print(f"third-party OTEL events: {len(otel_events)}")
    print(f"OTEL metrics: {len(metric_rows)}")
    print(f"OTEL spans: {len(spans)}")
    print(f"environment variables: {len(environment)}")
    print(f"direct process.env accesses: {len(direct_environment)}")
    print(f"feature flags: {len(feature_flags)}")
    print(f"GrowthBook keys: {len(growthbook_keys)}")
    print(f"root settings keys: {len(settings_keys)}")
    print(f"built-in tool identifiers: {len(builtin_tools)}")
    print(f"known tool catalog: {len(known_tools)}")
    print(f"slash commands: {len(slash_commands)}")
    print(f"named component identifiers: {len(named_components)}")
    print(f"schema descriptions: {len(descriptions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
