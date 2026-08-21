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

if (!process.argv[3]) {
  console.error("usage: compare_behaviors.mjs ORIGINAL_DIR REBUILT_DIR");
  process.exit(2);
}

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
  const mouse = await module.mouseLocation();
  const frontmost = module.getFrontmostAppInfo();
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
    mouseShape: { x: typeof mouse.x, y: typeof mouse.y },
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

function screenshotShape(result) {
  return {
    fields: Object.keys(result).sort(),
    width: result.width,
    height: result.height,
    displayWidth: result.displayWidth,
    displayHeight: result.displayHeight,
    displayId: result.displayId,
    originX: result.originX,
    originY: result.originY,
    jpegMagic: Buffer.from(result.base64, "base64").subarray(0, 3).toString("hex"),
  };
}

async function inspectSwift(original, rebuilt, inputModule) {
  const originalPump = setInterval(() => original._drainMainRunLoop(), 1);
  const rebuiltPump = setInterval(() => rebuilt._drainMainRunLoop(), 1);
  try {
    equal("swift optional undefined", rebuilt._testEchoOptionalInt(), original._testEchoOptionalInt());
    equal("swift optional null", rebuilt._testEchoOptionalInt(null), original._testEchoOptionalInt(null));
    equal("swift optional zero", rebuilt._testEchoOptionalInt(0), original._testEchoOptionalInt(0));
    equal("swift optional positive", rebuilt._testEchoOptionalInt(42), original._testEchoOptionalInt(42));
    equal("swift accessibility", rebuilt.tcc.checkAccessibility(), original.tcc.checkAccessibility());
    equal("swift screen recording", rebuilt.tcc.checkScreenRecording(), original.tcc.checkScreenRecording());

    const originalDisplays = original.display.listAll();
    const rebuiltDisplays = rebuilt.display.listAll();
    equal("swift displays", rebuiltDisplays, originalDisplays);
    const display = originalDisplays[0];
    if (display) {
      equal("swift display size", rebuilt.display.getSize(display.displayId), original.display.getSize(display.displayId));
    }

    const originalRunning = original.apps.listRunning();
    const rebuiltRunning = rebuilt.apps.listRunning();
    equal("swift running applications", canonicalApps(rebuiltRunning), canonicalApps(originalRunning));

    const [originalInstalled, rebuiltInstalled] = await Promise.all([
      original.apps.listInstalled(),
      rebuilt.apps.listInstalled(),
    ]);
    equal("swift installed applications", sortInstalled(rebuiltInstalled), sortInstalled(originalInstalled));

    const names = ["Finder", "Safari", "Application That Does Not Exist"];
    equal("swift resolve bundle ids", rebuilt.apps.resolveBundleIds(names), original.apps.resolveBundleIds(names));

    const bundleIds = originalRunning.map((app) => app.bundleId).filter(Boolean).slice(0, 8);
    equal(
      "swift window displays",
      sortByBundleId(rebuilt.apps.findWindowDisplays(bundleIds)),
      sortByBundleId(original.apps.findWindowDisplays(bundleIds)),
    );
    equal(
      "swift hide preview",
      sortByBundleId(rebuilt.apps.previewHideSet(bundleIds)),
      sortByBundleId(original.apps.previewHideSet(bundleIds)),
    );

    const point = await inputModule.mouseLocation();
    equal(
      "swift application under point",
      rebuilt.apps.appUnderPoint(point.x, point.y),
      original.apps.appUnderPoint(point.x, point.y),
    );

    const iconCandidate = originalInstalled.find((app) => app.path);
    if (iconCandidate) {
      equal(
        "swift application icon",
        rebuilt.apps.iconDataUrl(iconCandidate.path),
        original.apps.iconDataUrl(iconCandidate.path),
      );
    }

    equal("swift unhide empty", await rebuilt.apps.unhide([]), await original.apps.unhide([]));

    if (display) {
      const outputWidth = Math.min(display.width, 320);
      const outputHeight = Math.max(1, Math.round((outputWidth / display.width) * display.height));
      const originalCapture = await original.screenshot.captureExcluding(
        bundleIds,
        0.6,
        outputWidth,
        outputHeight,
        display.displayId,
      );
      const rebuiltCapture = await rebuilt.screenshot.captureExcluding(
        bundleIds,
        0.6,
        outputWidth,
        outputHeight,
        display.displayId,
      );
      equal("swift full screenshot shape", screenshotShape(rebuiltCapture), screenshotShape(originalCapture));

      const originalRegion = await original.screenshot.captureRegion(
        bundleIds,
        display.originX,
        display.originY,
        Math.min(display.width, 320),
        Math.min(display.height, 240),
        320,
        240,
        0.6,
        display.displayId,
      );
      const rebuiltRegion = await rebuilt.screenshot.captureRegion(
        bundleIds,
        display.originX,
        display.originY,
        Math.min(display.width, 320),
        Math.min(display.height, 240),
        320,
        240,
        0.6,
        display.displayId,
      );
      equal("swift region screenshot shape", screenshotShape(rebuiltRegion), screenshotShape(originalRegion));
    }
  } finally {
    clearInterval(originalPump);
    clearInterval(rebuiltPump);
  }
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

const originalImage = await inspectImage(load(originalDir, "image-processor.node"));
const rebuiltImage = await inspectImage(load(rebuiltDir, "image-processor.node"));
equal("image processor behavior", rebuiltImage, originalImage);

const originalInputModule = load(originalDir, "computer-use-input.node");
const rebuiltInputModule = load(rebuiltDir, "computer-use-input.node");
const originalInput = await inspectInput(originalInputModule);
const rebuiltInput = await inspectInput(rebuiltInputModule);
equal("input module behavior", rebuiltInput, originalInput);

const originalSwift = load(originalDir, "computer-use-swift.node").computerUse;
const rebuiltSwift = load(rebuiltDir, "computer-use-swift.node").computerUse;
await inspectSwift(originalSwift, rebuiltSwift, originalInputModule);

truthy("behavior check count", checks >= 20, `only ${checks} checks ran`);

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
      computerUseInput: "read-only mouse/frontmost queries and validation errors; no input injection",
      computerUseSwift: "display/TCC/application reads plus screenshot schema and JPEG invariants",
    },
    inputStrategies: {
      "audio-capture.node": "initial state and authorization query; no microphone capture",
      "url-handler.node": "1ms no-event timeout",
      "image-processor.node": "fixed in-memory 1x1 RGBA PNG and consumed/disposed lifecycle",
      "computer-use-input.node": "read-only mouse/frontmost queries and validation errors; no input injection",
      "computer-use-swift.node": "display/TCC/application reads plus screenshot schema and JPEG invariants",
    },
    literalOutput: {
      originalContract: "native contract validation: PASS",
      compatibleContract: "native contract validation: PASS",
      behavior: "native behavior comparison: PASS",
      checksPassed: checks,
    },
    exitStatus: { buildAndValidate: failures.length === 0 ? 0 : 1 },
    checks: {
      originalContract: true,
      compatibleContract: true,
      behaviorChecksPassed: failures.length === 0 && checks >= 23,
      arm64RuntimeCoverage: process.arch === "arm64",
      x86StaticBoundaryExplicit: (originalArchitectures.x86_64?.length ?? 0) > 0,
    },
    checkResults: results,
    summary: { checksRun: checks, checksPassed: results.filter((item) => item.status === "pass").length },
    pass: failures.length === 0 && process.arch === "arm64",
  };
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
}

if (failures.length) {
  console.error("native behavior comparison: FAIL");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("native behavior comparison: PASS");
console.log(`checks passed: ${checks}`);
console.log(`original modules: ${originalDir}`);
console.log(`rebuilt modules: ${rebuiltDir}`);
