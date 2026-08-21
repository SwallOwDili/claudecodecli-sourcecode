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
  allowed: "SANDBOX_ALLOWED_WRITE_MARKER",
  deniedWrite: "SANDBOX_DENIED_WRITE_MARKER",
  deniedNetwork: "SANDBOX_DENIED_NETWORK_MARKER",
};

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

function toolResponse(model, toolUseId, command) {
  return [
    messageStart(model, `msg_${toolUseId}`),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "tool_use", id: toolUseId, name: "Bash", input: {} },
    }],
    ["content_block_delta", {
      type: "content_block_delta",
      index: 0,
      delta: { type: "input_json_delta", partial_json: JSON.stringify({ command }) },
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

function findToolResult(body, toolUseId) {
  const stack = [body?.messages];
  while (stack.length > 0) {
    const value = stack.pop();
    if (Array.isArray(value)) {
      stack.push(...value);
    } else if (value && typeof value === "object") {
      if (value.type === "tool_result" && value.tool_use_id === toolUseId) return value;
      stack.push(...Object.values(value));
    }
  }
  return undefined;
}

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

async function fileText(file) {
  try {
    return await readFile(file, "utf8");
  } catch {
    return null;
  }
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-sandbox-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const outside = path.join(temporary, "outside");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
    mkdir(outside, { recursive: true }),
  ]);
  const allowedFile = path.join(workspace, "allowed.txt");
  const deniedFile = path.join(outside, "denied.txt");
  const settingsFile = path.join(temporary, "settings.json");

  let networkHits = 0;
  const networkServer = createServer((_request, response) => {
    networkHits += 1;
    response.writeHead(200, { "content-type": "text/plain" });
    response.end("NETWORK_SHOULD_NOT_BE_REACHED");
  });
  await new Promise((resolve, reject) => {
    networkServer.once("error", reject);
    networkServer.listen(0, "127.0.0.1", resolve);
  });

  await writeFile(settingsFile, JSON.stringify({
    sandbox: {
      enabled: true,
      failIfUnavailable: true,
      autoAllowBashIfSandboxed: true,
      allowUnsandboxedCommands: false,
      filesystem: {
        denyWrite: [outside],
      },
      network: {
        allowedDomains: [],
        strictAllowlist: true,
      },
    },
  }, null, 2));

  const toolUseIds = {
    allowed: "toolu_sandbox_allowed",
    deniedWrite: "toolu_sandbox_denied_write",
    deniedNetwork: "toolu_sandbox_denied_network",
  };
  const requests = [];
  const messageServer = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    requests.push(body);
    const text = JSON.stringify(body);
    const model = body.model ?? "claude-probe";
    if (text.includes(MARKERS.allowed)) {
      writeSse(response, findToolResult(body, toolUseIds.allowed)
        ? textResponse(model, "SANDBOX_ALLOWED_OK")
        : toolResponse(model, toolUseIds.allowed, `/usr/bin/printf ALLOWED > ${JSON.stringify(allowedFile)}`));
      return;
    }
    if (text.includes(MARKERS.deniedWrite)) {
      writeSse(response, findToolResult(body, toolUseIds.deniedWrite)
        ? textResponse(model, "SANDBOX_DENIED_WRITE_OK")
        : toolResponse(model, toolUseIds.deniedWrite, `/usr/bin/printf BLOCKED > ${JSON.stringify(deniedFile)}`));
      return;
    }
    if (text.includes(MARKERS.deniedNetwork)) {
      writeSse(response, findToolResult(body, toolUseIds.deniedNetwork)
        ? textResponse(model, "SANDBOX_DENIED_NETWORK_OK")
        : toolResponse(model, toolUseIds.deniedNetwork, `/usr/bin/curl --silent --show-error http://127.0.0.1:${networkServer.address().port}/probe`));
      return;
    }
    writeSse(response, textResponse(model, "AUXILIARY_OK"));
  });
  await new Promise((resolve, reject) => {
    messageServer.once("error", reject);
    messageServer.listen(0, "127.0.0.1", resolve);
  });

  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${messageServer.address().port}`,
    ANTHROPIC_AUTH_TOKEN: "sandbox-probe-token",
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
    "--model", "claude-sonnet-4-5",
    "--tools", "Bash",
    "--settings", settingsFile,
    "--permission-mode", "bypassPermissions",
    "--dangerously-skip-permissions",
  ];
  const run = (prompt) => runCli(binary, [
    ...commonArgs,
    "--session-id", randomUUID(),
    prompt,
  ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });

  let allowedRun;
  let deniedWriteRun;
  let deniedNetworkRun;
  try {
    allowedRun = await run(MARKERS.allowed);
    deniedWriteRun = await run(MARKERS.deniedWrite);
    deniedNetworkRun = await run(MARKERS.deniedNetwork);
  } finally {
    await Promise.all([
      new Promise((resolve) => messageServer.close(resolve)),
      new Promise((resolve) => networkServer.close(resolve)),
    ]);
  }

  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const bodiesByMarker = Object.fromEntries(Object.entries(MARKERS).map(([key, marker]) => [
    key,
    requests.filter((body) => JSON.stringify(body.messages).includes(marker)),
  ]));
  const allowedToolResult = findToolResult(bodiesByMarker.allowed[1], toolUseIds.allowed);
  const deniedWriteToolResult = findToolResult(bodiesByMarker.deniedWrite[1], toolUseIds.deniedWrite);
  const deniedNetworkToolResult = findToolResult(bodiesByMarker.deniedNetwork[1], toolUseIds.deniedNetwork);
  const allowedContent = JSON.stringify(allowedToolResult?.content ?? null);
  const deniedWriteContent = JSON.stringify(deniedWriteToolResult?.content ?? null);
  const deniedNetworkContent = JSON.stringify(deniedNetworkToolResult?.content ?? null);
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    allowedRunSucceeds: allowedRun.exitStatus === 0 && resultEvent(allowedRun)?.result === "SANDBOX_ALLOWED_OK",
    allowedWriteCreatedFile: await fileText(allowedFile) === "ALLOWED",
    allowedToolResultIsSuccess: allowedToolResult?.is_error !== true && allowedContent.includes("ALLOWED") === false,
    deniedWriteRunCompletesLoop: deniedWriteRun.exitStatus === 0 && resultEvent(deniedWriteRun)?.result === "SANDBOX_DENIED_WRITE_OK",
    deniedWriteReturnsToolError: deniedWriteToolResult?.is_error === true || /deny|sandbox|operation not permitted|permission/i.test(deniedWriteContent),
    deniedWriteDidNotCreateFile: await fileText(deniedFile) === null,
    deniedNetworkRunCompletesLoop: deniedNetworkRun.exitStatus === 0 && resultEvent(deniedNetworkRun)?.result === "SANDBOX_DENIED_NETWORK_OK",
    deniedNetworkReturnsToolError: deniedNetworkToolResult?.is_error === true || /deny|sandbox|network|connect|proxy/i.test(deniedNetworkContent),
    deniedNetworkDidNotReachServer: networkHits === 0,
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
      allowedWrite: "$CLAUDE_TARGET --print SANDBOX_ALLOWED_WRITE_MARKER --settings $SANDBOX_SETTINGS --tools Bash --permission-mode bypassPermissions --dangerously-skip-permissions",
      deniedWrite: "$CLAUDE_TARGET --print SANDBOX_DENIED_WRITE_MARKER --settings $SANDBOX_SETTINGS --tools Bash --permission-mode bypassPermissions --dangerously-skip-permissions",
      deniedNetwork: "$CLAUDE_TARGET --print SANDBOX_DENIED_NETWORK_MARKER --settings $SANDBOX_SETTINGS --tools Bash --permission-mode bypassPermissions --dangerously-skip-permissions",
    },
    input: {
      settings: {
        enabled: true,
        failIfUnavailable: true,
        allowUnsandboxedCommands: false,
        filesystemDenyWrite: "$OUTSIDE",
        networkAllowedDomains: [],
        networkStrictAllowlist: true,
      },
      allowedWrite: { target: "$WORKSPACE/allowed.txt", content: "ALLOWED" },
      deniedWrite: { target: "$OUTSIDE/denied.txt", content: "BLOCKED" },
      deniedNetwork: { target: "http://127.0.0.1:$PORT/probe" },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      allowedWrite: normalizeResult(allowedRun),
      deniedWrite: normalizeResult(deniedWriteRun),
      deniedNetwork: normalizeResult(deniedNetworkRun),
    },
    exitStatus: {
      version: versionRun.exitStatus,
      allowedWrite: allowedRun.exitStatus,
      deniedWrite: deniedWriteRun.exitStatus,
      deniedNetwork: deniedNetworkRun.exitStatus,
    },
    observed: {
      allowedWrite: {
        requestCount: bodiesByMarker.allowed.length,
        fileContent: await fileText(allowedFile),
        toolError: allowedToolResult?.is_error ?? false,
      },
      deniedWrite: {
        requestCount: bodiesByMarker.deniedWrite.length,
        fileExists: await fileText(deniedFile) !== null,
        toolError: deniedWriteToolResult?.is_error ?? null,
      },
      deniedNetwork: {
        requestCount: bodiesByMarker.deniedNetwork.length,
        serverHitCount: networkHits,
        toolError: deniedNetworkToolResult?.is_error ?? null,
      },
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(allowedRun.stderr);
    process.stderr.write(deniedWriteRun.stderr);
    process.stderr.write(deniedNetworkRun.stderr);
    process.exitCode = 1;
  }
}

await main();
