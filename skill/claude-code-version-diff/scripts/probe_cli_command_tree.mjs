#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { resolveProbeTarget } from "./probe_target.mjs";

const COMMANDS = [
  ["claude", "root-session", "public", "always", 603700],
  ["claude mcp", "mcp", "public", "registered outside --print early parse", 442367],
  ["claude mcp serve", "mcp", "public", "registered outside --print early parse", 442368],
  ["claude mcp add", "mcp", "public", "registered outside --print early parse", 423906],
  ["claude mcp remove", "mcp", "public", "registered outside --print early parse", 442372],
  ["claude mcp list", "mcp", "public", "registered outside --print early parse", 442375],
  ["claude mcp get", "mcp", "public", "registered outside --print early parse", 442378],
  ["claude mcp login", "mcp", "public", "registered outside --print early parse", 442381],
  ["claude mcp logout", "mcp", "public", "registered outside --print early parse", 442384],
  ["claude mcp add-json", "mcp", "public", "registered outside --print early parse", 442387],
  ["claude mcp add-from-claude-desktop", "mcp", "public", "Mac/WSL handler support", 442390],
  ["claude mcp reset-project-choices", "mcp", "public", "project scope", 442393],
  ["claude mcp xaa", "mcp-xaa", "conditional", "CLAUDE_CODE_ENABLE_XAA=1", 424008],
  ["claude mcp xaa setup", "mcp-xaa", "conditional", "CLAUDE_CODE_ENABLE_XAA=1", 424009],
  ["claude mcp xaa login", "mcp-xaa", "conditional", "CLAUDE_CODE_ENABLE_XAA=1", 424032],
  ["claude mcp xaa show", "mcp-xaa", "conditional", "CLAUDE_CODE_ENABLE_XAA=1", 424054],
  ["claude mcp xaa clear", "mcp-xaa", "conditional", "CLAUDE_CODE_ENABLE_XAA=1", 424065],
  ["claude plugin", "plugin", "public", "registered outside --print early parse", 448563, ["plugins"]],
  ["claude plugin init", "plugin", "public", "registered outside --print early parse", 448564, ["new"]],
  ["claude plugin validate", "plugin", "public", "registered outside --print early parse", 448567],
  ["claude plugin tag", "plugin", "public", "registered outside --print early parse", 448570],
  ["claude plugin list", "plugin", "public", "registered outside --print early parse", 448573],
  ["claude plugin eval", "plugin-eval", "public-entry/guarded-action", "lHn() early-access check runs on action", 448580],
  ["claude plugin eval init", "plugin-eval", "public-entry/guarded-action", "lHn() early-access check runs on action", 448585],
  ["claude plugin details", "plugin", "public", "registered outside --print early parse", 448591],
  ["claude plugin marketplace", "plugin", "public", "registered outside --print early parse", 448595],
  ["claude plugin marketplace add", "plugin", "public", "registered outside --print early parse", 448596],
  ["claude plugin marketplace list", "plugin", "public", "registered outside --print early parse", 448599],
  ["claude plugin marketplace remove", "plugin", "public", "registered outside --print early parse", 448602],
  ["claude plugin marketplace update", "plugin", "public", "registered outside --print early parse", 448605],
  ["claude plugin install", "plugin", "public", "registered outside --print early parse", 448608, ["i"]],
  ["claude plugin uninstall", "plugin", "public", "registered outside --print early parse", 448611, ["remove"]],
  ["claude plugin prune", "plugin", "public", "registered outside --print early parse", 448614, ["autoremove"]],
  ["claude plugin enable", "plugin", "public", "registered outside --print early parse", 448617],
  ["claude plugin disable", "plugin", "public", "registered outside --print early parse", 448620],
  ["claude plugin update", "plugin", "public", "registered outside --print early parse", 448623],
  ["claude gateway", "gateway", "public", "not registered in --print early parse", 630169],
  ["claude auth", "auth", "public", "not registered in --print early parse", 630183],
  ["claude auth login", "auth", "public", "not registered in --print early parse", 630184],
  ["claude auth status", "auth", "public", "not registered in --print early parse", 630187],
  ["claude auth logout", "auth", "public", "not registered in --print early parse", 630190],
  ["claude project", "project", "public", "not registered in --print early parse", 630193],
  ["claude project purge", "project", "public", "not registered in --print early parse", 630193],
  ["claude setup-token", "auth", "public", "not registered in --print early parse", 630196],
  ["claude agents", "background", "public/fast-path-capable", "TTY + fleet gate may bypass Commander action", 630199],
  ["claude ultrareview", "cloud-review", "public", "remote entitlement and repository target", 630202],
  ["claude auto-mode", "auto-mode", "conditional", "remote config state is not disabled", 630206],
  ["claude auto-mode defaults", "auto-mode", "conditional", "auto-mode command registered", 630207],
  ["claude auto-mode config", "auto-mode", "conditional", "auto-mode command registered", 630210],
  ["claude auto-mode reset", "auto-mode", "conditional", "auto-mode command registered", 630213],
  ["claude auto-mode critique", "auto-mode", "conditional", "auto-mode command registered", 630216],
  ["claude remote-control", "remote-control", "hidden/fast-path", "auth + policy + allow_remote_control + trusted-device gates", 630221, ["rc", "remote", "sync", "bridge"]],
  ["claude doctor", "lifecycle", "public", "local diagnostics", 630224],
  ["claude sandbox", "sandbox", "hidden", "platform-specific Windows implementation", 630228],
  ["claude sandbox install", "sandbox", "hidden", "Windows sandbox availability", 630229],
  ["claude sandbox status", "sandbox", "hidden", "Windows sandbox availability", 630232],
  ["claude update", "lifecycle", "public", "update policy/channel/install layout", 630235, ["upgrade", "--update", "--upgrade"]],
  ["claude install", "lifecycle", "public", "native installer availability", 630238],
  ["claude import", "import", "public-entry/conditional-action", "tengu_import plus config-readable pre-rewrite", 630241],
  ["claude import-conversations", "import", "hidden", "explicit archive path", 630246],
];

const MANUAL_COMMANDS = [
  ["claude daemon", "daemon", "hidden-fast-path", "FKc argv dispatch; policy and fleet gates", 93, []],
  ["claude daemon run", "daemon", "manual-parser", "background-agent availability", 632524, []],
  ["claude daemon status", "daemon", "manual-parser", "static policy continues when helper refresh fails", 632660, []],
  ["claude daemon logs", "daemon", "manual-parser", "local log path", 632704, ["log"]],
  ["claude daemon install", "daemon", "conditional/disabled-in-build", "HIt() and platform service manager", 632550, []],
  ["claude daemon start", "daemon", "conditional/disabled-in-build", "HIt(), service installed and singleton config dir", 632573, []],
  ["claude daemon restart", "daemon", "conditional/disabled-in-build", "HIt(), service installed and singleton config dir", 632573, []],
  ["claude daemon uninstall", "daemon", "manual-parser", "platform service manager", 632590, []],
  ["claude daemon stop", "daemon", "manual-parser", "lock identity and --any/--keep-workers", 632598, []],
  ["claude daemon list", "daemon", "hidden-manual-parser", "daemon config readable", 632506, []],
  ["claude daemon scheduled", "daemon-config", "hidden-manual-parser", "daemon config and service install for writes", 632511, []],
  ["claude daemon scheduled add", "daemon-config", "hidden-manual-parser", "trusted directory + valid cron + installed service", 632180, []],
  ["claude daemon scheduled remove", "daemon-config", "hidden-manual-parser", "installed service + matching task id", 632190, []],
  ["claude daemon scheduled list", "daemon-config", "hidden-manual-parser", "daemon config readable", 632174, []],
  ["claude daemon remote-control", "daemon-config", "hidden-manual-parser", "daemon config and service install for writes", 632511, []],
  ["claude daemon remote-control add", "daemon-config", "hidden-manual-parser", "trusted canonical directory + installed service", 632240, []],
  ["claude daemon remote-control remove", "daemon-config", "hidden-manual-parser", "installed service + unambiguous name/dir", 632232, []],
  ["claude daemon remote-control list", "daemon-config", "hidden-manual-parser", "daemon config readable", 632224, []],
  ["claude daemon hub", "daemon", "hidden-manual-parser", "TTY; otherwise prints a diagnostic", 632514, []],
  ["claude self-hosted-runner", "self-hosted-runner", "hidden-fast-path", "environment secret/work-order service", 638118, []],
  ["claude self-hosted-runner orchestrator", "self-hosted-runner", "hidden-fast-path", "environment secret + hooks-dir", 638121, []],
  ["claude self-hosted-runner setup", "self-hosted-runner", "hidden-fast-path", "spawns setup Agent session", 638126, []],
  ["claude self-hosted-runner doctor", "self-hosted-runner", "hidden-fast-path", "spawns diagnostic Agent session", 638131, []],
  ["claude self-hosted-runner code-sign", "self-hosted-runner", "internal-helper", "runner session id/token/base URL", 638136, []],
  ["claude self-hosted-runner decode-token", "self-hosted-runner", "operator-helper", "JWT source; verification on by default", 638141, []],
  ["claude logs", "background-verb", "conditional-fast-path", "fleet gate + job id", 638005, []],
  ["claude attach", "background-verb", "conditional-fast-path", "fleet gate + job id", 638005, []],
  ["claude stop", "background-verb", "conditional-fast-path", "fleet gate + job id", 638005, ["kill"]],
  ["claude respawn", "background-verb", "conditional-fast-path", "fleet gate + job id", 638005, []],
  ["claude rm", "background-verb", "conditional-fast-path", "fleet gate + job id", 638005, []],
];

const INTERNAL_ENTRYPOINTS = [
  {
    argv: "--handle-uri <uri>",
    owner: "OS deep-link protocol handler",
    sourceLine: 630130,
    handlerSourceLine: 604137,
    inputProtocol: "The next argv token must be a claude-cli://open URI. Optional cwd must be an absolute local path no longer than 4,096 characters; repo must be owner/repo; q is normalized and capped at 5,000 characters.",
    orderedLifecycle: [
      "Screen the complete argv, load configuration support, parse and validate the URI action and fields.",
      "Resolve cwd directly, from a local clone of repo, or to the user's home; optionally read the repository's last-fetch time.",
      "Select a supported terminal and detach a new Claude process with deep-link-origin, repository and encoded prefill arguments.",
    ],
    successState: "A supported terminal process is spawned and the handler exits 0. The query is passed as a prefill; this entrypoint does not itself submit the prompt.",
    failureBoundary: "Parse, unsafe path/query, repository resolution, terminal detection, quoting or spawn failures exit 1. A failed launch does not prove that no terminal-side process was partially created.",
    externalSideEffects: "May open a new terminal window/process and read local repository metadata. Any later model or tool side effects belong to the launched session, not to the URI parser.",
  },
  {
    argv: "--claude-in-chrome-mcp",
    owner: "Claude in Chrome MCP stdio child",
    sourceLine: 637899,
    handlerSourceLine: 410484,
    inputProtocol: "The parent speaks MCP JSON-RPC over stdin/stdout. Environment may supply remote-session identity, bridge endpoint selection and CLAUDE_CHROME_PERMISSION_MODE (ask, skip_all_permission_checks or follow_a_plan).",
    orderedLifecycle: [
      "Initialize configuration, auth and cleanup services, then build the Chrome bridge context and MCP server.",
      "Resolve OAuth/account identity, local socket paths, optional proxy settings and the local/staging/production WebSocket bridge URL.",
      "Connect the MCP server to stdio; on stdin end/error, close shared resources and exit 0.",
    ],
    successState: "A long-lived MCP server is connected to stdio and can relay tool calls to the paired browser extension.",
    failureBoundary: "Invalid permission mode is ignored with a warning; account mismatch uses token-derived identity with a warning. Bootstrap, auth, socket/WebSocket or stdio-connect failures reject the child. Extension disconnects surface as tool errors rather than proving server startup failed.",
    externalSideEffects: "May persist paired extension device metadata, open local/remote bridge connections and, after a tool call, change the user's real browser state. Cleanup or process exit cannot undo completed browser actions.",
  },
  {
    argv: "--chrome-native-host",
    owner: "Chrome native-messaging host and local MCP socket bridge",
    sourceLine: 637903,
    handlerSourceLine: 410597,
    inputProtocol: "Chrome native messaging uses a 4-byte little-endian length followed by UTF-8 JSON, capped at 1 MiB. Accepted Chrome message types are ping, get_status, tool_response and notification; local MCP clients use the same length framing on a private socket.",
    orderedLifecycle: [
      "Create the socket directory, remove stale PID sockets, listen on the process socket and attempt 0600 permissions.",
      "Read framed Chrome messages, answer status/ping locally, and forward tool responses or notifications to connected MCP clients.",
      "Forward framed MCP requests to Chrome as tool_request messages; on Chrome stdin EOF/error, close clients, listener and socket files.",
    ],
    successState: "The native host remains alive while Chrome keeps stdin open and bridges framed messages between the extension and zero or more MCP clients.",
    failureBoundary: "Invalid JSON/schema returns an error frame; zero, oversized or malformed lengths terminate that read/connection. Socket bind/start failure rejects startup. A chmod failure is logged but does not stop an already-listening socket.",
    externalSideEffects: "Creates and deletes local socket files, reports MCP connect/disconnect state to Chrome, and relays requests that can cause browser-side effects. Relayed browser actions are outside local rollback.",
  },
  {
    argv: "--computer-use-mcp",
    owner: "Computer Use MCP stdio child",
    sourceLine: 637907,
    handlerSourceLine: 383824,
    inputProtocol: "The parent speaks MCP JSON-RPC over stdin/stdout. Tool discovery is built from native computer-use capabilities and a best-effort installed-application enumeration with a 1-second budget.",
    orderedLifecycle: [
      "Initialize native/configuration services and enumerate a filtered list of installed applications within the 1-second budget.",
      "Construct the capability-backed MCP tool list; if the executor is disabled, tools/list returns an empty array.",
      "Connect over stdio; stdin end/error closes shared resources and exits 0.",
    ],
    successState: "A long-lived stdio MCP server exposes the locally available computer-use tools, or an empty tool list when locally disabled.",
    failureBoundary: "Application enumeration timeout/failure only removes the app list from tool descriptions. Native initialization, server construction or stdio connection failures reject startup; OS permission/TCC failures can still occur per tool call.",
    externalSideEffects: "Tool calls can capture the screen and interact with real local applications under OS permissions. Process cleanup does not reverse completed clicks, typing or application state changes.",
  },
  {
    argv: "--daemon-worker <kind>",
    owner: "Daemon heartbeat, scheduled-task or Remote Control worker",
    sourceLine: 637911,
    handlerSourceLine: 420601,
    inputProtocol: "kind must be heartbeat, scheduled or remoteControl. stdin is read to EOF as JSON containing config and optional initialAccessToken; config is validated against the selected worker schema.",
    orderedLifecycle: [
      "Load fast-path policy, reject unknown/unavailable kinds, read all stdin and validate the kind-specific config.",
      "Install SIGTERM/SIGINT/parent-message abort handlers and a 30-second parent-liveness watchdog; seed auth and Storage v5 when available.",
      "Run the selected worker, emitting newline-delimited status text on stdout until completion or abort.",
    ],
    successState: "The selected worker owns its heartbeat, schedule or Remote Control loop until it completes or receives an abort signal.",
    failureBoundary: "Unknown kind, unavailable non-heartbeat worker, invalid JSON or invalid config exit 2. HTTP 429 is reported on stdout and exits 75. Other worker exceptions escape to the process-level failure path; parent loss aborts and then exits 0 after a 2-second grace period.",
    externalSideEffects: "Heartbeat is observational, while scheduled and Remote Control workers may contact services, start sessions or deliver notifications. Aborting the worker cannot undo remote work already accepted or tools already executed.",
  },
  {
    argv: "--bg-pty-host",
    owner: "Background PTY process and socket supervisor",
    sourceLine: 637919,
    handlerSourceLine: 420732,
    inputProtocol: "argv is <socket> <cols> <rows> -- <executable> [args...]. The socket protocol carries PTY data plus auth, ping/pong, resize and kill controls; auth comes from CLAUDE_BG_PTY_AUTH or a one-use token file.",
    orderedLifecycle: [
      "Bootstrap settings best-effort, validate argv, consume auth material and create a Bun PTY plus the requested child process.",
      "Listen on the socket, replay a 256 KiB output ring to new clients, enforce auth before input, apply resize/kill controls and drop clients above 1 MiB writable backlog.",
      "Watch client heartbeats and parent/orphan state, escalate SIGTERM to SIGKILL after 5 seconds, drain final output, emit the exit frame and remove the socket.",
    ],
    successState: "The child exit code is propagated after buffered output is drained; connected clients receive the final code/signal frame and the socket is cleaned up.",
    failureBoundary: "Bad argv or spawn/listen/runtime failure exits 1 and writes host diagnostics. Settings bootstrap failure is explicitly non-fatal because the supervisor already gated the spawn. Losing the parent with no client for the default 60 seconds terminates the child.",
    externalSideEffects: "Creates socket/diagnostic/optional PTY-record files and executes the parent-selected command in a real PTY. Killing the host does not reverse filesystem, process, network or tool side effects already produced by that command.",
  },
  {
    argv: "--bg-spare",
    owner: "Authenticated warm background-session spare",
    sourceLine: 637928,
    handlerSourceLine: 630696,
    inputProtocol: "The first argv value is a claim socket path. A single newline-delimited JSON claim supplies cwd, env, argv, optional sessionId and auth; auth comes from CLAUDE_BG_CLAIM_AUTH or a one-use token file and authenticated frames are capped at 8 MiB.",
    orderedLifecycle: [
      "Consume and delete claim credentials, begin importing the main CLI in parallel, create the claim socket and watch the original parent every 2 seconds.",
      "Accept one authenticated claim, remove signal/watchdog handlers and delete the claim socket.",
      "Resolve and chdir to the claimed cwd, replace sensitive provider env/argv/session state, finish main import and enter the normal Claude main function in the same process.",
    ],
    successState: "The prewarmed process becomes the claimed background Claude session, preserving warm startup while using the claim's cwd, environment, argv and session identity.",
    failureBoundary: "Missing socket exits 2; claim receive/auth/JSON failure exits 1; parent replacement exits 0 before claim. Post-claim initialization throws after recording a classified failure. The warm-spare launcher disables refill after an early crash/daemonizing contract violation.",
    externalSideEffects: "Creates/deletes claim and PTY sockets/token files, changes cwd/environment/process identity and then runs a full Claude session. Model/tool effects after claim are not reversible by disposing the spare.",
  },
  {
    argv: "--preload",
    owner: "Remote preload process awaiting one session claim",
    sourceLine: 637935,
    handlerSourceLine: 630956,
    inputProtocol: "The optional first argv value is a claim socket path, defaulting to the runtime-owned remote spare socket under $CLAUDE_REMOTE_HOME. One newline-delimited JSON claim supplies cwd, env, argv and optional sessionId; this WUi call does not pass a per-frame auth token.",
    orderedLifecycle: [
      "Delete inherited session/worker environment fields, start importing the main CLI, remove stale socket state and create the claim listener plus a 0600 PID file.",
      "Wait for one JSON claim; signals clean socket/PID state and exit 0, while malformed/failed claim receipt exits 1.",
      "Delete listener state, resolve and chdir to the claimed cwd, replace environment/argv/session state, finish main import and enter the normal Claude main function.",
    ],
    successState: "The preload process is converted into the claimed Claude session and continues through the ordinary main entrypoint without a second executable startup.",
    failureBoundary: "The claim socket itself has no per-frame auth argument in this path, so trust relies on the parent-owned runtime and filesystem boundary. Signal exits 0; claim receive or uncaught failure exits 1; post-claim main failures follow normal CLI handling.",
    externalSideEffects: "Creates/deletes the claim socket and PID file, changes cwd/environment/argv and then runs a full session. Any model, filesystem or remote effects after claim remain outside preload rollback.",
  },
];

const FAMILIES = {
  "root-session": {
    owner: "VQg root Commander action -> ZGg -> qQg (headless) or Hb0 (interactive)",
    sideEffects: "May read settings/auth/keychain, restore or write transcript state, call the model, execute approved tools, and start TUI/SDK/cloud/worktree flows.",
    failure: "Startup validation, trust/policy/auth, incompatible input/output flags, resume lookup, transport, model, tool and terminal-result failures use different exit paths.",
  },
  mcp: {
    owner: "sWm/FMm registration; lazy mcp*Handler modules and settings writer",
    sideEffects: "Lists/health-checks servers, starts stdio MCP service, mutates scoped MCP settings, stores or revokes OAuth secrets, or resets project approval choices.",
    failure: "Scope/transport/URL/JSON validation, project trust, OAuth support, keychain writes and server health fail independently; help proves only registration.",
  },
  "mcp-xaa": {
    owner: "jMm registration; mcpXaaIdpLoginModule and user-settings writer",
    sideEffects: "Writes xaaIdp settings and stores/clears client secret or id_token in secure storage; browser login may open an authorization URL.",
    failure: "Disabled env gate, invalid issuer/port, missing secret, OIDC failure or keychain failure; setup can persist settings before a later keychain write fails.",
  },
  plugin: {
    owner: "bVm registration; lazy plugin/marketplace handlers",
    sideEffects: "Creates manifests/tags, clones or edits marketplace declarations, installs/uninstalls/enables/disables plugins, writes config and may execute marketplace-declared install commands after confirmation.",
    failure: "Trust, manifest/schema, dirty Git tree, scope, dependency, command-confirmation and cache/reload failures; many successes require restart before runtime state changes.",
  },
  "plugin-eval": {
    owner: "bVm eval branch -> pluginEvalHandler/pluginEvalInitHandler",
    sideEffects: "Runs bounded model/evaluator sessions, optional scaffold scripts, writes result JSON/HTML and may publish a report.",
    failure: "Early-access gate, invalid budget/threshold/ablation, tool grants, scaffold exit, cost ceiling and score threshold use distinct non-zero results.",
  },
  gateway: {
    owner: "Db0 gateway command -> startGateway",
    sideEffects: "Starts a long-lived enterprise auth/telemetry gateway from YAML configuration.",
    failure: "Missing/invalid config or listener/runtime failure prints claude gateway error and exits 1.",
  },
  auth: {
    owner: "Db0 auth/setup-token registrations -> auth* or setupTokenHandler",
    sideEffects: "Starts browser/SSO login, reads account state, clears credentials, or creates a long-lived subscription token.",
    failure: "Provider/account mismatch, login callback, credential storage and subscription eligibility failures; status can be JSON or text.",
  },
  project: {
    owner: "Db0 project purge -> purgeProjectHandler",
    sideEffects: "Deletes transcripts, tasks, file history and project config registration; dry-run is read-only.",
    failure: "--all/path conflict, confirmation mode, per-item filesystem failure and invalid target; deletion is not reversible by transcript rewind.",
  },
  background: {
    owner: "agentsCommandHandler or pre-Commander fleet-view fast path",
    sideEffects: "Reads background session registries, opens the agent view, or prints active/completed session JSON; dispatch defaults are carried to new sessions.",
    failure: "Fleet feature/policy gate, TTY mode, workspace trust and bypass-permission consent can stop before the Commander action.",
  },
  "cloud-review": {
    owner: "ultrareviewHandler",
    sideEffects: "Starts and polls a cloud multi-agent review; optional --post writes one PR comment.",
    failure: "Repository/target resolution, entitlement, timeout, remote job and PR-post failures; --no-post is the default.",
  },
  "auto-mode": {
    owner: "autoMode*Handler family",
    sideEffects: "Prints default/effective classifier rules, removes user autoMode config on reset, or calls a model to critique custom rules.",
    failure: "Command registration depends on remote config not being disabled; settings/policy/model gates can still make runtime auto mode unavailable.",
  },
  "remote-control": {
    owner: "gw0 fast path -> bridgeMain (Commander action is secondary)",
    sideEffects: "Starts a persistent bridge, enrolls trusted device state, attaches or creates local sessions and exchanges remote control events.",
    failure: "Managed disable, missing OAuth, product/plan gate, minimum version, policy and trusted-device checks fail before bridgeMain; aliases remote/sync/bridge are fast-path only.",
  },
  lifecycle: {
    owner: "doctorHandler, update, or installHandler",
    sideEffects: "Doctor reads local installation/settings; update/install download and replace the native build and may migrate local state.",
    failure: "Policy/channel/platform/download/signature/install-layout failures; binary rollback does not roll back settings or transcripts.",
  },
  sandbox: {
    owner: "sandboxInstallHandler/sandboxStatusHandler",
    sideEffects: "Status is read-only; install self-elevates on Windows and installs sandbox user/network filters.",
    failure: "Platform unavailable, policy lock, elevation or component install failure; status returns structured reasons.",
  },
  import: {
    owner: "Y3f/K3f pre-rewrite, /import command, or importConversationsHandler",
    sideEffects: "Imports selected Codex/Gemini config or writes archived exported conversations into Claude state; dry-run avoids writes.",
    failure: "Feature gate/config-read failure, digest mismatch, unsafe project-level items, malformed archive or storage write failure.",
  },
  daemon: {
    owner: "gw0 FKc fast path -> daemonMain/BS0 manual parser",
    sideEffects: "Runs/stops the background supervisor, tails logs, inspects lock/worker state, and conditionally manages a platform service.",
    failure: "Manual parser accepts more paths than help lists; policy, service-disabled build, lock identity, launcher, stale binary and reachability have separate exits.",
  },
  "daemon-config": {
    owner: "daemon handleCliKind -> scheduled or remote-control config handlers",
    sideEffects: "Lists or edits daemon.json scheduled tasks and persistent Remote Control servers.",
    failure: "Writes require installed service, trusted directories and valid cron/spawn mode; ambiguous or missing identifiers fail closed.",
  },
  "self-hosted-runner": {
    owner: "gw0 self-hosted-runner fast path -> runner/orchestrator/setup/doctor/helper mains",
    sideEffects: "Registers runner capacity, checks out repositories, spawns child Claude sessions, executes lifecycle hooks, exposes health/metrics, signs commits or inspects work-order JWTs.",
    failure: "Secret/auth, option parser, confinement, hook, child init/watchdog, token rotation, Git proxy/signing and drain/release failures are independently surfaced.",
  },
  "background-verb": {
    owner: "gw0 background fast path -> hMh handlers",
    sideEffects: "Tails/attaches to, stops, respawns or removes a background job; kill is routed to the same stop handler.",
    failure: "Fleet/policy gate, missing/ambiguous job, daemon/control socket and PTY attachment failures; completed external work is not undone.",
  },
};

const ROOT_HIDDEN_OPTIONS = [
  "-d2e, --debug-to-stderr", "--init", "--init-only", "--maintenance",
  "--session-mirror", "--thinking <mode>", "--thinking-display <display>",
  "--max-thinking-tokens <tokens>", "--max-turns <turns>", "--task-budget <tokens>",
  "--enable-auth-status", "--permission-prompt-tool <tool>", "--system-prompt-file <file>",
  "--append-system-prompt-file <file>", "--append-subagent-system-prompt <prompt>",
  "--plan-mode-instructions <instructions>", "--resume-session-at <message id>",
  "--resume-drops-turn <message id>", "--reply-on-resume", "--rewind-files <user-message-id>",
  "--workload <tag>", "--managed-settings <json>", "--plugin-dir-no-mcp <path>",
  "--advisor <model>", "--enable-auto-mode", "--messaging-socket-path <path>",
  "--channels <servers...>", "--dangerously-load-development-channels <servers...>",
  "--agent-id <id>", "--agent-name <name>", "--team-name <name>", "--agent-color <color>",
  "--plan-mode-required", "--parent-session-id <id>", "--teammate-mode <mode>",
  "--agent-type <type>", "--sdk-url <url>", "--remote [description|session_id|url]",
  "--pool <pool_id>", "--correlation-id <id>", "--ref <ref>", "--on-branch <branch>",
  "--rc [name]", "--watch-artifact <artifact>", "--watch-artifact-no-autoreact <artifact>",
  "--prefill <text>", "--deep-link-origin", "--deep-link-repo <slug>",
  "--deep-link-last-fetch <ms>", "--prefill-b64 <b64>", "--deep-link-cwd-b64 <b64>",
];

const STATIC_SYNTAX = {
  "claude remote-control": "claude remote-control [options]",
  "claude daemon run": "claude daemon run [json-path] [options]",
  "claude daemon status": "claude daemon status [options]",
  "claude daemon logs": "claude daemon logs [options]",
  "claude daemon install": "claude daemon install [options]",
  "claude daemon start": "claude daemon start [options]",
  "claude daemon restart": "claude daemon restart [options]",
  "claude daemon uninstall": "claude daemon uninstall [options]",
  "claude daemon stop": "claude daemon stop [--any] [--keep-workers] [options]",
  "claude daemon list": "claude daemon list [--json] [options]",
  "claude daemon scheduled": "claude daemon scheduled <add|remove|list> [options]",
  "claude daemon scheduled add": "claude daemon scheduled add --prompt <text> --cron <expr> [options]",
  "claude daemon scheduled remove": "claude daemon scheduled remove <task-id> [options]",
  "claude daemon scheduled list": "claude daemon scheduled list [--json] [options]",
  "claude daemon remote-control": "claude daemon remote-control <add|remove|list> [options]",
  "claude daemon remote-control add": "claude daemon remote-control add [options]",
  "claude daemon remote-control remove": "claude daemon remote-control remove <name-or-dir> [options]",
  "claude daemon remote-control list": "claude daemon remote-control list [--json] [options]",
  "claude daemon hub": "claude daemon hub",
  "claude self-hosted-runner code-sign": "claude self-hosted-runner code-sign -Y sign [-n namespace] [-f keyfile] <buffer-file>",
  "claude logs": "claude logs <job>",
  "claude attach": "claude attach <job>",
  "claude stop": "claude stop <job>",
  "claude respawn": "claude respawn <job>",
  "claude rm": "claude rm <job>",
};

const STATIC_OPTIONS = {
  "claude mcp add": ["--xaa (hidden unless CLAUDE_CODE_ENABLE_XAA=1)"],
  "claude plugin": ["--cowork (hidden on applicable leaf commands)"],
  "claude plugin eval init": ["--interview (hidden alias for --interactive)"],
  "claude agents": ["--plugin-dir-no-mcp <path> (hidden)"],
  "claude remote-control": [
    "--name <name>", "--remote-control-session-name-prefix <prefix>", "-c, --continue",
    "--session-id <id>", "--permission-mode <mode>", "--debug-file <path>",
    "-v, --verbose", "--spawn <same-dir|worktree|session>", "--capacity <N>",
    "--[no-]create-session-in-dir",
  ],
  "claude daemon": ["--origin <service|transient|foreground>", "--spawned-by <json> (internal)"],
  "claude daemon run": ["--json-path <path>", "--log-file <path>", "--origin <mode>", "--spawned-by <json>"],
  "claude daemon status": ["--json-path <path>", "--log-file <path>"],
  "claude daemon logs": ["--log-file <path>"],
  "claude daemon install": ["--json-path <path>", "--log-file <path>"],
  "claude daemon start": ["--json-path <path>", "--log-file <path>"],
  "claude daemon restart": ["--json-path <path>", "--log-file <path>"],
  "claude daemon uninstall": [],
  "claude daemon stop": ["--any", "--keep-workers"],
  "claude daemon list": ["--json"],
  "claude daemon scheduled": ["--json", "--id <id>", "--prompt <text>", "--cron <expr>", "--dir <path>", "--permission-mode <mode>", "--model <model>"],
  "claude daemon scheduled add": ["--id <id>", "--prompt <text>", "--cron <expr>", "--dir <path>", "--permission-mode <mode>", "--model <model>"],
  "claude daemon scheduled remove": [],
  "claude daemon scheduled list": ["--json"],
  "claude daemon remote-control": ["--json", "--dir <path>", "--name <name>", "--spawn-mode <same-dir|worktree>"],
  "claude daemon remote-control add": ["--dir <path>", "--name <name>", "--spawn-mode <same-dir|worktree>"],
  "claude daemon remote-control remove": [],
  "claude daemon remote-control list": ["--json"],
  "claude self-hosted-runner code-sign": ["-Y sign", "-n <namespace>", "-f <keyfile>"],
};

const HELP_PATHS = COMMANDS.map(([command]) => command).filter((command) => command !== "claude remote-control");
const MANUAL_HELP_PATHS = [
  "claude daemon",
  "claude self-hosted-runner",
  "claude self-hosted-runner orchestrator",
  "claude self-hosted-runner setup",
  "claude self-hosted-runner doctor",
  "claude self-hosted-runner decode-token",
];

function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(file) {
  return sha256Buffer(await readFile(file));
}

function parseTerms(output, section) {
  const lines = output.split("\n");
  const start = lines.findIndex((line) => line.trim() === `${section}:`);
  if (start < 0) return [];
  const terms = [];
  for (let index = start + 1; index < lines.length; index++) {
    const line = lines[index];
    if (/^[A-Z][A-Za-z ]+:$/.test(line.trim())) break;
    const match = /^  (\S(?:.*?\S)?)\s{2,}\S/.exec(line);
    if (match) terms.push(match[1]);
  }
  return terms;
}

function parseHelp(stdout, stderr) {
  const combined = `${stdout}${stderr}`;
  return {
    usage: combined.split("\n").find((line) => line.startsWith("Usage:")) ?? null,
    arguments: parseTerms(combined, "Arguments"),
    options: parseTerms(combined, "Options"),
    commands: parseTerms(combined, "Commands"),
  };
}

function run(binary, args, env, cwd, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("close", (exitStatus, signal) => {
      clearTimeout(timer);
      resolve({ exitStatus, signal, timedOut, stdout, stderr });
    });
  });
}

function helpArgs(command) {
  if (command === "claude") return ["--help"];
  return [...command.split(" ").slice(1), "--help"];
}

function caseId(command) {
  return command.replace(/^claude(?: |$)/, "root ").trim().replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function row(tuple, observedByCommand) {
  const [command, family, visibility, gate, sourceLine, aliases = []] = tuple;
  const observed = observedByCommand.get(command);
  return {
    path: command,
    family,
    parser: COMMANDS.includes(tuple) ? "commander-or-fast-path" : "manual-fast-path",
    visibility,
    gate,
    aliases,
    syntax: observed?.parsed.usage ?? STATIC_SYNTAX[command] ?? command,
    arguments: observed?.parsed.arguments ?? [],
    observedOptions: observed?.parsed.options ?? [],
    hiddenOrStaticOptions: [
      ...(command === "claude" ? ROOT_HIDDEN_OPTIONS : []),
      ...(STATIC_OPTIONS[command] ?? []),
    ],
    observedChildren: observed?.parsed.commands ?? [],
    handlerOwner: FAMILIES[family].owner,
    sideEffects: FAMILIES[family].sideEffects,
    failureBehavior: FAMILIES[family].failure,
    evidence: {
      static: `reverse/javascript/cli.readable.js:${sourceLine}`,
      probeCase: observed?.id ?? null,
      limitation: observed
        ? "Help/usage proves parser surface and option spelling, not successful handler execution."
        : "Static dispatcher evidence only; no help output was executed for this row.",
    },
  };
}

async function main() {
  const { repo, binary, expectedVersion, expectedSha256 } = resolveProbeTarget(import.meta.url);
  const reportPath = path.resolve(process.env.CLAUDE_CLI_TREE_REPORT ?? path.join(repo, "analysis/runtime-probes/cli-command-tree.json"));
  const inventoryPath = path.resolve(process.env.CLAUDE_CLI_TREE_INVENTORY ?? path.join(repo, "analysis/cli-command-inventory.json"));
  const temporary = await mkdtemp(path.join(os.tmpdir(), "claude-cli-tree-probe-"));
  const home = path.join(temporary, "home");
  const workspace = path.join(temporary, "workspace");
  await Promise.all([mkdir(home, { recursive: true }), mkdir(workspace, { recursive: true })]);
  const env = {
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_CACHE_HOME: path.join(home, ".cache"),
    XDG_DATA_HOME: path.join(home, ".local", "share"),
    PATH: process.env.PATH ?? "/usr/bin:/bin:/usr/sbin:/sbin",
    TERM: "dumb",
    NO_COLOR: "1",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  };
  const actualSha256 = await sha256File(binary);
  const versionResult = await run(binary, ["--version"], env, workspace);
  const cases = [];
  for (const command of [...HELP_PATHS, ...MANUAL_HELP_PATHS]) {
    const xaa = command.startsWith("claude mcp xaa");
    const result = await run(binary, helpArgs(command), { ...env, ...(xaa ? { CLAUDE_CODE_ENABLE_XAA: "1" } : {}) }, workspace);
    const parsed = parseHelp(result.stdout, result.stderr);
    cases.push({
      id: caseId(command),
      command,
      argv: `$CLAUDE_TARGET ${helpArgs(command).join(" ")}`,
      input: xaa ? { environment: { CLAUDE_CODE_ENABLE_XAA: "1" } } : { environment: "isolated HOME; no credentials or project settings" },
      literalOutput: { stdout: result.stdout, stderr: result.stderr },
      stdoutSha256: sha256Buffer(result.stdout),
      stderrSha256: sha256Buffer(result.stderr),
      exitStatus: result.exitStatus,
      signal: result.signal,
      timedOut: result.timedOut,
      parsed,
      checks: {
        exitedZero: result.exitStatus === 0,
        hasExpectedUsage: parsed.usage?.startsWith(`Usage: ${command}`) ?? false,
      },
    });
  }
  const fallback = await run(binary, ["status", "--help"], env, workspace);
  const remote = await run(binary, ["remote-control", "--help"], env, workspace);
  const codeSign = await run(binary, ["self-hosted-runner", "code-sign", "--help"], env, workspace);
  const observedByCommand = new Map(cases.map((item) => [item.command, item]));
  const source = await readFile(path.join(repo, "reverse/javascript/cli.readable.js"), "utf8");
  const registrationSpecs = [...source.matchAll(/\.command\("([^"]+)"/g)].map((match) => match[1]);
  const inventory = {
    schemaVersion: 1,
    version: expectedVersion,
    binarySha256: expectedSha256,
    source: {
      path: "reverse/javascript/cli.readable.js",
      sha256: sha256Buffer(source),
      explicitCommanderRegistrationCount: registrationSpecs.length,
      explicitCommanderRegistrationSpecs: registrationSpecs,
      boundary: "The readable bundle is generated analysis output. Commander/help/string presence proves parser surface, not a successful runtime branch.",
    },
    counts: {
      commandRows: COMMANDS.length + MANUAL_COMMANDS.length,
      commanderRows: COMMANDS.length,
      manualFastPathRows: MANUAL_COMMANDS.length,
      internalEntrypoints: INTERNAL_ENTRYPOINTS.length,
      exactBinaryHelpCases: cases.length,
    },
    families: FAMILIES,
    commands: [...COMMANDS, ...MANUAL_COMMANDS].map((tuple) => row(tuple, observedByCommand)),
    internalEntrypoints: INTERNAL_ENTRYPOINTS.map((entry) => ({
      argv: entry.argv,
      visibility: "internal",
      owner: entry.owner,
      source: `reverse/javascript/cli.readable.js:${entry.sourceLine}`,
      handlerSource: `reverse/javascript/cli.readable.js:${entry.handlerSourceLine}`,
      inputProtocol: entry.inputProtocol,
      orderedLifecycle: entry.orderedLifecycle,
      successState: entry.successState,
      failureBoundary: entry.failureBoundary,
      externalSideEffects: entry.externalSideEffects,
    })),
    caveats: [
      "claude status --help exits 0 but falls back to root help; exit status alone cannot prove command existence.",
      "Top-level --help omits hidden and pre-Commander paths including remote-control, sandbox, daemon, self-hosted-runner and background verbs.",
      "When -p/--print is present, Db0 parses before registering most subcommands, so root help and non-print command registration cannot be treated as one unconditional tree.",
      "Conditional registration (XAA, auto-mode) and action-time gates (plugin eval, import, Remote Control, platform services) are different states.",
    ],
  };
  const pass = versionResult.exitStatus === 0
    && versionResult.stdout.trim().startsWith(`${expectedVersion} (Claude Code)`)
    && actualSha256 === expectedSha256
    && registrationSpecs.length === 59
    && cases.every((item) => item.checks.exitedZero && item.checks.hasExpectedUsage)
    && fallback.exitStatus === 0
    && fallback.stdout.startsWith("Usage: claude [options]")
    && !fallback.stdout.startsWith("Usage: claude status")
    && remote.exitStatus === 1
    && remote.stderr.includes("You must be logged in to use Remote Control")
    && codeSign.exitStatus === 1
    && codeSign.stderr.includes("only SSH-style signing")
    && inventory.commands.every((item) => item.handlerOwner && item.sideEffects && item.failureBehavior);
  const report = {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    target: { version: expectedVersion, binarySha256: expectedSha256 },
    commands: { probe: "$CLAUDE_TARGET <command-path> --help in an isolated HOME" },
    input: { helpCases: cases.length, conditionalEnvironment: { CLAUDE_CODE_ENABLE_XAA: "1 for mcp xaa cases only" } },
    literalOutput: {
      version: versionResult.stdout.trim(),
      rootUsage: observedByCommand.get("claude")?.parsed.usage,
      xaaUsage: observedByCommand.get("claude mcp xaa")?.parsed.usage,
      daemonUsage: observedByCommand.get("claude daemon")?.parsed.usage,
      selfHostedRunnerUsage: observedByCommand.get("claude self-hosted-runner")?.parsed.usage,
      nonexistentStatusHelpFirstLine: fallback.stdout.split("\n")[0],
      remoteControlUnauthenticated: remote.stderr.trim(),
      codeSignHelpAttempt: codeSign.stderr.trim(),
    },
    exitStatus: {
      version: versionResult.exitStatus,
      helpCases: Object.fromEntries(cases.map((item) => [item.id, item.exitStatus])),
      nonexistentStatusHelp: fallback.exitStatus,
      remoteControlHelpWithoutAuth: remote.exitStatus,
      codeSignHelpAttempt: codeSign.exitStatus,
    },
    observed: {
      explicitCommanderRegistrationCount: registrationSpecs.length,
      structuredCommandRows: inventory.counts.commandRows,
      internalEntrypoints: inventory.counts.internalEntrypoints,
      helpCases: cases,
      fallback: { stdout: fallback.stdout, stderr: fallback.stderr },
      remoteControl: { stdout: remote.stdout, stderr: remote.stderr },
      codeSign: { stdout: codeSign.stdout, stderr: codeSign.stderr },
    },
    checks: {
      exactVersion: versionResult.stdout.trim().startsWith(`${expectedVersion} (Claude Code)`),
      exactBinarySha256: actualSha256 === expectedSha256,
      explicitCommanderRegistrationCount59: registrationSpecs.length === 59,
      allHelpCasesExitZeroWithExpectedUsage: cases.every((item) => item.checks.exitedZero && item.checks.hasExpectedUsage),
      nonexistentStatusFallsBackToRootAtExitZero: fallback.exitStatus === 0 && fallback.stdout.startsWith("Usage: claude [options]") && !fallback.stdout.startsWith("Usage: claude status"),
      remoteControlFastPathPreemptsCommanderHelp: remote.exitStatus === 1 && remote.stderr.includes("You must be logged in to use Remote Control"),
      codeSignIsHelperNotHelpCommand: codeSign.exitStatus === 1 && codeSign.stderr.includes("only SSH-style signing"),
      everyCommandHasOwnerSideEffectsAndFailure: inventory.commands.every((item) => item.handlerOwner && item.sideEffects && item.failureBehavior),
    },
    pass,
  };
  await Promise.all([
    mkdir(path.dirname(reportPath), { recursive: true }),
    mkdir(path.dirname(inventoryPath), { recursive: true }),
  ]);
  await Promise.all([
    writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`),
    writeFile(inventoryPath, `${JSON.stringify(inventory, null, 2)}\n`),
  ]);
  if (!pass) throw new Error(`CLI command-tree probe failed; inspect ${reportPath}`);
  process.stdout.write(`CLI command-tree probe: PASS (${cases.length} help cases, ${inventory.counts.commandRows} command rows)\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error}\n`);
  process.exit(1);
});
