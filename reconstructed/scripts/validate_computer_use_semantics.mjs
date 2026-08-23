#!/usr/bin/env node

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const originalDir = path.resolve(process.argv[2] ?? path.join(repoRoot, "extracted"));
const nativePath = path.join(originalDir, "computer-use-swift.node");
const sourcePath = path.join(
  repoRoot,
  "reconstructed/swift/computer-use-swift/Sources/ComputerUseSwift/Core.swift",
);

function universalSlices(buffer) {
  assert.equal(buffer.readUInt32BE(0), 0xcafebabe, "expected a universal Mach-O header");
  const slices = new Map();
  const architectureCount = buffer.readUInt32BE(4);
  for (let index = 0; index < architectureCount; index += 1) {
    const entryOffset = 8 + index * 20;
    const cpuType = buffer.readUInt32BE(entryOffset);
    const sliceOffset = buffer.readUInt32BE(entryOffset + 8);
    if (cpuType === 0x01000007) slices.set("x86_64", sliceOffset);
    if (cpuType === 0x0100000c) slices.set("arm64", sliceOffset);
  }
  assert.ok(slices.has("x86_64"), "x86_64 slice is missing");
  assert.ok(slices.has("arm64"), "arm64 slice is missing");
  return slices;
}

function decodeSwiftStaticString(buffer, offset) {
  const countAndFlags = buffer.readBigUInt64LE(offset);
  const object = buffer.readBigUInt64LE(offset + 8);
  const objectTag = Number((object >> 56n) & 0xffn);
  if ((objectTag & 0xf0) === 0xe0) {
    return buffer.subarray(offset, offset + (objectTag & 0x0f)).toString("utf8");
  }
  assert.equal(countAndFlags & 0xf000000000000000n, 0xd000000000000000n);
  assert.equal(object & 0x8000000000000000n, 0x8000000000000000n);
  const length = Number(countAndFlags & 0x0fffffffffffffffn);
  const cstringOffset = Number(object & 0x7fffffffffffffffn) + 0x20;
  return buffer.subarray(cstringOffset, cstringOffset + length).toString("utf8");
}

function staticStringArray(buffer, countOffset, elementsOffset) {
  const count = Number(buffer.readBigUInt64LE(countOffset));
  assert.equal(count, 8);
  assert.equal(buffer.readBigUInt64LE(countOffset + 8), 0x10n);
  return Array.from({ length: count }, (_, index) =>
    decodeSwiftStaticString(buffer, elementsOffset + index * 16));
}

function assertCString(buffer, offset, expected) {
  assert.equal(buffer.subarray(offset, offset + expected.length).toString("utf8"), expected);
  assert.equal(buffer[offset + expected.length], 0);
}

function validateCaptureScreenConsumer(swiftSource) {
  const start = swiftSource.indexOf("private static func captureScreen");
  const end = swiftSource.indexOf("private static func waitForAsync", start);
  assert.ok(start >= 0 && end > start, "captureScreen source range is missing");
  const captureScreenSource = swiftSource.slice(start, end);
  assert.match(
    captureScreenSource,
    /let allowed = Set\(allowedBundleIds\)\.union\(systemChromeBundleIds\)/,
    "captureScreen does not consume the exact system screenshot exclusion set",
  );
  assert.equal(
    captureScreenSource.split("throw CoreError.message(failureMessage)").length - 1,
    3,
    "captureScreen must map preflight, image encoding, and caught failures through failureMessage",
  );
  assert.match(
    captureScreenSource,
    /catch \{\s*throw CoreError\.message\(failureMessage\)\s*\}/,
    "captureScreen catch does not preserve the caller-specific failure contract",
  );
}

const source = fs.readFileSync(sourcePath, "utf8");
const expectedSystemChromeBundleIds = [
  "com.apple.dock",
  "com.apple.wallpaper.agent",
  "com.apple.controlcenter",
  "com.apple.SystemUIServer",
  "com.apple.TextInputSwitcher",
  "com.apple.wifi.WiFiAgent",
  "com.apple.AccessibilityUIServer",
  "com.apple.loginwindow",
];
const screenshotNilMessages = {
  full: "Screenshot capture returned nil (permission missing or SCContentFilter failure)",
  region: "Region capture returned nil (permission missing or SCContentFilter failure)",
};
const systemChromeMatch = source.match(
  /private static let systemChromeBundleIds: Set<String> = \[([\s\S]*?)\n\s*\]/,
);
assert.ok(systemChromeMatch, "system screenshot exclusion set is missing");
const actualSystemChromeBundleIds = [
  ...systemChromeMatch[1].matchAll(/"([^"]+)"/g),
].map((match) => match[1]);
assert.deepStrictEqual(actualSystemChromeBundleIds, expectedSystemChromeBundleIds);
assert.match(source, /if let id, let selected = displays\.first\(where:/);
assert.match(source, /return displays\.first \{ \$0\.isPrimary \} \?\? displays\.first/);
assert.match(source, /exempt\.insert\("com\.apple\.finder"\)/);
assert.match(source, /exemptBundleIds\.union\(\["com\.apple\.finder"\]\)/);
assert.doesNotMatch(source, /exemptBundleIds\.union\(\["com\.apple\.loginwindow"\]\)/);
assert.match(source, /display: displayInfo\(id: displayId\)/);
assert.match(source, /private static func appHasHideCandidateWindow/);
assert.match(source, /\(window\[kCGWindowLayer as String\] as\? Int\) == 0/);
assert.match(
  source,
  /let alpha = window\[kCGWindowAlpha as String\] as\? Double,\s+alpha > 0\.1,/,
);
assert.match(source, /return frame\.map \{ bounds\.intersects\(\$0\) \} \?\? true/);
for (const message of Object.values(screenshotNilMessages)) {
  assert.equal(
    source.split(message).length - 1,
    1,
    `unexpected screenshot error contract: ${message}`,
  );
}
const captureExcludingSource = source.slice(
  source.indexOf("static func captureExcluding"),
  source.indexOf("static func captureRegion"),
);
const captureRegionSource = source.slice(
  source.indexOf("static func captureRegion"),
  source.indexOf("static func resolvePrepareCapture"),
);
assert.match(captureExcludingSource, /let image = try captureScreen\(/);
assert.match(captureExcludingSource, new RegExp(screenshotNilMessages.full.replace(/[()]/g, "\\$&")));
assert.doesNotMatch(captureExcludingSource, new RegExp(screenshotNilMessages.region.replace(/[()]/g, "\\$&")));
assert.match(captureRegionSource, /let image = try captureScreen\(/);
assert.match(captureRegionSource, new RegExp(screenshotNilMessages.region.replace(/[()]/g, "\\$&")));
assert.doesNotMatch(captureRegionSource, new RegExp(screenshotNilMessages.full.replace(/[()]/g, "\\$&")));
validateCaptureScreenConsumer(source);
const missingSystemChromeConsumer = source.replace(".union(systemChromeBundleIds)", "");
assert.notEqual(missingSystemChromeConsumer, source, "system screenshot consumer mutation did not apply");
assert.throws(
  () => validateCaptureScreenConsumer(missingSystemChromeConsumer),
  /does not consume the exact system screenshot exclusion set/,
);
const missingFailureCatch = source.replace(
  /catch \{\s*throw CoreError\.message\(failureMessage\)\s*\}/,
  "catch { throw error }",
);
assert.notEqual(missingFailureCatch, source, "screenshot failure catch mutation did not apply");
assert.throws(
  () => validateCaptureScreenConsumer(missingFailureCatch),
  /must map preflight, image encoding, and caught failures through failureMessage/,
);
const hideWindowHelper = source.slice(
  source.indexOf("private static func appHasHideCandidateWindow"),
  source.indexOf("private static func appHasWindow"),
);
assert.ok(hideWindowHelper.length > 0, "hide-window helper source range is missing");
assert.doesNotMatch(hideWindowHelper, /bounds\.(?:width|height)/);

const native = fs.readFileSync(nativePath);
const slices = universalSlices(native);
const arm64 = slices.get("arm64");
const x86_64 = slices.get("x86_64");
const arm64Slice = native.subarray(arm64);
const x86Slice = native.subarray(x86_64);

assert.deepStrictEqual(
  staticStringArray(arm64Slice, 0x30e58, 0x30e68),
  expectedSystemChromeBundleIds,
);
assert.deepStrictEqual(
  staticStringArray(x86Slice, 0x31e48, 0x31e58),
  expectedSystemChromeBundleIds,
);
assertCString(arm64Slice, 0x25720, screenshotNilMessages.full);
assertCString(arm64Slice, 0x25630, screenshotNilMessages.region);
assertCString(x86Slice, 0x2a330, screenshotNilMessages.full);
assertCString(x86Slice, 0x2a240, screenshotNilMessages.region);
assert.equal(0x625d + 0x240b3 + 0x20, 0x2a330);
assert.equal(0x7442 + 0x22dde + 0x20, 0x2a240);

assert.equal(native.readDoubleLE(arm64 + 0x26738), 0.1);
assert.equal(native.readDoubleLE(x86_64 + 0x2b358), 0.1);
assert.equal(
  native.subarray(arm64 + 0x25240, arm64 + 0x25250).toString("ascii"),
  "com.apple.finder",
);
assert.equal(
  native.subarray(x86_64 + 0x29e50, x86_64 + 0x29e60).toString("ascii"),
  "com.apple.finder",
);
assert.equal(native.readBigUInt64LE(arm64 + 0x30f00), 1n);
const arm64FinderObject = native.readBigUInt64LE(arm64 + 0x30f18);
assert.equal(arm64FinderObject, 0x8000000000025220n);
assert.equal((arm64FinderObject & 0x7fffffffffffffffn) + 0x20n, 0x25240n);
assert.equal(native.readBigUInt64LE(x86_64 + 0x31ef0), 1n);
const x86FinderObject = native.readBigUInt64LE(x86_64 + 0x31f08);
assert.equal(x86FinderObject, 0x8000000000029e30n);
assert.equal((x86FinderObject & 0x7fffffffffffffffn) + 0x20n, 0x29e50n);

const arm64Disassembly = execFileSync(
  "/usr/bin/otool",
  ["-arch", "arm64", "-tvV", nativePath],
  { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
);
for (const instruction of [
  "0000000000007ee8\tldr\td0, [x8, #0x738]",
  "00000000000080e8\tfcmp\td0, d1",
  "00000000000080ec\tb.le\t0x7fd8",
  "00000000000081ec\tadrp\tx1, 40 ; 0x30000",
  "00000000000081f0\tadd\tx1, x1, #0xef0",
  "00000000000081f4\tbl\t0x243e8 ; symbol stub for: _swift_initStaticObject",
  "0000000000008210\tbl\t_$sSh9formUnion",
  "000000000000901c\tadd\tx8, x8, #0x240 ; literal pool for: \"com.apple.finder\"",
  "0000000000009020\tsub\tx8, x8, #0x20",
  "0000000000009024\torr\tx8, x8, #0x8000000000000000",
  "000000000000a3a8\tbl\t_$s16ComputerUseSwift13cuDisplayInfo",
  "000000000000a3f4\tbl\t_$s16ComputerUseSwift21computeHideCandidates",
  "00000000000200ec\tadrp\tx1, 16 ; 0x30000",
  "00000000000200f0\tadd\tx1, x1, #0xe48",
  "00000000000200f4\tbl\t0x243e8 ; symbol stub for: _swift_initStaticObject",
  "000000000002010c\tadd\tx0, x19, #0x20",
  "0000000000020110\tmov\tw1, #0x8",
  "00000000000228ac\tldr\tx8, [x8, #0xe38]",
  "00000000000228b4\tb.ne\t0x22948",
  "00000000000228bc\tldr\tx2, [x8, #0x130]",
  "00000000000228c8\tbl\t_$sSh8containsySbxFSS_Tg5",
  "0000000000022958\tbl\t0x2440c ; symbol stub for: _swift_once",
  "000000000002295c\tb\t0x228b8",
  "00000000000057fc\tcbz\tx19, 0x5968",
  "0000000000005970\tadd\tx8, x8, #0x720 ; literal pool for: \"Screenshot capture returned nil (permission missing or SCContentFilter failure)\"",
  "0000000000005974\tsub\tx8, x8, #0x20",
  "0000000000005994\tadd\tx8, x25, #0x38",
  "0000000000006810\tcbz\tx19, 0x6948",
  "0000000000006950\tadd\tx8, x8, #0x630 ; literal pool for: \"Region capture returned nil (permission missing or SCContentFilter failure)\"",
  "0000000000006954\tsub\tx8, x8, #0x20",
  "0000000000006974\tadd\tx8, x25, #0x34",
]) {
  assert.ok(arm64Disassembly.includes(instruction), `missing arm64 evidence: ${instruction}`);
}

const x86Disassembly = execFileSync(
  "/usr/bin/otool",
  ["-arch", "x86_64", "-tvV", nativePath],
  { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
);
for (const instruction of [
  "0000000000008fa3\tmovsd\t-0x90(%rbp), %xmm0",
  "0000000000008fab\tucomisd\t0x223a5(%rip), %xmm0",
  "0000000000008fb3\tjbe\t0x8ef5",
  "000000000000915d\tcallq\t0x29084",
  "000000000000917e\tcallq\t_$sSh9formUnion",
  "00000000000250fa\tleaq\t0xcd37(%rip), %rsi",
  "0000000000025104\tcallq\t0x29084",
  "0000000000025117\taddq\t$0x20, %rbx",
  "0000000000025122\tmovl\t$0x8, %esi",
  "0000000000027a7c\tcmpq\t$-0x1, _$s16ComputerUseSwift013ScreenshotForaB0O21systemChromeBundleIds_Wz(%rip)",
  "0000000000027a8a\tmovq\t_$s16ComputerUseSwift013ScreenshotForaB0O21systemChromeBundleIdsShySSGvpZ(%rip), %rdx",
  "0000000000027a97\tcallq\t_$sSh8containsySbxFSS_Tg5",
  "0000000000027b32\tcallq\t0x29096",
  "0000000000027b37\tjmp\t0x27a8a",
  "000000000000606c\tje\t0x6244",
  "0000000000006256\tleaq\t0x240b3(%rip), %r12",
  "000000000000625d\torq\t%rax, %r12",
  "0000000000006284\taddq\t$0x38, %r15",
  "000000000000728c\tje\t0x7429",
  "000000000000743b\tleaq\t0x22dde(%rip), %r12",
  "0000000000007442\torq\t%rax, %r12",
  "0000000000007469\taddq\t$0x34, %r15",
]) {
  assert.ok(x86Disassembly.includes(instruction), `missing x86_64 evidence: ${instruction}`);
}

console.log("computer-use static semantics: PASS");
console.log("fixed hide exemption: com.apple.finder");
console.log("visible-window threshold: kCGWindowLayer == 0 and kCGWindowAlpha > 0.1");
console.log("preview display scope: requested display, with main-display fallback");
console.log("screenshot system exclusions: exact 8-item dual-architecture contract");
console.log("screenshot nil errors: exact full/region dual-architecture contracts");
console.log("screenshot contract consumers: reachable in both architectures");
console.log("compatible screenshot consumer: systemChromeBundleIds union + failureMessage catch");
console.log("compatible consumer mutation tests: PASS");
