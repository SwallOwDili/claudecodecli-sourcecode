import assert from "node:assert/strict";
import test from "node:test";
import { agentLoopScenario } from "../src/scenarios/agent-loop";
import { compactScenario } from "../src/scenarios/compact";
import { permissionsScenario } from "../src/scenarios/permissions";
import { createPlaybackController } from "../src/runtime/machine";
import { normalizeTrace, type LabControlValues, type LabScenario } from "../src/runtime/types";

function trace(scenario: LabScenario, input: string, controls: LabControlValues) {
  return normalizeTrace(scenario.buildTrace(input, controls), scenario.initialFiles);
}

function assertToolPairs(scenario: LabScenario, input: string, controls: LabControlValues) {
  const steps = trace(scenario, input, controls).steps;
  const uses = steps
    .map((step, index) => ({ step, index }))
    .filter(({ step }) => step.kind === "tool_use" && step.tool_use_id);
  const results = steps
    .map((step, index) => ({ step, index }))
    .filter(({ step }) => step.kind === "tool_result" && step.tool_use_id);
  assert.equal(results.length, uses.length);
  for (const use of uses) {
    const matches = results.filter(
      ({ step }) => step.tool_use_id === use.step.tool_use_id,
    );
    assert.equal(matches.length, 1, `${use.step.tool_use_id} must have one result`);
    assert.ok(matches[0].index > use.index, `${use.step.tool_use_id} result must follow its use`);
  }
  for (const result of results) {
    assert.equal(
      uses.filter(({ step }) => step.tool_use_id === result.step.tool_use_id).length,
      1,
      `${result.step.tool_use_id} must have one use`,
    );
  }
}

function compactFixture(
  historyGroups: number,
  preservedGroups: number,
  input = "/compact 保留当前 Summary、文件附件和 Resume 要求",
) {
  return trace(compactScenario, input, {
    historyGroups,
    preservedGroups,
    attachmentRecovery: "exact",
    preCompact: "allow",
  });
}

function assertCompactPreservesToolPairs(historyGroups: number, preservedGroups: number) {
  const built = compactFixture(historyGroups, preservedGroups);
  const boundary = built.steps.find((step) => step.id === "write-boundary");
  assert.ok(boundary);
  const output = boundary.output as {
    compact_metadata: {
      preserved_messages: { uuids: string[]; all_uuids: string[] };
    };
  };
  const preserved = new Set(output.compact_metadata.preserved_messages.uuids);
  const groupStep = built.steps.find((step) => step.id === "group-history");
  const groupProjection = groupStep?.after as {
    preserved_group_heads: string[];
    preserved_message_uuids: string[];
  };
  assert.equal(
    groupProjection.preserved_message_uuids[0],
    groupProjection.preserved_group_heads[0],
  );
  const transcript = (built.initialFiles?.["/session/transcript.jsonl"] ?? "")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as {
      uuid: string;
      content_type: string;
      tool_use_id?: string;
    })
    .filter((message) => preserved.has(message.uuid));
  for (const message of transcript.filter((item) => item.tool_use_id)) {
    const counterpart = message.content_type === "tool_use" ? "tool_result" : "tool_use";
    assert.ok(
      transcript.some(
        (candidate) =>
          candidate.content_type === counterpart &&
          candidate.tool_use_id === message.tool_use_id,
      ),
      `${message.tool_use_id} must stay in one preserved group`,
    );
  }
  assert.deepEqual(
    output.compact_metadata.preserved_messages.all_uuids,
    output.compact_metadata.preserved_messages.uuids,
  );
}

function finalFiles(scenario: LabScenario, input: string, controls: LabControlValues) {
  const built = trace(scenario, input, controls);
  return built.steps.at(-1)?.files ?? built.initialFiles ?? scenario.initialFiles;
}

test("Playback controller preserves load, seek, play, and completion semantics", () => {
  const playback = createPlaybackController().start();
  const observed: Array<{ value: string; index: number }> = [];
  const subscription = playback.subscribe((snapshot) => {
    observed.push({ value: snapshot.value, index: snapshot.context.index });
  });
  playback.send({ type: "LOAD", total: 3 });
  assert.equal(playback.getSnapshot().value, "paused");
  assert.equal(playback.getSnapshot().context.index, -1);
  playback.send({ type: "NEXT" });
  assert.equal(playback.getSnapshot().context.index, 0);
  playback.send({ type: "PLAY" });
  assert.equal(playback.getSnapshot().value, "playing");
  playback.send({ type: "TICK" });
  assert.equal(playback.getSnapshot().context.index, 1);
  playback.send({ type: "TICK" });
  assert.equal(playback.getSnapshot().value, "completed");
  assert.equal(playback.getSnapshot().context.index, 2);
  playback.send({ type: "PREV" });
  assert.equal(playback.getSnapshot().value, "paused");
  assert.equal(playback.getSnapshot().context.index, 1);
  playback.send({ type: "RESET" });
  assert.equal(playback.getSnapshot().context.index, -1);
  playback.send({ type: "SEEK", index: 99 });
  assert.equal(playback.getSnapshot().value, "completed");
  assert.equal(playback.getSnapshot().context.index, 2);
  playback.send({ type: "SEEK", index: -99 });
  assert.equal(playback.getSnapshot().value, "paused");
  assert.equal(playback.getSnapshot().context.index, -1);
  playback.send({ type: "LOAD", total: 0 });
  playback.send({ type: "NEXT" });
  assert.equal(playback.getSnapshot().value, "paused");
  assert.equal(playback.getSnapshot().context.index, -1);
  assert.ok(observed.length >= 10);
  subscription.unsubscribe();
});

test("Agent Loop input controls the virtual tool chain", () => {
  const input = "读取 src/config.ts，搜索 port，把 8080 改成 9090，然后运行测试";
  const built = trace(agentLoopScenario, input, {
    permission: "allow",
    testResult: "pass",
  });
  const tools = built.steps.filter((step) => step.kind === "tool_use").map((step) => step.tool);
  assert.deepEqual(tools, ["Read", "Grep", "Edit", "Bash"]);
  assert.match(finalFiles(agentLoopScenario, input, { permission: "allow", testResult: "pass" })["src/config.ts"], /9090/);
  assertToolPairs(agentLoopScenario, input, { permission: "allow", testResult: "pass" });
});

test("Agent Loop keeps tool schemas stable and introduces each tool in a model iteration", () => {
  const full = trace(
    agentLoopScenario,
    "读取 src/config.ts，搜索 port，把 8080 改成 9090，然后运行测试",
    { permission: "allow", testResult: "pass" },
  );
  const readOnly = trace(agentLoopScenario, "读取 src/config.ts", {
    permission: "allow",
    testResult: "pass",
  });
  const requestSteps = full.steps.filter((step) => step.kind === "request");
  assert.equal(requestSteps.length, 5);
  for (const request of requestSteps) {
    assert.deepEqual(
      (request.input as { tools: string[] }).tools,
      ["Read", "Grep", "Edit", "Bash"],
    );
    assert.ok(
      !JSON.stringify(request.input).includes("current_virtual_files"),
      "virtual files must stay in client state, not model messages",
    );
  }
  assert.deepEqual(
    (readOnly.steps.find((step) => step.kind === "request")?.input as {
      tools: string[];
    }).tools,
    ["Read", "Grep", "Edit", "Bash"],
  );
  assert.deepEqual(
    (readOnly.steps.find((step) => step.kind === "request")?.output as {
      teaching_fixture_plan: string[];
    }).teaching_fixture_plan,
    ["Read"],
  );
  let latestRequest = -1;
  for (const [index, step] of full.steps.entries()) {
    if (step.kind === "request") latestRequest = index;
    if (step.kind === "tool_use") assert.ok(latestRequest >= 0 && latestRequest < index);
  }
});

test("Agent Loop sends full tool blocks and failure content in the next request", () => {
  const built = trace(
    agentLoopScenario,
    "读取 src/config.ts，把 8080 改成 9090，然后运行测试",
    { permission: "allow", testResult: "fail" },
  );
  const requests = built.steps.filter((step) => step.kind === "request");
  const finalMessages = JSON.stringify(requests.at(-1)?.input);
  assert.match(finalMessages, /"type":"tool_use"/);
  assert.match(finalMessages, /"type":"tool_result"/);
  assert.match(finalMessages, /1 test failed/);
  const messages = (requests.at(-1)?.input as {
    messages: Array<{ role: string; content: Array<Record<string, unknown>> | string }>;
  }).messages;
  const bashResult = messages
    .filter((message) => message.role === "user" && Array.isArray(message.content))
    .flatMap((message) => message.content as Array<Record<string, unknown>>)
    .find((block) => block.tool_use_id === "toolu_lab_03_bash");
  assert.equal(JSON.parse(String(bashResult?.content)).exit_code, 1);
});

test("Agent Loop terminal copy matches read, edit, test, and failure branches", () => {
  const controls = { permission: "allow", testResult: "pass" };
  const read = trace(agentLoopScenario, "读取 src/config.ts", controls).steps.at(-1);
  assert.match(String(read?.output), /读取完成/);
  assert.doesNotMatch(String(read?.output), /配置修改完成|测试通过/);

  const edit = trace(
    agentLoopScenario,
    "读取 src/config.ts，把 8080 改成 9090",
    controls,
  ).steps.at(-1);
  assert.match(String(edit?.output), /配置修改完成/);
  assert.match(String(edit?.output), /未运行测试/);

  const test = trace(
    agentLoopScenario,
    "读取 src/config.ts，然后运行测试",
    controls,
  ).steps.at(-1);
  assert.match(String(test?.output), /测试通过/);
  assert.match(String(test?.output), /没有修改文件/);

  const failedTestOnly = trace(
    agentLoopScenario,
    "读取 src/config.ts，然后运行测试",
    { permission: "allow", testResult: "fail" },
  ).steps.at(-1);
  assert.match(String(failedTestOnly?.summary), /没有文件修改需要回滚/);
});

test("Agent Loop rejects no-op and ambiguous Edit values", () => {
  assert.throws(
    () =>
      agentLoopScenario.buildTrace(
        "读取 src/config.ts，把 8080 改成 8080",
        { permission: "allow", testResult: "pass" },
      ),
    /旧值和新值相同/,
  );
  assert.throws(
    () =>
      agentLoopScenario.buildTrace(
        "读取 src/config.ts，把 30 改成 31",
        { permission: "allow", testResult: "pass" },
      ),
    /唯一出现.*2 次/,
  );
});

test("Agent Loop permission denial prevents the edit side effect", () => {
  const input = "读取 src/config.ts，把 8080 改成 9090，然后运行测试";
  const built = trace(agentLoopScenario, input, {
    permission: "deny",
    testResult: "pass",
  });
  assert.ok(built.steps.some((step) => step.kind === "denied"));
  assert.doesNotMatch(finalFiles(agentLoopScenario, input, { permission: "deny", testResult: "pass" })["src/config.ts"], /9090/);
  assertToolPairs(agentLoopScenario, input, { permission: "deny", testResult: "pass" });
});

test("Agent Loop test failure preserves the completed edit", () => {
  const input = "读取 src/config.ts，把 8080 改成 9091，然后运行测试";
  const built = trace(agentLoopScenario, input, {
    permission: "allow",
    testResult: "fail",
  });
  assert.match(finalFiles(agentLoopScenario, input, { permission: "allow", testResult: "fail" })["src/config.ts"], /9091/);
  assert.ok(built.steps.some((step) => step.tool === "Bash" && step.status === "failed"));
  assertToolPairs(agentLoopScenario, input, { permission: "allow", testResult: "fail" });
});

test("Compact normal path creates a boundary while PreCompact block does not", () => {
  const input = "/compact 保留当前 Summary、文件附件和 Resume 要求";
  const normal = trace(compactScenario, input, {
    historyGroups: 9,
    preservedGroups: 2,
    attachmentRecovery: "exact",
    preCompact: "allow",
  });
  const blocked = trace(compactScenario, input, {
    historyGroups: 9,
    preservedGroups: 2,
    attachmentRecovery: "exact",
    preCompact: "block",
  });
  assert.ok(normal.steps.some((step) => step.visualTarget === "boundary"));
  assert.ok(!blocked.steps.some((step) => step.visualTarget === "boundary"));
  assert.ok(blocked.steps.some((step) => step.kind === "denied"));
});

test("Compact preserves legal tool groups for every control combination", () => {
  assertCompactPreservesToolPairs(6, 1);
  assertCompactPreservesToolPairs(9, 2);
  assertCompactPreservesToolPairs(12, 3);
});

test("Compact emits the 2.1.235 boundary metadata shape", () => {
  const built = compactFixture(9, 2);
  const boundary = built.steps.find(
    (step) => step.id === "write-boundary",
  );
  assert.ok(boundary);
  const output = boundary.output as Record<string, unknown>;
  assert.equal(output.type, "system");
  assert.equal(output.subtype, "compact_boundary");
  assert.ok(output.compact_metadata);
  assert.ok(!("trigger" in output));
  const metadata = output.compact_metadata as Record<string, unknown>;
  assert.equal(metadata.trigger, "manual");
  assert.ok(metadata.preserved_messages && !Array.isArray(metadata.preserved_messages));
  assert.ok(metadata.preserved_segment && !Array.isArray(metadata.preserved_segment));
  assert.ok(!("messages_summarized" in metadata));
  const rebuilt = built.steps.find(
    (step) => step.id === "rebuild-context",
  )?.output as {
    summary_message: {
      type: string;
      uuid: string;
      message: { role: string; content: string };
    };
  };
  assert.equal(rebuilt.summary_message.type, "user");
  assert.equal(rebuilt.summary_message.message.role, "user");
  assert.match(
    rebuilt.summary_message.message.content,
    /^This session is being continued/,
  );
  assert.match(rebuilt.summary_message.message.content, /\nSummary:\n/);
  assert.equal(
    (metadata.preserved_messages as { anchor_uuid: string }).anchor_uuid,
    rebuilt.summary_message.uuid,
  );
  const finalTranscript = built.steps.at(-1)?.files?.["/session/transcript.jsonl"] ?? "";
  const finalRecords = finalTranscript
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { uuid?: string });
  const uuids = new Set(finalRecords.map((record) => record.uuid).filter(Boolean));
  const preservedSegment = metadata.preserved_segment as {
    head_uuid: string;
    anchor_uuid: string;
    tail_uuid: string;
  };
  assert.ok(uuids.has(preservedSegment.head_uuid));
  assert.ok(uuids.has(preservedSegment.anchor_uuid));
  assert.ok(uuids.has(preservedSegment.tail_uuid));
});

test("Compact keeps command instructions out of prior history and awaits a new user turn", () => {
  const input = "/compact 重点保留附件与 Resume";
  const built = compactFixture(9, 2, input);
  assert.doesNotMatch(built.initialFiles?.["/session/transcript.jsonl"] ?? "", /重点保留附件与 Resume/);
  const summaryGeneration = built.steps.find(
    (step) => step.id === "summary-generation",
  );
  assert.doesNotMatch(String(summaryGeneration?.output), /<summary>Summary:/);
  const next = built.steps.find((step) => step.id === "next-request");
  const nextInput = next?.input as {
    compact_custom_instructions: string;
    next_user_input: string;
  };
  assert.equal(nextInput.compact_custom_instructions, "重点保留附件与 Resume");
  assert.equal(nextInput.next_user_input, "not yet supplied");
});

test("Compact dispatches PostCompact after attachment restoration", () => {
  const built = compactFixture(9, 2);
  const restoreIndex = built.steps.findIndex(
    (step) => step.id === "restore-attachments",
  );
  const hookIndex = built.steps.findIndex(
    (step) => step.id === "post-compact-hook",
  );
  const boundaryIndex = built.steps.findIndex(
    (step) => step.id === "write-boundary",
  );
  assert.ok(restoreIndex >= 0 && hookIndex > restoreIndex && boundaryIndex > hookIndex);
});

test("Compact restores only existing normalized virtual attachments", () => {
  const existingAbsolute = compactFixture(
    9,
    2,
    "/compact 保留 /workspace/analysis-notes.md",
  ).steps.find((step) => step.id === "restore-attachments")?.output as {
    restored: string[];
    failed: string[];
  };
  assert.deepEqual(existingAbsolute.restored, ["/workspace/analysis-notes.md"]);
  assert.deepEqual(existingAbsolute.failed, []);

  const existingRelative = compactFixture(
    9,
    2,
    "/compact 保留 reverse/javascript/cli.readable.js",
  ).steps.find((step) => step.id === "restore-attachments")?.output as {
    restored: string[];
    failed: string[];
  };
  assert.deepEqual(existingRelative.restored, [
    "/workspace/reverse/javascript/cli.readable.js",
  ]);

  const missingBare = compactFixture(9, 2, "/compact 保留 README.md").steps.find(
    (step) => step.id === "restore-attachments",
  )?.output as { restored: string[]; failed: string[] };
  assert.deepEqual(missingBare.restored, []);
  assert.deepEqual(missingBare.failed, ["/workspace/README.md"]);
});

test("Permission scope, sandbox, and disk drift produce distinct outcomes", () => {
  const input = "把 /workspace/project/config.json 的端口从 8080 改成 9090";
  const success = trace(permissionsScenario, input, {
    approval: "once",
    preToolUse: "rewrite",
    toolSurface: "edit",
    sandbox: "allow",
    diskDrift: false,
  });
  const sandboxDenied = trace(permissionsScenario, input, {
    approval: "session",
    preToolUse: "unchanged",
    toolSurface: "bash",
    sandbox: "block",
    diskDrift: false,
  });
  const drift = trace(permissionsScenario, input, {
    approval: "once",
    preToolUse: "unchanged",
    toolSurface: "edit",
    sandbox: "allow",
    diskDrift: true,
  });
  assert.match(success.steps.at(-1)?.output ? JSON.stringify(success.steps.at(-1)?.output) : "", /successfully/);
  assert.ok(sandboxDenied.steps.some((step) => step.kind === "denied" || step.status === "denied"));
  assert.ok(drift.steps.some((step) => step.status === "failed"));
  assertToolPairs(permissionsScenario, input, {
    approval: "once",
    preToolUse: "rewrite",
    toolSurface: "edit",
    sandbox: "allow",
    diskDrift: false,
  });
});

test("Permission input requires an explicit old/new pair and seeds that old value", () => {
  const chinese = trace(
    permissionsScenario,
    "把 /workspace/project/config.json 的端口从 3000 更新为 9090",
    {
      approval: "once",
      preToolUse: "unchanged",
      toolSurface: "edit",
      sandbox: "allow",
      diskDrift: false,
    },
  );
  assert.match(chinese.steps.at(-1)?.files?.["/workspace/project/config.json"] ?? "", /9090/);
  assert.doesNotMatch(chinese.steps.at(-1)?.files?.["/workspace/project/config.json"] ?? "", /3000/);

  const english = trace(
    permissionsScenario,
    "change /workspace/project/config.json from 4000 to 4100",
    {
      approval: "once",
      preToolUse: "unchanged",
      toolSurface: "edit",
      sandbox: "allow",
      diskDrift: false,
    },
  );
  assert.match(english.steps.at(-1)?.files?.["/workspace/project/config.json"] ?? "", /4100/);

  assert.throws(
    () =>
      permissionsScenario.buildTrace(
        "把 /workspace/project/config.json 的端口更新为 9090",
        {
          approval: "once",
          preToolUse: "unchanged",
          toolSurface: "edit",
          sandbox: "allow",
          diskDrift: false,
        },
      ),
    /明确的旧值和新值/,
  );
  assert.throws(
    () =>
      permissionsScenario.buildTrace(
        "把 /workspace/project/config.json 的端口从 8080 改成 8080",
        {
          approval: "once",
          preToolUse: "unchanged",
          toolSurface: "edit",
          sandbox: "allow",
          diskDrift: false,
        },
      ),
    /旧值和新值相同/,
  );
  assert.throws(
    () =>
      permissionsScenario.buildTrace(
        "把 /workspace/project/config.json 从 o 改成 x",
        {
          approval: "once",
          preToolUse: "unchanged",
          toolSurface: "edit",
          sandbox: "allow",
          diskDrift: false,
        },
      ),
    /唯一出现/,
  );
});

test("Sandbox failures dispatch PostToolUseFailure before the paired result", () => {
  const built = trace(
    permissionsScenario,
    "把 /workspace/project/config.json 的端口从 8080 改成 9090",
    {
      approval: "session",
      preToolUse: "unchanged",
      toolSurface: "bash",
      sandbox: "block",
      diskDrift: false,
    },
  );
  const hookIndex = built.steps.findIndex(
    (step) => step.id === "permission-sandbox-post-failure",
  );
  const resultIndex = built.steps.findIndex(
    (step) => step.id === "permission-sandbox-result",
  );
  assert.ok(hookIndex >= 0 && resultIndex > hookIndex);
  assertToolPairs(permissionsScenario, "把 /workspace/project/config.json 的端口从 8080 改成 9090", {
    approval: "session",
    preToolUse: "unchanged",
    toolSurface: "bash",
    sandbox: "block",
    diskDrift: false,
  });
});

test("Disk drift never impersonates the requested replacement value", () => {
  const built = trace(
    permissionsScenario,
    "把 /workspace/project/config.json 的端口从 4321 改成 4322",
    {
      approval: "once",
      preToolUse: "unchanged",
      toolSurface: "edit",
      sandbox: "allow",
      diskDrift: true,
    },
  );
  const content =
    built.steps.at(-1)?.files?.["/workspace/project/config.json"] ?? "";
  assert.match(content, /4323/);
  assert.doesNotMatch(content, /4322/);
});
