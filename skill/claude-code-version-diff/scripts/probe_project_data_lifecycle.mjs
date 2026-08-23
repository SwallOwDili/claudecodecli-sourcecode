#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  readdir,
  rm,
  utimes,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const FIXED_TIME = new Date("2026-01-02T03:04:05.000Z");
const IMPORT_GATE_MESSAGE = "`claude import` is not yet available in this build. Run `claude` and use /mcp or edit ~/.claude/settings.json directly.";
const TARGET_VERSION = "2.1.235";
const TARGET_BINARY_SHA256 = "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748";
const PURGE_OWNED_TARGETS = ["projects", "tasks", "debug", "file-history", "history.jsonl"];
const PURGE_EXCLUDED_FIXTURES = ["shell-snapshots/keep.txt", "backups/keep.txt"];
const TRANSCRIPT_CANONICAL_EXPECTATIONS = {
  jsonImport: {
    bytes: 1216,
    sha256: "bbf01984050eecc6f52f0c4ead7b1f7758a7406b7f13ca7cd381c1a7f7aac6b0",
  },
  zipManifestMismatch: {
    bytes: 1216,
    sha256: "4d37df6304dce933a30a4550aa142ad16152c4fef5fe092c849713f7cb1836db",
  },
};

function run(binary, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, options);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", (exitStatus, signal) => {
      resolve({ exitStatus, signal, stdout, stderr });
    });
  });
}

function sha256Bytes(data) {
  return createHash("sha256").update(data).digest("hex");
}

async function sha256File(file) {
  return sha256Bytes(await readFile(file));
}

function modeString(mode) {
  return (mode & 0o777).toString(8).padStart(3, "0");
}

async function exists(target) {
  try {
    await lstat(target);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function inventory(root) {
  if (!await exists(root)) return [];
  const rows = [];
  async function visit(current, relative) {
    const metadata = await lstat(current);
    if (relative) {
      const row = {
        path: relative.split(path.sep).join("/"),
        kind: metadata.isDirectory() ? "directory" : metadata.isSymbolicLink() ? "symlink" : "file",
        mode: modeString(metadata.mode),
      };
      if (metadata.isFile()) {
        row.bytes = metadata.size;
        row.sha256 = await sha256File(current);
      }
      if (metadata.isSymbolicLink()) row.target = await readFile(current, "utf8").catch(() => "<unreadable>");
      rows.push(row);
    }
    if (!metadata.isDirectory()) return;
    const entries = await readdir(current, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      await visit(path.join(current, entry.name), relative ? path.join(relative, entry.name) : entry.name);
    }
  }
  await visit(root, "");
  return rows;
}

function deepEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function inventoryDelta(before, after) {
  const beforeByPath = new Map(before.map((row) => [row.path, row]));
  const afterByPath = new Map(after.map((row) => [row.path, row]));
  const paths = [...new Set([...beforeByPath.keys(), ...afterByPath.keys()])].sort();
  return paths.flatMap((entryPath) => {
    const left = beforeByPath.get(entryPath);
    const right = afterByPath.get(entryPath);
    if (deepEqual(left, right)) return [];
    return [{
      path: entryPath,
      change: left === undefined ? "added" : right === undefined ? "removed" : "changed",
    }];
  });
}

function rowsForPaths(rows, paths) {
  return rows.filter((row) => paths.some((entryPath) => (
    row.path === entryPath || row.path.startsWith(`${entryPath}/`)
  )));
}

function exactRows(rows, paths) {
  return paths.map((entryPath) => rows.find((row) => row.path === entryPath) ?? null);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function makeNormalizer(replacements) {
  const ordered = [...replacements].sort((left, right) => right[0].length - left[0].length);
  return (value) => {
    let output = String(value).replace(/\x1b\[[0-9;]*m/g, "");
    for (const [actual, label] of ordered) {
      output = output.replace(new RegExp(escapeRegExp(actual), "g"), label);
    }
    output = output.replace(
      /(projects\/)[^/"\s]+\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl)/gi,
      "$1$PROJECT_KEY/$2",
    );
    return output.trimEnd();
  };
}

function normalizeValue(value, normalize) {
  if (typeof value === "string") return normalize(value);
  if (Array.isArray(value)) return value.map((entry) => normalizeValue(entry, normalize));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, normalizeValue(entry, normalize)]),
    );
  }
  return value;
}

function shellQuote(value) {
  if (value === "") return "''";
  if (/^[A-Za-z0-9_./:$-]+$/.test(value)) return value;
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function renderReproductionCommand(contract) {
  const environment = Object.entries(contract.environment)
    .map(([key, value]) => `${key}=${shellQuote(value)}`)
    .join(" ");
  return [
    "env -i",
    environment,
    shellQuote(contract.executable),
    ...contract.argv.map(shellQuote),
  ].join(" ");
}

async function runCli(binary, args, { cwd, workspace, home, configDir, tempDir, importConversations = false, normalize }) {
  const executionCwd = cwd ?? workspace;
  const env = cliEnv({ home, configDir, tempDir, importConversations });
  const result = await run(binary, args, {
    cwd: executionCwd,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const contract = normalizeValue({
    executable: binary,
    argv: args,
    cwd: executionCwd,
    stdin: "ignored",
    environmentMode: "replace",
    environment: Object.fromEntries(Object.entries(env).sort(([left], [right]) => left.localeCompare(right))),
  }, normalize);
  return {
    ...result,
    contract,
    reproductionCommand: renderReproductionCommand(contract),
  };
}

function normalizeInventoryRows(rows) {
  return rows.map((row) => {
    const normalizedPath = row.kind === "directory" && !row.path.includes("/")
      ? "$PROJECT_KEY"
      : row.path.replace(
        /^([^/]*\/)?([^/]+)\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl)$/i,
        "$1$PROJECT_KEY/$3",
      );
    return { ...row, path: normalizedPath };
  });
}

function useCanonicalTranscriptHash(rows, evidence) {
  return normalizeInventoryRows(rows).map((row) => {
    if (!row.path.endsWith(".jsonl") || evidence === null) return row;
    const { sha256: _rawSha256, ...stableRow } = row;
    return {
      ...stableRow,
      contentSha256: evidence.canonicalContentSha256,
      hashBasis: "normalized transcript bytes",
    };
  });
}

function normalizeStartupPath(entryPath) {
  return entryPath.replace(/^backups\/\.claude\.json\.backup\..+$/, "backups/$AUTO_BACKUP");
}

function startupChanges(before, after) {
  return inventoryDelta(before, after)
    .filter((change) => !PURGE_OWNED_TARGETS.some((entryPath) => (
      change.path === entryPath || change.path.startsWith(`${entryPath}/`)
    )))
    .filter((change) => !PURGE_EXCLUDED_FIXTURES.includes(change.path))
    .map((change) => ({ ...change, path: normalizeStartupPath(change.path) }));
}

function purgeDomainRows(rows) {
  return rows.filter((row) => (
    row.path !== ".claude.json"
    && !row.path.startsWith("backups/.claude.json.backup.")
    && row.path !== "secure-storage"
    && !row.path.startsWith("secure-storage/")
  ));
}

async function findFiles(root, predicate) {
  if (!await exists(root)) return [];
  const found = [];
  async function visit(current) {
    const metadata = await lstat(current);
    if (metadata.isFile()) {
      if (predicate(current)) found.push(current);
      return;
    }
    if (!metadata.isDirectory()) return;
    const entries = await readdir(current, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) await visit(path.join(current, entry.name));
  }
  await visit(root);
  return found;
}

async function transcriptSummary(file) {
  const events = (await readFile(file, "utf8"))
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  return events.map((event) => {
    const content = event.message?.content;
    const text = typeof content === "string"
      ? content
      : Array.isArray(content)
        ? content.find((block) => block.type === "text")?.text
        : undefined;
    return {
      type: event.type,
      uuid: event.uuid,
      parentUuid: event.parentUuid,
      role: event.message?.role,
      text,
      version: event.version,
    };
  });
}

async function transcriptEvidence(file, normalize) {
  const metadata = await lstat(file);
  const raw = await readFile(file, "utf8");
  const canonical = normalize(raw);
  return {
    path: normalize(file),
    mode: modeString(metadata.mode),
    bytes: Buffer.byteLength(raw),
    canonicalBytes: Buffer.byteLength(canonical),
    canonicalContentSha256: sha256Bytes(canonical),
    hashBasis: "UTF-8 transcript after normalization of probe cwd, config, HOME and temporary-root paths",
    records: await transcriptSummary(file),
  };
}

async function artifactEvidence(root, relative, expectedContent) {
  const file = path.join(root, relative);
  if (!await exists(file)) {
    return {
      path: relative,
      exists: false,
      expectedBytes: Buffer.byteLength(expectedContent),
      expectedContentSha256: sha256Bytes(expectedContent),
    };
  }
  const metadata = await lstat(file);
  const content = await readFile(file, "utf8");
  return {
    path: relative,
    exists: true,
    mode: modeString(metadata.mode),
    bytes: Buffer.byteLength(content),
    contentSha256: sha256Bytes(content),
    expectedBytes: Buffer.byteLength(expectedContent),
    expectedContentSha256: sha256Bytes(expectedContent),
    contentMatchesExpected: content === expectedContent,
  };
}

function expectedTranscriptRecords(fixture) {
  return fixture.conversations[0].chat_messages.map((message) => ({
    type: message.sender === "human" ? "user" : "assistant",
    uuid: message.uuid,
    parentUuid: message.parent_message_uuid,
    role: message.sender === "human" ? "user" : "assistant",
    text: message.text,
    version: "claude-export-import",
  }));
}

function parsePurgePlan(stdout, configLabel) {
  return stdout.split("\n").flatMap((line) => {
    const match = line.match(/^\s*(dir|file):\s+(.+?)\s*$/);
    if (!match) return [];
    const absolutePath = match[2];
    const prefix = `${configLabel}/`;
    return [{
      kind: match[1],
      path: absolutePath,
      ownedTarget: absolutePath.startsWith(prefix) ? absolutePath.slice(prefix.length) : null,
    }];
  });
}

async function writeFixtureFile(file, content, mode = 0o600) {
  await mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  await writeFile(file, content, { encoding: "utf8", mode });
  await chmod(file, mode);
  await utimes(file, FIXED_TIME, FIXED_TIME);
}

function createArchiveFixture({ manifestMismatch = false } = {}) {
  const projectUuid = manifestMismatch
    ? "20000000-0000-4000-8000-000000000002"
    : "10000000-0000-4000-8000-000000000001";
  const conversationUuid = manifestMismatch
    ? "40000000-0000-4000-8000-000000000004"
    : "30000000-0000-4000-8000-000000000003";
  const humanUuid = manifestMismatch
    ? "60000000-0000-4000-8000-000000000006"
    : "50000000-0000-4000-8000-000000000005";
  const assistantUuid = manifestMismatch
    ? "80000000-0000-4000-8000-000000000008"
    : "70000000-0000-4000-8000-000000000007";
  const fileUuid = "90000000-0000-4000-8000-000000000009";
  const markerPrefix = manifestMismatch ? "ZIP_MISMATCH" : "JSON_IMPORT";
  const conversations = [{
    uuid: conversationUuid,
    name: `${markerPrefix} conversation`,
    created_at: "2026-01-02T03:04:05.000Z",
    updated_at: "2026-01-02T03:05:06.000Z",
    project_uuid: projectUuid,
    chat_messages: [
      {
        uuid: humanUuid,
        parent_message_uuid: null,
        sender: "human",
        text: `${markerPrefix}_HUMAN_MARKER`,
        content: [{ type: "text", text: `${markerPrefix}_HUMAN_MARKER` }],
        created_at: "2026-01-02T03:04:05.000Z",
        attachments: [],
        files: [],
      },
      {
        uuid: assistantUuid,
        parent_message_uuid: humanUuid,
        sender: "assistant",
        text: `${markerPrefix}_ASSISTANT_MARKER`,
        content: [{ type: "text", text: `${markerPrefix}_ASSISTANT_MARKER` }],
        created_at: "2026-01-02T03:05:06.000Z",
        attachments: [],
        files: [],
      },
    ],
  }];
  const projects = [{
    uuid: projectUuid,
    name: manifestMismatch ? "ZIP Mismatch Project" : "JSON Import Project",
    prompt_template: `${markerPrefix}_PROJECT_INSTRUCTIONS`,
    docs: [{ filename: "CLAUDE.md", content: `${markerPrefix}_RESERVED_DOC_MARKER` }],
    files: manifestMismatch ? [{ file_uuid: fileUuid, file_name: "AGENTS.md" }] : [],
  }];
  const manifest = {
    account_uuid: "00000000-0000-4000-8000-000000000000",
    conversations: [{
      uuid: conversationUuid,
      message_count: manifestMismatch ? 3 : 2,
    }],
    projects: [{
      uuid: projectUuid,
      doc_count: manifestMismatch ? 2 : 1,
    }],
  };
  return {
    manifest,
    conversations,
    projects,
    files: manifestMismatch ? { [fileUuid]: `${markerPrefix}_PROJECT_FILE_MARKER\n` } : {},
  };
}

async function createZipFixture(directory, archive, fixture) {
  await mkdir(path.join(directory, "files"), { recursive: true, mode: 0o700 });
  const files = [
    ["conversations.json", `${JSON.stringify(fixture.conversations, null, 2)}\n`],
    ["projects.json", `${JSON.stringify(fixture.projects, null, 2)}\n`],
    ["manifest.json", `${JSON.stringify(fixture.manifest, null, 2)}\n`],
    ["users.json", `${JSON.stringify([{ uuid: fixture.manifest.account_uuid }], null, 2)}\n`],
  ];
  for (const [name, content] of files) await writeFixtureFile(path.join(directory, name), content);
  for (const [name, content] of Object.entries(fixture.files)) {
    await writeFixtureFile(path.join(directory, "files", name), content);
    files.push([`files/${name}`, content]);
  }
  const zipRun = await run("/usr/bin/zip", ["-X", "-q", archive, ...files.map(([name]) => name)], {
    cwd: directory,
    env: { PATH: "/usr/bin:/bin" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (zipRun.exitStatus !== 0) throw new Error(`zip fixture creation failed: ${zipRun.stderr}`);
}

function cliEnv({ home, configDir, tempDir, importConversations = false }) {
  return {
    PATH: "/usr/bin:/bin:/usr/sbin:/sbin",
    HOME: home,
    USERPROFILE: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    TMPDIR: tempDir,
    SHELL: "/bin/zsh",
    LANG: "en_US.UTF-8",
    LC_ALL: "en_US.UTF-8",
    TERM: "dumb",
    NO_COLOR: "1",
    CI: "1",
    CLAUDE_CONFIG_DIR: configDir,
    CLAUDE_SECURESTORAGE_CONFIG_DIR: path.join(configDir, "secure-storage"),
    CLAUDE_IMPORT_CONVERSATIONS: importConversations ? "1" : "",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
    DISABLE_GROWTHBOOK: "1",
    ANTHROPIC_API_KEY: "",
    ANTHROPIC_AUTH_TOKEN: "",
    CLAUDE_CODE_OAUTH_TOKEN: "",
    CLAUDE_CODE_SESSION_ACCESS_TOKEN: "",
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
    GIT_TERMINAL_PROMPT: "0",
    GIT_ASKPASS: "/usr/bin/false",
    SSH_ASKPASS: "/usr/bin/false",
  };
}

function createPurgeFixture(markerPrefix) {
  return {
    ownedTargets: [...PURGE_OWNED_TARGETS],
    excludedFixtures: [...PURGE_EXCLUDED_FIXTURES],
    directories: ["projects", "tasks", "debug", "file-history", "shell-snapshots", "backups"],
    files: {
      "projects/project-marker/session.jsonl": `${markerPrefix}_TRANSCRIPT_MARKER\n`,
      "tasks/task-marker/task.json": `${markerPrefix}_TASK_MARKER\n`,
      "debug/debug-marker.txt": `${markerPrefix}_DEBUG_MARKER\n`,
      "file-history/history-marker/snapshot": `${markerPrefix}_FILE_HISTORY_MARKER\n`,
      "history.jsonl": `{"project":"/synthetic/project","display":"${markerPrefix}_PROMPT_MARKER"}\n`,
      "shell-snapshots/keep.txt": `${markerPrefix}_SHELL_SNAPSHOT_KEEP_MARKER\n`,
      "backups/keep.txt": `${markerPrefix}_BACKUP_KEEP_MARKER\n`,
    },
  };
}

async function seedPurgeFixture(configDir, fixture) {
  for (const directory of fixture.directories) {
    await mkdir(path.join(configDir, directory), { recursive: true, mode: 0o700 });
  }
  for (const [name, content] of Object.entries(fixture.files)) {
    await writeFixtureFile(path.join(configDir, name), content);
  }
}

function exactArtifactMatches(evidence) {
  return evidence.exists === true
    && evidence.mode === "600"
    && evidence.bytes === evidence.expectedBytes
    && evidence.contentSha256 === evidence.expectedContentSha256
    && evidence.contentMatchesExpected === true;
}

function environmentContractIsComplete(contract) {
  const env = contract.environment;
  return contract.environmentMode === "replace"
    && contract.stdin === "ignored"
    && contract.executable === "$CLAUDE_TARGET"
    && Array.isArray(contract.argv)
    && contract.argv.length > 0
    && typeof contract.cwd === "string"
    && contract.cwd.startsWith("$")
    && typeof env.HOME === "string"
    && env.HOME.startsWith("$")
    && typeof env.TMPDIR === "string"
    && env.TMPDIR.startsWith("$")
    && typeof env.CLAUDE_CONFIG_DIR === "string"
    && env.CLAUDE_CONFIG_DIR.startsWith("$")
    && env.CLAUDE_SECURESTORAGE_CONFIG_DIR === `${env.CLAUDE_CONFIG_DIR}/secure-storage`
    && env.DISABLE_GROWTHBOOK === "1"
    && env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC === "1"
    && env.ANTHROPIC_API_KEY === ""
    && env.ANTHROPIC_AUTH_TOKEN === ""
    && env.CLAUDE_CODE_OAUTH_TOKEN === ""
    && env.CLAUDE_CODE_SESSION_ACCESS_TOKEN === ""
    && env.GIT_CONFIG_NOSYSTEM === "1"
    && env.GIT_CONFIG_GLOBAL === "/dev/null"
    && env.GIT_TERMINAL_PROMPT === "0"
    && env.GIT_ASKPASS === "/usr/bin/false"
    && env.SSH_ASKPASS === "/usr/bin/false";
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-project-data-probe-"));
  let report;
  try {
    const scenarioLabels = {
      version: "VERSION",
      purgeDryRun: "PURGE_DRY",
      purgePositive: "PURGE_POSITIVE",
      jsonDryRun: "JSON_DRY",
      jsonImport: "JSON",
      zipManifestMismatch: "ZIP",
      configImportBoundary: "CONFIG_IMPORT",
    };
    const scenarios = Object.fromEntries(Object.entries(scenarioLabels).map(([name, label]) => {
      const root = path.join(temporary, "scenarios", name);
      return [name, {
        label,
        root,
        home: path.join(root, "home"),
        tempDir: path.join(root, "tmp"),
        configDir: path.join(root, "config"),
        workspace: path.join(root, "workspace"),
        target: path.join(root, "target"),
      }];
    }));
    const fixtures = path.join(temporary, "fixtures");
    const zipRoot = path.join(fixtures, "zip-root");
    const jsonArchive = path.join(fixtures, "conversations.json");
    const zipArchive = path.join(fixtures, "conversations-mismatch.zip");
    await Promise.all([
      fixtures,
      zipRoot,
      ...Object.values(scenarios).flatMap((scenario) => [
        scenario.home,
        path.join(scenario.home, ".config"),
        scenario.tempDir,
        scenario.configDir,
        scenario.workspace,
        scenario.target,
      ]),
    ].map((directory) => mkdir(directory, { recursive: true, mode: 0o700 })));

    const canonicalTemporary = await realpath(temporary);
    const replacements = [
      [jsonArchive, "$JSON_ARCHIVE"],
      [zipArchive, "$ZIP_ARCHIVE"],
      [fixtures, "$FIXTURES"],
      ...Object.values(scenarios).flatMap((scenario) => [
        [scenario.configDir, `$${scenario.label}_CONFIG`],
        [scenario.workspace, `$${scenario.label}_WORKSPACE`],
        [scenario.target, `$${scenario.label}_TARGET`],
        [scenario.tempDir, `$${scenario.label}_TMPDIR`],
        [scenario.home, `$${scenario.label}_HOME`],
        [scenario.root, `$${scenario.label}_ROOT`],
      ]),
      [temporary, "$PROBE_ROOT"],
      [binary, "$CLAUDE_TARGET"],
    ];
    if (canonicalTemporary !== temporary) {
      for (const [actual, label] of [...replacements]) {
        if (actual === temporary || actual.startsWith(`${temporary}${path.sep}`)) {
          replacements.push([`${canonicalTemporary}${actual.slice(temporary.length)}`, label]);
        }
      }
    }
    const normalize = makeNormalizer(replacements);

    const versionRun = await runCli(binary, ["--version"], {
      ...scenarios.version,
      normalize,
    });

    const purgeInput = createPurgeFixture("PURGE_DRY");
    await seedPurgeFixture(scenarios.purgeDryRun.configDir, purgeInput);
    const purgeBeforeFull = await inventory(scenarios.purgeDryRun.configDir);
    const purgeRun = await runCli(binary, ["project", "purge", "--all", "--dry-run"], {
      ...scenarios.purgeDryRun,
      normalize,
    });
    const purgeAfterFull = await inventory(scenarios.purgeDryRun.configDir);
    const purgeBefore = purgeDomainRows(purgeBeforeFull);
    const purgeAfter = purgeDomainRows(purgeAfterFull);

    const purgePositiveInput = createPurgeFixture("PURGE_POSITIVE");
    await seedPurgeFixture(scenarios.purgePositive.configDir, purgePositiveInput);
    const purgePositiveBeforeFull = await inventory(scenarios.purgePositive.configDir);
    const purgePositiveRun = await runCli(binary, ["project", "purge", "--all", "-y"], {
      ...scenarios.purgePositive,
      normalize,
    });
    const purgePositiveAfterFull = await inventory(scenarios.purgePositive.configDir);
    const purgePositiveBefore = purgeDomainRows(purgePositiveBeforeFull);
    const purgePositiveAfter = purgeDomainRows(purgePositiveAfterFull);

    const jsonFixture = createArchiveFixture();
    await writeFixtureFile(jsonArchive, `${JSON.stringify(jsonFixture, null, 2)}\n`);
    const jsonDryBefore = {
      transcript: await inventory(path.join(scenarios.jsonDryRun.configDir, "projects")),
      target: await inventory(scenarios.jsonDryRun.target),
    };
    const jsonDryRun = await runCli(binary, ["import-conversations", jsonArchive, "--cwd", scenarios.jsonDryRun.target, "--dry-run"], {
      ...scenarios.jsonDryRun,
      importConversations: true,
      normalize,
    });
    const jsonDryAfter = {
      transcript: await inventory(path.join(scenarios.jsonDryRun.configDir, "projects")),
      target: await inventory(scenarios.jsonDryRun.target),
    };

    const jsonBefore = {
      transcript: await inventory(path.join(scenarios.jsonImport.configDir, "projects")),
      target: await inventory(scenarios.jsonImport.target),
    };
    const jsonRun = await runCli(binary, ["import-conversations", jsonArchive, "--cwd", scenarios.jsonImport.target], {
      ...scenarios.jsonImport,
      importConversations: true,
      normalize,
    });
    const jsonTranscriptFiles = await findFiles(
      path.join(scenarios.jsonImport.configDir, "projects"),
      (file) => file.endsWith(".jsonl"),
    );
    const jsonTranscriptArtifact = jsonTranscriptFiles.length === 1
      ? await transcriptEvidence(jsonTranscriptFiles[0], normalize)
      : null;
    const jsonAfter = {
      transcript: useCanonicalTranscriptHash(
        await inventory(path.join(scenarios.jsonImport.configDir, "projects")),
        jsonTranscriptArtifact,
      ),
      target: await inventory(scenarios.jsonImport.target),
    };
    const jsonProjectRelative = `projects/json-import-project-${jsonFixture.projects[0].uuid}`;
    const jsonArtifacts = {
      projectInstructions: await artifactEvidence(
        scenarios.jsonImport.target,
        `${jsonProjectRelative}/project-instructions.md`,
        jsonFixture.projects[0].prompt_template,
      ),
      reservedClaudeDoc: await artifactEvidence(
        scenarios.jsonImport.target,
        `${jsonProjectRelative}/imported-CLAUDE.md`,
        jsonFixture.projects[0].docs[0].content,
      ),
    };

    const zipFixture = createArchiveFixture({ manifestMismatch: true });
    await createZipFixture(zipRoot, zipArchive, zipFixture);
    const zipBefore = {
      transcript: await inventory(path.join(scenarios.zipManifestMismatch.configDir, "projects")),
      target: await inventory(scenarios.zipManifestMismatch.target),
    };
    const zipRun = await runCli(binary, ["import-conversations", zipArchive, "--cwd", scenarios.zipManifestMismatch.target], {
      ...scenarios.zipManifestMismatch,
      importConversations: true,
      normalize,
    });
    const zipTranscriptFiles = await findFiles(
      path.join(scenarios.zipManifestMismatch.configDir, "projects"),
      (file) => file.endsWith(".jsonl"),
    );
    const zipTranscriptArtifact = zipTranscriptFiles.length === 1
      ? await transcriptEvidence(zipTranscriptFiles[0], normalize)
      : null;
    const zipAfter = {
      transcript: useCanonicalTranscriptHash(
        await inventory(path.join(scenarios.zipManifestMismatch.configDir, "projects")),
        zipTranscriptArtifact,
      ),
      target: await inventory(scenarios.zipManifestMismatch.target),
    };
    const zipProjectRelative = `projects/zip-mismatch-project-${zipFixture.projects[0].uuid}`;
    const zipFileUuid = zipFixture.projects[0].files[0].file_uuid;
    const zipArtifacts = {
      projectInstructions: await artifactEvidence(
        scenarios.zipManifestMismatch.target,
        `${zipProjectRelative}/project-instructions.md`,
        zipFixture.projects[0].prompt_template,
      ),
      reservedClaudeDoc: await artifactEvidence(
        scenarios.zipManifestMismatch.target,
        `${zipProjectRelative}/imported-CLAUDE.md`,
        zipFixture.projects[0].docs[0].content,
      ),
      reservedAgentsFile: await artifactEvidence(
        scenarios.zipManifestMismatch.target,
        `${zipProjectRelative}/imported-AGENTS.md`,
        zipFixture.files[zipFileUuid],
      ),
    };

    const codexRoot = path.join(scenarios.configImportBoundary.home, ".codex");
    const codexFixture = `[mcp_servers.local]\ncommand = "printf"\nargs = ["CONFIG_IMPORT_MARKER"]\n`;
    await writeFixtureFile(path.join(codexRoot, "config.toml"), codexFixture);
    const configImportBefore = {
      claudeConfig: await inventory(scenarios.configImportBoundary.configDir),
      codexConfig: await inventory(codexRoot),
    };
    const configImportRun = await runCli(binary, ["import", "codex", "--dry-run"], {
      ...scenarios.configImportBoundary,
      normalize,
    });
    const configImportAfter = {
      claudeConfig: await inventory(scenarios.configImportBoundary.configDir),
      codexConfig: await inventory(codexRoot),
    };

    const normalized = {
      version: {
        stdout: normalize(versionRun.stdout),
        stderr: normalize(versionRun.stderr),
      },
      purgeDryRun: {
        stdout: normalize(purgeRun.stdout),
        stderr: normalize(purgeRun.stderr),
      },
      purgePositive: {
        stdout: normalize(purgePositiveRun.stdout),
        stderr: normalize(purgePositiveRun.stderr),
      },
      jsonDryRun: {
        stdout: normalize(jsonDryRun.stdout),
        stderr: normalize(jsonDryRun.stderr),
      },
      jsonImport: {
        stdout: normalize(jsonRun.stdout),
        stderr: normalize(jsonRun.stderr),
      },
      zipManifestMismatch: {
        stdout: normalize(zipRun.stdout),
        stderr: normalize(zipRun.stderr),
      },
      configImportBoundary: {
        stdout: normalize(configImportRun.stdout),
        stderr: normalize(configImportRun.stderr),
      },
    };
    const executions = {
      version: versionRun,
      purgeDryRun: purgeRun,
      purgePositive: purgePositiveRun,
      jsonDryRun,
      jsonImport: jsonRun,
      zipManifestMismatch: zipRun,
      configImportBoundary: configImportRun,
    };
    const executionContracts = Object.fromEntries(
      Object.entries(executions).map(([name, execution]) => [name, execution.contract]),
    );
    const commands = Object.fromEntries(
      Object.entries(executions).map(([name, execution]) => [name, execution.reproductionCommand]),
    );
    const purgePlan = parsePurgePlan(normalized.purgeDryRun.stdout, "$PURGE_DRY_CONFIG");
    const purgePositivePlan = parsePurgePlan(normalized.purgePositive.stdout, "$PURGE_POSITIVE_CONFIG");
    const purgeDryDelta = inventoryDelta(purgeBefore, purgeAfter);
    const purgePositiveDeletedTargets = PURGE_OWNED_TARGETS.filter((entryPath) => (
      rowsForPaths(purgePositiveBefore, [entryPath]).length > 0
      && rowsForPaths(purgePositiveAfter, [entryPath]).length === 0
    ));
    const purgePositiveExcludedBefore = exactRows(purgePositiveBefore, PURGE_EXCLUDED_FIXTURES);
    const purgePositiveExcludedAfter = exactRows(purgePositiveAfter, PURGE_EXCLUDED_FIXTURES);
    const purgeDryStartupChanges = startupChanges(purgeBeforeFull, purgeAfterFull);
    const purgePositiveStartupChanges = startupChanges(purgePositiveBeforeFull, purgePositiveAfterFull);
    const jsonDryDelta = [
      ...inventoryDelta(jsonDryBefore.transcript, jsonDryAfter.transcript).map((row) => ({ ...row, scope: "transcript" })),
      ...inventoryDelta(jsonDryBefore.target, jsonDryAfter.target).map((row) => ({ ...row, scope: "target" })),
    ];
    const jsonTranscriptRows = jsonAfter.transcript.filter((entry) => entry.path.endsWith(".jsonl"));
    const zipTranscriptRows = zipAfter.transcript.filter((entry) => entry.path.endsWith(".jsonl"));
    const actualBinarySha256 = await sha256File(binary);
    const observedVersion = normalized.version.stdout.match(/^(\S+) \(Claude Code\)$/)?.[1] ?? normalized.version.stdout;
    const observed = {
      purgeDryRunPlan: purgePlan,
      purgeDryRunPlannedItems: purgePlan.length,
      purgeDryRunChanges: purgeDryDelta,
      purgeDryRunChangedEntries: purgeDryDelta.length,
      purgeDryRunStartupChanges: purgeDryStartupChanges,
      purgePositivePlan,
      purgePositivePlannedItems: purgePositivePlan.length,
      purgePositiveDeletedTargets,
      purgePositiveDeletedTargetCount: purgePositiveDeletedTargets.length,
      purgePositiveExcludedFixturesPreserved: PURGE_EXCLUDED_FIXTURES.filter((_, index) => (
        deepEqual(purgePositiveExcludedBefore[index], purgePositiveExcludedAfter[index])
      )),
      purgePositiveStartupChanges,
      jsonDryRunChanges: jsonDryDelta,
      jsonDryRunChangedEntries: jsonDryDelta.length,
      jsonImportTranscriptCount: jsonTranscriptRows.length,
      jsonImportTranscript: jsonTranscriptArtifact,
      jsonImportArtifacts: jsonArtifacts,
      zipMismatchTranscriptCount: zipTranscriptRows.length,
      zipMismatchTranscript: zipTranscriptArtifact,
      zipMismatchArtifacts: zipArtifacts,
      zipMismatchWritesSurvivedExitOne: zipTranscriptRows.length > 0 && zipAfter.target.length > 0,
      configImportFeatureAvailableOffline: configImportRun.exitStatus === 0,
    };
    const expectedPurgePlan = PURGE_OWNED_TARGETS.map((ownedTarget) => ({
      kind: ownedTarget === "history.jsonl" ? "file" : "dir",
      ownedTarget,
    }));
    const allowedStartupChanges = new Set([".claude.json", "backups/$AUTO_BACKUP"]);
    const jsonExpectedPaths = [
      "files",
      "projects",
      jsonProjectRelative,
      `${jsonProjectRelative}/imported-CLAUDE.md`,
      `${jsonProjectRelative}/project-instructions.md`,
    ];
    const zipExpectedPaths = [
      "files",
      "projects",
      zipProjectRelative,
      `${zipProjectRelative}/imported-AGENTS.md`,
      `${zipProjectRelative}/imported-CLAUDE.md`,
      `${zipProjectRelative}/project-instructions.md`,
    ];
    const checks = {
      snapshotMetadataVersionExact: expectedVersion === TARGET_VERSION,
      snapshotMetadataSha256Exact: expectedSha256 === TARGET_BINARY_SHA256,
      exactVersion: versionRun.exitStatus === 0 && observedVersion === TARGET_VERSION,
      exactBinarySha256: actualBinarySha256 === TARGET_BINARY_SHA256,
      everyExecutionContractComplete: Object.values(executionContracts).every(environmentContractIsComplete),
      everyCommandIsFullEnvironmentRendering: Object.values(commands).every((command) => (
        command.startsWith("env -i ")
        && command.includes("DISABLE_GROWTHBOOK=1")
        && command.includes("ANTHROPIC_API_KEY=''")
        && command.includes("GIT_CONFIG_GLOBAL=/dev/null")
      )),
      everyScenarioHasDistinctHome: new Set(Object.values(executionContracts).map((contract) => contract.environment.HOME)).size === Object.keys(executionContracts).length,
      everyScenarioHasDistinctConfig: new Set(Object.values(executionContracts).map((contract) => contract.environment.CLAUDE_CONFIG_DIR)).size === Object.keys(executionContracts).length,
      purgeDryRunExitZero: purgeRun.exitStatus === 0,
      purgeDryRunPrintsPlan: normalized.purgeDryRun.stdout.includes("Purge plan for all projects:"),
      purgeDryRunParsesEveryOwnedTarget: deepEqual(
        purgePlan.map(({ kind, ownedTarget }) => ({ kind, ownedTarget })),
        expectedPurgePlan,
      ),
      purgeDryRunListsFiveOwnedItems: deepEqual(
        purgePlan.map(({ kind, ownedTarget }) => ({ kind, ownedTarget })),
        expectedPurgePlan,
      ),
      purgeDryRunReportsParsedCount: normalized.purgeDryRun.stdout.includes(`Dry run: ${purgePlan.length} item(s) would be deleted.`),
      purgeDryRunPreservesAllBytes: deepEqual(purgeBefore, purgeAfter),
      purgeDryRunHasNoDomainDelta: purgeDryDelta.length === 0,
      purgeDryRunExcludesShellSnapshots: !purgePlan.some((entry) => entry.ownedTarget === "shell-snapshots"),
      purgeDryRunExcludesBackups: !purgePlan.some((entry) => entry.ownedTarget === "backups"),
      purgeDryRunClassifiesStartupFiles: purgeDryStartupChanges.length > 0
        && purgeDryStartupChanges.every((change) => allowedStartupChanges.has(change.path)),
      purgePositiveExitZero: purgePositiveRun.exitStatus === 0,
      purgePositiveParsesEveryOwnedTarget: deepEqual(
        purgePositivePlan.map(({ kind, ownedTarget }) => ({ kind, ownedTarget })),
        expectedPurgePlan,
      ),
      purgePositiveReportsDerivedCount: normalized.purgePositive.stdout.includes(`Purged ${purgePositiveDeletedTargets.length} item(s) across all projects.`),
      purgePositiveDeletesEveryOwnedTarget: deepEqual(purgePositiveDeletedTargets, PURGE_OWNED_TARGETS),
      purgePositiveLeavesNoOwnedRows: rowsForPaths(purgePositiveAfter, PURGE_OWNED_TARGETS).length === 0,
      purgePositivePreservesExcludedFixtureMetadataAndBytes: deepEqual(purgePositiveExcludedBefore, purgePositiveExcludedAfter),
      purgePositivePreservesShellSnapshotContent: purgePositiveExcludedAfter[0]?.sha256 === sha256Bytes(purgePositiveInput.files[PURGE_EXCLUDED_FIXTURES[0]]),
      purgePositivePreservesBackupContent: purgePositiveExcludedAfter[1]?.sha256 === sha256Bytes(purgePositiveInput.files[PURGE_EXCLUDED_FIXTURES[1]]),
      purgePositiveWarnsAboutBothExcludedRoots: normalized.purgePositive.stderr.includes("shell-snapshots/ are not project-scoped and will not be touched")
        && normalized.purgePositive.stderr.includes("backups/ may still contain project entries"),
      purgePositiveClassifiesStartupFiles: purgePositiveStartupChanges.length > 0
        && purgePositiveStartupChanges.every((change) => allowedStartupChanges.has(change.path)),
      jsonDryRunExitZero: jsonDryRun.exitStatus === 0,
      jsonDryRunReportsExpectedCounts: normalized.jsonDryRun.stdout.includes("[dry-run] imported: conversations=1 skipped=0 messages=2 projects=1 docs=1 files=0"),
      jsonDryRunDoesNotWrite: deepEqual(jsonDryBefore, jsonDryAfter),
      jsonDryRunHasNoObservedDelta: jsonDryDelta.length === 0,
      jsonImportExitZero: jsonRun.exitStatus === 0,
      jsonImportReportsExpectedCounts: normalized.jsonImport.stdout.includes("imported: conversations=1 skipped=0 messages=2 projects=1 docs=1 files=0"),
      jsonImportWritesOneTranscript: jsonTranscriptRows.length === 1,
      jsonImportPreservesExactUuidParentChain: deepEqual(jsonTranscriptArtifact?.records, expectedTranscriptRecords(jsonFixture)),
      jsonImportPreservesMessageChain: deepEqual(jsonTranscriptArtifact?.records, expectedTranscriptRecords(jsonFixture)),
      jsonImportTranscriptMode0600: jsonTranscriptArtifact?.mode === "600" && jsonTranscriptRows[0]?.mode === "600",
      jsonImportTranscriptHasCanonicalContentHash: /^[0-9a-f]{64}$/.test(jsonTranscriptArtifact?.canonicalContentSha256 ?? "")
        && jsonTranscriptRows[0]?.contentSha256 === jsonTranscriptArtifact?.canonicalContentSha256,
      jsonImportTranscriptCanonicalBytesAndHashExact: jsonTranscriptArtifact?.canonicalBytes === TRANSCRIPT_CANONICAL_EXPECTATIONS.jsonImport.bytes
        && jsonTranscriptArtifact?.canonicalContentSha256 === TRANSCRIPT_CANONICAL_EXPECTATIONS.jsonImport.sha256,
      jsonImportTranscriptPathsAreCanonicalized: jsonTranscriptArtifact !== null
        && !jsonTranscriptArtifact.path.includes(temporary)
        && jsonTranscriptArtifact.path.startsWith("$JSON_CONFIG/projects/$PROJECT_KEY/"),
      jsonImportProjectInstructionsExact: exactArtifactMatches(jsonArtifacts.projectInstructions),
      jsonImportReservedClaudeDocExact: exactArtifactMatches(jsonArtifacts.reservedClaudeDoc),
      jsonImportWritesProjectInstructions: exactArtifactMatches(jsonArtifacts.projectInstructions),
      jsonImportDemotesClaudeMd: exactArtifactMatches(jsonArtifacts.reservedClaudeDoc),
      jsonImportWritesOnlyExpectedTargetArtifacts: deepEqual(jsonAfter.target.map((entry) => entry.path), jsonExpectedPaths),
      zipMismatchExitOne: zipRun.exitStatus === 1,
      zipMismatchReportsExpectedCounts: normalized.zipManifestMismatch.stdout.includes("imported: conversations=1 skipped=0 messages=2 projects=1 docs=1 files=1"),
      zipMismatchReportsMessageDiff: normalized.zipManifestMismatch.stderr.includes("messages: manifest=3 imported=2"),
      zipMismatchReportsDocDiff: normalized.zipManifestMismatch.stderr.includes("docs: manifest=2 imported=1"),
      zipMismatchReportsTerminalCode: normalized.zipManifestMismatch.stderr.includes("Import completed with mismatches (IMPORT_MANIFEST_MISMATCH)"),
      zipMismatchKeepsTranscript: zipTranscriptRows.length === 1,
      zipMismatchPreservesExactUuidParentChain: deepEqual(zipTranscriptArtifact?.records, expectedTranscriptRecords(zipFixture)),
      zipMismatchPreservesMessageChain: deepEqual(zipTranscriptArtifact?.records, expectedTranscriptRecords(zipFixture)),
      zipMismatchTranscriptMode0600: zipTranscriptArtifact?.mode === "600" && zipTranscriptRows[0]?.mode === "600",
      zipMismatchTranscriptHasCanonicalContentHash: /^[0-9a-f]{64}$/.test(zipTranscriptArtifact?.canonicalContentSha256 ?? "")
        && zipTranscriptRows[0]?.contentSha256 === zipTranscriptArtifact?.canonicalContentSha256,
      zipMismatchTranscriptCanonicalBytesAndHashExact: zipTranscriptArtifact?.canonicalBytes === TRANSCRIPT_CANONICAL_EXPECTATIONS.zipManifestMismatch.bytes
        && zipTranscriptArtifact?.canonicalContentSha256 === TRANSCRIPT_CANONICAL_EXPECTATIONS.zipManifestMismatch.sha256,
      zipMismatchTranscriptPathsAreCanonicalized: zipTranscriptArtifact !== null
        && !zipTranscriptArtifact.path.includes(temporary)
        && zipTranscriptArtifact.path.startsWith("$ZIP_CONFIG/projects/$PROJECT_KEY/"),
      zipMismatchProjectInstructionsExact: exactArtifactMatches(zipArtifacts.projectInstructions),
      zipMismatchKeepsReservedClaudeDocExact: exactArtifactMatches(zipArtifacts.reservedClaudeDoc),
      zipMismatchKeepsReservedAgentsFileExact: exactArtifactMatches(zipArtifacts.reservedAgentsFile),
      zipMismatchKeepsReservedDoc: exactArtifactMatches(zipArtifacts.reservedClaudeDoc),
      zipMismatchKeepsReservedProjectFile: exactArtifactMatches(zipArtifacts.reservedAgentsFile),
      zipMismatchWritesOnlyExpectedTargetArtifacts: deepEqual(zipAfter.target.map((entry) => entry.path), zipExpectedPaths),
      zipMismatchWritesSurviveExitOne: observed.zipMismatchWritesSurvivedExitOne,
      configImportGateExitOne: configImportRun.exitStatus === 1,
      configImportGateMessageExact: [normalized.configImportBoundary.stdout, normalized.configImportBoundary.stderr].includes(IMPORT_GATE_MESSAGE),
      configImportGateWritesNothing: deepEqual(configImportBefore, configImportAfter),
      configImportAvailabilityDerivedFromRun: observed.configImportFeatureAvailableOffline === false,
    };

    report = {
      schemaVersion: 2,
      capturedAt: new Date().toISOString(),
      environment: {
        platform: process.platform,
        arch: process.arch,
        nodeVersion: process.version,
        zipExecutable: "/usr/bin/zip",
      },
      target: {
        version: observedVersion,
        binarySha256: actualBinarySha256,
        requiredVersion: TARGET_VERSION,
        requiredBinarySha256: TARGET_BINARY_SHA256,
      },
      commandSemantics: "commands is a shell reproduction rendering; executionContracts is the authoritative normalized spawn argv, cwd and replacement environment contract",
      commands,
      executionContracts,
      input: {
        purgeDryRun: purgeInput,
        purgePositive: purgePositiveInput,
        jsonArchive: jsonFixture,
        zipArchive: zipFixture,
        configImportBoundary: {
          source: "codex",
          dryRun: true,
          codexConfigToml: codexFixture,
          gate: "tengu_import uses its built-in false value because server evaluation is disabled and local overrides are unreachable in 2.1.235",
        },
      },
      literalOutput: normalized,
      exitStatus: {
        version: versionRun.exitStatus,
        purgeDryRun: purgeRun.exitStatus,
        purgePositive: purgePositiveRun.exitStatus,
        jsonDryRun: jsonDryRun.exitStatus,
        jsonImport: jsonRun.exitStatus,
        zipManifestMismatch: zipRun.exitStatus,
        configImportBoundary: configImportRun.exitStatus,
      },
      beforeAfter: {
        purgeDryRun: {
          domainBefore: purgeBefore,
          domainAfter: purgeAfter,
          startupChangesOutsidePlan: purgeDryStartupChanges,
        },
        purgePositive: {
          ownedBefore: rowsForPaths(purgePositiveBefore, PURGE_OWNED_TARGETS),
          ownedAfter: rowsForPaths(purgePositiveAfter, PURGE_OWNED_TARGETS),
          excludedFixturesBefore: purgePositiveExcludedBefore,
          excludedFixturesAfter: purgePositiveExcludedAfter,
          domainBefore: purgePositiveBefore,
          domainAfter: purgePositiveAfter,
          startupChangesOutsidePlan: purgePositiveStartupChanges,
        },
        jsonDryRun: { before: jsonDryBefore, after: jsonDryAfter },
        jsonImport: { before: jsonBefore, after: jsonAfter },
        zipManifestMismatch: { before: zipBefore, after: zipAfter },
        configImportBoundary: { before: configImportBefore, after: configImportAfter },
      },
      observed,
      reproducibilityContract: {
        canonicalization: "delete capturedAt, then compare the complete parsed JSON value byte-for-byte after deterministic JSON serialization",
        transcriptHashBasis: "normalize all scenario cwd, config, target, HOME, TMPDIR, fixture and probe-root paths before SHA-256",
      },
      checks,
      pass: Object.values(checks).every(Boolean),
    };
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }

  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) process.exitCode = 1;
}

await main();
