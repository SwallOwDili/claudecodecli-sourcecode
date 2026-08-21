#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";

const PROMPT = "CHECKPOINT_REWIND_PROMPT_MARKER";
const ORIGINAL = "CHECKPOINT_ORIGINAL";
const MODIFIED = "CHECKPOINT_MODIFIED";
const READ_ID = "toolu_checkpoint_read";
const EDIT_ID = "toolu_checkpoint_edit";

function messageStart(model, id) {
  return ["message_start", {
    type: "message_start",
    message: {
      id,
      type: "message",
      role: "assistant",
      model,
      content: [],
      stop_reason: null,
      stop_sequence: null,
      usage: { input_tokens: 100, output_tokens: 0 },
    },
  }];
}

function writeSse(response, events) {
  response.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "request-id": `msg_${Date.now()}`,
  });
  for (const [event, data] of events) {
    response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  }
  response.end();
}

function toolResponse(model, id, name, input) {
  return [
    messageStart(model, `msg_${id}`),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "tool_use", id, name, input: {} },
    }],
    ["content_block_delta", {
      type: "content_block_delta",
      index: 0,
      delta: { type: "input_json_delta", partial_json: JSON.stringify(input) },
    }],
    ["content_block_stop", { type: "content_block_stop", index: 0 }],
    ["message_delta", {
      type: "message_delta",
      delta: { stop_reason: "tool_use", stop_sequence: null },
      usage: { output_tokens: 20 },
    }],
    ["message_stop", { type: "message_stop" }],
  ];
}

function textResponse(model, text) {
  return [
    messageStart(model, `msg_${text.toLowerCase()}`),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "text", text: "" },
    }],
    ["content_block_delta", {
      type: "content_block_delta",
      index: 0,
      delta: { type: "text_delta", text },
    }],
    ["content_block_stop", { type: "content_block_stop", index: 0 }],
    ["message_delta", {
      type: "message_delta",
      delta: { stop_reason: "end_turn", stop_sequence: null },
      usage: { output_tokens: 4 },
    }],
    ["message_stop", { type: "message_stop" }],
  ];
}

function runCli(binary, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, options);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", (exitStatus, signal) => resolve({ exitStatus, signal, stdout, stderr }));
  });
}

function parseStream(stdout) {
  try {
    return stdout.split("\n").filter(Boolean).map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

function resultEvent(run) {
  return parseStream(run.stdout).findLast((event) => event.type === "result");
}

function normalizeResult(run) {
  const result = resultEvent(run);
  return {
    result: result?.result ?? null,
    subtype: result?.subtype ?? null,
    isError: result?.is_error ?? null,
    exitStatus: run.exitStatus,
  };
}

function hasToolResult(body, id) {
  return JSON.stringify(body?.messages ?? []).includes(`"tool_use_id":"${id}"`);
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const child = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(child));
    else files.push(child);
  }
  return files;
}

function recordContains(record, marker) {
  return JSON.stringify(record).includes(marker);
}

async function findUserMessageUuid(configDir, sessionId) {
  const candidates = (await walk(configDir)).filter((file) => file.endsWith(`${sessionId}.jsonl`));
  for (const file of candidates) {
    const records = (await readFile(file, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    const record = records.find((item) => item.type === "user" && recordContains(item, PROMPT));
    if (typeof record?.uuid === "string") return record.uuid;
  }
  return null;
}

async function main() {
  const binary = process.env.CLAUDE_BIN
    ?? path.join(os.homedir(), ".local/share/claude/versions/2.1.235");
  const expectedVersion = process.env.CLAUDE_VERSION ?? "2.1.235";
  const expectedSha256 = process.env.CLAUDE_SHA256
    ?? "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748";
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-checkpoint-rewind-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);
  const fixture = path.join(workspace, "checkpoint.txt");
  await writeFile(fixture, `${ORIGINAL}\n`, "utf8");

  let messageRequestCount = 0;
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    messageRequestCount += 1;
    const model = body.model ?? "claude-probe";
    if (!hasToolResult(body, READ_ID)) {
      writeSse(response, toolResponse(model, READ_ID, "Read", { file_path: fixture }));
    } else if (!hasToolResult(body, EDIT_ID)) {
      writeSse(response, toolResponse(model, EDIT_ID, "Edit", {
        file_path: fixture,
        old_string: ORIGINAL,
        new_string: MODIFIED,
      }));
    } else {
      writeSse(response, textResponse(model, "CHECKPOINT_EDIT_OK"));
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${server.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "checkpoint-probe-token",
    ANTHROPIC_API_KEY: "",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };
  const sessionId = randomUUID();
  const initialRun = await runCli(binary, [
    "--print",
    "--output-format", "stream-json",
    "--verbose",
    "--model", "claude-sonnet-4-5",
    "--tools", "Read,Edit",
    "--permission-mode", "bypassPermissions",
    "--dangerously-skip-permissions",
    "--session-id", sessionId,
    PROMPT,
  ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
  const modifiedContent = await readFile(fixture, "utf8");
  const userMessageUuid = await findUserMessageUuid(configDir, sessionId);
  const requestsBeforeRewind = messageRequestCount;
  const rewindRun = userMessageUuid === null
    ? { exitStatus: 1, signal: null, stdout: "", stderr: "missing user message uuid" }
    : await runCli(binary, [
      "--print",
      "--resume", sessionId,
      "--rewind-files", userMessageUuid,
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
  const restoredContent = await readFile(fixture, "utf8");
  const requestsAfterRewind = messageRequestCount;
  await new Promise((resolve) => server.close(resolve));
  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const normalizedRewindOutput = `${rewindRun.stdout}${rewindRun.stderr}`
    .trim()
    .replaceAll(userMessageUuid ?? "<missing>", "$USER_MESSAGE_UUID");
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    initialRunSucceeds: initialRun.exitStatus === 0 && resultEvent(initialRun)?.result === "CHECKPOINT_EDIT_OK",
    editChangedFile: modifiedContent === `${MODIFIED}\n`,
    transcriptUserUuidFound: userMessageUuid !== null,
    rewindExitZero: rewindRun.exitStatus === 0,
    rewindReportsTargetMessage: normalizedRewindOutput === "Files rewound to state at message $USER_MESSAGE_UUID",
    rewindRestoresOriginalBytes: restoredContent === `${ORIGINAL}\n`,
    rewindDoesNotCallModel: requestsAfterRewind === requestsBeforeRewind,
  };

  const report = {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    environment: {
      platform: process.platform,
      arch: process.arch,
      nodeVersion: process.version,
    },
    target: {
      version: expectedVersion,
      binarySha256: await sha256(binary),
    },
    commands: {
      createCheckpoint: "$CLAUDE_2_1_235 --print CHECKPOINT_REWIND_PROMPT_MARKER --tools Read,Edit --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID",
      rewind: "$CLAUDE_2_1_235 --print --resume $SESSION_ID --rewind-files $USER_MESSAGE_UUID",
    },
    input: {
      createCheckpoint: {
        file: "$WORKSPACE/checkpoint.txt",
        before: `${ORIGINAL}\n`,
        after: `${MODIFIED}\n`,
      },
      rewind: {
        sessionId: "$SESSION_ID",
        userMessageUuid: "$USER_MESSAGE_UUID",
        sdkFileCheckpointingEnabled: true,
      },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      createCheckpoint: normalizeResult(initialRun),
      rewind: normalizedRewindOutput,
    },
    exitStatus: {
      version: versionRun.exitStatus,
      createCheckpoint: initialRun.exitStatus,
      rewind: rewindRun.exitStatus,
    },
    observed: {
      before: `${ORIGINAL}\n`,
      afterEdit: modifiedContent,
      afterRewind: restoredContent,
      modelRequestsDuringCreate: requestsBeforeRewind,
      modelRequestsDuringRewind: requestsAfterRewind - requestsBeforeRewind,
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(initialRun.stderr);
    process.stderr.write(rewindRun.stderr);
    process.exitCode = 1;
  }
}

await main();
