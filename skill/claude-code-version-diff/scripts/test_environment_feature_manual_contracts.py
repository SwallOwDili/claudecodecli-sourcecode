#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "skill/claude-code-version-diff/scripts/build_environment_feature_references.py"


def load_generator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_environment_feature_references", GENERATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_value_error(action: Callable[[], None], fragment: str) -> None:
    try:
        action()
    except ValueError as error:
        if fragment not in str(error):
            raise AssertionError(
                f"expected error containing {fragment!r}, got {str(error)!r}"
            ) from error
        return
    raise AssertionError(f"expected ValueError containing {fragment!r}")


def mutate_and_reject(
    contract: dict[str, Any],
    field: str,
    value: Any,
    validation: Callable[[], None],
    fragment: str,
) -> None:
    sentinel = object()
    previous = contract.get(field, sentinel)
    contract[field] = value
    try:
        expect_value_error(validation, fragment)
    finally:
        if previous is sentinel:
            contract.pop(field, None)
        else:
            contract[field] = previous


def main() -> int:
    module = load_generator()
    inventory = ROOT / "analysis/source-inventory"
    env_calls = module.read_jsonl(inventory / "environment-access-callsites.jsonl")
    feature_calls = module.read_jsonl(inventory / "feature-flag-callsites.jsonl")
    feature_keys = [
        line.strip()
        for line in (inventory / "feature-flags.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    validate_env = lambda: module.validate_environment_manual_contracts(env_calls)
    validate_feature = lambda: module.validate_feature_manual_contracts(
        feature_keys, feature_calls
    )
    validate_env()
    validate_feature()

    if "tengu_ant_yolo_equiv_strip_config" in module.FEATURE_MANUAL_CONTRACTS:
        raise AssertionError("dormant exported predicate must remain Semantic follow-up")
    if "tengu_moss_anchor" not in module.FEATURE_MANUAL_CONTRACTS:
        raise AssertionError("reachable noninteractive Auto-default contract is missing")

    env_contract = module.ENV_MANUAL_CONTRACTS["CODESPACES"]
    mutate_and_reject(
        env_contract,
        "callsiteCount",
        2,
        validate_env,
        "callsite drift",
    )
    mutate_and_reject(
        env_contract,
        "lexicalFunctions",
        ("inventedOwner",),
        validate_env,
        "lexical owner drift",
    )
    mutate_and_reject(
        env_contract,
        "accessModes",
        ("write",),
        validate_env,
        "access-mode drift",
    )
    mutate_and_reject(
        env_contract,
        "userImpact",
        "",
        validate_env,
        "invalid userImpact",
    )

    feature_contract = module.FEATURE_MANUAL_CONTRACTS[
        "tengu_classifier_disabled_surfaces"
    ]
    mutate_and_reject(
        feature_contract,
        "callsiteCount",
        2,
        validate_feature,
        "callsite drift",
    )
    mutate_and_reject(
        feature_contract,
        "lexicalFunctions",
        ("inventedOwner",),
        validate_feature,
        "lexical owner drift",
    )
    mutate_and_reject(
        feature_contract,
        "failureBoundary",
        "",
        validate_feature,
        "invalid failureBoundary",
    )

    print(
        "environment/feature manual contracts: PASS "
        f"({len(module.ENV_MANUAL_CONTRACTS)} environment, "
        f"{len(module.FEATURE_MANUAL_CONTRACTS)} feature, "
        "7 negative mutations rejected, dormant-export guard passed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
