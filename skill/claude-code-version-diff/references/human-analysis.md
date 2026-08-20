# Human analysis contract

Use this reference when writing a version snapshot README, architecture documents, or a cross-version report. The goal is a two-layer archive: deterministic machine evidence plus explanations that a user can understand without reading minified JavaScript or raw JSONL.

## Required human documents

Every full snapshot includes:

```text
analysis/technical-architecture.md
analysis/context-governance-and-caching.md
analysis/inventory-field-guide.md
analysis/telemetry.md
analysis/source-surface.md
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
- a reader can follow one request without opening JSONL;
- context/cache contains real thresholds and a cost example;
- inventory field guide explains unresolved dynamic data honestly;
- telemetry distinguishes first-party, OTEL, Datadog, GrowthBook, error reporting, and local diagnostics;
- risk control distinguishes local execution governance from unobserved server-side abuse scoring;
- every strong claim has a reachable client branch or clearly labeled evidence class;
- no section uses a count table as its only explanation;
- all local paths and credentials pass the snapshot privacy scan.
