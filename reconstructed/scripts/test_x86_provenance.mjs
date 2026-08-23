#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDirectory, "../..");
const originalDirectory = path.join(repoRoot, "extracted");
const committedReportPath = path.join(
  repoRoot,
  "analysis/runtime-probes/native-reconstruction-x86.json",
);
const fakeDirectory = fs.mkdtempSync(
  path.join(os.tmpdir(), "claude-native-x86-forgery-"),
);
const reportPath = path.join(fakeDirectory, "forged-report.json");
const modules = [
  "audio-capture.node",
  "computer-use-input.node",
  "computer-use-swift.node",
  "image-processor.node",
  "url-handler.node",
];

function validateCommittedAttestationScope() {
  const report = JSON.parse(fs.readFileSync(committedReportPath, "utf8"));
  assert.equal(
    report.architectureCoverage?.compatible?.x86_64?.method,
    "validated-artifacts-and-runtime",
  );
  assert.deepEqual(
    report.architectureCoverage?.compatible?.x86_64
      ?.validatedArtifactContractModules,
    modules,
  );
  assert.equal(report.attestationScope?.method, "validated-artifacts-and-runtime");
  assert.ok(
    report.attestationScope.doesNotProve.some((item) =>
      item.includes("freshly built"),
    ),
  );
  assert.deepEqual(Object.keys(report.commands), ["behavior"]);
  assert.deepEqual(Object.keys(report.exitStatus), ["behavior"]);
  assert.deepEqual(Object.keys(report.literalOutput).sort(), [
    "behavior",
    "checksPassed",
  ]);
  assert.deepEqual(Object.keys(report.buildRecipes).sort(), [
    "rustBuild",
    "swiftBuild",
  ]);
  assert.match(report.buildRecipeSemantics, /Reference recipes only/);
  for (const field of ["rustBuild", "swiftBuild"]) {
    assert.equal(field in report.commands, false);
    assert.equal(field in report.exitStatus, false);
    assert.equal(field in report.literalOutput, false);
  }
}

try {
  validateCommittedAttestationScope();
  for (const filename of modules) {
    fs.symlinkSync(
      path.join(originalDirectory, filename),
      path.join(fakeDirectory, filename),
    );
  }
  const result = spawnSync(
    "/usr/bin/arch",
    [
      "-x86_64",
      process.execPath,
      path.join(scriptDirectory, "compare_behaviors.mjs"),
      originalDirectory,
      fakeDirectory,
      "--x86-dual-only",
      "--report",
      reportPath,
    ],
    { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 },
  );
  assert.notEqual(result.status, 0, "forged original-module symlinks were accepted");
  assert.match(
    result.stderr,
    /must not be a symlink|reuses original module bytes/,
    result.stderr,
  );
  assert.equal(fs.existsSync(reportPath), false, "forged PASS report was written");
  process.stdout.write("native x86 provenance forgery test: PASS\n");
} finally {
  fs.rmSync(fakeDirectory, { recursive: true, force: true });
}
