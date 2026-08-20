#!/usr/bin/env node

import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const modulePath = path.resolve(process.argv[2] ?? "extracted/computer-use-swift.node");
const inputPath = process.argv[3] ? path.resolve(process.argv[3]) : null;
const { computerUse } = require(modulePath);
const runLoopPump = setInterval(() => computerUse._drainMainRunLoop(), 1);

function summarize(value) {
  if (Array.isArray(value)) {
    return {
      kind: "array",
      count: value.length,
      sample: value.slice(0, 3),
    };
  }
  if (typeof value === "string" && value.startsWith("data:image/")) {
    return {
      kind: "data-url",
      prefix: value.slice(0, 32),
      length: value.length,
    };
  }
  if (value && typeof value === "object") {
    const result = { ...value };
    if (typeof result.base64 === "string") {
      result.base64 = {
        prefix: result.base64.slice(0, 24),
        length: result.base64.length,
      };
    }
    return result;
  }
  return value;
}

async function record(label, operation) {
  try {
    const value = await operation();
    console.log(`${label}: ${JSON.stringify(summarize(value))}`);
    return value;
  } catch (error) {
    console.log(`${label}: ERROR ${error?.message ?? String(error)}`);
    return undefined;
  }
}

await record("optional.undefined", () => computerUse._testEchoOptionalInt());
await record("optional.null", () => computerUse._testEchoOptionalInt(null));
await record("optional.zero", () => computerUse._testEchoOptionalInt(0));
await record("optional.positive", () => computerUse._testEchoOptionalInt(42));
await record("tcc.accessibility", () => computerUse.tcc.checkAccessibility());
await record("tcc.screenRecording", () => computerUse.tcc.checkScreenRecording());

const displays = await record("display.listAll", () => computerUse.display.listAll());
const display = Array.isArray(displays) ? displays[0] : undefined;
if (display) {
  await record("display.getSize", () => computerUse.display.getSize(display.displayId));
}

const running = await record("apps.listRunning", () => computerUse.apps.listRunning());
const installed = await record("apps.listInstalled", () => computerUse.apps.listInstalled());
await record("apps.resolveBundleIds", () =>
  computerUse.apps.resolveBundleIds(["Finder", "Safari", "Application That Does Not Exist"]),
);

const runningBundleIds = Array.isArray(running)
  ? running.map((app) => app.bundleId).filter(Boolean).slice(0, 5)
  : [];
await record("apps.findWindowDisplays", () =>
  computerUse.apps.findWindowDisplays(runningBundleIds),
);
await record("apps.previewHideSet", () =>
  computerUse.apps.previewHideSet(runningBundleIds),
);

if (inputPath) {
  const input = require(inputPath);
  const point = await input.mouseLocation();
  await record("apps.appUnderPoint", () => computerUse.apps.appUnderPoint(point.x, point.y));
}

const iconCandidate = Array.isArray(installed) ? installed.find((app) => app.path) : undefined;
if (iconCandidate) {
  await record("apps.iconDataUrl", () => computerUse.apps.iconDataUrl(iconCandidate.path));
}

if (display) {
  const outputWidth = Math.min(display.width, 320);
  const outputHeight = Math.max(1, Math.round((outputWidth / display.width) * display.height));
  await record("screenshot.captureExcluding", () =>
    computerUse.screenshot.captureExcluding(
      runningBundleIds,
      0.6,
      outputWidth,
      outputHeight,
      display.displayId,
    ),
  );
  await record("screenshot.captureRegion", () =>
    computerUse.screenshot.captureRegion(
      runningBundleIds,
      display.originX,
      display.originY,
      Math.min(display.width, 320),
      Math.min(display.height, 240),
      320,
      240,
      0.6,
      display.displayId,
    ),
  );
}

computerUse._drainMainRunLoop();
clearInterval(runLoopPump);
