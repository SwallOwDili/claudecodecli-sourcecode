#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const parser = path.join(scriptDirectory, "parse_javascript_surface.mjs");
const temporaryDirectory = fs.mkdtempSync(
  path.join(os.tmpdir(), "claude-dynamic-env-resolver-"),
);
const fixture = path.join(temporaryDirectory, "fixture.js");
const source = `
var FORWARD;
function readForward() { return process.env[FORWARD]; }
FORWARD = "FORWARD_NAME";
readForward();

const namespace = {};
namespace.KEY = void 0;
namespace.KEY = "MEMBER_NAME";
function readMember() { return process.env[namespace.KEY]; }
readMember();

const MAP = {
  first: { name: "MAP_ONE" },
  second: { name: "MAP_TWO" },
};
function readMap() {
  for (const item of Object.values(MAP)) console.log(process.env[item.name]);
}

const ENTRIES = { ENTRY_ONE: "one", ENTRY_TWO: "two" };
function readEntries() {
  for (const [key, value] of Object.entries(ENTRIES)) console.log(process.env[key], value);
}

const BASE = ["SET_ONE"];
const MORE = ["SET_TWO"];
const KEY_SET = new Set([...BASE, ...MORE, ...Object.keys({ SET_THREE: true })]);
function readSet() {
  for (const key of KEY_SET) console.log(process.env[key]);
}

const PREFIX = "CLAUDE_";
const SUFFIX = "CONCAT";
function readConcat() { return process.env[PREFIX + SUFFIX]; }
function readTemplate() { return process.env[\`\${PREFIX}TEMPLATE\`]; }
function fixedName() { return "FUNCTION_NAME"; }
function readFunction() { return process.env[fixedName()]; }
function destructured({ envName }) { return process.env[envName]; }
destructured({ envName: "DESTRUCTURED_NAME" });
const CALLBACK_NAMES = ["CALLBACK_ONE", "CALLBACK_TWO"];
function namedCallback(envName) { return process.env[envName]; }
CALLBACK_NAMES.map(namedCallback);

function runtimeName(name) { return process.env[name]; }
runtimeName(process.argv[2]);
let replaced = "INITIAL_NAME";
replaced = process.argv[3];
function readReplaced() { return process.env[replaced]; }
function runtimeMember(config) { return process.env[config.name]; }
runtimeMember(JSON.parse(process.argv[4] || "{}"));

function read(name) { return process.env[name]; }
read("INCOMPLETE_STATIC_NAME");
const alias = read;
alias(process.argv[2]);

var LATE_NAME;
readLate();
LATE_NAME = "LATE_STATIC_NAME";
function readLate() { return process.env[LATE_NAME]; }
readLate();

const lateNamespace = {};
readLateMember();
lateNamespace.KEY = "LATE_MEMBER_NAME";
function readLateMember() { return process.env[lateNamespace.KEY]; }
readLateMember();

var CROSS_SCOPE_NAME = "INITIAL_CROSS_SCOPE_NAME";
function readCrossScope() { return process.env[CROSS_SCOPE_NAME]; }
function mutateCrossScope() { CROSS_SCOPE_NAME = process.argv[3]; }
readCrossScope();
mutateCrossScope();
readCrossScope();

const mutableNamespace = {};
mutableNamespace.KEY = "INITIAL_CROSS_SCOPE_MEMBER";
function readCrossScopeMember() { return process.env[mutableNamespace.KEY]; }
function mutateCrossScopeMember() { mutableNamespace.KEY = process.argv[4]; }
readCrossScopeMember();
mutateCrossScopeMember();
readCrossScopeMember();
`;

function values(row) {
  if (Object.hasOwn(row, "resolvedStaticValue")) return [row.resolvedStaticValue];
  return row.resolvedFiniteValues ?? null;
}

try {
  fs.writeFileSync(fixture, source);
  const result = spawnSync(process.execPath, [parser, fixture, "{}"], {
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr);
  const parsed = JSON.parse(result.stdout);
  const rowFor = (expression, functionName) =>
    parsed.environmentAccesses.find(
      (row) =>
        source.slice(row.expressionStart, row.expressionEnd) === expression &&
        row.function === functionName,
    );

  assert.deepEqual(values(rowFor("FORWARD", "readForward")), ["FORWARD_NAME"]);
  assert.deepEqual(values(rowFor("namespace.KEY", "readMember")), ["MEMBER_NAME"]);
  assert.deepEqual(values(rowFor("item.name", "readMap")), ["MAP_ONE", "MAP_TWO"]);
  assert.deepEqual(values(rowFor("key", "readEntries")), ["ENTRY_ONE", "ENTRY_TWO"]);
  assert.deepEqual(values(rowFor("PREFIX + SUFFIX", "readConcat")), ["CLAUDE_CONCAT"]);
  assert.deepEqual(values(rowFor("`${PREFIX}TEMPLATE`", "readTemplate")), ["CLAUDE_TEMPLATE"]);
  assert.deepEqual(values(rowFor("fixedName()", "readFunction")), ["FUNCTION_NAME"]);
  assert.deepEqual(values(rowFor("envName", "destructured")), ["DESTRUCTURED_NAME"]);
  assert.deepEqual(values(rowFor("envName", "namedCallback")), ["CALLBACK_ONE", "CALLBACK_TWO"]);

  const setRow = rowFor("key", "readSet");
  assert.deepEqual(values(setRow), ["SET_ONE", "SET_THREE", "SET_TWO"]);

  for (const expression of [
    "name",
    "replaced",
    "config.name",
    "LATE_NAME",
    "lateNamespace.KEY",
    "CROSS_SCOPE_NAME",
    "mutableNamespace.KEY",
  ]) {
    const row = parsed.environmentAccesses.find(
      (candidate) =>
        source.slice(candidate.expressionStart, candidate.expressionEnd) === expression &&
        candidate.function !== "readEntries",
    );
    assert.equal(values(row), null, `${expression} must remain unresolved`);
    assert.equal(row.unresolvedResolution?.complete, false);
  }
  const escapedRow = rowFor("name", "read");
  assert.equal(values(escapedRow), null, "escaped function parameters are not exhaustive");
  assert.equal(escapedRow.unresolvedResolution?.complete, false);
  assert.equal(
    escapedRow.unresolvedResolution?.primaryReason,
    "untraced-function-reference",
  );
  for (const [expression, functionName] of [
    ["LATE_NAME", "readLate"],
    ["lateNamespace.KEY", "readLateMember"],
    ["CROSS_SCOPE_NAME", "readCrossScope"],
    ["mutableNamespace.KEY", "readCrossScopeMember"],
  ]) {
    const row = rowFor(expression, functionName);
    assert.equal(
      row.unresolvedResolution?.primaryReason,
      "assignment-does-not-dominate-function-executions",
    );
  }

  process.stdout.write(
    "dynamic environment resolver fixture: PASS (10 finite strategies, 8 runtime boundaries)\n",
  );
} finally {
  fs.rmSync(temporaryDirectory, { recursive: true, force: true });
}
