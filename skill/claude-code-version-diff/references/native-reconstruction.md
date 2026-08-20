# Native source reconstruction

Use this mode when the user asks to recover or recreate source corresponding to embedded `.node` modules.

## Evidence order

1. Preserve and hash the original module.
2. Record Mach-O architectures, dependencies, exports, imports, symbols, strings, Objective-C selectors, Swift demangle, and disassembly.
3. Trace every JavaScript call site and argument/result consumer.
4. Load the original module in a disposable Node process and probe stable behavior.
5. Implement in the observed language when the evidence identifies it; otherwise choose the smallest compatible native implementation and state that choice.

Use three labels:

- `Observed`: directly present in the shipped artifact or original runtime output.
- `Derived`: forced or strongly constrained by observed callers and signatures.
- `Compatible`: independently implemented behavior where compiled code no longer preserves the source body.

## Contract first

Store a machine-readable contract covering:

- top-level exports;
- class prototype methods;
- nested object groups and methods;
- sync vs Promise returns;
- `null` vs `undefined`;
- field names and stable error text.

Validate this contract against both the original and reconstructed module before deeper behavior testing.

## Behavior probes

Prefer deterministic and non-destructive cases:

- fixed in-memory image inputs and output hashes;
- timeouts with no external event;
- initial state queries;
- invalid input that fails before keyboard/mouse injection;
- application/display/TCC reads;
- screenshot schema, dimensions, and format rather than consecutive-frame hashes.

Do not invoke app opening, application hiding, key injection, mouse clicks, microphone capture, or permission prompts merely to increase test count. When such behavior is essential, isolate it and restore the prior state.

## Build and load invariant

Build release artifacts, then copy each dynamic library to a newly created directory with its original `.node` name. Never replace a `.node` file that a live Node process may have mapped. On macOS, replacing an in-use Mach-O can leave the process blocked while dyld reads a changed slice.

A reusable script should:

1. format/check/build all native projects;
2. obtain the Swift release binary directory from SwiftPM;
3. create a unique test directory with `mktemp`;
4. copy artifacts without overwriting an earlier test directory;
5. validate original and reconstructed contracts;
6. run paired behavior probes;
7. print the unique artifact directory.

## Documentation

For each module, record:

- observed language, dependency versions, architecture slices, APIs and system frameworks;
- exact behavior confirmed by probes;
- derived implementation decisions;
- compatible internals that cannot be recovered exactly;
- build/test status and untested architecture or permission paths.

Keep the original binary and packed `.node` hashes as the permanent evidence baseline.

## Cross-version comparison

Compare native reconstruction only after comparing the shipped modules. Report separately:

- original `.node` hash/size/architecture/dependency/import/export/symbol changes;
- contract additions/removals;
- reconstructed source file additions/removals and line churn;
- dependency or toolchain changes;
- behavior probes that newly pass, fail, or change output.

A source reconstruction change without a corresponding shipped-module change is maintenance churn, not product evidence.
