#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const PROMPT_MARKER = "PLUGIN_SKILL_LSP_PROMPT_MARKER";
const SKILL_DESCRIPTION_MARKER = "PLUGIN_SKILL_DESCRIPTION_MARKER";
const SKILL_BODY_MARKER = "PLUGIN_SKILL_BODY_MARKER";
const FINAL_MARKER = "PLUGIN_SKILL_LSP_OK";

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
      if (found) return found;
    }
    return null;
  }
  if (!value || typeof value !== "object") return null;
  if (predicate(value)) return value;
  for (const item of Object.values(value)) {
    const found = findBlock(item, predicate);
    if (found) return found;
  }
  return null;
}

function collectStrings(value, output = []) {
  if (typeof value === "string") output.push(value);
  else if (Array.isArray(value)) {
    for (const item of value) collectStrings(item, output);
  } else if (value && typeof value === "object") {
    for (const item of Object.values(value)) collectStrings(item, output);
  }
  return output;
}

function runCli(binary, args, options, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, options);
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => child.kill("SIGTERM"), timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("close", (exitStatus, signal) => {
      clearTimeout(timer);
      resolve({ exitStatus, signal, stdout, stderr });
    });
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

function findSkillName(body) {
  const listing = collectStrings(body).find((value) => value.includes(SKILL_DESCRIPTION_MARKER)) ?? "";
  const markerIndex = listing.indexOf(SKILL_DESCRIPTION_MARKER);
  const nearby = markerIndex >= 0
    ? listing.slice(Math.max(0, markerIndex - 1000), markerIndex + 1000)
    : listing;
  const xmlName = /<name>([^<]*probe-skill[^<]*)<\/name>/.exec(nearby)?.[1];
  const namespaced = nearby.match(/[A-Za-z0-9_-]+:probe-skill/g) ?? [];
  const bare = nearby.match(/\bprobe-skill\b/g) ?? [];
  return xmlName ?? namespaced[0] ?? bare[0] ?? null;
}

async function main() {
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-plugin-lsp-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const plugin = path.join(temporary, "probe-plugin");
  const skillDir = path.join(plugin, "skills", "probe-skill");
  const manifestDir = path.join(plugin, ".claude-plugin");
  const fixture = path.join(workspace, "fixture.probe");
  const lspServer = path.join(temporary, "probe-lsp.mjs");
  const lspLog = path.join(temporary, "lsp-log.jsonl");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
    mkdir(skillDir, { recursive: true }),
    mkdir(manifestDir, { recursive: true }),
  ]);
  await writeFile(fixture, "probeSymbol();\n");
  await writeFile(path.join(skillDir, "SKILL.md"), `---
name: probe-skill
description: ${SKILL_DESCRIPTION_MARKER}
---

Return this literal marker to the caller: ${SKILL_BODY_MARKER}
`);
  await writeFile(lspServer, `#!/usr/bin/env node
import { appendFile } from "node:fs/promises";
import process from "node:process";

let buffer = Buffer.alloc(0);
const log = async (value) => appendFile(process.env.LSP_PROBE_LOG, JSON.stringify(value) + "\\n");
const send = (message) => {
  const body = Buffer.from(JSON.stringify(message));
  process.stdout.write(\`Content-Length: \${body.length}\\r\\n\\r\\n\`);
  process.stdout.write(body);
};

async function handle(message) {
  await log({ method: message.method ?? null, id: message.id ?? null, params: message.params ?? null });
  if (message.method === "initialize") {
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        capabilities: {
          textDocumentSync: 1,
          definitionProvider: true,
        },
        serverInfo: { name: "claude-plugin-lsp-probe", version: "1.0.0" },
      },
    });
  } else if (message.method === "textDocument/definition") {
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        uri: message.params.textDocument.uri,
        range: {
          start: { line: 0, character: 0 },
          end: { line: 0, character: 11 },
        },
      },
    });
  } else if (message.method === "shutdown") {
    send({ jsonrpc: "2.0", id: message.id, result: null });
  } else if (message.id !== undefined) {
    send({ jsonrpc: "2.0", id: message.id, result: null });
  }
}

process.stdin.on("data", async (chunk) => {
  buffer = Buffer.concat([buffer, chunk]);
  while (true) {
    const headerEnd = buffer.indexOf("\\r\\n\\r\\n");
    if (headerEnd < 0) return;
    const header = buffer.subarray(0, headerEnd).toString("ascii");
    const match = /content-length:\\s*(\\d+)/i.exec(header);
    if (!match) throw new Error("missing Content-Length");
    const length = Number(match[1]);
    const bodyStart = headerEnd + 4;
    if (buffer.length < bodyStart + length) return;
    const body = buffer.subarray(bodyStart, bodyStart + length);
    buffer = buffer.subarray(bodyStart + length);
    await handle(JSON.parse(body.toString("utf8")));
  }
});
`);
  await chmod(lspServer, 0o700);
  await writeFile(path.join(manifestDir, "plugin.json"), JSON.stringify({
    name: "probe-plugin",
    version: "1.0.0",
    description: "Isolated plugin lifecycle probe",
    lspServers: {
      "probe-lsp": {
        command: process.execPath,
        args: [lspServer],
        extensionToLanguage: { ".probe": "probe" },
        env: { LSP_PROBE_LOG: lspLog },
        startupTimeout: 5000,
        shutdownTimeout: 1000,
        restartOnCrash: false,
        diagnostics: false,
      },
    },
  }, null, 2));

  const messageBodies = [];
  let selectedSkillName = null;
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
    selectedSkillName ??= findSkillName(body);
    const skillResult = findBlock(body.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_plugin_skill_probe"
    );
    const lspResult = findBlock(body.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_plugin_lsp_probe"
    );
    if (lspResult) {
      writeSse(response, textResponse(body.model ?? "claude-probe", FINAL_MARKER));
    } else if (skillResult && bodyText.includes(SKILL_BODY_MARKER)) {
      writeSse(response, toolResponse(
        body.model ?? "claude-probe",
        "toolu_plugin_lsp_probe",
        "LSP",
        { operation: "goToDefinition", filePath: fixture, line: 1, character: 1 },
      ));
    } else if (skillResult) {
      writeSse(response, textResponse(body.model ?? "claude-probe", "SKILL_RESULT_MISSING_MARKER"));
    } else if (selectedSkillName) {
      writeSse(response, toolResponse(
        body.model ?? "claude-probe",
        "toolu_plugin_skill_probe",
        "Skill",
        { skill: selectedSkillName },
      ));
    } else {
      writeSse(response, textResponse(body.model ?? "claude-probe", "PLUGIN_SKILL_MISSING"));
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
    ANTHROPIC_AUTH_TOKEN: "plugin-lsp-probe-token",
    ANTHROPIC_API_KEY: "",
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
      "--plugin-dir", plugin,
      "--tools", "Skill,LSP",
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
  let lspEvents = [];
  try {
    lspEvents = (await readFile(lspLog, "utf8"))
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch {
    lspEvents = [];
  }
  const firstTools = messageBodies[0]?.tools?.map((tool) => tool.name) ?? [];
  const result = resultEvent(run.stdout);
  const definition = lspEvents.find((event) => event.method === "textDocument/definition");
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    exitZero: run.exitStatus === 0,
    resultSuccess: result?.result === FINAL_MARKER && result?.subtype === "success",
    pluginSkillListed: JSON.stringify(messageBodies[0] ?? {}).includes(SKILL_DESCRIPTION_MARKER),
    pluginSkillNameResolved: Boolean(selectedSkillName?.includes("probe-skill")),
    skillToolAdvertised: firstTools.includes("Skill"),
    lspSchemaDeferredFromFirstRequest: !firstTools.includes("LSP"),
    pairedSkillResultObserved: containsBlock(messageBodies[1]?.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_plugin_skill_probe"
        && JSON.stringify(value.content).includes("Launching skill: probe-plugin:probe-skill")
    ),
    skillBodyInjected: JSON.stringify(messageBodies[1] ?? {}).includes(SKILL_BODY_MARKER),
    lspInitializeObserved: lspEvents.some((event) => event.method === "initialize"),
    lspDidOpenObserved: lspEvents.some((event) => event.method === "textDocument/didOpen"),
    lspDefinitionObserved: Boolean(definition),
    oneBasedPositionConvertedToZero: definition?.params?.position?.line === 0
      && definition?.params?.position?.character === 0,
    pairedLspResultObserved: containsBlock(messageBodies[2]?.messages, (value) =>
      value.type === "tool_result"
        && value.tool_use_id === "toolu_plugin_lsp_probe"
        && JSON.stringify(value.content).includes("fixture.probe")
    ),
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
      pluginSkillLsp: "$CLAUDE_TARGET --print PLUGIN_SKILL_LSP_PROMPT_MARKER --output-format stream-json --verbose --model claude-sonnet-4-5 --plugin-dir $PLUGIN_DIR --tools Skill,LSP --permission-mode bypassPermissions --dangerously-skip-permissions --session-id $SESSION_ID",
    },
    input: {
      plugin: "isolated --plugin-dir fixture with one Skill and one stdio LSP server",
      skillDescription: SKILL_DESCRIPTION_MARKER,
      skillBody: SKILL_BODY_MARKER,
      sourceFile: "$WORKSPACE/fixture.probe",
      lspOperation: { operation: "goToDefinition", line: 1, character: 1 },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      result: result?.result ?? null,
      subtype: result?.subtype ?? null,
    },
    exitStatus: { version: versionRun.exitStatus, pluginSkillLsp: run.exitStatus },
    observed: {
      messagesRequestCount: messageBodies.length,
      selectedSkillName,
      firstRequestToolNames: firstTools,
      lspMethods: lspEvents.map((event) => event.method).filter(Boolean),
      definitionPosition: definition?.params?.position ?? null,
      pairedSkillResult: checks.pairedSkillResultObserved,
      skillBodyInjected: checks.skillBodyInjected,
      pairedLspResult: checks.pairedLspResultObserved,
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
