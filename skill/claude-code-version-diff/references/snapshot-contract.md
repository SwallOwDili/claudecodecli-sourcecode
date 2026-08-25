# Snapshot contract

## Required files

```text
VERSION
README.md
ARTICLES.md
SNAPSHOT.md
extracted/cli.js
extracted/<all other packed files>
analysis/version.json
analysis/unpack-manifest.json
analysis/release-notes.md
analysis/cli-surface.txt
analysis/cli-command-inventory.json
analysis/risk-control-surface.txt
analysis/product-surface-evidence-map.md
analysis/product-surface-inventory-index.md
analysis/completeness-audit.md
analysis/technical-architecture.md
analysis/context-governance-and-caching.md
analysis/inventory-field-guide.md
analysis/telemetry.md
analysis/source-surface.md
analysis/source-inventory/summary.json
analysis/source-inventory/*.{txt,tsv,jsonl}
analysis/mechanism-evidence.jsonl
analysis/runtime-probe-index.md
analysis/runtime-probes/*.json
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
- `analysis/product-surface-evidence-map.md` is the reader-first architecture article. `analysis/product-surface-inventory-index.md` is the exact machine mapping regenerated from `summary.json`. Every registered inventory requires an explicit domain, evidence-strength classification, human reading route, and Boundary; a new inventory category must fail closed until classified. Keep the full table out of the architecture article so inventory volume cannot substitute for explanation.
- `analysis/completeness-audit.md` must use the evidence-appropriate state. A `Documented` row is valid only when it names the exact missing client/host fact and is not advertised as complete; `Boundary` is reserved for third-party, remote, platform or absent-source facts outside the artifact.

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

This normalized help surface is only the visible layer. Also generate `analysis/cli-command-inventory.json`, `analysis/cli-command-reference.md`, and `analysis/runtime-probes/cli-command-tree.json`. Recover every explicit Commander registration plus pre-Commander/manual routes such as daemon, background verbs, Remote Control aliases, self-hosted runner and internal worker/OS entrypoints. Every command row records path, syntax, arguments, visible and hidden/static options, aliases, visibility, registration/action gate, parser owner, handler owner, side effects, failure/exit behavior, Static source location and Probe limitation. Probe the exact binary in an isolated home and validate the usage marker as well as exit status: an unknown token may fall back to root help at exit zero, while a real fast-path command may fail an auth/policy gate before rendering help.

## Normalized risk-control surface

Keep stable, evidence-backed tokens under sections for permission modes and flags, permission decision sources, safety circuit breakers, sandbox runtime/network/filesystem controls, credential controls, trust gates, extension governance, enterprise governance, fail-closed behavior, and evidence boundaries.

Include a boundary stating that local CLI execution controls do not prove server-side account risk scoring or abuse-detection rules. Do not infer a control from a generic security-related string; require a CLI flag, settings schema field, decision branch, concrete rejection message, or reachable policy path.

## Human explanation documents

`ARTICLES.md` is the complete reader-first technical index. `README.md` must be its byte-identical publication copy so the GitHub homepage preserves the same curated order and grouped tutorial/reference/evidence navigation. `SNAPSHOT.md` preserves the former project README: artifact identity, source-recovery boundary, governing product thesis, request-lifecycle overview, release delta, hashes, reverse layers and validation commands. Inventory counts and validator ledgers remain in dedicated evidence indexes.

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

`analysis/product-surface-evidence-map.md` must begin with a reader model and teach one scenario across capability compilation, Agent Loop, execution control, context governance, observability, recovery, dynamic extension, remote uncertainty, and native boundaries. The same command must generate the exact full mapping as `analysis/product-surface-inventory-index.md`; the article links it instead of embedding its table. Run:

```bash
python3 skill/claude-code-version-diff/scripts/build_product_surface_map.py <repo> \
  --output <repo>/analysis/product-surface-evidence-map.md
```

The command writes both `product-surface-evidence-map.md` and the sibling `product-surface-inventory-index.md`; `--check` validates both byte-for-byte.

When Plugin/Skill/LSP are shipped, `probe_plugin_skill_lsp.mjs` must use an isolated session plugin and fake stdio LSP server. It must distinguish Skill launch acknowledgement from body injection, preserve deferred LSP schema semantics, verify initialize/open/request/shutdown, coordinate conversion, paired results, exact version/hash, literal output and exit status.

When proxy/CA/mTLS surfaces are shipped, require `analysis/runtime-probes/network-proxy-tls.json`, generated by `probe_network_proxy_tls.mjs` with a local HTTPS Messages service, conflicting lower/upper-case CONNECT proxies, NO_PROXY, an invalid scheme-less proxy, a probe CA and a client certificate. The report must bind exact version/SHA, commands, controlled inputs, literal results, exit statuses, API/proxy hit evidence, client-certificate identity, required checks and a transport-specific Boundary. `validate_network_proxy_tls.py` and its forgery test must reject field tampering; one Messages-path success never proves Axios, WebSocket, AWS, MCP, OTLP, subprocess or CCR behavior.

When OTLP HTTP export and TLS inputs ship, require `analysis/runtime-probes/otlp-tls.json` from `probe_otlp_tls.mjs`. The fixture must first prove its HTTPS/TLS 1.2/mTLS collectors with an independent client, then compare OTLP-specific certificate/client variables with the programmatic agent actually supplied by the product, verify a paired client identity, conflicting proxy precedence and failure isolation. Bind the effective owner rather than documenting only the bundled library parser. `validate_otlp_tls.py` and its forgery test must reject false CA success, false client-certificate forwarding, proxy relabeling, peer-identity tampering and lost Boundary text. Keep insecure TLS disabling diagnostic-only and keep gRPC, other signals, CCR and remote collector behavior outside the HTTP logs claim.

When Plugin Evaluation ships, require `analysis/runtime-probes/plugin-evaluation.json`, generated by `probe_plugin_evaluation.mjs` from an isolated local plugin/case, one with run, one without run, a free deterministic grader and a local Messages stub. The with request must carry plugin-only Hook context while the without request omits it; score, scoreWithout, Delta, partial state, JSON/HTML outputs and no-publish/no-scaffold command fields must be explicit. A dedicated validator and forgery test must reject arm/score/Delta/hook/path/Boundary tampering. Keep paid judges, model/plugin quality, cost ceilings, remote publish and OS/network isolation outside this smoke claim.

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

The summary completion audit must prove that every semantic target role was discovered from stable anchors, its release-local minified symbol matches callsite coverage, all target and message callsites are recorded, all lexical strings/templates are counted, dynamic expressions and unresolved spreads are retained, root settings direct keys match structured rows, and detected environment/settings/model/Datadog structures are nonempty. It must reject a copied symbol map from another version and keep `knownStaticExtractionGaps` empty. Non-recoverable boundaries must be limited to values/code absent from the release artifact, such as runtime remote data, server-side behavior, or pre-bundle source removed by the build.

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

Store the exact version's upstream release-note bullets. In `SNAPSHOT.md`, connect a note to source evidence only when the relevant setting, error, command, validation branch, or implementation literal is present in the extracted bundle.

## Completion checks

1. Source inventory extractor reruns deterministically.
2. Snapshot validator exits zero and reports source inventory files checked, deterministic product-surface mapping, evidence-appropriate Deep/Documented/Boundary capability states, and capture-path privacy PASS.
3. Source inventory summary reports the pinned parser, semantic JSONL fields, passing completion audit, and zero known static extraction gaps.
4. `README.md` and `ARTICLES.md` are byte-identical complete human indexes and link every required human document; `SNAPSHOT.md` owns the project explanation, release identity, hashes and verification details. Completeness and Skill contracts still bind each deep topic independently.
5. Skill validator and negative tests exit zero; negative cases cover a missing inventory classification, a contracted capability downgraded from `Deep`, and a `Documented` row that no longer names its exact missing fact.
6. Deep-reverse validator exits zero when `reverse/` exists.
7. Git branch name equals `VERSION`.
8. Native release builds, original/reconstructed contracts, and paired behavior probes exit zero when `reconstructed/` exists.
9. Privacy scanning covers tracked files and untracked publish candidates, not only the current Git index.
10. Working tree contains only intended snapshot files before commit.
11. Local commit is present on the requested remote branch after push.
12. A fresh remote checkout passes validation and contains no capture-machine home/workspace path.
