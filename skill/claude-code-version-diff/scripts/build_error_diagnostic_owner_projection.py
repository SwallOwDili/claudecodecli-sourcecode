#!/usr/bin/env python3
"""Build the exact-callsite Error/Diagnostic owner projection for 2.1.235."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable


EXPECTED_VERSION = "2.1.235"
EXPECTED_INPUTS = {
    "error": {
        "path": "analysis/source-inventory/error-message-callsites.jsonl",
        "lines": 4_831,
        "size": 5_639_025,
        "sha256": "1eeaaae9fd4f90ede1539c435b544315c39989d4f8747c48085b3a1c9043d205",
    },
    "diagnostic": {
        "path": "analysis/source-inventory/diagnostic-message-callsites.jsonl",
        "lines": 5_403,
        "size": 8_218_613,
        "sha256": "1cef982ab45ace333aaed9fa1d7488f2f153bb3828c48804d046c1c68f437bd6",
    },
}
RULES_PATH = "analysis/error-diagnostic-owner-rules.json"
PROJECTION_PATH = "analysis/error-diagnostic-owner-projection.jsonl"
SUMMARY_PATH = "analysis/error-diagnostic-owner-summary.json"
INDEX_PATH = "analysis/error-diagnostic-owner-index.md"

# Filled after the reviewed rule set is bootstrapped. These constants make rule
# deletion or silent coverage drift a validation failure on the fixed release.
EXPECTED_RULES_SHA256 = "58454341fe4b5135e5cd1908ec07a437485e9b75827841dd17bb2d566a90a749"
EXPECTED_RULE_COUNT = 49
EXPECTED_OWNER_COUNTS = {
    "Product": 308,
    "Dependency": 376,
    "Unresolved": 9_550,
}
EXPECTED_STREAM_OWNER_COUNTS = {
    "Error constructor": {
        "Product": 54,
        "Dependency": 376,
        "Unresolved": 4_401,
    },
    "Diagnostic callsite": {
        "Product": 254,
        "Dependency": 0,
        "Unresolved": 5_149,
    },
}


@dataclasses.dataclass(frozen=True)
class Seed:
    rule_id: str
    stream: str
    owner_class: str
    owner: str
    scenario: str
    exact_scopes: tuple[str, ...] = ()
    message_pattern: str | None = None
    package_function: str | None = None
    catch_owner: str | None = None
    retry_owner: str | None = None
    tool_result_owner: str | None = None
    user_surface_owner: str | None = None
    boundary: str = "Static ownership does not prove runtime reachability or observed failure frequency."


def product_seed(
    rule_id: str,
    stream: str,
    owner: str,
    scenario: str,
    scopes: Iterable[str],
    *,
    catch_owner: str | None = None,
    retry_owner: str | None = None,
    tool_result_owner: str | None = None,
    user_surface_owner: str | None = None,
    boundary: str = "No exact runtime Probe proves that this branch executed in the inspected session.",
) -> Seed:
    return Seed(
        rule_id,
        stream,
        "Product",
        owner,
        scenario,
        tuple(scopes),
        catch_owner=catch_owner,
        retry_owner=retry_owner,
        tool_result_owner=tool_result_owner,
        user_surface_owner=user_surface_owner,
        boundary=boundary,
    )


def dependency_scope_seed(
    rule_id: str,
    owner: str,
    scenario: str,
    scopes: Iterable[str],
    package_function: str,
) -> Seed:
    return Seed(
        rule_id,
        "error",
        "Dependency",
        owner,
        scenario,
        tuple(scopes),
        package_function=package_function,
        boundary="The dependency constructor is proven; its Product catch, translation and user surface remain unresolved until a first-party caller is traced.",
    )


def dependency_message_seed(
    rule_id: str,
    owner: str,
    scenario: str,
    message_pattern: str,
    package_function: str,
) -> Seed:
    return Seed(
        rule_id,
        "error",
        "Dependency",
        owner,
        scenario,
        message_pattern=message_pattern,
        package_function=package_function,
        boundary="The exact constructor belongs to the bundled dependency; Product catch/recovery and runtime reachability are not inferred from its message.",
    )


SEEDS = (
    product_seed(
        "product-compact-reactive-error",
        "error",
        "context/compact",
        "reactive compact response validation",
        ("1.49954",),
    ),
    product_seed(
        "product-compact-manual-error",
        "error",
        "context/compact",
        "manual compact model policy gate",
        ("1.50099",),
    ),
    product_seed(
        "product-compact-reactive-diagnostic",
        "diagnostic",
        "context/compact",
        "reactive compact hook and response diagnostics",
        ("1.47336", "1.49954"),
    ),
    product_seed(
        "product-compact-reactive-retry-diagnostic",
        "diagnostic",
        "context/compact",
        "reactive compact bounded retry ladder",
        ("1.49959",),
        retry_owner="reactive compact media-strip and prompt-gap ladder",
    ),
    product_seed(
        "product-compact-precomputed-diagnostic",
        "diagnostic",
        "context/compact",
        "precomputed compact sidecar lifecycle",
        (
            "1.49987",
            "1.49998",
            "1.50003",
            "1.50005",
            "1.50011",
            "1.50011.50012",
            "1.50020",
            "1.50024",
            "1.50035",
        ),
    ),
    product_seed(
        "product-compact-manual-auto-diagnostic",
        "diagnostic",
        "context/compact",
        "manual compact and context-hint diagnostics",
        (
            "1.50080",
            "1.50087",
            "1.50132",
            "1.50151",
        ),
    ),
    product_seed(
        "product-compact-fallback-breaker-diagnostic",
        "diagnostic",
        "context/compact",
        "manual compact fallback and autocompact breakers",
        ("1.50099", "1.50128", "1.50133"),
        retry_owner="model fallback, circuit breaker and rapid-refill owner",
    ),
    product_seed(
        "product-transcript-compact-diagnostic",
        "diagnostic",
        "session/transcript",
        "Storage V5 transcript compact",
        ("1.75147", "1.75158", "1.75158.75160"),
    ),
    product_seed(
        "product-tool-result-error",
        "error",
        "tool/runtime",
        "tool-result graph invariants",
        ("1.54812.54876", "1.67548", "1.74686"),
        tool_result_owner="tool-result ledger and model-message pairing guard",
    ),
    product_seed(
        "product-tool-result-diagnostic",
        "diagnostic",
        "tool/runtime",
        "tool-result persistence and context budget",
        ("1.35156", "1.35190"),
        tool_result_owner="tool-result ledger and context attachment owner",
    ),
    product_seed(
        "product-permission-hook-diagnostic",
        "diagnostic",
        "tool/hooks-permission",
        "PreTool and permission hook entry diagnostics",
        ("1.35484", "1.35489"),
    ),
    product_seed(
        "product-deferred-tool-resume-diagnostic",
        "diagnostic",
        "tool/hooks-permission",
        "deferred tool resume re-entry",
        ("1.43324",),
        tool_result_owner="deferred tool resume owner",
    ),
    product_seed(
        "product-end-turn-tool-result-diagnostic",
        "diagnostic",
        "tool/hooks-permission",
        "end-turn hook decisions after tool result",
        ("1.51511", "1.51685"),
        tool_result_owner="tool pipeline end-turn owner",
    ),
    product_seed(
        "product-hook-interrupt-diagnostic",
        "diagnostic",
        "tool/hooks-permission",
        "hook deny/interrupt decision diagnostic",
        ("1.53534.53544",),
    ),
    product_seed(
        "product-permission-hook-catch-diagnostic",
        "diagnostic",
        "tool/hooks-permission",
        "permission hook async failure/cancellation catch",
        ("1.53612.53617", "1.53612.53624"),
        catch_owner="permission request hook async catch boundary",
    ),
    product_seed(
        "product-post-tool-hook-catch-diagnostic",
        "diagnostic",
        "tool/hooks-permission",
        "PostToolUse cancellation/timeout catch",
        ("1.55101",),
        catch_owner="PostToolUse outer catch boundary",
    ),
    product_seed(
        "product-sandbox-error",
        "error",
        "sandbox/enforcement",
        "sandbox mount, bridge and platform invariants",
        (
            "1.27778.27804",
            "1.27821",
            "1.27917",
            "1.27980",
            "1.28025",
            "1.40610",
            "1.77624",
        ),
    ),
    product_seed(
        "product-sandbox-diagnostic",
        "diagnostic",
        "sandbox/enforcement",
        "sandbox trust compilation and one-shot relaxation",
        (
            "1.29914",
            "1.29914.29930",
            "1.29914.29956",
            "1.29914.29958",
            "1.29914.29959",
            "1.29914.29984",
            "1.29914.29985",
            "1.29997",
            "1.29998",
            "1.30009",
            "1.30055.30056",
            "1.30055.30057",
            "1.30055.30057.30058",
            "1.30070.30078",
            "1.40589",
            "1.40610.40623",
        ),
    ),
    product_seed(
        "product-sandbox-unsandboxed-retry-diagnostic",
        "diagnostic",
        "sandbox/enforcement",
        "REPL sandbox violation one-shot relaxation",
        ("1.55192.55193",),
        retry_owner="single unsandboxed retry gate",
    ),
    product_seed(
        "product-mcp-config-error",
        "error",
        "mcp/config-policy",
        "MCP trust, policy and local config guards",
        (
            "1.71746",
            "1.71810",
            "1.71826",
            "1.72364",
            "1.72416.72417.72421",
            "1.72514.72517",
            "1.72834",
            "1.72894",
            "1.73109",
            "1.73161.73162.73166",
            "1.73256.73258",
            "1.73416",
            "1.73421",
            "1.73439",
        ),
    ),
    product_seed(
        "product-mcp-config-diagnostic",
        "diagnostic",
        "mcp/config-policy",
        "MCPB, plugin, connector and policy compilation",
        (
            "1.51907",
            "1.51907.51908",
            "1.51911",
            "1.51911.51912",
            "1.51911.51914",
            "1.51915",
            "1.51920",
            "1.51936",
            "1.52059",
            "1.52068",
            "1.52077",
            "1.52087",
            "1.52112",
            "1.52118",
            "1.52131",
            "1.52521",
            "1.52522",
            "1.52522.52525",
            "1.52522.52529",
        ),
    ),
    product_seed(
        "product-mcp-connector-retry-diagnostic",
        "diagnostic",
        "mcp/config-policy",
        "claude.ai MCP connector bounded fetch",
        ("1.51944",),
        retry_owner="claude.ai connector bounded fetch budget",
    ),
    product_seed(
        "product-session-persistence-diagnostic",
        "diagnostic",
        "session/persistence",
        "remote session persistence conflict and retry",
        ("1.25591",),
        retry_owner="remote persistence conflict/backoff owner",
    ),
    product_seed(
        "product-session-continuity-diagnostic",
        "diagnostic",
        "session/persistence",
        "transcript and persistence continuity diagnostics",
        (
            "1.49931.49932",
            "1.49931.49933",
            "1.52532",
            "1.75184",
            "1.92118",
            "1.94063",
            "1.94069",
        ),
    ),
    product_seed(
        "product-request-recovery-diagnostic",
        "diagnostic",
        "model/request",
        "request degradation, retry and fallback",
        (
            "1.51699",
            "1.60841",
            "1.62435",
            "1.62455",
            "1.62469",
            "1.68715",
            "1.76343",
            "1.76343.76367.76368",
            "1.76343.76375",
            "1.76343.76390",
        ),
        retry_owner="request attempt, fallback-model and payload-repair controllers",
    ),
    dependency_scope_seed(
        "dependency-mcp-sdk-sampling",
        "@modelcontextprotocol/sdk",
        "sampling tool-result pairing and capability validation",
        (
            "1.7627",
            "1.7644.7652",
            "1.7644.7653",
            "1.7644.7655",
            "1.7644.7656",
            "1.7644.7657",
            "1.7644.7665",
            "1.7644.7674",
            "1.7644.7675",
        ),
        "Client methods createMessageStream/createMessage and exact capability guards",
    ),
    dependency_scope_seed(
        "dependency-anthropic-sdk-fetch",
        "@anthropic-ai/sdk",
        "Stainless Anthropic client fetch precondition",
        ("1.2712",),
        "Anthropic client fetch shim VQc",
    ),
    dependency_message_seed(
        "dependency-smithy-util-utf8",
        "@smithy/util-utf8",
        "UTF-8 encoder contract",
        r"@smithy/util-utf8:",
        "toUtf8 encoder",
    ),
    dependency_message_seed(
        "dependency-smithy-util-base64",
        "@smithy/util-base64",
        "base64 encoder contract",
        r"@smithy/util-base64:",
        "toBase64 encoder",
    ),
    dependency_message_seed(
        "dependency-smithy-node-http-handler",
        "@smithy/node-http-handler",
        "socket connect and inactivity timeout",
        r"@smithy/node-http-handler",
        "NodeHttpHandler timeout guards",
    ),
    dependency_message_seed(
        "dependency-smithy-util-stream",
        "@smithy/util-stream",
        "stream source, capability and index guards",
        r"@smithy/util-stream",
        "ChecksumStream and stream helpers",
    ),
    dependency_message_seed(
        "dependency-smithy-core-schema",
        "@smithy/core/schema",
        "Smithy normalized schema invariants",
        r"@smithy/core/schema",
        "NormalizedSchema and protocol schema helpers",
    ),
    dependency_message_seed(
        "dependency-smithy-core-serde",
        "@smithy/core/serde",
        "Smithy numeric serde invariant",
        r"@smithy/core/serde",
        "NumericValue parser",
    ),
    dependency_message_seed(
        "dependency-smithy-core-event-streams",
        "@smithy/core/event-streams",
        "Smithy event-stream union guard",
        r"@smithy/core/event-streams",
        "event stream serializer",
    ),
    dependency_message_seed(
        "dependency-smithy-core-protocols",
        "@smithy/core/protocols",
        "Smithy HTTP protocol implementation guards",
        r"@smithy/core/protocols",
        "HTTP protocol base methods",
    ),
    dependency_message_seed(
        "dependency-smithy-core-base",
        "@smithy/core",
        "Smithy HTTP protocol base invariant",
        r"@smithy/core - ",
        "HttpProtocol event-stream marshaller guard",
    ),
    dependency_message_seed(
        "dependency-smithy-core-cbor",
        "@smithy/core/cbor",
        "Smithy CBOR precision and undefined-value guards",
        r"@smithy/core/cbor",
        "CBOR serializer",
    ),
    dependency_message_seed(
        "dependency-smithy-middleware-endpoint",
        "@smithy/middleware-endpoint",
        "Smithy endpoint configuration guard",
        r"@smithy/middleware-endpoint",
        "default endpoint rule-set resolver",
    ),
    dependency_message_seed(
        "dependency-aws-sdk-core",
        "@aws-sdk/core",
        "AWS SDK credential and protocol invariants",
        r"@aws-sdk/core",
        "SigV4 configuration and protocol serializers",
    ),
    dependency_message_seed(
        "dependency-aws-sdk-credential-providers",
        "@aws-sdk/credential-providers",
        "AWS credential source/profile guards",
        r"@aws-sdk/credential-providers",
        "credential provider profile resolver",
    ),
    dependency_message_seed(
        "dependency-aws-sdk-util-endpoint",
        "@aws-sdk/util-endpoint",
        "AWS endpoint provider precondition",
        r"@aws-sdk/util-endpoint",
        "endpoint configuration resolver",
    ),
    dependency_message_seed(
        "dependency-opentelemetry-api",
        "@opentelemetry/api",
        "OpenTelemetry global API registration guards",
        r"@opentelemetry/api:",
        "global API register/version check",
    ),
    dependency_scope_seed(
        "dependency-protobufjs-reader",
        "protobufjs/minimal",
        "protobuf wire reader bounds and encoding guards",
        (
            "1.63353.63354",
            "1.63353.63356",
            "1.63353.63357",
            "1.63353.63365",
            "1.63353.63376",
        ),
        "Reader index/varint/wire-type guards",
    ),
    dependency_scope_seed(
        "dependency-grpc-service-config",
        "@grpc/grpc-js",
        "gRPC service config, retry, hedging and load-balancing validation",
        (
            "1.64314.64315",
            "1.64314.64316",
            "1.64314.64317",
            "1.64314.64318",
            "1.64314.64319",
            "1.64314.64320",
            "1.64314.64321",
            "1.64314.64322",
            "1.64314.64323",
        ),
        "service-config parser and retry/hedging policy validators",
    ),
    dependency_scope_seed(
        "dependency-google-auth-oauth2client",
        "google-auth-library",
        "OAuth2Client token, certificate and refresh-handler guards",
        (
            "1.20986.20991",
            "1.20986.20992",
            "1.20986.21001",
            "1.20986.21007",
            "1.20986.21009",
            "1.20986.21016",
            "1.20986.21021",
            "1.20986.21023",
            "1.20986.21027",
            "1.20986.21031",
            "1.20986.21032",
            "1.20986.21033",
        ),
        "OAuth2Client auth URL, refresh, ID-token and signed-JWT validators",
    ),
    dependency_scope_seed(
        "dependency-jose",
        "jose",
        "JWS/JWT/JWK algorithm, key-type and claims validation",
        (
            "1.102244",
            "1.102245",
            "1.102338",
            "1.102350",
            "1.102371",
            "1.102410",
            "1.102462.102466",
            "1.102462.102468",
            "1.102476.102477",
            "1.102625.102631",
            "1.102712.102772",
            "1.102928",
            "1.102937",
            "1.102958",
            "1.102959",
            "1.102982",
            "1.102992",
        ),
        "JWS/JWT/JWK validation functions",
    ),
    dependency_message_seed(
        "dependency-opentelemetry-protobuf",
        "protobufjs OpenTelemetry OTLP generated codec",
        "OTLP protobuf object/array verification",
        r"^\"\.opentelemetry\.proto\.",
        "generated verify/fromObject field guards",
    ),
    dependency_message_seed(
        "dependency-ajv",
        "ajv",
        "Ajv compiler internal invariants",
        r"^(?:\"ajv implementation error\"|\"ajv\.removeSchema: invalid parameter\")$",
        "schema compiler and removeSchema",
    ),
    dependency_message_seed(
        "dependency-zod",
        "zod",
        "Zod schema conversion internal invariants",
        r"^(?:\"Unprocessed schema\. This is a bug in Zod\.\"|\"Internal ZodObject error: invalid unknownKeys value\.\"|\"Uninitialized schema in ZodMiniType\.\"|\"Mixed Zod versions detected in object shape\.\")$",
        "Zod parser and JSON Schema converter",
    ),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def fail(message: str) -> None:
    raise ValueError(message)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    os.replace(temporary, path)


def source_text(row: dict[str, Any]) -> str:
    return str(row.get("nameArgument", {}).get("source", {}).get("text", ""))


def message_sha(row: dict[str, Any]) -> str | None:
    value = row.get("nameArgument", {}).get("source", {}).get("sha256")
    return value if isinstance(value, str) else None


def consumer_projection(row: dict[str, Any]) -> dict[str, Any]:
    consumer = row.get("consumer", {})
    return {
        key: consumer.get(key)
        for key in ("parentType", "relation", "role", "target")
        if consumer.get(key) is not None
    }


def row_identity_payload(stream: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stream": stream,
        "calleeRole": row.get("calleeRole"),
        "comparisonKey": row.get("comparisonKey"),
        "canonical": {
            "line": row.get("line"),
            "column": row.get("column"),
            "offset": row.get("offset"),
        },
        "lexical": {
            "scopePath": row.get("scopePath", []),
            "functionKind": row.get("functionKind"),
            "function": row.get("function"),
        },
        "immediateConsumer": consumer_projection(row),
        "message": {
            "kind": row.get("nameArgument", {}).get("kind"),
            "sha256": message_sha(row),
        },
    }


def row_identity(stream: str, row: dict[str, Any]) -> str:
    return f"{stream}:{sha256_bytes(canonical_json(row_identity_payload(stream, row)))}"


def load_inputs(root: Path) -> dict[str, list[dict[str, Any]]]:
    if (root / "VERSION").read_text(encoding="utf-8").strip() != EXPECTED_VERSION:
        fail(f"owner projection only supports {EXPECTED_VERSION}")
    summary = json.loads((root / "analysis/source-inventory/summary.json").read_text(encoding="utf-8"))
    registered = {item["path"]: item for item in summary.get("files", [])}
    result: dict[str, list[dict[str, Any]]] = {}
    for stream, contract in EXPECTED_INPUTS.items():
        path = root / contract["path"]
        data = path.read_bytes()
        observed = {
            "lines": data.count(b"\n"),
            "size": len(data),
            "sha256": sha256_bytes(data),
        }
        expected = {key: contract[key] for key in observed}
        if observed != expected:
            fail(f"{stream} source inventory fingerprint changed: {observed}")
        registration = registered.get(contract["path"])
        if registration is None:
            fail(f"summary.json does not register {contract['path']}")
        if {key: registration.get(key) for key in observed} != observed:
            fail(f"summary.json fingerprint mismatch for {contract['path']}")
        rows = read_jsonl(path)
        if len(rows) != contract["lines"]:
            fail(f"{stream} parsed row count changed")
        result[stream] = rows
    return result


def select_seed(seed: Seed, inputs: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = inputs[seed.stream]
    if seed.exact_scopes:
        scopes = set(seed.exact_scopes)
        selected = [row for row in rows if ".".join(map(str, row.get("scopePath", []))) in scopes]
        found = {".".join(map(str, row.get("scopePath", []))) for row in selected}
        missing = sorted(scopes - found)
        if missing:
            fail(f"seed {seed.rule_id} has empty exact scope(s): {missing}")
    elif seed.message_pattern is not None:
        pattern = re.compile(seed.message_pattern)
        selected = [row for row in rows if pattern.search(source_text(row))]
    else:
        fail(f"seed {seed.rule_id} has no selector")
    if not selected:
        fail(f"seed {seed.rule_id} selects no callsites")
    return sorted(selected, key=lambda row: (row["offset"], row["comparisonKey"]))


def bootstrap_rules(inputs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    seen: dict[str, str] = {}
    rules = []
    for seed in SEEDS:
        selected = select_seed(seed, inputs)
        identities = [row_identity(seed.stream, row) for row in selected]
        overlap = [(identity, seen[identity]) for identity in identities if identity in seen]
        if overlap:
            fail(f"seed {seed.rule_id} overlaps exact identities: {overlap[:3]}")
        for identity in identities:
            seen[identity] = seed.rule_id
        representative = next(
            (
                row
                for row in selected
                if row.get("nameArgument", {}).get("kind") in {"string", "template"}
                and len(source_text(row)) >= 8
            ),
            selected[0],
        )
        flow = None
        if seed.owner_class == "Product":
            flow = {
                "catchOwner": seed.catch_owner,
                "retryOwner": seed.retry_owner,
                "toolResultOwner": seed.tool_result_owner,
                "userSurfaceOwner": seed.user_surface_owner,
            }
        rules.append(
            {
                "ruleId": seed.rule_id,
                "stream": seed.stream,
                "ownerClass": seed.owner_class,
                "owner": seed.owner,
                "scenario": seed.scenario,
                "packageFunction": seed.package_function,
                "productFlow": flow,
                "boundary": seed.boundary,
                "reviewSelector": {
                    "exactScopes": list(seed.exact_scopes),
                    "messagePattern": seed.message_pattern,
                    "classificationInput": False,
                },
                "navigationOnly": {
                    "canonicalLines": sorted({row["line"] for row in selected}),
                    "minimumOffset": min(row["offset"] for row in selected),
                    "maximumOffset": max(row["offset"] for row in selected),
                },
                "representative": {
                    "identity": row_identity(seed.stream, representative),
                    "lexicalFunction": representative.get("function"),
                    "messageSha256": message_sha(representative),
                    "messagePreview": source_text(representative)[:240],
                },
                "exactCallsiteIds": identities,
                "exactCallsiteDigest": sha256_bytes(canonical_json(identities)),
                "expectedCount": len(identities),
            }
        )
    return {
        "schemaVersion": 1,
        "sourceVersion": EXPECTED_VERSION,
        "classificationKey": "exactCallsiteIds only",
        "navigationAndReviewSelectorsClassify": False,
        "sourceInputs": EXPECTED_INPUTS,
        "rules": rules,
    }


def validate_rules(
    root: Path,
    inputs: dict[str, list[dict[str, Any]]],
    *,
    allow_bootstrap_constants: bool = False,
) -> tuple[dict[str, Any], dict[str, tuple[str, dict[str, Any]]]]:
    path = root / RULES_PATH
    data = path.read_bytes()
    rules_digest = sha256_bytes(data)
    if not allow_bootstrap_constants and rules_digest != EXPECTED_RULES_SHA256:
        fail(f"reviewed owner rule digest changed: {rules_digest}")
    document = json.loads(data)
    if document.get("schemaVersion") != 1 or document.get("sourceVersion") != EXPECTED_VERSION:
        fail("owner rule schema/version mismatch")
    if document.get("classificationKey") != "exactCallsiteIds only":
        fail("owner rules no longer require exact callsite identity")
    if document.get("navigationAndReviewSelectorsClassify") is not False:
        fail("navigation/review selectors must not classify")
    by_identity: dict[str, tuple[str, dict[str, Any]]] = {}
    source_identities: dict[str, tuple[str, dict[str, Any]]] = {}
    for stream, rows in inputs.items():
        for row in rows:
            identity = row_identity(stream, row)
            if identity in source_identities:
                fail(f"source exact identity collision: {identity}")
            source_identities[identity] = (stream, row)
    rules = document.get("rules")
    if not isinstance(rules, list):
        fail("owner rules must be a list")
    if not allow_bootstrap_constants and len(rules) != EXPECTED_RULE_COUNT:
        fail(f"owner rule count changed: {len(rules)}")
    rule_ids: set[str] = set()
    for rule in rules:
        rule_id = rule.get("ruleId")
        if not isinstance(rule_id, str) or not rule_id or rule_id in rule_ids:
            fail(f"invalid/duplicate owner rule id: {rule_id}")
        rule_ids.add(rule_id)
        if rule.get("ownerClass") not in {"Product", "Dependency"}:
            fail(f"invalid owner class in {rule_id}")
        if not rule.get("owner") or not rule.get("scenario") or not rule.get("boundary"):
            fail(f"empty owner/scenario/boundary in {rule_id}")
        if rule.get("ownerClass") == "Dependency" and not rule.get("packageFunction"):
            fail(f"dependency rule lacks exact package/function evidence: {rule_id}")
        if rule.get("ownerClass") == "Product":
            flow = rule.get("productFlow")
            if not isinstance(flow, dict) or set(flow) != {
                "catchOwner",
                "retryOwner",
                "toolResultOwner",
                "userSurfaceOwner",
            }:
                fail(f"Product flow fields are incomplete: {rule_id}")
        selector = rule.get("reviewSelector", {})
        if selector.get("classificationInput") is not False:
            fail(f"review selector became a classifier: {rule_id}")
        identities = rule.get("exactCallsiteIds")
        if not isinstance(identities, list) or not identities:
            fail(f"rule has no exact callsite identities: {rule_id}")
        if len(identities) != rule.get("expectedCount"):
            fail(f"exact callsite count mismatch: {rule_id}")
        if sha256_bytes(canonical_json(identities)) != rule.get("exactCallsiteDigest"):
            fail(f"exact callsite digest mismatch: {rule_id}")
        representative = rule.get("representative", {})
        if representative.get("identity") not in identities:
            fail(f"representative identity is not selected: {rule_id}")
        for identity in identities:
            if identity not in source_identities:
                fail(f"exact callsite identity no longer exists: {rule_id}/{identity}")
            if identity in by_identity:
                fail(f"exact callsite identity owned twice: {identity}")
            stream, row = source_identities[identity]
            if stream != rule.get("stream"):
                fail(f"rule stream mismatch: {rule_id}/{identity}")
            by_identity[identity] = (rule_id, rule)
        rep_stream, rep_row = source_identities[representative["identity"]]
        if rep_stream != rule["stream"]:
            fail(f"representative stream mismatch: {rule_id}")
        if representative.get("lexicalFunction") != rep_row.get("function"):
            fail(f"representative lexical function mismatch: {rule_id}")
        if representative.get("messageSha256") != message_sha(rep_row):
            fail(f"representative message fingerprint mismatch: {rule_id}")
    return document, by_identity


def evidence_state(owner: str | None) -> dict[str, Any]:
    if owner is None:
        return {"status": "Unresolved", "owner": None}
    return {"status": "Resolved exact rule", "owner": owner}


def projection_row(
    stream: str,
    row: dict[str, Any],
    mapping: tuple[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    identity = row_identity(stream, row)
    if mapping is None:
        owner_class = "Unresolved"
        classification = "Unresolved"
        owner = None
        rule_id = None
        scenario = None
        package_function = None
        product_flow = None
        boundary = "No reviewed exact callsite identity maps this constructor/diagnostic to a Product or Dependency owner."
    else:
        rule_id, rule = mapping
        owner_class = rule["ownerClass"]
        classification = (
            "Product exact caller"
            if owner_class == "Product"
            else "Dependency exact package/function"
        )
        owner = rule["owner"]
        scenario = rule["scenario"]
        package_function = rule.get("packageFunction")
        flow = rule.get("productFlow")
        product_flow = None
        if owner_class == "Product":
            product_flow = {
                "catchOwner": evidence_state(flow.get("catchOwner")),
                "retryOwner": evidence_state(flow.get("retryOwner")),
                "toolResultOwner": evidence_state(flow.get("toolResultOwner")),
                "userSurfaceOwner": evidence_state(flow.get("userSurfaceOwner")),
            }
        boundary = rule["boundary"]
    name = row.get("nameArgument", {})
    result = {
        "schemaVersion": 1,
        "sourceVersion": EXPECTED_VERSION,
        "identity": identity,
        "stream": "Error constructor" if stream == "error" else "Diagnostic callsite",
        "classification": classification,
        "ownerClass": owner_class,
        "owner": owner,
        "ruleId": rule_id,
        "scenario": scenario,
        "dependencyPackageFunction": package_function,
        "canonical": {
            "line": row.get("line"),
            "column": row.get("column"),
            "offset": row.get("offset"),
            "comparisonKey": row.get("comparisonKey"),
        },
        "lexical": {
            "scopePath": row.get("scopePath", []),
            "functionKind": row.get("functionKind"),
            "function": row.get("function"),
        },
        "immediateConsumer": consumer_projection(row),
        "message": {
            "kind": name.get("kind"),
            "shape": name.get("templateShape"),
            "staticValue": name.get("staticValue"),
            "sourceSha256": message_sha(row),
        },
        "productFlow": product_flow,
        "boundary": boundary,
    }
    result["evidenceFingerprint"] = sha256_bytes(canonical_json(result))[:20]
    return result


def build_projection(
    inputs: dict[str, list[dict[str, Any]]],
    by_identity: dict[str, tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    result = []
    for stream in ("error", "diagnostic"):
        for row in sorted(inputs[stream], key=lambda item: (item["offset"], item["comparisonKey"])):
            identity = row_identity(stream, row)
            result.append(projection_row(stream, row, by_identity.get(identity)))
    if len(result) != 10_234:
        fail(f"projection row count changed: {len(result)}")
    if len({row["identity"] for row in result}) != len(result):
        fail("projection contains duplicate exact identities")
    return result


def owner_counts(projection: list[dict[str, Any]]) -> dict[str, int]:
    counter = collections.Counter(row["ownerClass"] for row in projection)
    return {key: counter[key] for key in ("Product", "Dependency", "Unresolved")}


def stream_owner_counts(projection: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for stream in ("Error constructor", "Diagnostic callsite"):
        counter = collections.Counter(
            row["ownerClass"] for row in projection if row["stream"] == stream
        )
        result[stream] = {
            key: counter[key] for key in ("Product", "Dependency", "Unresolved")
        }
    return result


def build_summary(
    rules_document: dict[str, Any],
    rules_data: bytes,
    projection: list[dict[str, Any]],
    projection_data: bytes,
) -> dict[str, Any]:
    counts = owner_counts(projection)
    by_stream = stream_owner_counts(projection)
    owners: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    scenarios: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    flow = collections.Counter()
    for row in projection:
        if row["owner"]:
            owners[row["owner"]][row["stream"]] += 1
        if row["scenario"]:
            scenarios[row["scenario"]][row["stream"]] += 1
        if row["productFlow"]:
            for field, state in row["productFlow"].items():
                flow[f"{field}:{state['status']}"] += 1
    return {
        "schemaVersion": 1,
        "sourceVersion": EXPECTED_VERSION,
        "totalCallsites": len(projection),
        "sourceCallsites": {
            "errorConstructors": EXPECTED_INPUTS["error"]["lines"],
            "diagnosticCallsites": EXPECTED_INPUTS["diagnostic"]["lines"],
        },
        "sourceInputs": EXPECTED_INPUTS,
        "classification": counts,
        "classificationByStream": by_stream,
        "mappedCallsites": counts["Product"] + counts["Dependency"],
        "unresolvedCallsites": counts["Unresolved"],
        "reviewedRuleCount": len(rules_document["rules"]),
        "ownerCounts": {
            owner: dict(sorted(counter.items())) for owner, counter in sorted(owners.items())
        },
        "scenarioCounts": {
            scenario: dict(sorted(counter.items()))
            for scenario, counter in sorted(scenarios.items())
        },
        "productFlowEvidence": dict(sorted(flow.items())),
        "classificationContract": {
            "exactCallsiteIdentityOnly": True,
            "lineRangesClassify": False,
            "messageSimilarityClassifies": False,
            "reviewSelectorsClassify": False,
            "unresolvedIsSemanticDebt": True,
        },
        "artifacts": {
            RULES_PATH: {
                "size": len(rules_data),
                "sha256": sha256_bytes(rules_data),
            },
            PROJECTION_PATH: {
                "lines": len(projection),
                "size": len(projection_data),
                "sha256": sha256_bytes(projection_data),
            },
        },
    }


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_index(
    rules_document: dict[str, Any],
    summary: dict[str, Any],
    projection: list[dict[str, Any]],
) -> str:
    counts = summary["classification"]
    by_stream = summary["classificationByStream"]
    flow = summary["productFlowEvidence"]
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    by_identity = {row["identity"]: row for row in projection}
    for rule in rules_document["rules"]:
        grouped[rule["scenario"]].append(rule)
    lines = [
        "# Claude Code CLI 2.1.235 Error/Diagnostic 精确 owner 索引",
        "",
        "**读者问题：** 4,831 个错误构造点和 5,403 个 diagnostic 调用点里，哪些真是 Claude Code 产品机制，哪些只是打包依赖，失败后又由谁捕获、重试、写 tool_result 或展示给用户？",
        "",
        "**一句话模型：** constructor/diagnostic 只说明“这里生成了失败对象或调试记录”；本投影只有在完整 exact callsite identity 命中人工规则时才授予 owner，行号区间和相似文案永远不能替代 caller、consumer 与 source fingerprint。",
        "",
        "## 结论：先把总数拆成三种证据状态",
        "",
        "| 状态 | Error constructor | Diagnostic | 合计 | 能证明什么 |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Product exact caller | {by_stream['Error constructor']['Product']:,} | {by_stream['Diagnostic callsite']['Product']:,} | {counts['Product']:,} | exact lexical caller 属于已审阅的客户端机制；catch/retry/tool-result/user-surface 仍逐字段判定 |",
        f"| Dependency exact package/function | {by_stream['Error constructor']['Dependency']:,} | {by_stream['Diagnostic callsite']['Dependency']:,} | {counts['Dependency']:,} | constructor 位于精确依赖 package/function；不自动继承产品恢复语义 |",
        f"| Unresolved | {by_stream['Error constructor']['Unresolved']:,} | {by_stream['Diagnostic callsite']['Unresolved']:,} | {counts['Unresolved']:,} | 只有 lexical/immediate consumer inventory，尚无经过复核的 owner |",
        f"| **全量** | **{EXPECTED_INPUTS['error']['lines']:,}** | **{EXPECTED_INPUTS['diagnostic']['lines']:,}** | **{len(projection):,}** | 每条 canonical callsite 恰好出现一次 |",
        "",
        "这不是把 `Unresolved` 换成漂亮标签。当前只收口高置信第一批；剩余记录继续作为可量化的 semantic debt。特别是 diagnostic 的 `T()` 名称在压缩 bundle 中可能与依赖局部符号碰撞，未审阅 scope 不按“看起来像日志”归 Product。",
        "",
        f"Product flow 继续独立 fail closed：catchOwner 仅 **{flow.get('catchOwner:Resolved exact rule', 0):,}** 条、retryOwner **{flow.get('retryOwner:Resolved exact rule', 0):,}** 条、toolResultOwner **{flow.get('toolResultOwner:Resolved exact rule', 0):,}** 条、userSurfaceOwner **{flow.get('userSurfaceOwner:Resolved exact rule', 0):,}** 条获得 exact rule。owner 已解析不会自动抬高四个 flow 字段。",
        "",
        "## 四个 Product 后续 owner 字段怎样读",
        "",
        "| 字段 | 它回答的问题 | `Resolved exact rule` 的门槛 |",
        "| --- | --- | --- |",
        "| `catchOwner` | 谁接住或翻译这个失败 | 已审阅 caller/catch wrapper；不能由 `Error` class 猜 |",
        "| `retryOwner` | 谁持有 attempt、backoff、fallback 或 breaker | callsite 所在精确机制直接维护该预算 |",
        "| `toolResultOwner` | 谁把失败写回模型消息图 | exact scope 位于 tool-result ledger/pairing/end-turn 链 |",
        "| `userSurfaceOwner` | 谁把结果变成 TUI/stderr/SDK 输出 | exact scope 或其已审阅 wrapper 明确拥有表面；debug 文案本身不算 |",
        "",
        "没有证据的字段写 `Unresolved`。同一条 Product callsite 可以确认 retry owner，却仍不知道最终是否进入 tool_result 或用户界面。",
        "",
        "## 场景索引：从故障症状追 owner，而不是翻流水账",
        "",
        "| 场景 | owner class / owner | mapped callsites | 已确认的状态机特征 | 仍不能断言 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for scenario in sorted(grouped):
        rules = grouped[scenario]
        identities = [identity for rule in rules for identity in rule["exactCallsiteIds"]]
        rows = [by_identity[identity] for identity in identities]
        owners = ", ".join(sorted({f"{rule['ownerClass']}: {rule['owner']}" for rule in rules}))
        flow_parts = []
        for field in ("catchOwner", "retryOwner", "toolResultOwner", "userSurfaceOwner"):
            values = sorted(
                {
                    rule["productFlow"][field]
                    for rule in rules
                    if rule.get("productFlow") and rule["productFlow"].get(field)
                }
            )
            if values:
                flow_parts.append(f"{field}={'; '.join(values)}")
        feature = "; ".join(flow_parts) or rules[0].get("packageFunction") or "exact lexical caller only"
        boundaries = "; ".join(sorted({rule["boundary"] for rule in rules}))
        lines.append(
            f"| {md_escape(scenario)} | {md_escape(owners)} | {len(rows):,} | {md_escape(feature)} | {md_escape(boundaries)} |"
        )
    lines.extend(
        [
            "",
            "## 五条值得读的机制结论",
            "",
            "### 1. compact 的失败不是一个 retry counter",
            "",
            "Reactive compact、precomputed sidecar、manual compact、model fallback、autocompact breaker 与 Storage V5 transcript compact 分属不同 owner。`retryOwner` 只有在精确 scope 直接持有 media-strip、prompt-gap ladder、re-arm cap、fallback 或 breaker 时才解析；它不能回答本次压缩是否真的触发，也不能把 transcript compact 的存储失败算成模型 API retry。",
            "",
            "### 2. tool_result 是因果账本，不是错误字符串的展示容器",
            "",
            "tool-result pairing、持久化、deferred resume 与 end-turn hook 各自拥有不同状态。只有进入 pairing/ledger 的 exact caller 才解析 `toolResultOwner`；PostTool diagnostic 即使写了 `error`，也可能只是观察到 hook 取消，并未产生新的模型反馈轮。",
            "",
            "### 3. sandbox failure 可能是风控成功，而不是可靠性失败",
            "",
            "mount pin、credential mask、bridge socket、platform capability 与 single unsandboxed retry 都是独立 guard。分类器把这些 exact Product caller 放入 sandbox owner，但只有 retry scope 能声明 retry owner；其他拒绝仍可能是 fail-closed 的预期结果。非零退出或 diagnostic 也不证明外部命令没有先产生副作用。",
            "",
            "### 4. MCP 有“依赖协议 guard”和“产品配置/策略”两层",
            "",
            "`@modelcontextprotocol/sdk` 的 capability/tool_result 校验属于 Dependency exact package/function；Claude Code 的 MCPB、workspace trust、managed policy、connector fetch 与 agent frontmatter 属于 Product exact caller。两层可能抛出相似 message，但恢复 owner 不同：SDK 抛给调用者，产品层才决定 config warning、reauth、tool failure 或用户表面。",
            "",
            "### 5. `level:error` 与 `Error(...)` 都不是产品故障率",
            "",
            "OpenTelemetry protobuf、Ajv、Zod、Smithy 和 Anthropic/MCP SDK 的 constructor 都打包在同一 bundle。dependency constructor 数量反映代码体积和生成器形状，不反映 Claude Code 用户遇到多少错误；diagnostic 是否写盘、上传或展示还受 logger、telemetry、privacy 和 UI gate 控制。",
            "",
            "## Exact classifier 合同",
            "",
            "1. 每条记录的 identity 绑定 stream、callee role、comparison key、canonical line/column/offset、scopePath、lexical function、immediate consumer 和 message source hash。",
            "2. owner lookup 只读取规则中的 `exactCallsiteIds`。`reviewSelector`、canonical line range、message preview 和 scenario 仅供审阅/导航，明确标记 `classificationInput=false`。",
            "3. rules 文件、两个 canonical input、投影 JSONL 都有固定 SHA-256；删除规则、修改 identity、换 owner 或改输入都会失败。",
            "4. 相似 message 不继承 owner；同一 lexical function 名出现在另一 scope 也不继承 owner；扩大导航范围不会增加 mapped callsite。",
            "5. Product 四个 flow 字段独立 fail closed；owner 已解析不等于 catch/retry/tool-result/user-surface 全解析。",
            "6. 机器摘要把这一约束固定为 `messageSimilarityClassifies=false`、`lineRangesClassify=false`、`reviewSelectorsClassify=false`；validator 会检查字段和值。",
            "",
            "## 机器产物与剩余欠账",
            "",
            f"- [`error-diagnostic-owner-projection.jsonl`]({PROJECTION_PATH.split('/')[-1]})：{len(projection):,} 条互斥投影，每个 callsite 一行；",
            f"- [`error-diagnostic-owner-summary.json`]({SUMMARY_PATH.split('/')[-1]})：覆盖、owner/scenario、flow 证据与全部 artifact hash；",
            f"- [`error-diagnostic-owner-rules.json`]({RULES_PATH.split('/')[-1]})：{len(rules_document['rules'])} 条 reviewed rules 和逐 callsite exact allowlist；",
            f"- 原始清单：[`error-message-callsites.jsonl`](source-inventory/error-message-callsites.jsonl) 与 [`diagnostic-message-callsites.jsonl`](source-inventory/diagnostic-message-callsites.jsonl)。",
            "",
            f"当前明确欠账是 **{counts['Unresolved']:,} / {len(projection):,} callsites Unresolved**。后续应按风险优先追 request terminal、tool failure、auth、filesystem write、remote side effect 和 process supervisor 的 caller/catch/user surface；不能用宽行区间或关键词批量填平。",
            "",
            "**Static：** 所有映射限定 2.1.235 canonical bundle 与当前 source-inventory hash。",
            "",
            "**Boundary：** 本投影不证明分支 runtime reachability、实际错误值、出现频率、日志写盘/上传、服务端接收/保留，也不证明已经发生的文件、进程或远端副作用被回滚。",
            "",
        ]
    )
    return "\n".join(lines)


def generated_artifacts(
    root: Path,
    *,
    allow_bootstrap_constants: bool = False,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    inputs = load_inputs(root)
    rules_document, by_identity = validate_rules(
        root,
        inputs,
        allow_bootstrap_constants=allow_bootstrap_constants,
    )
    rules_data = (root / RULES_PATH).read_bytes()
    projection = build_projection(inputs, by_identity)
    projection_data = b"".join(canonical_json(row) + b"\n" for row in projection)
    summary = build_summary(rules_document, rules_data, projection, projection_data)
    counts = summary["classification"]
    by_stream = summary["classificationByStream"]
    if not allow_bootstrap_constants:
        if counts != EXPECTED_OWNER_COUNTS:
            fail(f"owner classification counts changed: {counts}")
        if by_stream != EXPECTED_STREAM_OWNER_COUNTS:
            fail(f"stream/owner classification counts changed: {by_stream}")
    index_data = build_index(rules_document, summary, projection).encode()
    summary["artifacts"][INDEX_PATH] = {
        "size": len(index_data),
        "sha256": sha256_bytes(index_data),
    }
    summary_data = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    return {
        PROJECTION_PATH: projection_data,
        SUMMARY_PATH: summary_data,
        INDEX_PATH: index_data,
    }, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--bootstrap-rules", action="store_true")
    parser.add_argument("--bootstrap-artifacts", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    try:
        if args.bootstrap_rules:
            rules = bootstrap_rules(load_inputs(root))
            data = json.dumps(rules, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
            atomic_write(root / RULES_PATH, data)
            print(
                json.dumps(
                    {
                        "rules": len(rules["rules"]),
                        "mappedCallsites": sum(rule["expectedCount"] for rule in rules["rules"]),
                        "sha256": sha256_bytes(data),
                    },
                    sort_keys=True,
                )
            )
            return 0
        artifacts, summary = generated_artifacts(
            root,
            allow_bootstrap_constants=args.bootstrap_artifacts,
        )
        if args.check:
            stale = [relative for relative, data in artifacts.items() if not (root / relative).is_file() or (root / relative).read_bytes() != data]
            if stale:
                fail(f"generated owner projection artifacts are stale: {stale}")
            print(
                "PASS: exact Error/Diagnostic owner projection is current "
                + json.dumps(
                    {
                        "version": EXPECTED_VERSION,
                        "total": summary["totalCallsites"],
                        "classification": summary["classification"],
                        "rules": summary["reviewedRuleCount"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        for relative, data in artifacts.items():
            atomic_write(root / relative, data)
            print(f"WROTE: {relative}")
        print(json.dumps(summary["classification"], sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error/diagnostic owner projection failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
