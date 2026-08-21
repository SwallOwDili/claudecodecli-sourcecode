import { existsSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

function findSnapshotRoot(importMetaUrl) {
  const scriptRoot = path.resolve(
    path.dirname(fileURLToPath(importMetaUrl)),
    "../../..",
  );
  const candidates = [process.env.CLAUDE_REPO, process.cwd(), scriptRoot]
    .filter(Boolean)
    .map((candidate) => path.resolve(candidate));
  for (const candidate of candidates) {
    if (
      existsSync(path.join(candidate, "VERSION"))
      && existsSync(path.join(candidate, "analysis/version.json"))
    ) {
      return candidate;
    }
  }
  throw new Error(
    "could not locate a snapshot root; run from the version branch or set CLAUDE_REPO",
  );
}

export function resolveProbeTarget(importMetaUrl) {
  const repo = findSnapshotRoot(importMetaUrl);
  const metadata = JSON.parse(
    readFileSync(path.join(repo, "analysis/version.json"), "utf8"),
  );
  const expectedVersion = process.env.CLAUDE_VERSION
    ?? readFileSync(path.join(repo, "VERSION"), "utf8").trim();
  const expectedSha256 = process.env.CLAUDE_SHA256 ?? metadata.binary?.sha256;
  if (!expectedVersion || !expectedSha256) {
    throw new Error("snapshot VERSION or analysis/version.json binary SHA-256 is missing");
  }
  const canonicalSource = readFileSync(path.join(repo, "extracted/cli.js"), "utf8");
  const gitShaMatch = canonicalSource.match(/GIT_SHA:"([0-9a-f]{40})"/);
  if (!gitShaMatch) {
    throw new Error("canonical bundle does not expose a 40-character GIT_SHA");
  }
  const binary = process.env.CLAUDE_BIN
    ?? path.join(os.homedir(), ".local/share/claude/versions", expectedVersion);
  return {
    repo,
    binary,
    expectedVersion,
    expectedSha256,
    expectedGitSha: gitShaMatch[1],
  };
}
