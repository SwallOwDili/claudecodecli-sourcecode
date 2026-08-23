#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, readdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const MARKERS = {
  redacted: "TELEMETRY_REDACTED_PROMPT_MARKER",
  included: "TELEMETRY_INCLUDED_PROMPT_MARKER",
  rawDefaultRequest: "RAW_API_DEFAULT_REQUEST_MARKER",
  rawDefaultResponse: "RAW_API_DEFAULT_RESPONSE_MARKER",
  rawInlineRequest: "RAW_API_INLINE_REQUEST_MARKER",
  rawInlineResponse: "RAW_API_INLINE_RESPONSE_MARKER",
  rawFileRequest: "RAW_API_FILE_REQUEST_MARKER",
  rawFileResponse: "RAW_API_FILE_RESPONSE_MARKER",
};

const RAW_RESPONSE_BY_REQUEST = new Map([
  [MARKERS.rawDefaultRequest, MARKERS.rawDefaultResponse],
  [MARKERS.rawInlineRequest, MARKERS.rawInlineResponse],
  [MARKERS.rawFileRequest, MARKERS.rawFileResponse],
]);

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

async function waitForRawBodyFiles(directory, minimum = 2) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const names = await readdir(directory).catch(() => []);
    const jsonNames = names.filter((name) => name.endsWith(".json")).sort();
    if (jsonNames.length >= minimum) {
      return Promise.all(jsonNames.map(async (name) => ({
        name,
        body: await readFile(path.join(directory, name), "utf8"),
      })));
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return [];
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-telemetry-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const rawBodyDir = path.join(temporary, "raw-api-bodies");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
    mkdir(rawBodyDir, { recursive: true }),
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
    const rawResponse = [...RAW_RESPONSE_BY_REQUEST]
      .find(([requestMarker]) => bodyText.includes(requestMarker))?.[1];
    const text = rawResponse ?? (bodyText.includes(MARKERS.redacted) ? "REDACTED_OK"
      : bodyText.includes(MARKERS.included) ? "INCLUDED_OK"
        : "AUXILIARY_OK");
    writeSse(response, body.model ?? "claude-probe", text);
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
  for (const key of [
    "DISABLE_TELEMETRY",
    "DO_NOT_TRACK",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_RAW_API_BODIES",
  ]) {
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
  let rawDefaultRun;
  let rawInlineRun;
  let rawFileRun;
  let rawDefaultTelemetry;
  let rawInlineTelemetry;
  let rawFileTelemetry;
  let rawBodyFiles = [];
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

    start = telemetryRequests.length;
    rawDefaultRun = await run(MARKERS.rawDefaultRequest, baseEnv);
    rawDefaultTelemetry = telemetryRequests.slice(start);

    start = telemetryRequests.length;
    rawInlineRun = await run(MARKERS.rawInlineRequest, {
      ...baseEnv,
      OTEL_LOG_RAW_API_BODIES: "1",
    });
    rawInlineTelemetry = telemetryRequests.slice(start);

    start = telemetryRequests.length;
    rawFileRun = await run(MARKERS.rawFileRequest, {
      ...baseEnv,
      OTEL_LOG_RAW_API_BODIES: `file:${rawBodyDir}`,
    });
    rawFileTelemetry = telemetryRequests.slice(start);
    rawBodyFiles = await waitForRawBodyFiles(rawBodyDir);
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
  const rawDefaultText = payloadText(rawDefaultTelemetry);
  const rawInlineText = payloadText(rawInlineTelemetry);
  const rawFileText = payloadText(rawFileTelemetry);
  const rawBodyFileText = rawBodyFiles.map(({ body }) => body).join("\n");
  const allTelemetry = [
    ...redactedTelemetry,
    ...includedTelemetry,
    ...rawDefaultTelemetry,
    ...rawInlineTelemetry,
    ...rawFileTelemetry,
  ];
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
    rawDefaultRunSucceeds: rawDefaultRun.exitStatus === 0
      && resultEvent(rawDefaultRun)?.result === MARKERS.rawDefaultResponse,
    rawInlineRunSucceeds: rawInlineRun.exitStatus === 0
      && resultEvent(rawInlineRun)?.result === MARKERS.rawInlineResponse,
    rawFileRunSucceeds: rawFileRun.exitStatus === 0
      && resultEvent(rawFileRun)?.result === MARKERS.rawFileResponse,
    rawDefaultExportObserved: rawDefaultTelemetry.some((record) => record.method === "POST" && record.url === "/v1/logs"),
    rawInlineExportObserved: rawInlineTelemetry.some((record) => record.method === "POST" && record.url === "/v1/logs"),
    rawFileExportObserved: rawFileTelemetry.some((record) => record.method === "POST" && record.url === "/v1/logs"),
    rawDefaultOmitsBodyEvents: !rawDefaultText.includes("claude_code.api_request_body")
      && !rawDefaultText.includes("claude_code.api_response_body"),
    rawDefaultOmitsBodyMarkers: !rawDefaultText.includes(MARKERS.rawDefaultRequest)
      && !rawDefaultText.includes(MARKERS.rawDefaultResponse),
    rawInlineHasRequestBodyEvent: rawInlineText.includes("claude_code.api_request_body"),
    rawInlineHasResponseBodyEvent: rawInlineText.includes("claude_code.api_response_body"),
    rawInlineContainsRequestMarker: rawInlineText.includes(MARKERS.rawInlineRequest),
    rawInlineContainsResponseMarker: rawInlineText.includes(MARKERS.rawInlineResponse),
    rawFileCollectorUsesReferences: rawFileText.includes("claude_code.api_request_body")
      && rawFileText.includes("claude_code.api_response_body")
      && rawFileText.includes("body_ref"),
    rawFileCollectorOmitsBodyMarkers: !rawFileText.includes(MARKERS.rawFileRequest)
      && !rawFileText.includes(MARKERS.rawFileResponse),
    rawFileWritesRequestAndResponse: rawBodyFiles.some(({ name }) => name.endsWith(".request.json"))
      && rawBodyFiles.some(({ name }) => name.endsWith(".response.json")),
    rawFileBodiesContainMarkers: rawBodyFileText.includes(MARKERS.rawFileRequest)
      && rawBodyFileText.includes(MARKERS.rawFileResponse),
    exportsUseJsonContentType: allTelemetry
      .every((record) => String(record.contentType).startsWith("application/json")),
  };

  const report = {
    schemaVersion: 2,
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
      rawDefault: "CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_LOGS_EXPORTER=otlp OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json $CLAUDE_TARGET --print RAW_API_DEFAULT_REQUEST_MARKER --tools ''",
      rawInline: "OTEL_LOG_RAW_API_BODIES=1 CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_LOGS_EXPORTER=otlp OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json $CLAUDE_TARGET --print RAW_API_INLINE_REQUEST_MARKER --tools ''",
      rawFile: "OTEL_LOG_RAW_API_BODIES=file:$RAW_BODY_DIR CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_LOGS_EXPORTER=otlp OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json $CLAUDE_TARGET --print RAW_API_FILE_REQUEST_MARKER --tools ''",
    },
    input: {
      redacted: { prompt: MARKERS.redacted, logUserPrompts: false },
      included: { prompt: MARKERS.included, logUserPrompts: true },
      rawDefault: { prompt: MARKERS.rawDefaultRequest, rawApiBodies: "disabled" },
      rawInline: { prompt: MARKERS.rawInlineRequest, rawApiBodies: "inline" },
      rawFile: { prompt: MARKERS.rawFileRequest, rawApiBodies: "file:$RAW_BODY_DIR" },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      redacted: normalizeResult(redactedRun),
      included: normalizeResult(includedRun),
      collector: {
        redacted: redactedTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
        included: includedTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
        rawDefault: rawDefaultTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
        rawInline: rawInlineTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
        rawFile: rawFileTelemetry.map(({ method, url, contentType }) => ({ method, url, contentType })),
      },
      rawBodyFiles: rawBodyFiles.map(({ name, body }) => ({
        kind: name.endsWith(".request.json") ? "request" : "response",
        bytes: Buffer.byteLength(body),
        requestMarkerPresent: body.includes(MARKERS.rawFileRequest),
        responseMarkerPresent: body.includes(MARKERS.rawFileResponse),
      })),
    },
    exitStatus: {
      version: versionRun.exitStatus,
      redacted: redactedRun.exitStatus,
      included: includedRun.exitStatus,
      rawDefault: rawDefaultRun.exitStatus,
      rawInline: rawInlineRun.exitStatus,
      rawFile: rawFileRun.exitStatus,
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
      rawDefault: {
        exportCount: rawDefaultTelemetry.length,
        requestBodyEvent: rawDefaultText.includes("claude_code.api_request_body"),
        responseBodyEvent: rawDefaultText.includes("claude_code.api_response_body"),
      },
      rawInline: {
        exportCount: rawInlineTelemetry.length,
        requestBodyEvent: rawInlineText.includes("claude_code.api_request_body"),
        responseBodyEvent: rawInlineText.includes("claude_code.api_response_body"),
        requestMarkerPresent: rawInlineText.includes(MARKERS.rawInlineRequest),
        responseMarkerPresent: rawInlineText.includes(MARKERS.rawInlineResponse),
      },
      rawFile: {
        exportCount: rawFileTelemetry.length,
        requestBodyEvent: rawFileText.includes("claude_code.api_request_body"),
        responseBodyEvent: rawFileText.includes("claude_code.api_response_body"),
        collectorUsesBodyRef: rawFileText.includes("body_ref"),
        collectorContainsBodyMarker: rawFileText.includes(MARKERS.rawFileRequest)
          || rawFileText.includes(MARKERS.rawFileResponse),
        files: rawBodyFiles.map(({ name, body }) => ({
          kind: name.endsWith(".request.json") ? "request" : "response",
          bytes: Buffer.byteLength(body),
          requestMarkerPresent: body.includes(MARKERS.rawFileRequest),
          responseMarkerPresent: body.includes(MARKERS.rawFileResponse),
        })),
      },
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(redactedRun.stderr);
    process.stderr.write(includedRun.stderr);
    process.stderr.write(rawDefaultRun.stderr);
    process.stderr.write(rawInlineRun.stderr);
    process.stderr.write(rawFileRun.stderr);
    process.exitCode = 1;
  }
}

await main();
