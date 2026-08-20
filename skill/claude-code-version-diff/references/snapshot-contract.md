# Snapshot contract

## Required files

```text
VERSION
README.md
extracted/cli.js
extracted/<all other packed files>
analysis/version.json
analysis/unpack-manifest.json
analysis/release-notes.md
analysis/cli-surface.txt
analysis/risk-control-surface.txt
analysis/technical-architecture.md
analysis/context-governance-and-caching.md
analysis/inventory-field-guide.md
analysis/telemetry.md
analysis/source-surface.md
analysis/source-inventory/summary.json
analysis/source-inventory/*.{txt,tsv,jsonl}
skill/claude-code-version-diff/...
reverse/...                        Required when deep reverse is requested
reconstructed/...                  Required when native source reconstruction is requested
```

## `analysis/version.json`

Required top-level fields:

- `version`, `branch`, `capturedAt`
- `binary`: redacted/symbolic source path, redacted/symbolic entrypoint path, size, SHA-256, container, architecture, signing identity
- `extraction`: tool, tool version/commit, path-patching flag, payload offsets/sizes, file count, extracted bytes, skipped bytecode
- `mainSource`: packed path, repository path, size, line count, SHA-256, Bun banner

## Fidelity rules

- The installed executable is read-only input.
- The executable SHA-256 must match before and after extraction.
- Never commit the capture machine's username, home directory, Codex workspace, cache directory, or concrete install path. Use `$CLAUDE_INSTALL_ROOT`, `$CLAUDE_ENTRYPOINT`, or another stable symbolic placeholder in metadata and verification records.
- Absolute paths embedded in the shipped executable may remain only in canonical `extracted/` bytes and evidence derived directly under `reverse/`; label them as upstream build evidence rather than capture-machine metadata.
- Extraction uses packed bytes with path patching disabled.
- Every committed extracted file must match `sha256Packed` in the manifest.
- Renaming the primary packed path `cli` to repository path `extracted/cli.js` is allowed; its contents must not change.
- Do not commit generated formatting as the canonical source. A separately generated analysis view may be added only when clearly labeled.
- Do not claim the bundle reproduces upstream TypeScript modules or source names when source maps are absent.
- Deep-reverse outputs are derived evidence and must remain separate from `extracted/`.
- Native source reconstruction must remain under `reconstructed/`, carry evidence labels, and never replace the packed `.node` baseline.
- Generated source inventories must come only from canonical `extracted/cli.js`; do not generate them from the readable JavaScript view or hand-edit them.
- `analysis/source-inventory/summary.json` must record the canonical source hash plus every generated file's path, line count, size, and SHA-256.
- Source inventory format v3 must record vendored Acorn 8.15.0 as the JavaScript parser. Node or Bun may host it, but parser semantics must not depend on an unpinned global package.
- Every JSONL row must contain stable `comparisonKey` and `comparisonValue` fields. Location fields remain evidence but are excluded from semantic comparison values.
- Broad inventories must document dependency/embedded-document contamination boundaries. Do not label all environment-shaped tokens, schema properties, namespaces, URLs, or named components as user-facing Claude Code settings.

## Deep-reverse files

When `reverse/` exists, require:

```text
reverse/summary.json
reverse/manifest.json
reverse/bytecode/cli.jsc.gz
reverse/bytecode/metadata.json
reverse/javascript/cli.readable.js
reverse/javascript/metadata.json
reverse/index/summary.json
reverse/index/*.txt
reverse/native/<module>.node/metadata.json
reverse/native/<module>.node/<arch>/...
```

`reverse/manifest.json` hashes every deep-reverse artifact except itself. Bytecode metadata records both gzip and decompressed sizes/hashes. Native reports include every architecture present in the packed module.

## Normalized CLI surface

Keep one token per line under stable sections such as `[options]`, `[commands]`, and command-specific option sections. Remove aliases, wrapping, descriptions, and terminal-width effects so Git set diffs represent actual surface changes.

## Normalized risk-control surface

Keep stable, evidence-backed tokens under sections for permission modes and flags, permission decision sources, safety circuit breakers, sandbox runtime/network/filesystem controls, credential controls, trust gates, extension governance, enterprise governance, fail-closed behavior, and evidence boundaries.

Include a boundary stating that local CLI execution controls do not prove server-side account risk scoring or abuse-detection rules. Do not infer a control from a generic security-related string; require a CLI flag, settings schema field, decision branch, concrete rejection message, or reachable policy path.

## Human explanation documents

`README.md` must start with a reading guide and a plain request-lifecycle overview. Inventory counts are machine-evidence navigation, not the main explanation.

`analysis/technical-architecture.md` must connect input/resume, message graph, system/user context, tools/agents/skills/MCP, permissions/policy/hooks/sandbox, cache markers, API request/stream/tool loop, persistence, compaction, telemetry, native modules, and UI. It should let a reader follow the system without opening JSONL.

`analysis/context-governance-and-caching.md` must cover:

- system prompt stable/dynamic segmentation and cache scope;
- process-local schema/model cache versus API prompt cache;
- message breakpoints, fork pinning, skip-cache-write, family disable switches, and 5m/1h TTL precedence;
- tool search/deferred schema eligibility and provider/model fallback;
- context hint, keep-recent tool-result cleanup, persistence, thresholds, and status-specific fallback;
- auto-compact window source priority, model cap, output reservation, precompute/warn/compact/blocked thresholds, hooks, and failures;
- precomputed summary persistence/rehydration, compact boundary fields, JSONL parent repair, resume, transcript, and memory;
- one threshold example and one cache-cost example using the version's model catalog.

`analysis/inventory-field-guide.md` must explain JSONL/TSV/TXT formats, comparison fields, source locations/hashes, callsite and payload fields, environment/settings/model records, telemetry field families, heuristic boundaries, and how to translate a record into a product conclusion.

Read [human-analysis.md](human-analysis.md) for the full writing and cross-version comparison contract.

## Telemetry and source-surface documents

`analysis/telemetry.md` must cover every network and local observability path found in the bundle:

- first-party queues, enable/disable gates, sampling, batch defaults, endpoint, persistence, retry/backoff, auth fallback, envelopes, and event-field inventories;
- third-party OTEL metrics/logs/traces, exporter/protocol matrix, global/signal-specific config, temporality, timeouts, structured events, content controls, length limits, and spans;
- Datadog provider restriction, feature gate, allowlist, redacted/tag fields, normalization, rate bounds, batch defaults, and endpoint;
- GrowthBook transport/fields;
- error reporting, policy/compliance gates, secret scrubbing, Perfetto, startup/query profiling, debug/diagnostic/session/frame recording.

`analysis/source-surface.md` must map build/runtime, CLI/protocol, settings/env/schema, models/providers/auth, session/storage/memory/cache, agents/teams/worktrees/background, risk controls, MCP/hooks/plugins/skills/LSP, native/IDE/Chrome/Computer Use, cloud/remote/BYOC/workflows/artifacts, telemetry, update/doctor, UI/accessibility/voice, and API/error/retry/compact. Label each conclusion Observed, Derived, Compatible, or Heuristic.

## Deterministic source inventory

Run:

```bash
python3 skill/claude-code-version-diff/scripts/extract_source_inventory.py <repo>
```

The validator must regenerate into a temporary directory and compare exact bytes for the summary and every inventory file. It must also check required non-empty categories and reject stale, missing, extra, or manually edited artifacts.

The summary completion audit must prove all target `H`/`Fv`/`Nd`/`et`/`CB` and message callsites are recorded, all lexical strings/templates are counted, dynamic expressions and unresolved spreads are retained, root settings direct keys match structured rows, the baked model catalog is parsed, and `knownStaticExtractionGaps` is empty. Non-recoverable boundaries must be limited to values/code absent from the release artifact, such as runtime remote data, server-side behavior, or pre-bundle source removed by the build.

## Native reconstruction files

When `reconstructed/` exists, require:

```text
reconstructed/README.md
reconstructed/EVIDENCE.md
reconstructed/contracts/module-exports.json
reconstructed/scripts/validate_contracts.mjs
reconstructed/scripts/compare_behaviors.mjs
reconstructed/scripts/build_and_validate.sh
reconstructed/<language projects and lockfiles>
```

The build script must use a unique load directory. Document original/reconstructed contract results, behavior comparison results, and architecture coverage.

## Release evidence

Store the exact version's upstream release-note bullets. In the README, connect a note to source evidence only when the relevant setting, error, command, validation branch, or implementation literal is present in the extracted bundle.

## Completion checks

1. Source inventory extractor reruns deterministically.
2. Snapshot validator exits zero and reports source inventory files checked plus capture-path privacy PASS.
3. Source inventory summary reports the pinned parser, semantic JSONL fields, passing completion audit, and zero known static extraction gaps.
4. README links every required human document; the validator confirms each document is substantive and covers its required mechanism/field families.
5. Skill validator exits zero.
6. Deep-reverse validator exits zero when `reverse/` exists.
7. Git branch name equals `VERSION`.
8. Native release builds, original/reconstructed contracts, and paired behavior probes exit zero when `reconstructed/` exists.
9. Privacy scanning covers tracked files and untracked publish candidates, not only the current Git index.
10. Working tree contains only intended snapshot files before commit.
11. Local commit is present on the requested remote branch after push.
12. A fresh remote checkout passes validation and contains no capture-machine home/workspace path.
