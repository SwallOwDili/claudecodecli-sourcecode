# Human analysis contract

Use this reference when writing a version snapshot README, architecture documents, or a cross-version report. The goal is a two-layer archive: deterministic machine evidence plus explanations that a user can understand without reading minified JavaScript or raw JSONL.

For mechanisms with multiple phases, state transformations, retries, or version-sensitive behavior, read [reader-first-visual-explanation.md](reader-first-visual-explanation.md) before writing. That reference defines the teaching sequence and visual contract; this file remains the completeness and evidence contract.

## Required human documents

Every full snapshot includes:

```text
analysis/technical-mechanism-atlas.md
analysis/public-claims-validation.md
analysis/technical-architecture.md
analysis/agent-loop.md
analysis/context-governance-and-caching.md
analysis/sessions-checkpoints-memory.md
analysis/tools-permissions-hooks.md
analysis/mcp-agents-background.md
analysis/resilience-and-recovery.md
analysis/models-auth-providers-request.md
analysis/settings-feature-flags-policy.md
analysis/tui-ide-remote-cloud.md
analysis/install-update-doctor-lifecycle.md
analysis/native-bridge-runtime.md
analysis/inventory-field-guide.md
analysis/telemetry.md
analysis/source-surface.md
analysis/mechanism-evidence.jsonl
analysis/public-sources/manifest.json
analysis/public-source-excerpts.md
analysis/runtime-probe-index.md
analysis/runtime-probes/*.json
```

README routes readers into these documents and keeps hashes/counts secondary.

## Mechanism template

For each important mechanism, answer in this order:

1. **Purpose**: the concrete user/runtime problem it solves.
2. **Owned state**: messages, cache entry, tool schema, transcript, permission, queue, model config, native object, or other state.
3. **Entry point**: command, setting, environment variable, request field, hook, protocol frame, or automatic trigger.
4. **Call chain**: the ordered client path from input through state change and observable output.
5. **Gates and precedence**: provider/model/auth/query source/feature/policy checks, including dead or shadowed branches.
6. **Defaults and thresholds**: exact units, ranges, caps, reservations, TTLs, queue sizes, timeouts, and retry limits.
7. **Success state**: fields/messages/files/request changes produced on success.
8. **Failure state**: status-specific retry, strip, fallback, fail-closed, persistence, and user message.
9. **Invalidation/lifecycle**: what makes cached or persisted state stale and how long it survives.
10. **User impact**: quality, latency, cost, privacy, security, recoverability, and operational behavior.
11. **Evidence**: readable-source locator, structured inventory row/category, CLI text, runtime probe, or upstream note.
12. **Boundary**: what remains server-side, runtime-only, removed before shipping, or compatible rather than original.

Do not replace these answers with counts, identifier lists, or field dumps.

Do not present all twelve answers at the same visual level. Start with the user problem and one complete lifecycle, then reveal thresholds, branches, fields, and evidence progressively. A technically complete chapter that does not give the reader a stable mental model is incomplete as human documentation.

Verification is an authoring discipline, not the default storyline. Unless the user requested a review or comparison, the main chapter explains the target mechanism directly; source disputes, rejected hypotheses, and research detours stay out of the reader path.

## Public research and target-version validation

Before writing the mechanism layer, search current first-party Claude Code/Agent SDK documentation and relevant Anthropic Engineering articles. Public material is a source of design intent and verification hypotheses, not automatic target-version evidence.

Create `analysis/public-claims-validation.md` and record:

- retrieval date and first-party URL;
- a short, non-copied statement of each public claim;
- the concrete target-version object to search: CLI surface, stable key, state field, default, threshold, error, request field, or ordered call path;
- target-version static evidence and reachability;
- exact-version runtime probe command, controlled input, literal result, and exit status when practical;
- an explicit boundary for current-doc-only, server-side, remote-config, platform-specific, or untriggered behavior.

Use the labels `Public`, `Static`, `Probe`, and `Boundary`. Never use a current documentation page to fill an implementation gap in an old branch, and never infer implementation solely from a release-note sentence or lexical hit.

Public research must be reproducible enough to detect documentation drift. Store HTTP status, response-body byte length, raw-body SHA-256, normalized visible-text SHA-256, per-excerpt SHA-256, per-excerpt source-presence verification, retrieval timestamp, URL, and excerpt IDs in `analysis/public-sources/manifest.json`. Store the short passages actually used to form hypotheses in `analysis/public-source-excerpts.md`, and require every normalized quoted line to occur in the captured visible page text. Every official Anthropic URL cited in snapshot Markdown must have a manifest record. A URL alone is not a stable research record, and an HTML hash alone is not readable evidence.

## Structured mechanism evidence

Every strong mechanism claim must have one unique row in `analysis/mechanism-evidence.jsonl`. Human prose explains the mechanism; this registry lets the validator and comparator recheck what the prose relies on.

Set validator-enforced minimums for every core topic and a nontrivial total claim floor. A long chapter with zero registered claims is incomplete, even when the prose is accurate; a large inventory is not a substitute for mechanism evidence.

- `Static` rows name the exact source view and path, a real line range within that file, and anchors that occur inside the range. They must also classify `staticEvidenceKind` as `runtime`, `constant`, `consumer`, `surface`, or `declaration`. `surface` and `declaration` prove only a registered command, schema/help contract, or user-facing message and must state `evidenceLimitation`; they cannot silently stand in for an executed branch. Use `extracted/cli.js` only for canonical packed line numbers and `reverse/javascript/cli.readable.js` only for readable-view line numbers. Never attach a readable-view six-digit line number to the one-line packed bundle.
- `Probe` rows point to a committed normalized report and identify fields containing the exact command, controlled input, literal output, exit status, and required checks. Prefer successful state transitions. Empty lists, validation errors, missing-session errors, and command help prove only their narrow command/error surface.
- `Public` rows resolve both a source ID in the public manifest and an excerpt ID in the excerpt file.
- `Boundary` rows state why the claim cannot be recovered from the shipped client.

At least one exact-binary positive probe must exercise the central Agent Loop contract when the release can be isolated: advertise a real tool schema, receive a complete `tool_use`, execute a reversible tool, observe a paired `tool_result` in the next Messages request, reach a success result, then resume the created session and prove history injection. Record the target binary SHA-256. A mock Messages endpoint is acceptable because the object under test is the client loop; the report must state that it does not prove model quality or server-side behavior.

Maintain `analysis/runtime-probe-index.md` as the human bridge over normalized reports. It must explain report field semantics, list every `Probe` claim ID exactly once or more, translate command/input/literal output/exit status into a state transition, and state the narrow boundary of each probe family. The validator must reject an unindexed Probe claim.

## Mechanism atlas

`analysis/technical-mechanism-atlas.md` is the first human reading route. It must:

- show one complete request from input/session through context assembly, model stream, tool control, result feedback, persistence, collaboration, recovery, and observability;
- distinguish the reasoning/execution loop, context-control loop, and control/recovery loop;
- name which state is process-local, session-persistent, or external;
- map each mechanism to its user symptom and deep topic;
- include one concrete end-to-end task crossing all major layers;
- explain the evidence hierarchy and current-document version-drift rule.

## Agent Loop chapter

Trace one complete execution turn through the actual loop entrypoints and state object. Distinguish user turn, model/agent iteration, API attempt, and tool batch. Cover:

- the outer lifecycle wrapper, optional observer tap, and core loop generator;
- loop-carried messages, tool context, turn count, compact tracking, recovery counters, Stop hook state, pending summaries, and transition reasons;
- queue absorption before the first request and between tool batches, including fail-without-drop behavior;
- the exact stream event at which a complete `tool_use` becomes executable;
- streaming model/tool interleaving and progress delivery;
- per-input concurrency-safe classification, unsafe ordering barriers, drain behavior, and result pairing by `tool_use_id`;
- tool lookup, parse/coercion/schema, custom validation, PreToolUse, permission/policy/classifier, updated-input validation, call, PostToolUse, output validation, and error mapping;
- normal completion, tool end-turn, hook stop/defer, Stop hook blocking re-entry, default/overridden caps, and max-turn accounting;
- prompt-too-long/reactive compact, max-output recovery, malformed tool retry, thinking-only nudge, transport retry, model/refusal/server fallback, abort, and terminal reasons;
- main/sub/background Agent reuse of the loop with model/tool/permission/worktree/transcript isolation;
- the boundary that tombstones and abort signals restore message consistency but do not roll back completed external side effects.

Include at least one concrete multi-tool timeline showing which calls overlap, which form barriers, when queued user input enters, and what `maxTurns=1` does after tool execution.

## Context and cache chapter

Trace one main-thread request end to end:

```text
input/resume
-> transcript/message graph
-> system prompt sections
-> user/system context
-> tools/agents/skills/MCP
-> schema deferral
-> normalization
-> cache segmentation and breakpoints
-> request body
-> response/tool loop
-> usage/transcript/telemetry
-> microcompact/compact/resume
```

Explain separately:

- process-local memoization versus API prompt cache;
- stable/global and org/dynamic system blocks;
- user/assistant/api-system message markers and fork pins;
- prompt-cache family disable switches and 5m/1h eligibility;
- tool search as context deferral, not an API response cache;
- context hint request conditions and status-specific fallbacks;
- local tool-result cleanup threshold, keep-recent count, persistence, and placeholders;
- auto-compact window-source precedence and model cap;
- output reservation, precompute, warn, compact, and blocked lines;
- PreCompact hooks, precomputed summary persistence/rehydration, and failure behavior;
- compact boundary metadata, JSONL parent repair, resume, and memory;
- settings/environment variables that exist but cannot activate a reachable branch.

Include at least:

- one concrete threshold calculation for a baked model window;
- one prompt-cache dollar calculation using baked input/write/read prices;
- one table distinguishing cache, deferral, compaction, transcript, and memory.

## Sessions, checkpoints, and memory chapter

Trace separately:

- session ID lookup and invalid/missing-session errors;
- message UUID, parent, logical parent, branch leaf, fork, and tombstone semantics;
- JSONL physical event order versus the logical message view sent to the model;
- transcript persistence/retention versus prompt cache and auto-memory;
- compact boundary fields, preserved messages/segments, and resume graph repair;
- file checkpoint enablement, exact cap, pruning, dry-run diff, restore, link/error handling, and conversation-versus-file rewind;
- `CLAUDE.md`, auto-memory, `MEMORY.md`, and compact summary roles and budgets;
- process state, durable task state, and external side effects that resume cannot restore.

Include a recovery matrix and at least one user-facing diagnosis for resume, rewind, retention, and memory growth.

## Tools, permissions, and hooks chapter

Trace the exact ordered path from tool name/raw input through alias lookup, parse/coercion, input schema, custom validation, PreToolUse, permission/policy/classifier, updated-input revalidation, runtime sandbox, call, result mapping, PostToolUse/PostToolUseFailure, output validation, PostToolBatch, and result/context persistence.

Explain:

- every target-version permission mode and its enabling gate;
- rule and managed-policy precedence, decision source/reason, ask/deny/fail-closed behavior;
- hook event timing, concurrency, blocking, defer, input/output mutation, timeout/error, and Stop-hook cap;
- filesystem/network/socket/domain/credential sandbox dimensions and unavailable-sandbox fallback;
- workspace/MCP/plugin/helper trust boundaries;
- why a post-action hook or tombstone cannot undo a completed side effect.

Include a failure matrix that states whether `tool.call` occurred and what the next model turn observes.

## MCP, agents, and background chapter

Trace:

- MCP config sources, workspace trust, strict/managed filters, transport/auth, capability listing, connection state, generation refresh, and error recovery;
- Tool Search enable/disable reasons, `defer_loading`, discovery, schema residency, generation-bound cache, and invalidation;
- subagent messages/tools/model/effort/maxTurns/permission/abort/worktree/transcript isolation and exact defaults;
- parent tool-use/result/progress mapping and permission bubbling;
- foreground tool batch versus background/durable task lifecycle;
- task registry, atomic claim/owner/status/dependency behavior;
- team mailbox sender/recipient/broadcast/ack/size/redelivery/shutdown behavior;
- worktree benefits and shared-resource limitations;
- token, latency, model, coordination, and duplicated-work cost.

Include one complete orchestrator-worker timeline and explain when multi-agent work is a poor fit.

## Resilience and recovery chapter

Separate at least these recovery layers:

- HTTP/API retry and status/provider classification;
- streaming watchdog, partial block boundaries, and non-stream fallback;
- model/refusal/server fallback, consent/allowlist, tombstone, abort, and usage identity;
- max-output continuation, malformed-tool retry, thinking-only nudge, and their independent counters;
- precompute/reactive compact and bounded retry;
- tool errors as result feedback versus transparent tool retry;
- hook errors and Stop-hook re-entry/circuit breaking;
- MCP reconnect plus tool-generation/schema-cache refresh;
- transcript resume, checkpoint/rewind, and durable versus process-only background state;
- typed terminal reasons and SDK/exit-code mapping.

For every recovery path, say what is retried, what state is retained, what is discarded, whether tools can repeat, and which external side effects survive. Include one failure chain where a local file change is recoverable but a remote action is not.

## Models, authentication, providers, and request chapter

Trace provider selection precedence, model alias/catalog resolution, credential-source precedence, OAuth/API-key/cloud credential paths, custom base-URL and first-party-host gates, beta/header construction, Messages request fields, streaming selection, and error identity. Explain which model facts are baked into the client and which come from remote config or the service. Include a field-level request example with content redacted but shape preserved.

## Settings, feature flags, and managed policy chapter

Trace user, project, local, CLI/flag, and managed-policy sources separately. For important settings, state merge semantics rather than only source order: scalar replacement, map merge, list concatenation/deduplication, deletion/reset behavior, invalid-value fallback, and managed-only restrictions. Show how remote feature evaluation, environment overrides, and enterprise policy gates enter reachable branches. Do not treat the presence of an environment name as proof that it wins or is reachable.

## TUI, IDE, remote control, and cloud chapter

Separate local TUI/print/SDK modes, IDE discovery and bidirectional context, local socket or protocol ownership, Remote Control reconnect and attachment lifecycle, and cloud/teleport session ownership. Explain where input, rendering, files, approval state, and transcripts live; what survives disconnect; what is retransmitted; and which behavior depends on remote services. Include reconnect limits and user-visible failure states when recoverable.

## Install, update, doctor, and release lifecycle chapter

Trace the resolved real version file rather than trusting a launcher. Record version, size, hash, architecture, signature, install shape, migrations, auto-update/check gates, doctor fault domains, native-module release matching, and rollback compatibility. Distinguish disabling automatic installation, disabling checks/traffic, hiding commands, and externally managed deployment. State that binary rollback does not automatically downgrade settings or transcript schemas.

## Native bridge runtime chapter

Join each JavaScript consumer to its N-API export/object/prototype contract, language/dependency evidence, Mach-O slices/frameworks, resource lifetime, error mapping, permission/TCC boundary, and external side effects. Compare original and compatible modules on the same controlled inputs, but retain `Observed`, `Derived`, and `Compatible` labels. A matching export count is insufficient; cover arguments, nullability, return fields, sync/Promise/callback form, disposal, threads, and architecture coverage.

Emit a normalized native behavior report under `analysis/runtime-probes/`. Record every check, module, comparison mode, controlled input strategy, literal PASS/FAIL, original-versus-compatible label, and architecture method. Distinguish release-module static slices from architectures actually built and executed.

## Field guide

Explain how to read every JSONL family, not every row in prose. Cover:

- `comparisonKey` and `comparisonValue`;
- line/column/offset and source length/hash/text;
- callee/function/functionKind/arguments/nameArgument;
- payload direct/shorthand/computed/expanded keys, spreads, unresolved spreads, and assignment resolution;
- environment schema versus actual access callsites;
- root settings builders, descriptions, enums, default/catch expressions, and scope restrictions;
- model provider IDs, context, output limits, capabilities, aliases, pricing, and effort metadata;
- telemetry identity, request correlation, tokens/cache/cost, latency/retry, tool/permission, and compact fields;
- heuristic files and the need to return to a reachable callsite.

Use one shortened real record per major JSONL family and translate it into a plain-language conclusion. State what the same record cannot prove.

## Telemetry chapter

For each transport, document independently:

- default endpoint/exporter and enable/disable gates;
- queue layers, sampling, batching, flush, timeout, persistence, retry/backoff, and auth fallback;
- envelope/resource fields versus event-specific fields;
- content controls, redaction, truncation, and secret scrubbing;
- provider restrictions and allowlists;
- network paths versus local-only logs/profiles/traces;
- current reachability and remote-config boundaries.

Do not apply one transport's redaction list or defaults to another transport.

## Cross-version writing

For every material change, use this comparison block:

```text
Change:
Old path/state:
New path/state:
Trigger and precedence:
Failure/fallback difference:
User impact:
Cost/latency/privacy/security impact:
Evidence:
Confidence/boundary:
```

Group related fields into a mechanism. A new telemetry event alone is an observability change until a reachable product-state change is also proven. A minified symbol/hash/address change alone is not a feature change.

## Quality checks

Before publication, verify:

- README first screen links all human documents;
- the mechanism atlas links every deep topic and lets a reader choose by user problem;
- public research has retrieval dates and clearly separates `Public`, `Static`, `Probe`, and `Boundary` evidence;
- public sources have status, byte length, raw and semantic SHA-256, excerpt hashes, and readable fixed excerpts;
- every official Anthropic URL cited in Markdown is registered in the public manifest;
- every mechanism evidence row has a unique claim ID and valid source/probe/public/boundary shape, and every core topic meets its minimum;
- readable-JavaScript line numbers point to `reverse/javascript/cli.readable.js`, while canonical line numbers point to `extracted/cli.js`;
- the Agent Loop positive probe proves real tool execution, paired result feedback, success, and successful resume on the exact binary hash;
- a reader can follow one request without opening JSONL;
- Agent Loop explains streaming tool start, concurrency barriers, permission order, result feedback, max turns, Stop hook re-entry, fallback side effects, and every terminal class;
- context/cache contains real thresholds and a cost example;
- sessions/checkpoints/memory distinguishes message graph, transcript, file history, prompt cache, memory, process state, and external state;
- tools/permissions/hooks states the exact execution order, mode set, fail-closed paths, and whether a failed layer called the tool;
- MCP/agents/background explains generation refresh, deferred schema, child isolation, task/mailbox state, durability, and coordination cost;
- resilience/recovery distinguishes every retry/fallback counter and states which side effects remain;
- models/auth/providers/request explains selector and credential precedence plus the actual Messages request shape;
- settings/feature flags/policy explains per-field merge semantics and managed-only gates;
- TUI/IDE/remote/cloud distinguishes local state from remote ownership and reconnect behavior;
- install/update/doctor distinguishes launcher, immutable version file, migration, update gates, and rollback compatibility;
- native bridge analysis joins JavaScript consumers to N-API contracts, lifetimes, side effects, and architecture limits, with a machine report separating arm64 runtime coverage from x86_64 static-only evidence;
- inventory field guide explains unresolved dynamic data honestly;
- telemetry distinguishes first-party, OTEL, Datadog, GrowthBook, error reporting, and local diagnostics;
- risk control distinguishes local execution governance from unobserved server-side abuse scoring;
- every strong claim has a reachable client branch or clearly labeled evidence class;
- no section uses a count table as its only explanation;
- all local paths and credentials pass the snapshot privacy scan.
