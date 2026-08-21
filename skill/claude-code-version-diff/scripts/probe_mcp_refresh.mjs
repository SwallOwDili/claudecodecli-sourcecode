#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const PROMPT_MARKER = "MCP_REFRESH_PROMPT_MARKER";
const TOOL_RESULT_MARKER = "MCP_TOOL_RESULT_MARKER";

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

function toolResponse(model, toolUseId, toolName) {
  return [
    messageStart(model, "msg_mcp_tool"),
    ["content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "tool_use", id: toolUseId, name: toolName, input: {} },
    }],
    ["content_block_delta", {
      type: "content_block_delta",
      index: 0,
      delta: { type: "input_json_delta", partial_json: JSON.stringify({ value: "probe" }) },
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
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-mcp-refresh-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const mcpLog = path.join(temporary, "mcp-log.jsonl");
  const mcpServer = path.join(temporary, "mcp-server.mjs");
  const mcpConfig = path.join(temporary, "mcp.json");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);

  await writeFile(mcpServer, `#!/usr/bin/env node
import { appendFile } from "node:fs/promises";
import process from "node:process";

let buffer = "";
let refreshed = false;
const log = async (event) => appendFile(process.env.MCP_PROBE_LOG, JSON.stringify(event) + "\\n");
const send = (message) => process.stdout.write(JSON.stringify(message) + "\\n");
const tools = () => [
  {
    name: "probe_echo",
    description: "Return a fixed MCP probe marker",
    inputSchema: { type: "object", properties: { value: { type: "string" } } },
  },
  ...(refreshed ? [{
    name: "probe_new",
    description: "Tool added after tools/list_changed",
    inputSchema: { type: "object", properties: {} },
  }] : []),
];

process.stdin.setEncoding("utf8");
process.stdin.on("data", async (chunk) => {
  buffer += chunk;
  while (buffer.includes("\\n")) {
    const index = buffer.indexOf("\\n");
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (!line) continue;
    const message = JSON.parse(line);
    await log({ method: message.method ?? null, id: message.id ?? null, refreshed });
    if (message.method === "initialize") {
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          protocolVersion: message.params?.protocolVersion ?? "2025-06-18",
          capabilities: { tools: { listChanged: true } },
          serverInfo: { name: "claude-version-probe", version: "1.0.0" },
        },
      });
    } else if (message.method === "tools/list") {
      send({ jsonrpc: "2.0", id: message.id, result: { tools: tools() } });
    } else if (message.method === "tools/call") {
      if (!refreshed) {
        refreshed = true;
        send({ jsonrpc: "2.0", method: "notifications/tools/list_changed", params: {} });
      }
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: { content: [{ type: "text", text: "${TOOL_RESULT_MARKER}" }] },
      });
    } else if (message.id !== undefined) {
      send({ jsonrpc: "2.0", id: message.id, result: {} });
    }
  }
});
`);
  await chmod(mcpServer, 0o700);
  await writeFile(mcpConfig, JSON.stringify({
    mcpServers: {
      probe: {
        type: "stdio",
        command: process.execPath,
        args: [mcpServer],
        env: { MCP_PROBE_LOG: mcpLog },
        alwaysLoad: true,
      },
    },
  }, null, 2));

  const messageBodies = [];
  let selectedToolName = null;
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
    if (!bodyText.includes(PROMPT_MARKER)) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "AUXILIARY_OK"));
      return;
    }
    messageBodies.push(body);
    const toolNames = body.tools?.map((tool) => tool.name) ?? [];
    selectedToolName ??= toolNames.find((name) => name.includes("probe_echo")) ?? null;
    const hasFirstToolResult = containsBlock(body.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_mcp_refresh_probe"
        && JSON.stringify(value.content).includes(TOOL_RESULT_MARKER)
    );
    const hasSecondToolResult = containsBlock(body.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_mcp_refresh_probe_2"
        && JSON.stringify(value.content).includes(TOOL_RESULT_MARKER)
    );
    if (hasSecondToolResult) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "MCP_REFRESH_OK"));
    } else if (hasFirstToolResult) {
      writeSse(response, toolResponse(body.model ?? "claude-probe", "toolu_mcp_refresh_probe_2", selectedToolName));
    } else if (selectedToolName) {
      writeSse(response, toolResponse(body.model ?? "claude-probe", "toolu_mcp_refresh_probe", selectedToolName));
    } else {
      writeSse(response, textResponse(body.model ?? "claude-probe", "MCP_TOOL_MISSING"));
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
    ANTHROPIC_AUTH_TOKEN: "mcp-refresh-probe-token",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };
  let run;
  try {
    run = await runCli(binary, [
      "--print", PROMPT_MARKER,
      "--output-format", "stream-json",
      "--verbose",
      "--model", "claude-sonnet-4-5",
      "--mcp-config", mcpConfig,
      "--strict-mcp-config",
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
  const mcpEvents = (await readFile(mcpLog, "utf8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  const firstTools = messageBodies[0]?.tools?.map((tool) => tool.name) ?? [];
  const secondTools = messageBodies[1]?.tools?.map((tool) => tool.name) ?? [];
  const thirdTools = messageBodies[2]?.tools?.map((tool) => tool.name) ?? [];
  const result = resultEvent(run.stdout);
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    exitZero: run.exitStatus === 0,
    resultSuccess: result?.result === "MCP_REFRESH_OK" && result?.subtype === "success",
    initializeObserved: mcpEvents.some((event) => event.method === "initialize"),
    initialToolsListObserved: mcpEvents.some((event) => event.method === "tools/list" && event.refreshed === false),
    firstRequestAdvertisesMcpTool: firstTools.some((name) => name.includes("probe_echo")),
    toolCallObserved: mcpEvents.some((event) => event.method === "tools/call"),
    firstPairedToolResultObserved: containsBlock(messageBodies[1]?.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_mcp_refresh_probe"
        && JSON.stringify(value.content).includes(TOOL_RESULT_MARKER)
    ),
    secondPairedToolResultObserved: containsBlock(messageBodies[2]?.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_mcp_refresh_probe_2"
        && JSON.stringify(value.content).includes(TOOL_RESULT_MARKER)
    ),
    refreshedToolsListObserved: mcpEvents.some((event) => event.method === "tools/list" && event.refreshed === true),
    laterRequestAdvertisesNewTool: [...secondTools, ...thirdTools].some((name) => name.includes("probe_new")),
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
      mcpRefresh: "$CLAUDE_TARGET --print MCP_REFRESH_PROMPT_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --mcp-config $MCP_CONFIG --strict-mcp-config --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID",
    },
    input: {
      server: "isolated stdio MCP server with tools/list_changed capability",
      initialTool: "probe_echo",
      addedTool: "probe_new",
      toolResult: TOOL_RESULT_MARKER,
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      result: result?.result ?? null,
      subtype: result?.subtype ?? null,
    },
    exitStatus: { version: versionRun.exitStatus, mcpRefresh: run.exitStatus },
    observed: {
      messagesRequestCount: messageBodies.length,
      toolsListCalls: mcpEvents.filter((event) => event.method === "tools/list").length,
      toolCallCount: mcpEvents.filter((event) => event.method === "tools/call").length,
      firstRequestToolNames: firstTools.map((name) => name.replace(/^mcp__[^_]+__/, "mcp__$SERVER__")),
      secondRequestToolNames: secondTools.map((name) => name.replace(/^mcp__[^_]+__/, "mcp__$SERVER__")),
      thirdRequestToolNames: thirdTools.map((name) => name.replace(/^mcp__[^_]+__/, "mcp__$SERVER__")),
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
