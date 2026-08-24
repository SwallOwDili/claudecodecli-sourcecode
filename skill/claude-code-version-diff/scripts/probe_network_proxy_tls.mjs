#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer as createHttpServer } from "node:http";
import { createServer as createHttpsServer } from "node:https";
import { chmod, mkdir, mkdtemp, readFile, rename, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const MARKERS = {
  caFailure: "NETWORK_CA_FAILURE_MARKER",
  caSuccess: "NETWORK_CA_SUCCESS_MARKER",
  proxyPrecedence: "NETWORK_PROXY_PRECEDENCE_MARKER",
  noProxy: "NETWORK_NO_PROXY_MARKER",
  invalidProxy: "NETWORK_INVALID_PROXY_MARKER",
  mtls: "NETWORK_MTLS_MARKER",
};

function writeSse(response, model, text) {
  const events = [
    ["message_start", {
      type: "message_start",
      message: {
        id: `msg_${text.toLowerCase()}`,
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

function runCli(binary, args, options, timeoutMs = 45000) {
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

function parseResult(stdout) {
  try {
    return stdout
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line))
      .findLast((event) => event.type === "result");
  } catch {
    return undefined;
  }
}

function normalizeRun(run) {
  const result = parseResult(run.stdout);
  return {
    exitStatus: run.exitStatus,
    signal: run.signal ?? null,
    subtype: result?.subtype ?? null,
    isError: result?.is_error ?? null,
    result: result?.result ?? null,
    stderrClass: /proxy/i.test(run.stderr)
      ? "proxy"
      : /certificate|self.signed|unable to verify|tls/i.test(run.stderr)
        ? "tls"
        : run.stderr.trim() ? "other" : "empty",
  };
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

function requireSetup(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(
      `TLS fixture setup failed: ${command} ${args.join(" ")}\n${result.stdout}${result.stderr}`,
    );
  }
  return { command: `${command} ${args.join(" ")}`, exitStatus: result.status };
}

async function buildTlsFixture(directory) {
  const serverExt = path.join(directory, "server.ext");
  const clientExt = path.join(directory, "client.ext");
  await Promise.all([
    writeFile(serverExt, "subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n"),
    writeFile(clientExt, "extendedKeyUsage=clientAuth\n"),
  ]);
  const invocations = [];
  invocations.push(requireSetup("openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
    "-keyout", "ca.key", "-out", "ca.pem", "-subj", "/CN=Claude Probe CA",
  ], directory));
  invocations.push(requireSetup("openssl", [
    "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "server.key",
    "-out", "server.csr", "-subj", "/CN=localhost",
  ], directory));
  invocations.push(requireSetup("openssl", [
    "x509", "-req", "-days", "1", "-in", "server.csr", "-CA", "ca.pem",
    "-CAkey", "ca.key", "-CAcreateserial", "-out", "server.pem", "-extfile", "server.ext",
  ], directory));
  invocations.push(requireSetup("openssl", [
    "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "client.key",
    "-out", "client.csr", "-subj", "/CN=Claude Probe Client",
  ], directory));
  invocations.push(requireSetup("openssl", [
    "x509", "-req", "-days", "1", "-in", "client.csr", "-CA", "ca.pem",
    "-CAkey", "ca.key", "-CAcreateserial", "-out", "client.pem", "-extfile", "client.ext",
  ], directory));
  return {
    invocations,
    ca: path.join(directory, "ca.pem"),
    serverCert: path.join(directory, "server.pem"),
    serverKey: path.join(directory, "server.key"),
    clientCert: path.join(directory, "client.pem"),
    clientKey: path.join(directory, "client.key"),
  };
}

async function listen(server, host = "127.0.0.1") {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, host, resolve);
  });
  return server.address().port;
}

async function close(server) {
  await new Promise((resolve) => server.close(resolve));
}

function createConnectProxy(name, records) {
  const server = createHttpServer((request, response) => {
    records.push({ proxy: name, kind: "http", method: request.method, target: request.url });
    response.writeHead(405, { "content-type": "text/plain" });
    response.end("CONNECT required");
  });
  server.on("connect", (request, clientSocket, head) => {
    const authority = request.url ?? "";
    records.push({
      proxy: name,
      kind: "connect",
      authority,
      proxyAuthorizationPresent: request.headers["proxy-authorization"] !== undefined,
    });
    const separator = authority.lastIndexOf(":");
    const rawHost = separator >= 0 ? authority.slice(0, separator) : authority;
    const host = rawHost === "localhost" ? "127.0.0.1" : rawHost;
    const port = Number(separator >= 0 ? authority.slice(separator + 1) : 443);
    const upstream = net.connect(port, host);
    upstream.once("connect", () => {
      clientSocket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
      if (head.length) upstream.write(head);
      upstream.pipe(clientSocket);
      clientSocket.pipe(upstream);
    });
    upstream.once("error", () => clientSocket.destroy());
    clientSocket.once("error", () => upstream.destroy());
  });
  return server;
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
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-network-proxy-tls-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  const tlsDirectory = path.join(temporary, "tls");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
    mkdir(tlsDirectory, { recursive: true }),
  ]);

  const tls = await buildTlsFixture(tlsDirectory);
  const apiRecords = [];
  const proxyRecords = [];
  const apiServer = createHttpsServer({
    key: await readFile(tls.serverKey),
    cert: await readFile(tls.serverCert),
    ca: await readFile(tls.ca),
    requestCert: true,
    rejectUnauthorized: false,
  }, async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const bodyText = Buffer.concat(chunks).toString("utf8");
    let body;
    try { body = JSON.parse(bodyText); } catch { body = {}; }
    const marker = Object.values(MARKERS).find((value) => bodyText.includes(value)) ?? null;
    const peer = request.socket.getPeerCertificate?.() ?? {};
    apiRecords.push({
      marker,
      method: request.method,
      path: request.url,
      clientAuthorized: request.socket.authorized === true,
      clientAuthorizationError: request.socket.authorizationError ?? null,
      clientCommonName: peer.subject?.CN ?? null,
    });
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }
    if (marker === MARKERS.mtls && (
      request.socket.authorized !== true || peer.subject?.CN !== "Claude Probe Client"
    )) {
      response.writeHead(401, { "content-type": "application/json" });
      response.end('{"error":{"type":"authentication_error","message":"client certificate required"}}');
      return;
    }
    writeSse(response, body.model ?? "claude-probe", marker === MARKERS.mtls ? "MTLS_OK" : "NETWORK_OK");
  });
  const proxyA = createConnectProxy("lowercase", proxyRecords);
  const proxyB = createConnectProxy("uppercase", proxyRecords);
  const apiPort = await listen(apiServer);
  const proxyAPort = await listen(proxyA);
  const proxyBPort = await listen(proxyB);

  const baseEnv = { ...process.env };
  for (const name of [
    "all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
    "no_proxy", "NO_PROXY", "NODE_EXTRA_CA_CERTS", "CLAUDE_CODE_CLIENT_CERT",
    "CLAUDE_CODE_CLIENT_KEY", "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE",
    "NODE_TLS_REJECT_UNAUTHORIZED",
  ]) delete baseEnv[name];
  Object.assign(baseEnv, {
    HOME: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `https://localhost:${apiPort}`,
    ANTHROPIC_AUTH_TOKEN: "network-probe-token",
    ANTHROPIC_API_KEY: "",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
    CLAUDE_CODE_MAX_RETRIES: "0",
  });
  const commonArgs = [
    "--print", "--output-format", "stream-json", "--verbose",
    "--model", "claude-sonnet-4-5", "--tools", "",
  ];
  const run = (marker, env) => runCli(binary, [
    ...commonArgs, "--session-id", randomUUID(), marker,
  ], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });

  const runs = {};
  let proxyABefore;
  let proxyBBefore;
  let invalidApiBefore;
  try {
    runs.caFailure = await run(MARKERS.caFailure, { ...baseEnv, no_proxy: "localhost" });
    runs.caSuccess = await run(MARKERS.caSuccess, {
      ...baseEnv,
      no_proxy: "localhost",
      NODE_EXTRA_CA_CERTS: tls.ca,
    });

    proxyABefore = proxyRecords.filter((record) => record.proxy === "lowercase").length;
    proxyBBefore = proxyRecords.filter((record) => record.proxy === "uppercase").length;
    runs.proxyPrecedence = await run(MARKERS.proxyPrecedence, {
      ...baseEnv,
      https_proxy: `http://127.0.0.1:${proxyAPort}`,
      HTTPS_PROXY: `http://127.0.0.1:${proxyBPort}`,
      no_proxy: "",
      NO_PROXY: "",
      NODE_EXTRA_CA_CERTS: tls.ca,
    });
    const proxyAAfterPrecedence = proxyRecords.filter((record) => record.proxy === "lowercase").length;
    const proxyBAfterPrecedence = proxyRecords.filter((record) => record.proxy === "uppercase").length;

    runs.noProxy = await run(MARKERS.noProxy, {
      ...baseEnv,
      https_proxy: `http://127.0.0.1:${proxyAPort}`,
      HTTPS_PROXY: `http://127.0.0.1:${proxyBPort}`,
      no_proxy: "localhost",
      NO_PROXY: "",
      NODE_EXTRA_CA_CERTS: tls.ca,
    });
    const proxyAAfterNoProxy = proxyRecords.filter((record) => record.proxy === "lowercase").length;
    const proxyBAfterNoProxy = proxyRecords.filter((record) => record.proxy === "uppercase").length;

    invalidApiBefore = apiRecords.length;
    runs.invalidProxy = await run(MARKERS.invalidProxy, {
      ...baseEnv,
      https_proxy: "proxy.invalid:8080",
      no_proxy: "",
      NO_PROXY: "",
      NODE_EXTRA_CA_CERTS: tls.ca,
    });
    const invalidApiAfter = apiRecords.length;

    runs.mtls = await run(MARKERS.mtls, {
      ...baseEnv,
      no_proxy: "localhost",
      NODE_EXTRA_CA_CERTS: tls.ca,
      CLAUDE_CODE_CLIENT_CERT: tls.clientCert,
      CLAUDE_CODE_CLIENT_KEY: tls.clientKey,
    });

    const recordsByMarker = Object.fromEntries(
      Object.entries(MARKERS).map(([name, marker]) => [name, apiRecords.filter((record) => record.marker === marker)]),
    );
    const resultText = Object.fromEntries(
      Object.entries(runs).map(([name, runResult]) => [name, parseResult(runResult.stdout)?.result ?? null]),
    );
    const checks = {
      exactVersion: expectedVersion === "2.1.235",
      exactBinarySha256: await sha256(binary) === expectedSha256,
      caFailureRejectedBeforeHttp: runs.caFailure.exitStatus !== 0 && recordsByMarker.caFailure.length === 0,
      caFailureClassifiedAsTls: /certificate|self.signed|unable to verify|tls/i.test(
        `${runs.caFailure.stderr}\n${parseResult(runs.caFailure.stdout)?.result ?? ""}`,
      ),
      extraCaAllowsMessagesRequest: runs.caSuccess.exitStatus === 0
        && resultText.caSuccess === "NETWORK_OK"
        && recordsByMarker.caSuccess.length === 1,
      lowercaseProxyWinsPrecedence: proxyAAfterPrecedence > proxyABefore,
      uppercaseProxyNotUsed: proxyBAfterPrecedence === proxyBBefore,
      proxiedMessagesRequestSucceeds: runs.proxyPrecedence.exitStatus === 0
        && resultText.proxyPrecedence === "NETWORK_OK"
        && recordsByMarker.proxyPrecedence.length === 1,
      noProxyBypassesBothProxies: proxyAAfterNoProxy === proxyAAfterPrecedence
        && proxyBAfterNoProxy === proxyBAfterPrecedence,
      noProxyDirectRequestSucceeds: runs.noProxy.exitStatus === 0
        && resultText.noProxy === "NETWORK_OK"
        && recordsByMarker.noProxy.length === 1,
      invalidProxyFailsClosed: runs.invalidProxy.exitStatus !== 0 && invalidApiAfter === invalidApiBefore,
      invalidProxyDiagnostic: /proxy/i.test(runs.invalidProxy.stderr)
        && /valid|invalid|scheme|url/i.test(runs.invalidProxy.stderr),
      mtlsRequestSucceeds: runs.mtls.exitStatus === 0 && resultText.mtls === "MTLS_OK",
      mtlsClientCertificateObserved: recordsByMarker.mtls.length === 1
        && recordsByMarker.mtls[0].clientAuthorized === true
        && recordsByMarker.mtls[0].clientCommonName === "Claude Probe Client",
    };

    const report = {
      schemaVersion: 1,
      capturedAt: new Date().toISOString(),
      target: { version: expectedVersion, binarySha256: await sha256(binary) },
      environment: {
        platform: process.platform,
        arch: process.arch,
        nodeVersion: process.version,
        opensslVersion: spawnSync("openssl", ["version"], { encoding: "utf8" }).stdout.trim(),
      },
      commands: {
        caFailure: "NO_PROXY=localhost $CLAUDE_TARGET --print NETWORK_CA_FAILURE_MARKER ...",
        caSuccess: "NODE_EXTRA_CA_CERTS=$CA NO_PROXY=localhost $CLAUDE_TARGET --print NETWORK_CA_SUCCESS_MARKER ...",
        proxyPrecedence: "https_proxy=$PROXY_A HTTPS_PROXY=$PROXY_B NO_PROXY= $CLAUDE_TARGET --print NETWORK_PROXY_PRECEDENCE_MARKER ...",
        noProxy: "https_proxy=$PROXY_A HTTPS_PROXY=$PROXY_B no_proxy=localhost $CLAUDE_TARGET --print NETWORK_NO_PROXY_MARKER ...",
        invalidProxy: "https_proxy=proxy.invalid:8080 $CLAUDE_TARGET --print NETWORK_INVALID_PROXY_MARKER ...",
        mtls: "NODE_EXTRA_CA_CERTS=$CA CLAUDE_CODE_CLIENT_CERT=$CERT CLAUDE_CODE_CLIENT_KEY=$KEY NO_PROXY=localhost $CLAUDE_TARGET --print NETWORK_MTLS_MARKER ...",
      },
      input: {
        baseUrl: "https://localhost:$PORT",
        proxyA: "http://127.0.0.1:$PROXY_A_PORT",
        proxyB: "http://127.0.0.1:$PROXY_B_PORT",
        markers: MARKERS,
        tls: {
          serverCommonName: "localhost",
          clientCommonName: "Claude Probe Client",
          generatedForProbeOnly: true,
        },
      },
      literalOutput: Object.fromEntries(
        Object.entries(runs).map(([name, runResult]) => [name, normalizeRun(runResult)]),
      ),
      exitStatus: Object.fromEntries(
        Object.entries(runs).map(([name, runResult]) => [name, runResult.exitStatus]),
      ),
      observed: {
        apiRequestsByMarker: Object.fromEntries(
          Object.entries(recordsByMarker).map(([name, records]) => [name, records]),
        ),
        proxyConnects: proxyRecords.map((record) => ({
          ...record,
          authority: record.authority.replace(/:\d+$/, ":$PORT"),
        })),
        tlsFixtureSetupExitStatuses: tls.invocations.map((invocation) => invocation.exitStatus),
      },
      checks,
      boundaries: [
        "This probe exercises the exact 2.1.235 main Messages HTTPS transport only.",
        "It does not prove Axios, undici-global, WebSocket, AWS SDK, MCP, OTEL, subprocess, or CCR relay behavior.",
        "The CA, server certificate, and client certificate are local one-day test fixtures; no external service or account behavior is exercised.",
        "A successful client-certificate observation proves the local TLS handshake, not enterprise certificate issuance, rotation, or revocation.",
      ],
      pass: Object.values(checks).every(Boolean),
    };
    await writeReport(output, report);
    if (!report.pass) {
      process.stderr.write(`${JSON.stringify({ checks, literalOutput: report.literalOutput }, null, 2)}\n`);
      process.exitCode = 1;
    }
  } finally {
    await Promise.all([close(apiServer), close(proxyA), close(proxyB)]);
  }
}

await main();
