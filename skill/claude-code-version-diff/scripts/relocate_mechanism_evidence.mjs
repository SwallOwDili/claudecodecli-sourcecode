#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

function usage() {
  console.error(
    "usage: CLAUDE_SOURCE_VERSION=OLD relocate_mechanism_evidence.mjs [REPO] [OVERRIDES_JSON] [--write]",
  );
  process.exit(2);
}

const positional = process.argv.slice(2).filter((value) => value !== "--write");
if (positional.length > 2) usage();

const repo = path.resolve(positional[0] ?? ".");
const overridesPath = positional[1]
  ? path.resolve(positional[1])
  : path.join(repo, "analysis/mechanism-anchor-overrides.json");
const shouldWrite = process.argv.includes("--write");
const evidencePath = path.join(repo, "analysis/mechanism-evidence.jsonl");
const targetVersion = fs.readFileSync(path.join(repo, "VERSION"), "utf8").trim();
const sourceVersion = process.env.CLAUDE_SOURCE_VERSION;

const records = fs.readFileSync(evidencePath, "utf8")
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line));
const overrides = fs.existsSync(overridesPath)
  ? JSON.parse(fs.readFileSync(overridesPath, "utf8"))
  : {};
const sourceCache = new Map();
const occurrenceCache = new Map();
const failures = [];
const changes = [];

function rewriteClaimVersion(claim) {
  if (typeof claim !== "string" || !sourceVersion || sourceVersion === targetVersion) {
    return claim;
  }
  return claim.replaceAll(sourceVersion, targetVersion);
}

function sourceLines(relative) {
  if (!sourceCache.has(relative)) {
    sourceCache.set(
      relative,
      fs.readFileSync(path.join(repo, relative), "utf8").split("\n"),
    );
  }
  return sourceCache.get(relative);
}

function occurrences(relative, anchor) {
  const key = `${relative}\0${anchor}`;
  if (!occurrenceCache.has(key)) {
    const hits = [];
    const lines = sourceLines(relative);
    for (let index = 0; index < lines.length; index += 1) {
      if (lines[index].includes(anchor)) hits.push(index + 1);
    }
    occurrenceCache.set(key, hits);
  }
  return occurrenceCache.get(key);
}

function smallestCover(lists, preferredLine) {
  const points = lists
    .flatMap((lines, anchorIndex) => lines.map((line) => ({ line, anchorIndex })))
    .sort((left, right) => left.line - right.line || left.anchorIndex - right.anchorIndex);
  const counts = Array(lists.length).fill(0);
  let covered = 0;
  let left = 0;
  let best = null;
  for (let right = 0; right < points.length; right += 1) {
    if (counts[points[right].anchorIndex]++ === 0) covered += 1;
    while (covered === lists.length) {
      const start = points[left].line;
      const end = points[right].line;
      const span = end - start;
      const distance = preferredLine === undefined
        ? start
        : Math.abs((start + end) / 2 - preferredLine);
      const isBetter = best === null || (preferredLine === undefined
        ? span < best.span
          || (span === best.span && start < best.start)
        : distance < best.distance
          || (distance === best.distance && span < best.span)
          || (distance === best.distance && span === best.span && start < best.start));
      if (isBetter) {
        best = { start, end, span, distance };
      }
      if (--counts[points[left].anchorIndex] === 0) covered -= 1;
      left += 1;
    }
  }
  return best;
}

for (const record of records) {
  if (record.evidenceClass !== "Static") {
    record.claim = rewriteClaimVersion(record.claim);
    continue;
  }
  const override = overrides[record.claimId] ?? {};
  for (const field of override.removeFields ?? []) delete record[field];
  Object.assign(record, override.fields ?? {});
  if (override.anchors) record.anchors = override.anchors;
  record.claim = rewriteClaimVersion(record.claim);
  const lists = record.anchors.map((anchor) => occurrences(record.path, anchor));
  const missing = record.anchors.filter((_, index) => lists[index].length === 0);
  if (missing.length > 0) {
    failures.push(`${record.claimId}: missing anchors: ${missing.join(" | ")}`);
    continue;
  }
  const preferredLine = override.preferredLine
    ?? (record.startLine + record.endLine) / 2;
  const range = override.startLine !== undefined && override.endLine !== undefined
    ? { start: override.startLine, end: override.endLine, span: override.endLine - override.startLine }
    : smallestCover(lists, preferredLine);
  if (!range) {
    failures.push(`${record.claimId}: could not cover all anchors`);
    continue;
  }
  const maxSpan = override.maxSpan ?? 250;
  if (range.span > maxSpan) {
    failures.push(`${record.claimId}: relocated span ${range.span} exceeds ${maxSpan}`);
    continue;
  }
  const before = `${record.startLine}-${record.endLine}`;
  record.startLine = range.start;
  record.endLine = range.end;
  changes.push(`${record.claimId}\t${before}\t${range.start}-${range.end}`);
}

if (failures.length > 0) {
  console.error("mechanism evidence relocation: FAIL");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

const output = `${records.map((record) => JSON.stringify(record)).join("\n")}\n`;
if (shouldWrite) fs.writeFileSync(evidencePath, output);
else process.stdout.write(output);
console.error(`mechanism evidence relocation: ${shouldWrite ? "WROTE" : "DRY RUN"}`);
console.error(`static records relocated: ${changes.length}`);
for (const change of changes) console.error(change);
