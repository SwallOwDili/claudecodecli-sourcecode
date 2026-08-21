#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const MARKERS = {
  policyModel: "SETTINGS_POLICY_MODEL_MARKER",
  flagModel: "SETTINGS_FLAG_MODEL_MARKER",
  localModel: "SETTINGS_LOCAL_MODEL_MARKER",
  userModel: "SETTINGS_USER_MODEL_MARKER",
  retry529: "RETRY_529_MARKER",
  noRetry400: "NO_RETRY_400_MARKER",
  fallback: "MODEL_FALLBACK_MARKER",
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

function writeApiError(response, status, type, message) {
  response.writeHead(status, {
    "content-type": "application/json",
    "request-id": `req_${status}_${Date.now()}`,
  });
  response.end(JSON.stringify({ type: "error", error: { type, message } }));
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
  try {
    return stdout.split("\n").filter(Boolean).map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

function resultEvent(run) {
  return parseStream(run.stdout).findLast((event) => event.type === "result");
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
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
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-settings-resilience-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const projectConfig = path.join(workspace, ".claude");
  const managedEmpty = path.join(temporary, "managed-empty");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(projectConfig, { recursive: true }),
    mkdir(managedEmpty, { recursive: true }),
  ]);

  const models = {
    user: "claude-haiku-4-5",
    project: "claude-sonnet-4-5",
    local: "claude-opus-4-5",
    flag: "claude-opus-4-6",
    primary: "claude-sonnet-4-5",
    fallback: "claude-haiku-4-5",
  };
  const flagSettings = path.join(temporary, "flag-settings.json");
  await Promise.all([
    writeFile(path.join(configDir, "settings.json"), JSON.stringify({ model: models.user })),
    writeFile(path.join(projectConfig, "settings.json"), JSON.stringify({ model: models.project })),
    writeFile(path.join(projectConfig, "settings.local.json"), JSON.stringify({ model: models.local })),
    writeFile(flagSettings, JSON.stringify({ model: models.flag })),
  ]);
  const requests = [];
  const attempts = new Map();
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
    const marker = Object.values(MARKERS).find((value) => bodyText.includes(value)) ?? "AUXILIARY";
    const attempt = (attempts.get(marker) ?? 0) + 1;
    attempts.set(marker, attempt);
    requests.push({ marker, attempt, body });
    const model = body.model ?? "claude-probe";

    if (marker === MARKERS.retry529 && attempt <= 2) {
      writeApiError(response, 529, "overloaded_error", "controlled overload");
      return;
    }
    if (marker === MARKERS.noRetry400) {
      writeApiError(response, 400, "invalid_request_error", "controlled invalid request");
      return;
    }
    if (marker === MARKERS.fallback && model === models.primary) {
      writeApiError(response, 529, "overloaded_error", "controlled primary overload");
      return;
    }
    writeSse(response, textResponse(model, `${marker}_OK`));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const baseEnv = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${server.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "settings-resilience-probe-token",
    ANTHROPIC_API_KEY: "",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };
  const commonArgs = [
    "--print",
    "--output-format", "stream-json",
    "--verbose",
    "--tools", "",
    "--setting-sources", "user,project,local",
  ];
  const run = (args, env = baseEnv) => runCli(binary, args, {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  let policyModelRun;
  let flagModelRun;
  let localModelRun;
  let userModelRun;
  let retry529Run;
  let noRetry400Run;
  let fallbackRun;
  try {
    policyModelRun = await run([
      ...commonArgs,
      "--settings", flagSettings,
      "--session-id", randomUUID(),
      MARKERS.policyModel,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty });
    flagModelRun = await run([
      ...commonArgs,
      "--settings", flagSettings,
      "--session-id", randomUUID(),
      MARKERS.flagModel,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty });
    localModelRun = await run([
      ...commonArgs,
      "--session-id", randomUUID(),
      MARKERS.localModel,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty });
    userModelRun = await run([
      ...commonArgs,
      "--setting-sources", "user",
      "--session-id", randomUUID(),
      MARKERS.userModel,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty });

    retry529Run = await run([
      ...commonArgs,
      "--model", models.primary,
      "--session-id", randomUUID(),
      MARKERS.retry529,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty, CLAUDE_CODE_MAX_RETRIES: "2" });
    noRetry400Run = await run([
      ...commonArgs,
      "--model", models.primary,
      "--session-id", randomUUID(),
      MARKERS.noRetry400,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty, CLAUDE_CODE_MAX_RETRIES: "2" });
    fallbackRun = await run([
      ...commonArgs,
      "--model", models.primary,
      "--fallback-model", models.fallback,
      "--session-id", randomUUID(),
      MARKERS.fallback,
    ], { ...baseEnv, CLAUDE_CODE_MANAGED_SETTINGS_PATH: managedEmpty, CLAUDE_CODE_MAX_RETRIES: "2" });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env: baseEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const grouped = Object.fromEntries(Object.values(MARKERS).map((marker) => [
    marker,
    requests.filter((item) => item.marker === marker),
  ]));
  const fallbackModels = grouped[MARKERS.fallback].map(({ body }) => body.model);
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    flagModelWinsAcrossLoadedSources: grouped[MARKERS.policyModel][0]?.body?.model === models.flag,
    flagModelWins: grouped[MARKERS.flagModel][0]?.body?.model === models.flag,
    localModelWinsWithoutFlagOrPolicy: grouped[MARKERS.localModel][0]?.body?.model === models.local,
    userSourceFilterExcludesProjectAndLocal: grouped[MARKERS.userModel][0]?.body?.model === models.user,
    settingsRunsSucceed: [policyModelRun, flagModelRun, localModelRun, userModelRun].every((runResult) => runResult.exitStatus === 0),
    overloadedRequestRetried: grouped[MARKERS.retry529].length === 3,
    overloadedRetryEventuallySucceeds: retry529Run.exitStatus === 0 && resultEvent(retry529Run)?.result === `${MARKERS.retry529}_OK`,
    invalidRequestNotRetried: grouped[MARKERS.noRetry400].length === 1,
    invalidRequestFails: noRetry400Run.exitStatus !== 0 && resultEvent(noRetry400Run)?.is_error === true,
    fallbackRequestSequenceExact: JSON.stringify(fallbackModels) === JSON.stringify([
      models.primary,
      models.primary,
      models.primary,
      models.fallback,
    ]),
    fallbackEventuallySucceeds: fallbackRun.exitStatus === 0 && resultEvent(fallbackRun)?.result === `${MARKERS.fallback}_OK`,
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
      allLoadedSources: "$CLAUDE_TARGET --print SETTINGS_POLICY_MODEL_MARKER --settings $FLAG_SETTINGS --setting-sources user,project,local",
      flagModel: "$CLAUDE_TARGET --print SETTINGS_FLAG_MODEL_MARKER --settings $FLAG_SETTINGS --setting-sources user,project,local",
      localModel: "$CLAUDE_TARGET --print SETTINGS_LOCAL_MODEL_MARKER --setting-sources user,project,local",
      userModel: "$CLAUDE_TARGET --print SETTINGS_USER_MODEL_MARKER --setting-sources user",
      retry529: "CLAUDE_CODE_MAX_RETRIES=2 $CLAUDE_TARGET --print RETRY_529_MARKER --model claude-sonnet-4-5",
      noRetry400: "CLAUDE_CODE_MAX_RETRIES=2 $CLAUDE_TARGET --print NO_RETRY_400_MARKER --model claude-sonnet-4-5",
      fallback: "CLAUDE_CODE_MAX_RETRIES=2 $CLAUDE_TARGET --print MODEL_FALLBACK_MARKER --model claude-sonnet-4-5 --fallback-model claude-haiku-4-5",
    },
    input: {
      settingsLayers: models,
      retry529: { controlledResponses: [529, 529, 200] },
      noRetry400: { controlledResponses: [400] },
      fallback: {
        primaryModel: models.primary,
        fallbackModel: models.fallback,
        controlledResponses: [529, 529, 529, 200],
      },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      policyModel: normalizeResult(policyModelRun),
      flagModel: normalizeResult(flagModelRun),
      localModel: normalizeResult(localModelRun),
      userModel: normalizeResult(userModelRun),
      retry529: normalizeResult(retry529Run),
      noRetry400: normalizeResult(noRetry400Run),
      fallback: normalizeResult(fallbackRun),
    },
    exitStatus: {
      version: versionRun.exitStatus,
      policyModel: policyModelRun.exitStatus,
      flagModel: flagModelRun.exitStatus,
      localModel: localModelRun.exitStatus,
      userModel: userModelRun.exitStatus,
      retry529: retry529Run.exitStatus,
      noRetry400: noRetry400Run.exitStatus,
      fallback: fallbackRun.exitStatus,
    },
    observed: {
      settingsModels: {
        allLoadedSources: grouped[MARKERS.policyModel][0]?.body?.model ?? null,
        flag: grouped[MARKERS.flagModel][0]?.body?.model ?? null,
        local: grouped[MARKERS.localModel][0]?.body?.model ?? null,
        userOnly: grouped[MARKERS.userModel][0]?.body?.model ?? null,
      },
      managedPolicyBoundary: "The exact binary reads macOS managed settings from /Library/Application Support/ClaudeCode; the environment field CLAUDE_CODE_MANAGED_SETTINGS_PATH did not redirect that runtime path in this probe.",
      retry529: {
        requestCount: grouped[MARKERS.retry529].length,
        models: grouped[MARKERS.retry529].map(({ body }) => body.model),
      },
      noRetry400: {
        requestCount: grouped[MARKERS.noRetry400].length,
      },
      fallback: {
        requestCount: grouped[MARKERS.fallback].length,
        models: fallbackModels,
      },
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    for (const runResult of [policyModelRun, flagModelRun, localModelRun, userModelRun, retry529Run, noRetry400Run, fallbackRun]) {
      if (runResult.stderr) process.stderr.write(runResult.stderr);
    }
    process.exitCode = 1;
  }
}

await main();
