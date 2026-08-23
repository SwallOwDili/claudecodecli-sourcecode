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

Every snapshot or comparison intended for human readers must also follow [references/human-analysis.md](references/human-analysis.md). For a dense or high-value mechanism that readers need to learn, debug, or compare, also follow [references/reader-first-visual-explanation.md](references/reader-first-visual-explanation.md). Machine inventories prove coverage; they do not replace architecture, field semantics, lifecycle, cost, failure, user-impact explanations, or a coherent teaching path.

When the request is to improve an existing analysis archive, preserve the existing evidence layer and add the teaching layer in place. Do not shorten away thresholds, fields, call order, source ranges, Probe outcomes, failure branches, privacy/security/cost effects, or recovery boundaries. Every core human topic should open with a reader question, one-sentence mental model, one scenario, a before/after or state-ownership table, and an editable lifecycle diagram before continuing into the original technical depth.

Generated exhaustive references are publication contracts, not optional appendices. Build and validate `analysis/environment-variable-reference.md` with `scripts/build_environment_feature_references.py`, keeping typed declarations, named reads, declaration-only names, non-typed static names, dynamic expressions, parser/fallback shape, consumer evidence and sensitivity heuristics separate. Use `Static consumer` only after tracing the client owner and secondary gates, `Untraced/Inventory only` for shipped named reads whose consumer work is unfinished, `Opaque codename / Inventory only` for feature codenames, and `Boundary` only for runtime-computed names, server state, missing source, or facts outside the release artifact. The same generator must build `analysis/feature-flag-reference.md`, distinguishing direct literals, assignment-resolved static keys, truly unresolved dynamic calls and cached dynamic-config keys. Build `analysis/telemetry-event-catalog.md` with `scripts/build_telemetry_event_catalog.py`; it must preserve every first-party event/callsite, dynamic event expression, payload field/spread, Datadog eligibility, OTEL event/metric/span and the client/server boundary. Before the exhaustive rows, generate a scenario semantic index that covers at least API request attempts, tool permission/execution, permission UI, compact, session persistence/resume, MCP auth, background dispatch, account auth, query/process errors and transcript recovery; for each scenario explain ordered/optional events, state owner, field value meaning, success/failure delta, diagnostic action and deeper mechanism link. Treat catch-all families such as `tengu_other` as navigation buckets, never as low-value product taxonomy. Validators must regenerate these documents byte-for-byte and reject count drift, deleted semantic-index/Boundary text or stale generated output.

Build `analysis/api-beta-route-ownership.md` and `analysis/error-diagnostic-atlas.md` with `scripts/build_api_error_references.py`. The API/Beta chapter must classify every fixed path and version identifier by reachable product consumer, bundled server handler, dependency/SDK, prefix/allowlist, embedded reference or remote Boundary; path/header presence never proves a request was sent or accepted. The error atlas must connect constructor and diagnostic callsites to concrete owners, fields, recovery budgets, user surfaces, observability lanes, privacy controls and post-side-effect boundaries. Bind both chapters to README, `ARTICLES.md`, the complete guide, completeness capabilities, editable DOT/SVG, topic-depth validation and negative mutation tests.

Do not let rare entrypoints disappear inside a broad command, Artifact or telemetry table. When shipped, maintain dedicated reader-first lifecycle chapters for `analysis/artifact-watch-comment-autoreact.md`, `analysis/insights-history-analysis-pipeline.md`, `analysis/cli-startup-files-plugins-deeplinks.md` and `analysis/complex-slash-command-lifecycles.md`. Cover local/remote state ownership, untrusted-input isolation, cache invalidation, exact download/ZIP/queue/model budgets, partial success, external side effects and rollback boundaries. Bind each chapter to README, `ARTICLES.md`, the complete guide, the completeness matrix, an editable DOT/SVG, a topic-depth validator contract and at least one negative test that proves the contract cannot silently disappear.

## Snapshot workflow

1. Record the resolved binary path locally, plus version output, size, SHA-256, container, architecture, code signature, and current Git remote/branches. Replace the committed source/entrypoint path with stable placeholders such as `$CLAUDE_INSTALL_ROOT` and `$CLAUDE_ENTRYPOINT`.
2. Preserve the installed binary. Extract from it without changing it and verify the binary hash again afterward.
3. Prefer a Bun module-graph extractor that emits a per-file manifest with offsets and packed hashes. Pin and record the extractor version/commit.
4. Extract with path rewriting disabled. Do not format, rename identifiers, or reconstruct modules before committing the raw comparison target.
5. Keep JavaScript, native helpers, assets, and the manifest. Add JSC bytecode and deep static-analysis artifacts when deep reverse is requested.
6. Store the primary packed module as `extracted/cli.js`; retain every other packed filename under `extracted/`.
7. Capture `VERSION`, `analysis/version.json`, the raw unpack manifest, exact upstream release notes for the version, a normalized CLI option/command inventory, and an evidence-based risk-control surface.
8. Run `scripts/extract_source_inventory.py <repo>` against canonical `extracted/cli.js`. It requires Node or Bun and the vendored Acorn 8.15.0 parser. Commit every generated file and `analysis/source-inventory/summary.json`; never hand-edit generated inventories.
9. Research current first-party Claude Code/Agent SDK documentation and relevant Anthropic Engineering articles. Use `scripts/refresh_public_sources.py` to store retrieval time, URL, HTTP status, response bytes, response-body SHA-256, normalized visible-text SHA-256, per-excerpt SHA-256, and per-excerpt source-presence verification in `analysis/public-sources/manifest.json`; store only passages whose quoted lines occur in the captured visible page text in `analysis/public-source-excerpts.md`. Every official Anthropic URL cited by snapshot Markdown must exist in the manifest. Label results `Public`, target-version `Static`, exact-binary `Probe`, or `Boundary`. Current documentation must never be silently backported into an older snapshot.
10. Create `analysis/mechanism-evidence.jsonl`. Give every strong claim a unique ID and a validator-checkable evidence shape: real source view/path/range/anchors plus `staticEvidenceKind` for `Static`, command/input/literal output/exit status/checks for `Probe`, manifest source plus excerpt for `Public`, and an explicit reason for `Boundary`. Classify schema/help/message-only evidence as `declaration` or `surface`, state its limitation, and do not use it to claim that a runtime branch executed. Maintain `analysis/runtime-probe-index.md` so every Probe claim has a human explanation of its state transition and boundary. When carrying this registry from an older branch, run `CLAUDE_SOURCE_VERSION=<old> node scripts/relocate_mechanism_evidence.mjs <repo> --write` only after the new readable view exists. The relocator reads the target `VERSION`, prefers anchor groups near each record's prior range, and requires explicit overrides for genuine symbol collisions; never hardcode one release pair into the reusable script.
11. Write the complete human mechanism layer: `analysis/product-surface-evidence-map.md`, `analysis/completeness-audit.md`, `analysis/tool-registration-and-host-surfaces.md`, `analysis/brief-mode-and-user-visible-output.md`, `analysis/plan-mode-and-human-approval.md`, `analysis/structured-output-and-schema-contract.md`, `analysis/repl-programmatic-tool-runtime.md`, `analysis/end-conversation-risk-control.md`, `analysis/remote-routines-runner-and-notifications.md`, `analysis/connectors-catalog-and-mcp-operators.md`, `analysis/claude-design-and-projects.md`, `analysis/builtin-tools-reference.md`, `analysis/settings-reference.md`, `analysis/cli-command-reference.md`, `analysis/cli-sdk-output-protocol.md`, `analysis/plugins-skills-commands-lsp.md`, `analysis/slash-command-reference.md`, `analysis/hooks-event-reference.md`, `analysis/storage-v5-reference.md`, `analysis/workflow-artifact-design.md`, `analysis/feature-flags-remote-config.md`, `analysis/tui-input-accessibility-media-ide-chrome.md`, `analysis/cloud-background-channels.md`, `analysis/technical-mechanism-atlas.md`, `analysis/public-claims-validation.md`, `analysis/technical-architecture.md`, `analysis/agent-loop.md`, `analysis/context-governance-and-caching.md`, `analysis/sessions-checkpoints-memory.md`, `analysis/tools-permissions-hooks.md`, `analysis/mcp-agents-background.md`, `analysis/resilience-and-recovery.md`, `analysis/models-auth-providers-request.md`, `analysis/settings-feature-flags-policy.md`, `analysis/tui-ide-remote-cloud.md`, `analysis/install-update-doctor-lifecycle.md`, `analysis/native-bridge-runtime.md`, `analysis/auto-mode-classifier.md`, `analysis/plugin-evaluation-harness.md`, `analysis/runtime-supervision-and-processes.md`, `analysis/enterprise-gateway-runtime.md`, `analysis/auth-account-and-subscription-lifecycle.md`, `analysis/onboarding-workspace-trust-and-safe-startup.md`, `analysis/thinking-effort-and-fast-mode.md`, `analysis/usage-cost-credits-and-limits.md`, `analysis/project-purge-import-and-data-lifecycle.md`, `analysis/sandbox-install-and-runtime-enforcement.md`, `analysis/network-proxy-ca-and-mtls.md`, `analysis/active-goal-and-stop-loop.md`, `analysis/background-model-tasks-and-memory-consolidation.md`, `analysis/advisor-dual-model-runtime.md`, `analysis/ultrareview-cloud-review.md`, `analysis/inventory-field-guide.md`, `analysis/telemetry.md`, and `analysis/source-surface.md`. Generate `analysis/cli-command-inventory.json` and `analysis/runtime-probes/cli-command-tree.json` with `scripts/probe_cli_command_tree.mjs`; do not treat `cli-surface.txt` or root help as the complete command authority. Recover Commander nodes, pre-Commander fast paths, manual parsers, aliases, hidden/conditional gates, arguments/options, handler owners, side effects, failure behavior and internal worker/OS entrypoints. Run `scripts/build_product_surface_map.py <repo> --output analysis/product-surface-evidence-map.md`; every inventory file registered by `summary.json` must be classified as product structure/callsite/broad surface, mixed heuristic, dependency surface, or evidence substrate and linked to its human mechanism and Boundary. Cover request assembly, Agent Loop, context/cache/compact, session/checkpoint/memory, the exact release-local core-tool reference set, every same-factory tool registration callsite plus aliases/dynamic name expressions/host classification, Brief/user-visible-output routing, Plan Mode/human approval, Structured Output/schema enforcement, REPL programmatic tool execution and replay, EndConversation risk-control termination, RemoteTrigger/routines/runner/notification ownership, Connector/account catalog discovery and MCP operator refresh, ClaudeDesign dynamic MCP discovery plus Projects consent/grant/file/RAG lifecycle, every slash command, every Hook event, every Claude storage namespace, tool/permission/hook/sandbox, Auto Mode classification, MCP/agents/tasks/background, daemon/PTY/rendezvous supervision, retry/fallback/resume/rewind, every direct root setting, full CLI command routing, CLI/SDK/output protocol, plugins/skills/commands/LSP, Plugin Evaluation ablation/grading, Workflow/Artifact/Design, feature evaluation, TUI/input/accessibility/media/IDE/Chrome, Channels/Remote/Cloud/runner ownership, Enterprise Gateway identity/policy/routing/spend/telemetry, auth/account/subscription/setup-token, onboarding/workspace trust/safe startup, Thinking/Effort/Fast Mode, usage/cost/credits/limits, project purge/import/data lifecycle, sandbox install/runtime enforcement, proxy/NO_PROXY/CA/mTLS, Active Goal/Stop-loop, background model tasks/memory consolidation, Advisor server-tool runtime, Ultrareview cloud review, models/auth/providers, install/update/doctor, native bridges, observability, and field semantics. For tool counts, state whether the unit is an AST factory callsite, a reusable factory template, a statically expanded factory invocation, a curated reference set, or a request-time tool object. Do not present a hand-maintained name allowlist as a source-native assembly set, and do not label a retained dynamic expression runtime-unknown until its callers and constant arguments have been traced. For Brief attachments, trace lane selection through the actual upload function and endpoint; lane labels do not prove distinct transports, and HTTP success plus `file_uuid` does not prove a remote viewer rendered the file. `completeness-audit.md` must enumerate the authoritative product surfaces and keep any non-deep capability visible instead of letting inventory counts stand in for explanation. Exact marker blocks must match the release-local core tool, same-factory registration, setting, slash-command, Hook-event and Claude-storage-namespace inventories. A `Deep` row for a multi-phase mechanism is valid only when its topic depth contract binds the row to a reader-first article, an ordered lifecycle, gates/thresholds, failure/recovery, user impact, source evidence, an explicit Boundary, and valid DOT/SVG. Add reader-first visual guides for the mechanisms most likely to be misunderstood; each guide must retain editable diagram sources beside rendered assets. Separate product schema from dependency/embedded-doc heuristics.
12. Run an isolated exact-binary positive Agent Loop probe when practical. It must advertise a real tool schema, receive `tool_use`, execute a reversible tool, observe the paired `tool_result` in the next request, reach success, then successfully resume that session and prove history injection. Empty state and error-only commands remain command-surface evidence, not positive mechanism probes. When Plugin/Skill/LSP are shipped, also run `scripts/probe_plugin_skill_lsp.mjs`: use an isolated `--plugin-dir`, verify the namespaced Skill listing, distinguish launch acknowledgement from body injection, start a fake stdio LSP server, observe initialize/open/request/shutdown, verify editor-to-protocol coordinate conversion, and pair the result by tool-use ID. Record deferred schema residency rather than forcing it into first-request tools.
13. Write the README as the reading router: lead with the best reader-first visual guide, mechanism atlas, public-claim validation, question-oriented topic links, and a request-lifecycle overview, then version delta and major behavior. Keep inventory counts as machine evidence, not the primary explanation.
14. Run `scripts/validate_snapshot.py` before committing. It regenerates every source inventory and the release-local product-surface map from `summary.json`, requires every non-Boundary completeness capability to be `Deep`, enforces declarative topic depth contracts for multi-phase mechanisms, validates the exact tool-registration table/classification, human documents, structured mechanism evidence, public manifests/excerpts and probe reports, validates `reverse/` when present, and rejects capture-machine home/workspace paths or credential-shaped values outside canonical packed/reverse evidence. Run `scripts/test_validator_negative.py` to prove the validator rejects path leakage, fabricated excerpts, unclassified inventory surfaces, missing registration/Brief coverage, a capability downgraded from `Deep`, missing lifecycle/threshold/evidence/binding/visual depth, unindexed Probe claims and failed required checks while restoring every mutated file byte-for-byte.
15. Commit on the numeric version branch. Push, verify that the remote branch points at the local commit, then clone/fetch the remote branch into a fresh directory and rerun validation, positive probes, and privacy scanning.

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
6. Validate original and reconstructed exports, then run both modules against the same inputs. Compare exact bytes/errors where stable and compare schemas/invariants for live screenshots, application order, devices, or permissions. Emit `analysis/runtime-probes/native-reconstruction.json` with every check, comparison mode, input strategy, original/compatible evidence label, and per-architecture coverage.
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
- Agent Loop entrypoints, state fields, streaming tool start point, concurrency barriers, tool pipeline order, queue absorption, max-turn accounting, Stop hook re-entry, fallback sweeps, terminal reasons, and subagent isolation;
- session/message-graph/compact-boundary repair, checkpoint caps, rewind semantics, transcript retention, and memory entrypoint limits;
- tool schema and alias contracts, permission precedence, hooks, sandbox/filesystem/network/credential controls, managed policy, and fail-closed behavior;
- MCP generation refresh, Tool Search deferral/cache invalidation, subagent defaults/isolation, background durability, task claim, mailbox, and worktree boundaries;
- request/stream/model/output/context/tool/hook/MCP/session recovery layers, including exactly which provisional messages are discarded and which completed external side effects remain;
- provider selector/model catalog/auth source/custom endpoint/request-body changes;
- auth credential/account/org/subscription/setup-token state transitions, trust gates, local/remote logout effects and account-cache invalidation;
- onboarding versus workspace trust, safe/bare/print startup matrices and post-trust rediscovery;
- Thinking/Effort/Fast Mode request shapes, precedence, model/organization gates, compatibility latches, service-tier cooldown and cost indices;
- usage/cost/credits/limit windows, warning/checkpoint thresholds, auto-resume arming/cancellation/stale/rearm behavior;
- project purge/import plans, preview digests, archive guards, manifest checks, partial completion and data-retention effects;
- sandbox host installation versus per-command runtime enforcement, proxy/NO_PROXY/CA/mTLS transport coverage and certificate reload;
- Active Goal Stop-hook re-entry/caps, background model-task ownership/persistence, Advisor server-tool selection/strip, and Ultrareview cloud/fix/post consent boundaries;
- settings source and per-field merge semantics, feature evaluation, environment override and managed-policy changes;
- TUI/print/SDK, IDE protocol/context, Remote Control reconnect/attachment and cloud-session ownership changes;
- installer shape, real version file, migrations, update gates, doctor checks and rollback compatibility changes;
- JavaScript-to-N-API consumer contracts, native object lifetimes, errors, dependencies, slices and side-effect changes;
- changes between current public claims and what each target release can actually prove, with source retrieval dates and explicit version-drift boundaries;
- mechanism claim additions/removals, semantic changes, evidence-class upgrades/downgrades, and evidence-shape changes;
- first-party response hash/excerpt drift and exact-binary probe command/input/output/check drift;
- upstream release notes corroborated by reachable source strings or structures.

After the deterministic report, write a human comparison for every materially changed subsystem. Explain old behavior, new behavior, trigger/priority/default, state transition, failure fallback, user-visible effect, token/latency/cost impact, and exact evidence. Do not publish a count-only report when settings, context, cache, telemetry, permissions, tools, models, storage, or protocol changed.

Do not infer a feature change only because a minified symbol, bytecode hash, address, or disassembly blob changed. Prefer a public CLI change, stable literal/config key, native API/dependency change, reachable validation branch, or official release note plus matching source evidence.

## README expectations

Cover:

- a first-screen reading guide and a plain request-lifecycle diagram;
- an exact release-local product-surface evidence map regenerated from `summary.json`, separating product structure/callsites from mixed heuristics, dependencies and lexical evidence;
- an exact same-factory tool-registration reference distinguishing AST callsites, reusable factory templates, statically expanded invocations, the curated core reference set, editorial host classification and the request-time `tools[]` surface;
- a dedicated Brief/user-visible-output guide covering entry gates, `SendUserMessage`, plain-text projection, lane selection versus the actual upload endpoint, client-mapped partial delivery, remote-viewer boundaries, renderer behavior and turn-end enforcement;
- dedicated `analysis/claude-design-and-projects.md`, Plan Mode, Structured Output, REPL runtime, EndConversation risk control, Remote Ops, and Connector/Catalog/MCP guides whose topic depth contracts bind README, `ARTICLES.md`, every applicable completeness row, Skill instructions, ordered state machines, evidence, Boundary, and editable/rendered visuals; the ClaudeDesign/Projects guide must preserve dynamic MCP discovery, layered consent/path/durable grants, attached-project OAuth scope, RAG fallback, TOCTOU upload checks, knowledge budgets, and remote-side-effect boundaries;
- a capability-by-capability completeness audit that tracks `Deep`, `Documented`, `Inventory only`, and `Boundary` while work is in progress, but allows publication only when every non-Boundary capability is `Deep`;
- an exact built-in-tool reference whose coverage marker matches the release inventory and explains each tool's owned state, side effects, failure and recovery boundaries;
- an exact direct-root-settings reference whose coverage marker matches the release schema and explains source, merge, consumer, lifecycle and evidence strength;
- a CLI/SDK/output-protocol guide that separates local input/output envelopes, control request/response, observation events, structured output, session state and slash-command routing;
- a complete CLI command-tree guide and structured inventory that distinguish root help from Commander registration, pre-Commander fast paths and manual parsers; record aliases, hidden/conditional gates, arguments/options, handler owner, side effects, failure/exit behavior and internal entrypoints, with an exact-binary help-tree probe that rejects exit-status-only existence tests;
- a plugins/skills/commands/LSP lifecycle guide covering source trust, registry/cache, enablement, listing budget, reload, process ownership, diagnostics and prompt-cache invalidation;
- an exact slash-command reference whose marker matches the release inventory and whose per-command rows distinguish type/twin, visibility, host, gate, owned state, persistence, failure and irreversible side effects;
- an exact Hook-event reference whose marker matches the release inventory and whose rows distinguish event timing, common and event-specific fields, matcher, command/HTTP/MCP runner, blocking/mutation, timeout and post-side-effect boundaries;
- an exact Claude storage-namespace reference whose marker matches the release inventory and whose rows distinguish typed key/scope, real consumer, write discipline, preconditions, backend reachability, concurrency, retention, migration, sensitivity and Boundary;
- dedicated Workflow/Artifact/Design, feature-flags/remote-config, TUI/input/accessibility/media/IDE/Chrome, and background/Channels/Remote/Cloud/runner lifecycle guides;
- a mechanism atlas that names owned state, lifecycle transitions, failure symptoms, user impact, and links to every deep topic;
- a public-claim validation matrix separating current first-party documentation, target-version static evidence, exact-binary probes, and unverified/server-side boundaries;
- a dedicated Agent Loop chapter covering model turns versus API attempts, streaming tool execution, concurrency, hooks/permissions, result feedback, stop conditions, retries/fallbacks, max turns, and subagents;
- dedicated session/checkpoint/memory, tools/permissions/hooks, MCP/agents/background, and resilience/recovery chapters;
- dedicated models/auth/providers/request, settings/feature-flags/policy, TUI/IDE/remote/cloud, install/update/doctor, and native-bridge chapters;
- dedicated Auto Mode, Plugin Evaluation Harness, runtime supervision, Enterprise Gateway, auth/account/subscription, onboarding/workspace trust, Thinking/Effort/Fast Mode, usage/cost/credits/limits, project/data lifecycle, sandbox install/runtime, proxy/CA/mTLS, Active Goal, background model tasks, Advisor and Ultrareview chapters when those surfaces ship; explain their owned state and full failure contracts instead of leaving them under generic permission/plugin/background/provider headings;
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
- settings/env/schema, tools/slash commands/hooks/protocol, models/providers/auth/betas, session/storage/memory/cache, agents/teams/worktrees/background/cloud, Workflow/Artifact/Design, feature-evaluation, Channels/runner, integrations and UI/input/accessibility/media surfaces;
- limitations of bundled/minified source;
- validation and cross-version commands;
- structured mechanism evidence, fixed public-source excerpts/hashes, and normalized exact-binary probe reports.
- a human runtime-probe index covering every Probe claim ID, report-field semantics, literal outcomes and narrow proof boundaries.

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

For Agent Loop analysis, trace the outer turn wrapper, observer tap, core state object, pre-call queue absorption and compaction, model streaming parser, the exact point where a completed `tool_use` block starts execution, concurrency-safe scheduling and barriers, input/hook/permission/output validation order, tool-result pairing, Stop hook re-entry, max-turn accounting, fallback abort/tombstone behavior, terminal reasons, and subagent isolation. Explicitly state that message tombstones and aborts cannot undo completed external side effects.

For session and recovery analysis, trace message UUID/parent graphs, transcript event persistence, compact boundaries and resume repair, fork and leaf selection, file checkpoint limits/dry-run/rewind, memory entrypoint budgets, prompt-cache independence, and the exact external side effects that cannot be restored.

For MCP and multi-agent analysis, trace configuration trust, connection/auth/list lifecycle, generation refresh, deferred schema and cache invalidation, child-loop defaults and isolation, permission bubbling, task registry/claim, mailbox delivery/ack/size semantics, background durability, worktree scope, and token/coordination cost.

For model and request analysis, trace provider and credential precedence, model alias/catalog resolution, first-party/custom endpoint gates, beta/header construction, request fields, streaming selection, and server-side boundaries. For settings and product-surface analysis, trace per-field merge semantics, feature/policy gates, TUI/IDE/remote/cloud state ownership, updater/doctor lifecycle, and JavaScript-to-N-API contracts rather than listing identifiers.

For Auto Mode analysis, place it after deterministic permission and policy floors; trace trusted rule sources, `$defaults`, `classifyAllShell`, fast paths, transcript construction, each classifier stage and budget, XML parsing, unavailable/refusal behavior, fail-closed outcomes, PermissionDenied Hook re-entry, interactive/headless fallback, and hash-bound settings setup. Do not describe a no-verdict denial as a proven dangerous-action classification.

For Plugin Evaluation analysis, trace case schema and identity checks, plugin trust, with/without ablation, per-run HOME/config/workspace isolation, actual child argv and tool grants, all grader types, judge voting, weight math, cost/auth interruption, partial/Delta comparability, scaffold side effects, output schemas and CI exits. State explicitly that its temp sandbox is not OS or network isolation.

For runtime supervision, separate Agent View, daemon supervisor, PTY host, Claude worker, rendezvous and durable job storage. Record socket authentication, ring/backpressure bounds, liveness timers, wrapper contract, cold/warm/adopt paths, respawn budget, settled-state suppression, memory-pressure reap, async hook rewake and the external side effects resume cannot undo.

For Enterprise Gateway, trace native-runtime gating, config expansion/validation, Postgres migration, OIDC/device/session identity, managed policy, admin authentication precedence, CRI/JWKS/webhook admission, spend precheck and metering, model mapping/provider failover, response hygiene, OTLP fanout/circuit breaker and retention. Separate locally implemented gateway behavior from IdP, CRI issuer, cloud provider and account-abuse internals.

For auth/account/subscription analysis, separate credential acquisition, persistence, account and organization validation, subscription-derived state, setup-token, runtime generation/cache invalidation, Remote Control side effects, remote refresh-token revocation and local logout cleanup. Do not describe local credential deletion as proof of server-side revocation.

For onboarding and workspace trust, separate account onboarding from project trust. Enumerate every project-controlled executable or permission-expanding surface, persisted versus session trust, the post-trust rediscovery step, and the exact safe/bare/noninteractive startup matrix. No helper or project command may be described as active before the trust gate is reachable.

For Thinking/Effort/Fast Mode, keep the three axes separate. Trace model capability, organization ceiling, command/setting/environment precedence, request fields, tool-choice interactions, compatibility 400 latches, Fast Mode service-tier eligibility, 429/529 cooldown, fallback and local cost estimation. Do not equate UI opt-in with server adoption.

For usage/cost/credits/limits, separate token accounting, local dollar estimates, response-header quota state, usage API state, warning windows, wrap-up/checkpoint prompts, credit flows and auto-resume. Record identity/generation guards, reset scheduling, stale and rearm caps, cancellation events, and the exact synthetic continuation message; do not imply it replays a completed tool action.

For project/data lifecycle, trace purge ownership discovery, transcript/history/prompt rewrites, import mapping, preview digests, ZIP/JSON size and path guards, no-overwrite behavior, manifest verification, sequential side effects and recovery. A preview or digest prevents drift; it does not create an atomic transaction.

For sandbox and network analysis, keep host installation separate from per-command enforcement, and test tool-result/external-state outcomes rather than trusting the CLI process exit alone. Trace every transport's proxy adapter and NO_PROXY matcher, proxy-auth refresh, CA composition, mTLS pair validation/reload, CCR CONNECT relay and unsupported clients. One successful transport cannot prove all transports.

For Active Goal and background model tasks, trace Stop-hook registration, evaluation timing, re-entry and blocking caps, background-task detach/special termination, then separately classify Auto Dream, Away Summary, Post-turn Summary, Prompt Suggestion and Feedback Draft by owner, transcript/cache flags, persistence, user consent, token cost and privacy. Only mechanisms with a verified write consumer may be called persistent memory.

For Advisor, prove whether the implementation is a local loop, client tool or server tool. Trace model-rank eligibility, request-time recomputation across fallback attempts, request schema, stream blocks, wire-view stripping, 400 retry, token/context/latency effects and server-side boundaries.

For Ultrareview, distinguish local review, cloud review and ordinary code-review commands. Trace identity/policy/Git scope gates, merge-base and diff caps, preflight/quota/price, cloud session resources, event polling, recovery, local fix handoff, post consent, posting routine permissions, timeout ambiguity and irreversible remote comments.

## Exhaustive source inventory

`scripts/extract_source_inventory.py` is the deterministic cross-version source-surface extractor. It must read only the canonical packed bundle and emit `analysis/source-inventory/` plus a summary containing:

- canonical source size/hash;
- explicit extraction-method boundaries;
- count per category;
- path, line count, size, and SHA-256 for every generated file.

The current inventory contract uses vendored Acorn 8.15.0 with `ecmaVersion=latest`. Before parsing callsites, it must discover release-local minified symbols from stable semantic anchors: the exported `logEvent`/`logEventAsync` pair, the OTEL `claude_code.${event}` envelope, cached feature/dynamic-config export names, the diagnostic logger body, `CLAUDE_INTERNAL_FC_OVERRIDES`, typed environment-builder joins, `strictPolicyHelperKeys` plus `$schema`, the hand-maintained model-catalog note, and Datadog field anchors. Store those short symbols in `summary.json` as version evidence, but use stable roles such as `firstPartyEvent`, `otelStructuredEvent`, `featureValue`, and `dynamicConfig` in `comparisonKey`/`comparisonValue`. Never carry a minified name from one release into another.

After discovery, record every AST callsite for those semantic roles plus `Error`, `TypeError`, and `RangeError`; lexical function scope and nearest resolvable assignment; all arguments; static, template, conditional, identifier, member/call, and unresolved name expressions; payload properties, computed keys, shorthand, recursively resolvable spreads, and unresolved spreads; every quoted string and template occurrence; every static and dynamic environment access; typed environment builders/defaults; the complete root settings object; and the complete baked model catalog, pricing, aliases, and metadata.

Every JSONL row must carry `comparisonKey` and `comparisonValue`. The comparison value excludes location-only fields but preserves the semantic expression, payload, schema, or catalog value. Long, credential-shaped, or user-home-shaped values retain length, SHA-256, and locations without duplicating their content outside canonical evidence.

The validator must regenerate the entire directory to a temporary location and compare exact bytes. A passing check requires the committed summary, file set, counts, hashes, canonical source hash, Acorn version, semantic-role/symbol mapping, JSONL comparison fields, target-callsite totals, and completion audit to match regeneration. `completionAudit` must confirm all target callsites and lexical literals are recorded, dynamic expressions are retained, settings keys match structured rows, environment/settings/model/Datadog surfaces are nonempty when their stable anchors are detected, and `knownStaticExtractionGaps` is empty. Negative tests must corrupt at least one discovered symbol and empty at least one detected structured inventory, prove rejection, and restore the original hashes.

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
