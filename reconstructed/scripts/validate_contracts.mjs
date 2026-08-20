#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nativeDir = path.resolve(process.argv[2] ?? path.join(root, "..", "extracted"));
const contract = JSON.parse(fs.readFileSync(path.join(root, "contracts/module-exports.json"), "utf8"));
const failures = [];

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

for (const [filename, expected] of Object.entries(contract)) {
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
console.log(`modules checked: ${Object.keys(contract).length}`);
