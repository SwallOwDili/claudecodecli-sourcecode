#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";

const MARKERS = {
  request: "REQUEST_SHAPE_MARKER",
  hookDeny: "HOOK_DENY_PROMPT_MARKER",
  hookReason: "HOOK_DENY_MARKER",
  stop: "STOP_REENTRY_PROMPT_MARKER",
  stopReason: "STOP_HOOK_REENTER_MARKER",
  maxTurns: "MAX_TURNS_PROMPT_MARKER",
  file: "RUNTIME_CONTROL_FILE_MARKER",
};

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

function toolResponse(model, toolUseId, filePath) {
  return [
    messageStart(model, `msg_${toolUseId}`),
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

function resultEvent(run) {
  try {
    return parseStream(run.stdout).findLast((event) => event.type === "result");
  } catch {
    return undefined;
  }
}

function containsBlock(value, predicate) {
  if (Array.isArray(value)) return value.some((item) => containsBlock(item, predicate));
  if (!value || typeof value !== "object") return false;
  if (predicate(value)) return true;
  return Object.values(value).some((item) => containsBlock(item, predicate));
}

function countCacheControls(value) {
  if (Array.isArray(value)) return value.reduce((total, item) => total + countCacheControls(item), 0);
  if (!value || typeof value !== "object") return 0;
  return (Object.hasOwn(value, "cache_control") ? 1 : 0)
    + Object.values(value).reduce((total, item) => total + countCacheControls(item), 0);
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

async function readJsonLines(file) {
  try {
    return (await readFile(file, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
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

async function main() {
  const binary = process.env.CLAUDE_BIN
    ?? path.join(os.homedir(), ".local/share/claude/versions/2.1.235");
  const expectedVersion = process.env.CLAUDE_VERSION ?? "2.1.235";
  const expectedSha256 = process.env.CLAUDE_SHA256
    ?? "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748";
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-runtime-controls-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);

  const fixture = path.join(workspace, "runtime-control-fixture.txt");
  const hookLog = path.join(temporary, "hook-events.jsonl");
  const stopState = path.join(temporary, "stop-state");
  const hookScript = path.join(temporary, "probe-hook.mjs");
  const settingsFile = path.join(temporary, "settings.json");
  await writeFile(fixture, `${MARKERS.file}\n`, { mode: 0o600 });
  await writeFile(hookScript, `#!/usr/bin/env node
import { appendFile, readFile, writeFile } from "node:fs/promises";
import process from "node:process";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const event = JSON.parse(input || "{}");
await appendFile(process.env.PROBE_HOOK_LOG, JSON.stringify({
  event: event.hook_event_name,
  tool: event.tool_name ?? null,
  toolUseId: event.tool_use_id ?? null,
}) + "\\n");

if (process.env.PROBE_HOOK_MODE === "deny" && event.hook_event_name === "PreToolUse") {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "${MARKERS.hookReason}",
    },
  }));
} else if (process.env.PROBE_HOOK_MODE === "stop" && event.hook_event_name === "Stop") {
  let seen = false;
  try { seen = (await readFile(process.env.PROBE_STOP_STATE, "utf8")) === "1"; } catch {}
  if (!seen) {
    await writeFile(process.env.PROBE_STOP_STATE, "1");
    process.stdout.write(JSON.stringify({
      decision: "block",
      reason: "${MARKERS.stopReason}",
      hookSpecificOutput: {
        hookEventName: "Stop",
        additionalContext: "${MARKERS.stopReason}",
      },
    }));
  } else {
    process.stdout.write("{}");
  }
} else {
  process.stdout.write("{}");
}
`);
  await chmod(hookScript, 0o700);
  await writeFile(settingsFile, JSON.stringify({
    hooks: {
      PreToolUse: [{ matcher: "Read", hooks: [{ type: "command", command: hookScript }] }],
      PostToolUse: [{ matcher: "Read", hooks: [{ type: "command", command: hookScript }] }],
      Stop: [{ matcher: "", hooks: [{ type: "command", command: hookScript }] }],
    },
  }, null, 2));

  const requests = [];
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
    const headers = Object.fromEntries(
      Object.entries(request.headers).map(([key, value]) => [key, Array.isArray(value) ? value.join(",") : value]),
    );
    requests.push({ body, headers });
    const model = body.model ?? "claude-probe";

    if (bodyText.includes(MARKERS.request)) {
      writeSse(response, textResponse(model, "REQUEST_SHAPE_OK"));
    } else if (bodyText.includes(MARKERS.hookDeny)) {
      const hasToolResult = containsBlock(body.messages, (value) => value.type === "tool_result");
      writeSse(response, hasToolResult
        ? textResponse(model, "HOOK_DENY_OK")
        : toolResponse(model, "toolu_hook_deny_probe", fixture));
    } else if (bodyText.includes(MARKERS.stop)) {
      writeSse(response, bodyText.includes(MARKERS.stopReason)
        ? textResponse(model, "STOP_REENTRY_OK")
        : textResponse(model, "STOP_FIRST_END"));
    } else if (bodyText.includes(MARKERS.maxTurns)) {
      const hasToolResult = containsBlock(body.messages, (value) => value.type === "tool_result");
      writeSse(response, hasToolResult
        ? textResponse(model, "MAX_TURNS_UNEXPECTED_SECOND_REQUEST")
        : toolResponse(model, "toolu_max_turns_probe", fixture));
    } else {
      writeSse(response, textResponse(model, "AUXILIARY_OK"));
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const baseEnv = {
    ...process.env,
    HOME: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${server.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "runtime-control-probe-token",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
    PROBE_HOOK_LOG: hookLog,
    PROBE_STOP_STATE: stopState,
  };
  const commonArgs = [
    "--print",
    "--output-format", "stream-json",
    "--verbose",
    "--model", "claude-sonnet-4-5",
  ];
  const run = (args, env = baseEnv) => runCli(binary, args, {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  let requestRun;
  let hookDenyRun;
  let stopRun;
  let maxTurnsRun;
  try {
    requestRun = await run([
      ...commonArgs,
      "--tools", "Read",
      "--session-id", randomUUID(),
      MARKERS.request,
    ]);
    hookDenyRun = await run([
      ...commonArgs,
      "--settings", settingsFile,
      "--tools", "Read",
      "--permission-mode", "bypassPermissions",
      "--dangerously-skip-permissions",
      "--session-id", randomUUID(),
      MARKERS.hookDeny,
    ], { ...baseEnv, PROBE_HOOK_MODE: "deny" });
    stopRun = await run([
      ...commonArgs,
      "--settings", settingsFile,
      "--tools", "",
      "--session-id", randomUUID(),
      MARKERS.stop,
    ], { ...baseEnv, PROBE_HOOK_MODE: "stop" });
    maxTurnsRun = await run([
      ...commonArgs,
      "--settings", settingsFile,
      "--tools", "Read",
      "--permission-mode", "bypassPermissions",
      "--dangerously-skip-permissions",
      "--max-turns", "1",
      "--session-id", randomUUID(),
      MARKERS.maxTurns,
    ], { ...baseEnv, PROBE_HOOK_MODE: "observe" });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env: baseEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const hookEvents = await readJsonLines(hookLog);
  const requestGroups = Object.fromEntries(Object.entries(MARKERS)
    .filter(([key]) => ["request", "hookDeny", "stop", "maxTurns"].includes(key))
    .map(([key, marker]) => [key, requests.filter(({ body }) => JSON.stringify(body.messages).includes(marker))]));

  const requestShapeBody = requestGroups.request[0]?.body;
  const requestShapeHeaders = requestGroups.request[0]?.headers ?? {};
  const hookDenySecond = requestGroups.hookDeny[1]?.body;
  const hookDenyToolResult = containsBlock(hookDenySecond?.messages, (value) =>
    value.type === "tool_result"
      && value.tool_use_id === "toolu_hook_deny_probe"
      && JSON.stringify(value.content).includes(MARKERS.hookReason)
      && !JSON.stringify(value.content).includes(MARKERS.file)
  );
  const stopSecondText = JSON.stringify(requestGroups.stop[1]?.body?.messages);
  const maxTurnPostToolHook = hookEvents.some((event) =>
    event.event === "PostToolUse" && event.toolUseId === "toolu_max_turns_probe"
  );

  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    requestExitZero: requestRun.exitStatus === 0,
    requestResultSuccess: resultEvent(requestRun)?.result === "REQUEST_SHAPE_OK",
    requestUsesBearerAuth: requestShapeHeaders.authorization === "Bearer runtime-control-probe-token",
    requestOmitsApiKeyHeader: requestShapeHeaders["x-api-key"] === undefined,
    requestHasAnthropicVersion: typeof requestShapeHeaders["anthropic-version"] === "string",
    requestHasBetaHeader: typeof requestShapeHeaders["anthropic-beta"] === "string",
    requestModelMatches: requestShapeBody?.model === "claude-sonnet-4-5",
    requestAdvertisesRead: requestShapeBody?.tools?.some((tool) => tool.name === "Read") ?? false,
    requestHasCacheControl: countCacheControls(requestShapeBody) > 0,
    hookDenyExitZero: hookDenyRun.exitStatus === 0,
    hookDenyResultSuccess: resultEvent(hookDenyRun)?.result === "HOOK_DENY_OK",
    hookDenyEventObserved: hookEvents.some((event) => event.event === "PreToolUse" && event.toolUseId === "toolu_hook_deny_probe"),
    hookDenyReturnsPairedError: hookDenyToolResult,
    stopExitZero: stopRun.exitStatus === 0,
    stopResultSuccess: resultEvent(stopRun)?.result === "STOP_REENTRY_OK",
    stopHookRanTwice: hookEvents.filter((event) => event.event === "Stop").length >= 2,
    stopCreatedSecondRequest: requestGroups.stop.length === 2,
    stopFeedbackEnteredContext: stopSecondText.includes(MARKERS.stopReason),
    maxTurnsNoSecondRequest: requestGroups.maxTurns.length === 1,
    maxTurnsToolCompleted: maxTurnPostToolHook,
    maxTurnsResultObserved: resultEvent(maxTurnsRun) !== undefined,
  };

  const report = {
    schemaVersion: 1,
    target: {
      version: expectedVersion,
      binarySha256: await sha256(binary),
    },
    commands: {
      requestShape: "$CLAUDE_2_1_235 --print REQUEST_SHAPE_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Read --session-id $SESSION_ID",
      hookDeny: "$CLAUDE_2_1_235 --print HOOK_DENY_PROMPT_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --settings $SETTINGS --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID",
      stopReentry: "$CLAUDE_2_1_235 --print STOP_REENTRY_PROMPT_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --settings $SETTINGS --tools '' --session-id $SESSION_ID",
      maxTurns: "$CLAUDE_2_1_235 --print MAX_TURNS_PROMPT_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --settings $SETTINGS --tools Read --permission-mode bypassPermissions --dangerously-skip-permissions --max-turns 1 --session-id $SESSION_ID",
    },
    input: {
      requestShape: { prompt: MARKERS.request, auth: "ANTHROPIC_AUTH_TOKEN", tools: ["Read"] },
      hookDeny: { prompt: MARKERS.hookDeny, toolUseId: "toolu_hook_deny_probe", hookReason: MARKERS.hookReason },
      stopReentry: { prompt: MARKERS.stop, firstModelResult: "STOP_FIRST_END", feedback: MARKERS.stopReason },
      maxTurns: { prompt: MARKERS.maxTurns, maxTurns: 1, toolUseId: "toolu_max_turns_probe" },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      requestShape: normalizeResult(requestRun),
      hookDeny: normalizeResult(hookDenyRun),
      stopReentry: normalizeResult(stopRun),
      maxTurns: normalizeResult(maxTurnsRun),
    },
    exitStatus: {
      version: versionRun.exitStatus,
      requestShape: requestRun.exitStatus,
      hookDeny: hookDenyRun.exitStatus,
      stopReentry: stopRun.exitStatus,
      maxTurns: maxTurnsRun.exitStatus,
    },
    observed: {
      requestShape: {
        requestCount: requestGroups.request.length,
        authHeader: requestShapeHeaders.authorization === undefined ? "absent" : "Bearer $TOKEN",
        apiKeyHeader: requestShapeHeaders["x-api-key"] === undefined ? "absent" : "present",
        anthropicVersion: requestShapeHeaders["anthropic-version"] ?? null,
        anthropicBetaPresent: typeof requestShapeHeaders["anthropic-beta"] === "string",
        cacheControlCount: countCacheControls(requestShapeBody),
        toolNames: requestShapeBody?.tools?.map((tool) => tool.name) ?? [],
      },
      hookDeny: {
        requestCount: requestGroups.hookDeny.length,
        pairedErrorResult: hookDenyToolResult,
        preToolUseEvents: hookEvents.filter((event) => event.event === "PreToolUse").length,
      },
      stopReentry: {
        requestCount: requestGroups.stop.length,
        stopEvents: hookEvents.filter((event) => event.event === "Stop").length,
        feedbackInSecondRequest: stopSecondText.includes(MARKERS.stopReason),
      },
      maxTurns: {
        requestCount: requestGroups.maxTurns.length,
        postToolUseObserved: maxTurnPostToolHook,
      },
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(requestRun.stderr);
    process.stderr.write(hookDenyRun.stderr);
    process.stderr.write(stopRun.stderr);
    process.stderr.write(maxTurnsRun.stderr);
    process.exitCode = 1;
  }
}

await main();
