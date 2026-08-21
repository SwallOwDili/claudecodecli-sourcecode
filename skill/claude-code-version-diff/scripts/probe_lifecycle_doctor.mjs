#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";

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

async function sha256(file) {
  const hash = createHash("sha256");
  hash.update(await readFile(file));
  return hash.digest("hex");
}

function matchingLines(output, patterns) {
  return output
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => patterns.some((pattern) => pattern.test(line)));
}

async function main() {
  const binary = process.env.CLAUDE_BIN
    ?? path.join(os.homedir(), ".local/share/claude/versions/2.1.235");
  const expectedVersion = process.env.CLAUDE_VERSION ?? "2.1.235";
  const expectedSha256 = process.env.CLAUDE_SHA256
    ?? "83b8f806f6f2eea316cfe246628e6c23374711d868f1fd0409db551b877b7748";
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-lifecycle-doctor-probe-"));
  const home = path.join(temporary, "home");
  const configDir = path.join(temporary, "config");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([
    mkdir(home, { recursive: true }),
    mkdir(configDir, { recursive: true }),
    mkdir(workspace, { recursive: true }),
  ]);
  await writeFile(path.join(configDir, "settings.json"), "{invalid", "utf8");

  const baseEnv = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    CLAUDE_CONFIG_DIR: configDir,
    ANTHROPIC_BASE_URL: "http://127.0.0.1:9",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    DISABLE_AUTOUPDATER: "1",
    DISABLE_ERROR_REPORTING: "1",
    DISABLE_TELEMETRY: "1",
  };
  const versionRun = await runCli(binary, ["--version"], {
    cwd: workspace,
    env: baseEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const updateRun = await runCli(binary, ["update"], {
    cwd: workspace,
    env: { ...baseEnv, DISABLE_UPDATES: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const doctorRun = await runCli(binary, ["doctor"], {
    cwd: workspace,
    env: baseEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });

  const doctorLines = matchingLines(doctorRun.stdout, [
    /^Claude Code doctor$/,
    /^Running: native \(2\.1\.235\)$/,
    /^Commit: ba01fa45e3d1$/,
    /^Platform: darwin-arm64$/,
    /^Search: OK \(bundled\)$/,
    /^Auto-updates: disabled \(set by env: DISABLE_AUTOUPDATER\)$/,
    /^Auto-update channel: latest$/,
    /^Last update attempt: none recorded$/,
    /^Invalid settings$/,
    /Invalid or malformed JSON$/,
    /^Remote Control$/,
    /^Remote Control is only available when using Claude via api\.anthropic\.com\./,
    /^- Not connected to the Anthropic API \(api\.anthropic\.com\)$/,
    /^- Feature-flag evaluation disabled \(disabled by CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC\)$/,
  ]).map((line) => line.includes("Invalid or malformed JSON")
    ? "- $CONFIG/settings.json: Invalid or malformed JSON"
    : line);
  const doctorText = doctorLines.join("\n");
  const updateText = updateRun.stdout.trim();
  const checks = {
    exactVersion: versionRun.stdout.trim() === `${expectedVersion} (Claude Code)`,
    exactBinarySha256: await sha256(binary) === expectedSha256,
    updateGateExitZero: updateRun.exitStatus === 0,
    updateGateMessageExact: updateText === "Updates are disabled by your administrator. Contact your IT team to get the latest version.",
    doctorExitZero: doctorRun.exitStatus === 0,
    doctorIdentifiesNativeVersion: doctorText.includes("Running: native (2.1.235)"),
    doctorIdentifiesCommit: doctorText.includes("Commit: ba01fa45e3d1"),
    doctorIdentifiesPlatform: doctorText.includes("Platform: darwin-arm64"),
    doctorIdentifiesBundledSearch: doctorText.includes("Search: OK (bundled)"),
    doctorReportsAutoUpdateGate: doctorText.includes("Auto-updates: disabled (set by env: DISABLE_AUTOUPDATER)"),
    doctorReportsInvalidSettings: doctorText.includes("$CONFIG/settings.json: Invalid or malformed JSON"),
    doctorReportsRemoteCustomEndpointBoundary: doctorText.includes("Remote Control is only available when using Claude via api.anthropic.com."),
    doctorReportsFeatureEvaluationBoundary: doctorText.includes("Feature-flag evaluation disabled (disabled by CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC)"),
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
      updateDisabled: "DISABLE_UPDATES=1 $CLAUDE_2_1_235 update",
      doctor: "DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 ANTHROPIC_BASE_URL=http://127.0.0.1:9 $CLAUDE_2_1_235 doctor",
    },
    input: {
      updateDisabled: { disableUpdates: true },
      doctor: {
        settingsFile: "$CONFIG/settings.json",
        settingsContent: "{invalid",
        customEndpoint: "http://127.0.0.1:9",
        disableAutoUpdater: true,
        disableNonessentialTraffic: true,
      },
    },
    literalOutput: {
      version: versionRun.stdout.trim(),
      updateDisabled: updateText,
      doctor: doctorLines,
    },
    exitStatus: {
      version: versionRun.exitStatus,
      updateDisabled: updateRun.exitStatus,
      doctor: doctorRun.exitStatus,
    },
    observed: {
      doctorLineCount: doctorLines.length,
      invalidSettingsDetected: doctorText.includes("Invalid or malformed JSON"),
      remoteControlAvailable: false,
      autoUpdatesEnabled: false,
    },
    checks,
    pass: Object.values(checks).every(Boolean),
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.pass) {
    process.stderr.write(updateRun.stderr);
    process.stderr.write(doctorRun.stderr);
    process.exitCode = 1;
  }
}

await main();
