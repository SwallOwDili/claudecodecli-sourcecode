#!/usr/bin/env python3
"""Build deterministic deep-reverse artifacts for a Claude Code snapshot."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


ENV_RE = re.compile(rb"\b(?:ANTHROPIC|CLAUDE_CODE)_[A-Z][A-Z0-9_]{2,}\b")
FEATURE_RE = re.compile(rb"\bENABLE_[A-Z][A-Z0-9_]{2,}\b")
URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
CONFIG_RE = re.compile(
    rb"[\"']([a-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*){1,5})[\"']"
)
SOURCE_PATH_RE = re.compile(
    rb"(?:/" + rb"Users/runner/work/[A-Za-z0-9_./@+~-]+|"
    rb"(?:packages|src|crates)/[A-Za-z0-9_./@+~-]+)"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_lines(path: Path, values: set[str] | list[str]) -> None:
    ordered = sorted(set(values))
    write_text(path, "".join(f"{value}\n" for value in ordered))


def extract_urls(source: bytes) -> set[str]:
    return {
        match.decode("utf-8", errors="ignore").rstrip(".,;)'\"")
        for match in URL_RE.findall(source)
    }


def gzip_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0, compresslevel=9) as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)


def gzip_bytes(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0, compresslevel=9) as output_handle:
            output_handle.write(data)


def normalized_command(command: list[str], replacements: dict[str, str]) -> str:
    rendered = " ".join(command)
    for source, target in replacements.items():
        rendered = rendered.replace(source, target)
    return rendered


def capture(command: list[str], replacements: dict[str, str]) -> bytes:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = process.stdout.decode("utf-8", errors="replace")
    for source, target in replacements.items():
        output = output.replace(source, target)
    header = (
        f"command: {normalized_command(command, replacements)}\n"
        f"exitStatus: {process.returncode}\n"
        "--- output ---\n"
    )
    return (header + output).encode("utf-8")


def tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"required tool is unavailable: {name}")
    return resolved


def architectures(path: Path) -> list[str]:
    process = subprocess.run(
        [tool("lipo"), "-archs", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode == 0:
        return process.stdout.strip().split()
    description = subprocess.check_output([tool("file"), str(path)], text=True)
    if "arm64" in description:
        return ["arm64"]
    if "x86_64" in description:
        return ["x86_64"]
    raise RuntimeError(f"cannot determine architecture for {path}")


def inventory(source: bytes, output: Path) -> dict[str, object]:
    environment = {item.decode("ascii") for item in ENV_RE.findall(source)}
    features = {item.decode("ascii") for item in FEATURE_RE.findall(source)}
    urls = extract_urls(source)
    hosts: set[str] = set()
    for value in urls:
        try:
            host = urlparse(value).netloc.lower()
        except ValueError:
            continue
        if host:
            hosts.add(host)

    ignored_suffixes = {
        "cjs", "css", "dylib", "gif", "html", "jpeg", "jpg", "js", "json",
        "map", "md", "mjs", "node", "png", "rs", "svg", "swift", "ts", "tsx",
        "txt", "wasm", "xml", "yaml", "yml",
    }
    config = {
        item.decode("utf-8", errors="ignore")
        for item in CONFIG_RE.findall(source)
        if item.rsplit(b".", 1)[-1].decode("ascii", errors="ignore").lower()
        not in ignored_suffixes
    }
    source_paths = {
        item.decode("utf-8", errors="ignore").rstrip(".,;:)'\"")
        for item in SOURCE_PATH_RE.findall(source)
    }

    files = {
        "environment-identifiers.txt": environment,
        "feature-identifiers.txt": features,
        "endpoint-hosts.txt": hosts,
        "urls.txt": urls,
        "probable-config-keys.txt": config,
        "embedded-source-paths.txt": source_paths,
    }
    for name, values in files.items():
        write_lines(output / name, values)

    return {
        "environmentIdentifiers": len(environment),
        "featureIdentifiers": len(features),
        "endpointHosts": len(hosts),
        "urls": len(urls),
        "probableConfigKeys": len(config),
        "embeddedSourcePaths": len(source_paths),
        "configKeyMethod": "quoted dotted identifiers minus common file extensions; heuristic",
    }


def endpoint_hosts(source: bytes) -> set[str]:
    hosts: set[str] = set()
    for item in extract_urls(source):
        try:
            host = urlparse(item).netloc.lower()
        except ValueError:
            continue
        if host:
            hosts.add(host)
    return hosts


def report_output(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        marker = lines.index("--- output ---")
    except ValueError:
        return lines
    return lines[marker + 1 :]


def build_native_index(reverse: Path) -> dict[str, int]:
    architectures_index: set[str] = set()
    dependencies: set[str] = set()
    exports: set[str] = set()
    imports: set[str] = set()
    napi_imports: set[str] = set()
    swift_project_symbols: set[str] = set()

    for module_root in sorted((reverse / "native").glob("*.node")):
        metadata = json.loads((module_root / "metadata.json").read_text(encoding="utf-8"))
        for arch_entry in metadata["architectures"]:
            arch = arch_entry["architecture"]
            prefix = f"{module_root.name} [{arch}]"
            architectures_index.add(f"{prefix}: {metadata['size']} bytes; {metadata['sha256']}")
            arch_root = module_root / arch

            for line in report_output(arch_root / "linked-dylibs.txt"):
                value = line.strip()
                if value.startswith(("/", "@")):
                    dependencies.add(f"{prefix}: {value.split(' (', 1)[0]}")

            for line in report_output(arch_root / "exports.txt"):
                value = line.strip()
                if value:
                    exports.add(f"{prefix}: {value.rsplit(' ', 1)[-1]}")

            for line in report_output(arch_root / "imports.txt"):
                value = line.strip()
                if not value:
                    continue
                imports.add(f"{prefix}: {value}")
                if value.startswith("_napi_"):
                    napi_imports.add(f"{prefix}: {value}")

            for line in (arch_root / "swift-demangled.txt").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if "ComputerUseSwift." in line:
                    swift_project_symbols.add(f"{prefix}: {line.strip()}")

    index = reverse / "index"
    values = {
        "native-architectures.txt": architectures_index,
        "native-dependencies.txt": dependencies,
        "native-exports.txt": exports,
        "native-imports.txt": imports,
        "native-napi-imports.txt": napi_imports,
        "native-swift-project-symbols.txt": swift_project_symbols,
    }
    for name, entries in values.items():
        write_lines(index / name, entries)
    return {
        "nativeArchitectureEntries": len(architectures_index),
        "nativeDependencies": len(dependencies),
        "nativeExports": len(exports),
        "nativeImports": len(imports),
        "nativeNapiImports": len(napi_imports),
        "nativeSwiftProjectSymbols": len(swift_project_symbols),
    }


def build_native(repo: Path, reverse: Path) -> list[dict[str, object]]:
    modules: list[dict[str, object]] = []
    native_root = reverse / "native"
    native_root.mkdir(parents=True, exist_ok=True)
    swift_demangle = subprocess.check_output(
        [tool("xcrun"), "--find", "swift-demangle"], text=True
    ).strip()

    for source in sorted((repo / "extracted").glob("*.node")):
        module_root = native_root / source.name
        module_root.mkdir(parents=True, exist_ok=True)
        relative_source = f"extracted/{source.name}"
        replacements = {str(source): relative_source, str(repo): "."}
        archs = architectures(source)

        general_commands = {
            "file.txt": [tool("file"), str(source)],
            "uuid.txt": [tool("dwarfdump"), "--uuid", str(source)],
            "code-signature.txt": [tool("codesign"), "-dvvv", str(source)],
            "strings.txt.gz": [tool("strings"), "-a", "-n", "5", str(source)],
        }
        for filename, command in general_commands.items():
            data = capture(command, replacements)
            destination = module_root / filename
            if destination.suffix == ".gz":
                gzip_bytes(data, destination)
            else:
                destination.write_bytes(data)

        arch_metadata = []
        for arch in archs:
            arch_root = module_root / arch
            arch_root.mkdir(parents=True, exist_ok=True)
            commands = {
                "mach-header.txt": [tool("otool"), "-arch", arch, "-hv", str(source)],
                "load-commands.txt": [tool("otool"), "-arch", arch, "-l", str(source)],
                "linked-dylibs.txt": [tool("otool"), "-arch", arch, "-L", str(source)],
                "exports.txt": [tool("nm"), "-arch", arch, "-gU", str(source)],
                "imports.txt": [tool("nm"), "-arch", arch, "-gu", str(source)],
                "symbols.txt.gz": [tool("nm"), "-arch", arch, "-a", "-n", str(source)],
                "indirect-symbols.txt.gz": [tool("otool"), "-arch", arch, "-Iv", str(source)],
                "objc-runtime.txt.gz": [tool("otool"), "-arch", arch, "-ov", str(source)],
                "disassembly.txt.gz": [tool("otool"), "-arch", arch, "-tvV", str(source)],
            }
            for filename, command in commands.items():
                data = capture(command, replacements)
                destination = arch_root / filename
                if destination.suffix == ".gz":
                    gzip_bytes(data, destination)
                else:
                    destination.write_bytes(data)

            names_process = subprocess.run(
                [tool("nm"), "-arch", arch, "-j", str(source)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            swift_symbols = sorted(
                {
                    line.strip()
                    for line in names_process.stdout.decode("utf-8", errors="ignore").splitlines()
                    if line.strip().startswith(("_$s", "$s"))
                }
            )
            if swift_symbols:
                demangled = subprocess.run(
                    [swift_demangle],
                    input=("\n".join(swift_symbols) + "\n").encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                ).stdout.decode("utf-8", errors="replace")
            else:
                demangled = ""
            write_lines(arch_root / "swift-symbols.txt", swift_symbols)
            write_text(arch_root / "swift-demangled.txt", demangled)
            arch_metadata.append(
                {"architecture": arch, "swiftSymbolCount": len(swift_symbols)}
            )

        module = {
            "name": source.name,
            "sourcePath": relative_source,
            "size": source.stat().st_size,
            "sha256": sha256(source),
            "architectures": arch_metadata,
        }
        write_text(module_root / "metadata.json", json.dumps(module, indent=2) + "\n")
        modules.append(module)
    return modules


def build_manifest(reverse: Path) -> dict[str, object]:
    files = []
    for path in sorted(reverse.rglob("*")):
        if not path.is_file() or path == reverse / "manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(reverse).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return {"formatVersion": 1, "files": files}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--bytecode", required=True)
    parser.add_argument("--readable-js", required=True)
    parser.add_argument("--esbuild-version", default="0.25.10")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    bytecode_source = Path(args.bytecode).resolve()
    readable_source = Path(args.readable_js).resolve()
    source = repo / "extracted/cli.js"
    if not source.is_file() or not bytecode_source.is_file() or not readable_source.is_file():
        raise SystemExit("source, bytecode, or readable JavaScript input is missing")

    reverse = repo / "reverse"
    if reverse.exists():
        shutil.rmtree(reverse)
    (reverse / "bytecode").mkdir(parents=True)
    (reverse / "javascript").mkdir(parents=True)
    (reverse / "index").mkdir(parents=True)
    write_text(
        reverse / "README.md",
        """# Deep reverse artifacts

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
""",
    )

    bytecode_gzip = reverse / "bytecode/cli.jsc.gz"
    gzip_copy(bytecode_source, bytecode_gzip)
    with tempfile.NamedTemporaryFile() as strings_file:
        process = subprocess.run(
            [tool("strings"), "-a", "-n", "5", str(bytecode_source)],
            stdout=strings_file,
            stderr=subprocess.STDOUT,
        )
        strings_file.flush()
        if process.returncode != 0:
            raise RuntimeError(f"strings failed with exit status {process.returncode}")
        gzip_copy(Path(strings_file.name), reverse / "bytecode/strings.txt.gz")

    bytecode_meta = {
        "source": "Bun standalone JSC bytecode cache for /$bunfs/root/cli",
        "sourceOffsetInBinary": 69107840,
        "uncompressedSize": bytecode_source.stat().st_size,
        "uncompressedSha256": sha256(bytecode_source),
        "gzipPath": "reverse/bytecode/cli.jsc.gz",
        "gzipSize": bytecode_gzip.stat().st_size,
        "gzipSha256": sha256(bytecode_gzip),
        "compression": "gzip level 9, mtime 0",
    }
    write_text(reverse / "bytecode/metadata.json", json.dumps(bytecode_meta, indent=2) + "\n")

    readable_destination = reverse / "javascript/cli.readable.js"
    shutil.copyfile(readable_source, readable_destination)
    source_bytes = source.read_bytes()
    readable_bytes = readable_destination.read_bytes()
    source_environment = {item.decode("ascii") for item in ENV_RE.findall(source_bytes)}
    readable_environment = {item.decode("ascii") for item in ENV_RE.findall(readable_bytes)}
    source_hosts = endpoint_hosts(source_bytes)
    readable_hosts = endpoint_hosts(readable_bytes)
    readable_meta = {
        "canonicalSource": "extracted/cli.js",
        "canonicalSourceSha256": sha256(source),
        "path": "reverse/javascript/cli.readable.js",
        "size": readable_destination.stat().st_size,
        "lines": readable_bytes.count(b"\n") + 1,
        "sha256": sha256(readable_destination),
        "generator": "esbuild",
        "generatorVersion": args.esbuild_version,
        "semanticInventoryCheck": {
            "environmentIdentifiersEqual": source_environment == readable_environment,
            "environmentIdentifierCount": len(source_environment),
            "endpointHostsEqual": source_hosts == readable_hosts,
            "endpointHostCount": len(source_hosts),
        },
        "role": "analysis view only; canonical packed bytes remain extracted/cli.js",
    }
    write_text(reverse / "javascript/metadata.json", json.dumps(readable_meta, indent=2) + "\n")

    index_summary = inventory(source_bytes, reverse / "index")
    shutil.copyfile(repo / "analysis/cli-surface.txt", reverse / "index/cli-surface.txt")
    index_summary["cliSurfaceSha256"] = sha256(reverse / "index/cli-surface.txt")
    write_text(reverse / "index/summary.json", json.dumps(index_summary, indent=2) + "\n")

    native_modules = build_native(repo, reverse)
    index_summary.update(build_native_index(reverse))
    write_text(reverse / "index/summary.json", json.dumps(index_summary, indent=2) + "\n")
    summary = {
        "formatVersion": 1,
        "version": (repo / "VERSION").read_text(encoding="utf-8").strip(),
        "canonicalBundle": {
            "path": "extracted/cli.js",
            "size": source.stat().st_size,
            "sha256": sha256(source),
        },
        "bytecode": bytecode_meta,
        "readableJavaScript": readable_meta,
        "index": index_summary,
        "nativeModules": native_modules,
    }
    write_text(reverse / "summary.json", json.dumps(summary, indent=2) + "\n")
    write_text(reverse / "manifest.json", json.dumps(build_manifest(reverse), indent=2) + "\n")

    print(f"deep reverse built: {reverse}")
    print(f"bytecode sha256: {bytecode_meta['uncompressedSha256']}")
    print(f"readable JavaScript sha256: {readable_meta['sha256']}")
    print(f"native modules: {len(native_modules)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
