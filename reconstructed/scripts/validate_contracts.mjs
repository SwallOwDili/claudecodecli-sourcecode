#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nativeDir = path.resolve(process.argv[2] ?? path.join(root, "..", "extracted"));
const contract = JSON.parse(fs.readFileSync(path.join(root, "contracts/module-exports.json"), "utf8"));
const modulesFlag = process.argv.indexOf("--modules");
const selectedModules = modulesFlag >= 0
  ? new Set((process.argv[modulesFlag + 1] ?? "").split(",").filter(Boolean))
  : null;
const failures = [];

if (modulesFlag >= 0 && selectedModules.size === 0) {
  console.error("--modules requires a comma-separated module list");
  process.exit(2);
}
if (selectedModules) {
  for (const filename of selectedModules) {
    if (!(filename in contract)) failures.push(`unknown contract module: ${filename}`);
  }
}

function ownFunctionNames(value) {
  return Object.entries(Object.getOwnPropertyDescriptors(value))
    .filter(([, descriptor]) => typeof descriptor.value === "function")
    .map(([name]) => name)
    .sort();
}

function compare(label, actual, expected) {
  const actualJson = JSON.stringify([...actual].sort());
  const expectedJson = JSON.stringify([...expected].sort());
  if (actualJson !== expectedJson) failures.push(`${label}: ${actualJson} != ${expectedJson}`);
}

const contractEntries = Object.entries(contract).filter(
  ([filename]) => !selectedModules || selectedModules.has(filename),
);
for (const [filename, expected] of contractEntries) {
  const loaded = require(path.join(nativeDir, filename));
  if (expected.functions) compare(`${filename} exports`, ownFunctionNames(loaded), expected.functions);
  if (expected.prototype) {
    const names = Object.getOwnPropertyNames(loaded.ImageProcessor.prototype).filter((name) => name !== "constructor");
    compare(`${filename} prototype`, names, expected.prototype);
  }
  if (expected.objects?.computerUse) {
    const computerUse = loaded.computerUse;
    compare(`${filename} computerUse`, ownFunctionNames(computerUse), expected.objects.computerUse.functions);
    for (const [group, functions] of Object.entries(expected.objects.computerUse.objects)) {
      compare(`${filename} computerUse.${group}`, ownFunctionNames(computerUse[group]), functions);
    }
  }
}

if (failures.length) {
  console.error("native contract validation: FAIL");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("native contract validation: PASS");
console.log(`modules checked: ${contractEntries.length}`);
