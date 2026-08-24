#!/usr/bin/env python3
"""Fail-closed tests for the 2.1.235 Error/Diagnostic owner projection."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile


def fail(message: str) -> None:
    raise AssertionError(message)


def load_generator(path: Path):
    spec = importlib.util.spec_from_file_location("error_owner_generator", path)
    if spec is None or spec.loader is None:
        fail("could not load owner projection generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_failure(callable_value, fragment: str) -> None:
    try:
        callable_value()
    except ValueError as error:
        if fragment not in str(error):
            fail(f"wrong failure, expected {fragment!r}: {error}")
    else:
        fail(f"invalid owner projection passed: {fragment}")


def write_rules(path: Path, document: dict) -> bytes:
    data = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    path.write_bytes(data)
    return data


def classification_map(projection: list[dict]) -> dict[str, tuple[str, str | None, str | None]]:
    return {
        row["identity"]: (row["ownerClass"], row["owner"], row["ruleId"])
        for row in projection
    }


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    generator_path = root / "skill/claude-code-version-diff/scripts/build_error_diagnostic_owner_projection.py"
    rules_path = root / "analysis/error-diagnostic-owner-rules.json"
    module = load_generator(generator_path)

    baseline_artifacts, baseline_summary = module.generated_artifacts(root)
    for relative, expected in baseline_artifacts.items():
        path = root / relative
        if not path.is_file() or path.read_bytes() != expected:
            fail(f"committed generated artifact is stale: {relative}")
    if baseline_summary["totalCallsites"] != 10_234:
        fail("full 10,234-callsite projection is missing")
    if baseline_summary["classification"] != module.EXPECTED_OWNER_COUNTS:
        fail("exclusive owner counts changed")
    if baseline_summary["classificationByStream"] != module.EXPECTED_STREAM_OWNER_COUNTS:
        fail("stream owner counts changed")
    contract = baseline_summary["classificationContract"]
    if contract != {
        "exactCallsiteIdentityOnly": True,
        "lineRangesClassify": False,
        "messageSimilarityClassifies": False,
        "reviewSelectorsClassify": False,
        "unresolvedIsSemanticDebt": True,
    }:
        fail(f"classifier contract changed: {contract}")

    projection = [
        json.loads(line)
        for line in baseline_artifacts[module.PROJECTION_PATH].decode().splitlines()
    ]
    if len({row["identity"] for row in projection}) != 10_234:
        fail("projection identities are not one-to-one")
    mapped = [row for row in projection if row["ownerClass"] != "Unresolved"]
    if len(mapped) != 684:
        fail(f"mapped callsite count changed: {len(mapped)}")
    product = [row for row in projection if row["ownerClass"] == "Product"]
    catch_resolved_rows = [
        row
        for row in product
        if row["productFlow"]["catchOwner"]["status"] == "Resolved exact rule"
    ]
    expected_catch_rules = {
        "product-permission-hook-catch-diagnostic",
        "product-post-tool-hook-catch-diagnostic",
    }
    if (
        len(catch_resolved_rows) != 4
        or {row["ruleId"] for row in catch_resolved_rows} != expected_catch_rules
    ):
        fail(
            "Product catch evidence changed: "
            f"count={len(catch_resolved_rows)}, "
            f"rules={sorted({row['ruleId'] for row in catch_resolved_rows})}"
        )
    if any(row["productFlow"]["userSurfaceOwner"]["status"] != "Unresolved" for row in product):
        fail("unproven Product user-surface owner was introduced")
    retry_resolved = sum(
        row["productFlow"]["retryOwner"]["status"] == "Resolved exact rule"
        for row in product
    )
    tool_result_resolved = sum(
        row["productFlow"]["toolResultOwner"]["status"] == "Resolved exact rule"
        for row in product
    )
    if (retry_resolved, tool_result_resolved) != (99, 13):
        fail(f"Product flow evidence changed: retry={retry_resolved}, toolResult={tool_result_resolved}")

    # Same canonical line as mapped OTLP constructors, but outside the reviewed
    # exact IDs. A broad line rule would incorrectly absorb it.
    same_line_counterexamples = [
        row
        for row in projection
        if row["stream"] == "Error constructor"
        and row["canonical"]["line"] == 19_249
        and row["ownerClass"] == "Unresolved"
    ]
    if not same_line_counterexamples:
        fail("missing broad-line negative counterexample")

    # Zod-looking text is not enough: this caller is not in the reviewed Zod
    # internal allowlist and must remain unresolved.
    source_inputs = module.load_inputs(root)
    projection_by_identity = {row["identity"]: row for row in projection}
    zod_similarity = []
    function_name_collision = []
    for row in source_inputs["error"]:
        identity = module.row_identity("error", row)
        projected = projection_by_identity[identity]
        text = module.source_text(row)
        if "expected a Zod schema" in text and projected["ownerClass"] == "Unresolved":
            zod_similarity.append(projected)
        if row.get("function") == "code" and projected["ownerClass"] == "Unresolved":
            function_name_collision.append(projected)
    if not zod_similarity:
        fail("message-similarity counterexample was incorrectly classified")
    if not function_name_collision:
        fail("same lexical function-name counterexample was incorrectly classified")

    original_rules = rules_path.read_bytes()
    original_digest = module.EXPECTED_RULES_SHA256
    original_rules_path = module.RULES_PATH
    with tempfile.TemporaryDirectory(prefix="claude-error-owner-negative-") as temporary:
        temporary_rules = Path(temporary) / "rules.json"
        temporary_rules.write_bytes(original_rules)
        module.RULES_PATH = str(temporary_rules)
        try:
            # Navigation is display-only. Expanding every range to the full
            # bundle must not alter one exact owner classification.
            expanded = json.loads(original_rules)
            for rule in expanded["rules"]:
                rule["navigationOnly"]["canonicalLines"] = [1, 65_943]
                rule["navigationOnly"]["minimumOffset"] = 0
                rule["navigationOnly"]["maximumOffset"] = 27_305_344
            expanded_data = write_rules(temporary_rules, expanded)
            module.EXPECTED_RULES_SHA256 = module.sha256_bytes(expanded_data)
            inputs = module.load_inputs(root)
            _rules, expanded_by_identity = module.validate_rules(root, inputs)
            expanded_projection = module.build_projection(inputs, expanded_by_identity)
            if classification_map(expanded_projection) != classification_map(projection):
                fail("expanded navigation range changed owner classification")

            temporary_rules.write_bytes(original_rules)
            module.EXPECTED_RULES_SHA256 = original_digest

            # Deleting one exact identity without repairing the rule digest is
            # rejected before a reduced-coverage projection can be emitted.
            deleted = json.loads(original_rules)
            deleted["rules"][0]["exactCallsiteIds"] = deleted["rules"][0]["exactCallsiteIds"][1:]
            deleted_data = write_rules(temporary_rules, deleted)
            module.EXPECTED_RULES_SHA256 = module.sha256_bytes(deleted_data)
            expect_failure(
                lambda: module.validate_rules(root, module.load_inputs(root)),
                "exact callsite count mismatch",
            )

            temporary_rules.write_bytes(original_rules)
            module.EXPECTED_RULES_SHA256 = original_digest

            # A fabricated exact identity remains invalid even if an attacker
            # updates the list count/digest and top-level rules digest.
            fabricated = json.loads(original_rules)
            target = fabricated["rules"][0]
            target["exactCallsiteIds"][-1] = "error:" + "0" * 64
            target["exactCallsiteDigest"] = module.sha256_bytes(
                module.canonical_json(target["exactCallsiteIds"])
            )
            fabricated_data = write_rules(temporary_rules, fabricated)
            module.EXPECTED_RULES_SHA256 = module.sha256_bytes(fabricated_data)
            expect_failure(
                lambda: module.validate_rules(root, module.load_inputs(root)),
                "exact callsite identity no longer exists",
            )

            temporary_rules.write_bytes(original_rules)
            module.EXPECTED_RULES_SHA256 = original_digest

            # Owner text itself is part of the reviewed rules hash. The normal
            # validator (without monkeypatching the digest) rejects mutation.
            owner_tamper = json.loads(original_rules)
            owner_tamper["rules"][0]["owner"] = "wide-range-guessed-owner"
            write_rules(temporary_rules, owner_tamper)
            expect_failure(
                lambda: module.validate_rules(root, module.load_inputs(root)),
                "reviewed owner rule digest changed",
            )

            temporary_rules.write_bytes(original_rules)
            flow_tamper = json.loads(original_rules)
            catch_rule = next(
                rule
                for rule in flow_tamper["rules"]
                if rule["ruleId"] == "product-permission-hook-catch-diagnostic"
            )
            catch_rule["productFlow"]["catchOwner"] = "wide-range-guessed-catch"
            write_rules(temporary_rules, flow_tamper)
            expect_failure(
                lambda: module.validate_rules(root, module.load_inputs(root)),
                "reviewed owner rule digest changed",
            )
        finally:
            module.RULES_PATH = original_rules_path
            module.EXPECTED_RULES_SHA256 = original_digest

    restored_artifacts, restored_summary = module.generated_artifacts(root)
    if restored_summary != baseline_summary or restored_artifacts != baseline_artifacts:
        fail("owner projection did not restore byte-for-byte after negative mutations")

    print(
        json.dumps(
            {
                "version": module.EXPECTED_VERSION,
                "totalCallsites": 10_234,
                "mappedCallsites": 684,
                "classification": module.EXPECTED_OWNER_COUNTS,
                "productFlowResolved": {
                    "catch": len(catch_resolved_rows),
                    "retry": retry_resolved,
                    "toolResult": tool_result_resolved,
                    "userSurface": 0,
                },
                "broadLineCounterexamples": len(same_line_counterexamples),
                "messageSimilarityCounterexamples": len(zod_similarity),
                "sameFunctionNameCounterexamples": len(function_name_collision),
                "broadNavigationCannotClassify": True,
                "identityDeletionRejected": True,
                "fabricatedIdentityRejected": True,
                "ownerTamperRejected": True,
                "catchFlowTamperRejected": True,
                "deterministic": True,
                "restored": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
