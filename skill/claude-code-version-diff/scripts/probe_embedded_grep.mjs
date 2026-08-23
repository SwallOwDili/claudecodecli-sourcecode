#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { resolveProbeTarget } from "./probe_target.mjs";

const PROCESS_TIMEOUT_MS = 3_000;
const CLI_TIMEOUT_MS = 30_000;
const MAX_PATHOLOGICAL_RSS_BYTES = 512 * 1024 * 1024;
const PATHOLOGICAL_PATTERN = "a{1,1000000000}";

function writeSse(response, events) {
  response.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "request-id": "msg_embedded_grep_probe",
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

function toolResponse(model, id, toolUseId, input) {
  return [
    messageStart(model, id),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "tool_use", id: toolUseId, name: "Grep", input: {} },
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
    messageStart(model, "msg_embedded_grep_done"),
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

function findBlock(value, predicate) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findBlock(item, predicate);
      if (found !== undefined) return found;
    }
    return undefined;
  }
  if (!value || typeof value !== "object") return undefined;
  if (predicate(value)) return value;
  for (const item of Object.values(value)) {
    const found = findBlock(item, predicate);
    if (found !== undefined) return found;
  }
  return undefined;
}

function toolResultText(block) {
  if (!block) return "";
  if (typeof block.content === "string") return block.content;
  return JSON.stringify(block.content);
}

function parseStream(stdout) {
  return stdout.split("\n").filter(Boolean).map((line) => JSON.parse(line));
}

function resultEvent(events) {
  return events.findLast((event) => event.type === "result");
}

function terminateProcessGroup(child, signal) {
  if (child.pid === undefined) return;
  try {
    process.kill(-child.pid, signal);
  } catch {
    try {
      child.kill(signal);
    } catch {
      // The process already exited.
    }
  }
}

function runProcess(command, args, options, timeoutMs) {
  return new Promise((resolve, reject) => {
    const startedAt = performance.now();
    const child = spawn(command, args, { ...options, detached: true });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    const timer = setTimeout(() => {
      timedOut = true;
      terminateProcessGroup(child, "SIGTERM");
      setTimeout(() => terminateProcessGroup(child, "SIGKILL"), 500).unref();
    }, timeoutMs);
    child.once("close", (exitStatus, signal) => {
      clearTimeout(timer);
      resolve({
        exitStatus,
        signal,
        stdout,
        stderr,
        timedOut,
        elapsedMs: Math.round((performance.now() - startedAt) * 100) / 100,
      });
    });
  });
}

function splitTimeMetrics(stderr) {
  const metricStart = stderr.search(/(?:^|\n)\s*\d+\.\d+\s+real\s+/);
  const toolStderr = metricStart < 0 ? stderr : stderr.slice(0, metricStart).replace(/\n?$/, "\n");
  const maximumResidentSet = stderr.match(/\n?\s*(\d+)\s+maximum resident set size/);
  const peakMemoryFootprint = stderr.match(/\n?\s*(\d+)\s+peak memory footprint/);
  return {
    toolStderr,
    maximumResidentSetBytes: maximumResidentSet ? Number(maximumResidentSet[1]) : null,
    peakMemoryFootprintBytes: peakMemoryFootprint ? Number(peakMemoryFootprint[1]) : null,
  };
}

async function runTimedEmbeddedRg(binary, args, cwd) {
  const result = await runProcess(
    "/usr/bin/time",
    ["-l", "/bin/bash", "-c", 'exec -a rg "$1" "${@:2}"', "_", binary, ...args],
    { cwd, env: process.env, stdio: ["ignore", "pipe", "pipe"] },
    PROCESS_TIMEOUT_MS,
  );
  const metrics = splitTimeMetrics(result.stderr);
  return { ...result, stderr: metrics.toolStderr, ...metrics };
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

function normalize(value, temporary) {
  if (typeof value === "string") return value.split(temporary).join("$PROBE_ROOT");
  if (Array.isArray(value)) return value.map((item) => normalize(item, temporary));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, normalize(item, temporary)]),
  );
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-embedded-grep-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);

  const contextLines = [
    "zero",
    "MATCH first",
    "after one",
    "after two",
    "MATCH second",
    "after second",
    "tail",
  ];
  const longMarker = "LONG_MATCH_MARKER";
  const longLine = `${"L".repeat(600)}${longMarker}${"R".repeat(600)}`;
  await Promise.all([
    writeFile(path.join(workspace, "context.txt"), `${contextLines.join("\n")}\n`),
    writeFile(path.join(workspace, "long.txt"), `${longLine}\nshort\n`),
    writeFile(path.join(workspace, "pathological.txt"), "aaaa\n"),
  ]);

  const embeddedVersion = await runTimedEmbeddedRg(binary, ["--version"], workspace);
  const maxCountAfter = await runTimedEmbeddedRg(
    binary,
    ["--no-config", "-n", "-m", "1", "-A", "2", "MATCH", "context.txt"],
    workspace,
  );
  const maxCountBoth = await runTimedEmbeddedRg(
    binary,
    ["--no-config", "-n", "-m", "1", "-C", "2", "MATCH", "context.txt"],
    workspace,
  );
  const pathological = await runTimedEmbeddedRg(
    binary,
    ["--no-config", PATHOLOGICAL_PATTERN, "pathological.txt"],
    workspace,
  );

  const prompt = "EMBEDDED_GREP_TOOL_PROBE";
  const longToolUseId = "toolu_embedded_grep_long_line";
  const pathologicalToolUseId = "toolu_embedded_grep_pathological";
  const requestBodies = [];
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
    const isProbeRequest = body.tools?.some((tool) => tool.name === "Grep")
      || bodyText.includes(prompt)
      || bodyText.includes(longToolUseId)
      || bodyText.includes(pathologicalToolUseId);
    if (!isProbeRequest) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "AUXILIARY_OK"));
      return;
    }

    requestBodies.push(body);
    if (requestBodies.length === 1) {
      writeSse(response, toolResponse(
        body.model ?? "claude-probe",
        "msg_embedded_grep_long",
        longToolUseId,
        { pattern: longMarker, path: ".", output_mode: "content" },
      ));
    } else if (requestBodies.length === 2) {
      writeSse(response, toolResponse(
        body.model ?? "claude-probe",
        "msg_embedded_grep_pathological",
        pathologicalToolUseId,
        { pattern: PATHOLOGICAL_PATTERN, path: ".", output_mode: "content" },
      ));
    } else {
      writeSse(response, textResponse(body.model ?? "claude-probe", "EMBEDDED_GREP_TOOL_OK"));
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
    ANTHROPIC_AUTH_TOKEN: "probe-token",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };
  let grepToolRun;
  try {
    grepToolRun = await runProcess(binary, [
      "--print",
      "--output-format", "stream-json",
      "--verbose",
      "--model", "claude-sonnet-4-5",
      "--tools", "Grep",
      "--permission-mode", "bypassPermissions",
      "--dangerously-skip-permissions",
      "--no-session-persistence",
      prompt,
    ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] }, CLI_TIMEOUT_MS);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const events = parseStream(grepToolRun.stdout);
  const result = resultEvent(events);
  const firstBody = requestBodies[0];
  const secondBody = requestBodies[1];
  const thirdBody = requestBodies[2];
  const grepSchema = firstBody?.tools?.find((tool) => tool.name === "Grep")?.input_schema;
  const schemaProperties = Object.keys(grepSchema?.properties ?? {}).sort();
  const longToolResult = findBlock(secondBody?.messages, (value) =>
    value.type === "tool_result" && value.tool_use_id === longToolUseId
  );
  const pathologicalToolResult = findBlock(thirdBody?.messages, (value) =>
    value.type === "tool_result" && value.tool_use_id === pathologicalToolUseId
  );
  const longToolResultLiteral = toolResultText(longToolResult);
  const pathologicalToolResultLiteral = toolResultText(pathologicalToolResult);
  const expectedAfter = "2:MATCH first\n3-after one\n4-after two\n";
  const expectedBoth = "1-zero\n2:MATCH first\n3-after one\n4-after two\n";
  const expectedFastFail = "rg: compiled regex exceeds size limit of 104857600\n";
  const binaryHash = await sha256(binary);

  const checks = {
    exactVersion: expectedVersion === "2.1.235",
    exactBinarySha256: binaryHash === expectedSha256,
    embeddedVersionExitZero: embeddedVersion.exitStatus === 0,
    embeddedVersionIsRipgrep1411PatchedRevision:
      embeddedVersion.stdout.startsWith("ripgrep 14.1.1 (rev fdb5e06cce)\n"),
    maxCountAfterExitZero: maxCountAfter.exitStatus === 0,
    maxCountAfterLiteralOutput: maxCountAfter.stdout === expectedAfter,
    maxCountAfterDidNotTimeout: maxCountAfter.timedOut === false,
    maxCountBothExitZero: maxCountBoth.exitStatus === 0,
    maxCountBothLiteralOutput: maxCountBoth.stdout === expectedBoth,
    maxCountBothDidNotTimeout: maxCountBoth.timedOut === false,
    pathologicalExitTwo: pathological.exitStatus === 2,
    pathologicalFastFailLiteral: pathological.stderr === expectedFastFail,
    pathologicalDidNotTimeout: pathological.timedOut === false,
    pathologicalCompletedWithinDeadline: pathological.elapsedMs < PROCESS_TIMEOUT_MS,
    pathologicalPeakRssMeasured:
      Number.isInteger(pathological.maximumResidentSetBytes)
      && pathological.maximumResidentSetBytes > 0,
    pathologicalPeakRssBounded:
      Number.isInteger(pathological.maximumResidentSetBytes)
      && pathological.maximumResidentSetBytes < MAX_PATHOLOGICAL_RSS_BYTES,
    grepToolExitZero: grepToolRun.exitStatus === 0,
    grepToolDidNotTimeout: grepToolRun.timedOut === false,
    firstRequestAdvertisesGrep: firstBody?.tools?.some((tool) => tool.name === "Grep") ?? false,
    grepSchemaDoesNotExposeMaxCount:
      !schemaProperties.includes("-m") && !schemaProperties.includes("max_count"),
    longLineToolResultPaired: longToolResult !== undefined,
    longLineUsesOmissionMarker: longToolResultLiteral.includes("[Omitted long matching line]"),
    longLineDoesNotLeakFullInput: !longToolResultLiteral.includes(longMarker),
    pathologicalToolResultPaired: pathologicalToolResult !== undefined,
    pathologicalToolResultIsError: pathologicalToolResult?.is_error === true,
    pathologicalToolResultContainsFastFail:
      pathologicalToolResultLiteral.includes("compiled regex exceeds size limit of 104857600"),
    finalResultSuccess:
      result?.subtype === "success" && result?.result === "EMBEDDED_GREP_TOOL_OK",
  };

  const report = normalize({
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    environment: {
      platform: process.platform,
      arch: process.arch,
      nodeVersion: process.version,
    },
    target: { version: expectedVersion, binarySha256: binaryHash },
    commands: {
      embeddedVersion: "$CLAUDE_TARGET (argv0=rg) --version",
      maxCountAfterContext: "(cwd=$FIXTURE) $CLAUDE_TARGET (argv0=rg) --no-config -n -m 1 -A 2 MATCH context.txt",
      maxCountBothContext: "(cwd=$FIXTURE) $CLAUDE_TARGET (argv0=rg) --no-config -n -m 1 -C 2 MATCH context.txt",
      pathological: "(cwd=$FIXTURE) $CLAUDE_TARGET (argv0=rg) --no-config 'a{1,1000000000}' pathological.txt",
      grepTool: "$CLAUDE_TARGET --print EMBEDDED_GREP_TOOL_PROBE --output-format stream-json --verbose --model claude-sonnet-4-5 --tools Grep --permission-mode bypassPermissions --dangerously-skip-permissions --no-session-persistence",
    },
    input: {
      contextFixture: contextLines,
      pathological: {
        pattern: PATHOLOGICAL_PATTERN,
        fixture: "aaaa\\n",
        deadlineMs: PROCESS_TIMEOUT_MS,
        maximumResidentSetBoundBytes: MAX_PATHOLOGICAL_RSS_BYTES,
      },
      longLine: {
        utf8Bytes: Buffer.byteLength(longLine),
        shape: "600 x L + LONG_MATCH_MARKER + 600 x R",
      },
      modelToolUses: [
        { id: longToolUseId, name: "Grep", input: { pattern: longMarker, path: ".", output_mode: "content" } },
        { id: pathologicalToolUseId, name: "Grep", input: { pattern: PATHOLOGICAL_PATTERN, path: ".", output_mode: "content" } },
      ],
      schemaReachability: {
        grepInputProperties: schemaProperties,
        maxCountExposed: schemaProperties.includes("-m") || schemaProperties.includes("max_count"),
        boundary: "The 2.1.235 Grep tool schema has no -m/max_count field, so -m context semantics are reached through the same embedded argv0=rg engine rather than fabricated as a model tool input.",
      },
    },
    literalOutput: {
      embeddedVersion: embeddedVersion.stdout,
      maxCountAfterContext: maxCountAfter.stdout,
      maxCountBothContext: maxCountBoth.stdout,
      pathological: {
        stdout: pathological.stdout,
        stderr: pathological.stderr,
        signal: pathological.signal,
        timedOut: pathological.timedOut,
        elapsedMs: pathological.elapsedMs,
        maximumResidentSetBytes: pathological.maximumResidentSetBytes,
        peakMemoryFootprintBytes: pathological.peakMemoryFootprintBytes,
      },
      grepTool: {
        result: result?.result ?? null,
        subtype: result?.subtype ?? null,
        longLineToolResult: longToolResult ?? null,
        pathologicalToolResult: pathologicalToolResult ?? null,
      },
    },
    exitStatus: {
      embeddedVersion: embeddedVersion.exitStatus,
      maxCountAfterContext: maxCountAfter.exitStatus,
      maxCountBothContext: maxCountBoth.exitStatus,
      pathological: pathological.exitStatus,
      grepTool: grepToolRun.exitStatus,
    },
    observedRequestCount: requestBodies.length,
    checks,
  }, temporary);
  report.checks.reportHasNoAbsoluteProbePath = !JSON.stringify(report).includes(temporary);
  report.checks.reportHasNoSessionIdentifier = !/session[_ -]?id/i.test(JSON.stringify(report));
  report.pass = Object.values(report.checks).every(Boolean);

  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(grepToolRun.stderr);
    process.exitCode = 1;
  }
  await rm(temporary, { recursive: true, force: true });
}

await main();
