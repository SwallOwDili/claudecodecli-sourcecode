#!/usr/bin/env python3
"""Build the deterministic Claude Code 2.1.235 telemetry event catalog."""

from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Sequence


EXPECTED_VERSION = "2.1.235"
EXPECTED_COUNTS = {
    "first-party-events": 1441,
    "first-party-event-callsites": 2194,
    "datadog-forwarded-events": 181,
    "datadog-redacted-fields": 26,
    "datadog-tag-fields": 34,
    "third-party-otel-events": 26,
    "otel-event-callsites": 52,
    "otel-metrics": 8,
    "otel-spans": 10,
}
EXPECTED_FIRST_PARTY_NAME_KINDS = {
    "string": 2151,
    "identifier": 24,
    "conditional": 9,
    "member-or-call": 7,
    "template": 3,
}
EXPECTED_DYNAMIC_NAME_KINDS = {
    "identifier": 24,
    "conditional": 9,
    "member-or-call": 7,
    "template": 3,
}
EXPECTED_FIRST_PARTY_ROLES = {
    "firstPartyEvent": 2162,
    "firstPartyEventAsync": 32,
}
EXPECTED_FIRST_PARTY_CALLEES = {"H": 2162, "Fv": 32}
EXPECTED_FIRST_PARTY_PAYLOADS = {
    "static-object": 1860,
    "not-static-object": 334,
}
EXPECTED_FIRST_PARTY_UNRESOLVED_SPREADS = 524
EXPECTED_FIRST_PARTY_FUNCTIONS = 940
EXPECTED_OTEL_NAME_KINDS = {"string": 49, "identifier": 2, "template": 1}
EXPECTED_OTEL_PAYLOADS = {"static-object": 51, "not-static-object": 1}
EXPECTED_OTEL_UNRESOLVED_SPREADS = 72
EXPECTED_OTEL_FUNCTIONS = 35

PREFIX_FAMILIES = {
    "tengu_agent",
    "tengu_api",
    "tengu_artifact",
    "tengu_auto",
    "tengu_bg",
    "tengu_bridge",
    "tengu_chrome",
    "tengu_compact",
    "tengu_config",
    "tengu_daemon",
    "tengu_hook",
    "tengu_ide",
    "tengu_lsp",
    "tengu_mcp",
    "tengu_memory",
    "tengu_oauth",
    "tengu_permission",
    "tengu_plugin",
    "tengu_prompt",
    "tengu_remote",
    "tengu_sandbox",
    "tengu_sdk",
    "tengu_session",
    "tengu_tool",
    "tengu_ultrareview",
    "tengu_voice",
    "tengu_workflow",
    "tengu_worktree",
}

SOURCE_FILES = (
    "first-party-events.txt",
    "first-party-event-callsites.jsonl",
    "first-party-event-families.tsv",
    "first-party-event-fields.tsv",
    "datadog-forwarded-events.txt",
    "datadog-redacted-fields.txt",
    "datadog-tag-fields.txt",
    "third-party-otel-events.txt",
    "third-party-otel-event-fields.tsv",
    "otel-event-callsites.jsonl",
    "otel-metrics.tsv",
    "otel-spans.txt",
)

SEMANTIC_INDEX_EVENTS = {
    "tengu_api_query",
    "tengu_api_retry",
    "tengu_api_success",
    "tengu_api_error",
    "tengu_tool_use_show_permission_request",
    "tengu_tool_use_can_use_tool_allowed",
    "tengu_tool_use_can_use_tool_rejected",
    "tengu_tool_use_success",
    "tengu_tool_use_error",
    "tengu_tool_use_cancelled",
    "tengu_permission_explainer_generated",
    "tengu_permission_explainer_error",
    "tengu_permission_request_option_selected",
    "tengu_reactive_compact_triggered",
    "tengu_reactive_compact_attempt",
    "tengu_reactive_compact_succeeded",
    "tengu_reactive_compact_failed",
    "tengu_session_start",
    "tengu_session_resumed",
    "tengu_session_persistence_failed",
    "tengu_mcp_server_needs_auth",
    "tengu_mcp_oauth_flow_start",
    "tengu_mcp_oauth_flow_success",
    "tengu_mcp_oauth_flow_failure",
    "tengu_mcp_oauth_flow_error",
    "tengu_mcp_tool_call_auth_error",
    "tengu_bg_dispatch",
    "tengu_bg_dispatch_rejected",
    "tengu_bg_dispatch_fallback",
    "tengu_bg_dispatch_rescued",
    "tengu_bg_agent_terminal",
    "tengu_oauth_flow_start",
    "tengu_oauth_auth_code_received",
    "tengu_oauth_token_exchange_success",
    "tengu_oauth_success",
    "tengu_oauth_error",
    "tengu_query_error",
    "tengu_uncaught_exception",
    "tengu_unhandled_rejection",
    "tengu_transcript_write_failed",
    "tengu_transcript_writer_recovered",
}

SENSITIVITY_RULES = {
    "identity": {
        "account",
        "customer",
        "device",
        "email",
        "identity",
        "member",
        "organization",
        "org",
        "owner",
        "profile",
        "tenant",
        "user",
        "username",
    },
    "path/content": {
        "body",
        "command",
        "content",
        "cwd",
        "detail",
        "directory",
        "file",
        "filename",
        "input",
        "message",
        "output",
        "path",
        "prompt",
        "query",
        "response",
        "result",
        "text",
        "transcript",
    },
    "credential/network": {
        "api",
        "auth",
        "bearer",
        "certificate",
        "cookie",
        "credential",
        "endpoint",
        "header",
        "host",
        "hostname",
        "ip",
        "jwt",
        "key",
        "network",
        "password",
        "port",
        "proxy",
        "secret",
        "token",
        "url",
    },
    "stable identifier/hash": {
        "fingerprint",
        "hash",
        "id",
        "identifier",
        "request",
        "session",
        "sha",
        "uuid",
    },
    "operational": {
        "attempt",
        "build",
        "code",
        "cost",
        "count",
        "duration",
        "error",
        "event",
        "failure",
        "latency",
        "mode",
        "model",
        "provider",
        "reason",
        "status",
        "success",
        "time",
        "timestamp",
        "type",
        "usage",
        "version",
    },
}


def fail(message: str) -> None:
    raise SystemExit(f"telemetry catalog validation failed: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_count(data: bytes) -> int:
    return len(data.decode("utf-8").splitlines())


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(read_lines(path), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"{path.name}:{number}: invalid JSON: {exc}")
        require(isinstance(value, dict), f"{path.name}:{number}: row is not an object")
        rows.append(value)
    return rows


def read_two_column_tsv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, line in enumerate(read_lines(path), start=1):
        parts = line.split("\t", 1)
        require(len(parts) == 2, f"{path.name}:{number}: expected two TSV columns")
        key, value = parts
        require(key not in result, f"{path.name}:{number}: duplicate key {key!r}")
        result[key] = value
    return result


def source_text(value: dict[str, Any]) -> str:
    source = value.get("source")
    if not isinstance(source, dict):
        return "<source unavailable>"
    text = source.get("text")
    return text if isinstance(text, str) else "<source unavailable>"


def sorted_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value) for value in values})


def code_span(value: Any) -> str:
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    runs = [len(match.group(0)) for match in re.finditer(r"`+", text)]
    fence = "`" * (max(runs, default=0) + 1)
    if text.startswith(("`", " ")) or text.endswith(("`", " ")) or "`" in text:
        return f"{fence} {text} {fence}"
    return f"{fence}{text}{fence}"


def code_list(values: Iterable[Any], empty: str = "none") -> str:
    items = sorted_unique(values)
    return ", ".join(code_span(item) for item in items) if items else empty


def table_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def position(row: dict[str, Any]) -> tuple[int, int, int]:
    return (int(row["line"]), int(row["column"]), int(row["offset"]))


def position_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str, str]:
    return (
        int(row["offset"]),
        int(row["line"]),
        int(row["column"]),
        str(row.get("function", "")),
        str(row.get("callee", "")),
    )


def format_position(row: dict[str, Any]) -> str:
    line, column, offset = position(row)
    return f"L{line}:C{column}@{offset}"


def function_label(row: dict[str, Any]) -> str:
    function = row.get("function")
    display = "<anonymous>" if function is None else str(function)
    return f"{row.get('functionKind')}:{display}"


def payload_keys(rows: Sequence[dict[str, Any]], key: str) -> list[str]:
    return sorted_unique(
        field
        for row in rows
        for field in row.get("payload", {}).get(key, [])
    )


def unresolved_spreads(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        spread
        for row in rows
        for spread in row.get("payload", {}).get("unresolvedSpreads", [])
        if isinstance(spread, dict)
    ]


def format_counter(counter: collections.Counter[str]) -> str:
    return ", ".join(f"{code_span(key)} {counter[key]}" for key in sorted(counter))


def field_tokens(field: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", field)
    return {part for part in re.split(r"[^A-Za-z0-9]+", separated.lower()) if part}


def sensitivity_hits(fields: Iterable[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for field in sorted_unique(fields):
        tokens = field_tokens(field)
        for group, keywords in SENSITIVITY_RULES.items():
            if tokens & keywords:
                result.setdefault(group, []).append(field)
    return result


def format_sensitivity(fields: Iterable[str]) -> str:
    hits = sensitivity_hits(fields)
    if not hits:
        return "no configured field-name keyword hit"
    parts = []
    for group in SENSITIVITY_RULES:
        if group in hits:
            parts.append(f"{group}: {code_list(hits[group])}")
    return "; ".join(parts)


def parse_field_map(path: Path) -> dict[str, list[str]]:
    raw = read_two_column_tsv(path)
    result: dict[str, list[str]] = {}
    for event, value in raw.items():
        result[event] = [] if value == "<no-static-fields>" else value.split(",")
    return result


def family_projection(event: str, families: Sequence[str]) -> str:
    candidates = [family for family in families if event == family]
    candidates.extend(
        family
        for family in families
        if family in PREFIX_FAMILIES and event.startswith(family + "_")
    )
    if not candidates:
        return "tengu_other"
    return max(candidates, key=lambda family: (len(family), family))


def quoted_literals(expression: str) -> set[str]:
    return set(re.findall(r"[\"']([^\"']+)[\"']", expression))


def verify_source_files(
    inventory: Path,
    summary: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    files = summary.get("files")
    require(isinstance(files, list), "summary.json files is not a list")
    by_path = {
        entry["path"]: entry
        for entry in files
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    verified: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILES:
        relative = f"analysis/source-inventory/{name}"
        require(relative in by_path, f"summary.json does not register {relative}")
        path = inventory / name
        require(path.is_file(), f"missing source inventory {relative}")
        data = path.read_bytes()
        actual = {
            "path": relative,
            "lines": line_count(data),
            "size": len(data),
            "sha256": sha256_bytes(data),
        }
        expected = by_path[relative]
        for key in ("lines", "size", "sha256"):
            require(
                actual[key] == expected.get(key),
                f"{relative} {key} is {actual[key]!r}, expected {expected.get(key)!r}",
            )
        verified[name] = actual
    return verified


def validate_exact_counts(summary: dict[str, Any]) -> None:
    require(summary.get("version") == EXPECTED_VERSION, "summary version mismatch")
    counts = summary.get("counts")
    require(isinstance(counts, dict), "summary.json counts is not an object")
    for key, expected in EXPECTED_COUNTS.items():
        require(counts.get(key) == expected, f"summary count {key} != {expected}")


def aggregate_by_static_event(
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    dynamic: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("nameArgument", {}).get("staticValue")
        if isinstance(name, str):
            grouped[name].append(row)
        else:
            dynamic.append(row)
    for event_rows in grouped.values():
        event_rows.sort(key=position_sort_key)
    dynamic.sort(key=position_sort_key)
    return dict(grouped), dynamic


def validate_first_party(
    events: Sequence[str],
    fields: dict[str, list[str]],
    families: dict[str, int],
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, str]]:
    require(len(rows) == EXPECTED_COUNTS["first-party-event-callsites"], "first-party row count")
    require(
        collections.Counter(row["nameArgument"]["kind"] for row in rows)
        == EXPECTED_FIRST_PARTY_NAME_KINDS,
        "first-party name kind counts",
    )
    require(
        collections.Counter(row["calleeRole"] for row in rows) == EXPECTED_FIRST_PARTY_ROLES,
        "first-party role counts",
    )
    require(
        collections.Counter(row["callee"] for row in rows) == EXPECTED_FIRST_PARTY_CALLEES,
        "first-party callee counts",
    )
    require(
        collections.Counter(row["payload"]["objectStatus"] for row in rows)
        == EXPECTED_FIRST_PARTY_PAYLOADS,
        "first-party payload status counts",
    )
    require(
        sum(len(row["payload"].get("unresolvedSpreads", [])) for row in rows)
        == EXPECTED_FIRST_PARTY_UNRESOLVED_SPREADS,
        "first-party unresolved spread count",
    )
    require(
        len({str(row.get("function")) for row in rows}) == EXPECTED_FIRST_PARTY_FUNCTIONS,
        "first-party unique function count",
    )

    grouped, dynamic = aggregate_by_static_event(rows)
    require(len(dynamic) == 43, "first-party dynamic callsites != 43")
    require(
        collections.Counter(row["nameArgument"]["kind"] for row in dynamic)
        == EXPECTED_DYNAMIC_NAME_KINDS,
        "dynamic first-party kind counts",
    )
    require(sorted(grouped) == sorted(events), "static first-party names differ from event inventory")
    require(sorted(fields) == sorted(events), "first-party field map names differ from event inventory")
    for event in sorted(events):
        expanded = payload_keys(grouped[event], "expandedKeys")
        require(expanded == fields[event], f"expanded field map mismatch for {event}")

    family_names = sorted(families)
    projections = {event: family_projection(event, family_names) for event in events}
    projected_counts = collections.Counter(projections.values())
    require(dict(sorted(projected_counts.items())) == dict(sorted(families.items())), "family projection counts")
    return grouped, dynamic, projections


def validate_otel(
    events: Sequence[str],
    fields: dict[str, list[str]],
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    require(len(rows) == EXPECTED_COUNTS["otel-event-callsites"], "OTEL row count")
    require(
        collections.Counter(row["nameArgument"]["kind"] for row in rows)
        == EXPECTED_OTEL_NAME_KINDS,
        "OTEL name kind counts",
    )
    require(
        collections.Counter(row["payload"]["objectStatus"] for row in rows)
        == EXPECTED_OTEL_PAYLOADS,
        "OTEL payload status counts",
    )
    require(
        sum(len(row["payload"].get("unresolvedSpreads", [])) for row in rows)
        == EXPECTED_OTEL_UNRESOLVED_SPREADS,
        "OTEL unresolved spread count",
    )
    require(
        len({str(row.get("function")) for row in rows}) == EXPECTED_OTEL_FUNCTIONS,
        "OTEL unique function count",
    )
    grouped, dynamic = aggregate_by_static_event(rows)
    require(sorted(grouped) == sorted(events), "static OTEL names differ from event inventory")
    require(sorted(fields) == sorted(events), "OTEL field map names differ from event inventory")
    require(len(dynamic) == 3, "OTEL dynamic callsites != 3")
    for event in sorted(events):
        expanded = payload_keys(grouped[event], "expandedKeys")
        require(expanded == fields[event], f"OTEL expanded field map mismatch for {event}")
    return grouped, dynamic


def render_header(version: str) -> list[str]:
    return [
        f"# Claude Code {version} 遥测事件目录",
        "",
        "> 版本证据：`Static`（已发布 bundle 的 AST 清单）+ `Derived`（确定性聚合）+ `Heuristic`（字段名启发式）+ `Boundary`（静态包无法证明的运行时/服务端状态）。",
        "",
        "<!-- TELEMETRY_EVENT_CATALOG_BEGIN -->",
        "<!-- first-party-events:1441 -->",
        "<!-- first-party-callsites:2194 -->",
        "<!-- resolved-callsites:2151 -->",
        "<!-- dynamic-callsites:43 -->",
        "<!-- datadog-allowlist:181 -->",
        "<!-- otel-events:26 -->",
        "<!-- otel-callsites:52 -->",
        "<!-- otel-metrics:8 -->",
        "<!-- otel-spans:10 -->",
        "<!-- TELEMETRY_EVENT_CATALOG_END -->",
        "",
        "## 60 秒看懂：一条事件如何走到不同出口",
        "",
        "**读者问题：** Claude Code 里一次工具调用、API 请求、压缩或错误到底会留下什么事件？事件从哪个客户端通道产生、携带哪些静态可见字段、是否具备 Datadog 转发资格，又有哪些信息仅凭发布包无法证明？",
        "",
        "这份目录把 1,441 个静态一方事件和 43 个动态事件名调用点分开：前者可以按名字聚合，后者只能保留表达式与位置，不能伪装成已经解析的产品事件。",
        "",
        "**一句话模型：** 业务组件在本地调用通道专属 logger 形成事件候选，客户端再按门控、采样、队列、批处理和 exporter 配置决定是否尝试发送；静态事件名或 Datadog allowlist 命中都不等于运行时已经上报，更不证明服务端接受或保留。",
        "",
        "![事件候选从本地 logger 进入一方、Datadog 和 OTEL 出口的生命周期](visuals/telemetry-event-catalog-lifecycle.svg)",
        "",
        "贯穿场景：用户发起一次请求，Agent 调用工具，权限层作出决定，工具返回结果，随后上下文触发 compact。这个场景可以同时遇到两组互不等价的记录面：",
        "",
        "1. 一方业务代码可能调用 `H` / `Fv` 记录 `tengu_tool_use_success`、`tengu_api_success`、`tengu_compact` 等候选事件。它们先进入一方队列，再受共享非必要流量门、远程采样和 batch exporter 控制。",
        "2. 管理员显式启用 OTEL 后，代码中的 `Nd` 调用点可形成 `tool`、`tool_decision`、`tool_result`、`compaction` 等 structured event，并交给管理员配置的 exporter。",
        "3. 若一方事件名位于 Datadog 的 181 项 allowlist，它只获得进入该转发分支的资格；first-party provider、feature gate、killswitch、初始化、限流与发送成功仍是额外条件。",
        "4. 同一动作没有“一条万能遥测记录”。不同通道拥有不同 gate、字段处理、队列和目的地，不能拿一个通道的开关或删除字段推断另一个通道。",
        "",
        "### 通道所有权表",
        "",
        "| 状态 owner / 通道组件 | 客户端拥有的状态 | 本目录能证明 | 本目录不能证明 |",
        "| --- | --- | --- | --- |",
        "| 业务调用点 | 事件名表达式、payload 表达式、所在函数与源码位置 | `H` / `Fv` / `Nd` 的静态调用形状 | 某次真实会话一定执行到该分支 |",
        "| 一方 `H` / `Fv` 流水线 | sink、预初始化队列、采样结果、batch queue、失败批次 | 2,194 个调用点和 1,441 个可静态聚合的名字 | 当前账号/组织最终是否允许发送 |",
        "| Datadog 转发分支 | allowlist、字段删除、tag 归一化、分支限流 | 181 个允许名、26 个删除字段、34 个 tag 字段 | allowlist 命中的事件已实际到达 Datadog |",
        "| 第三方 OTEL | enable gate、signal exporter、content gate、resource attributes | 26 个事件、52 个调用点、8 个 metric、10 个 span | 管理员 collector 的落盘、转发和保留策略 |",
        "| 服务端/collector | 接受、拒绝、二次处理、保留和访问控制 | 客户端请求形状之外没有静态证据 | Anthropic 服务端或管理员 collector 的最终处理 |",
        "",
        "`tengu_other` 只是本生成器的 `Derived` 投影兜底桶：它表示事件名没有命中 release-local family 规则，不是产品 owner、模块边界或服务端分类。像 `tengu_background` 这类 singleton label 只匹配同名事件，不会自动吞并所有同前缀名字。",
        "",
        "## 字段怎么读",
        "",
        "| 字段 | 证据等级 | 正确解释 |",
        "| --- | --- | --- |",
        "| event name | `Static` | AST 已把第一个参数解析成固定字符串；同名调用点可聚合 |",
        "| family projection | `Derived` | 复现 release-local extractor：eligible family prefixes 做最长匹配，singleton labels 只做 exact match；仅用于导航和跨版本统计 |",
        "| call count | `Derived` from `Static` | 发布包中同名静态调用点数量，不是生产上报次数 |",
        "| logger role / callee | `Static` | 稳定角色和版本本地短符号；`H` 与 `Fv` 分别是一方同步/异步入口 |",
        "| function | `Static` | AST 记录的词法函数；压缩名用于定位，不等于原始 TypeScript 名 |",
        "| line / column / offset | `Static` | canonical 位置取最小 offset；所有位置仍列出，便于回到 `extracted/cli.js` |",
        "| direct keys | `Static` | payload 顶层对象中直接出现的属性 |",
        "| expanded keys | `Static` | direct keys 加上能在词法作用域解析的 object/identifier spread；与事件字段 TSV 精确对齐 |",
        "| shorthand keys | `Static` | `{foo}` 这类简写属性；它们也属于 direct/expanded 字段 |",
        "| unresolved spread | `Boundary` | 表达式被完整保留，但静态分析不能列出运行时展开字段；这不等于运行时没有字段 |",
        "| Datadog allowlist | `Static` | 事件名存在于允许集合，只代表分支资格，不证明 gate、采样、初始化或发送结果 |",
        "| field-name sensitivity | `Heuristic` | 只按字段名 token 命中 identity、path/content、credential/network、identifier/hash、operational 词表；命中不证明值敏感，未命中也不证明安全 |",
        "",
        "## 隐私、采样、批处理、失败和服务端边界",
        "",
        "- **隐私：** 一方 envelope、Datadog 归一化和 OTEL content gate 是不同层。Datadog 的 26 个删除字段只约束 Datadog 分支；OTEL prompt/tool/response 正文还受独立开关和长度上限控制；字段名启发式不能替代值级审计。",
        "- **采样：** 一方事件可按事件名读取 `sample_rate`。缺少/非法/等于 1 时不额外采样，`<= 0` 丢弃，`0 < rate < 1` 才随机判定。目录中的调用点不会因为运行时未采中而消失。",
        "- **队列与批处理：** 一方 sink 安装前 FIFO 上限 1,000，logger 初始化前队列上限 1,024；默认 provider queue 8,192、batch 200、flush 10 秒、请求 timeout 10 秒。Datadog 默认 batch 100、flush 15 秒、timeout 5 秒。",
        "- **失败：** 一方 exporter 的连续失败周期默认最多 8 attempts，二次 backoff 在 500 ms 到 30 s 之间；剩余 batch 可写入本地 telemetry storage，部分成功时只重写未发送部分。HTTP 401 还存在去认证头的单次 fallback。OTEL 默认 flush timeout 5 s、shutdown timeout 2 s；超时只说明客户端停止等待，不能证明 collector 最终收到了积压。调用点清单本身不记录某次发送结果。",
        "- **服务端边界：** bundle 能证明客户端分支、字段和 transport 形状，不能证明服务端接收、去重、聚合、告警、保留期限、账号风控或人工访问。任何此类结论都需要 wire capture、服务端配置或服务端证据。",
        "",
    ]


def render_lifecycle_and_impact() -> list[str]:
    return [
        "## 从事件产生到各出口的有序生命周期",
        "",
        "下面按一次真实业务动作可能经过的顺序拆开状态。`H` / `Fv` 的一方通道与 `Nd` 的 OTEL 通道可以由同一业务动作分别调用，但没有证据表明一个 logger 自动复制成另一个 logger。",
        "",
        "| Phase | 输入与 owner | 状态变化 | 成功后交给谁 | 失败/边界 |",
        "| ---: | --- | --- | --- | --- |",
        "| 1 | 业务分支调用 `H(name, payload)`、`Fv(name, payload)` 或 `Nd(name, attributes)` | 固定 name 被记录为 `Static`；动态 name 保留表达式 | 对应通道的本地 logger | 代码分支未执行时不会产生候选事件；静态存在不等于运行时发生 |",
        "| 2 | 一方全局 sink | sink 未安装时写入 FIFO，最多 1,000，满时删除最旧项并累计 dropped | sink 安装后以 microtask 排空 | 被 FIFO 淘汰的候选不会由后续安装恢复 |",
        "| 3 | 一方 logger provider | provider 尚未初始化时进入第二层 pre-init queue，最多 1,024；初始化完成后顺序重放 | sampling / provider logger | 超限的新事件不进入队列；provider 重建时先 force-flush，失败则恢复旧 provider/logger |",
        "| 4 | 一方共享流量门与远程采样 | `DISABLE_TELEMETRY`、`DO_NOT_TRACK`、nonessential-traffic 状态和 event sampling config 决定保留/丢弃 | 一方 exporter；同一 sampling 结果也约束 Datadog 候选 | `rate <= 0` 丢弃；`0 < rate < 1` 随机；缺失/非法/1 不额外采样 |",
        "| 5 | 一方 envelope builder | 合并 session/model/environment/process/identity 等公共 metadata 与 event-specific payload | BatchSpanProcessor / exporter queue | 本目录的 direct/expanded keys 只描述 event payload，不等于完整 envelope 每次都填满 |",
        "| 6 | 一方 batch exporter | 默认 queue 8,192、batch 200、flush 10 s、HTTP timeout 10 s | `event_logging/v2/batch` 请求 | queue/batch 配置可被远程 config 改写；目录不记录某次采用的运行时值 |",
        "| 7 | 一方 HTTP 与认证 fallback | 带基础 headers 和可用认证发送；401 时去掉认证头再试一次 | 成功会清零 exporter 当前连续失败计数 | 服务端接受、去重、存储和风控不可由客户端调用点证明 |",
        "| 8 | 一方失败恢复 | 剩余 batch 写入 telemetry storage；部分成功只重写未发送事件 | 启动/后续扫描重试 legacy 文件或 v5 stream | 默认连续失败周期 8 attempts；二次 backoff 500 ms 到 30 s；进程重启不会继承内存 attempt counter |",
        "| 9 | Datadog forwarding 分支 | first-party provider + feature gate + killswitch + 181 allowlist + sampling 共同决定资格；删除 26 字段并构造 34 个 tags | 默认 batch 100、flush 15 s、timeout 5 s 的 Datadog client | allowlist 命中不是发送证据；分支还有 peer-rate-bound 和 key 淘汰 |",
        "| 10 | OTEL `Nd` 与 SDK | `CLAUDE_CODE_ENABLE_TELEMETRY`、signal exporter、protocol/endpoint/header 与 content gates 决定构造和导出 | console、OTLP 或 Prometheus（metrics）等管理员目的地 | 默认 prompt 正文可被 redaction；collector 的保存/转发是管理员边界 |",
        "| 11 | flush / shutdown | 一方、Datadog、OTEL 各自处理积压；OTEL 默认 flush timeout 5 s、shutdown timeout 2 s | 进程退出 | timeout 后不能由静态目录证明积压是否到达目的地；已发生的工具/API 外部副作用不会因遥测失败回滚 |",
        "",
        "### 可读源码证据锚点",
        "",
        "以下链接指向同一 2.1.235 readable view，不使用本机绝对路径：",
        "",
        "1. [全局 sink/FIFO 与排空路径](../reverse/javascript/cli.readable.js#L5310-L5352)。",
        "2. [错误上报的 provider/auth/policy/compliance gates](../reverse/javascript/cli.readable.js#L73690-L73880)。",
        "3. [一方 batch endpoint 与 exporter 构造](../reverse/javascript/cli.readable.js#L77540-L77570)。",
        "4. [失败 batch 文件/stream 持久化与恢复](../reverse/javascript/cli.readable.js#L77920-L77970)。",
        "5. [一方 provider、pre-init queue、flush/rebuild](../reverse/javascript/cli.readable.js#L77970-L78100)。",
        "6. [sampling config 与 batch config 读取](../reverse/javascript/cli.readable.js#L78090-L78110)。",
        "7. [Datadog endpoint、client 和默认 batch 参数](../reverse/javascript/cli.readable.js#L90820-L90850)。",
        "8. [Datadog feature gate、allowlist、字段归一化与限流](../reverse/javascript/cli.readable.js#L90880-L90910)。",
        "9. [OTEL structured events 与内容字段处理](../reverse/javascript/cli.readable.js#L93720-L94360)。",
        "10. [OTEL/Perfetto span 构造与关联](../reverse/javascript/cli.readable.js#L93980-L94360)。",
        "11. [OTEL metrics/logs/traces exporter bootstrap](../reverse/javascript/cli.readable.js#L361450-L361710)。",
        "12. [观测环境变量、content gates、flush/shutdown 配置入口](../reverse/javascript/cli.readable.js#L17097-L17120)。",
        "",
        "### Token、成本、延迟、隐私和副作用",
        "",
        "| 影响面 | 本版本客户端行为 | 读者应如何判断 |",
        "| --- | --- | --- |",
        "| Model tokens | 事件可记录 input/output/cache token 计数，但目录没有证据表明事件被插回模型 prompt | 报告 token usage 不等于额外消耗同等模型 token；模型调用本身的 token 成本与遥测 transport 分开计算 |",
        "| Money | `cost_usd` / `cost_usd_micros` 等字段报告已计算的使用成本 | 字段是观测值，不是额外收费动作；第三方 collector、Datadog 或 OTEL 后端的存储/查询费用属于部署边界 |",
        "| Latency | 主要路径使用 microtask、queue 和 batch；force-flush、shutdown、磁盘恢复和网络重试会产生客户端工作 | 不能用“异步”推断零延迟；尤其退出、provider 重建和故障恢复会等待 timeout/flush |",
        "| Privacy | 一方 envelope 可承载 identity/session/environment/process；OTEL 另有 prompt/response/tool/raw-body content gates；Datadog 只删除自己的 26 字段 | 必须按出口审计实际 gate、字段值与 collector；字段名启发式只做排查导航 |",
        "| Local side effects | 失败 batch、v5 telemetry stream、debug/profile 文件可写盘；2.1.235 未观察到 Perfetto recorder/file writer，Perfetto 文件创建仍为 Boundary | 禁止远端发送不自动删除既有本地诊断或失败批次；需要分别检查 retention/purge |",
        "| External side effects | 遥测通常观察已经发生的 model/tool/API 生命周期 | 遥测失败、丢队列或 server reject 不会撤销已经完成的文件写入、命令、网络请求或其他工具副作用 |",
        "",
    ]


def render_scenario_semantic_index(
    grouped: dict[str, list[dict[str, Any]]], projections: dict[str, str]
) -> list[str]:
    missing = sorted(SEMANTIC_INDEX_EVENTS - set(grouped))
    require(not missing, f"semantic scenario events missing: {', '.join(missing)}")
    other_examples = [
        "tengu_reactive_compact_succeeded",
        "tengu_query_error",
        "tengu_transcript_write_failed",
    ]
    require(
        all(projections.get(event) == "tengu_other" for event in other_examples),
        "semantic index tengu_other examples changed family projection",
    )
    return [
        "## 按排障场景阅读：事件名、字段和状态变化",
        "",
        "<!-- TELEMETRY_SCENARIO_SEMANTIC_INDEX -->",
        "",
        "下面不是再造一套事件 taxonomy，而是把最常用的调用点放回真实状态机。箭头表示同一业务场景中可能出现的先后关系，不保证每次都经过所有节点；例如预授权工具不会显示 permission dialog，API 首次成功也不会产生 retry。",
        "",
        "| 场景 | 事件顺序或分支 | 状态 owner 与真正变化 | 关键字段怎样读 | 排障结论与深读入口 |",
        "| --- | --- | --- | --- | --- |",
        "| API 请求 | `tengu_api_query` -> `tengu_api_retry`（0..N） -> `tengu_api_success` 或 `tengu_api_error` | request controller 拥有一次模型请求及其重试 attempt；retry 增加网络 attempt，不自动增加 Agent Loop turn | `attempt` 是本请求内序号；`delayMs/status/errorType` 解释为何等待；`durationMsIncludingRetries` 是跨 attempt 总时长；token/cost 字段只在成功面有完整值；`requestId/clientRequestId` 用于关联，不是业务成功标志 | query 之后没有 success/error，先查 abort、进程退出或日志丢失；有 retry 要区分 429/5xx、fallback 与用户新一轮。见 [请求装配](models-auth-providers-request.md)、[韧性与恢复](resilience-and-recovery.md)，源码 215719、232156-232244 |",
        "| 工具授权与执行 | `tengu_tool_use_show_permission_request`（可选） -> `...can_use_tool_allowed` 或 `...rejected` -> `...success` / `...error` / `...cancelled` | permission pipeline 决定是否允许，tool executor 才拥有实际调用；allowed 只证明通过权限层，不证明 `tool.call` 成功 | `messageID/toolUseID` 分别关联 assistant message 和具体调用；`decisionReasonType/deniedBy/permissionMode` 解释决策来源；`durationMs/permissionDurationMs/preToolHookDurationMs` 拆开等待；`errorCode/phase/abortKind` 区分校验、执行和中断 | 有 rejected 时工具没有进入正常 call；有 allowed 后仍可能 validation/error/cancel；success 也不等于外部副作用可回滚。见 [Agent Loop](agent-loop.md)、[工具/权限/Hooks](tools-permissions-hooks.md)，源码 289754、315978-316476 |",
        "| Permission 解释器 UI | `tengu_permission_explainer_generated` 或 `...error`；用户选择记录 `tengu_permission_request_option_selected` | explainer 只生成风险说明和记录界面选择，不拥有最终 allow/deny；最终决策仍看上一行的 tool permission 事件 | `risk_level/tool_name/latency_ms/error_type` 描述说明生成；`option_index` 只是 UI 选项位置，必须结合当时选项集合解释 | 不能用 explainer success 断言工具获批，也不能用 option_index 跨版本推断固定语义。见 [工具/权限/Hooks](tools-permissions-hooks.md)，源码 530713、530993、532684 |",
        "| Reactive compact | `tengu_reactive_compact_triggered` -> `...attempt`（1..N） -> `...succeeded` 或 `...failed` | compactor 拥有“总结前缀、保留合法后缀、恢复附件、写 boundary”的表示切换；它不回滚既有工具副作用 | `groupsToSummarize/groupsToPreserve/tokenGap` 描述每次选择；`attempts/preCompactTokens/postCompactTokens/preservedMessageCount/restoredAttachmentCount` 描述结果；`trigger/thresholdSource/precomputed` 解释入口 | success 才证明 rebuilt context 已形成；failed 后旧历史仍是当前表示。注意这些 `tengu_reactive_*` 事件落在 Derived 的 `tengu_other`，不能因 family 名缺失而跳过。见 [`/compact` 图文专题](compact-visual-guide.md)，源码 232819-232876、262267 |",
        "| Session 启动、恢复与持久化 | `tengu_session_start`；resume 分支产生 `tengu_session_resumed{success}`；远端/内部镜像失败另记 `tengu_session_persistence_failed` | session loader 拥有恢复视图，transcript/remote mirror 各自拥有持久化；启动成功和后续每次写入成功不是同一状态 | `previous_session_id/source/permissionMode` 描述启动来源；`entrypoint/success/failure_reason/resume_duration_ms` 描述恢复；persistence failure 当前无 payload，必须回源码/diagnostic 定位 owner | resumed success 不证明之后 transcript 永不丢写；persistence failure 也不等于当前模型回答失败。见 [Sessions/Checkpoint/Memory](sessions-checkpoints-memory.md)，源码 401679-401697、587827-594803、591606 |",
        "| MCP 认证与工具失败 | `tengu_mcp_server_needs_auth` -> `tengu_mcp_oauth_flow_start` -> `...success` / `...failure` / `...error`；调用期仍可出现 `tengu_mcp_tool_call_auth_error` | MCP connection/auth controller 拥有发现、OAuth 和 token；tool executor 只消费当时连接状态 | `transportType/cause` 说明在哪个发现阶段需要认证；`flowAttemptId/authMethod/http_status/error_code/reason` 关联 OAuth；`authErrorKind` 区分未连接和 token 过期 | OAuth success 只完成该 flow，不保证 tools/list 或下一次 tool call 成功；调用期 auth error 需要重新连接/授权。见 [MCP、Agents 与后台协作](mcp-agents-background.md)，源码 381285-381456、384086、385348 |",
        "| 后台任务派发 | `tengu_bg_dispatch`；失败前后可见 `...rejected`、`...fallback`、`...rescued`；最终工作结果另看 `tengu_bg_agent_terminal` | dispatcher/daemon 拥有进程与消息投递，agent registry 拥有最终 outcome；dispatch ACK 不是任务完成 | `source_* / via / has_worktree / has_agent` 解释入口；fallback 的 reason flags 解释 transport；rescued 表示 ACK 不确定但 worker 被 readback 找到；terminal 的 `outcome/durationMs` 才接近任务终态 | 只有 dispatch 没有 terminal 时查 daemon、roster、worker crash 或会话仍运行；rescued 不是重复启动证据。见 [Runtime Supervision](runtime-supervision-and-processes.md)，源码 270118、480234-480323、631031 |",
        "| CLI 登录 | `tengu_oauth_flow_start` -> `tengu_oauth_auth_code_received`（浏览器流） -> `tengu_oauth_token_exchange_success` -> `tengu_oauth_success` 或 `tengu_oauth_error` | login controller 拥有 UI/flow，token exchange/storage 和 profile/account check 是后续独立阶段 | `loginWithClaudeAi/automatic` 区分入口；`account_on_hold/ssl_error` 是特定失败分类；token-exchange success 不携带账号完整状态 | 不要把 token exchange success 当作最终登录；最终 success 之后仍可能有 profile、role 或持久化告警。见 [认证与账号生命周期](auth-account-and-subscription-lifecycle.md)，源码 78277、299879、441642-441703 |",
        "| 错误终态层级 | tool 层用 `tengu_tool_use_error`；Agent/query wrapper 用 `tengu_query_error`；未捕获进程错误用 `tengu_uncaught_exception` / `tengu_unhandled_rejection` | 不同 owner 决定错误能否作为 tool_result 回到模型、结束当前 query，或升级为进程级异常 | tool 的 `errorCode/toolName` 可操作；query error 只给 assistant/tool-use 数量和 chain 深度；uncaught/rejection 的 `error_name` 已经过错误封装，不能替代原始 stack | 同一次根因可能在多层留下记录，但不能把多条事件统计成多个独立故障。`tengu_query_error` 位于 `tengu_other`，仍是高价值终态事件。见 [错误与诊断图谱](error-diagnostic-atlas.md)，源码 272115、316183-316476、78172、111364-111403 |",
        "| Transcript 写入恢复 | `tengu_transcript_write_failed` -> 后续成功写同一路径时 `tengu_transcript_writer_recovered` | transcript writer 拥有本地落盘和 degraded latch；模型/API 请求可以已经成功，而持久化单独失败 | `errno_code/errno_enospc/errno_emfile/consecutive_failures/degraded/source` 用于判断磁盘、fd 和连续退化；recovered 只说明 writer 清除了对应 degraded state | failed 后应核对磁盘与 transcript 完整性；recovered 不补证失败窗口内每条记录都已重放。两事件也落在 `tengu_other`。见 [Sessions/Checkpoint/Memory](sessions-checkpoints-memory.md)，源码 400287-400292 |",
        "",
        "### 为什么 `tengu_other` 不能当作“低价值垃圾桶”",
        "",
        "`tengu_other` 只表示当前 family 前缀规则没有命中。`tengu_reactive_compact_succeeded`、`tengu_query_error`、`tengu_transcript_write_failed` 都在这个桶里，却分别对应上下文切换、query 终态和持久化退化。排障应先按事件 consumer 和相邻状态机阅读，再用 family 做导航；不能按 family 名决定事件是否重要。",
        "",
    ]


def render_coverage(
    first_party_rows: Sequence[dict[str, Any]],
    first_party_dynamic: Sequence[dict[str, Any]],
    otel_rows: Sequence[dict[str, Any]],
) -> list[str]:
    first_party_functions = len({str(row.get("function")) for row in first_party_rows})
    first_party_spreads = sum(
        len(row["payload"].get("unresolvedSpreads", [])) for row in first_party_rows
    )
    otel_functions = len({str(row.get("function")) for row in otel_rows})
    otel_spreads = sum(len(row["payload"].get("unresolvedSpreads", [])) for row in otel_rows)
    return [
        "## 精确覆盖摘要",
        "",
        "| Surface | 精确数量 | 读法 |",
        "| --- | ---: | --- |",
        "| 一方 unique static events | 1,441 | 可按固定事件名聚合 |",
        "| 一方 callsites | 2,194 | `H` 2,162 + `Fv` 32 |",
        "| 一方 resolved string callsites | 2,151 | 第一个参数为静态字符串 |",
        f"| 一方 truly dynamic callsites | {len(first_party_dynamic)} | identifier 24 + conditional 9 + member-or-call 7 + template 3 |",
        f"| 一方 unique lexical functions | {first_party_functions} | 压缩后的定位名 |",
        "| 一方 static-object payloads | 1,860 | 顶层对象形状可解析 |",
        "| 一方 not-static-object payloads | 334 | 仅保留原参数/边界 |",
        f"| 一方 unresolved spreads | {first_party_spreads} | 保留表达式，字段集合是下界 |",
        "| Datadog allowlist | 181 | 只代表分支资格 |",
        "| OTEL unique static events | 26 | structured event 名字 |",
        "| OTEL callsites | 52 | 49 string + 2 identifier + 1 template |",
        f"| OTEL unique lexical functions | {otel_functions} | 压缩后的定位名 |",
        "| OTEL static-object payloads | 51 | 顶层对象形状可解析 |",
        "| OTEL not-static-object payloads | 1 | 静态字段集合不完整 |",
        f"| OTEL unresolved spreads | {otel_spreads} | 保留表达式，字段集合是下界 |",
        "| OTEL metrics | 8 | metric instruments |",
        "| OTEL spans | 10 | span names |",
        "",
    ]


def render_sensitivity_summary(field_map: dict[str, list[str]]) -> list[str]:
    all_fields = sorted_unique(field for fields in field_map.values() for field in fields)
    hits = sensitivity_hits(all_fields)
    lines = [
        "## 字段名启发式总览",
        "",
        f"1,441 个事件的静态 expanded field 集合共有 {len(all_fields):,} 个唯一字段名。下面只是字段名命中，不读取运行时值，也不表示字段一定会发送。一个字段可以命中多个组。",
        "",
        "| Heuristic group | 命中字段数 | 关键词口径 |",
        "| --- | ---: | --- |",
    ]
    for group, keywords in SENSITIVITY_RULES.items():
        lines.append(
            f"| {group} | {len(hits.get(group, []))} | {table_cell(code_list(keywords))} |"
        )
    lines.extend(
        [
            "",
            "Datadog 的删除字段和 tag 字段在后文独立列出。`redacted` 是该分支的静态处理集合，`tag` 是归一化/索引集合；两者都不能被外推成所有遥测通道的统一隐私策略。",
            "",
        ]
    )
    return lines


def render_family_summary(
    families: dict[str, int],
    grouped: dict[str, list[dict[str, Any]]],
    projections: dict[str, str],
    allowlist: set[str],
) -> list[str]:
    by_family: dict[str, list[str]] = collections.defaultdict(list)
    for event, family in projections.items():
        by_family[family].append(event)
    lines = [
        "## 40 个 family projection 摘要",
        "",
        "这些 family 复现 release-local extractor 的确定性投影：eligible prefixes 做最长匹配，singleton labels 只匹配同名事件。它们用于把 1,441 个名字分段阅读，不是运行时路由、服务端 taxonomy 或产品 owner。",
        "",
        "| Derived family | unique events | static callsites | functions | expanded fields | DD eligible events | unresolved spreads |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for family in sorted(families):
        events = sorted(by_family[family])
        rows = [row for event in events for row in grouped[event]]
        lines.append(
            "| {family} | {events} | {calls} | {functions} | {fields} | {dd} | {spreads} |".format(
                family=code_span(family),
                events=len(events),
                calls=len(rows),
                functions=len({str(row.get("function")) for row in rows}),
                fields=len(set(payload_keys(rows, "expandedKeys"))),
                dd=sum(event in allowlist for event in events),
                spreads=len(unresolved_spreads(rows)),
            )
        )
    lines.extend(["", "`tengu_other` 的 911 项只是未命中其余前缀的兜底集合，不能解释为一个拥有 911 个功能的模块。", ""])
    return lines


def render_dynamic_first_party(rows: Sequence[dict[str, Any]]) -> list[str]:
    lines = [
        "## 43 个一方动态事件名调用点",
        "",
        "这 43 个调用点没有 `nameArgument.staticValue`，因此不会混入 1,441 个静态事件。表中表达式来自 AST source slice；即使表达式文本里出现字符串分支，也不能把整个调用点伪装成单一固定事件。",
        "",
        "| # | kind | expression | role / callee | function | position | direct keys | expanded keys | unresolved spreads |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for index, row in enumerate(rows, start=1):
        argument = row["nameArgument"]
        payload = row["payload"]
        lines.append(
            "| {index} | {kind} | {expression} | {role} / {callee} | {function} | {position} | {direct} | {expanded} | {spreads} |".format(
                index=index,
                kind=code_span(argument["kind"]),
                expression=table_cell(code_span(source_text(argument))),
                role=code_span(row["calleeRole"]),
                callee=code_span(row["callee"]),
                function=code_span(function_label(row)),
                position=code_span(format_position(row)),
                direct=table_cell(code_list(payload.get("directKeys", []))),
                expanded=table_cell(code_list(payload.get("expandedKeys", []))),
                spreads=len(payload.get("unresolvedSpreads", [])),
            )
        )
    lines.extend(
        [
            "",
            "`identifier` 的 resolution、`template` 的 shape 和每个 source slice 的长度/SHA-256 仍保存在 `first-party-event-callsites.jsonl`。这里展示可读表达式和定位信息，不执行表达式。",
            "",
        ]
    )
    return lines


def render_event_entry(
    event: str,
    family: str,
    rows: Sequence[dict[str, Any]],
    allowlist: set[str],
) -> list[str]:
    ordered = sorted(rows, key=position_sort_key)
    canonical = ordered[0]
    direct = payload_keys(ordered, "directKeys")
    expanded = payload_keys(ordered, "expandedKeys")
    shorthand = payload_keys(ordered, "shorthandKeys")
    spreads = unresolved_spreads(ordered)
    spread_counts = collections.Counter(source_text(spread) for spread in spreads)
    roles = sorted_unique(f"{row['calleeRole']} / {row['callee']}" for row in ordered)
    functions = sorted_unique(function_label(row) for row in ordered)
    statuses = collections.Counter(row["payload"]["objectStatus"] for row in ordered)
    all_positions = [format_position(row) for row in ordered]
    dd = event in allowlist
    summary = (
        f"{event}: {len(ordered)} callsite{'s' if len(ordered) != 1 else ''}; "
        f"{len(expanded)} expanded fields; Datadog {'eligible' if dd else 'not allowlisted'}"
    )
    lines = [
        "<details>",
        f"<summary><code>{html.escape(summary)}</code></summary>",
        "",
        f"- **Family projection (`Derived`):** {code_span(family)}. This is a release-local reading bucket, not an owner.",
        f"- **Call shape (`Static`):** {len(ordered)} callsite{'s' if len(ordered) != 1 else ''}; logger role / callee: {code_list(roles)}; lexical functions: {code_list(functions)}; payload status: {format_counter(statuses)}.",
        f"- **Canonical position (`Static`):** line {canonical['line']}, column {canonical['column']}, offset {canonical['offset']}. All positions in offset order: {', '.join(code_span(item) for item in all_positions)}.",
        f"- **Payload keys (`Static`):** direct: {code_list(direct)}; expanded: {code_list(expanded)}; shorthand: {code_list(shorthand)}.",
        f"- **Unresolved spreads (`Boundary`):** {len(spreads)} occurrence(s).",
    ]
    if spread_counts:
        rendered = "; ".join(
            f"{code_span(expression)} x{count}"
            for expression, count in sorted(spread_counts.items(), key=lambda item: (item[0].lower(), item[0]))
        )
        lines.append(f"  Retained expressions: {rendered}.")
    else:
        lines.append("  No unresolved spread was recorded; runtime values and send outcome remain outside static proof.")
    lines.extend(
        [
            f"- **Datadog allowlist (`Static`):** {'yes' if dd else 'no'}. {'This name is eligible for the forwarding branch, but runtime forwarding is not proven.' if dd else 'This static name is not in the 181-item forwarding allowlist.'}",
            f"- **Field-name sensitivity (`Heuristic`):** {format_sensitivity(expanded)}.",
            "- **Evidence boundary:** `Static` proves the shipped callsite and statically recoverable payload shape; `Derived` supplies counts/family aggregation; `Heuristic` only labels field names; `Boundary` includes runtime execution, dynamic spread values, gate/sample decisions, transport success and server retention.",
            "",
            "</details>",
            "",
        ]
    )
    return lines


def render_static_first_party(
    grouped: dict[str, list[dict[str, Any]]],
    projections: dict[str, str],
    families: dict[str, int],
    allowlist: set[str],
) -> list[str]:
    by_family: dict[str, list[str]] = collections.defaultdict(list)
    for event, family in projections.items():
        by_family[family].append(event)
    lines = [
        "## 1,441 个一方静态事件",
        "",
        "每个条目都保留同名调用点的完整聚合。`expanded` 与 `first-party-event-fields.tsv` 逐项校验；`unresolved spread` 另列原表达式，避免把静态下界误写成完整运行时 payload。",
        "",
    ]
    for family in sorted(families):
        events = sorted(by_family[family])
        lines.extend(
            [
                f"### {code_span(family)}",
                "",
                f"{len(events)} 个 unique static events；source family inventory 期望值 {families[family]}。",
                "",
            ]
        )
        for event in events:
            lines.extend(render_event_entry(event, family, grouped[event], allowlist))
    return lines


def render_datadog(
    allowlist: Sequence[str],
    static_events: set[str],
    dynamic_rows: Sequence[dict[str, Any]],
    redacted_fields: Sequence[str],
    tag_fields: Sequence[str],
) -> list[str]:
    dynamic_literals = set()
    for row in dynamic_rows:
        dynamic_literals.update(quoted_literals(source_text(row["nameArgument"])))
    allowlist_set = set(allowlist)
    static_count = len(allowlist_set & static_events)
    dynamic_literal_count = len((allowlist_set - static_events) & dynamic_literals)
    allowlist_only_count = len(allowlist_set - static_events - dynamic_literals)
    require((static_count, dynamic_literal_count, allowlist_only_count) == (166, 2, 13), "Datadog allowlist projection")
    lines = [
        "## Datadog forwarding 目录",
        "",
        f"181 个 allowlist 名中，{static_count} 个与 1,441 个静态一方事件相交，{dynamic_literal_count} 个只作为动态事件名表达式里的字符串分支出现，{allowlist_only_count} 个在本次 `H` / `Fv` 静态名字和动态字符串分支中都没有直接调用点。后两类不应被补进静态事件目录。",
        "",
        "| # | allowlisted name | Catalog relation (`Derived`) |",
        "| ---: | --- | --- |",
    ]
    for index, event in enumerate(sorted(allowlist), start=1):
        if event in static_events:
            relation = "first-party static event"
        elif event in dynamic_literals:
            relation = "literal inside dynamic name expression"
        else:
            relation = "allowlist-only in this callsite inventory"
        lines.append(f"| {index} | {code_span(event)} | {relation} |")
    lines.extend(
        [
            "",
            "### 26 个 Datadog 删除字段",
            "",
            "这些字段只在 Datadog forwarding 归一化分支中删除，不能外推到一方 batch 或 OTEL。",
            "",
            code_list(redacted_fields),
            "",
            "### 34 个 Datadog tag 字段",
            "",
            "这些字段被该分支当作稳定 tag/索引维度处理。进入 tag 集合不等于字段不敏感，也不证明某条事件实际发送。",
            "",
            code_list(tag_fields),
            "",
        ]
    )
    return lines


def render_otel_events(
    events: Sequence[str],
    grouped: dict[str, list[dict[str, Any]]],
    fields: dict[str, list[str]],
) -> list[str]:
    lines = [
        "## 26 个第三方 OTEL structured events",
        "",
        "OTEL 是管理员/用户配置的 exporter 通道，不是 `H` / `Fv` 一方 transport 的别名。下表的调用次数只统计固定事件名；全部 52 个调用点在下一节逐条列出。",
        "",
        "| event | static callsites | functions | canonical position | expanded fields | unresolved spreads | sensitivity (`Heuristic`) |",
        "| --- | ---: | --- | --- | --- | ---: | --- |",
    ]
    for event in sorted(events):
        rows = grouped[event]
        canonical = sorted(rows, key=position_sort_key)[0]
        functions = sorted_unique(function_label(row) for row in rows)
        spreads = unresolved_spreads(rows)
        lines.append(
            "| {event} | {calls} | {functions} | {position} | {fields} | {spreads} | {sensitivity} |".format(
                event=code_span(event),
                calls=len(rows),
                functions=table_cell(code_list(functions)),
                position=code_span(format_position(canonical)),
                fields=table_cell(code_list(fields[event])),
                spreads=len(spreads),
                sensitivity=table_cell(format_sensitivity(fields[event])),
            )
        )
    lines.extend(["", "这里的 fields 是静态 expanded keys。内容字段是否保留原文仍由 OTEL content gates 和长度上限决定。", ""])
    return lines


def render_otel_callsites(rows: Sequence[dict[str, Any]]) -> list[str]:
    lines = [
        "## 52 个 OTEL 调用点",
        "",
        "49 个调用点使用 string 名，2 个使用 unresolved identifier，1 个使用 template。动态 3 项仍留在表中，但不会被归入 26 个固定名字。",
        "",
        "| # | name / expression | kind | function | position | direct keys | expanded keys | unresolved spreads |",
        "| ---: | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for index, row in enumerate(sorted(rows, key=position_sort_key), start=1):
        argument = row["nameArgument"]
        name = argument.get("staticValue")
        display = name if isinstance(name, str) else source_text(argument)
        payload = row["payload"]
        lines.append(
            "| {index} | {name} | {kind} | {function} | {position} | {direct} | {expanded} | {spreads} |".format(
                index=index,
                name=table_cell(code_span(display)),
                kind=code_span(argument["kind"]),
                function=code_span(function_label(row)),
                position=code_span(format_position(row)),
                direct=table_cell(code_list(payload.get("directKeys", []))),
                expanded=table_cell(code_list(payload.get("expandedKeys", []))),
                spreads=len(payload.get("unresolvedSpreads", [])),
            )
        )
    lines.extend(["", "所有 OTEL payload unresolved spread 原表达式、source hash 和 comparison fields 仍保存在 `otel-event-callsites.jsonl`。", ""])
    return lines


def render_metrics_and_spans(metrics_path: Path, spans: Sequence[str]) -> list[str]:
    metrics: list[tuple[str, str, str]] = []
    for number, line in enumerate(read_lines(metrics_path), start=1):
        parts = line.split("\t")
        require(len(parts) == 3, f"otel-metrics.tsv:{number}: expected three columns")
        metrics.append((parts[0], parts[1], parts[2]))
    metrics.sort(key=lambda row: row[0])
    lines = [
        "## 8 个 OTEL metrics",
        "",
        "| metric | unit | description (`Static`) |",
        "| --- | --- | --- |",
    ]
    for name, unit, description in metrics:
        lines.append(
            f"| {code_span(name)} | {table_cell(code_span(unit) if unit else 'unitless/count')} | {table_cell(description)} |"
        )
    lines.extend(
        [
            "",
            "## 10 个 OTEL spans",
            "",
            "这些是发布包中静态恢复的 span names；是否创建、采样和导出仍取决于 trace gates/exporter。",
            "",
        ]
    )
    for span in sorted(spans):
        lines.append(f"- {code_span(span)}")
    lines.append("")
    return lines


def render_provenance(
    root: Path,
    summary_path: Path,
    summary: dict[str, Any],
    verified: dict[str, dict[str, Any]],
) -> list[str]:
    summary_data = summary_path.read_bytes()
    generator_path = Path(__file__)
    generator_data = generator_path.read_bytes()
    canonical = summary["canonicalSource"]
    lines = [
        "## Evidence provenance 与复现",
        "",
        f"- Version: {code_span(summary['version'])}.",
        f"- Canonical source: {code_span(canonical['path'])}; bytes {canonical['size']:,}; SHA-256 {code_span(canonical['sha256'])}.",
        f"- Parser: {code_span(summary['javascriptParser']['name'])} {code_span(summary['javascriptParser']['version'])}, ECMAScript {code_span(summary['javascriptParser']['ecmaVersion'])}.",
        f"- Generator: {code_span('skill/claude-code-version-diff/scripts/build_telemetry_event_catalog.py')}; SHA-256 {code_span(sha256_bytes(generator_data))}.",
        "",
        "| Input | lines | bytes | SHA-256 |",
        "| --- | ---: | ---: | --- |",
    ]
    for name in SOURCE_FILES:
        item = verified[name]
        lines.append(
            f"| {code_span(item['path'])} | {item['lines']} | {item['size']} | {code_span(item['sha256'])} |"
        )
    lines.append(
        f"| {code_span('analysis/source-inventory/summary.json')} | {line_count(summary_data)} | {len(summary_data)} | {code_span(sha256_bytes(summary_data))} |"
    )
    lines.extend(
        [
            "",
            "复现命令：",
            "",
            "```bash",
            "python3 skill/claude-code-version-diff/scripts/build_telemetry_event_catalog.py .",
            "shasum -a 256 analysis/telemetry-event-catalog.md",
            "```",
            "",
            "生成器会先校验版本、所有精确数量、调用点 kinds/roles/callees、payload 状态、unresolved spread 总数、family 投影、事件字段映射和输入文件 hash；任一不匹配都会拒绝覆盖输出。输出按稳定排序生成，不包含时间戳或机器绝对路径，并通过同目录临时文件原子替换。",
            "",
            "## 最终边界",
            "",
            "- `Static`：只描述 Claude Code 2.1.235 已发布 bundle 中可到达的语法结构和静态集合，不等于某次运行已触发。",
            "- `Derived`：family、计数、交集、canonical position 和聚合字段由本生成器确定性计算；它们不是 Anthropic 服务端定义。",
            "- `Heuristic`：sensitivity 只看字段名，不看值、数据来源、内容 gate 或服务端处理。",
            "- `Boundary`：动态 name expression、unresolved spread 的实际展开、feature/policy/auth 状态、随机采样、队列丢弃、网络发送、collector 行为和服务端风控/保留不在静态目录的证明范围内。",
            "",
        ]
    )
    return lines


def build_catalog(root: Path) -> str:
    inventory = root / "analysis" / "source-inventory"
    summary_path = inventory / "summary.json"
    require(summary_path.is_file(), "missing analysis/source-inventory/summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    validate_exact_counts(summary)
    verified = verify_source_files(inventory, summary)

    events = sorted(read_lines(inventory / "first-party-events.txt"))
    require(len(events) == EXPECTED_COUNTS["first-party-events"], "first-party event count")
    require(len(events) == len(set(events)), "duplicate first-party event names")
    first_party_fields = parse_field_map(inventory / "first-party-event-fields.tsv")
    first_party_rows = read_jsonl(inventory / "first-party-event-callsites.jsonl")
    family_raw = read_two_column_tsv(inventory / "first-party-event-families.tsv")
    families = {name: int(count) for name, count in family_raw.items()}
    require(len(families) == 40, "family count != 40")
    grouped, dynamic, projections = validate_first_party(
        events, first_party_fields, families, first_party_rows
    )

    allowlist = sorted(read_lines(inventory / "datadog-forwarded-events.txt"))
    redacted_fields = sorted(read_lines(inventory / "datadog-redacted-fields.txt"))
    tag_fields = sorted(read_lines(inventory / "datadog-tag-fields.txt"))
    require(len(allowlist) == EXPECTED_COUNTS["datadog-forwarded-events"], "Datadog allowlist count")
    require(len(redacted_fields) == EXPECTED_COUNTS["datadog-redacted-fields"], "Datadog redacted field count")
    require(len(tag_fields) == EXPECTED_COUNTS["datadog-tag-fields"], "Datadog tag field count")
    require(len(allowlist) == len(set(allowlist)), "duplicate Datadog allowlist names")

    otel_events = sorted(read_lines(inventory / "third-party-otel-events.txt"))
    otel_fields = parse_field_map(inventory / "third-party-otel-event-fields.tsv")
    otel_rows = read_jsonl(inventory / "otel-event-callsites.jsonl")
    require(len(otel_events) == EXPECTED_COUNTS["third-party-otel-events"], "OTEL event count")
    otel_grouped, _otel_dynamic = validate_otel(otel_events, otel_fields, otel_rows)
    spans = sorted(read_lines(inventory / "otel-spans.txt"))
    require(len(spans) == EXPECTED_COUNTS["otel-spans"], "OTEL span count")
    require(len(read_lines(inventory / "otel-metrics.tsv")) == EXPECTED_COUNTS["otel-metrics"], "OTEL metric count")

    lines: list[str] = []
    lines.extend(render_header(summary["version"]))
    lines.extend(render_lifecycle_and_impact())
    lines.extend(render_scenario_semantic_index(grouped, projections))
    lines.extend(render_coverage(first_party_rows, dynamic, otel_rows))
    lines.extend(render_sensitivity_summary(first_party_fields))
    lines.extend(render_family_summary(families, grouped, projections, set(allowlist)))
    lines.extend(render_dynamic_first_party(dynamic))
    lines.extend(render_static_first_party(grouped, projections, families, set(allowlist)))
    lines.extend(
        render_datadog(
            allowlist,
            set(events),
            dynamic,
            redacted_fields,
            tag_fields,
        )
    )
    lines.extend(render_otel_events(otel_events, otel_grouped, otel_fields))
    lines.extend(render_otel_callsites(otel_rows))
    lines.extend(render_metrics_and_spans(inventory / "otel-metrics.tsv", spans))
    lines.extend(render_provenance(root, summary_path, summary, verified))
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    require(str(root.resolve()) not in text, "generated output contains repository absolute path")
    require("/Users/" not in text, "generated output contains a macOS user path")
    return text


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", default=".", help="snapshot repository root")
    parser.add_argument(
        "--output",
        default="analysis/telemetry-event-catalog.md",
        help="output path, relative to repo_root unless absolute",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the existing output differs instead of writing it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    require(root.is_dir(), f"repository root does not exist: {args.repo_root}")
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    catalog = build_catalog(root)
    encoded = catalog.encode("utf-8")
    if args.check:
        require(output.is_file(), f"missing output: {output}")
        require(output.read_bytes() == encoded, f"stale output: {output}")
    else:
        atomic_write(output, catalog)
    try:
        display = output.relative_to(root)
    except ValueError:
        display = output
    action = "checked" if args.check else "wrote"
    print(f"{action} {display} ({len(encoded)} bytes, sha256={sha256_bytes(encoded)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
