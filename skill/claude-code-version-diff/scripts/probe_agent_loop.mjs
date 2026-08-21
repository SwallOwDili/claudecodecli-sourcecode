#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";

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

function toolResponse(model, toolUseId, filePath) {
  return [
    messageStart(model, "msg_probe_tool"),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "tool_use", id: toolUseId, name: "Read", input: {} },
    }],
    ["content_block_delta", {
      type: "content_block_delta",
      index: 0,
      delta: {
        type: "input_json_delta",
        partial_json: JSON.stringify({ file_path: filePath }),
      },
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
    messageStart(model, `msg_probe_${text.toLowerCase()}`),
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

function containsBlock(value, predicate) {
  if (Array.isArray(value)) return value.some((item) => containsBlock(item, predicate));
  if (!value || typeof value !== "object") return false;
  if (predicate(value)) return true;
  return Object.values(value).some((item) => containsBlock(item, predicate));
}

function runCli(binary, args, options) {
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

function parseStream(stdout) {
  return stdout.split("\n").filter(Boolean).map((line) => JSON.parse(line));
}

function resultEvent(events) {
  return events.findLast((event) => event.type === "result");
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

async function main() {
  const binary = process.env.CLAUDE_BIN
    ?? path.join(os.homedir(), ".local/share/claude/versions/2.1.235");
  const expectedVersion = process.env.CLAUDE_VERSION ?? "2.1.235";
  const expectedSha256 = process.env.CLAUDE_SHA256
    ?? "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748";
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-agent-loop-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);

  const initialPrompt = "AGENT_LOOP_INITIAL_MARKER";
  const resumePrompt = "AGENT_LOOP_RESUME_MARKER";
  const forkPrompt = "AGENT_LOOP_FORK_MARKER";
  const compactPrompt = "/compact COMPACT_REQUEST_MARKER retain key facts";
  const fileMarker = "AGENT_LOOP_FILE_MARKER";
  const fixture = path.join(workspace, "probe-fixture.txt");
  await writeFile(fixture, `${fileMarker}\n`, { mode: 0o600 });

  const toolUseId = "toolu_agent_loop_probe";
  const mainBodies = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }

    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const bodyText = JSON.stringify(body);
    const isProbeRequest = body.tools?.some((tool) => tool.name === "Read")
      || bodyText.includes(initialPrompt)
      || bodyText.includes(resumePrompt)
      || bodyText.includes(forkPrompt)
      || bodyText.includes(toolUseId);
    if (!isProbeRequest) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "AUXILIARY_OK"));
      return;
    }

    mainBodies.push(body);
    if (mainBodies.length === 1) {
      writeSse(response, toolResponse(body.model ?? "claude-probe", toolUseId, fixture));
    } else if (mainBodies.length === 2) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "TOOL_EXECUTION_OK"));
    } else if (bodyText.includes(forkPrompt)) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "FORK_OK"));
    } else if (bodyText.includes("COMPACT_REQUEST_MARKER")) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "COMPACT_SUMMARY_OK"));
    } else {
      writeSse(response, textResponse(body.model ?? "claude-probe", "RESUME_OK"));
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const sessionId = randomUUID();
  const commonArgs = [
    "--print",
    "--output-format", "stream-json",
    "--verbose",
    "--model", "claude-sonnet-4-5",
    "--tools", "Read",
    "--permission-mode", "bypassPermissions",
    "--dangerously-skip-permissions",
  ];
  const env = {
    ...process.env,
    HOME: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${server.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "probe-token",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };

  let initial;
  let resumed;
  let forked;
  let compacted;
  try {
    initial = await runCli(binary, [
      ...commonArgs,
      "--session-id", sessionId,
      initialPrompt,
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
    resumed = await runCli(binary, [
      ...commonArgs,
      "--resume", sessionId,
      resumePrompt,
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
    compacted = await runCli(binary, [
      ...commonArgs,
      "--resume", sessionId,
      compactPrompt,
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
    forked = await runCli(binary, [
      ...commonArgs,
      "--resume", sessionId,
      "--fork-session",
      forkPrompt,
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const initialEvents = parseStream(initial.stdout);
  const resumeEvents = parseStream(resumed.stdout);
  const compactEvents = parseStream(compacted.stdout);
  const forkEvents = parseStream(forked.stdout);
  const initialResult = resultEvent(initialEvents);
  const resumeResult = resultEvent(resumeEvents);
  const compactResult = resultEvent(compactEvents);
  const compactBoundary = compactEvents.find((event) => event.type === "system" && event.subtype === "compact_boundary");
  const forkResult = resultEvent(forkEvents);
  const initialSystem = initialEvents.find((event) => event.type === "system" && event.subtype === "init");
  const forkSystem = forkEvents.find((event) => event.type === "system" && event.subtype === "init");
  const firstBody = mainBodies[0];
  const secondBody = mainBodies[1];
  const resumeBody = mainBodies.find((body) => JSON.stringify(body.messages).includes(resumePrompt));
  const forkBody = mainBodies.find((body) => JSON.stringify(body.messages).includes(forkPrompt));
  const secondRequestHasToolUse = containsBlock(secondBody?.messages, (value) =>
    value.type === "tool_use" && value.id === toolUseId && value.name === "Read"
  );
  const secondRequestHasToolResult = containsBlock(secondBody?.messages, (value) =>
    value.type === "tool_result"
      && value.tool_use_id === toolUseId
      && JSON.stringify(value.content).includes(fileMarker)
  );
  const resumeBodyText = JSON.stringify(resumeBody?.messages);
  const forkBodyText = JSON.stringify(forkBody?.messages);
  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const literalVersion = versionRun.stdout.trim();

  const checks = {
    exactVersion: literalVersion === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    initialExitZero: initial.exitStatus === 0,
    initialResultSuccess: initialResult?.subtype === "success",
    firstRequestHasPrompt: JSON.stringify(firstBody?.messages).includes(initialPrompt),
    firstRequestAdvertisesRead: firstBody?.tools?.some((tool) => tool.name === "Read") ?? false,
    secondRequestHasToolUse,
    secondRequestHasToolResult,
    toolResultContainsFileMarker: secondRequestHasToolResult,
    resumeExitZero: resumed.exitStatus === 0,
    resumeResultSuccess: resumeResult?.subtype === "success",
    resumeRequestHasInitialPrompt: resumeBodyText.includes(initialPrompt),
    resumeRequestHasInitialAssistantResult: resumeBodyText.includes("TOOL_EXECUTION_OK"),
    resumeRequestHasCurrentPrompt: resumeBodyText.includes(resumePrompt),
    compactCommandExitZero: compacted.exitStatus === 0,
    compactCommandProducedResult: compactResult !== undefined,
    compactBoundaryEmitted: compactBoundary !== undefined,
    forkExitZero: forked.exitStatus === 0,
    forkResultSuccess: forkResult?.result === "FORK_OK",
    forkSessionIdDiffers: typeof initialSystem?.session_id === "string"
      && typeof forkSystem?.session_id === "string"
      && forkSystem.session_id !== initialSystem.session_id,
    forkRequestOmitsPreCompactPrompt: !forkBodyText.includes(initialPrompt),
    forkRequestOmitsPreCompactToolUseId: !forkBodyText.includes(toolUseId),
    forkRequestOmitsPreCompactAssistantResult: !forkBodyText.includes("TOOL_EXECUTION_OK"),
    forkRequestHasCompactSummary: forkBodyText.includes("COMPACT_SUMMARY_OK"),
    forkRequestHasCurrentPrompt: forkBodyText.includes(forkPrompt),
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
      baseline: "$CLAUDE_2_1_235 --version",
      initial: "$CLAUDE_2_1_235 --print AGENT_LOOP_INITIAL_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID",
      resume: "$CLAUDE_2_1_235 --print AGENT_LOOP_RESUME_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --resume $SESSION_ID",
      compact: "$CLAUDE_2_1_235 --print '/compact COMPACT_REQUEST_MARKER retain key facts' --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --resume $SESSION_ID",
      fork: "$CLAUDE_2_1_235 --print AGENT_LOOP_FORK_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --resume $SESSION_ID --fork-session",
    },
    input: {
      initialPrompt,
      modelToolUse: { id: toolUseId, name: "Read", file: "$WORKSPACE/probe-fixture.txt" },
      fixtureContent: fileMarker,
      resumePrompt,
      compactPrompt,
      forkPrompt,
    },
    literalOutput: {
      version: literalVersion,
      initialResult: initialResult?.result ?? null,
      initialSubtype: initialResult?.subtype ?? null,
      resumeResult: resumeResult?.result ?? null,
      resumeSubtype: resumeResult?.subtype ?? null,
      compactResult: compactResult?.result ?? null,
      compactSubtype: compactResult?.subtype ?? null,
      compactEventTypes: compactEvents.map((event) => `${event.type}:${event.subtype ?? ""}`),
      compactBoundary: compactBoundary === undefined ? null : {
        trigger: compactBoundary.compact_metadata?.trigger ?? compactBoundary.trigger ?? null,
        preTokens: compactBoundary.compact_metadata?.pre_tokens ?? compactBoundary.pre_tokens ?? null,
      },
      forkResult: forkResult?.result ?? null,
      forkSubtype: forkResult?.subtype ?? null,
      sessionIds: {
        initial: initialSystem?.session_id === undefined ? null : "$SESSION_ID",
        fork: forkSystem?.session_id === undefined ? null : "$FORK_SESSION_ID",
      },
    },
    exitStatus: {
      version: versionRun.exitStatus,
      initial: initial.exitStatus,
      resume: resumed.exitStatus,
      compact: compacted.exitStatus,
      fork: forked.exitStatus,
    },
    observedRequestCount: mainBodies.length,
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(initial.stderr);
    process.stderr.write(resumed.stderr);
    process.stderr.write(compacted.stderr);
    process.stderr.write(forked.stderr);
    process.exitCode = 1;
  }
}

await main();
