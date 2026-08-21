#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const MARKERS = {
  redacted: "TELEMETRY_REDACTED_PROMPT_MARKER",
  included: "TELEMETRY_INCLUDED_PROMPT_MARKER",
};

function writeSse(response, model, text) {
  const id = `msg_${text.toLowerCase()}`;
  const events = [
    ["message_start", {
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
    }],
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
  response.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "request-id": id,
  });
  for (const [event, data] of events) {
    response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  }
  response.end();
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

function resultEvent(run) {
  try {
    return run.stdout
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line))
      .findLast((event) => event.type === "result");
  } catch {
    return undefined;
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

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

function payloadText(records) {
  return records.map((record) => record.body).join("\n");
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-telemetry-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);

  const messageRequests = [];
  const messageServer = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    messageRequests.push(body);
    const bodyText = JSON.stringify(body);
    const marker = bodyText.includes(MARKERS.redacted) ? "REDACTED"
      : bodyText.includes(MARKERS.included) ? "INCLUDED"
        : "AUXILIARY";
    writeSse(response, body.model ?? "claude-probe", `${marker}_OK`);
  });

  const telemetryRequests = [];
  const telemetryServer = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    telemetryRequests.push({
      method: request.method,
      url: request.url,
      contentType: request.headers["content-type"] ?? null,
      body: Buffer.concat(chunks).toString("utf8"),
    });
    response.writeHead(200, { "content-type": "application/json" });
    response.end("{}");
  });

  await Promise.all([
    new Promise((resolve, reject) => {
      messageServer.once("error", reject);
      messageServer.listen(0, "127.0.0.1", resolve);
    }),
    new Promise((resolve, reject) => {
      telemetryServer.once("error", reject);
      telemetryServer.listen(0, "127.0.0.1", resolve);
    }),
  ]);

  const baseEnv = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${messageServer.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "telemetry-probe-token",
    ANTHROPIC_API_KEY: "",
    CLAUDE_CODE_ENABLE_TELEMETRY: "1",
    OTEL_METRICS_EXPORTER: "none",
    OTEL_LOGS_EXPORTER: "otlp",
    OTEL_TRACES_EXPORTER: "none",
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: "http/json",
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: `http://127.0.0.1:${telemetryServer.address().port}/v1/logs`,
    OTEL_LOGS_EXPORT_INTERVAL: "50",
    CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS: "5000",
    CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS: "5000",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_GROWTHBOOK: "1",
  };
  for (const key of ["DISABLE_TELEMETRY", "DO_NOT_TRACK", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"]) {
    delete baseEnv[key];
  }
  const commonArgs = [
    "--print",
    "--output-format", "stream-json",
    "--verbose",
    "--model", "claude-sonnet-4-5",
    "--tools", "",
  ];
  const run = (prompt, env) => runCli(binary, [
    ...commonArgs,
    "--session-id", randomUUID(),
    prompt,
  ], {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  let redactedRun;
  let includedRun;
  let redactedTelemetry;
  let includedTelemetry;
  try {
    let start = telemetryRequests.length;
    redactedRun = await run(MARKERS.redacted, baseEnv);
    redactedTelemetry = telemetryRequests.slice(start);

    start = telemetryRequests.length;
    includedRun = await run(MARKERS.included, {
      ...baseEnv,
      OTEL_LOG_USER_PROMPTS: "1",
    });
    includedTelemetry = telemetryRequests.slice(start);
  } finally {
    await Promise.all([
      new Promise((resolve) => messageServer.close(resolve)),
      new Promise((resolve) => telemetryServer.close(resolve)),
    ]);
  }

  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env: baseEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const redactedText = payloadText(redactedTelemetry);
  const includedText = payloadText(includedTelemetry);
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    redactedRunSucceeds: redactedRun.exitStatus === 0 && resultEvent(redactedRun)?.result === "REDACTED_OK",
    includedRunSucceeds: includedRun.exitStatus === 0 && resultEvent(includedRun)?.result === "INCLUDED_OK",
    redactedExportObserved: redactedTelemetry.some((record) => record.method === "POST" && record.url === "/v1/logs"),
    includedExportObserved: includedTelemetry.some((record) => record.method === "POST" && record.url === "/v1/logs"),
    redactedPayloadHasUserPromptEvent: redactedText.includes("claude_code.user_prompt"),
    redactedPayloadUsesPlaceholder: redactedText.includes("<REDACTED>"),
    redactedPayloadOmitsPrompt: !redactedText.includes(MARKERS.redacted),
    includedPayloadHasUserPromptEvent: includedText.includes("claude_code.user_prompt"),
    includedPayloadContainsPrompt: includedText.includes(MARKERS.included),
    exportsUseJsonContentType: [...redactedTelemetry, ...includedTelemetry]
      .every((record) => String(record.contentType).startsWith("application/json")),
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
      redacted: "CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_LOGS_EXPORTER=otlp OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json $CLAUDE_TARGET --print TELEMETRY_REDACTED_PROMPT_MARKER --tools ''",
      included: "OTEL_LOG_USER_PROMPTS=1 CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_LOGS_EXPORTER=otlp OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json $CLAUDE_TARGET --print TELEMETRY_INCLUDED_PROMPT_MARKER --tools ''",
    },
    input: {
      redacted: { prompt: MARKERS.redacted, logUserPrompts: false },
      included: { prompt: MARKERS.included, logUserPrompts: true },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      redacted: normalizeResult(redactedRun),
      included: normalizeResult(includedRun),
      collector: {
        redacted: redactedTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
        included: includedTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
      },
    },
    exitStatus: {
      version: versionRun.exitStatus,
      redacted: redactedRun.exitStatus,
      included: includedRun.exitStatus,
    },
    observed: {
      redacted: {
        exportCount: redactedTelemetry.length,
        userPromptEvent: redactedText.includes("claude_code.user_prompt"),
        promptAttribute: redactedText.includes("<REDACTED>") ? "<REDACTED>" : "missing",
        originalPromptPresent: redactedText.includes(MARKERS.redacted),
      },
      included: {
        exportCount: includedTelemetry.length,
        userPromptEvent: includedText.includes("claude_code.user_prompt"),
        originalPromptPresent: includedText.includes(MARKERS.included),
      },
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(redactedRun.stderr);
    process.stderr.write(includedRun.stderr);
    process.exitCode = 1;
  }
}

await main();
