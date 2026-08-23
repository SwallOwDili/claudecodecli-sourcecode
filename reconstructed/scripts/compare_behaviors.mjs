#!/usr/bin/env node

import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const originalDir = path.resolve(process.argv[2] ?? path.join(repoRoot, "extracted"));
const rebuiltDir = path.resolve(process.argv[3] ?? "");
const reportFlag = process.argv.indexOf("--report");
const reportPath = reportFlag >= 0 ? path.resolve(process.argv[reportFlag + 1] ?? "") : null;
const selfTest = process.argv.includes("--self-test");
const contractsValidated = process.argv.includes("--contracts-validated");

if (!selfTest && !process.argv[3]) {
  console.error("usage: compare_behaviors.mjs ORIGINAL_DIR REBUILT_DIR");
  process.exit(2);
}
if (reportFlag >= 0 && !process.argv[reportFlag + 1]) {
  console.error("--report requires a path");
  process.exit(2);
}
if (reportPath && !contractsValidated) {
  console.error("--report requires --contracts-validated after both contract validators pass");
  process.exit(2);
}
if (reportPath) fs.rmSync(reportPath, { force: true });

const failures = [];
const results = [];
let checks = 0;

function moduleFor(label) {
  if (label.startsWith("audio")) return "audio-capture.node";
  if (label.startsWith("URL")) return "url-handler.node";
  if (label.startsWith("image")) return "image-processor.node";
  if (label.startsWith("input")) return "computer-use-input.node";
  if (label.startsWith("swift")) return "computer-use-swift.node";
  return "all";
}

function comparisonFor(label) {
  if (label.includes("screenshot shape") || label === "input module behavior") return "schema-and-invariants";
  if (label.includes("applications") || label.includes("displays") || label.includes("icon")) return "normalized-semantic";
  return "exact";
}

function record(label, passed) {
  results.push({
    label,
    module: moduleFor(label),
    comparison: comparisonFor(label),
    status: passed ? "pass" : "fail",
  });
}

function equal(label, actual, expected) {
  checks += 1;
  try {
    assert.deepStrictEqual(actual, expected);
    record(label, true);
  } catch (error) {
    record(label, false);
    failures.push(`${label}: ${error.message}`);
  }
}

function truthy(label, condition, detail) {
  checks += 1;
  record(label, Boolean(condition));
  if (!condition) failures.push(`${label}: ${detail}`);
}

function boundary(label, reason) {
  checks += 1;
  results.push({
    label,
    module: moduleFor(label),
    comparison: "environment-boundary",
    status: "pass",
    boundary: reason,
  });
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let index = 0; index < 8; index += 1) {
      crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const name = Buffer.from(type);
  const output = Buffer.alloc(12 + data.length);
  output.writeUInt32BE(data.length, 0);
  name.copy(output, 4);
  data.copy(output, 8);
  output.writeUInt32BE(crc32(Buffer.concat([name, data])), 8 + data.length);
  return output;
}

function onePixelPng() {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(1, 0);
  header.writeUInt32BE(1, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", zlib.deflateSync(Buffer.from([0, 255, 0, 0, 255]))),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

async function errorResult(operation) {
  try {
    await operation();
    return { ok: true };
  } catch (error) {
    return { ok: false, message: error?.message, code: error?.code };
  }
}

async function valueResult(operation) {
  try {
    return { ok: true, value: await operation() };
  } catch (error) {
    return { ok: false, message: error?.message, code: error?.code };
  }
}

async function compareValueResults(label, rebuiltOperation, originalOperation, normalize = (value) => value) {
  const [originalResult, rebuiltResult] = await Promise.all([
    valueResult(originalOperation),
    valueResult(rebuiltOperation),
  ]);
  if (originalResult.ok) originalResult.value = normalize(originalResult.value);
  if (rebuiltResult.ok) rebuiltResult.value = normalize(rebuiltResult.value);
  equal(label, rebuiltResult, originalResult);
  return { original: originalResult, rebuilt: rebuiltResult };
}

function load(directory, filename) {
  return require(path.join(directory, filename));
}

async function inspectImage(module) {
  const input = onePixelPng();
  const processor = await module.processImage(input);
  const metadata = processor.metadata();
  const resizeSame = processor.resize(1, 1) === processor;
  const jpegSame = processor.jpeg(80) === processor;
  const jpeg = await processor.toBuffer();
  const consumed = await errorResult(() => processor.metadata());

  const encoded = {};
  for (const format of ["jpeg", "png", "webp"]) {
    const instance = await module.processImage(input);
    if (format === "png") instance.png();
    else instance[format](80);
    const output = await instance.toBuffer();
    encoded[format] = { bytes: output.length, sha256: sha256(output) };
  }

  const disposed = await module.processImage(input);
  const disposeResult = disposed.dispose();
  const disposedError = await errorResult(() => disposed.metadata());

  return {
    metadata,
    resizeSame,
    jpegSame,
    jpegMagic: jpeg.subarray(0, 3).toString("hex"),
    consumed,
    encoded,
    disposeResult,
    disposedError,
    clipboardImageAvailable: module.hasClipboardImage(),
  };
}

async function inspectInput(module) {
  const mouse = await valueResult(() => module.mouseLocation());
  const frontmost = await valueResult(() => module.getFrontmostAppInfo());
  const invalid = {};
  for (const [label, operation] of [
    ["keys.empty", () => module.keys([])],
    ["key.name", () => module.key("invalid-long-key", "click")],
    ["key.action", () => module.key("a", "invalid-action")],
    ["button.name", () => module.mouseButton("invalid-button", "click")],
    ["button.action", () => module.mouseButton("left", "invalid-action")],
    ["scroll.axis", () => module.mouseScroll(0, "invalid-axis")],
  ]) {
    invalid[label] = await errorResult(operation);
  }
  return {
    mouse: mouse.ok
      ? { ok: true, shape: { x: typeof mouse.value.x, y: typeof mouse.value.y }, value: mouse.value }
      : mouse,
    frontmost,
    invalid,
  };
}

function canonicalApps(apps) {
  return apps.map(({ bundleId, displayName, path, pid }) => ({
    bundleId,
    displayName,
    ...(path === undefined ? {} : { path }),
    ...(pid === undefined ? {} : { pid }),
  }));
}

function sortInstalled(apps) {
  return canonicalApps(apps).sort((a, b) =>
    a.path.localeCompare(b.path) || a.bundleId.localeCompare(b.bundleId),
  );
}

function sortByBundleId(values) {
  return [...values]
    .map((value) => ({
      ...value,
      ...(Array.isArray(value.displayIds) ? { displayIds: [...value.displayIds].sort((a, b) => a - b) } : {}),
    }))
    .sort((a, b) => a.bundleId.localeCompare(b.bundleId));
}

function decodeCanonicalBase64(value) {
  if (
    typeof value !== "string"
    || value.length === 0
    || value.length % 4 !== 0
    || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)
  ) return null;
  const bytes = Buffer.from(value, "base64");
  return bytes.toString("base64") === value ? bytes : null;
}

function screenshotShape(result) {
  const base64 = typeof result?.base64 === "string" ? result.base64 : "";
  const canonicalBytes = decodeCanonicalBase64(base64);
  const bytes = canonicalBytes ?? Buffer.alloc(0);
  return {
    fields: result && typeof result === "object" ? Object.keys(result).sort() : [],
    base64Type: typeof result?.base64,
    canonicalBase64: canonicalBytes !== null,
    hasImageBytes: bytes.length > 0,
    width: result?.width,
    height: result?.height,
    displayWidth: result?.displayWidth,
    displayHeight: result?.displayHeight,
    displayId: result?.displayId,
    originX: result?.originX,
    originY: result?.originY,
    jpegMagic: bytes.subarray(0, 3).toString("hex"),
    jpegEnd: bytes.subarray(-2).toString("hex"),
  };
}

const screenshotBoundaryMessages = new Set([
  "Screenshot capture returned nil (permission missing or SCContentFilter failure)",
  "Region capture returned nil (permission missing or SCContentFilter failure)",
  "ScreenCaptureKit requires macOS 14.0",
]);

function classifyScreenshotResult(result) {
  if (result.ok) return { kind: "success", value: screenshotShape(result.value) };
  const message = String(result.message ?? "");
  if (screenshotBoundaryMessages.has(message)) {
    return {
      kind: "environment-boundary",
      message,
      ...(result.code === undefined ? {} : { code: result.code }),
    };
  }
  return {
    kind: "error",
    ...(result.code === undefined ? {} : { code: result.code }),
    message,
  };
}

function screenshotPairDecision(originalResult, rebuiltResult) {
  const original = classifyScreenshotResult(originalResult);
  const rebuilt = classifyScreenshotResult(rebuiltResult);
  if (original.kind === "environment-boundary" && rebuilt.kind === "environment-boundary") {
    try {
      assert.deepStrictEqual(rebuilt, original);
      return { kind: "environment-boundary", original, rebuilt };
    } catch {
      return { kind: "incompatible", original, rebuilt };
    }
  }
  if (original.kind === "success" && rebuilt.kind === "success") {
    return { kind: "success", original, rebuilt };
  }
  return { kind: "incompatible", original, rebuilt };
}

function canonicalImageFormat(value) {
  const format = String(value ?? "").toLowerCase();
  return format === "jpg" ? "jpeg" : format;
}

async function decodeScreenshotJpeg(imageModule, bytes) {
  let processor;
  try {
    processor = await imageModule.processImage(bytes);
    const metadata = processor.metadata();
    return {
      ok: true,
      format: canonicalImageFormat(metadata.format),
      width: metadata.width,
      height: metadata.height,
    };
  } catch (error) {
    return { ok: false, message: String(error?.message ?? error) };
  } finally {
    try {
      processor?.dispose();
    } catch {
      // Decoding success is the invariant; disposal failure is already covered by the image module checks.
    }
  }
}

async function compareScreenshotResults(
  label,
  rebuiltOperation,
  originalOperation,
  rebuiltImageModule,
  originalImageModule,
) {
  const [originalResult, rebuiltResult] = await Promise.all([
    valueResult(originalOperation),
    valueResult(rebuiltOperation),
  ]);
  const decision = screenshotPairDecision(originalResult, rebuiltResult);
  if (decision.kind === "environment-boundary") {
    boundary(
      label,
      `Both modules reported the same display-capture boundary: ${decision.original.message}`,
    );
    return;
  }
  if (decision.kind === "success") {
    const original = decision.original.value;
    const rebuilt = decision.rebuilt.value;
    const [originalDecode, rebuiltDecode] = await Promise.all([
      decodeScreenshotJpeg(
        originalImageModule,
        Buffer.from(originalResult.value.base64, "base64"),
      ),
      decodeScreenshotJpeg(
        rebuiltImageModule,
        Buffer.from(rebuiltResult.value.base64, "base64"),
      ),
    ]);
    original.jpegDecode = originalDecode;
    rebuilt.jpegDecode = rebuiltDecode;
    const valid = [original, rebuilt].every((value) =>
      value.base64Type === "string"
      && value.canonicalBase64
      && value.hasImageBytes
      && value.jpegMagic === "ffd8ff"
      && value.jpegEnd === "ffd9"
      && value.jpegDecode.ok
      && value.jpegDecode.format === "jpeg"
      && value.jpegDecode.width === value.width
      && value.jpegDecode.height === value.height,
    );
    if (!valid) {
      checks += 1;
      record(label, false);
      failures.push(
        `${label}: invalid screenshot payloads: rebuilt=${JSON.stringify(rebuilt)} original=${JSON.stringify(original)}`,
      );
      return;
    }
    equal(label, rebuilt, original);
    return;
  }
  checks += 1;
  record(label, false);
  failures.push(
    `${label}: incompatible screenshot outcomes: rebuilt=${JSON.stringify(decision.rebuilt)} original=${JSON.stringify(decision.original)}`,
  );
}

function runNormalizationSelfTest() {
  const base = [{ bundleId: "com.apple.Stickies", displayName: "Stickies" }];
  const reordered = [
    { bundleId: "com.microsoft.Word", displayName: "Microsoft Word" },
    ...base,
  ];
  assert.deepStrictEqual(
    sortByBundleId(reordered),
    sortByBundleId([...reordered].reverse()),
  );
  const finderDrift = [
    { bundleId: "com.apple.finder", displayName: "Finder" },
    ...base,
  ];
  assert.notDeepStrictEqual(
    sortByBundleId(base),
    sortByBundleId(finderDrift),
  );
  assert.equal(screenshotShape({ base64: "/9j/2Q==" }).canonicalBase64, true);
  assert.equal(screenshotShape({ base64: "!!!!/9j/2Q==" }).canonicalBase64, false);
  assert.equal(canonicalImageFormat("jpg"), "jpeg");
  assert.equal(canonicalImageFormat("JPEG"), "jpeg");
  const fullBoundary = {
    ok: false,
    message: "Screenshot capture returned nil (permission missing or SCContentFilter failure)",
  };
  const regionBoundary = {
    ok: false,
    message: "Region capture returned nil (permission missing or SCContentFilter failure)",
  };
  assert.equal(screenshotPairDecision(fullBoundary, fullBoundary).kind, "environment-boundary");
  assert.equal(screenshotPairDecision(fullBoundary, regionBoundary).kind, "incompatible");
  assert.equal(
    screenshotPairDecision({ ok: true, value: { base64: "/9j/2Q==" } }, fullBoundary).kind,
    "incompatible",
  );
  assert.deepStrictEqual(
    classifyScreenshotResult({
      ok: false,
      code: "EIO",
      message: "unexpected capture returned nil after SCContentFilter failure",
    }),
    {
      kind: "error",
      code: "EIO",
      message: "unexpected capture returned nil after SCContentFilter failure",
    },
  );
}

async function inspectSwift(
  original,
  rebuilt,
  inputObservation,
  originalImageModule,
  rebuiltImageModule,
) {
  const originalPump = setInterval(() => original._drainMainRunLoop(), 1);
  const rebuiltPump = setInterval(() => rebuilt._drainMainRunLoop(), 1);
  try {
    equal("swift optional undefined", rebuilt._testEchoOptionalInt(), original._testEchoOptionalInt());
    equal("swift optional null", rebuilt._testEchoOptionalInt(null), original._testEchoOptionalInt(null));
    equal("swift optional zero", rebuilt._testEchoOptionalInt(0), original._testEchoOptionalInt(0));
    equal("swift optional positive", rebuilt._testEchoOptionalInt(42), original._testEchoOptionalInt(42));
    equal("swift accessibility", rebuilt.tcc.checkAccessibility(), original.tcc.checkAccessibility());
    equal("swift screen recording", rebuilt.tcc.checkScreenRecording(), original.tcc.checkScreenRecording());

    const displays = await compareValueResults(
      "swift displays",
      () => rebuilt.display.listAll(),
      () => original.display.listAll(),
    );
    const display = displays.original.ok
      ? displays.original.value.find((item) => item.isPrimary) ?? displays.original.value[0]
      : undefined;
    const invalidDisplayId = 0xffffffff;
    if (display) {
      await compareValueResults(
        "swift display size",
        () => ({
          selected: rebuilt.display.getSize(display.displayId),
          invalidFallback: rebuilt.display.getSize(invalidDisplayId),
        }),
        () => ({
          selected: original.display.getSize(display.displayId),
          invalidFallback: original.display.getSize(invalidDisplayId),
        }),
      );
    } else {
      boundary("swift display size", "No display was visible to either module in this execution environment");
    }

    const running = await compareValueResults(
      "swift running applications",
      () => rebuilt.apps.listRunning(),
      () => original.apps.listRunning(),
      canonicalApps,
    );
    const originalRunning = running.original.ok ? running.original.value : [];

    const installed = await compareValueResults(
      "swift installed applications",
      () => rebuilt.apps.listInstalled(),
      () => original.apps.listInstalled(),
      sortInstalled,
    );

    const names = ["Finder", "Safari", "Application That Does Not Exist"];
    await compareValueResults(
      "swift resolve bundle ids",
      () => rebuilt.apps.resolveBundleIds(names),
      () => original.apps.resolveBundleIds(names),
    );

    const bundleIds = originalRunning.map((app) => app.bundleId).filter(Boolean).slice(0, 8);
    await compareValueResults(
      "swift window displays",
      () => rebuilt.apps.findWindowDisplays(bundleIds),
      () => original.apps.findWindowDisplays(bundleIds),
      sortByBundleId,
    );
    const previewMatrix = (module) => ({
      defaultDisplay: sortByBundleId(module.apps.previewHideSet(bundleIds)),
      invalidDisplayFallback: sortByBundleId(
        module.apps.previewHideSet(bundleIds, invalidDisplayId),
      ),
      ...(display
        ? { selectedDisplay: sortByBundleId(module.apps.previewHideSet(bundleIds, display.displayId)) }
        : {}),
    });
    await compareValueResults(
      "swift hide preview",
      () => previewMatrix(rebuilt),
      () => previewMatrix(original),
    );

    if (inputObservation.mouse.ok) {
      const point = inputObservation.mouse.value;
      await compareValueResults(
        "swift application under point",
        () => rebuilt.apps.appUnderPoint(point.x, point.y),
        () => original.apps.appUnderPoint(point.x, point.y),
      );
    } else {
      boundary("swift application under point", "Accessibility permission prevented a read-only pointer query");
    }

    const iconCandidate = installed.original.ok
      ? installed.original.value.find((app) => app.path)
      : undefined;
    if (iconCandidate) {
      await compareValueResults(
        "swift application icon",
        () => rebuilt.apps.iconDataUrl(iconCandidate.path),
        () => original.apps.iconDataUrl(iconCandidate.path),
      );
    } else {
      boundary("swift application icon", "Spotlight did not provide an installed-application path");
    }

    await compareValueResults(
      "swift unhide empty",
      () => rebuilt.apps.unhide([]),
      () => original.apps.unhide([]),
    );

    if (display) {
      const outputWidth = Math.min(display.width, 320);
      const outputHeight = Math.max(1, Math.round((outputWidth / display.width) * display.height));
      await compareScreenshotResults(
        "swift full screenshot shape",
        () => rebuilt.screenshot.captureExcluding(
          bundleIds,
          0.6,
          outputWidth,
          outputHeight,
          display.displayId,
        ),
        () => original.screenshot.captureExcluding(
          bundleIds,
          0.6,
          outputWidth,
          outputHeight,
          display.displayId,
        ),
        rebuiltImageModule,
        originalImageModule,
      );

      await compareScreenshotResults(
        "swift region screenshot shape",
        () => rebuilt.screenshot.captureRegion(
          bundleIds,
          display.originX,
          display.originY,
          Math.min(display.width, 320),
          Math.min(display.height, 240),
          320,
          240,
          0.6,
          display.displayId,
        ),
        () => original.screenshot.captureRegion(
          bundleIds,
          display.originX,
          display.originY,
          Math.min(display.width, 320),
          Math.min(display.height, 240),
          320,
          240,
          0.6,
          display.displayId,
        ),
        rebuiltImageModule,
        originalImageModule,
      );
    } else {
      boundary("swift full screenshot shape", "No display was visible to either module in this execution environment");
      boundary("swift region screenshot shape", "No display was visible to either module in this execution environment");
    }
  } finally {
    clearInterval(originalPump);
    clearInterval(rebuiltPump);
  }
}

if (selfTest) {
  runNormalizationSelfTest();
  console.log("native behavior normalization tests: PASS");
  process.exit(0);
}

const originalAudio = load(originalDir, "audio-capture.node");
const rebuiltAudio = load(rebuiltDir, "audio-capture.node");
equal(
  "audio initial state",
  {
    recording: rebuiltAudio.isRecording(),
    playing: rebuiltAudio.isPlaying(),
    microphoneAuthorizationStatus: rebuiltAudio.microphoneAuthorizationStatus(),
  },
  {
    recording: originalAudio.isRecording(),
    playing: originalAudio.isPlaying(),
    microphoneAuthorizationStatus: originalAudio.microphoneAuthorizationStatus(),
  },
);

const originalUrl = load(originalDir, "url-handler.node");
const rebuiltUrl = load(rebuiltDir, "url-handler.node");
equal("URL timeout", await rebuiltUrl.waitForUrlEvent(1), await originalUrl.waitForUrlEvent(1));

const originalImageModule = load(originalDir, "image-processor.node");
const rebuiltImageModule = load(rebuiltDir, "image-processor.node");
const originalImage = await inspectImage(originalImageModule);
const rebuiltImage = await inspectImage(rebuiltImageModule);
equal("image processor behavior", rebuiltImage, originalImage);

const originalInputModule = load(originalDir, "computer-use-input.node");
const rebuiltInputModule = load(rebuiltDir, "computer-use-input.node");
const originalInput = await inspectInput(originalInputModule);
const rebuiltInput = await inspectInput(rebuiltInputModule);
equal("input module behavior", rebuiltInput, originalInput);

const originalSwift = load(originalDir, "computer-use-swift.node").computerUse;
const rebuiltSwift = load(rebuiltDir, "computer-use-swift.node").computerUse;
await inspectSwift(
  originalSwift,
  rebuiltSwift,
  originalInput,
  originalImageModule,
  rebuiltImageModule,
);

truthy("behavior check count", checks === 22, `expected 22 substantive checks before the guard, got ${checks}`);

const passedChecks = results.filter((item) => item.status === "pass").length;
const labels = results.map((item) => item.label);
const behaviorPass = failures.length === 0
  && checks === 23
  && results.length === 23
  && passedChecks === 23
  && new Set(labels).size === labels.length
  && process.arch === "arm64";

if (reportPath) {
  const version = fs.readFileSync(path.join(repoRoot, "VERSION"), "utf8").trim();
  const versionRecord = JSON.parse(fs.readFileSync(path.join(repoRoot, "analysis/version.json"), "utf8"));
  const architectureLines = fs.readFileSync(
    path.join(repoRoot, "reverse/index/native-architectures.txt"),
    "utf8",
  ).trim().split("\n");
  const originalArchitectures = {};
  for (const line of architectureLines) {
    const match = line.match(/^(.+\.node) \[([^\]]+)\]:/);
    if (!match) continue;
    (originalArchitectures[match[2]] ??= []).push(match[1]);
  }
  for (const modules of Object.values(originalArchitectures)) modules.sort();
  const report = {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    environment: {
      platform: process.platform,
      arch: process.arch,
      nodeVersion: process.version,
    },
    target: { version, binarySha256: versionRecord.binary.sha256 },
    evidenceClasses: {
      original: "Observed: release modules and same-input runtime outputs",
      compatible: "Compatible: independently rebuilt modules matching checked external behavior",
    },
    architectureCoverage: {
      original: {
        arm64: { method: "runtime-and-static", modules: originalArchitectures.arm64 ?? [] },
        x86_64: { method: "static-only", modules: originalArchitectures.x86_64 ?? [] },
      },
      compatible: {
        arm64: { method: "build-and-runtime", modules: Object.keys(JSON.parse(fs.readFileSync(path.join(repoRoot, "reconstructed/contracts/module-exports.json"), "utf8"))).sort() },
        x86_64: { method: "not-built-or-run", modules: [] },
      },
    },
    commands: {
      buildAndValidate: "reconstructed/scripts/build_and_validate.sh extracted $OUTPUT_PARENT",
    },
    input: {
      audioCapture: "initial state and authorization query; no microphone capture",
      urlHandler: "1ms no-event timeout",
      imageProcessor: "fixed in-memory 1x1 RGBA PNG and consumed/disposed lifecycle",
      computerUseInput: "read-only mouse/frontmost outcomes, permission failures, and validation ordering; no input injection",
      computerUseSwift: "display/TCC/application outcomes, default/explicit/invalid display selection for hide preview, plus screenshot schema and JPEG decode invariants when available; unavailable system services are explicit environment boundaries",
    },
    inputStrategies: {
      "audio-capture.node": "initial state and authorization query; no microphone capture",
      "url-handler.node": "1ms no-event timeout",
      "image-processor.node": "fixed in-memory 1x1 RGBA PNG and consumed/disposed lifecycle",
      "computer-use-input.node": "read-only mouse/frontmost outcomes, permission failures, and validation ordering; no input injection",
      "computer-use-swift.node": "display/TCC/application outcomes, default/explicit/invalid display selection for hide preview, plus screenshot schema and JPEG decode invariants when available; unavailable system services are explicit environment boundaries",
    },
    literalOutput: {
      originalContract: "native contract validation: PASS",
      compatibleContract: "native contract validation: PASS",
      behavior: `native behavior comparison: ${behaviorPass ? "PASS" : "FAIL"}`,
      checksPassed: passedChecks,
    },
    exitStatus: { buildAndValidate: behaviorPass ? 0 : 1 },
    checks: {
      originalContract: true,
      compatibleContract: true,
      behaviorChecksPassed: behaviorPass,
      arm64RuntimeCoverage: process.arch === "arm64",
      x86StaticBoundaryExplicit: (originalArchitectures.x86_64?.length ?? 0) > 0,
    },
    checkResults: results,
    summary: { checksRun: checks, checksPassed: passedChecks },
    pass: behaviorPass,
  };
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  const temporaryReportPath = `${reportPath}.${process.pid}.${crypto.randomBytes(6).toString("hex")}.tmp`;
  let descriptor;
  try {
    descriptor = fs.openSync(temporaryReportPath, "wx");
    fs.writeFileSync(descriptor, `${JSON.stringify(report, null, 2)}\n`);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporaryReportPath, reportPath);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    if (fs.existsSync(temporaryReportPath)) fs.unlinkSync(temporaryReportPath);
  }
}

if (!behaviorPass) {
  if (failures.length === 0) {
    failures.push(
      `behavior report integrity failed: checks=${checks} results=${results.length} passed=${passedChecks} uniqueLabels=${new Set(labels).size} arch=${process.arch}`,
    );
  }
  console.error("native behavior comparison: FAIL");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("native behavior comparison: PASS");
console.log(`checks passed: ${checks}`);
console.log(`original modules: ${originalDir}`);
console.log(`rebuilt modules: ${rebuiltDir}`);
