# Reader-first visual explanation

Use this reference for a mechanism that is important, stateful, version-sensitive, or difficult to understand from a field inventory. It converts source analysis into a teaching artifact without weakening evidence standards.

Keep two jobs separate: evidence determines what may be claimed; teaching determines how the reader encounters those claims. Source review, probes, captures, and cross-version checks happen before writing. They guard accuracy, but they do not become the narrative unless the reader explicitly asked for an audit or comparison.

## Output model

Build three progressive layers, but do not expose those layers as fixed headings or labels. `60 秒`, `读者问题`, `一句话模型`, `场景`, and `状态表` are authoring checks, not a Markdown template.

1. **Concrete first pass**: show an input, the relevant starting state, at least one real action/result pair, and the resulting state change. A reader should understand what happened before learning the internal name.
2. **Mechanism depth**: explain the ordered client path, state owner, trigger, gates, success, failure, recovery, and user impact for that same example.
3. **Evidence appendix**: retain version identity, source ranges, probe results, field semantics, public-source boundary, and cross-version delta outside the main reading path.

Do not begin with binary hashes, inventory counts, minified names, a list of every future concept, or a fictional-task synopsis. A paragraph that says an Agent already read files, tried several versions, hit failures, used hooks, compacted, resumed, and recovered has not supplied an example; it has compressed the whole article into unexplained nouns.

## Reader-first anti-regression contract

Machine validation must protect the reading path, not force authors to preserve a fixed paragraph template. Parse Markdown into headings and block types (`prose`, `table`, `list`, `code`, `image`, `details`) and validate their order and density. Do not accept a bag of required phrases as a substitute for prose structure.

- A tutorial begins with enough concrete state for the first action and result to make sense. Do not open with a taxonomy, a five-column state table, a list of mechanisms, or a context-free sentence such as “the task has already failed twice.”
- Keep baseline architecture and target-release delta explicitly separate. A version article may lead with the delta judgment, but it must perform a clear scope switch to baseline architecture before the mechanism chapters; the delta must not be presented as the definition of the whole architecture.
- Follow one complete example through the core chapters. The example must show the user's actual request, relevant input/file/message data, the first action, the literal or faithfully simplified result, and the next state. A mere checklist of facts that supposedly happened is not an example.
- Core chapters appear in causal order. Each starts with prose, teaches the ordinary path before failure/retry/optimization, and ends by explaining the engineering choice or transition to the next owner.
- A chapter must contain a concrete tension, the client's design choice, and both benefit and cost. These ideas may be written naturally; do not require visible `Question:`, `Conflict:`, or other mechanical labels.
- Tables summarize a model already introduced in prose. They do not open or close a core chapter, and a chapter cannot consist mainly of tables or bullet lists. Long matrices and enumerations move to a deep topic, collapsed appendix, or machine index.
- Keep source locators local to the claim they support, but avoid link walls. A prose paragraph should carry at most two source locators; additional ranges belong in a short evidence strip or footnotes.
- Counts, filenames, fields, and symbols are supporting evidence. Consecutive count-led or file-led paragraphs indicate that the article has regressed into an audit ledger.
- The last narrative chapter derives one integrated technical judgment from multiple earlier mechanisms. Reading routes, evidence methods, inventories, and completeness debt follow it as navigation or appendices, not as competing conclusions.

Validator thresholds should be calibrated against block roles rather than total byte length or heading count. Keep exact semantic checks for known implementation traps, but bind them to the relevant chapter and evidence claim instead of requiring long fixed strings.

## Teaching sequence

Use this sequence unless the mechanism genuinely requires a different order. These are reasoning steps, not required visible headings.

1. **Establish the concrete input**: quote or faithfully simplify the user command/request and show any data, file snippet, request body, or current state needed to understand it.
2. **Show the first action and result**: render the actual tool/API/client action and the output or state delta. Do not summarize several unseen attempts as backstory.
3. **Continue the same trace**: show the decision caused by that result. Introduce an internal term only when the reader has just seen the object it names.
4. **Compare before and after**: explain what was replaced, preserved, appended, persisted, or left external. Use a table only if prose and the example have already introduced every row.
5. **Name the mechanism and lifecycle**: now show the complete success path and assign each component one job.
6. **Explain failure and recovery**: use the same trace to show a failed attempt, retry decision, retained/discarded state, terminal failure, and surviving external side effects.
7. **State version and evidence boundaries**: separate target-version behavior, exact Probe observations, public intent, and what remains unproved.

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

## Interactive teaching contract

Use an interactive lab when the mechanism has a state transition a reader can learn by changing an input, policy, failure or recovery condition. Do not force a lab into lookup-oriented references or inventories. For a tutorial, however, prefer at least one reader-controlled transformation over a fixed animation whenever the mechanism admits a faithful local simulation.

The static article remains the source of truth. The lab is a second way to inspect the same causal path, not a replacement for the ordinary explanation, thresholds, field semantics, failure boundaries or evidence. It must remain useful with JavaScript disabled: keep a readable fallback inside the custom element and keep the complete prose and static diagrams after it.

An acceptable lab has all of these properties:

- Reader input materially changes the trace. It must alter concrete tool arguments, message content, branch selection, owned state, virtual files/diff, attachment set or evidence view. Do not silently replace unsupported free text with a default trace; explain which action could not be parsed.
- Each step records the actor, action kind, input/output, before/after state when relevant, external or virtual side effects, evidence class and diagram target. The visible trace follows causal order and lets the reader move forward, backward, seek and pause autoplay.
- Success and failure branches preserve real ownership rules. Permission denial happens before the blocked side effect; a later test failure does not erase an earlier edit; a compact hook block does not write a success Boundary; an Edit path is not described as passing through a Bash OS-command sandbox.
- Every `tool_use` has exactly one same-ID success or error `tool_result` in traces that return control to the loop. If the target release has a different protocol boundary, model that release instead of preserving the old fixture.
- Evidence labels distinguish `Exact-binary probe`, `Static source reconstruction` and `Teaching fixture`. A deterministic browser simulation is not a captured Claude response or a new runtime Probe.
- The default implementation runs entirely in browser memory. It does not call Claude, request an API key, read or modify the reader's workspace, use `eval`, load a third-party runtime CDN, embed an iframe or send the entered task to an external service.
- A shared runtime owns playback, inspection, virtual files, diff, SVG highlighting, keyboard behavior and responsive layout. Scenario modules own only parsing, controls and version-specific trace construction. Reuse that runtime across tutorials instead of shipping one framework per article.
- Load the runtime only on pages containing the lab element. Keep one production bundle under the repository budget, currently `50 KiB` gzip unless the project records and approves a different limit.
- Keyboard shortcuts never override focused links, buttons, form controls, editable content or ARIA interactive controls. Provide visible focus, meaningful labels, stable control dimensions, a reduced-motion path and a fullscreen option when the trace needs more room.
- At 390px, every scenario control must remain wholly inside the lab; a hidden outer overflow with clipped children is a failure even when the page's `scrollWidth` equals its viewport. Wide diagrams and code/diff regions may scroll inside their named region.

Validate the behavior rather than the presence of UI labels. Tests should cover representative input-driven success, denial before mutation, failure after mutation, compact block/no-Boundary, sandbox rejection, state drift and protocol pairing. Browser acceptance must then operate the real generated page in light and dark themes, inspect desktop and 390x844 layouts, emulate reduced motion, prove non-lab pages do not load the runtime, and verify the no-JavaScript fallback remains a light-DOM child hidden after upgrade.

## Explanation contracts

### A complete example

Before the article asks the reader to remember an abstraction, its example must provide:

- the user's concrete request;
- the relevant starting data or source/message fragment;
- the client/model/tool action;
- the result, including an error or state change when relevant;
- the next decision caused by that result.

Examples may simplify payloads, but must say so. Do not call an invented scenario a captured run. Do not spend more explanation on an unrelated demo domain than on the target mechanism itself; when the article is about Claude Code, prefer a Claude Code request/tool/result trace.

### State transformation

After the example has introduced the objects, state which component owns each decision and what it replaces, preserves, appends, persists, or leaves external. Prose is the default. Use a before/after or ownership table only when it reduces complexity rather than satisfying a template.

### Failure and recovery

Explain detection, retry/change, retained state, terminal effect, and whether an external side effect already occurred. A matrix is optional; a well-ordered trace is often easier to read.

Keep source names and fields in a short evidence line after the explanation, not in the opening sentence.

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
3. Replace visible authoring labels such as `读者问题`, `一句话模型`, and `60 秒模型` with natural prose and a complete example.
4. Follow one target-version-valid trace through the ordinary path; do not summarize the whole trace in a “scenario” paragraph.
5. Introduce internal terms after the example first exposes the object. Keep adjacent mechanisms out unless they change this trace.
6. Add one focused diagram with editable source and rendered output after the reader understands its nodes.
7. Leave thresholds, defaults, fields, retry limits, hooks, policy gates, source locations, Probe literal results, and evidence boundaries in the detailed body or collapsed evidence layer.
8. Explain failure/recovery and user impact in causal order instead of turning them into an interview checklist.

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

## No reusable prose skeleton

Do not provide or enforce one Markdown skeleton for every mechanism. A fixed skeleton is useful for an evidence registry and destructive for teaching prose: authors begin filling headings instead of deciding what the reader must see next.

The reusable artifact is the causal contract:

```text
concrete input -> action -> result -> next decision -> named mechanism
               -> state ownership -> failure/recovery -> evidence boundary
```

Tutorials, reference manuals, and machine evidence have different jobs:

- **Tutorials** follow a concrete trace and introduce terms progressively.
- **Reference manuals** optimize for lookup and may open with a navigation table; they do not need a fictional scenario.
- **Machine evidence** optimizes for deterministic regeneration and exact fields; it should be linked as evidence, not presented as a prose article.

## Quality gate

Before publication, verify all answers are yes:

1. Can a reader explain the first action and result before encountering internal terminology?
2. Does the example include a concrete request, starting data, action, result, and next decision?
3. Does every diagram state a conclusion and use action verbs?
4. Are before/after states explicit without requiring a table?
5. Does each component have one clear responsibility?
6. Are success, failure, retry, and terminal states separate?
7. Are token, latency, quality, privacy, security, and recovery effects stated where relevant?
8. Are exact numeric claims bound to the target release?
9. Are public claims separated from target-version static and probe evidence?
10. Are field dumps and inventory counts deferred until after the concrete trace?
11. Are editable diagram sources committed and reproducibly rendered?
12. Has the publishable output passed the repository privacy scan?

If the guide fails questions 1-6, adding more fields, headings, tables, or visible “reader-friendly” labels will not fix it. Rewrite the teaching path first.
