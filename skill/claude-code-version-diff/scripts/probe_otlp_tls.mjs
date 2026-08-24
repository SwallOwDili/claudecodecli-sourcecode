#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer as createHttpServer } from "node:http";
import { createServer as createHttpsServer, request as httpsRequest } from "node:https";
import { chmod, mkdir, mkdtemp, readFile, rename, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const RUNS = [
  "noCa",
  "signalOtlpCa",
  "commonOtlpCa",
  "signalOtlpCaProtobuf",
  "signalOtlpCaTls12",
  "nodeExtraCa",
  "signalOtlpCaIp",
  "tlsVerificationDisabled",
  "signalOtlpCaWithWrongCommon",
  "mtlsMissingClient",
  "mtlsOtelClient",
  "mtlsClaudeCertOnly",
  "mtlsClaudeClient",
  "mtlsOtelClientProtobuf",
  "proxyPrecedence",
];

const MARKERS = Object.fromEntries(
  RUNS.map((name) => [name, `OTLP_TLS_${name.replaceAll(/([A-Z])/g, "_$1").toUpperCase()}_MARKER`]),
);

function writeSse(response, model) {
  const id = `msg_${randomUUID()}`;
  const text = "OTLP_TLS_MODEL_OK";
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
    "request-id": id,
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

function normalizeRun(run) {
  const result = resultEvent(run);
  return {
    exitStatus: run.exitStatus,
    signal: run.signal ?? null,
    subtype: result?.subtype ?? null,
    isError: result?.is_error ?? null,
    result: result?.result ?? null,
    stderrClass: /certificate|self.signed|unable to verify|tls|ssl/i.test(run.stderr)
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
  await Promise.all([
    writeFile(
      path.join(directory, "server.ext"),
      "subjectAltName=DNS:localhost,DNS:collector.invalid,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n",
    ),
    writeFile(path.join(directory, "client.ext"), "extendedKeyUsage=clientAuth\n"),
  ]);
  const invocations = [];
  invocations.push(requireSetup("openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
    "-keyout", "ca.key", "-out", "ca.pem", "-subj", "/CN=Claude OTLP Probe CA",
  ], directory));
  invocations.push(requireSetup("openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
    "-keyout", "wrong-ca.key", "-out", "wrong-ca.pem", "-subj", "/CN=Wrong Probe CA",
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
    "-out", "client.csr", "-subj", "/CN=Claude OTLP Probe Client",
  ], directory));
  invocations.push(requireSetup("openssl", [
    "x509", "-req", "-days", "1", "-in", "client.csr", "-CA", "ca.pem",
    "-CAkey", "ca.key", "-CAcreateserial", "-out", "client.pem", "-extfile", "client.ext",
  ], directory));
  return {
    invocations,
    ca: path.join(directory, "ca.pem"),
    wrongCa: path.join(directory, "wrong-ca.pem"),
    serverCert: path.join(directory, "server.pem"),
    serverKey: path.join(directory, "server.key"),
    clientCert: path.join(directory, "client.pem"),
    clientKey: path.join(directory, "client.key"),
  };
}

async function listen(server) {
  const sockets = new Set();
  server.__probeSockets = sockets;
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return server.address().port;
}

async function close(server) {
  await new Promise((resolve) => {
    let resolved = false;
    const finish = () => {
      if (resolved) return;
      resolved = true;
      resolve();
    };
    server.close(finish);
    server.closeAllConnections?.();
    for (const socket of server.__probeSockets ?? []) socket.destroy();
    setTimeout(finish, 250);
  });
}

function createConnectProxy(name, records) {
  const server = createHttpServer((request, response) => {
    records.push({ proxy: name, kind: "http", method: request.method, target: request.url });
    response.writeHead(405, { "content-type": "text/plain" });
    response.end("CONNECT required");
  });
  server.on("connect", (request, clientSocket, head) => {
    const authority = request.url ?? "";
    records.push({ proxy: name, kind: "connect", authority });
    const separator = authority.lastIndexOf(":");
    const rawHost = separator >= 0 ? authority.slice(0, separator) : authority;
    const host = rawHost === "localhost" || rawHost === "collector.invalid"
      ? "127.0.0.1"
      : rawHost;
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

function markerForBody(body) {
  return RUNS.find((name) => body.includes(MARKERS[name])) ?? null;
}

function createCollector(options, requests, tlsErrors) {
  const server = createHttpsServer(options, async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    const peer = request.socket.getPeerCertificate?.() ?? {};
    requests.push({
      run: markerForBody(body),
      method: request.method,
      path: request.url,
      contentType: request.headers["content-type"] ?? null,
      clientAuthorized: request.socket.authorized,
      clientAuthorizationError: request.socket.authorizationError ?? null,
      clientCommonName: peer.subject?.CN ?? null,
    });
    response.writeHead(200, { "content-type": "application/json" });
    response.end("{}");
  });
  server.on("tlsClientError", (error) => {
    tlsErrors.push({
      code: error.code ?? null,
      class: /certificate required|peer did not return a certificate/i.test(error.message)
        ? "client-certificate-required"
        : /self.signed|unable to verify|certificate/i.test(error.message)
          ? "certificate"
          : "tls-other",
    });
  });
  return server;
}

function sanityPost(url, options) {
  return new Promise((resolve, reject) => {
    const request = httpsRequest(url, { method: "POST", ...options }, (response) => {
      response.resume();
      response.once("end", () => resolve(response.statusCode));
    });
    request.once("error", reject);
    request.end('{"sanity":true}');
  });
}

function normalizeObservation(name, observation) {
  const collectorRequests = observation.collectorRequests
    .filter((record) => record.run === name)
    .map(({ run, ...record }) => record);
  const collectorProxyConnects = observation.proxyRecords
    .filter((record) => record.authority?.startsWith("collector.invalid:"))
    .map((record) => ({
      proxy: record.proxy,
      kind: record.kind,
      authority: "collector.invalid:$TLS_PORT",
    }));
  return {
    collectorRequests,
    tlsErrorCodes: [...new Set(observation.tlsErrors.map(({ code }) => code))].sort(),
    tlsErrorClasses: [...new Set(observation.tlsErrors.map(({ class: value }) => value))].sort(),
    collectorProxyConnects,
  };
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
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-otlp-tls-probe-"));
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
  const messageRequests = [];
  const messageServer = createHttpServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end('{"error":{"type":"not_found_error","message":"not found"}}');
      return;
    }
    messageRequests.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
    writeSse(response, "claude-probe");
  });

  const tlsRequests = [];
  const mtlsRequests = [];
  const tls12Requests = [];
  const tlsErrors = [];
  const mtlsErrors = [];
  const tls12Errors = [];
  const commonTlsOptions = {
    key: await readFile(tls.serverKey),
    cert: await readFile(tls.serverCert),
  };
  const tlsCollector = createCollector(commonTlsOptions, tlsRequests, tlsErrors);
  const tls12Collector = createCollector({
    ...commonTlsOptions,
    minVersion: "TLSv1.2",
    maxVersion: "TLSv1.2",
  }, tls12Requests, tls12Errors);
  const mtlsCollector = createCollector({
    ...commonTlsOptions,
    ca: await readFile(tls.ca),
    requestCert: true,
    rejectUnauthorized: true,
  }, mtlsRequests, mtlsErrors);
  const proxyRecords = [];
  const lowercaseProxy = createConnectProxy("lowercase", proxyRecords);
  const uppercaseProxy = createConnectProxy("uppercase", proxyRecords);

  const [messagePort, tlsPort, tls12Port, mtlsPort, lowercaseProxyPort, uppercaseProxyPort] = await Promise.all([
    listen(messageServer),
    listen(tlsCollector),
    listen(tls12Collector),
    listen(mtlsCollector),
    listen(lowercaseProxy),
    listen(uppercaseProxy),
  ]);

  const fixtureSanity = {
    tlsStatus: await sanityPost(`https://localhost:${tlsPort}/v1/logs`, {
      ca: await readFile(tls.ca),
    }),
    tls12Status: await sanityPost(`https://localhost:${tls12Port}/v1/logs`, {
      ca: await readFile(tls.ca),
    }),
    mtlsStatus: await sanityPost(`https://localhost:${mtlsPort}/v1/logs`, {
      ca: await readFile(tls.ca),
      cert: await readFile(tls.clientCert),
      key: await readFile(tls.clientKey),
    }),
  };
  tlsRequests.length = 0;
  tls12Requests.length = 0;
  mtlsRequests.length = 0;
  tlsErrors.length = 0;
  tls12Errors.length = 0;
  mtlsErrors.length = 0;

  const baseEnv = { ...process.env };
  for (const key of [
    "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
    "NO_PROXY", "no_proxy", "NODE_EXTRA_CA_CERTS",
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "OTEL_EXPORTER_OTLP_CERTIFICATE", "OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE",
    "OTEL_EXPORTER_OTLP_CLIENT_KEY", "OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE",
    "OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE", "OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY",
    "CLAUDE_CODE_CLIENT_CERT", "CLAUDE_CODE_CLIENT_KEY", "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE",
  ]) delete baseEnv[key];
  Object.assign(baseEnv, {
    HOME: home,
    USERPROFILE: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${messagePort}`,
    ANTHROPIC_AUTH_TOKEN: "otlp-tls-probe-token",
    ANTHROPIC_API_KEY: "",
    CLAUDE_CODE_ENABLE_TELEMETRY: "1",
    OTEL_METRICS_EXPORTER: "none",
    OTEL_LOGS_EXPORTER: "otlp",
    OTEL_TRACES_EXPORTER: "none",
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: "http/json",
    OTEL_LOG_USER_PROMPTS: "1",
    OTEL_LOGS_EXPORT_INTERVAL: "50",
    CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS: "5000",
    CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS: "5000",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_GROWTHBOOK: "1",
  });
  for (const key of [
    "DISABLE_TELEMETRY", "DO_NOT_TRACK", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
  ]) delete baseEnv[key];

  const commonArgs = [
    "--print", "--output-format", "stream-json", "--verbose",
    "--model", "claude-sonnet-4-5", "--tools", "",
  ];
  const run = (name, endpoint, env) => runCli(binary, [
    ...commonArgs,
    "--session-id", randomUUID(),
    MARKERS[name],
  ], {
    cwd: workspace,
    env: {
      ...baseEnv,
      ...env,
      OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: endpoint,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  const runs = {};
  const observations = {};
  const execute = async (name, endpoint, env, collectorRecords, collectorErrors) => {
    const requestStart = collectorRecords.length;
    const errorStart = collectorErrors.length;
    const proxyStart = proxyRecords.length;
    runs[name] = await run(name, endpoint, env);
    observations[name] = {
      collectorRequests: collectorRecords.slice(requestStart),
      tlsErrors: collectorErrors.slice(errorStart),
      proxyRecords: proxyRecords.slice(proxyStart),
    };
  };

  try {
    await execute("noCa", `https://localhost:${tlsPort}/v1/logs`, {}, tlsRequests, tlsErrors);
    await execute("signalOtlpCa", `https://localhost:${tlsPort}/v1/logs`, {
      OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE: tls.ca,
    }, tlsRequests, tlsErrors);
    await execute("commonOtlpCa", `https://localhost:${tlsPort}/v1/logs`, {
      OTEL_EXPORTER_OTLP_CERTIFICATE: tls.ca,
    }, tlsRequests, tlsErrors);
    await execute("signalOtlpCaProtobuf", `https://localhost:${tlsPort}/v1/logs`, {
      OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE: tls.ca,
      OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: "http/protobuf",
    }, tlsRequests, tlsErrors);
    await execute("signalOtlpCaTls12", `https://localhost:${tls12Port}/v1/logs`, {
      OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE: tls.ca,
    }, tls12Requests, tls12Errors);
    await execute("nodeExtraCa", `https://localhost:${tlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
    }, tlsRequests, tlsErrors);
    await execute("signalOtlpCaIp", `https://127.0.0.1:${tlsPort}/v1/logs`, {
      OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE: tls.ca,
    }, tlsRequests, tlsErrors);
    await execute("tlsVerificationDisabled", `https://localhost:${tlsPort}/v1/logs`, {
      NODE_TLS_REJECT_UNAUTHORIZED: "0",
    }, tlsRequests, tlsErrors);
    await execute("signalOtlpCaWithWrongCommon", `https://localhost:${tlsPort}/v1/logs`, {
      OTEL_EXPORTER_OTLP_CERTIFICATE: tls.wrongCa,
      OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE: tls.ca,
    }, tlsRequests, tlsErrors);
    await execute("mtlsMissingClient", `https://localhost:${mtlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
    }, mtlsRequests, mtlsErrors);
    await execute("mtlsOtelClient", `https://localhost:${mtlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
      OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE: tls.clientCert,
      OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY: tls.clientKey,
    }, mtlsRequests, mtlsErrors);
    await execute("mtlsClaudeCertOnly", `https://localhost:${mtlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
      CLAUDE_CODE_CLIENT_CERT: tls.clientCert,
    }, mtlsRequests, mtlsErrors);
    await execute("mtlsClaudeClient", `https://localhost:${mtlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
      CLAUDE_CODE_CLIENT_CERT: tls.clientCert,
      CLAUDE_CODE_CLIENT_KEY: tls.clientKey,
    }, mtlsRequests, mtlsErrors);
    await execute("mtlsOtelClientProtobuf", `https://localhost:${mtlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
      OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE: tls.clientCert,
      OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY: tls.clientKey,
      OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: "http/protobuf",
    }, mtlsRequests, mtlsErrors);
    await execute("proxyPrecedence", `https://collector.invalid:${tlsPort}/v1/logs`, {
      NODE_EXTRA_CA_CERTS: tls.ca,
      https_proxy: `http://127.0.0.1:${lowercaseProxyPort}`,
      HTTPS_PROXY: `http://127.0.0.1:${uppercaseProxyPort}`,
      NO_PROXY: "127.0.0.1",
      no_proxy: "127.0.0.1",
    }, tlsRequests, tlsErrors);
  } finally {
    await Promise.all([
      close(messageServer), close(tlsCollector), close(tls12Collector), close(mtlsCollector),
      close(lowercaseProxy), close(uppercaseProxy),
    ]);
  }

  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env: baseEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const literalOutput = Object.fromEntries(
    RUNS.map((name) => [name, normalizeRun(runs[name])]),
  );
  const allRunsSucceed = RUNS.every((name) => (
    runs[name].exitStatus === 0 && resultEvent(runs[name])?.result === "OTLP_TLS_MODEL_OK"
  ));
  const requestObserved = (name) => observations[name].collectorRequests.length > 0;
  const mtlsRecord = observations.mtlsClaudeClient.collectorRequests[0];
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    fixtureSanityPasses: Object.values(fixtureSanity).every((status) => status === 200),
    everyRunReachedMessagesApi: RUNS.every((name) => messageRequests
      .some((body) => JSON.stringify(body).includes(MARKERS[name]))),
    allAgentRunsSucceed: allRunsSucceed,
    noCaProducesNoHttpRequest: !requestObserved("noCa"),
    noCaTlsHandshakeErrorObserved: observations.noCa.tlsErrors.length > 0,
    signalCaExportFailsBeforeHttp: !requestObserved("signalOtlpCa"),
    commonOtlpCaExportFailsBeforeHttp: !requestObserved("commonOtlpCa"),
    protobufSignalCaExportFailsBeforeHttp: !requestObserved("signalOtlpCaProtobuf"),
    tls12SignalCaExportFailsBeforeHttp: !requestObserved("signalOtlpCaTls12"),
    nodeExtraCaAllowsExport: requestObserved("nodeExtraCa"),
    ipSanSignalCaExportFailsBeforeHttp: !requestObserved("signalOtlpCaIp"),
    disabledVerificationAllowsExport: requestObserved("tlsVerificationDisabled"),
    signalSpecificCaDoesNotRestoreExport: !requestObserved("signalOtlpCaWithWrongCommon"),
    missingClientCertificateRejectsExport: !requestObserved("mtlsMissingClient"),
    missingClientCertificateTlsErrorObserved: observations.mtlsMissingClient.tlsErrors.length > 0,
    certWithoutKeyRejectsExport: !requestObserved("mtlsClaudeCertOnly"),
    certWithoutKeyTlsErrorObserved: observations.mtlsClaudeCertOnly.tlsErrors.length > 0,
    otelClientPairNotForwarded: !requestObserved("mtlsOtelClient"),
    mtlsExportObserved: requestObserved("mtlsClaudeClient"),
    mtlsClientAuthorized: mtlsRecord?.clientAuthorized === true,
    mtlsClientCommonNameObserved: mtlsRecord?.clientCommonName === "Claude OTLP Probe Client",
    protobufOtelClientPairNotForwarded: !requestObserved("mtlsOtelClientProtobuf"),
    proxyRunExportObserved: requestObserved("proxyPrecedence"),
    collectorEndpointUsesLowercaseProxy: observations.proxyPrecedence.proxyRecords
      .some((record) => record.proxy === "lowercase" && record.authority?.startsWith("collector.invalid:")),
    collectorEndpointNotSentToUppercaseProxy: !observations.proxyPrecedence.proxyRecords
      .some((record) => record.proxy === "uppercase" && record.authority?.startsWith("collector.invalid:")),
    otlpHttpJsonUsesGenericHttpsProxy: observations.proxyPrecedence.proxyRecords
      .some((record) => record.proxy === "lowercase" && record.authority?.startsWith("collector.invalid:"))
      && requestObserved("proxyPrecedence"),
    successfulExportsUseJsonContentType: ["nodeExtraCa", "tlsVerificationDisabled", "mtlsClaudeClient", "proxyPrecedence"]
      .every((name) => requestObserved(name) && observations[name].collectorRequests
        .filter((record) => record.run === name)
        .every((record) => String(record.contentType).startsWith("application/json"))),
    telemetryTransportFailureDoesNotFailAgentTask: [
      "noCa", "signalOtlpCa", "mtlsMissingClient", "mtlsOtelClient", "mtlsClaudeCertOnly",
    ]
      .every((name) => runs[name].exitStatus === 0 && resultEvent(runs[name])?.is_error === false),
  };

  const report = {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    target: {
      version: expectedVersion,
      binarySha256: await sha256(binary),
    },
    environment: {
      platform: process.platform,
      arch: process.arch,
      nodeVersion: process.version,
      opensslVersion: spawnSync("openssl", ["version"], { encoding: "utf8" }).stdout.trim(),
    },
    commands: {
      noCa: `OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json $CLAUDE_TARGET --print ${MARKERS.noCa} --tools ''`,
      signalOtlpCa: `OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE=$CA $CLAUDE_TARGET --print ${MARKERS.signalOtlpCa} --tools ''`,
      commonOtlpCa: `OTEL_EXPORTER_OTLP_CERTIFICATE=$CA $CLAUDE_TARGET --print ${MARKERS.commonOtlpCa} --tools ''`,
      signalOtlpCaProtobuf: `OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE=$CA OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/protobuf $CLAUDE_TARGET --print ${MARKERS.signalOtlpCaProtobuf} --tools ''`,
      signalOtlpCaTls12: `OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE=$CA $CLAUDE_TARGET --print ${MARKERS.signalOtlpCaTls12} --tools ''`,
      nodeExtraCa: `NODE_EXTRA_CA_CERTS=$CA $CLAUDE_TARGET --print ${MARKERS.nodeExtraCa} --tools ''`,
      signalOtlpCaIp: `OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE=$CA $CLAUDE_TARGET --print ${MARKERS.signalOtlpCaIp} --tools ''`,
      tlsVerificationDisabled: `NODE_TLS_REJECT_UNAUTHORIZED=0 $CLAUDE_TARGET --print ${MARKERS.tlsVerificationDisabled} --tools ''`,
      signalOtlpCaWithWrongCommon: `OTEL_EXPORTER_OTLP_CERTIFICATE=$WRONG_CA OTEL_EXPORTER_OTLP_LOGS_CERTIFICATE=$CA $CLAUDE_TARGET --print ${MARKERS.signalOtlpCaWithWrongCommon} --tools ''`,
      mtlsMissingClient: `NODE_EXTRA_CA_CERTS=$CA $CLAUDE_TARGET --print ${MARKERS.mtlsMissingClient} --tools ''`,
      mtlsOtelClient: `NODE_EXTRA_CA_CERTS=$CA OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE=$CERT OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY=$KEY $CLAUDE_TARGET --print ${MARKERS.mtlsOtelClient} --tools ''`,
      mtlsClaudeCertOnly: `NODE_EXTRA_CA_CERTS=$CA CLAUDE_CODE_CLIENT_CERT=$CERT $CLAUDE_TARGET --print ${MARKERS.mtlsClaudeCertOnly} --tools ''`,
      mtlsClaudeClient: `NODE_EXTRA_CA_CERTS=$CA CLAUDE_CODE_CLIENT_CERT=$CERT CLAUDE_CODE_CLIENT_KEY=$KEY $CLAUDE_TARGET --print ${MARKERS.mtlsClaudeClient} --tools ''`,
      mtlsOtelClientProtobuf: `NODE_EXTRA_CA_CERTS=$CA OTEL_EXPORTER_OTLP_LOGS_CLIENT_CERTIFICATE=$CERT OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY=$KEY OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/protobuf $CLAUDE_TARGET --print ${MARKERS.mtlsOtelClientProtobuf} --tools ''`,
      proxyPrecedence: `NODE_EXTRA_CA_CERTS=$CA https_proxy=$LOWERCASE HTTPS_PROXY=$UPPERCASE NO_PROXY=127.0.0.1 $CLAUDE_TARGET --print ${MARKERS.proxyPrecedence} --tools ''`,
    },
    input: {
      messagesBaseUrl: "http://127.0.0.1:$MESSAGES_PORT",
      tlsCollector: "https://localhost:$TLS_PORT/v1/logs",
      mtlsCollector: "https://localhost:$MTLS_PORT/v1/logs",
      tls12Collector: "https://localhost:$TLS12_PORT/v1/logs",
      proxiedCollector: "https://collector.invalid:$TLS_PORT/v1/logs",
      lowercaseProxy: "http://127.0.0.1:$LOWERCASE_PROXY_PORT",
      uppercaseProxy: "http://127.0.0.1:$UPPERCASE_PROXY_PORT",
      markers: MARKERS,
      tls: {
        serverCommonName: "localhost / collector.invalid",
        clientCommonName: "Claude OTLP Probe Client",
        generatedForProbeOnly: true,
      },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      ...literalOutput,
    },
    exitStatus: {
      version: versionRun.exitStatus,
      ...Object.fromEntries(RUNS.map((name) => [name, runs[name].exitStatus])),
    },
    observed: {
      runs: Object.fromEntries(RUNS.map((name) => [name, normalizeObservation(name, observations[name])])),
      fixtureSanity,
      messagesMarkersObserved: Object.fromEntries(RUNS.map((name) => [
        name,
        messageRequests.some((body) => JSON.stringify(body).includes(MARKERS[name])),
      ])),
      tlsFixtureSetupExitStatuses: tls.invocations.map(({ exitStatus }) => exitStatus),
    },
    checks,
    boundaries: [
      "This probe covers the exact 2.1.235 OTLP HTTP logs exporter; positive exports use HTTP/JSON and protobuf arms are negative precedence controls.",
      "It does not prove OTLP gRPC, metrics, traces, collector retention, or remote delivery semantics.",
      "The proxy observation covers a local CONNECT proxy and generic HTTP(S)_PROXY variables, not CCR policy relay or exporter behavior in another runtime.",
      "All certificates are local one-day test fixtures and do not prove enterprise issuance, rotation, revocation, or key protection.",
      "NODE_TLS_REJECT_UNAUTHORIZED=0 is a diagnostic control only and is not a remediation or supported security posture.",
    ],
    pass: Object.values(checks).every(Boolean),
  };
  await writeReport(output, report);
  if (!report.pass) {
    for (const name of RUNS) process.stderr.write(runs[name].stderr);
    process.exitCode = 1;
  }
}

await main();
