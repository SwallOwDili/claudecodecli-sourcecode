#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const PARENT_PROMPT = "SUBAGENT_PARENT_PROMPT_MARKER";
const CHILD_PROMPT = "SUBAGENT_CHILD_PROMPT_MARKER";
const CHILD_RESULT = "SUBAGENT_CHILD_RESULT_MARKER";

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

async function writeSseAfter(response, events, delayMs) {
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  writeSse(response, events);
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

function toolResponse(model, toolName) {
  const input = {
    description: "Run an isolated child-loop probe",
    prompt: CHILD_PROMPT,
    subagent_type: "general-purpose",
  };
  return [
    messageStart(model, "msg_subagent_tool"),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "tool_use", id: "toolu_subagent_probe", name: toolName, input: {} },
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
    child.once("close", (exitStatus, signal) => resolve({ exitStatus, signal, stdout, stderr }));
  });
}

function resultEvent(stdout) {
  return stdout.split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .findLast((event) => event.type === "result");
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-subagent-loop-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);

  const parentBodies = [];
  const childBodies = [];
  let agentToolName = null;
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
    const model = body.model ?? "claude-probe";
    if (bodyText.includes(CHILD_PROMPT) && !bodyText.includes(PARENT_PROMPT)) {
      childBodies.push(body);
      writeSse(response, textResponse(model, CHILD_RESULT));
      return;
    }
    if (!bodyText.includes(PARENT_PROMPT)) {
      writeSse(response, textResponse(model, "AUXILIARY_OK"));
      return;
    }
    parentBodies.push(body);
    agentToolName ??= body.tools?.find((tool) => tool.name === "Agent")?.name ?? null;
    const hasLaunchResult = containsBlock(body.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_subagent_probe"
        && JSON.stringify(value.content).includes("Async agent launched successfully")
    );
    const hasChildNotification = bodyText.includes("<task-notification>")
      && bodyText.includes(CHILD_RESULT);
    if (hasChildNotification) {
      writeSse(response, textResponse(model, "SUBAGENT_PARENT_OK"));
    } else if (hasLaunchResult) {
      // Keep the parent turn open briefly so the completed background child can
      // enqueue its task notification before the loop decides whether to stop.
      await writeSseAfter(response, textResponse(model, "SUBAGENT_WAITING"), 100);
    } else if (agentToolName) {
      writeSse(response, toolResponse(model, agentToolName));
    } else {
      writeSse(response, textResponse(model, "SUBAGENT_TOOL_MISSING"));
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const env = {
    ...process.env,
    HOME: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${server.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "subagent-loop-probe-token",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };
  let run;
  try {
    run = await runCli(binary, [
      "--print", PARENT_PROMPT,
      "--output-format", "stream-json",
      "--verbose",
      "--model", "claude-sonnet-4-5",
      "--tools", "Agent",
      "--permission-mode", "bypassPermissions",
      "--dangerously-skip-permissions",
      "--session-id", randomUUID(),
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const result = resultEvent(run.stdout);
  const childText = JSON.stringify(childBodies[0]?.messages);
  const parentLaunchResult = containsBlock(parentBodies[1]?.messages, (value) =>
    value.type === "tool_result"
      && value.tool_use_id === "toolu_subagent_probe"
      && JSON.stringify(value.content).includes("Async agent launched successfully")
  );
  const parentNotificationText = JSON.stringify(parentBodies.at(-1)?.messages);
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    exitZero: run.exitStatus === 0,
    resultSuccess: result?.result === "SUBAGENT_PARENT_OK" && result?.subtype === "success",
    parentAdvertisesAgent: parentBodies[0]?.tools?.some((tool) => tool.name === "Agent") ?? false,
    childRequestObserved: childBodies.length === 1,
    childReceivesOwnPrompt: childText.includes(CHILD_PROMPT),
    childOmitsParentPrompt: !childText.includes(PARENT_PROMPT),
    childHasIndependentTools: (childBodies[0]?.tools?.length ?? 0) > 0,
    parentReceivesAsyncLaunchResult: parentLaunchResult,
    parentReceivesTaskNotification: parentNotificationText.includes("<task-notification>")
      && parentNotificationText.includes(CHILD_RESULT),
    parentMakesFinalDecision: parentBodies.length === 3,
  };
  const report = {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    environment: {
      platform: process.platform,
      arch: process.arch,
      nodeVersion: process.version,
    },
    target: { version: expectedVersion, binarySha256: await sha256(binary) },
    commands: {
      subagentLoop: "$CLAUDE_TARGET --print SUBAGENT_PARENT_PROMPT_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Agent --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID",
    },
    input: {
      parentPrompt: PARENT_PROMPT,
      toolUseId: "toolu_subagent_probe",
      agentInput: {
        description: "Run an isolated child-loop probe",
        prompt: CHILD_PROMPT,
        subagent_type: "general-purpose",
      },
      childResult: CHILD_RESULT,
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      result: result?.result ?? null,
      subtype: result?.subtype ?? null,
    },
    exitStatus: { version: versionRun.exitStatus, subagentLoop: run.exitStatus },
    observed: {
      parentRequestCount: parentBodies.length,
      childRequestCount: childBodies.length,
      parentFeedbackSequence: ["tool_result:async_launched", "task-notification:completed"],
      childToolCount: childBodies[0]?.tools?.length ?? 0,
      childModel: childBodies[0]?.model ?? null,
      parentModel: parentBodies[0]?.model ?? null,
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(run.stderr);
    process.exitCode = 1;
  }
}

await main();
