#!/usr/bin/env python3
"""Validate the exact-binary project purge/import lifecycle probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_RELATIVE = "analysis/runtime-probes/project-data-lifecycle.json"
NEGATIVE_TEST_RELATIVE = (
    "skill/claude-code-version-diff/scripts/test_project_data_lifecycle_validator.py"
)
OWNED_TARGETS = ["projects", "tasks", "debug", "file-history", "history.jsonl"]
EXCLUDED_FIXTURES = ["shell-snapshots/keep.txt", "backups/keep.txt"]
STARTUP_CHANGES = [
    {"path": ".claude.json", "change": "added"},
    {"path": "backups/$AUTO_BACKUP", "change": "added"},
]
TOP_LEVEL_FIELDS = (
    "schemaVersion",
    "capturedAt",
    "environment",
    "target",
    "commandSemantics",
    "commands",
    "executionContracts",
    "input",
    "literalOutput",
    "exitStatus",
    "beforeAfter",
    "observed",
    "reproducibilityContract",
    "checks",
    "pass",
)
EXPECTED_CHECKS = (
    "snapshotMetadataVersionExact",
    "snapshotMetadataSha256Exact",
    "exactVersion",
    "exactBinarySha256",
    "everyExecutionContractComplete",
    "everyCommandIsFullEnvironmentRendering",
    "everyScenarioHasDistinctHome",
    "everyScenarioHasDistinctConfig",
    "purgeDryRunExitZero",
    "purgeDryRunPrintsPlan",
    "purgeDryRunParsesEveryOwnedTarget",
    "purgeDryRunListsFiveOwnedItems",
    "purgeDryRunReportsParsedCount",
    "purgeDryRunPreservesAllBytes",
    "purgeDryRunHasNoDomainDelta",
    "purgeDryRunExcludesShellSnapshots",
    "purgeDryRunExcludesBackups",
    "purgeDryRunClassifiesStartupFiles",
    "purgePositiveExitZero",
    "purgePositiveParsesEveryOwnedTarget",
    "purgePositiveReportsDerivedCount",
    "purgePositiveDeletesEveryOwnedTarget",
    "purgePositiveLeavesNoOwnedRows",
    "purgePositivePreservesExcludedFixtureMetadataAndBytes",
    "purgePositivePreservesShellSnapshotContent",
    "purgePositivePreservesBackupContent",
    "purgePositiveWarnsAboutBothExcludedRoots",
    "purgePositiveClassifiesStartupFiles",
    "jsonDryRunExitZero",
    "jsonDryRunReportsExpectedCounts",
    "jsonDryRunDoesNotWrite",
    "jsonDryRunHasNoObservedDelta",
    "jsonImportExitZero",
    "jsonImportReportsExpectedCounts",
    "jsonImportWritesOneTranscript",
    "jsonImportPreservesExactUuidParentChain",
    "jsonImportPreservesMessageChain",
    "jsonImportTranscriptMode0600",
    "jsonImportTranscriptHasCanonicalContentHash",
    "jsonImportTranscriptCanonicalBytesAndHashExact",
    "jsonImportTranscriptPathsAreCanonicalized",
    "jsonImportProjectInstructionsExact",
    "jsonImportReservedClaudeDocExact",
    "jsonImportWritesProjectInstructions",
    "jsonImportDemotesClaudeMd",
    "jsonImportWritesOnlyExpectedTargetArtifacts",
    "zipMismatchExitOne",
    "zipMismatchReportsExpectedCounts",
    "zipMismatchReportsMessageDiff",
    "zipMismatchReportsDocDiff",
    "zipMismatchReportsTerminalCode",
    "zipMismatchKeepsTranscript",
    "zipMismatchPreservesExactUuidParentChain",
    "zipMismatchPreservesMessageChain",
    "zipMismatchTranscriptMode0600",
    "zipMismatchTranscriptHasCanonicalContentHash",
    "zipMismatchTranscriptCanonicalBytesAndHashExact",
    "zipMismatchTranscriptPathsAreCanonicalized",
    "zipMismatchProjectInstructionsExact",
    "zipMismatchKeepsReservedClaudeDocExact",
    "zipMismatchKeepsReservedAgentsFileExact",
    "zipMismatchKeepsReservedDoc",
    "zipMismatchKeepsReservedProjectFile",
    "zipMismatchWritesOnlyExpectedTargetArtifacts",
    "zipMismatchWritesSurviveExitOne",
    "configImportGateExitOne",
    "configImportGateMessageExact",
    "configImportGateWritesNothing",
    "configImportAvailabilityDerivedFromRun",
)

SCENARIOS = {
    "version": {
        "argv": ["--version"],
        "prefix": "VERSION",
        "import": "",
    },
    "purgeDryRun": {
        "argv": ["project", "purge", "--all", "--dry-run"],
        "prefix": "PURGE_DRY",
        "import": "",
    },
    "purgePositive": {
        "argv": ["project", "purge", "--all", "-y"],
        "prefix": "PURGE_POSITIVE",
        "import": "",
    },
    "jsonDryRun": {
        "argv": [
            "import-conversations",
            "$JSON_ARCHIVE",
            "--cwd",
            "$JSON_DRY_TARGET",
            "--dry-run",
        ],
        "prefix": "JSON_DRY",
        "import": "1",
    },
    "jsonImport": {
        "argv": ["import-conversations", "$JSON_ARCHIVE", "--cwd", "$JSON_TARGET"],
        "prefix": "JSON",
        "import": "1",
    },
    "zipManifestMismatch": {
        "argv": ["import-conversations", "$ZIP_ARCHIVE", "--cwd", "$ZIP_TARGET"],
        "prefix": "ZIP",
        "import": "1",
    },
    "configImportBoundary": {
        "argv": ["import", "codex", "--dry-run"],
        "prefix": "CONFIG_IMPORT",
        "import": "",
    },
}

LITERAL_OUTPUT_SHA256 = {
    "version": {
        "stdout": "a40d2dec5365169c556f232c84d8edae51e1637039c4fd4f984ba782e4d82827",
        "stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
    "purgeDryRun": {
        "stdout": "fcdad2c147f7deb1b48d593dc0ccfc93579059e0ae16d5ce0aebabb1deaf285b",
        "stderr": "661d0f91d41a0705704405c0a08a7c104cbd8dc18a461a9079a5d6bb102d3afa",
    },
    "purgePositive": {
        "stdout": "087a94ea4067720ce0a2bff07660163cb1af23876cf0e690c5dc65c2e65a4479",
        "stderr": "31d52fb386429c73a1eb5a9074af2af81d0efa77b18bea2399c3568ea54f80b4",
    },
    "jsonDryRun": {
        "stdout": "3b866279db616d9aa108b71239cab8d5761955edcca0cacd995607ab90388695",
        "stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
    "jsonImport": {
        "stdout": "25fdb29e75b9a1d8ddfaf17dcdf7308555851651288295259c3ebe319b45b8ab",
        "stderr": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
    "zipManifestMismatch": {
        "stdout": "4942431fd36ba914175a1218ef31c486e0e0ed9a0549afd890d9bf713019ab47",
        "stderr": "76a69f4825d64b04a899642232aefce657786e04ef2e2c9ce6efc5ac8b0b9f67",
    },
    "configImportBoundary": {
        "stdout": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "stderr": "a88bdb9d86701a0073db1aa88bd99bbee3a319b7dd008c542c4809d71e4ced0f",
    },
}

TRANSCRIPTS = {
    "jsonImport": {
        "config": "$JSON_CONFIG",
        "session": "5cbc017d-7c10-53ae-8c44-3eb1b9a5ce89",
        "rawBytes": 1427,
        "canonicalBytes": 1216,
        "canonicalSha256": "bbf01984050eecc6f52f0c4ead7b1f7758a7406b7f13ca7cd381c1a7f7aac6b0",
        "uuids": [
            "50000000-0000-4000-8000-000000000005",
            "70000000-0000-4000-8000-000000000007",
        ],
        "texts": ["JSON_IMPORT_HUMAN_MARKER", "JSON_IMPORT_ASSISTANT_MARKER"],
        "conversationUuid": "30000000-0000-4000-8000-000000000003",
        "conversationName": "JSON_IMPORT conversation",
        "manifestMessageCount": 2,
        "manifestDocCount": 1,
        "projectUuid": "10000000-0000-4000-8000-000000000001",
        "projectName": "JSON Import Project",
        "projectDir": "json-import-project-10000000-0000-4000-8000-000000000001",
        "instructions": "JSON_IMPORT_PROJECT_INSTRUCTIONS",
        "claudeDoc": "JSON_IMPORT_RESERVED_DOC_MARKER",
    },
    "zipManifestMismatch": {
        "config": "$ZIP_CONFIG",
        "session": "a2b47e45-0eba-5b1c-aec1-a7ffb525080d",
        "rawBytes": 1447,
        "canonicalBytes": 1216,
        "canonicalSha256": "4d37df6304dce933a30a4550aa142ad16152c4fef5fe092c849713f7cb1836db",
        "uuids": [
            "60000000-0000-4000-8000-000000000006",
            "80000000-0000-4000-8000-000000000008",
        ],
        "texts": ["ZIP_MISMATCH_HUMAN_MARKER", "ZIP_MISMATCH_ASSISTANT_MARKER"],
        "conversationUuid": "40000000-0000-4000-8000-000000000004",
        "conversationName": "ZIP_MISMATCH conversation",
        "manifestMessageCount": 3,
        "manifestDocCount": 2,
        "projectUuid": "20000000-0000-4000-8000-000000000002",
        "projectName": "ZIP Mismatch Project",
        "projectDir": "zip-mismatch-project-20000000-0000-4000-8000-000000000002",
        "instructions": "ZIP_MISMATCH_PROJECT_INSTRUCTIONS",
        "claudeDoc": "ZIP_MISMATCH_RESERVED_DOC_MARKER",
        "agentsDoc": "ZIP_MISMATCH_PROJECT_FILE_MARKER\n",
    },
}


def _sha256_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _expect(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(f"project data lifecycle {message}")


def _shell_quote(value: str) -> str:
    if value == "":
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_./:$-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _render_command(contract: dict[str, Any]) -> str:
    environment = contract.get("environment", {})
    rendered_environment = " ".join(
        f"{key}={_shell_quote(environment[key])}" for key in sorted(environment)
    )
    return " ".join(
        [
            "env -i",
            rendered_environment,
            _shell_quote(contract.get("executable", "")),
            *[_shell_quote(value) for value in contract.get("argv", [])],
        ]
    )


def _expected_environment(prefix: str, import_conversations: str) -> dict[str, str]:
    home = f"${prefix}_HOME"
    config = f"${prefix}_CONFIG"
    return {
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_AUTH_TOKEN": "",
        "CI": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_OAUTH_TOKEN": "",
        "CLAUDE_CODE_SESSION_ACCESS_TOKEN": "",
        "CLAUDE_CONFIG_DIR": config,
        "CLAUDE_IMPORT_CONVERSATIONS": import_conversations,
        "CLAUDE_SECURESTORAGE_CONFIG_DIR": f"{config}/secure-storage",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_GROWTHBOOK": "1",
        "DISABLE_TELEMETRY": "1",
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": home,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "NO_COLOR": "1",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "SHELL": "/bin/zsh",
        "SSH_ASKPASS": "/usr/bin/false",
        "TERM": "dumb",
        "TMPDIR": f"${prefix}_TMPDIR",
        "USERPROFILE": home,
        "XDG_CONFIG_HOME": f"{home}/.config",
    }


def _fixture_inventory(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    directories = set(fixture.get("directories", []))
    files = fixture.get("files", {})
    for file_path in files:
        parent = Path(file_path).parent
        while str(parent) not in ("", "."):
            directories.add(parent.as_posix())
            parent = parent.parent
    rows: list[dict[str, Any]] = [
        {"path": path, "kind": "directory", "mode": "700"} for path in directories
    ]
    rows.extend(
        {
            "path": path,
            "kind": "file",
            "mode": "600",
            "bytes": len(content.encode("utf-8")),
            "sha256": _sha256_bytes(content),
        }
        for path, content in files.items()
    )
    return sorted(rows, key=lambda row: row["path"])


def _rows_under(rows: list[dict[str, Any]], roots: list[str]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if any(
            row.get("path") == root or row.get("path", "").startswith(root + "/")
            for root in roots
        )
    ]


def _artifact_row(path: str, content: str) -> dict[str, Any]:
    return {
        "path": path,
        "kind": "file",
        "mode": "600",
        "bytes": len(content.encode("utf-8")),
        "sha256": _sha256_bytes(content),
    }


def _observed_artifact(path: str, content: str) -> dict[str, Any]:
    content_bytes = len(content.encode("utf-8"))
    content_sha256 = _sha256_bytes(content)
    return {
        "path": path,
        "exists": True,
        "mode": "600",
        "bytes": content_bytes,
        "contentSha256": content_sha256,
        "expectedBytes": content_bytes,
        "expectedContentSha256": content_sha256,
        "contentMatchesExpected": True,
    }


def _validate_execution_contracts(report: dict[str, Any], failures: list[str]) -> None:
    contracts = report.get("executionContracts")
    commands = report.get("commands")
    _expect(failures, isinstance(contracts, dict), "executionContracts are missing")
    _expect(failures, isinstance(commands, dict), "commands are missing")
    if not isinstance(contracts, dict) or not isinstance(commands, dict):
        return
    _expect(
        failures,
        set(contracts) == set(SCENARIOS),
        "execution contract scenario set mismatch",
    )
    _expect(failures, set(commands) == set(SCENARIOS), "command scenario set mismatch")
    for scenario, spec in SCENARIOS.items():
        contract = contracts.get(scenario)
        if not isinstance(contract, dict):
            failures.append(
                f"project data lifecycle execution contract is missing: {scenario}"
            )
            continue
        expected_environment = _expected_environment(spec["prefix"], spec["import"])
        expected_contract = {
            "executable": "$CLAUDE_TARGET",
            "argv": spec["argv"],
            "cwd": f"${spec['prefix']}_WORKSPACE",
            "stdin": "ignored",
            "environmentMode": "replace",
            "environment": expected_environment,
        }
        _expect(
            failures,
            contract == expected_contract,
            f"execution contract mismatch: {scenario}",
        )
        _expect(
            failures,
            commands.get(scenario) == _render_command(expected_contract),
            f"full environment command rendering mismatch: {scenario}",
        )


def _validate_purge(report: dict[str, Any], failures: list[str]) -> None:
    inputs = report.get("input", {})
    before_after = report.get("beforeAfter", {})
    observed = report.get("observed", {})
    outputs = report.get("literalOutput", {})
    statuses = report.get("exitStatus", {})
    expected_plan_paths = OWNED_TARGETS

    for scenario in ("purgeDryRun", "purgePositive"):
        fixture = inputs.get(scenario)
        _expect(
            failures, isinstance(fixture, dict), f"{scenario} input fixture is missing"
        )
        if not isinstance(fixture, dict):
            continue
        _expect(
            failures,
            fixture.get("ownedTargets") == OWNED_TARGETS,
            f"{scenario} owned target fixture mismatch",
        )
        _expect(
            failures,
            fixture.get("excludedFixtures") == EXCLUDED_FIXTURES,
            f"{scenario} excluded fixture mismatch",
        )
        marker = "PURGE_DRY" if scenario == "purgeDryRun" else "PURGE_POSITIVE"
        expected_directories = [
            "projects",
            "tasks",
            "debug",
            "file-history",
            "shell-snapshots",
            "backups",
        ]
        expected_files = {
            "projects/project-marker/session.jsonl": f"{marker}_TRANSCRIPT_MARKER\n",
            "tasks/task-marker/task.json": f"{marker}_TASK_MARKER\n",
            "debug/debug-marker.txt": f"{marker}_DEBUG_MARKER\n",
            "file-history/history-marker/snapshot": f"{marker}_FILE_HISTORY_MARKER\n",
            "history.jsonl": f'{{"project":"/synthetic/project","display":"{marker}_PROMPT_MARKER"}}\n',
            "shell-snapshots/keep.txt": f"{marker}_SHELL_SNAPSHOT_KEEP_MARKER\n",
            "backups/keep.txt": f"{marker}_BACKUP_KEEP_MARKER\n",
        }
        _expect(
            failures,
            fixture.get("directories") == expected_directories,
            f"{scenario} directory fixture mismatch",
        )
        _expect(
            failures,
            fixture.get("files") == expected_files,
            f"{scenario} file fixture mismatch",
        )
        expected_before = _fixture_inventory(fixture)
        state = before_after.get(scenario, {})
        _expect(
            failures,
            state.get("domainBefore") == expected_before,
            f"{scenario} domainBefore inventory mismatch",
        )
        _expect(
            failures,
            state.get("startupChangesOutsidePlan") == STARTUP_CHANGES,
            f"{scenario} startup boundary mismatch",
        )
        _expect(
            failures,
            observed.get(f"{scenario}StartupChanges") == STARTUP_CHANGES,
            f"{scenario} observed startup boundary mismatch",
        )
        plan_prefix = (
            "$PURGE_DRY_CONFIG"
            if scenario == "purgeDryRun"
            else "$PURGE_POSITIVE_CONFIG"
        )
        expected_plan = [
            {
                "kind": "file" if target == "history.jsonl" else "dir",
                "path": f"{plan_prefix}/{target}",
                "ownedTarget": target,
            }
            for target in expected_plan_paths
        ]
        plan = observed.get(f"{scenario}Plan")
        _expect(
            failures,
            plan == expected_plan,
            f"{scenario} plan does not cover the five owned targets in order",
        )
        _expect(
            failures,
            observed.get(f"{scenario}PlannedItems") == 5,
            f"{scenario} planned item count is not 5",
        )
        _expect(
            failures, statuses.get(scenario) == 0, f"{scenario} exit status is not 0"
        )
        stdout = outputs.get(scenario, {}).get("stdout", "")
        stderr = outputs.get(scenario, {}).get("stderr", "")
        for target in expected_plan_paths:
            _expect(
                failures,
                f"/{target}" in stdout,
                f"{scenario} literal plan omits {target}",
            )
        _expect(
            failures,
            "shell-snapshots/ are not project-scoped" in stderr,
            f"{scenario} omits shell-snapshots exclusion warning",
        )
        _expect(
            failures,
            "backups/ may still contain project entries" in stderr,
            f"{scenario} omits backups exclusion warning",
        )

    dry_state = before_after.get("purgeDryRun", {})
    _expect(
        failures,
        dry_state.get("domainAfter") == dry_state.get("domainBefore"),
        "purge dry-run changed its owned data domain",
    )
    _expect(
        failures,
        observed.get("purgeDryRunChanges") == [],
        "purge dry-run reports a domain delta",
    )
    _expect(
        failures,
        observed.get("purgeDryRunChangedEntries") == 0,
        "purge dry-run changed-entry count is not zero",
    )
    _expect(
        failures,
        "Dry run: 5 item(s) would be deleted."
        in outputs.get("purgeDryRun", {}).get("stdout", ""),
        "purge dry-run literal count is missing",
    )

    positive_fixture = inputs.get("purgePositive", {})
    positive_before = (
        _fixture_inventory(positive_fixture)
        if isinstance(positive_fixture, dict)
        else []
    )
    expected_owned = _rows_under(positive_before, OWNED_TARGETS)
    positive_by_path = {row["path"]: row for row in positive_before}
    expected_excluded = [positive_by_path[path] for path in EXCLUDED_FIXTURES]
    expected_after = _rows_under(positive_before, ["backups", "shell-snapshots"])
    positive_state = before_after.get("purgePositive", {})
    _expect(
        failures,
        positive_state.get("ownedBefore") == expected_owned,
        "positive purge ownedBefore inventory mismatch",
    )
    _expect(
        failures,
        positive_state.get("ownedAfter") == [],
        "positive purge left owned rows behind",
    )
    _expect(
        failures,
        positive_state.get("domainAfter") == expected_after,
        "positive purge domainAfter inventory mismatch",
    )
    _expect(
        failures,
        positive_state.get("excludedFixturesBefore") == expected_excluded,
        "positive purge excluded before-state mismatch",
    )
    _expect(
        failures,
        positive_state.get("excludedFixturesAfter") == expected_excluded,
        "positive purge did not preserve excluded fixture metadata and bytes",
    )
    _expect(
        failures,
        observed.get("purgePositiveDeletedTargets") == OWNED_TARGETS,
        "positive purge deleted-target evidence mismatch",
    )
    _expect(
        failures,
        observed.get("purgePositiveDeletedTargetCount") == 5,
        "positive purge deleted-target count is not 5",
    )
    _expect(
        failures,
        observed.get("purgePositiveExcludedFixturesPreserved") == EXCLUDED_FIXTURES,
        "positive purge excluded preservation evidence mismatch",
    )
    _expect(
        failures,
        "Purged 5 item(s) across all projects."
        in outputs.get("purgePositive", {}).get("stdout", ""),
        "positive purge literal count is missing",
    )


def _input_messages(report: dict[str, Any], scenario: str) -> list[dict[str, Any]]:
    archive_name = "jsonArchive" if scenario == "jsonImport" else "zipArchive"
    conversations = (
        report.get("input", {}).get(archive_name, {}).get("conversations", [])
    )
    if len(conversations) != 1 or not isinstance(conversations[0], dict):
        return []
    return conversations[0].get("chat_messages", [])


def _validate_import_scenario(
    report: dict[str, Any], scenario: str, failures: list[str]
) -> None:
    spec = TRANSCRIPTS[scenario]
    observed_prefix = "zipMismatch" if scenario == "zipManifestMismatch" else scenario
    observed = report.get("observed", {})
    before_after = report.get("beforeAfter", {})
    transcript = observed.get(f"{observed_prefix}Transcript")
    _expect(
        failures,
        isinstance(transcript, dict),
        f"{scenario} transcript evidence is missing",
    )
    if not isinstance(transcript, dict):
        return
    expected_records = [
        {
            "type": "user",
            "uuid": spec["uuids"][0],
            "parentUuid": None,
            "role": "user",
            "text": spec["texts"][0],
            "version": "claude-export-import",
        },
        {
            "type": "assistant",
            "uuid": spec["uuids"][1],
            "parentUuid": spec["uuids"][0],
            "role": "assistant",
            "text": spec["texts"][1],
            "version": "claude-export-import",
        },
    ]
    expected_path = f"{spec['config']}/projects/$PROJECT_KEY/{spec['session']}.jsonl"
    _expect(
        failures,
        transcript.get("path") == expected_path,
        f"{scenario} transcript path is not canonical",
    )
    _expect(
        failures,
        transcript.get("mode") == "600",
        f"{scenario} transcript mode is not 0600",
    )
    _expect(
        failures,
        transcript.get("bytes") == spec["rawBytes"],
        f"{scenario} transcript raw byte count mismatch",
    )
    _expect(
        failures,
        transcript.get("canonicalBytes") == spec["canonicalBytes"],
        f"{scenario} canonical transcript byte count mismatch",
    )
    _expect(
        failures,
        transcript.get("canonicalContentSha256") == spec["canonicalSha256"],
        f"{scenario} canonical transcript hash mismatch",
    )
    _expect(
        failures,
        transcript.get("hashBasis")
        == "UTF-8 transcript after normalization of probe cwd, config, HOME and temporary-root paths",
        f"{scenario} canonical transcript hash basis mismatch",
    )
    _expect(
        failures,
        transcript.get("records") == expected_records,
        f"{scenario} UUID/parent/message chain mismatch",
    )

    input_messages = _input_messages(report, scenario)
    _expect(
        failures, len(input_messages) == 2, f"{scenario} input message count is not 2"
    )
    if len(input_messages) == 2:
        expected_input_chain = [
            (spec["uuids"][0], None, "human", spec["texts"][0]),
            (spec["uuids"][1], spec["uuids"][0], "assistant", spec["texts"][1]),
        ]
        actual_input_chain = [
            (
                message.get("uuid"),
                message.get("parent_message_uuid"),
                message.get("sender"),
                message.get("text"),
            )
            for message in input_messages
        ]
        _expect(
            failures,
            actual_input_chain == expected_input_chain,
            f"{scenario} input UUID/parent/message fixture mismatch",
        )

    archive_name = "jsonArchive" if scenario == "jsonImport" else "zipArchive"
    archive = report.get("input", {}).get(archive_name, {})
    manifest = archive.get("manifest", {})
    expected_manifest = {
        "account_uuid": "00000000-0000-4000-8000-000000000000",
        "conversations": [
            {
                "uuid": spec["conversationUuid"],
                "message_count": spec["manifestMessageCount"],
            }
        ],
        "projects": [
            {
                "uuid": spec["projectUuid"],
                "doc_count": spec["manifestDocCount"],
            }
        ],
    }
    _expect(
        failures, manifest == expected_manifest, f"{scenario} manifest fixture mismatch"
    )
    expected_project_files = (
        [
            {
                "file_uuid": "90000000-0000-4000-8000-000000000009",
                "file_name": "AGENTS.md",
            }
        ]
        if scenario == "zipManifestMismatch"
        else []
    )
    expected_archive_files = (
        {"90000000-0000-4000-8000-000000000009": spec["agentsDoc"]}
        if scenario == "zipManifestMismatch"
        else {}
    )
    expected_input_messages = [
        {
            "uuid": spec["uuids"][0],
            "parent_message_uuid": None,
            "sender": "human",
            "text": spec["texts"][0],
            "content": [{"type": "text", "text": spec["texts"][0]}],
            "created_at": "2026-01-02T03:04:05.000Z",
            "attachments": [],
            "files": [],
        },
        {
            "uuid": spec["uuids"][1],
            "parent_message_uuid": spec["uuids"][0],
            "sender": "assistant",
            "text": spec["texts"][1],
            "content": [{"type": "text", "text": spec["texts"][1]}],
            "created_at": "2026-01-02T03:05:06.000Z",
            "attachments": [],
            "files": [],
        },
    ]
    expected_archive = {
        "manifest": expected_manifest,
        "conversations": [
            {
                "uuid": spec["conversationUuid"],
                "name": spec["conversationName"],
                "created_at": "2026-01-02T03:04:05.000Z",
                "updated_at": "2026-01-02T03:05:06.000Z",
                "project_uuid": spec["projectUuid"],
                "chat_messages": expected_input_messages,
            }
        ],
        "projects": [
            {
                "uuid": spec["projectUuid"],
                "name": spec["projectName"],
                "prompt_template": spec["instructions"],
                "docs": [{"filename": "CLAUDE.md", "content": spec["claudeDoc"]}],
                "files": expected_project_files,
            }
        ],
        "files": expected_archive_files,
    }
    _expect(
        failures,
        archive == expected_archive,
        f"{scenario} complete archive input fixture mismatch",
    )

    state = before_after.get(scenario, {})
    _expect(
        failures,
        state.get("before") == {"transcript": [], "target": []},
        f"{scenario} before-state is not empty",
    )
    expected_transcript_rows = [
        {"path": "$PROJECT_KEY", "kind": "directory", "mode": "700"},
        {
            "path": f"$PROJECT_KEY/{spec['session']}.jsonl",
            "kind": "file",
            "mode": "600",
            "bytes": spec["rawBytes"],
            "contentSha256": spec["canonicalSha256"],
            "hashBasis": "normalized transcript bytes",
        },
    ]
    _expect(
        failures,
        state.get("after", {}).get("transcript") == expected_transcript_rows,
        f"{scenario} transcript before/after evidence mismatch",
    )

    project_root = f"projects/{spec['projectDir']}"
    expected_target = [
        {"path": "files", "kind": "directory", "mode": "700"},
        {"path": "projects", "kind": "directory", "mode": "700"},
        {"path": project_root, "kind": "directory", "mode": "700"},
    ]
    if scenario == "zipManifestMismatch":
        expected_target.append(
            _artifact_row(f"{project_root}/imported-AGENTS.md", spec["agentsDoc"])
        )
    expected_target.extend(
        [
            _artifact_row(f"{project_root}/imported-CLAUDE.md", spec["claudeDoc"]),
            _artifact_row(
                f"{project_root}/project-instructions.md", spec["instructions"]
            ),
        ]
    )
    expected_target.sort(key=lambda row: row["path"])
    _expect(
        failures,
        state.get("after", {}).get("target") == expected_target,
        f"{scenario} target artifact before/after evidence mismatch",
    )

    expected_observed_artifacts = {
        "projectInstructions": _observed_artifact(
            f"{project_root}/project-instructions.md", spec["instructions"]
        ),
        "reservedClaudeDoc": _observed_artifact(
            f"{project_root}/imported-CLAUDE.md", spec["claudeDoc"]
        ),
    }
    if scenario == "zipManifestMismatch":
        expected_observed_artifacts["reservedAgentsFile"] = _observed_artifact(
            f"{project_root}/imported-AGENTS.md", spec["agentsDoc"]
        )
    _expect(
        failures,
        observed.get(f"{observed_prefix}Artifacts") == expected_observed_artifacts,
        f"{scenario} observed artifact content/mode evidence mismatch",
    )


def _validate_imports(report: dict[str, Any], failures: list[str]) -> None:
    statuses = report.get("exitStatus", {})
    outputs = report.get("literalOutput", {})
    before_after = report.get("beforeAfter", {})
    observed = report.get("observed", {})

    dry = before_after.get("jsonDryRun", {})
    _expect(
        failures, statuses.get("jsonDryRun") == 0, "JSON dry-run exit status is not 0"
    )
    _expect(
        failures,
        dry.get("before") == {"transcript": [], "target": []},
        "JSON dry-run before-state is not empty",
    )
    _expect(
        failures,
        dry.get("after") == dry.get("before"),
        "JSON dry-run wrote transcript or project artifacts",
    )
    _expect(
        failures,
        observed.get("jsonDryRunChanges") == [],
        "JSON dry-run observed a write delta",
    )
    _expect(
        failures,
        observed.get("jsonDryRunChangedEntries") == 0,
        "JSON dry-run changed-entry count is not zero",
    )
    _expect(
        failures,
        "[dry-run] imported: conversations=1 skipped=0 messages=2 projects=1 docs=1 files=0"
        in outputs.get("jsonDryRun", {}).get("stdout", ""),
        "JSON dry-run literal import counts mismatch",
    )

    _validate_import_scenario(report, "jsonImport", failures)
    _expect(
        failures, statuses.get("jsonImport") == 0, "JSON import exit status is not 0"
    )
    _expect(
        failures,
        observed.get("jsonImportTranscriptCount") == 1,
        "JSON import transcript count is not 1",
    )
    _expect(
        failures,
        "imported: conversations=1 skipped=0 messages=2 projects=1 docs=1 files=0"
        in outputs.get("jsonImport", {}).get("stdout", ""),
        "JSON import literal counts mismatch",
    )

    _validate_import_scenario(report, "zipManifestMismatch", failures)
    _expect(
        failures,
        statuses.get("zipManifestMismatch") == 1,
        "manifest mismatch exit status is not 1",
    )
    _expect(
        failures,
        observed.get("zipMismatchTranscriptCount") == 1,
        "manifest mismatch transcript count is not 1",
    )
    _expect(
        failures,
        observed.get("zipMismatchWritesSurvivedExitOne") is True,
        "manifest mismatch exit 1 did not retain writes",
    )
    mismatch_stderr = outputs.get("zipManifestMismatch", {}).get("stderr", "")
    for marker in (
        "messages: manifest=3 imported=2",
        "docs: manifest=2 imported=1",
        "IMPORT_MANIFEST_MISMATCH",
    ):
        _expect(
            failures,
            marker in mismatch_stderr,
            f"manifest mismatch output omits {marker}",
        )
    _expect(
        failures,
        "imported: conversations=1 skipped=0 messages=2 projects=1 docs=1 files=1"
        in outputs.get("zipManifestMismatch", {}).get("stdout", ""),
        "manifest mismatch literal counts mismatch",
    )

    zip_archive = report.get("input", {}).get("zipArchive", {})
    manifest = zip_archive.get("manifest", {})
    conversations = zip_archive.get("conversations", [])
    projects = zip_archive.get("projects", [])
    _expect(
        failures,
        manifest.get("conversations", [{}])[0].get("message_count") == 3,
        "manifest mismatch fixture does not claim 3 messages",
    )
    _expect(
        failures,
        len(conversations) == 1 and len(conversations[0].get("chat_messages", [])) == 2,
        "manifest mismatch fixture does not contain 2 imported messages",
    )
    _expect(
        failures,
        manifest.get("projects", [{}])[0].get("doc_count") == 2,
        "manifest mismatch fixture does not claim 2 docs",
    )
    _expect(
        failures,
        len(projects) == 1 and len(projects[0].get("docs", [])) == 1,
        "manifest mismatch fixture does not contain 1 imported doc",
    )

    gate = before_after.get("configImportBoundary", {})
    config_content = (
        '[mcp_servers.local]\ncommand = "printf"\nargs = ["CONFIG_IMPORT_MARKER"]\n'
    )
    expected_config_input = {
        "source": "codex",
        "dryRun": True,
        "codexConfigToml": config_content,
        "gate": "tengu_import uses its built-in false value because server evaluation is disabled and local overrides are unreachable in 2.1.235",
    }
    _expect(
        failures,
        report.get("input", {}).get("configImportBoundary") == expected_config_input,
        "config import input fixture mismatch",
    )
    expected_config_state = {
        "claudeConfig": [],
        "codexConfig": [_artifact_row("config.toml", config_content)],
    }
    _expect(
        failures,
        gate.get("before") == expected_config_state,
        "config import before-state mismatch",
    )
    _expect(
        failures,
        statuses.get("configImportBoundary") == 1,
        "config import gate exit status is not 1",
    )
    _expect(
        failures,
        gate.get("after") == gate.get("before"),
        "config import gate wrote data",
    )
    _expect(
        failures,
        observed.get("configImportFeatureAvailableOffline") is False,
        "config import offline availability boundary mismatch",
    )
    expected_gate = "`claude import` is not yet available in this build. Run `claude` and use /mcp or edit ~/.claude/settings.json directly."
    _expect(
        failures,
        outputs.get("configImportBoundary", {}).get("stderr") == expected_gate,
        "config import gate message mismatch",
    )


def validate_project_data_lifecycle_document(
    report: Any,
    expected_version: str,
    expected_binary_sha256: str,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(report, dict):
        return ["project data lifecycle probe report root is not an object"]

    _expect(
        failures,
        tuple(report) == TOP_LEVEL_FIELDS,
        "probe top-level field contract mismatch",
    )
    _expect(
        failures,
        set(report.get("literalOutput", {})) == set(SCENARIOS),
        "literal output scenario set mismatch",
    )
    _expect(
        failures,
        set(report.get("exitStatus", {})) == set(SCENARIOS),
        "exit-status scenario set mismatch",
    )
    _expect(
        failures,
        tuple(report.get("input", {}))
        == (
            "purgeDryRun",
            "purgePositive",
            "jsonArchive",
            "zipArchive",
            "configImportBoundary",
        ),
        "input fixture scenario set mismatch",
    )
    _expect(
        failures,
        tuple(report.get("beforeAfter", {}))
        == (
            "purgeDryRun",
            "purgePositive",
            "jsonDryRun",
            "jsonImport",
            "zipManifestMismatch",
            "configImportBoundary",
        ),
        "before/after scenario set mismatch",
    )
    _expect(
        failures,
        tuple(report.get("observed", {}))
        == (
            "purgeDryRunPlan",
            "purgeDryRunPlannedItems",
            "purgeDryRunChanges",
            "purgeDryRunChangedEntries",
            "purgeDryRunStartupChanges",
            "purgePositivePlan",
            "purgePositivePlannedItems",
            "purgePositiveDeletedTargets",
            "purgePositiveDeletedTargetCount",
            "purgePositiveExcludedFixturesPreserved",
            "purgePositiveStartupChanges",
            "jsonDryRunChanges",
            "jsonDryRunChangedEntries",
            "jsonImportTranscriptCount",
            "jsonImportTranscript",
            "jsonImportArtifacts",
            "zipMismatchTranscriptCount",
            "zipMismatchTranscript",
            "zipMismatchArtifacts",
            "zipMismatchWritesSurvivedExitOne",
            "configImportFeatureAvailableOffline",
        ),
        "observed evidence field contract mismatch",
    )
    _expect(
        failures, report.get("schemaVersion") == 2, "probe schemaVersion must equal 2"
    )
    captured_at = report.get("capturedAt")
    try:
        parsed_captured_at = datetime.fromisoformat(
            str(captured_at).replace("Z", "+00:00")
        )
        captured_at_valid = parsed_captured_at.tzinfo is not None
    except ValueError:
        captured_at_valid = False
    _expect(failures, captured_at_valid, "probe capturedAt is invalid")

    target = report.get("target")
    _expect(failures, isinstance(target, dict), "probe target is missing")
    if isinstance(target, dict):
        _expect(
            failures,
            target.get("version") == expected_version,
            "probe target version differs from VERSION",
        )
        _expect(
            failures,
            target.get("requiredVersion") == expected_version,
            "probe requiredVersion differs from VERSION",
        )
        _expect(
            failures,
            target.get("binarySha256") == expected_binary_sha256,
            "probe target binary hash differs from analysis/version.json",
        )
        _expect(
            failures,
            target.get("requiredBinarySha256") == expected_binary_sha256,
            "probe required binary hash differs from analysis/version.json",
        )

    checks = report.get("checks")
    _expect(failures, isinstance(checks, dict), "probe checks are missing")
    if isinstance(checks, dict):
        _expect(
            failures,
            tuple(checks) == EXPECTED_CHECKS,
            "probe check set/order is not the fixed 69-check contract",
        )
        for name in EXPECTED_CHECKS:
            if checks.get(name) is not True:
                failures.append(
                    f"project data lifecycle required probe check failed: {name}"
                )
        extras = sorted(set(checks) - set(EXPECTED_CHECKS))
        _expect(
            failures, not extras, f"probe has unexpected checks: {', '.join(extras)}"
        )
    _expect(failures, report.get("pass") is True, "probe report did not pass")

    environment = report.get("environment", {})
    _expect(
        failures,
        environment.get("platform") == "darwin",
        "probe platform is not darwin",
    )
    _expect(
        failures, environment.get("arch") == "arm64", "probe architecture is not arm64"
    )
    _expect(
        failures,
        environment.get("nodeVersion") == "v22.21.1",
        "probe nodeVersion mismatch",
    )
    _expect(
        failures,
        environment.get("zipExecutable") == "/usr/bin/zip",
        "probe zip executable mismatch",
    )
    _expect(
        failures,
        report.get("commandSemantics")
        == "commands is a shell reproduction rendering; executionContracts is the authoritative normalized spawn argv, cwd and replacement environment contract",
        "command semantics contract mismatch",
    )
    _expect(
        failures,
        report.get("reproducibilityContract")
        == {
            "canonicalization": "delete capturedAt, then compare the complete parsed JSON value byte-for-byte after deterministic JSON serialization",
            "transcriptHashBasis": "normalize all scenario cwd, config, target, HOME, TMPDIR, fixture and probe-root paths before SHA-256",
        },
        "reproducibility contract mismatch",
    )
    _expect(
        failures,
        report.get("exitStatus", {}).get("version") == 0,
        "version command exit status is not 0",
    )
    _expect(
        failures,
        report.get("literalOutput", {}).get("version")
        == {"stdout": f"{expected_version} (Claude Code)", "stderr": ""},
        "version literal output mismatch",
    )
    literal_outputs = report.get("literalOutput", {})
    for scenario, expected_hashes in LITERAL_OUTPUT_SHA256.items():
        scenario_output = literal_outputs.get(scenario, {})
        _expect(
            failures,
            set(scenario_output) == {"stdout", "stderr"}
            and all(isinstance(value, str) for value in scenario_output.values()),
            f"{scenario} literal output stream contract mismatch",
        )
        for stream, expected_hash in expected_hashes.items():
            actual = scenario_output.get(stream)
            _expect(
                failures,
                isinstance(actual, str) and _sha256_bytes(actual) == expected_hash,
                f"{scenario} {stream} literal output hash mismatch",
            )

    _validate_execution_contracts(report, failures)
    _validate_purge(report, failures)
    _validate_imports(report, failures)
    return failures


def validate_project_data_lifecycle_report(
    repo: Path,
    version: str,
    metadata: dict[str, Any],
    failures: list[str],
) -> int:
    if not (repo / NEGATIVE_TEST_RELATIVE).is_file():
        failures.append("missing project data lifecycle validator forgery test")
    report_path = repo / REPORT_RELATIVE
    if not report_path.is_file():
        failures.append("project data lifecycle probe report is missing")
        return 0
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"project data lifecycle probe report is invalid: {error}")
        return 0
    expected_sha = metadata.get("binary", {}).get("sha256", "")
    failures.extend(
        validate_project_data_lifecycle_document(report, version, expected_sha)
    )
    checks = report.get("checks")
    return len(checks) if isinstance(checks, dict) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    metadata = json.loads((repo / "analysis/version.json").read_text(encoding="utf-8"))
    report_path = args.report.resolve() if args.report else repo / REPORT_RELATIVE
    if not report_path.is_file():
        print("project data lifecycle validation: FAIL")
        print("- project data lifecycle probe report is missing")
        return 1
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print("project data lifecycle validation: FAIL")
        print(f"- project data lifecycle probe report is invalid: {error}")
        return 1
    failures = validate_project_data_lifecycle_document(
        report,
        version,
        metadata.get("binary", {}).get("sha256", ""),
    )
    if failures:
        print("project data lifecycle validation: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("project data lifecycle validation: PASS")
    print(f"version: {version}")
    print(f"binary sha256: {metadata['binary']['sha256']}")
    print(f"checks validated: {len(EXPECTED_CHECKS)}")
    print(f"execution contracts validated: {len(SCENARIOS)}")
    print("purge owned targets validated: 5")
    print("import transcript chains validated: 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
