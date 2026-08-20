# Deep reverse artifacts

This directory contains deterministic analysis artifacts derived from the byte-for-byte files in `../extracted/` and the JSC cache embedded in the installed Claude Code executable.

- `summary.json`: machine-readable top-level facts.
- `manifest.json`: SHA-256 and size of every file below this directory, excluding the manifest itself.
- `bytecode/cli.jsc.gz`: lossless deterministic gzip of the complete JSC bytecode cache.
- `bytecode/strings.txt.gz`: full printable-string view of that bytecode.
- `javascript/cli.readable.js`: esbuild-generated analysis view; not canonical source.
- `index/`: normalized sets intended for version-to-version comparison.
- `native/`: complete static reports for every architecture in every packed `.node` module.

Validate with:

```bash
python3 ../skill/claude-code-version-diff/scripts/validate_deep_reverse.py ..
```

The canonical released JavaScript remains `../extracted/cli.js`. No generated file in this directory represents Anthropic's original TypeScript layout.
