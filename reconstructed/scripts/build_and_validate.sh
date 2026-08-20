#!/bin/bash
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
original_dir=${1:-"$repo_root/extracted"}
output_parent=${2:-"$repo_root/.."}
version=$(tr -d '[:space:]' < "$repo_root/VERSION")

mkdir -p "$output_parent"

cargo fmt --manifest-path "$repo_root/reconstructed/Cargo.toml" --all -- --check
cargo check --manifest-path "$repo_root/reconstructed/Cargo.toml"
cargo build --manifest-path "$repo_root/reconstructed/Cargo.toml" --release
swift build --package-path "$repo_root/reconstructed/swift/computer-use-swift" -c release

swift_bin=$(swift build \
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

node "$script_dir/validate_contracts.mjs" "$original_dir"
node "$script_dir/validate_contracts.mjs" "$test_dir"
node "$script_dir/compare_behaviors.mjs" "$original_dir" "$test_dir"

echo "reconstructed native validation: PASS"
echo "RECONSTRUCTED_NATIVE_DIR=$test_dir"
