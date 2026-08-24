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
from typing import Any, Iterable, NamedTuple, Sequence


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
EXPECTED_READABLE_SHA256 = "99c8608118d643802dbca7bf86b031bb3f565fb78bad093494a841de3e6783b4"
EXPECTED_READABLE_SIZE = 34_418_467
EXPECTED_READABLE_LINES = 638_178

class CallerOwnerMapping(NamedTuple):
    mapping_id: str
    rule_id: str
    event: str
    readable_line: int
    function: str
    consumer: str
    comparison_key: str
    evidence_fingerprint: str
    owner: str
    topic: str
    scenario: str
    navigation_start: int
    navigation_end: int


class CallerOwnerSemantics(NamedTuple):
    state_change: str
    boundary: str


# Owner labels are admitted one caller at a time. The navigation range only tells
# a reviewer where to read surrounding code; it is never part of the match.
CALLER_OWNER_ALLOWLIST = (
    CallerOwnerMapping("reactive-compact-succeeded", "limits-teleport-compact", "tengu_reactive_compact_succeeded", 232_876, "named:Smi", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:efe72721146a01b53303:1", "ed0e3fc8361b6e11", "model-request", "limits, teleport and compact", "request watchdog, quota, teleport and reactive compact", 232_819, 232_876),
    CallerOwnerMapping("transcript-write-failed", "transcript-storage", "tengu_transcript_write_failed", 400_287, "named:VBt", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:17dcb89a5d0c4c678677:1", "12f0d75e82351f99", "workspace-state", "transcript storage", "transcript writes, compaction and graph repair", 400_287, 400_292),
    CallerOwnerMapping("post-tool-hook-error", "tool-hooks-and-subagents", "tengu_post_tool_hook_error", 292_451, "named:Tcr", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:9105077132739d67e8e2:1", "437e45b5ec5debcb", "tool-runtime", "tool hooks and subagents", "subagent execution, tool hooks and MCP tool calls", 292_451, 292_451),
    CallerOwnerMapping("review-remote-precondition-01", "remote-review", "tengu_review_remote_precondition_failed", 363_040, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:77f7dc32276c3b3f875a:1", "4bcd7bc9ec6b5a3f", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-02", "remote-review", "tengu_review_remote_precondition_failed", 363_048, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:3334a2f1d5c60e09efc0:1", "dab82b5e72ab975e", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-03", "remote-review", "tengu_review_remote_precondition_failed", 363_052, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:77f7dc32276c3b3f875a:2", "d1ec8824e31cf1d7", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-04", "remote-review", "tengu_review_remote_precondition_failed", 363_053, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:77f7dc32276c3b3f875a:3", "fac1e91436f5617e", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-05", "remote-review", "tengu_review_remote_precondition_failed", 363_058, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe77f89981a097154130:1", "02c4583d6ac5fb43", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-06", "remote-review", "tengu_review_remote_precondition_failed", 363_064, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:70765335f41f6085292d:1", "a8215d19cd6dba34", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-07", "remote-review", "tengu_review_remote_precondition_failed", 363_068, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:9ce132afd38a2de77563:1", "89567f42b4e29344", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-08", "remote-review", "tengu_review_remote_precondition_failed", 363_077, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:087d1e4a1583760734b9:1", "a23dc3ce0df11070", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-09", "remote-review", "tengu_review_remote_precondition_failed", 363_080, "named:v1i", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:087d1e4a1583760734b9:2", "2e8cd5f0a2f5fb56", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-10", "remote-review", "tengu_review_remote_precondition_failed", 363_100, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:77f7dc32276c3b3f875a:4", "f702b685d4248d36", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-11", "remote-review", "tengu_review_remote_precondition_failed", 363_103, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:e89d37bfed2506422351:1", "3cb7ac8f86efd78c", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-12", "remote-review", "tengu_review_remote_precondition_failed", 363_111, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:e1f096346c8efc4369bf:1", "e424ecc4f312a3d4", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-13", "remote-review", "tengu_review_remote_precondition_failed", 363_119, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:7d358430ca3e11061685:1", "4771f494ba97995d", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-14", "remote-review", "tengu_review_remote_precondition_failed", 363_123, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:0c05c311849e1a19b527:1", "01ad925d46649881", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-15", "remote-review", "tengu_review_remote_precondition_failed", 363_131, "named:v1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe77f89981a097154130:2", "9e412a005b1d8bec", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-16", "remote-review", "tengu_review_remote_precondition_failed", 363_198, "named:w1i", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:afb0620a24652829ac87:1", "2f19c0f9fd246b2d", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("review-remote-precondition-17", "remote-review", "tengu_review_remote_precondition_failed", 363_218, "named:w1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:77f7dc32276c3b3f875a:5", "e416e9357e321e15", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 363_040, 363_218),
    CallerOwnerMapping("fast-mode-identity", "identity-and-model-access", "tengu_fast_mode_toggled", 69_298, "named:GW", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:84d18855ecc4c75fe60c:1", "f86f1d5f8048b76f", "identity-account", "identity, limits and model access", "credential locks, account limits and fast mode", 69_298, 69_298),
    CallerOwnerMapping("fast-mode-remote-review", "remote-review", "tengu_fast_mode_toggled", 364_739, "named:$1i", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:84d18855ecc4c75fe60c:2", "e49adb6d17c58782", "workflow-product", "remote review and Ultraplan", "remote review gates, recovery and Ultraplan", 364_739, 364_739),
    CallerOwnerMapping("fast-mode-usage-picker", "usage-and-credits", "tengu_fast_mode_toggled", 487_764, "named:des", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:84d18855ecc4c75fe60c:3", "f84c72f348ead43c", "identity-account", "usage and credits", "usage-credit approval, extra usage and fast-mode selection", 487_764, 487_764),
    CallerOwnerMapping("fast-mode-message-ui", "input-and-refusal-ui", "tengu_fast_mode_toggled", 524_166, "named:onMessage", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:84d18855ecc4c75fe60c:4", "8669fea1e83d5530", "terminal-host", "input and refusal UI", "hotkeys, paste, mode cycling and refusal retraction", 524_166, 524_166),
    CallerOwnerMapping("copper-lantern", "daemon-service-recall", "tengu_copper_lantern", 632_061, "named:Ehy", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:deaf317c346f375f3cd9:1", "a575093a2f5cb62f", "remote-runtime", "daemon supervisor", "service recall, worker drain and supervisor shutdown", 632_000, 632_084),
    CallerOwnerMapping("github-app-step-01", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_752, "named:z1w", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:1", "c787d2e4f0d8d30d", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-02", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_772, "named:J1w", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:2", "695eede1f623e0ee", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-03", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_821, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:3", "bca052604411955e", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-04", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_857, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:4", "cb740b8cb1782023", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-05", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_858, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:5", "8c95a8ce845a7b50", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-06", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_864, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:6", "e2b3607dae16b352", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-07", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_879, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:7", "f0cb1646e9786baf", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-08", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_880, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:8", "09099d283aa83afb", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-09", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_881, "named:nHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:9", "1b4fcf57756d58bf", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-10", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_906, "named:pHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:10", "700a7f07734b2b3b", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-11", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_911, "named:fHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:11", "2a7135446633f63e", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-12", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_944, "named:wHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:88a6d75cae3dfd5dc4a3:1", "d2f74b907185fca0", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-13", "github-app-install-wizard", "tengu_install_github_app_step_completed", 490_955, "named:CHw", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:12", "48732f718d0ba540", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-app-step-14", "github-app-install-wizard", "tengu_install_github_app_step_completed", 491_054, "named:iv", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:fe028b39df055326e598:13", "ebda12e3e2fc56f8", "workflow-product", "GitHub App and Actions setup", "install wizard validation, repository selection, credentials and workflow setup", 490_640, 491_065),
    CallerOwnerMapping("github-actions-failed-01", "github-actions-setup", "tengu_setup_github_actions_failed", 490_533, "named:I1w", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:5e4d7b6c1aeafa3ec001:1", "ad57dc7cc37b177f", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-02", "github-actions-setup", "tengu_setup_github_actions_failed", 490_534, "named:I1w", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:5e4d7b6c1aeafa3ec001:2", "307872d6d38bf420", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-03", "github-actions-setup", "tengu_setup_github_actions_failed", 490_548, "named:moc", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:97d6823b47c031eb4244:1", "bfbdb255a5223a54", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-04", "github-actions-setup", "tengu_setup_github_actions_failed", 490_550, "named:moc", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:97d6823b47c031eb4244:2", "31a04760af3c0c53", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-05", "github-actions-setup", "tengu_setup_github_actions_failed", 490_552, "named:moc", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:97d6823b47c031eb4244:3", "ca9247a9815c8b01", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-06", "github-actions-setup", "tengu_setup_github_actions_failed", 490_557, "named:moc", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:97d6823b47c031eb4244:4", "3760ce6766dc745f", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-07", "github-actions-setup", "tengu_setup_github_actions_failed", 490_567, "named:moc", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:97d6823b47c031eb4244:5", "b983d26e97b329af", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("github-actions-failed-08", "github-actions-setup", "tengu_setup_github_actions_failed", 490_585, "named:moc", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:6f92a876503946181b32:1", "75934776b60cc1e1", "workflow-product", "GitHub App and Actions setup", "repository checks, branch and workflow creation, secret write and error propagation", 490_523, 490_588),
    CallerOwnerMapping("marketplace-autoinstall-01", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_888, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:be2be2dd83eee6ed1e1b:1", "9ff854b2c2860ef3", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-02", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_890, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:be2be2dd83eee6ed1e1b:2", "83fc8ab134541dce", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-03", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_896, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:5326bb8a2af85c59b487:1", "7b2cd7863a1aff56", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-04", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_900, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:4944ba300c5ac0cedc1b:1", "a75f44d2e748f7fc", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-05", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_905, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:a878f23544b050915e7e:1", "b18ff479be6303c9", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-06", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_909, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:773b54301da682aa10d6:1", "a7ae823b16390ac8", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-07", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_914, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:dca9c2396dfba04cf1bc:1", "0e1d3bae540741d0", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("marketplace-autoinstall-08", "official-marketplace-autoinstall", "tengu_official_marketplace_auto_install", 583_919, "named:z3g", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:6644c277f20abe4c55be:1", "5153da207c5d2471", "plugin-runtime", "plugin marketplace lifecycle", "policy gates, GCS or git install, retry scheduling and terminal outcome", 583_864, 583_920),
    CallerOwnerMapping("stage-file-01", "remote-stage-file", "tengu_stage_file_completed", 599_468, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:67e476324232924b8220:1", "63dbedacc0ac1779", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-02", "remote-stage-file", "tengu_stage_file_completed", 599_479, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:2dfe5deae56b79089d68:1", "a74e07db5afe6059", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-03", "remote-stage-file", "tengu_stage_file_completed", 599_489, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:7e5e3cd42ebaa97cb5e7:1", "c264867695d091a2", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-04", "remote-stage-file", "tengu_stage_file_completed", 599_490, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:26a32766eecfab82713f:1", "3ec4218c53ac0a97", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-05", "remote-stage-file", "tengu_stage_file_completed", 599_495, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:7e5e3cd42ebaa97cb5e7:2", "a161f7091ef4e090", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-06", "remote-stage-file", "tengu_stage_file_completed", 599_496, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:17095582c9b78f666694:1", "7894ac5b5c69eb2d", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-07", "remote-stage-file", "tengu_stage_file_completed", 599_503, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:f02f03adca5299a3bc3b:1", "b90c7c6f8b9713fc", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-08", "remote-stage-file", "tengu_stage_file_completed", 599_505, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:08fe93cabfc7f78ff108:1", "18bbd48156278b03", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("stage-file-09", "remote-stage-file", "tengu_stage_file_completed", 599_507, "named:vKE", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:08fe93cabfc7f78ff108:2", "a2eb6f808daa19d0", "remote-runtime", "remote staged files", "runner gate, existing-file no-op, fetch, atomic publish and terminal result", 599_443, 599_508),
    CallerOwnerMapping("file-history-rewind-failed-01", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_746, "anonymous:<anonymous>", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:1", "2071d66a3476fad0", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-02", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_752, "anonymous:<anonymous>", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:2", "f732b548809adc05", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-03", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_766, "named:uiS", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:3", "b798ca4d3e932154", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-04", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_771, "named:uiS", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:4", "62c15cef498ad10d", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-05", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_780, "named:uiS", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:5", "f71f69462bf2a0c4", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-06", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_788, "named:uiS", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:6", "45df7fcd624829a1", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-07", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_802, "named:uiS", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:7", "495e515430dc10f1", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-08", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_973, "named:o", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:8", "73ca0a2db63caa97", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("file-history-rewind-failed-09", "file-history-rewind", "tengu_file_history_rewind_restore_file_failed", 194_977, "named:yiS", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:c4dfcbff0b40b3f9859d:9", "cbb0da335c3d9985", "workspace-state", "file history and rewind", "dry-run diff failure, restore refusal, path identity guard and missing backup", 194_721, 195_057),
    CallerOwnerMapping("transcript-compact-failed-01", "transcript-file-compaction", "tengu_transcript_compact_failed", 401_362, "named:performCompactTranscript", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:22ed3192e2bcce7d7f40:1", "cb5cd5aaecf08771", "workspace-state", "transcript storage", "file and V5 transcript compaction validation, source race and I/O abort", 401_330, 401_500),
    CallerOwnerMapping("transcript-compact-failed-02", "transcript-file-compaction", "tengu_transcript_compact_failed", 401_369, "named:performCompactTranscript", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:22ed3192e2bcce7d7f40:2", "97f0e934b5a93c03", "workspace-state", "transcript storage", "file and V5 transcript compaction validation, source race and I/O abort", 401_330, 401_500),
    CallerOwnerMapping("transcript-compact-failed-03", "transcript-file-compaction", "tengu_transcript_compact_failed", 401_385, "named:performCompactTranscript", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:22ed3192e2bcce7d7f40:3", "0854318d84a65772", "workspace-state", "transcript storage", "file and V5 transcript compaction validation, source race and I/O abort", 401_330, 401_500),
    CallerOwnerMapping("transcript-compact-failed-04", "transcript-file-compaction", "tengu_transcript_compact_failed", 401_404, "named:performCompactTranscript", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:22ed3192e2bcce7d7f40:4", "fe95f2292eaeedda", "workspace-state", "transcript storage", "file and V5 transcript compaction validation, source race and I/O abort", 401_330, 401_500),
    CallerOwnerMapping("transcript-compact-failed-05", "transcript-file-compaction", "tengu_transcript_compact_failed", 401_417, "named:performCompactTranscript", "SequenceExpression/expressions/other", "firstPartyEvent+firstPartyEventAsync:22ed3192e2bcce7d7f40:5", "282fc20b4aa18dde", "workspace-state", "transcript storage", "file and V5 transcript compaction validation, source race and I/O abort", 401_330, 401_500),
    CallerOwnerMapping("transcript-compact-failed-06", "transcript-file-compaction", "tengu_transcript_compact_failed", 401_425, "named:n", "ExpressionStatement/expression/other", "firstPartyEvent+firstPartyEventAsync:22ed3192e2bcce7d7f40:6", "018f87d97b41c90c", "workspace-state", "transcript storage", "file and V5 transcript compaction validation, source race and I/O abort", 401_330, 401_500),
)

CALLER_OWNER_RULE_SEMANTICS = {
    "limits-teleport-compact": CallerOwnerSemantics(
        "request watchdog 将 reactive compact 记为成功，request loop 因而可以带着压实后的会话状态继续。",
        "静态 caller 不证明用户会话实际触发了 compact、删掉多少上下文，或后续请求成功。",
    ),
    "transcript-storage": CallerOwnerSemantics(
        "transcript writer 进入写失败分支；本次记录没有获得 durable 确认，连续性仍交给后续 graph repair 或 recovery。",
        "caller 只证明本地失败处理，不证明运行时文件错误、实际保留字节、后续恢复结果或遥测送达。",
    ),
    "tool-hooks-and-subagents": CallerOwnerSemantics(
        "post-tool hook 路径在 tool/subagent 执行后记录错误，并把控制权交回外层 tool runtime。",
        "映射不证明具体执行了哪个 hook、工具副作用是否已经完成，或后续 hook/model turn 是否恢复。",
    ),
    "remote-review": CallerOwnerSemantics(
        "remote-review workflow 拒绝或恢复 launch precondition，或在推进本地 gate/launch 状态时记录 fast-mode 选择。",
        "静态 caller 不证明 remote session 已创建、quota 已接受、cloud review 已执行、findings 已送达或 PR comment 已完成。",
    ),
    "identity-and-model-access": CallerOwnerSemantics(
        "identity/model-access surface 在应用本地 access 与 account-limit 检查后记录所选 fast-mode 状态。",
        "映射不证明当前 entitlement、服务端 policy、模型可用性、实际 request routing 或遥测送达。",
    ),
    "usage-and-credits": CallerOwnerSemantics(
        "usage picker 把 fast-mode 选择与本地 usage-credit approval 状态一起记录。",
        "映射不证明 billing 已接受、账号余额、后续请求模式或服务端实际扣费。",
    ),
    "input-and-refusal-ui": CallerOwnerSemantics(
        "message UI 应用并记录由输入处理触发的 fast-mode toggle。",
        "映射不证明下一次模型请求使用该模式、服务端接受该模式，或事件离开本地队列。",
    ),
    "daemon-service-recall": CallerOwnerSemantics(
        "daemon supervisor 进入 service recall，开始 drain workers、卸载 service，并转向 supervisor shutdown。",
        "exact caller 不证明每个 worker 都已干净退出、OS service 删除成功，或 exit event 到达 collector。",
    ),
    "github-app-install-wizard": CallerOwnerSemantics(
        "GitHub setup UI 推进一个具名 wizard milestone，更新 repository/credential/workflow 选择，或在 setup 返回后进入 success。",
        "这些静态 UI 转移不证明 browser authorization、GitHub App 安装、远端仓库写入、secret 持久化，或部分远端副作用已回滚。",
    ),
    "github-actions-setup": CallerOwnerSemantics(
        "GitHub Actions setup 在 repository、branch、workflow file 或 secret 操作后进入具名失败分支，并抛出或继续传播错误。",
        "更早的 GitHub 写入可能已经存在；caller 不证明网络操作实际结果、远端回滚、最终仓库状态或事件送达。",
    ),
    "official-marketplace-autoinstall": CallerOwnerSemantics(
        "plugin owner 在 auto-install 状态机中记录 policy skip、安装成功、可重试失败与 backoff，或 xcrun-shim 终态。",
        "xcrun-shim 分支只返回分类结果，没有同样的 retry 持久化更新；caller 不证明未来重试、marketplace 完整性、网络成功或遥测保留。",
    ),
    "remote-stage-file": CallerOwnerSemantics(
        "remote file stager 到达一个终态：unsupported runner、existing/read-only no-op、gated fetch、mkdir/write failure，或 atomic rename 成功发布到 stage root。",
        "映射不证明远端文件真实存在、字节符合服务端意图、后续 consumer 打开了 staged path，或事件已发送。",
    ),
    "file-history-rewind": CallerOwnerSemantics(
        "rewind owner 在 backup lookup、path type、link count、parent identity 或 file I/O guard 失败时丢弃 dry-run row，或拒绝/跳过 restore。",
        "同一轮 rewind 的其他文件可能已经恢复或删除；这些 caller 不证明事务级回滚、运行时文件系统最终状态或 recovery 完成。",
    ),
    "transcript-file-compaction": CallerOwnerSemantics(
        "file/V5 transcript compaction 在 torn tail、invalid plan、source race 或 I/O error 时放弃 publish；文件路径未发布 replacement 时还会尝试清理临时文件。",
        "映射不证明源 transcript 其余部分健康、没有 concurrent append、cleanup 成功，或后续 compaction 已恢复。",
    ),
}

EXPECTED_CALLER_OWNER_EVENTS = 911
EXPECTED_CALLER_OWNER_CALLSITES = 1_297
EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES = 79
EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256 = "43d545d8f0c85d69f5f1fefc0663e1153dece9e392b07520616107aa8d2f3aac"
EXPECTED_CALLER_OWNER_STATUS = {
    "Single-owner": 11,
    "Cross-owner": 1,
    "Partially resolved": 0,
    "Unresolved": 899,
}
EXPECTED_CALLER_OWNER_BUCKETS = {
    "Unresolved": (899, 1_218),
    "identity-account": (1, 2),
    "model-request": (1, 1),
    "plugin-runtime": (1, 8),
    "remote-runtime": (2, 10),
    "terminal-host": (1, 1),
    "tool-runtime": (1, 1),
    "workflow-product": (4, 40),
    "workspace-state": (3, 16),
}
CALLER_OWNER_REPRESENTATIVES = {
    "Unresolved": ("tengu_end_conversation_tool_call", "tengu_heap_dump", "tengu_update_refused"),
    "identity-account": ("tengu_fast_mode_toggled",),
    "model-request": ("tengu_reactive_compact_succeeded",),
    "plugin-runtime": ("tengu_official_marketplace_auto_install",),
    "remote-runtime": ("tengu_copper_lantern", "tengu_stage_file_completed"),
    "terminal-host": ("tengu_fast_mode_toggled",),
    "tool-runtime": ("tengu_post_tool_hook_error",),
    "workflow-product": (
        "tengu_review_remote_precondition_failed",
        "tengu_fast_mode_toggled",
        "tengu_install_github_app_step_completed",
        "tengu_setup_github_actions_failed",
    ),
    "workspace-state": (
        "tengu_transcript_write_failed",
        "tengu_file_history_rewind_restore_file_failed",
        "tengu_transcript_compact_failed",
    ),
}

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


def verify_readable_callsites(
    root: Path,
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[int, int], dict[str, Any]]:
    readable_path = root / "reverse/javascript/cli.readable.js"
    metadata_path = root / "reverse/javascript/metadata.json"
    require(readable_path.is_file(), "missing reverse/javascript/cli.readable.js")
    require(metadata_path.is_file(), "missing reverse/javascript/metadata.json")
    readable_data = readable_path.read_bytes()
    metadata_data = metadata_path.read_bytes()
    readable_hash = sha256_bytes(readable_data)
    # Use physical LF records. Python splitlines() also treats embedded Unicode
    # separators as line breaks, while esbuild/readable source locations do not.
    readable_lines = readable_data.decode("utf-8").split("\n")
    require(len(readable_data) == EXPECTED_READABLE_SIZE, "readable source size changed")
    physical_line_count = readable_data.count(b"\n")
    require(physical_line_count == EXPECTED_READABLE_LINES, "readable source line count changed")
    require(
        len(readable_lines) == EXPECTED_READABLE_LINES + 1 and readable_lines[-1] == "",
        "readable source must end with one physical newline",
    )
    require(readable_hash == EXPECTED_READABLE_SHA256, "readable source hash changed")
    metadata = json.loads(metadata_data.decode("utf-8"))
    require(metadata.get("path") == "reverse/javascript/cli.readable.js", "readable metadata path")
    require(metadata.get("size") == len(readable_data), "readable metadata size")
    require(metadata.get("lines") == len(readable_lines), "readable metadata lines")
    require(metadata.get("sha256") == readable_hash, "readable metadata hash")

    queues: dict[str, collections.deque[dict[str, Any]]] = collections.defaultdict(collections.deque)
    static_rows = []
    for row in sorted(rows, key=position_sort_key):
        event = row.get("nameArgument", {}).get("staticValue")
        if isinstance(event, str):
            queues[event].append(row)
            static_rows.append(row)

    pattern = re.compile(r"\b(?:H|Fv)\(\s*[\"'](tengu_[^\"']+)[\"']")
    readable_by_row: dict[int, int] = {}
    observed = collections.Counter()
    for line_number, line in enumerate(readable_lines, start=1):
        for match in pattern.finditer(line):
            event = match.group(1)
            require(queues[event], f"readable caller has no inventory row: {event}@L{line_number}")
            row = queues[event].popleft()
            readable_by_row[id(row)] = line_number
            observed[event] += 1
    leftovers = {
        event: len(queue)
        for event, queue in queues.items()
        if queue
    }
    require(not leftovers, f"inventory callsites missing from readable view: {leftovers}")
    require(len(readable_by_row) == len(static_rows) == 2_151, "readable static caller count")
    require(
        observed
        == collections.Counter(row["nameArgument"]["staticValue"] for row in static_rows),
        "readable event/callsite multiplicity differs from inventory",
    )
    return readable_by_row, {
        "path": "reverse/javascript/cli.readable.js",
        "lines": physical_line_count,
        "size": len(readable_data),
        "sha256": readable_hash,
        "metadataPath": "reverse/javascript/metadata.json",
        "metadataLines": line_count(metadata_data),
        "metadataSize": len(metadata_data),
        "metadataSha256": sha256_bytes(metadata_data),
    }


def caller_consumer_label(row: dict[str, Any]) -> str:
    consumer = row.get("consumer", {})
    return "/".join(
        str(consumer.get(key, ""))
        for key in ("parentType", "relation", "role", "target")
        if consumer.get(key) is not None
    )


def caller_owner_allowlist_sha256(
    mappings: Sequence[CallerOwnerMapping],
) -> str:
    rule_ids = sorted({mapping.rule_id for mapping in mappings})
    encoded = json.dumps(
        {
            "mappings": [mapping._asdict() for mapping in mappings],
            "ruleSemantics": {
                rule_id: (
                    CALLER_OWNER_RULE_SEMANTICS[rule_id]._asdict()
                    if rule_id in CALLER_OWNER_RULE_SEMANTICS
                    else None
                )
                for rule_id in rule_ids
            },
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256_bytes(encoded)


def caller_exact_identity(
    event: str,
    row: dict[str, Any],
    readable_line: int,
) -> tuple[str, int, str, str, str]:
    return (
        event,
        readable_line,
        function_label(row),
        caller_consumer_label(row),
        str(row.get("comparisonKey")),
    )


def caller_evidence_fingerprint(
    event: str,
    row: dict[str, Any],
    readable_line: int,
    rule_id: str | None,
) -> str:
    consumer = row.get("consumer", {})
    payload = row.get("payload", {})
    evidence = {
        "event": event,
        "function": row.get("function"),
        "functionKind": row.get("functionKind"),
        "consumer": {
            "parentType": consumer.get("parentType"),
            "relation": consumer.get("relation"),
            "role": consumer.get("role"),
            "target": consumer.get("target"),
        },
        "payload": {
            "objectStatus": payload.get("objectStatus"),
            "directKeys": payload.get("directKeys", []),
            "expandedKeys": payload.get("expandedKeys", []),
            "unresolvedSpreads": [source_text(item) for item in payload.get("unresolvedSpreads", [])],
        },
        "canonical": {
            "line": row.get("line"),
            "column": row.get("column"),
            "offset": row.get("offset"),
        },
        "readableLine": readable_line,
        "rule": rule_id,
    }
    encoded = json.dumps(evidence, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(encoded)[:16]


def validate_caller_owner_allowlist(
    grouped: dict[str, list[dict[str, Any]]],
    projections: dict[str, str],
    readable_by_row: dict[int, int],
) -> None:
    require(
        len(CALLER_OWNER_ALLOWLIST) == EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES,
        "caller-owner allowlist entry count",
    )
    require(
        caller_owner_allowlist_sha256(CALLER_OWNER_ALLOWLIST)
        == EXPECTED_CALLER_OWNER_ALLOWLIST_SHA256,
        "caller-owner exact allowlist digest changed",
    )
    rule_ids = {mapping.rule_id for mapping in CALLER_OWNER_ALLOWLIST}
    require(
        rule_ids == set(CALLER_OWNER_RULE_SEMANTICS),
        "caller-owner rule semantics coverage changed",
    )
    for rule_id, semantics in CALLER_OWNER_RULE_SEMANTICS.items():
        require(
            semantics.state_change and semantics.boundary,
            f"caller-owner rule semantics is incomplete: {rule_id}",
        )
    mapping_ids: set[str] = set()
    exact_identities: set[tuple[str, int, str, str, str]] = set()
    target_events = {
        event for event, family in projections.items() if family == "tengu_other"
    }
    for mapping in CALLER_OWNER_ALLOWLIST:
        require(mapping.mapping_id not in mapping_ids, f"duplicate caller-owner mapping {mapping.mapping_id}")
        mapping_ids.add(mapping.mapping_id)
        require(mapping.event in target_events, f"caller-owner mapping event is not tengu_other: {mapping.mapping_id}")
        require(mapping.owner and mapping.topic and mapping.scenario, f"caller-owner mapping has empty label: {mapping.mapping_id}")
        require(
            mapping.navigation_start <= mapping.readable_line <= mapping.navigation_end,
            f"caller-owner navigation range misses exact line: {mapping.mapping_id}",
        )
        exact_identity = (
            mapping.event,
            mapping.readable_line,
            mapping.function,
            mapping.consumer,
            mapping.comparison_key,
        )
        require(exact_identity not in exact_identities, f"duplicate caller-owner exact identity: {mapping.mapping_id}")
        exact_identities.add(exact_identity)
        matches = [
            row
            for row in grouped[mapping.event]
            if caller_exact_identity(
                mapping.event,
                row,
                readable_by_row[id(row)],
            )
            == exact_identity
        ]
        require(len(matches) == 1, f"caller-owner mapping does not select one exact callsite: {mapping.mapping_id}")
        actual_fingerprint = caller_evidence_fingerprint(
            mapping.event,
            matches[0],
            mapping.readable_line,
            mapping.rule_id,
        )
        require(
            actual_fingerprint == mapping.evidence_fingerprint,
            f"caller-owner exact mapping fingerprint mismatch: {mapping.mapping_id}",
        )


def caller_owner_mapping(
    event: str,
    row: dict[str, Any],
    readable_line: int,
) -> CallerOwnerMapping | None:
    exact_identity = caller_exact_identity(event, row, readable_line)
    candidates = [
        mapping
        for mapping in CALLER_OWNER_ALLOWLIST
        if (
            mapping.event,
            mapping.readable_line,
            mapping.function,
            mapping.consumer,
            mapping.comparison_key,
        )
        == exact_identity
    ]
    require(len(candidates) <= 1, f"multiple caller-owner mappings select {event}@L{readable_line}")
    if not candidates:
        return None
    mapping = candidates[0]
    require(
        caller_evidence_fingerprint(event, row, readable_line, mapping.rule_id)
        == mapping.evidence_fingerprint,
        f"caller-owner exact mapping fingerprint mismatch: {mapping.mapping_id}",
    )
    return mapping


def project_caller_owners(
    grouped: dict[str, list[dict[str, Any]]],
    projections: dict[str, str],
    readable_by_row: dict[int, int],
) -> dict[str, dict[str, Any]]:
    validate_caller_owner_allowlist(grouped, projections, readable_by_row)
    result: dict[str, dict[str, Any]] = {}
    target_events = sorted(event for event, family in projections.items() if family == "tengu_other")
    require(len(target_events) == EXPECTED_CALLER_OWNER_EVENTS, "caller-owner target event count")
    for event in target_events:
        callsites = []
        for row in sorted(grouped[event], key=position_sort_key):
            readable_line = readable_by_row[id(row)]
            mapping = caller_owner_mapping(event, row, readable_line)
            if mapping is None:
                mapping_id = None
                rule_id = None
                owner = "Unresolved"
                topic = "Unresolved"
                scenario = "No reviewed exact caller allowlist entry matches this callsite"
                state_change = "Unresolved: no exact caller rule establishes the observed local state transition"
                boundary = "No owner or runtime claim is admitted without an exact reviewed mapping"
                navigation_range = None
            else:
                mapping_id = mapping.mapping_id
                rule_id = mapping.rule_id
                owner = mapping.owner
                topic = mapping.topic
                scenario = mapping.scenario
                semantics = CALLER_OWNER_RULE_SEMANTICS[mapping.rule_id]
                state_change = semantics.state_change
                boundary = semantics.boundary
                navigation_range = [mapping.navigation_start, mapping.navigation_end]
            callsites.append(
                {
                    "owner": owner,
                    "topic": topic,
                    "scenario": scenario,
                    "stateChange": state_change,
                    "boundary": boundary,
                    "mappingId": mapping_id,
                    "ruleId": rule_id,
                    "navigationRange": navigation_range,
                    "readableLine": readable_line,
                    "function": function_label(row),
                    "consumer": caller_consumer_label(row),
                    "payloadStatus": row.get("payload", {}).get("objectStatus"),
                    "payloadKeys": row.get("payload", {}).get("expandedKeys", []),
                    "canonicalPosition": format_position(row),
                    "evidenceFingerprint": caller_evidence_fingerprint(
                        event, row, readable_line, rule_id
                    ),
                }
            )
        owners = sorted_unique(item["owner"] for item in callsites)
        topics = sorted_unique(item["topic"] for item in callsites)
        scenarios = sorted_unique(item["scenario"] for item in callsites)
        rules = sorted_unique(
            item["ruleId"] for item in callsites if item["ruleId"] is not None
        )
        state_changes = sorted_unique(item["stateChange"] for item in callsites)
        boundaries = sorted_unique(item["boundary"] for item in callsites)
        if owners == ["Unresolved"]:
            status = "Unresolved"
        elif "Unresolved" in owners:
            status = "Partially resolved"
        elif len(owners) > 1:
            status = "Cross-owner"
        else:
            status = "Single-owner"
        result[event] = {
            "status": status,
            "owners": owners,
            "topics": topics,
            "scenarios": scenarios,
            "rules": rules,
            "stateChanges": state_changes,
            "boundaries": boundaries,
            "callsites": callsites,
        }
    require(len(result) == EXPECTED_CALLER_OWNER_EVENTS, "caller-owner projection output count")
    status_counter = collections.Counter(item["status"] for item in result.values())
    status_counts = {
        status: status_counter[status]
        for status in EXPECTED_CALLER_OWNER_STATUS
    }
    require(
        dict(status_counts) == EXPECTED_CALLER_OWNER_STATUS,
        f"caller-owner status counts changed: {dict(status_counts)}",
    )
    require(
        sum(len(item["callsites"]) for item in result.values())
        == EXPECTED_CALLER_OWNER_CALLSITES,
        "caller-owner callsite count",
    )
    owner_events: dict[str, set[str]] = collections.defaultdict(set)
    owner_callsites: collections.Counter[str] = collections.Counter()
    for event, item in result.items():
        for callsite in item["callsites"]:
            owner_events[callsite["owner"]].add(event)
            owner_callsites[callsite["owner"]] += 1
    observed_buckets = {
        owner: (len(owner_events[owner]), owner_callsites[owner])
        for owner in sorted(owner_events)
    }
    require(
        observed_buckets == EXPECTED_CALLER_OWNER_BUCKETS,
        f"caller-owner bucket counts changed: {observed_buckets}",
    )
    require(
        set(CALLER_OWNER_REPRESENTATIVES) == set(EXPECTED_CALLER_OWNER_BUCKETS),
        "caller-owner representative bucket set",
    )
    for owner, events in CALLER_OWNER_REPRESENTATIVES.items():
        for event in events:
            require(event in result, f"caller-owner representative missing: {event}")
            require(
                owner in result[event]["owners"],
                f"caller-owner representative moved: {owner}/{event}",
            )
    return result


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
        f"family 层的 `tengu_other` 只表示事件名没有命中 release-local family 规则。它不是产品 owner、模块边界或服务端分类；后文 caller projection 只给 {EXPECTED_CALLER_OWNER_ALLOWLIST_ENTRIES} 个逐项复核的 exact callsite 归属，剩余 {EXPECTED_CALLER_OWNER_STATUS['Unresolved']} 个事件保持 `Unresolved`。像 `tengu_background` 这类 singleton label 仍只匹配同名事件，不会自动吞并所有同前缀名字。",
        "",
        "## 字段怎么读",
        "",
        "| 字段 | 证据等级 | 正确解释 |",
        "| --- | --- | --- |",
        "| event name | `Static` | AST 已把第一个参数解析成固定字符串；同名调用点可聚合 |",
        "| family projection | `Derived` | 复现 release-local extractor：eligible family prefixes 做最长匹配，singleton labels 只做 exact match；仅用于导航和跨版本统计 |",
        "| caller owner/topic/scenario | `Derived` from `Static` | 只有 event、readable line、function、consumer、comparison key 与证据指纹同时命中逐 caller allowlist 才投影本地状态 owner；导航区间不参与分类；不是原始源码模块名 |",
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
    grouped: dict[str, list[dict[str, Any]]],
    projections: dict[str, str],
    caller_projections: dict[str, dict[str, Any]],
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
    expected_callers = {
        "tengu_reactive_compact_succeeded": ["model-request"],
        "tengu_query_error": ["Unresolved"],
        "tengu_transcript_write_failed": ["workspace-state"],
    }
    for event, expected in expected_callers.items():
        require(
            caller_projections[event]["owners"] == expected,
            f"semantic index caller owner changed: {event}",
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
        "| Reactive compact | `tengu_reactive_compact_triggered` -> `...attempt`（1..N） -> `...succeeded` 或 `...failed` | compactor 拥有“总结前缀、保留合法后缀、恢复附件、写 boundary”的表示切换；它不回滚既有工具副作用 | `groupsToSummarize/groupsToPreserve/tokenGap` 描述每次选择；`attempts/preCompactTokens/postCompactTokens/preservedMessageCount/restoredAttachmentCount` 描述结果；`trigger/thresholdSource/precomputed` 解释入口 | family 仍是 `tengu_other`，caller projection 则落到 `model-request` / compact 场景；success 才证明 rebuilt context 已形成，failed 后旧历史仍是当前表示。见 [`/compact` 图文专题](compact-visual-guide.md)，源码 232819-232876、262267 |",
        "| Session 启动、恢复与持久化 | `tengu_session_start`；resume 分支产生 `tengu_session_resumed{success}`；远端/内部镜像失败另记 `tengu_session_persistence_failed` | session loader 拥有恢复视图，transcript/remote mirror 各自拥有持久化；启动成功和后续每次写入成功不是同一状态 | `previous_session_id/source/permissionMode` 描述启动来源；`entrypoint/success/failure_reason/resume_duration_ms` 描述恢复；persistence failure 当前无 payload，必须回源码/diagnostic 定位 owner | resumed success 不证明之后 transcript 永不丢写；persistence failure 也不等于当前模型回答失败。见 [Sessions/Checkpoint/Memory](sessions-checkpoints-memory.md)，源码 401679-401697、587827-594803、591606 |",
        "| MCP 认证与工具失败 | `tengu_mcp_server_needs_auth` -> `tengu_mcp_oauth_flow_start` -> `...success` / `...failure` / `...error`；调用期仍可出现 `tengu_mcp_tool_call_auth_error` | MCP connection/auth controller 拥有发现、OAuth 和 token；tool executor 只消费当时连接状态 | `transportType/cause` 说明在哪个发现阶段需要认证；`flowAttemptId/authMethod/http_status/error_code/reason` 关联 OAuth；`authErrorKind` 区分未连接和 token 过期 | OAuth success 只完成该 flow，不保证 tools/list 或下一次 tool call 成功；调用期 auth error 需要重新连接/授权。见 [MCP、Agents 与后台协作](mcp-agents-background.md)，源码 381285-381456、384086、385348 |",
        "| 后台任务派发 | `tengu_bg_dispatch`；失败前后可见 `...rejected`、`...fallback`、`...rescued`；最终工作结果另看 `tengu_bg_agent_terminal` | dispatcher/daemon 拥有进程与消息投递，agent registry 拥有最终 outcome；dispatch ACK 不是任务完成 | `source_* / via / has_worktree / has_agent` 解释入口；fallback 的 reason flags 解释 transport；rescued 表示 ACK 不确定但 worker 被 readback 找到；terminal 的 `outcome/durationMs` 才接近任务终态 | 只有 dispatch 没有 terminal 时查 daemon、roster、worker crash 或会话仍运行；rescued 不是重复启动证据。见 [Runtime Supervision](runtime-supervision-and-processes.md)，源码 270118、480234-480323、631031 |",
        "| CLI 登录 | `tengu_oauth_flow_start` -> `tengu_oauth_auth_code_received`（浏览器流） -> `tengu_oauth_token_exchange_success` -> `tengu_oauth_success` 或 `tengu_oauth_error` | login controller 拥有 UI/flow，token exchange/storage 和 profile/account check 是后续独立阶段 | `loginWithClaudeAi/automatic` 区分入口；`account_on_hold/ssl_error` 是特定失败分类；token-exchange success 不携带账号完整状态 | 不要把 token exchange success 当作最终登录；最终 success 之后仍可能有 profile、role 或持久化告警。见 [认证与账号生命周期](auth-account-and-subscription-lifecycle.md)，源码 78277、299879、441642-441703 |",
        "| 错误终态层级 | tool 层用 `tengu_tool_use_error`；Agent/query wrapper 用 `tengu_query_error`；未捕获进程错误用 `tengu_uncaught_exception` / `tengu_unhandled_rejection` | 不同 owner 决定错误能否作为 tool_result 回到模型、结束当前 query，或升级为进程级异常 | tool 的 `errorCode/toolName` 可操作；query error 只给 assistant/tool-use 数量和 chain 深度；uncaught/rejection 的 `error_name` 已经过错误封装，不能替代原始 stack | 同一次根因可能在多层留下记录，但不能把多条事件统计成多个独立故障。`tengu_query_error` 的 family 是 `tengu_other`，但本版尚无逐 caller 人工 allowlist，owner 保持 `Unresolved`。见 [错误与诊断图谱](error-diagnostic-atlas.md)，源码 272115、316183-316476、78172、111364-111403 |",
        "| Transcript 写入恢复 | `tengu_transcript_write_failed` -> 后续成功写同一路径时 `tengu_transcript_writer_recovered` | transcript writer 拥有本地落盘和 degraded latch；模型/API 请求可以已经成功，而持久化单独失败 | `errno_code/errno_enospc/errno_emfile/consecutive_failures/degraded/source` 用于判断磁盘、fd 和连续退化；recovered 只说明 writer 清除了对应 degraded state | family 仍是 `tengu_other`，caller projection 已解析为 `workspace-state` / transcript storage；recovered 不补证失败窗口内每条记录都已重放。见 [Sessions/Checkpoint/Memory](sessions-checkpoints-memory.md)，源码 400287-400292 |",
        "",
        "### 为什么 family `tengu_other` 不能再承担语义归属",
        "",
        "`tengu_other` 不能当作语义兜底或低价值垃圾桶；它只表示当前 family 前缀规则没有命中。独立 caller projection 已逐项复核 compact、transcript 写入/压实、tool hook、remote review、fast mode、daemon recall、GitHub setup、官方 Marketplace、remote stage file 与 File History rewind 等 exact caller；`tengu_query_error` 等未映射事件继续标成 `Unresolved`。排障先看 exact caller 证据，再用 family 做名字导航；family 和行区间都不能决定产品所有权。",
        "",
    ]


def render_coverage(
    first_party_rows: Sequence[dict[str, Any]],
    first_party_dynamic: Sequence[dict[str, Any]],
    otel_rows: Sequence[dict[str, Any]],
    caller_projections: dict[str, dict[str, Any]],
) -> list[str]:
    first_party_functions = len({str(row.get("function")) for row in first_party_rows})
    first_party_spreads = sum(
        len(row["payload"].get("unresolvedSpreads", [])) for row in first_party_rows
    )
    otel_functions = len({str(row.get("function")) for row in otel_rows})
    otel_spreads = sum(len(row["payload"].get("unresolvedSpreads", [])) for row in otel_rows)
    caller_status = collections.Counter(item["status"] for item in caller_projections.values())
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
        f"| family `tengu_other` caller projection | {len(caller_projections)} events / {sum(len(item['callsites']) for item in caller_projections.values())} callsites | {caller_status['Single-owner']} single-owner + {caller_status['Cross-owner']} cross-owner + {caller_status['Partially resolved']} partial + {caller_status['Unresolved']} unresolved |",
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


def render_caller_owner_projection(
    projection: dict[str, dict[str, Any]],
) -> list[str]:
    status_counts = collections.Counter(item["status"] for item in projection.values())
    callsite_count = sum(len(item["callsites"]) for item in projection.values())
    unresolved_events = sorted(
        event for event, item in projection.items() if item["status"] == "Unresolved"
    )
    partial_events = sorted(
        event for event, item in projection.items() if item["status"] == "Partially resolved"
    )
    cross_owner_events = sorted(
        event for event, item in projection.items() if item["status"] == "Cross-owner"
    )
    owner_events: dict[str, set[str]] = collections.defaultdict(set)
    owner_callsites: collections.Counter[str] = collections.Counter()
    owner_topics: dict[str, set[str]] = collections.defaultdict(set)
    owner_rules: dict[str, set[str]] = collections.defaultdict(set)
    for event, item in projection.items():
        for callsite in item["callsites"]:
            owner = callsite["owner"]
            owner_events[owner].add(event)
            owner_callsites[owner] += 1
            owner_topics[owner].add(callsite["topic"])
            if callsite["ruleId"] is not None:
                owner_rules[owner].add(callsite["ruleId"])

    lines = [
        "## `tengu_other` caller/owner 场景投影",
        "",
        "<!-- TELEMETRY_CALLER_OWNER_PROJECTION -->",
        f"<!-- caller-owner-target-events:{len(projection)} -->",
        f"<!-- caller-owner-target-callsites:{callsite_count} -->",
        f"<!-- caller-owner-single:{status_counts['Single-owner']} -->",
        f"<!-- caller-owner-cross:{status_counts['Cross-owner']} -->",
        f"<!-- caller-owner-partial:{status_counts['Partially resolved']} -->",
        f"<!-- caller-owner-unresolved:{status_counts['Unresolved']} -->",
        f"<!-- caller-owner-allowlist-entries:{len(CALLER_OWNER_ALLOWLIST)} -->",
        f"<!-- caller-owner-mapped-callsites:{callsite_count - owner_callsites['Unresolved']} -->",
        f"<!-- caller-owner-unresolved-callsites:{owner_callsites['Unresolved']} -->",
        "",
        f"family projection 有 911 个名字、1,297 个静态调用点落入 `tengu_other`。生成器先把它们与同哈希 readable view 逐个对齐，再只接受 {len(CALLER_OWNER_ALLOWLIST)} 条逐 caller 人工 allowlist：这些调用点完整覆盖 {status_counts['Single-owner'] + status_counts['Cross-owner']} 个事件，其余 {len(unresolved_events)} 个事件、{owner_callsites['Unresolved']:,} 个调用点保持 `Unresolved`。family 继续承担名字导航；caller projection 不会用邻近行替未审阅 caller 猜 owner。",
        "",
        "### 分类合同",
        "",
        "1. **输入不是事件名清单。** 每条 allowlist 同时固定 event name、readable line、词法 function、consumer parent/relation/role、inventory comparison key 和 16 位证据指纹；缺一项都不能命中。",
        "2. **owner 由 exact caller allowlist 决定。** readable range 只帮助人阅读附近代码，分类器完全不读取 range；扩大导航区间不会吸收同区间的其他 caller，事件前缀也不会自动成为 owner。",
        "3. **同名事件按全部调用点聚合。** 全部 caller 都有 exact mapping 且落在同一 owner 才是 `Single-owner`；跨 host/owner 的同名事件标成 `Cross-owner`；只有一部分 caller 命中时标成 `Partially resolved`；所有调用点都没有 exact mapping 才是 `Unresolved`。",
        f"4. **双重身份校验防止静默换义。** inventory comparison key 参与初筛；event/function/consumer/payload/canonical position/readable line/rule 生成的 16 位 SHA-256 前缀再做复核。整个 {len(CALLER_OWNER_ALLOWLIST)} 条 allowlist 连同 rule 的状态变化与 Boundary 另有完整 SHA-256，删除或篡改都会让生成失败。",
        "5. **这是客户端 Derived 投影。** 它说明 2.1.235 中 logger caller 的状态 owner，不证明分支实际执行、采样命中、网络送达、服务端保留，也不声称这些 owner 是 Anthropic 原始源码模块名。",
        "",
        "### 覆盖结果",
        "",
        "| Projection status | unique events | 正确读法 |",
        "| --- | ---: | --- |",
        f"| `Single-owner` | {status_counts['Single-owner']} | 全部静态调用点逐项命中 allowlist，且落在同一个 caller owner；topic/scenario 仍可有多个 |",
        f"| `Cross-owner` | {status_counts['Cross-owner']} | 同名事件由多个本地 owner/host 调用，不能强塞进单一模块 |",
        f"| `Partially resolved` | {status_counts['Partially resolved']} | 至少一个调用点命中 exact mapping，至少一个调用点没有 mapping |",
        f"| `Unresolved` | {status_counts['Unresolved']} | 所有调用点都没有经过逐项复核的 exact mapping |",
        f"| **Total** | **{len(projection)}** | 对应 family `tengu_other` 的全部 unique static events、共 {callsite_count} 个静态调用点 |",
        "",
        "### Caller owner buckets",
        "",
        "| Derived caller owner | member events | callsites | topics | rules | representative events |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for owner in sorted(owner_events):
        events = sorted(owner_events[owner])
        representatives = CALLER_OWNER_REPRESENTATIVES[owner]
        lines.append(
            f"| {code_span(owner)} | {len(events)} | {owner_callsites[owner]} | "
            f"{len(owner_topics[owner])} | {len(owner_rules[owner])} | "
            f"{table_cell(code_list(representatives))} |"
        )

    lines.extend(
        [
            "",
            "`Unresolved` bucket 是未完成人工归属的显式欠账，不是一个产品 owner。事件 membership 可以在 `Cross-owner` 情况下进入多个已解析 owner bucket，所以 owner 表的 member-event 列不能相加后当作 911；上面的 status 表才是互斥覆盖。callsites 按真实调用点计数。",
            "",
            "### 代表性因果链",
            "",
            "| event | status | caller owner | topic / scenario | 观测到的状态变化 | Boundary | caller evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    representative_events = (
        "tengu_reactive_compact_succeeded",
        "tengu_transcript_write_failed",
        "tengu_post_tool_hook_error",
        "tengu_review_remote_precondition_failed",
        "tengu_fast_mode_toggled",
        "tengu_copper_lantern",
        "tengu_install_github_app_step_completed",
        "tengu_setup_github_actions_failed",
        "tengu_official_marketplace_auto_install",
        "tengu_stage_file_completed",
        "tengu_file_history_rewind_restore_file_failed",
        "tengu_transcript_compact_failed",
    )
    for event in representative_events:
        require(event in projection, f"caller-owner representative missing: {event}")
        item = projection[event]
        evidence_items = [
            f"{callsite['function']} @ readable L{callsite['readableLine']} / "
            f"{callsite['consumer']} / {callsite['evidenceFingerprint']}"
            for callsite in item["callsites"]
        ]
        evidence = "; ".join(evidence_items[:3])
        if len(evidence_items) > 3:
            evidence += f"; +{len(evidence_items) - 3} more callsites in the exhaustive entry"
        lines.append(
            f"| {code_span(event)} | {code_span(item['status'])} | "
            f"{table_cell(code_list(item['owners']))} | "
            f"{table_cell(code_list(item['topics']))}<br>{table_cell(code_list(item['scenarios']))} | "
            f"{table_cell('<br>'.join(item['stateChanges']))} | "
            f"{table_cell('<br>'.join(item['boundaries']))} | "
            f"{table_cell(evidence)} |"
        )

    lines.extend(
        [
            "",
            "**不靠名字猜的代表：** `tengu_copper_lantern` 的名字和空 payload 都不提供产品语义；其唯一 caller 位于 daemon supervisor 的 service-recall 条件，紧邻 worker drain、service uninstall 和 `tengu_daemon_exit{cause=service_recall}`。因此 exact identity `event + L632061 + named:Ehy + ExpressionStatement/expression/other + comparison key + fingerprint` 才绑定到 `remote-runtime / daemon supervisor`；`L632000-L632084` 仅供阅读上下文。",
            "",
            "**不能强行单归属的代表：** `tengu_fast_mode_toggled` 有四个 caller，分别位于身份/模型访问、remote review、usage picker 和消息 UI。目录把它保留为 `Cross-owner`，说明同名事件可以是共享观测词，而不是共享状态 owner。",
            "",
            "### Cross-owner events",
            "",
            "这些同名事件的 caller 确实跨 owner；把它们按名字强制归入一个功能，会丢掉 host 或状态所有权差异。",
            "",
            "| event | owners | topics | rules | readable lines |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for event in cross_owner_events:
        item = projection[event]
        lines.append(
            f"| {code_span(event)} | {table_cell(code_list(item['owners']))} | "
            f"{table_cell(code_list(item['topics']))} | {table_cell(code_list(item['rules']))} | "
            f"{table_cell(code_list(callsite['readableLine'] for callsite in item['callsites']))} |"
        )

    unresolved_callsite_count = sum(
        len(projection[event]["callsites"])
        for event in unresolved_events + partial_events
    )
    counterexample_events = (
        "tengu_end_conversation_tool_call",
        "tengu_heap_dump",
        "tengu_update_refused",
    )
    lines.extend(
        [
            "",
            "### 真正未收口的调用点",
            "",
            f"当前明确欠账是 **{len(unresolved_events)} 个 Unresolved events / {unresolved_callsite_count:,} 个 callsites**。`Unresolved` 不是低价值事件，而是当前没有逐 caller 复核结果承担语义归属。即便调用点恰好落在某个已解释机制附近，也不会自动继承邻近 owner。",
            "",
            "**高频仍不等于可批量认领。** `tengu_feedback_survey_event` 的 13 个 caller 分布在多种 survey/feedback surface；`tengu_left_arrow_blocked` 的 10 个 caller 跨输入编辑、inflight guard 与不同 TUI 路径；`tengu_git_operation` 的 10 个 caller 同时观察 shell command 与 MCP tool name。`tengu_review_remote_precondition_recovery` 虽有 12 个 caller 邻近 remote-review gate，另一个 caller 位于独立入口；在完整 owner/continuation trace 完成前，它也不会继承 `remote-review` 的导航区间。",
            "",
            "下列三个反例原先会被宽行区间误归属；现在即使把 allowlist 的导航区间扩大到覆盖它们，event/function/consumer/comparison identity 不匹配，仍必须保持 `Unresolved`：",
            "",
            "| regression counterexample | callsites | functions | readable lines | result |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for event in counterexample_events:
        require(event in unresolved_events, f"caller-owner counterexample is no longer unresolved: {event}")
        item = projection[event]
        lines.append(
            f"| {code_span(event)} | {len(item['callsites'])} | "
            f"{table_cell(code_list(callsite['function'] for callsite in item['callsites']))} | "
            f"{table_cell(code_list(callsite['readableLine'] for callsite in item['callsites']))} | "
            "`Unresolved`; no exact mapping |"
        )
    lines.extend(
        [
            "",
            "<details>",
            f"<summary>完整 Unresolved caller 证据（{len(unresolved_events)} events / {unresolved_callsite_count:,} callsites）</summary>",
            "",
            "完整表保留 function、consumer、payload、canonical/readable 双位置和 fingerprint，作为后续逐 caller 人工收口的输入；默认折叠，避免机器清单打断正文。",
            "",
            "| event | status | functions | consumer contexts | payload keys | canonical / readable positions | evidence fingerprints |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for event in sorted(unresolved_events + partial_events):
        item = projection[event]
        callsites = item["callsites"]
        lines.append(
            f"| {code_span(event)} | {code_span(item['status'])} | "
            f"{table_cell(code_list(callsite['function'] for callsite in callsites))} | "
            f"{table_cell(code_list(callsite['consumer'] for callsite in callsites))} | "
            f"{table_cell(code_list(field for callsite in callsites for field in callsite['payloadKeys']))} | "
            f"{table_cell(code_list(callsite['canonicalPosition'] + ' / readable L' + str(callsite['readableLine']) for callsite in callsites))} | "
            f"{table_cell(code_list(callsite['evidenceFingerprint'] for callsite in callsites))} |"
        )
    lines.extend(
        [
            "",
            "</details>",
            "",
            "<details>",
            "<summary>Exact caller allowlist 全集（导航区间不参与分类）</summary>",
            "",
            "| mapping | rule | event | exact caller identity | evidence fingerprint | navigation only | caller owner | topic / scenario | 观测到的状态变化 | Boundary |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for mapping in CALLER_OWNER_ALLOWLIST:
        semantics = CALLER_OWNER_RULE_SEMANTICS[mapping.rule_id]
        lines.append(
            f"| {code_span(mapping.mapping_id)} | {code_span(mapping.rule_id)} | {code_span(mapping.event)} | "
            f"{table_cell(code_span(f'L{mapping.readable_line} / {mapping.function} / {mapping.consumer} / {mapping.comparison_key}'))} | "
            f"{code_span(mapping.evidence_fingerprint)} | "
            f"{code_span(f'L{mapping.navigation_start}-L{mapping.navigation_end}')} | "
            f"{code_span(mapping.owner)} | {table_cell(mapping.topic)}<br>{table_cell(mapping.scenario)} | "
            f"{table_cell(semantics.state_change)} | {table_cell(semantics.boundary)} |"
        )
    lines.extend(["", "</details>", ""])
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
    lines.extend(
        [
            "",
            f"family 层的 `tengu_other` 仍有 911 项，因为 family 规则只复现名字前缀。独立 caller/owner projection 目前逐项收口 {EXPECTED_CALLER_OWNER_STATUS['Single-owner'] + EXPECTED_CALLER_OWNER_STATUS['Cross-owner']} 个事件；其余 {EXPECTED_CALLER_OWNER_STATUS['Unresolved']} 项明确保持 `Unresolved`，不能把它们解释成一个语义兜底、产品模块或低价值集合。",
            "",
        ]
    )
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
    caller_projection: dict[str, Any] | None,
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
    ]
    if caller_projection is not None:
        caller_lines = sorted_unique(
            callsite["readableLine"] for callsite in caller_projection["callsites"]
        )
        caller_consumers = sorted_unique(
            callsite["consumer"] for callsite in caller_projection["callsites"]
        )
        fingerprints = sorted_unique(
            callsite["evidenceFingerprint"] for callsite in caller_projection["callsites"]
        )
        lines.extend(
            [
                f"- **Caller/owner projection (`Derived` from `Static` caller evidence):** status {code_span(caller_projection['status'])}; owner {code_list(caller_projection['owners'])}; topic {code_list(caller_projection['topics'])}; scenario {code_list(caller_projection['scenarios'])}; rules {code_list(caller_projection['rules'])}.",
                f"- **Caller evidence:** readable lines {code_list(caller_lines)}; consumer contexts {code_list(caller_consumers)}; evidence fingerprints {code_list(fingerprints)}. Classification requires an exact allowlist identity; name prefixes and navigation ranges do not assign owner.",
            ]
        )
    lines.extend(
        [
            f"- **Call shape (`Static`):** {len(ordered)} callsite{'s' if len(ordered) != 1 else ''}; logger role / callee: {code_list(roles)}; lexical functions: {code_list(functions)}; payload status: {format_counter(statuses)}.",
            f"- **Canonical position (`Static`):** line {canonical['line']}, column {canonical['column']}, offset {canonical['offset']}. All positions in offset order: {', '.join(code_span(item) for item in all_positions)}.",
            f"- **Payload keys (`Static`):** direct: {code_list(direct)}; expanded: {code_list(expanded)}; shorthand: {code_list(shorthand)}.",
            f"- **Unresolved spreads (`Boundary`):** {len(spreads)} occurrence(s).",
        ]
    )
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
    caller_projections: dict[str, dict[str, Any]],
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
            lines.extend(
                render_event_entry(
                    event,
                    family,
                    grouped[event],
                    allowlist,
                    caller_projections.get(event),
                )
            )
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
    readable: dict[str, Any],
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
        f"- Caller projection additionally verifies the linked readable JavaScript view and its metadata file byte-for-byte, then admits owner labels only through the {len(CALLER_OWNER_ALLOWLIST)}-entry exact caller allowlist; rule-bound state changes and Boundaries participate in the allowlist digest, while navigation ranges are display-only.",
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
    lines.append(
        f"| {code_span('readable caller view input')} | {readable['lines']} | {readable['size']} | {code_span(readable['sha256'])} |"
    )
    lines.append(
        f"| {code_span('readable caller metadata input')} | {readable['metadataLines']} | {readable['metadataSize']} | {code_span(readable['metadataSha256'])} |"
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
            f"生成器会先校验版本、所有精确数量、调用点 kinds/roles/callees、payload 状态、unresolved spread 总数、family 投影、事件字段映射、readable view hash、2,151 个固定 caller 的逐项对齐，以及 {len(CALLER_OWNER_ALLOWLIST)} 条 exact caller mapping 连同状态变化/Boundary 的完整 digest、identity 和 evidence fingerprint；任一不匹配都会拒绝覆盖输出。导航区间只用于阅读，不参与归属。输出按稳定排序生成，不包含时间戳或机器绝对路径，并通过同目录临时文件原子替换。",
            "",
            "## 最终边界",
            "",
            "- `Static`：只描述 Claude Code 2.1.235 已发布 bundle 中可到达的语法结构和静态集合，不等于某次运行已触发。",
            "- `Derived`：family、caller owner/topic/scenario、计数、交集、canonical/readable position 和聚合字段由本生成器确定性计算；它们不是 Anthropic 原始源码模块或服务端 taxonomy。",
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
    readable_by_row, readable_provenance = verify_readable_callsites(root, first_party_rows)
    caller_projections = project_caller_owners(grouped, projections, readable_by_row)

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
    lines.extend(render_scenario_semantic_index(grouped, projections, caller_projections))
    lines.extend(render_coverage(first_party_rows, dynamic, otel_rows, caller_projections))
    lines.extend(render_sensitivity_summary(first_party_fields))
    lines.extend(render_caller_owner_projection(caller_projections))
    lines.extend(render_family_summary(families, grouped, projections, set(allowlist)))
    lines.extend(render_dynamic_first_party(dynamic))
    lines.extend(
        render_static_first_party(
            grouped,
            projections,
            families,
            set(allowlist),
            caller_projections,
        )
    )
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
    lines.extend(
        render_provenance(
            root,
            summary_path,
            summary,
            verified,
            readable_provenance,
        )
    )
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
