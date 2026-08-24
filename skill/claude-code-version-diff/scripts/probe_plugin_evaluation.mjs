#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { chmod, mkdir, mkdtemp, readFile, rename, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const PROMPT_MARKER = "PLUGIN_EVAL_PROMPT_MARKER";
const RESULT_MARKER = "PLUGIN_EVAL_RESULT_OK";
const HOOK_MARKER = "PLUGIN_EVAL_WITH_ARM_HOOK_MARKER";

function writeSse(response, model, text) {
  const events = [
    ["message_start", {
      type: "message_start",
      message: {
        id: `msg_${Date.now()}`,
        type: "message",
        role: "assistant",
        model,
        content: [],
        stop_reason: null,
        stop_sequence: null,
        usage: { input_tokens: 10, output_tokens: 0 },
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
    "request-id": `msg_${Date.now()}`,
  });
  for (const [event, data] of events) {
    response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  }
  response.end();
}

function runCli(binary, args, options, timeoutMs = 90000) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, options);
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 1000).unref();
    }, timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", (exitStatus, signal) => {
      clearTimeout(timer);
      resolve({ exitStatus, signal, stdout, stderr });
    });
  });
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return server.address().port;
}

async function close(server) {
  await new Promise((resolve) => server.close(resolve));
}

function collectKeys(value, key, output = []) {
  if (Array.isArray(value)) {
    for (const item of value) collectKeys(item, key, output);
  } else if (value && typeof value === "object") {
    for (const [name, item] of Object.entries(value)) {
      if (name === key) output.push(item);
      collectKeys(item, key, output);
    }
  }
  return output;
}

async function writeReport(output, report) {
  const text = `${JSON.stringify(report, null, 2)}\n`;
  if (!output) {
    process.stdout.write(text);
    return;
  }
  const temporary = `${output}.tmp-${process.pid}`;
  await writeFile(temporary, text, { mode: 0o644 });
  await rename(temporary, output);
  await chmod(output, 0o644);
}

async function main() {
  const outputIndex = process.argv.indexOf("--output");
  const output = outputIndex >= 0 ? path.resolve(process.argv[outputIndex + 1]) : null;
  if (outputIndex >= 0 && !process.argv[outputIndex + 1]) {
    throw new Error("--output requires a path");
  }
  const { binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-plugin-eval-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const plugin = path.join(temporary, "plugin");
  const manifestDir = path.join(plugin, ".claude-plugin");
  const skillDir = path.join(plugin, "skills", "probe-skill");
  const hooksDir = path.join(plugin, "hooks");
  const caseDir = path.join(plugin, "evals", "exact-binary-smoke");
  const outputDir = path.join(temporary, "results");
  const resultJson = path.join(temporary, "eval-result.json");
  const htmlReport = path.join(temporary, "eval-report.html");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
    mkdir(manifestDir, { recursive: true }),
    mkdir(skillDir, { recursive: true }),
    mkdir(hooksDir, { recursive: true }),
    mkdir(caseDir, { recursive: true }),
    mkdir(outputDir, { recursive: true }),
  ]);
  await Promise.all([
    writeFile(path.join(manifestDir, "plugin.json"), JSON.stringify({
      name: "eval-probe-plugin",
      version: "1.0.0",
      description: "Exact-binary Plugin Evaluation probe",
      experimental: { evals: "evals" },
    }, null, 2)),
    writeFile(path.join(skillDir, "SKILL.md"), `---
name: eval-probe-skill
description: Exact-binary eval probe skill that is intentionally not required by the prompt.
---

Return ${RESULT_MARKER} when explicitly invoked.
`),
    writeFile(path.join(hooksDir, "session-start.mjs"), `#!/usr/bin/env node
import process from "node:process";
for await (const _chunk of process.stdin) {}
process.stdout.write(JSON.stringify({
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: "${HOOK_MARKER}",
  },
}));
`),
    writeFile(path.join(hooksDir, "hooks.json"), JSON.stringify({
      hooks: {
        SessionStart: [{
          matcher: "",
          hooks: [{
            type: "command",
            command: "node \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.mjs\"",
          }],
        }],
      },
    }, null, 2)),
    writeFile(path.join(caseDir, "case.yaml"), `schema_version: "1.0"
name: exact-binary-smoke
description: Free deterministic with/without smoke test
tags: [probe]
plugins: ["../.."]
context:
  add_dirs: []
execution:
  prompt: "Return exactly ${RESULT_MARKER}. Input marker: ${PROMPT_MARKER}"
  max_turns: 1
  timeout_seconds: 30
  allowed_tools: []
  env: {}
runs: 1
graders:
  - type: regex
    name: exact-result
    target: last_message
    pattern: "${RESULT_MARKER}"
    match: contains
    weight: 1
expected_outcome: Both arms pass with Delta zero.
`),
  ]);
  await chmod(path.join(hooksDir, "session-start.mjs"), 0o700);

  const requests = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const bodyText = Buffer.concat(chunks).toString("utf8");
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }
    const body = JSON.parse(bodyText);
    requests.push({
      markerPresent: bodyText.includes(PROMPT_MARKER),
      pluginHookMarkerPresent: bodyText.includes(HOOK_MARKER),
      model: body.model ?? null,
      toolNames: Array.isArray(body.tools) ? body.tools.map((tool) => tool.name) : [],
    });
    writeSse(response, body.model ?? "claude-probe", RESULT_MARKER);
  });
  const port = await listen(server);

  const env = { ...process.env };
  for (const name of ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"]) {
    delete env[name];
  }
  Object.assign(env, {
    HOME: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${port}`,
    ANTHROPIC_AUTH_TOKEN: "plugin-eval-probe-token",
    ANTHROPIC_API_KEY: "",
    CLAUDE_CODE_WALNUT_SPIRE: "1",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  });
  const args = [
    "plugin", "eval", plugin,
    "--eval-dir", "evals",
    "--runs", "1",
    "--ablation", "with-without",
    "--threshold", "1",
    "--model", "claude-sonnet-4-5",
    "--json", resultJson,
    "--report", htmlReport,
    "--output-dir", outputDir,
    "--no-publish",
    "--no-scaffold",
  ];
  let run;
  try {
    run = await runCli(binary, args, {
      cwd: workspace,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } finally {
    await close(server);
  }

  let rawResult = null;
  try { rawResult = JSON.parse(await readFile(resultJson, "utf8")); } catch {}
  let html = "";
  try { html = await readFile(htmlReport, "utf8"); } catch {}
  const resultCase = rawResult?.cases?.find((item) => item.name === "exact-binary-smoke") ?? null;
  const arms = Object.keys(resultCase?.arms ?? {}).sort();
  const withScores = (resultCase?.arms?.with ?? []).map((run) => run.score);
  const withoutScores = (resultCase?.arms?.without ?? []).map((run) => run.score);
  const delta = resultCase?.aggregates?.delta ?? null;
  const markerRequests = requests.filter((request) => request.markerPresent);
  const pluginProblems = collectKeys(rawResult, "problem").filter(Boolean);
  const checks = {
    exactVersion: expectedVersion === "2.1.235",
    exactBinarySha256: await sha256(binary) === expectedSha256,
    commandExitZero: run.exitStatus === 0,
    jsonResultWritten: rawResult !== null,
    htmlReportWritten: html.length > 1000,
    htmlContainsCaseName: html.includes("exact-binary-smoke"),
    htmlContainsResultMarker: html.includes(RESULT_MARKER),
    bothArmsPresent: arms.includes("with") && arms.includes("without"),
    scoresAllPerfect: withScores.length === 1 && withoutScores.length === 1
      && withScores[0] === 1 && withoutScores[0] === 1,
    deltaZero: delta === 0,
    resultNotPartial: rawResult?.partial === false,
    noPluginLoadProblem: pluginProblems.length === 0,
    twoAgentRequestsObserved: markerRequests.length === 2,
    withRequestHasPluginHookContext: markerRequests[0]?.pluginHookMarkerPresent === true,
    withoutRequestOmitsPluginHookContext: markerRequests[1]?.pluginHookMarkerPresent === false,
    modelPinned: markerRequests
      .every((request) => request.model === "claude-sonnet-4-5"),
    schemaVersionOne: rawResult?.schemaVersion === 1,
  };
  const report = {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    target: { version: expectedVersion, binarySha256: await sha256(binary) },
    environment: {
      platform: process.platform,
      arch: process.arch,
      nodeVersion: process.version,
    },
    command: "$CLAUDE_TARGET plugin eval $PLUGIN --eval-dir evals --runs 1 --ablation with-without --threshold 1 --model claude-sonnet-4-5 --json $RESULT --report $HTML --output-dir $OUTPUT --no-publish --no-scaffold",
    input: {
      pluginManifest: { name: "eval-probe-plugin", version: "1.0.0" },
      case: {
        schemaVersion: "1.0",
        name: "exact-binary-smoke",
        runs: 1,
        maxTurns: 1,
        timeoutSeconds: 30,
        grader: { type: "regex", target: "last_message", pattern: RESULT_MARKER, weight: 1 },
      },
      promptMarker: PROMPT_MARKER,
      resultMarker: RESULT_MARKER,
      hookMarker: HOOK_MARKER,
    },
    literalOutput: {
      exitStatus: run.exitStatus,
      signal: run.signal ?? null,
      stdout: run.stdout.includes(`Wrote ${resultJson}`) ? "Wrote $RESULT_JSON" : run.stdout.trim() || "<empty>",
      stderr: run.stderr.includes(`Report: ${htmlReport}`) ? "Report: $HTML_REPORT" : run.stderr.trim() || "<empty>",
    },
    exitStatus: run.exitStatus,
    observed: {
      requestCount: requests.filter((request) => request.markerPresent).length,
      arms,
      withScores,
      withoutScores,
      caseScore: resultCase?.aggregates?.score ?? null,
      scoreWithout: resultCase?.aggregates?.scoreWithout ?? null,
      delta,
      partial: rawResult?.partial ?? null,
      schemaVersion: rawResult?.schemaVersion ?? null,
      withRequestHasPluginHookContext: markerRequests[0]?.pluginHookMarkerPresent ?? null,
      withoutRequestHasPluginHookContext: markerRequests[1]?.pluginHookMarkerPresent ?? null,
      pluginProblemCount: pluginProblems.length,
      jsonNonempty: rawResult !== null,
      htmlNonempty: html.length > 1000,
      resultFileMode: rawResult === null ? null : (await stat(resultJson)).mode & 0o777,
      reportFileMode: html ? (await stat(htmlReport)).mode & 0o777 : null,
    },
    checks,
    boundaries: [
      "The Messages service is a local deterministic stub; this probe does not measure model or plugin quality.",
      "Only a free regex grader is exercised; LLM and baseline judges, voting noise, and paid cost ceilings are not probed.",
      "The probe proves with/without orchestration and local JSON/HTML output, not claude.ai report publication or retention.",
      "The eval temp sandbox is process-state isolation, not OS or network isolation.",
    ],
    pass: Object.values(checks).every(Boolean),
  };
  await writeReport(output, report);
  if (!report.pass) {
    process.stderr.write(`${JSON.stringify({ checks, observed: report.observed, rawResult }, null, 2)}\n`);
    process.exitCode = 1;
  }
}

await main();
