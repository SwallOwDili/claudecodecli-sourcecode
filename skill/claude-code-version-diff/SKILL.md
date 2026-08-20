---
name: claude-code-version-diff
description: Unpack, deeply reverse, and source-reconstruct locally installed native Claude Code CLI releases into version-numbered Git branches, then produce evidence-based cross-version comparisons. Use for executable snapshots, release archaeology, bytecode/native-module analysis, native source compatibility, CLI surface diffs, or a long-running source archive; do not use for ordinary Claude configuration changes.
---

# Claude Code Version Diff

Create reproducible version snapshots from the installed Claude Code executable, optionally add the maximum static reverse-engineering view available from the shipped artifact, then compare version branches.

## Required inputs

- Target archive repository or local clone.
- Claude binary, defaulting to `command -v claude` with symlinks resolved.
- Version from `claude --version`; use the numeric value as the branch name unless the repository already uses a different convention.

Read [references/snapshot-contract.md](references/snapshot-contract.md) before creating or repairing a snapshot. For requests containing "完整逆向", "全量逆向", bytecode, native symbols, or disassembly, also read [references/deep-reverse.md](references/deep-reverse.md). When the request asks for `.node` C/C++/Rust/Swift source, "尽可能重建", or runnable native replacements, read [references/native-reconstruction.md](references/native-reconstruction.md).

Every snapshot or comparison intended for human readers must also follow [references/human-analysis.md](references/human-analysis.md). Machine inventories prove coverage; they do not replace architecture, field semantics, lifecycle, cost, failure, and user-impact explanations.

## Snapshot workflow

1. Record the resolved binary path locally, plus version output, size, SHA-256, container, architecture, code signature, and current Git remote/branches. Replace the committed source/entrypoint path with stable placeholders such as `$CLAUDE_INSTALL_ROOT` and `$CLAUDE_ENTRYPOINT`.
2. Preserve the installed binary. Extract from it without changing it and verify the binary hash again afterward.
3. Prefer a Bun module-graph extractor that emits a per-file manifest with offsets and packed hashes. Pin and record the extractor version/commit.
4. Extract with path rewriting disabled. Do not format, rename identifiers, or reconstruct modules before committing the raw comparison target.
5. Keep JavaScript, native helpers, assets, and the manifest. Add JSC bytecode and deep static-analysis artifacts when deep reverse is requested.
6. Store the primary packed module as `extracted/cli.js`; retain every other packed filename under `extracted/`.
7. Capture `VERSION`, `analysis/version.json`, the raw unpack manifest, exact upstream release notes for the version, a normalized CLI option/command inventory, and an evidence-based risk-control surface.
8. Run `scripts/extract_source_inventory.py <repo>` against canonical `extracted/cli.js`. It requires Node or Bun and the vendored Acorn 8.15.0 parser. Commit every generated file and `analysis/source-inventory/summary.json`; never hand-edit generated inventories.
9. Write `analysis/technical-architecture.md`, `analysis/context-governance-and-caching.md`, `analysis/inventory-field-guide.md`, `analysis/telemetry.md`, and `analysis/source-surface.md`. Cover every generated inventory category, the complete product capability surface, context/cache/compact/resume call chains, telemetry/export/log/profile paths, and field semantics. Separate product schema from dependency/embedded-doc heuristics.
10. Write the README as the reading router: lead with what to read and a request-lifecycle overview, then version delta and major behavior. Keep inventory counts as machine evidence, not the primary explanation.
11. Run `scripts/validate_snapshot.py` before committing. It regenerates source inventories in a temporary directory, validates `reverse/` when present, and rejects capture-machine home/workspace paths or credential-shaped values outside canonical packed/reverse evidence.
12. Commit on the numeric version branch. Push, verify that the remote branch points at the local commit, then clone/fetch the remote branch into a fresh directory and rerun validation plus privacy scanning.

If the executable is not a Bun standalone build, stop assuming this format and inspect its actual container/packaging before choosing an extractor.

## Deep reverse workflow

Deep reverse supplements the canonical packed bytes; it never replaces them.

1. Dump the complete JSC bytecode region recorded by the unpack manifest. Store it as deterministic gzip and record both compressed and decompressed hashes.
2. Produce a separately labeled readable JavaScript view with a pinned parser/formatter. Verify that stable environment identifiers and endpoint hosts match the canonical bundle.
3. Analyze every embedded `.node` file for each architecture: Mach-O headers and load commands, linked dylibs, imports, exports, full symbols, strings, Objective-C runtime data, Swift demangling, and complete text disassembly.
4. Generate normalized indexes for environment/feature identifiers, URLs and hosts, probable config keys, embedded build paths, native architectures, dependencies, imports, exports, and project Swift symbols.
5. Run `scripts/validate_deep_reverse.py` and record the decompressed bytecode hash, readable-JS hash, native-module count, and manifest file count.

Use `scripts/build_deep_reverse.py` so later versions have the same directory and report format. Keep compressed disassembly and full strings as evidence; use the normalized `reverse/index/` files for ordinary Git diffs.

## Native source reconstruction

Native reconstruction is a separate layer under `reconstructed/`; it never replaces `extracted/*.node` or `reverse/native/` evidence.

1. Recover the exact N-API object/function/prototype contract and record it as structured data.
2. Probe the original module with read-only or reversible inputs before implementing edge behavior.
3. Prefer the observed implementation language and dependency versions retained in build paths and strings.
4. Label each implementation claim `Observed`, `Derived`, or `Compatible`; passing tests do not turn compatible code into original source.
5. Build release artifacts and copy them to a unique directory using the original `.node` filenames. Never overwrite a native file already loaded by Node.
6. Validate original and reconstructed exports, then run both modules against the same inputs. Compare exact bytes/errors where stable and compare schemas/invariants for live screenshots, application order, devices, or permissions.
7. Keep architecture coverage explicit. A working arm64 rebuild does not prove x86-64 compatibility merely because the release module is universal.

Use the repository's `reconstructed/scripts/build_and_validate.sh` pattern for each version. Read the detailed reconstruction reference before creating or changing this layer.

## Comparison workflow

Run:

```bash
python3 scripts/compare_versions.py <repo> <old-branch> <new-branch> --output <report.md>
```

Lead with observed changes:

- embedded files, sizes, kinds, and hashes;
- CLI flags and commands;
- permission modes, safety circuit breakers, sandbox/network/filesystem/credential controls, trust gates, and managed-policy controls;
- provider/config/feature identifiers;
- endpoint hosts;
- every inventory file registered in `analysis/source-inventory/summary.json`, including event/field schemas, OTEL, Datadog, settings/schema, tools/commands, hooks/protocol, models/betas, storage, APIs, errors/diagnostics, URLs/hosts, and runtime requires;
- semantic JSONL rows via `comparisonKey` / `comparisonValue`, so source offsets, line wrapping, and minifier movement do not masquerade as behavior changes;
- source and analysis churn;
- JSC bytecode size/hash and readable-JavaScript size;
- native architecture, dependency, import/export, and Swift project-symbol changes;
- reconstructed native contracts, source files, languages, and implementation churn when present;
- upstream release notes corroborated by reachable source strings or structures.

After the deterministic report, write a human comparison for every materially changed subsystem. Explain old behavior, new behavior, trigger/priority/default, state transition, failure fallback, user-visible effect, token/latency/cost impact, and exact evidence. Do not publish a count-only report when settings, context, cache, telemetry, permissions, tools, models, storage, or protocol changed.

Do not infer a feature change only because a minified symbol, bytecode hash, address, or disassembly blob changed. Prefer a public CLI change, stable literal/config key, native API/dependency change, reachable validation branch, or official release note plus matching source evidence.

## README expectations

Cover:

- a first-screen reading guide and a plain request-lifecycle diagram;
- binary and extraction facts;
- payload structure and fidelity;
- exact release delta;
- major features and small behavioral details;
- CLI commands/options and supported execution modes;
- local execution risk controls and enterprise governance, with a boundary against unobserved server-side account/abuse scoring;
- native modules and embedded assets;
- source-reconstructed native modules, evidence classes, build commands, behavior probes, and architecture limits when present;
- bytecode, readable-JavaScript, native reverse reports, and normalized indexes when present;
- deterministic source inventories with counts, method boundaries, file hashes, and links;
- first-party analytics queues/sampling/batching/retry/storage/auth fallback, third-party OTEL exporters/content controls, Datadog forwarding, GrowthBook, error reporting, Perfetto, profiling, debug logs, and diagnostics;
- settings/env/schema, tools/slash commands/hooks/protocol, models/providers/auth/betas, session/storage/memory/cache, agents/teams/worktrees/background/cloud, integrations and UI/input/accessibility surfaces;
- limitations of bundled/minified source;
- validation and cross-version commands.

Keep hashes and byte counts machine-readable in `analysis/version.json`; do not make the README the only evidence store.

Put numeric inventories after the human entry points and label them as machine evidence. Link detailed architecture documents instead of duplicating every field in the README.

## Human explanation contract

Read [references/human-analysis.md](references/human-analysis.md) before writing or comparing the human layer. Every important mechanism must answer:

- what problem it solves and what object/state it governs;
- where it enters the request or runtime lifecycle;
- enable/disable gates, source precedence, defaults, thresholds, and limits;
- success state, failure states, retry/fallback, invalidation, and persistence;
- user-visible behavior and token/latency/cost/privacy/security impact;
- which fields prove each conclusion and how a reader should interpret them;
- what changed from the previous version and what did not.

For context governance, trace system prompt segmentation, user/system context, tool schema residency/deferral, prompt-cache scopes and message breakpoints, 5m/1h TTL eligibility, context hints, tool-result cleanup, precomputed/reactive/manual compaction, compact boundaries, transcripts, resume, and memory. Include at least one concrete window-threshold example and one cache-cost example using the version's baked model catalog.

## Exhaustive source inventory

`scripts/extract_source_inventory.py` is the deterministic cross-version source-surface extractor. It must read only the canonical packed bundle and emit `analysis/source-inventory/` plus a summary containing:

- canonical source size/hash;
- explicit extraction-method boundaries;
- count per category;
- path, line count, size, and SHA-256 for every generated file.

The current inventory contract uses vendored Acorn 8.15.0 with `ecmaVersion=latest`. It must record every AST callsite for `H`, `Fv`, `Nd`, `et`, `CB`, `T`, `Error`, `TypeError`, and `RangeError`; lexical function scope and nearest resolvable assignment; all arguments; static, template, conditional, identifier, member/call, and unresolved name expressions; payload properties, computed keys, shorthand, recursively resolvable spreads, and unresolved spreads; every quoted string and template occurrence; every static and dynamic environment access; typed environment builders/defaults; the complete root settings object; and the complete baked model catalog, pricing, aliases, and metadata.

Every JSONL row must carry `comparisonKey` and `comparisonValue`. The comparison value excludes location-only fields but preserves the semantic expression, payload, schema, or catalog value. Long, credential-shaped, or user-home-shaped values retain length, SHA-256, and locations without duplicating their content outside canonical evidence.

The validator must regenerate the entire directory to a temporary location and compare exact bytes. A passing check requires the committed summary, file set, counts, hashes, canonical source hash, Acorn version, JSONL comparison fields, target-callsite totals, and completion audit to match regeneration. `completionAudit` must confirm all target callsites and lexical literals are recorded, dynamic expressions are retained, settings keys match structured rows, the model catalog is parsed, and `knownStaticExtractionGaps` is empty.

Broad regex inventories such as environment-shaped identifiers, schema properties, storage namespaces, named components, URLs, and beta identifiers can include third-party dependencies or embedded documentation. Keep those labels heuristic. AST and structured parsers retain computed keys, spreads, and dynamic expressions without executing them. Runtime values returned by remote config/APIs/user files/environment variables, server-side behavior, and source removed before shipping remain outside the artifact and must be listed only as non-recoverable boundaries.

## Publication privacy

Before push, scan both tracked files and untracked publish candidates. Reject the capture user's concrete home directory, workspace/repository path, platform user-home paths, and credential-shaped values. The only path-evidence exception is canonical `extracted/` and derived `reverse/`, where upstream build paths already embedded in the shipped binary are retained as evidence.

After push, use a fresh remote checkout to prove that no local-only ignored file or stale index affected the result.

## Recovery boundary

Use precise labels:

- `extracted/` is the complete packed module graph recovered byte-for-byte from the executable.
- `reverse/bytecode/` is the complete shipped JSC bytecode cache, not source code.
- `reverse/javascript/` is a generated readable analysis view, not Anthropic's original formatting or module tree.
- `reverse/native/` is static analysis of the shipped Mach-O modules, not reconstructed Rust/Swift source files.
- `reconstructed/` is independently written compatible source grounded in shipped evidence and runtime probes, not Anthropic's original native repository.

Without source maps or debug information, original TypeScript filenames, comments, pre-bundle module boundaries, local variable names removed by minification, and code removed by tree shaking cannot be recovered exactly from the release executable. State this as an evidence boundary, while still delivering all recoverable shipped bytes and static-analysis views.
