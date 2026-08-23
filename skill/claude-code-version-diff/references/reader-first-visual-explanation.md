# Reader-first visual explanation

Use this reference for a mechanism that is important, stateful, version-sensitive, or difficult to understand from a field inventory. It converts source analysis into a teaching artifact without weakening evidence standards.

Keep two jobs separate: evidence determines what may be claimed; teaching determines how the reader encounters those claims. Source review, probes, captures, and cross-version checks happen before writing. They guard accuracy, but they do not become the narrative unless the reader explicitly asked for an audit or comparison.

## Output model

Build three progressive layers. A reader should be able to stop after any layer and retain a correct, explicitly bounded model.

1. **60-second model**: one user problem, one-sentence conclusion, one lifecycle image, and one before/after state change.
2. **10-minute mechanism**: ordered phases, owned state, trigger and gates, success path, failure path, recovery, and user impact.
3. **Evidence appendix**: version identity, source ranges, probe results, field semantics, public-source boundary, and cross-version delta.

Do not begin with binary hashes, inventory counts, minified names, or a wall of configuration fields. Those belong in layer three.

## Teaching sequence

Use this sequence unless the mechanism genuinely requires a different order:

1. **Reader question**: phrase the concrete symptom or task in the user's language.
2. **Version badge**: name the exact release and evidence class without interrupting the opening explanation. State whether the guide describes a static path, an exact-binary observation, current public behavior, or a boundary.
3. **Scenario**: choose one realistic input and follow it through the system. Reuse the same scenario instead of changing examples between sections.
4. **Before and after**: show which state is replaced, preserved, appended, persisted, or external. Use concrete but version-valid values only.
5. **Main lifecycle**: show the success path from entrypoint to observable result before explaining internal branches.
6. **Layered explanation**: assign each component one job. Explain why each layer exists and what would break without it.
7. **Failure and recovery**: show the first failed attempt, retry decision, retained/discarded state, terminal failure, and surviving external side effects.
8. **Version delta and evidence**: separate observed target-version behavior from current documentation and from nearby releases.

The governing narrative is always:

```text
problem -> trigger -> state transition -> observable result -> why -> failure/recovery -> evidence -> version boundary
```

Teach one ordinary success path completely before introducing automatic triggers, precomputation, retries, fallback, or exceptional states. A reader who has not yet seen the basic state transition cannot usefully distinguish its recovery branches.

## Visual contract

Every image must answer one question. Do not create decorative architecture posters.

- Keep a main diagram to roughly 5-9 nodes. Split success, rebuilt state, and failure paths into separate images when needed.
- Put verbs on arrows: `summarizes`, `preserves`, `restores`, `blocks`, `retries`, `persists`. A line without a state-changing verb hides the mechanism.
- Name domain objects in nodes: message graph, summary, tool batch, boundary, hook result, cache entry. Avoid minified identifiers in the teaching layer.
- Use a stable semantic palette across guides: input/action, model/computation, durable state, restored context, and failure/retry must be distinguishable without relying on hue alone.
- Give every rendered SVG/PNG meaningful alt text and a short caption stating the conclusion.
- Retain an editable `.dot`, `.mmd`, or equivalent source beside every generated image. Use deterministic rendering and commit both source and output.
- A screenshot may prove an observed UI or request, but it must not be the only explanation. Annotate the significant field and bind it to a version.
- Do not embed machine-local absolute paths, usernames, credentials, request IDs, or private session content in publishable visuals.

## Required explanation blocks

### One-sentence mental model

Use a sentence with an owned object and a state change:

> The client replaces a long message representation with a summary, a valid recent suffix, restored exact context, and a persistent boundary so the next model call can continue with fewer tokens.

Avoid labels that merely rename the feature, such as "compaction compresses context."

### Before/after table

Use five columns:

| Object | Before | Transformation | After | User-visible effect |
| --- | --- | --- | --- | --- |

This forces the guide to distinguish deletion, summarization, preservation, rehydration, and persistence.

### Phase cards

For every phase, answer in prose:

- what enters;
- which component owns the decision;
- what state changes;
- what the next phase receives;
- what the reader can observe.

Keep source names and fields in a short evidence line after the explanation, not in the opening sentence.

### Failure matrix

Use these columns:

| Failure | Detection | Retry/change | State retained | Final user effect |
| --- | --- | --- | --- | --- |

For an agentic path, also state whether any tool or external side effect already occurred.

### Version matrix

Include a version matrix only when the user requested a comparison or the deliverable itself is a version-comparison report. A standalone guide stays focused on the target mechanism.

When a comparison is in scope, use:

| Claim | Observed version | Target version | Status | Evidence |
| --- | --- | --- | --- | --- |

Use `same`, `changed`, `not proven`, or `server-side boundary`. Never silently carry a numeric threshold or request field from one release into another.

## Writing rules

- Lead with conclusions and causal verbs, not nouns and categories.
- Translate every important field into what changes in runtime behavior.
- Explain redundancy as a reliability decision: identify which information channel is lossy and which exact channel compensates for it.
- Distinguish a user turn, model iteration, API attempt, retry, tool batch, persisted event, and restored view.
- Use examples to illuminate a verified rule, never to invent one.
- Keep research scaffolding in the evidence appendix. The main narrative should read like a direct explanation of the mechanism, not a diary of how the author verified it.
- Place exact line references and claim IDs near the conclusion they support, then collect full evidence in the appendix.
- Label interpretations as interpretations. A subjective description such as "patchwork" may summarize complexity, but it cannot replace the state ownership and failure analysis.

## Optimizing an existing technical archive

An archive refresh is not a summarization pass. Treat the existing mechanism prose, field dictionaries, thresholds, source ranges, Probe results, failure matrices, evidence IDs, and boundaries as the evidence layer. Improve the order in which the reader encounters them.

For every core human topic:

1. Keep the original detailed sections unless a claim is disproved or duplicated verbatim.
2. Add a first-screen teaching block before research history, inventory counts, or minified call chains.
3. Use exactly one reader question and one owned-state mental model.
4. Follow one target-version-valid scenario through the ordinary success path.
5. Add a state transition or ownership table that makes replacement, preservation, persistence, and external side effects explicit.
6. Add one focused diagram with editable source and rendered output.
7. Leave thresholds, defaults, fields, retry limits, hooks, policy gates, source locations, Probe literal results, and evidence boundaries in the detailed body.
8. Link failure/recovery and user impact from the teaching block instead of pretending the happy path is the whole mechanism.

The refresh is incomplete if readability improves by deleting details that a debugger, implementer, auditor, or cross-version comparator still needs.

## Product-surface overview contract

A product-surface overview is not the place to display how much extraction work was performed. It must synthesize how the product behaves as a system.

- Use one governing thesis and one end-to-end scenario. Do not make readers simultaneously memorize several competing taxonomies such as worlds, planes, contradictions, feature groups and evidence axes.
- Give every major chapter one technical claim that could support a 10-15 minute explanation. A chapter that only names fields, files, routes or counts is still an inventory entry.
- The normal sequence is `user symptom -> owned state -> ordinary path -> design reason -> failure/recovery -> user impact -> evidence boundary`.
- Connect settings/trust/provider capability compilation, Agent Loop, execution control, context, persistence, extensions, remote uncertainty, observability and native boundaries when the release ships those surfaces. Do not select only the mechanisms that already have convenient tables.
- Put exact inventory ordering, canonical hashes, claim counts and unresolved-work counts in a separate generated machine index. Link that index from the article; do not embed its full table in the reader narrative, even under a collapsed block.
- Keep numbers in the article only when they change a runtime decision, budget, timeout, threshold or user-visible result. Numbers that measure analyst output belong in the audit/index.
- A validator should test semantic chapter contracts, evidence bindings and generated machine blocks. Avoid making prose authors preserve obsolete fixed headings or sentences solely to satisfy a fixture.

The overview fails this contract when its sentences are governed mainly by filenames and counts, even if every number is correct.

## Reusable Markdown skeleton

```markdown
# Mechanism name: the user question it answers

> Version: X | Evidence: Static / Probe / Public / Boundary

One-sentence mental model.

![Lifecycle conclusion](visuals/mechanism-lifecycle.svg)

## What changes

Before/after table.

## One real scenario

Input and observable result.

## Phase 1 ...

Purpose, owner, state change, output, evidence.

## Failure and recovery

Failure diagram and matrix.

## Cost, latency, quality, privacy and recovery impact

## Version differences

Version matrix.

## Evidence appendix

Claim IDs, source ranges, probe commands/results, and boundaries.
```

## Quality gate

Before publication, verify all answers are yes:

1. Can a reader explain the mechanism after the first image without reading source code?
2. Does the guide use one scenario from trigger through result?
3. Does every diagram state a conclusion and use action verbs?
4. Are before/after states explicit?
5. Does each component have one clear responsibility?
6. Are success, failure, retry, and terminal states separate?
7. Are token, latency, quality, privacy, security, and recovery effects stated where relevant?
8. Are exact numeric claims bound to the target release?
9. Are public claims separated from target-version static and probe evidence?
10. Are field dumps and inventory counts deferred until after the mental model?
11. Are editable diagram sources committed and reproducibly rendered?
12. Has the publishable output passed the repository privacy scan?

If the guide fails questions 1-6, adding more fields will not fix it. Rewrite the teaching path first.
