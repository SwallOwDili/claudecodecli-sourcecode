#!/bin/bash
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
original_dir=${1:-"$repo_root/extracted"}
output_parent=${2:-"$repo_root/.."}
version=$(tr -d '[:space:]' < "$repo_root/VERSION")
report_dir="$repo_root/analysis/runtime-probes"
report_path="$report_dir/native-reconstruction.json"
x86_report_path="$report_dir/native-reconstruction-x86.json"

mkdir -p "$output_parent"
mkdir -p "$report_dir"
rm -f "$report_path" "$x86_report_path"

node "$script_dir/validate_computer_use_semantics.mjs" "$original_dir"
cargo fmt --manifest-path "$repo_root/reconstructed/Cargo.toml" --all -- --check
cargo check --manifest-path "$repo_root/reconstructed/Cargo.toml"
cargo build --manifest-path "$repo_root/reconstructed/Cargo.toml" --release
swift build --disable-sandbox \
  --package-path "$repo_root/reconstructed/swift/computer-use-swift" \
  -c release

swift_bin=$(swift build \
  --disable-sandbox \
  --package-path "$repo_root/reconstructed/swift/computer-use-swift" \
  -c release \
  --show-bin-path)
test_dir=$(mktemp -d "$output_parent/reconstructed-native-$version-XXXXXX")

install -m 755 \
  "$repo_root/reconstructed/target/release/libaudio_capture_reconstructed.dylib" \
  "$test_dir/audio-capture.node"
install -m 755 \
  "$repo_root/reconstructed/target/release/libcomputer_use_input_reconstructed.dylib" \
  "$test_dir/computer-use-input.node"
install -m 755 \
  "$repo_root/reconstructed/target/release/libimage_processor_reconstructed.dylib" \
  "$test_dir/image-processor.node"
install -m 755 \
  "$repo_root/reconstructed/target/release/liburl_handler_reconstructed.dylib" \
  "$test_dir/url-handler.node"
install -m 755 \
  "$swift_bin/libComputerUseSwift.dylib" \
  "$test_dir/computer-use-swift.node"

node "$script_dir/compare_behaviors.mjs" --self-test
node "$script_dir/validate_contracts.mjs" "$original_dir"
node "$script_dir/validate_contracts.mjs" "$test_dir"
node "$script_dir/compare_behaviors.mjs" \
  "$original_dir" \
  "$test_dir" \
  --report "$report_path"
node -e '
const r = require(process.argv[1]);
const labels = r.checkResults.map((item) => item.label);
if (
  !r.pass
  || r.summary.checksRun !== 23
  || r.summary.checksPassed !== 23
  || r.checkResults.length !== 23
  || new Set(labels).size !== 23
) process.exit(1);
' "$report_path"

if ! rustup target list --installed | grep -qx x86_64-apple-darwin; then
  echo "missing Rust target: rustup target add x86_64-apple-darwin" >&2
  exit 1
fi
if ! arch -x86_64 node -e 'process.exit(process.arch === "x64" ? 0 : 1)'; then
  echo "x86_64 Node execution through Rosetta is unavailable" >&2
  exit 1
fi
node "$script_dir/test_x86_provenance.mjs"

x86_cargo_target=$(mktemp -d "$output_parent/reconstructed-native-x86-cargo-$version-XXXXXX")
x86_swift_scratch=$(mktemp -d "$output_parent/reconstructed-native-x86-swift-$version-XXXXXX")
CARGO_TARGET_DIR="$x86_cargo_target" cargo build \
  --manifest-path "$repo_root/reconstructed/Cargo.toml" \
  --release \
  --target x86_64-apple-darwin
swift build --disable-sandbox \
  --package-path "$repo_root/reconstructed/swift/computer-use-swift" \
  --scratch-path "$x86_swift_scratch" \
  --triple x86_64-apple-macosx \
  -c release
x86_swift_bin=$(swift build \
  --disable-sandbox \
  --package-path "$repo_root/reconstructed/swift/computer-use-swift" \
  --scratch-path "$x86_swift_scratch" \
  --triple x86_64-apple-macosx \
  -c release \
  --show-bin-path)
x86_test_dir=$(mktemp -d "$output_parent/reconstructed-native-x86-$version-XXXXXX")

install -m 755 \
  "$x86_cargo_target/x86_64-apple-darwin/release/libaudio_capture_reconstructed.dylib" \
  "$x86_test_dir/audio-capture.node"
install -m 755 \
  "$x86_cargo_target/x86_64-apple-darwin/release/libcomputer_use_input_reconstructed.dylib" \
  "$x86_test_dir/computer-use-input.node"
install -m 755 \
  "$x86_cargo_target/x86_64-apple-darwin/release/libimage_processor_reconstructed.dylib" \
  "$x86_test_dir/image-processor.node"
install -m 755 \
  "$x86_cargo_target/x86_64-apple-darwin/release/liburl_handler_reconstructed.dylib" \
  "$x86_test_dir/url-handler.node"
install -m 755 \
  "$x86_swift_bin/libComputerUseSwift.dylib" \
  "$x86_test_dir/computer-use-swift.node"

arch -x86_64 node "$script_dir/compare_behaviors.mjs" --self-test
arch -x86_64 node "$script_dir/validate_contracts.mjs" \
  "$original_dir" \
  --modules computer-use-input.node,computer-use-swift.node
arch -x86_64 node "$script_dir/validate_contracts.mjs" "$x86_test_dir"
arch -x86_64 node "$script_dir/compare_behaviors.mjs" \
  "$original_dir" \
  "$x86_test_dir" \
  --x86-dual-only \
  --report "$x86_report_path"
arch -x86_64 node -e '
const r = require(process.argv[1]);
const labels = r.checkResults.map((item) => item.label);
if (
  !r.pass
  || r.summary.checksRun !== 20
  || r.summary.checksPassed !== 20
  || r.checkResults.length !== 20
  || new Set(labels).size !== 20
  || !r.checks.x86RuntimeCoverage
  || !r.checks.x86OriginalDualSliceCoverage
  || !r.checks.x86CompatibleAllModuleContractCoverage
  || !r.checks.x86OriginalSlicesPresent
  || !r.checks.x86ArtifactProvenanceValidated
  || !r.checks.x86RosettaTranslationObserved
) process.exit(1);
' "$x86_report_path"

echo "reconstructed native validation: PASS"
echo "NATIVE_BEHAVIOR_REPORT=$report_path"
echo "RECONSTRUCTED_NATIVE_DIR=$test_dir"
echo "NATIVE_X86_BEHAVIOR_REPORT=$x86_report_path"
echo "RECONSTRUCTED_NATIVE_X86_DIR=$x86_test_dir"
