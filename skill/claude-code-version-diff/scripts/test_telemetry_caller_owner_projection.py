#!/usr/bin/env python3
"""Validate the deterministic 2.1.235 telemetry caller-owner projection."""

from __future__ import annotations

import collections
import importlib.util
import json
import os
from pathlib import Path
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"telemetry caller-owner projection test failed: {message}")


def load_generator(path: Path):
    spec = importlib.util.spec_from_file_location("telemetry_catalog_generator", path)
    if spec is None or spec.loader is None:
        fail("could not load telemetry generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def marker(text: str, name: str) -> int:
    match = re.search(rf"<!-- {re.escape(name)}:(\d+) -->", text)
    if match is None:
        fail(f"missing marker {name}")
    return int(match.group(1))


def load_projection(module, root: Path):
    inventory = root / "analysis/source-inventory"
    events = sorted(module.read_lines(inventory / "first-party-events.txt"))
    fields = module.parse_field_map(inventory / "first-party-event-fields.tsv")
    rows = module.read_jsonl(inventory / "first-party-event-callsites.jsonl")
    families = {
        name: int(count)
        for name, count in module.read_two_column_tsv(
            inventory / "first-party-event-families.tsv"
        ).items()
    }
    grouped, _dynamic, projections = module.validate_first_party(
        events, fields, families, rows
    )
    readable_by_row, _provenance = module.verify_readable_callsites(root, rows)
    projection = module.project_caller_owners(grouped, projections, readable_by_row)
    return grouped, readable_by_row, projection


def expect_build_failure(module, root: Path, fragment: str) -> None:
    try:
        module.build_catalog(root)
    except SystemExit as exc:
        if fragment not in str(exc):
            fail(f"wrong negative-test failure, expected {fragment!r}: {exc}")
    else:
        fail(f"generator accepted invalid caller-owner mapping: {fragment}")


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    generator_path = root / "skill/claude-code-version-diff/scripts/build_telemetry_event_catalog.py"
    catalog_path = root / "analysis/telemetry-event-catalog.md"
    module = load_generator(generator_path)

    first = module.build_catalog(root)
    second = module.build_catalog(root)
    if first != second:
        fail("two in-memory generations differ")

    expected_markers = {
        "caller-owner-target-events": module.EXPECTED_CALLER_OWNER_EVENTS,
        "caller-owner-target-callsites": module.EXPECTED_CALLER_OWNER_CALLSITES,
        "caller-owner-single": module.EXPECTED_CALLER_OWNER_STATUS["Single-owner"],
        "caller-owner-cross": module.EXPECTED_CALLER_OWNER_STATUS["Cross-owner"],
        "caller-owner-partial": module.EXPECTED_CALLER_OWNER_STATUS["Partially resolved"],
        "caller-owner-unresolved": module.EXPECTED_CALLER_OWNER_STATUS["Unresolved"],
        "caller-owner-allowlist-entries": module.EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES,
        "caller-owner-mapped-callsites": module.EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES,
        "caller-owner-unresolved-callsites": (
            module.EXPECTED_CALLER_OWNER_CALLSITES
            - module.EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES
        ),
    }
    observed_markers = {name: marker(first, name) for name in expected_markers}
    if observed_markers != expected_markers:
        fail(f"projection markers changed: {observed_markers}")

    required = (
        "TELEMETRY_CALLER_OWNER_PROJECTION",
        "owner 由 exact caller allowlist 决定",
        "导航区间不参与分类",
        "tengu_fast_mode_toggled` | `Cross-owner`",
        "tengu_copper_lantern` | `Single-owner` | `remote-runtime`",
        "tengu_install_github_app_step_completed` | `Single-owner` | `workflow-product`",
        "tengu_official_marketplace_auto_install` | `Single-owner` | `plugin-runtime`",
        "tengu_streaming_error` | `Single-owner` | `model-request`",
        "tengu_claudeai_mcp_eligibility` | `Single-owner` | `mcp-runtime`",
        "tengu_resume_parked_permission` | `Single-owner` | `workspace-state`",
        "观测到的状态变化",
        "部分远端副作用已回滚",
        f"| `Unresolved` | {module.EXPECTED_CALLER_OWNER_STATUS['Unresolved']} |",
        "完整 Unresolved caller 证据（891 events / 1,157 callsites）",
    )
    for value in required:
        if value not in first:
            fail(f"missing projection contract: {value}")

    grouped, readable_by_row, projection = load_projection(module, root)
    expected_resolved = {
        "tengu_reactive_compact_succeeded": ("Single-owner", ["model-request"], 1),
        "tengu_transcript_write_failed": ("Single-owner", ["workspace-state"], 1),
        "tengu_post_tool_hook_error": ("Single-owner", ["tool-runtime"], 1),
        "tengu_review_remote_precondition_failed": ("Single-owner", ["workflow-product"], 17),
        "tengu_fast_mode_toggled": (
            "Cross-owner",
            ["identity-account", "terminal-host", "workflow-product"],
            4,
        ),
        "tengu_copper_lantern": ("Single-owner", ["remote-runtime"], 1),
        "tengu_install_github_app_step_completed": (
            "Single-owner",
            ["workflow-product"],
            14,
        ),
        "tengu_setup_github_actions_failed": (
            "Single-owner",
            ["workflow-product"],
            8,
        ),
        "tengu_official_marketplace_auto_install": (
            "Single-owner",
            ["plugin-runtime"],
            8,
        ),
        "tengu_stage_file_completed": ("Single-owner", ["remote-runtime"], 9),
        "tengu_file_history_rewind_restore_file_failed": (
            "Single-owner",
            ["workspace-state"],
            9,
        ),
        "tengu_transcript_compact_failed": (
            "Single-owner",
            ["workspace-state"],
            6,
        ),
        "tengu_review_remote_precondition_recovery": (
            "Single-owner",
            ["workflow-product"],
            13,
        ),
        "tengu_plan_exit": ("Single-owner", ["workflow-product"], 8),
        "tengu_streaming_error": ("Single-owner", ["model-request"], 8),
        "tengu_claudeai_mcp_eligibility": (
            "Single-owner",
            ["mcp-runtime"],
            8,
        ),
        "tengu_at_mention_mcp_resource_error": (
            "Single-owner",
            ["input-context"],
            6,
        ),
        "tengu_quota_auto_resume_cancelled": (
            "Single-owner",
            ["model-request"],
            6,
        ),
        "tengu_resume_parked_permission": (
            "Single-owner",
            ["workspace-state"],
            6,
        ),
        "tengu_ultraplan_create_failed": (
            "Single-owner",
            ["workflow-product"],
            6,
        ),
    }
    for event, (status, owners, callsites) in expected_resolved.items():
        item = projection[event]
        observed = (item["status"], item["owners"], len(item["callsites"]))
        if observed != (status, owners, callsites):
            fail(f"exact resolved event changed: {event} -> {observed}")
        if any(callsite["mappingId"] is None for callsite in item["callsites"]):
            fail(f"resolved event has an unmapped caller: {event}")
        if any(
            not callsite["stateChange"] or not callsite["boundary"]
            for callsite in item["callsites"]
        ):
            fail(f"resolved event lacks state-change or Boundary semantics: {event}")

    mapped_rule_ids = {mapping.rule_id for mapping in module.CALLER_OWNER_ALLOWLIST}
    if mapped_rule_ids != set(module.CALLER_OWNER_RULE_SEMANTICS):
        fail("rule semantics do not exactly cover mapped caller rules")
    if any(
        not semantics.state_change or not semantics.boundary
        for semantics in module.CALLER_OWNER_RULE_SEMANTICS.values()
    ):
        fail("rule semantics contains an empty state change or Boundary")

    counterexamples = (
        "tengu_end_conversation_tool_call",
        "tengu_heap_dump",
        "tengu_update_refused",
        "tengu_streaming_fallback_to_non_streaming",
    )
    for event in counterexamples:
        item = projection[event]
        if item["status"] != "Unresolved" or item["owners"] != ["Unresolved"]:
            fail(f"known broad-region misclassification returned: {event}")
        if any(callsite["mappingId"] is not None for callsite in item["callsites"]):
            fail(f"counterexample unexpectedly matched an exact mapping: {event}")

    status = collections.Counter(item["status"] for item in projection.values())
    if dict(status) != {
        "Cross-owner": 1,
        "Single-owner": 19,
        "Unresolved": 891,
    }:
        fail(f"exclusive status counts changed: {dict(status)}")
    mapped_callsites = sum(
        callsite["mappingId"] is not None
        for item in projection.values()
        for callsite in item["callsites"]
    )
    if mapped_callsites != module.EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES:
        fail(f"mapped callsite count changed: {mapped_callsites}")

    original_allowlist = module.CALLER_OWNER_ALLOWLIST
    original_digest = module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256
    original_semantics = module.CALLER_OWNER_RULE_SEMANTICS
    try:
        module.CALLER_OWNER_ALLOWLIST = tuple(
            mapping._replace(
                navigation_start=1,
                navigation_end=module.EXPECTED_READABLE_LINES,
            )
            for mapping in original_allowlist
        )
        for event in counterexamples:
            for row in grouped[event]:
                mapping = module.caller_owner_mapping(
                    event, row, readable_by_row[id(row)]
                )
                if mapping is not None:
                    fail(f"navigation range classified an unlisted caller: {event}")
    finally:
        module.CALLER_OWNER_ALLOWLIST = original_allowlist

    try:
        module.CALLER_OWNER_ALLOWLIST = original_allowlist[:-1]
        expect_build_failure(module, root, "caller-owner allowlist entry count")
    finally:
        module.CALLER_OWNER_ALLOWLIST = original_allowlist

    try:
        changed = original_allowlist[0]._replace(
            readable_line=original_allowlist[0].readable_line + 1,
            navigation_end=original_allowlist[0].navigation_end + 1,
        )
        module.CALLER_OWNER_ALLOWLIST = (changed,) + original_allowlist[1:]
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = (
            module.caller_owner_allowlist_sha256(module.CALLER_OWNER_ALLOWLIST)
        )
        expect_build_failure(
            module,
            root,
            "caller-owner mapping does not select one exact callsite",
        )
    finally:
        module.CALLER_OWNER_ALLOWLIST = original_allowlist
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = original_digest

    identity_mutations = (
        ("event", "tengu_heap_dump"),
        ("function", "named:tampered"),
        ("consumer", "ExpressionStatement/expression/other"),
        ("comparison_key", "firstPartyEvent+firstPartyEventAsync:tampered:1"),
    )
    for field, value in identity_mutations:
        try:
            changed = original_allowlist[0]._replace(**{field: value})
            module.CALLER_OWNER_ALLOWLIST = (changed,) + original_allowlist[1:]
            module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = (
                module.caller_owner_allowlist_sha256(module.CALLER_OWNER_ALLOWLIST)
            )
            expect_build_failure(
                module,
                root,
                "caller-owner mapping does not select one exact callsite",
            )
        finally:
            module.CALLER_OWNER_ALLOWLIST = original_allowlist
            module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = original_digest

    try:
        changed = original_allowlist[0]._replace(evidence_fingerprint="0" * 16)
        module.CALLER_OWNER_ALLOWLIST = (changed,) + original_allowlist[1:]
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = (
            module.caller_owner_allowlist_sha256(module.CALLER_OWNER_ALLOWLIST)
        )
        expect_build_failure(
            module,
            root,
            "caller-owner exact mapping fingerprint mismatch",
        )
    finally:
        module.CALLER_OWNER_ALLOWLIST = original_allowlist
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = original_digest

    try:
        changed_semantics = dict(original_semantics)
        changed_semantics.pop("ultraplan-launch")
        module.CALLER_OWNER_RULE_SEMANTICS = changed_semantics
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = (
            module.caller_owner_allowlist_sha256(original_allowlist)
        )
        expect_build_failure(module, root, "caller-owner rule semantics coverage changed")
    finally:
        module.CALLER_OWNER_RULE_SEMANTICS = original_semantics
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = original_digest

    try:
        changed_semantics = dict(original_semantics)
        changed_semantics["assistant-stream-parser"] = module.CallerOwnerSemantics(
            "",
            original_semantics["assistant-stream-parser"].boundary,
        )
        module.CALLER_OWNER_RULE_SEMANTICS = changed_semantics
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = (
            module.caller_owner_allowlist_sha256(original_allowlist)
        )
        expect_build_failure(module, root, "caller-owner rule semantics is incomplete")
    finally:
        module.CALLER_OWNER_RULE_SEMANTICS = original_semantics
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = original_digest

    try:
        changed_semantics = dict(original_semantics)
        changed_semantics["resume-parked-permission"] = module.CallerOwnerSemantics(
            original_semantics["resume-parked-permission"].state_change,
            "tampered Boundary",
        )
        module.CALLER_OWNER_RULE_SEMANTICS = changed_semantics
        expect_build_failure(module, root, "caller-owner exact allowlist digest changed")
    finally:
        module.CALLER_OWNER_RULE_SEMANTICS = original_semantics
        module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = original_digest

    restored = module.build_catalog(root)
    if restored != first:
        fail("projection did not restore after negative mutations")

    catalog_fresh = (
        catalog_path.is_file()
        and catalog_path.read_text(encoding="utf-8") == first
    )
    allow_stale = os.environ.get("CLAUDE_TELEMETRY_ALLOW_STALE_CATALOG") == "1"
    if not catalog_fresh and not allow_stale:
        fail("committed catalog differs from deterministic generation")

    print(
        json.dumps(
            {
                "version": module.EXPECTED_VERSION,
                "targetEvents": module.EXPECTED_CALLER_OWNER_EVENTS,
                "targetCallsites": module.EXPECTED_CALLER_OWNER_CALLSITES,
                "allowlistEntries": module.EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES,
                "allowlistSha256": module.EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256,
                "status": module.EXPECTED_CALLER_OWNER_STATUS,
                "ownerBuckets": module.EXPECTED_CALLER_OWNER_BUCKETS,
                "mappedCallsites": mapped_callsites,
                "unresolvedCallsites": module.EXPECTED_CALLER_OWNER_CALLSITES
                - mapped_callsites,
                "counterexamplesUnresolved": list(counterexamples),
                "broadNavigationCannotClassify": True,
                "negativeMappingDeletionRejected": True,
                "negativeMappingTamperRejected": True,
                "negativeEventTamperRejected": True,
                "negativeFunctionTamperRejected": True,
                "negativeConsumerTamperRejected": True,
                "negativeComparisonKeyTamperRejected": True,
                "negativeFingerprintTamperRejected": True,
                "negativeRuleDeletionRejected": True,
                "negativeEmptyStateChangeRejected": True,
                "negativeBoundaryTamperRejected": True,
                "deterministic": True,
                "catalogFresh": catalog_fresh,
                "restored": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
