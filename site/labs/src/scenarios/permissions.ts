import { registerLabScenario } from "../runtime/registry";
import type {
  LabActor,
  LabControlValues,
  LabEvidence,
  LabFileMap,
  LabScenario,
  LabStep,
} from "../runtime/types";

const REPOSITORY =
  "https://github.com/SwallOwDili/claudecodecli-sourcecode/blob/2.1.235";

const DEFAULT_INPUT =
  "把 /workspace/project/config.json 的端口从 8080 改成 9090";

const DEFAULT_FILES: LabFileMap = {
  "/workspace/project/config.json": '{"port": 8080, "mode": "production"}\n',
  "/workspace/project/config.staging.json": '{"port": 8080, "mode": "staging"}\n',
};

interface PermissionRequest {
  raw: string;
  path: string;
  oldValue: string;
  newValue: string;
  stagingPath: string;
}

function evidence(
  owner: string,
  type: "Static source" | "Exact-binary probe" | "Explanatory fixture",
  href: string,
  detail: string,
): LabEvidence {
  return {
    label: type,
    href,
    detail: `evidence_owner=${owner}; ${detail}`,
  };
}

const PIPELINE_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    "client orchestrator",
    "Static source",
    `${REPOSITORY}/reverse/javascript/cli.readable.js#L316092-L316487`,
    "generic tool lookup, validation, hooks, permission, call, and result mapping",
  );

const SANDBOX_PROBE_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    "client sandbox runtime",
    "Exact-binary probe",
    `${REPOSITORY}/analysis/runtime-probes/sandbox-enforcement.json`,
    "Bash write denial remains effective after interactive permission is bypassed",
  );

const CONTROL_FIXTURE_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    `teaching fixture/${actor}`,
    "Explanatory fixture",
    "#先亲自走一遍控制管线",
    "the selected control value, virtual file state, hook match count, and generated result text belong to this browser fixture",
  );

function stringControl(
  controls: LabControlValues,
  id: string,
  fallback: string,
): string {
  const value = controls[id];
  return typeof value === "string" && value ? value : fallback;
}

function booleanControl(
  controls: LabControlValues,
  id: string,
  fallback: boolean,
): boolean {
  const value = controls[id];
  return typeof value === "boolean" ? value : fallback;
}

function cleanValue(value: string): string {
  return value.replace(/^["'`]+|["'`，。；;]+$/g, "").trim();
}

function stagingPathFor(path: string): string {
  const extension = path.match(/(\.[^./]+)$/)?.[1];
  return extension
    ? `${path.slice(0, -extension.length)}.staging${extension}`
    : `${path}.staging`;
}

function parsePermissionInput(input: string): PermissionRequest {
  const raw = input.trim() || DEFAULT_INPUT;
  const path =
    raw.match(/\/(?:[A-Za-z0-9_.-]+\/)*[A-Za-z0-9_.-]+/)?.[0] ??
    "/workspace/project/config.json";
  const token = "[A-Za-z0-9_.:-]+";
  const explicitChange = [
    new RegExp(
      `(?:从|把|将)\\s*["'\`]?(${token})["'\`]?\\s*(?:改成|改为|替换为|变成|修改为|更新为)\\s*["'\`]?(${token})["'\`]?`,
      "iu",
    ),
    new RegExp(
      `\\bfrom\\s+["'\`]?(${token})["'\`]?\\s+(?:to|with)\\s+["'\`]?(${token})["'\`]?`,
      "iu",
    ),
    new RegExp(
      `\\b(?:change|replace|update)\\s+["'\`]?(${token})["'\`]?\\s+(?:to|with)\\s+["'\`]?(${token})["'\`]?`,
      "iu",
    ),
    new RegExp(
      `["'\`]?(${token})["'\`]?\\s*(?:->|=>)\\s*["'\`]?(${token})["'\`]?`,
      "iu",
    ),
  ].map((pattern) => raw.match(pattern)).find(Boolean);
  if (!explicitChange) {
    throw new Error(
      "没有找到明确的旧值和新值。请使用“从 OLD 改成 NEW”或“change OLD to NEW”。",
    );
  }
  const oldValue = cleanValue(explicitChange[1]);
  const newValue = cleanValue(explicitChange[2]);
  if (oldValue === newValue) {
    throw new Error("修改操作的旧值和新值相同；目标版本会在执行前拒绝这个输入。");
  }

  return {
    raw,
    path,
    oldValue,
    newValue,
    stagingPath: stagingPathFor(path),
  };
}

function initialContent(path: string, value: string, mode: string): string {
  if (path.endsWith(".json")) {
    const parsed = Number(value);
    const serialized = Number.isFinite(parsed) ? String(parsed) : JSON.stringify(value);
    return `{"port": ${serialized}, "mode": "${mode}"}\n`;
  }
  return `value=${value}\nmode=${mode}\n`;
}

function replaceFirst(content: string, oldValue: string, newValue: string): string | null {
  const index = content.indexOf(oldValue);
  if (index < 0) return null;
  return `${content.slice(0, index)}${newValue}${content.slice(index + oldValue.length)}`;
}

function occurrenceCount(source: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let offset = 0;
  while ((offset = source.indexOf(needle, offset)) >= 0) {
    count++;
    offset += needle.length;
  }
  return count;
}

function driftValue(value: string, requestedValue: string): string {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const first = String(numeric + 1);
    return first === requestedValue ? String(numeric + 2) : first;
  }
  const first = `external-${value}`;
  return first === requestedValue ? `${first}-drift` : first;
}

function unifiedDiff(path: string, before: string, after: string): string {
  const beforeLines = before.trimEnd().split("\n");
  const afterLines = after.trimEnd().split("\n");
  return [
    `--- a${path}`,
    `+++ b${path}`,
    `@@ -1,${beforeLines.length} +1,${afterLines.length} @@`,
    ...beforeLines.map((line) => `-${line}`),
    ...afterLines.map((line) => `+${line}`),
  ].join("\n");
}

function toolInput(
  toolSurface: string,
  path: string,
  oldValue: string,
  newValue: string,
): Record<string, unknown> {
  if (toolSurface === "bash") {
    return {
      command: `replace-exact --path ${JSON.stringify(path)} --old ${JSON.stringify(
        oldValue,
      )} --new ${JSON.stringify(newValue)}`,
      virtual_executor: true,
    };
  }
  return {
    file_path: path,
    old_string: oldValue,
    new_string: newValue,
    replace_all: false,
  };
}

function pairedErrorResult(
  toolUseId: string,
  content: string,
  source: string,
): Record<string, unknown> {
  return {
    wireBlock: {
      type: "tool_result",
      tool_use_id: toolUseId,
      is_error: true,
      content,
    },
    clientMetadata: {
      decision_source: source,
    },
  };
}

function buildPermissionsTrace(
  input: string,
  controls: LabControlValues,
): { parsed: unknown; steps: LabStep[]; initialFiles: LabFileMap; notes: string[] } {
  if (
    !/(?:改成|改为|替换为|变成|修改为|更新为|\bchange\b|\breplace\b|\bupdate\b)/iu.test(
      input,
    )
  ) {
    throw new Error(
      "没有识别到文件修改。请提供路径，并说明旧值要改成什么新值。",
    );
  }
  const request = parsePermissionInput(input);
  const approval = stringControl(controls, "approval", "once");
  const preToolUse = stringControl(controls, "preToolUse", "unchanged");
  const toolSurface = stringControl(controls, "toolSurface", "edit");
  const sandbox = stringControl(controls, "sandbox", "allow");
  const diskDrift = booleanControl(controls, "diskDrift", false);
  const tool = toolSurface === "bash" ? "Bash" : "Edit";
  const toolUseId = "toolu-permission-lab-01";
  const initialFiles: LabFileMap = {
    ...DEFAULT_FILES,
    [request.path]: initialContent(request.path, request.oldValue, "production"),
    [request.stagingPath]: initialContent(
      request.stagingPath,
      request.oldValue,
      "staging",
    ),
  };
  const originalMatches = occurrenceCount(
    initialFiles[request.path],
    request.oldValue,
  );
  if (originalMatches !== 1) {
    throw new Error(
      `${tool} 的旧值必须在原目标文件中唯一出现；当前夹具找到 ${originalMatches} 次。请提供更精确的旧值。`,
    );
  }
  const effectivePath = preToolUse === "rewrite" ? request.stagingPath : request.path;
  const originalInput = toolInput(
    toolSurface,
    request.path,
    request.oldValue,
    request.newValue,
  );
  const effectiveInput = toolInput(
    toolSurface,
    effectivePath,
    request.oldValue,
    request.newValue,
  );
  const steps: LabStep[] = [
    {
      id: "permission-user-input",
      title: "用户提出有副作用的修改",
      actor: "user",
      kind: "input",
      summary: request.raw,
      input: request,
      evidence: [
        evidence(
          "user",
          "Explanatory fixture",
          "#从一次真实文件改写看完整链路",
          "the entered path and replacement values drive this local teaching trace",
        ),
      ],
      visualTarget: "call",
      status: "success",
    },
    {
      id: "permission-tool-use",
      title: `模型发出 ${tool} tool_use`,
      actor: "model",
      kind: "tool_use",
      summary: `tool_use.id=${toolUseId}，目标是 ${request.path}。`,
      tool,
      tool_use_id: toolUseId,
      input: originalInput,
      evidence: [
        PIPELINE_EVIDENCE("client"),
        evidence(
          "model",
          "Explanatory fixture",
          "#先亲自走一遍控制管线",
          "the specific tool choice and entered arguments are generated by the teaching fixture",
        ),
      ],
      visualTarget: "call",
      status: "success",
    },
    {
      id: "permission-validate",
      title: "客户端校验原始输入",
      actor: "client",
      kind: "assemble",
      summary: `${tool} schema 和原始语义检查通过；这一步不等于权限已经允许。`,
      before: originalInput,
      after: {
        canonical_tool: tool,
        schema: "valid",
        custom_validate_input: "completed for original input",
      },
      evidence: [PIPELINE_EVIDENCE("client")],
      visualTarget: "validate",
      status: "success",
    },
    {
      id: "permission-pre-tool-use",
      title: "PreToolUse 观察或改写输入",
      actor: "hook",
      kind: "hook",
      summary:
        preToolUse === "rewrite"
          ? `Hook 把目标从 ${request.path} 改为 ${request.stagingPath}。`
          : "Hook 保留模型给出的目标。",
      before: originalInput,
      after: effectiveInput,
      effects: [
        {
          label:
            preToolUse === "rewrite"
              ? "updatedInput 重新进入 schema 与 permission 语义复验"
              : "原输入继续进入 permission",
          state: "applied",
          reversible: true,
        },
      ],
      evidence: [
        PIPELINE_EVIDENCE("hook"),
        CONTROL_FIXTURE_EVIDENCE("hook"),
        evidence(
          "hook",
          "Static source",
          `${REPOSITORY}/analysis/tools-permissions-hooks.md#pretooluse动作前的可编程控制点`,
          "updatedInput is structurally revalidated; generic code does not rerun custom validateInput",
        ),
      ],
      visualTarget: "pre",
      status: "success",
    },
  ];

  let filesAfterPermission = { ...initialFiles };

  if (approval === "deny") {
    const result = pairedErrorResult(
      toolUseId,
      `Permission denied before ${tool}. No file was modified.`,
      "user/permission",
    );
    steps.push(
      {
        id: "permission-decision-deny",
        title: "权限拒绝本次调用",
        actor: "permission",
        kind: "permission",
        summary: "拒绝发生在 tool.call 之前，磁盘状态保持不变。",
        tool,
        tool_use_id: toolUseId,
        input: effectiveInput,
        output: {
          behavior: "deny",
          scope: "this tool_use",
          checked_path: effectivePath,
        },
        files: filesAfterPermission,
        effects: [
          {
            label: "阻止工具副作用",
            state: "blocked",
            reversible: true,
          },
        ],
        evidence: [
          PIPELINE_EVIDENCE("permission"),
          CONTROL_FIXTURE_EVIDENCE("permission"),
        ],
        visualTarget: "permission",
        status: "denied",
      },
      {
        id: "permission-denied-result",
        title: "生成配对 error tool_result",
        actor: "client",
        kind: "tool_result",
        summary: "Agent Loop 收到拒绝原因，可以改计划；会话不因单次拒绝自动崩溃。",
        tool,
        tool_use_id: toolUseId,
        output: result,
        files: filesAfterPermission,
        evidence: [
          PIPELINE_EVIDENCE("client"),
          CONTROL_FIXTURE_EVIDENCE("client"),
        ],
        visualTarget: "result",
        status: "denied",
      },
    );

    return {
      parsed: {
        request,
        approval,
        preToolUse,
        toolSurface,
        sandbox,
        diskDrift,
        effectivePath,
      },
      steps,
      initialFiles,
      notes: [
        "这是客户端控制链教学夹具；动态路径、diff 和错误文本不是新采集的 Claude Code wire dump。",
        "permission deny 阻止的是本次 tool.call，不是阻止 Agent Loop 继续处理配对结果。",
      ],
    };
  }

  if (approval === "session") {
    filesAfterPermission = {
      ...filesAfterPermission,
      "/session/permission-rules.json": `${JSON.stringify(
        {
          tool,
          path: effectivePath,
          behavior: "allow",
          scope: "session fixture",
        },
        null,
        2,
      )}\n`,
    };
  }

  steps.push({
    id: "permission-decision-allow",
    title: approval === "session" ? "本会话允许同类调用" : "仅允许本次调用",
    actor: "permission",
    kind: "permission",
    summary:
      approval === "session"
        ? `当前 session 为 ${tool} + ${effectivePath} 建立允许规则。`
        : `允许只绑定 ${toolUseId}，下一次同类调用仍需重新裁决。`,
    tool,
    tool_use_id: toolUseId,
    input: effectiveInput,
    output: {
      behavior: "allow",
      scope: approval === "session" ? "session" : "once",
      checked_path: effectivePath,
      updatedInput: effectiveInput,
      schema_revalidation: "valid",
      custom_validate_input_rerun: false,
    },
    files: filesAfterPermission,
    effects: [
      {
          label:
            approval === "session"
              ? "记录本沙盘 session 允许规则"
              : "只放行当前 tool_use_id",
          state: "applied",
          reversible: approval !== "session",
      },
    ],
    evidence: [
      PIPELINE_EVIDENCE("permission"),
      CONTROL_FIXTURE_EVIDENCE("permission"),
    ],
    visualTarget: "permission",
    status: "success",
  });

  const sandboxApplies = toolSurface === "bash";
  const sandboxBlocks = sandboxApplies && sandbox === "block";
  steps.push({
    id: "permission-sandbox",
    title: sandboxApplies ? "Bash 进入 sandbox 边界" : "Edit 不启动 OS 命令 sandbox",
    actor: "client",
    kind: "execute",
    summary: sandboxApplies
      ? sandboxBlocks
        ? "permission 已允许，但 filesystem sandbox 拒绝目标写入。"
        : "permission 已允许，sandbox 也允许该虚拟工作区写入。"
      : "Edit 直接进入文件工具实现；本次 sandbox 选项不伪装成 Bash wrapper。",
    input: {
      tool,
      path: effectivePath,
      sandbox_control: sandbox,
      applies: sandboxApplies,
    },
    output: {
      decision: sandboxApplies ? (sandboxBlocks ? "deny" : "allow") : "not-applicable",
    },
    files: filesAfterPermission,
    effects: [
      {
        label: sandboxBlocks
          ? "阻止 Bash 写入"
          : sandboxApplies
            ? "允许 Bash 进入虚拟执行器"
            : "保持 Edit 自身文件保护路径",
        state: sandboxBlocks ? "blocked" : "applied",
        reversible: true,
      },
    ],
    evidence: [
      sandboxApplies
        ? SANDBOX_PROBE_EVIDENCE("client")
        : PIPELINE_EVIDENCE("client"),
      CONTROL_FIXTURE_EVIDENCE("client"),
    ],
    visualTarget: "sandbox",
    status: sandboxBlocks ? "denied" : "success",
  });

  if (sandboxBlocks) {
    steps.push(
      {
        id: "permission-sandbox-post-failure",
        title: "PostToolUseFailure 接收 sandbox 失败",
        actor: "hook",
        kind: "hook",
        summary:
          "tool.call 失败后仍进入失败 Hook dispatch；本夹具没有匹配 Hook，因此不追加 additionalContext。",
        tool,
        tool_use_id: toolUseId,
        input: {
          tool_input: effectiveInput,
          error_source: "sandbox",
        },
        output: {
          matching_hooks: 0,
          additionalContext: null,
        },
        files: filesAfterPermission,
        evidence: [
          PIPELINE_EVIDENCE("hook"),
          CONTROL_FIXTURE_EVIDENCE("hook"),
        ],
        visualTarget: "post",
        status: "failed",
      },
      {
        id: "permission-sandbox-result",
        title: "sandbox 生成 error tool_result",
        actor: "client",
        kind: "tool_result",
        summary: "permission allow 没有覆盖 filesystem sandbox；目标文件仍未改变。",
        tool,
        tool_use_id: toolUseId,
        output: pairedErrorResult(
          toolUseId,
          `Sandbox denied write access to ${effectivePath}. No file was modified.`,
          "sandbox",
        ),
        files: filesAfterPermission,
        evidence: [
          SANDBOX_PROBE_EVIDENCE("client"),
          PIPELINE_EVIDENCE("client"),
          CONTROL_FIXTURE_EVIDENCE("client"),
        ],
        visualTarget: "result",
        status: "denied",
      },
    );

    return {
      parsed: {
        request,
        approval,
        preToolUse,
        toolSurface,
        sandbox,
        diskDrift,
        effectivePath,
      },
      steps,
      initialFiles,
      notes: [
        "这是客户端控制链教学夹具；动态路径、diff 和错误文本不是新采集的 Claude Code wire dump。",
        "sandbox 只在 Bash surface 中执行；Edit 不被伪装成经过相同 OS command wrapper。",
      ],
    };
  }

  let filesBeforeCall = { ...filesAfterPermission };
  const contentBeforeDrift = filesBeforeCall[effectivePath] ??
    initialContent(effectivePath, request.oldValue, preToolUse === "rewrite" ? "staging" : "production");

  if (diskDrift) {
    const drifted = replaceFirst(
      contentBeforeDrift,
      request.oldValue,
      driftValue(request.oldValue, request.newValue),
    ) ??
      `${contentBeforeDrift.trimEnd()}\nexternal_change=true\n`;
    filesBeforeCall = {
      ...filesBeforeCall,
      [effectivePath]: drifted,
    };
    steps.push({
      id: "permission-disk-drift",
      title: "外部进程在执行前改变磁盘",
      actor: "external",
      kind: "execute",
      summary: `${effectivePath} 已不再包含经过校验时看到的精确旧值 ${request.oldValue}。`,
      before: contentBeforeDrift,
      after: drifted,
      files: filesBeforeCall,
      effects: [
        {
          label: "制造 validation 与 tool.call 之间的状态漂移",
          state: "applied",
          reversible: false,
        },
      ],
      evidence: [
        evidence(
          "external",
          "Explanatory fixture",
          "#第七步真正写文件时再次遇到当前磁盘状态",
          "disk drift is injected by the lab so tool.call must observe current state",
        ),
      ],
      visualTarget: "execute",
      status: "success",
    });
  }

  const contentAtCall = filesBeforeCall[effectivePath] ?? contentBeforeDrift;
  const contentAfterCall = replaceFirst(contentAtCall, request.oldValue, request.newValue);

  if (contentAfterCall === null) {
    const errorResult = pairedErrorResult(
      toolUseId,
      `The expected old value ${JSON.stringify(
        request.oldValue,
      )} is no longer present in ${effectivePath}. No tool write was applied.`,
      "tool.call/current-disk-state",
    );
    steps.push(
      {
        id: "permission-execute-stale",
        title: `${tool} 读取当前磁盘后失败`,
        actor: "tool",
        kind: "execute",
        summary: "较早 schema 和 permission 都通过，但当前文件已漂移，精确替换不能继续。",
        tool,
        tool_use_id: toolUseId,
        input: effectiveInput,
        before: contentAtCall,
        after: contentAtCall,
        output: {
          error: "expected old value not found",
          write_applied: false,
        },
        files: filesBeforeCall,
        effects: [
          {
            label: "拒绝基于陈旧内容写入",
            state: "failed",
            reversible: true,
          },
        ],
        evidence: [PIPELINE_EVIDENCE("tool")],
        visualTarget: "execute",
        status: "failed",
      },
      {
        id: "permission-post-failure",
        title: "PostToolUseFailure 观察失败",
        actor: "hook",
        kind: "hook",
        summary: "后置失败 Hook 可以补充诊断，但不能把未发生的写入伪装成成功。",
        tool,
        tool_use_id: toolUseId,
        input: effectiveInput,
        output: {
          additionalContext: "文件在审批后发生变化；重新读取后再生成新的工具调用。",
        },
        files: filesBeforeCall,
        evidence: [
          PIPELINE_EVIDENCE("hook"),
          CONTROL_FIXTURE_EVIDENCE("hook"),
        ],
        visualTarget: "post",
        status: "failed",
      },
      {
        id: "permission-stale-result",
        title: "同 ID error tool_result 回到 Agent Loop",
        actor: "client",
        kind: "tool_result",
        summary: "模型得到当前状态失败原因，可以重新 Read 后再决定。",
        tool,
        tool_use_id: toolUseId,
        output: errorResult,
        files: filesBeforeCall,
        evidence: [
          PIPELINE_EVIDENCE("client"),
          CONTROL_FIXTURE_EVIDENCE("client"),
        ],
        visualTarget: "result",
        status: "failed",
      },
    );

    return {
      parsed: {
        request,
        approval,
        preToolUse,
        toolSurface,
        sandbox,
        diskDrift,
        effectivePath,
      },
      steps,
      initialFiles,
      notes: [
        "这是客户端控制链教学夹具；动态路径、diff 和错误文本不是新采集的 Claude Code wire dump。",
        "permission 的 updatedInput 通过复验，不代表 tool.call 可以忽略执行时的当前磁盘状态。",
      ],
    };
  }

  const filesAfterCall: LabFileMap = {
    ...filesBeforeCall,
    [effectivePath]: contentAfterCall,
  };
  const diff = unifiedDiff(effectivePath, contentAtCall, contentAfterCall);
  steps.push(
    {
      id: "permission-execute-success",
      title: `${tool} 应用虚拟文件修改`,
      actor: "tool",
      kind: "execute",
      summary: `只有 ${effectivePath} 发生变化；原始 production/staging 另一份文件保持不变。`,
      tool,
      tool_use_id: toolUseId,
      input: effectiveInput,
      before: contentAtCall,
      after: contentAfterCall,
      output: {
        filePath: effectivePath,
        oldString: request.oldValue,
        newString: request.newValue,
        fixtureUnifiedDiff: diff,
      },
      files: filesAfterCall,
      effects: [
        {
          label: `写入 ${effectivePath}`,
          state: "applied",
          reversible: false,
        },
      ],
      evidence: [
        PIPELINE_EVIDENCE("tool"),
        evidence(
          "tool",
          "Explanatory fixture",
          "#第七步真正写文件时再次遇到当前磁盘状态",
          "the displayed diff is generated from the lab virtual file system",
        ),
      ],
      visualTarget: "execute",
      status: "success",
    },
    {
      id: "permission-post-success",
      title: "PostToolUse 检查成功输出",
      actor: "hook",
      kind: "hook",
      summary: "Hook 观察最终输入和输出；它只能影响后续消息，不能自动撤销已经应用的字节变化。",
      tool,
      tool_use_id: toolUseId,
      input: effectiveInput,
      output: {
        hook_dispatch: "completed",
        matching_hooks: 0,
        additionalContext: null,
      },
      files: filesAfterCall,
      evidence: [
        PIPELINE_EVIDENCE("hook"),
        CONTROL_FIXTURE_EVIDENCE("hook"),
      ],
      visualTarget: "post",
      status: "success",
    },
    {
      id: "permission-success-result",
      title: "同 ID tool_result 回到 Agent Loop",
      actor: "client",
      kind: "tool_result",
      summary: `结果明确指出实际变化发生在 ${effectivePath}。`,
      tool,
      tool_use_id: toolUseId,
      output: {
        wireBlock: {
          type: "tool_result",
          tool_use_id: toolUseId,
          content: `Updated ${effectivePath} successfully.`,
          is_error: false,
        },
        clientMetadata: {
          fixtureUnifiedDiff: diff,
        },
      },
      files: filesAfterCall,
      evidence: [
        PIPELINE_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "result",
      status: "success",
    },
  );

  return {
    parsed: {
      request,
      approval,
      preToolUse,
      toolSurface,
      sandbox,
      diskDrift,
      effectivePath,
    },
    steps,
    initialFiles,
    notes: [
      "这是客户端控制链教学夹具；动态路径、diff 和错误文本不是新采集的 Claude Code wire dump。",
      "Bash 使用 allowlisted 虚拟 replace-exact 执行器；页面不会启动真实 shell。",
      "session allow 只存在于本沙盘当前 trace，不写入真实 Claude Code settings。",
    ],
  };
}

export const permissionsScenario: LabScenario = registerLabScenario({
  id: "permissions",
  title: "工具权限与副作用控制沙盘",
  description:
    "改变审批范围、PreToolUse 改写、工具 surface、sandbox 和磁盘漂移，观察虚拟 diff 或配对 error tool_result 怎样形成。",
  defaultInput: DEFAULT_INPUT,
  examples: [
    {
      label: "Hook 改到 staging 后单次允许",
      input: DEFAULT_INPUT,
      controls: {
        approval: "once",
        preToolUse: "rewrite",
        toolSurface: "edit",
        sandbox: "allow",
        diskDrift: false,
      },
    },
    {
      label: "会话允许，但 Bash 被 sandbox 拒绝",
      input: "把 /workspace/project/config.json 的端口从 8080 改成 9090",
      controls: {
        approval: "session",
        preToolUse: "unchanged",
        toolSurface: "bash",
        sandbox: "block",
        diskDrift: false,
      },
    },
    {
      label: "允许后发生磁盘漂移",
      input: "把 /workspace/project/config.json 的端口从 8080 改成 9090",
      controls: {
        approval: "once",
        preToolUse: "unchanged",
        toolSurface: "edit",
        sandbox: "allow",
        diskDrift: true,
      },
    },
    {
      label: "权限直接拒绝",
      input: "把 /workspace/project/config.json 的端口从 8080 改成 9090",
      controls: {
        approval: "deny",
        preToolUse: "rewrite",
        toolSurface: "edit",
        sandbox: "allow",
        diskDrift: false,
      },
    },
  ],
  initialFiles: DEFAULT_FILES,
  graph: {
    src: "../assets/visuals/tool-control-lifecycle.svg",
    label: "tool_use 经过校验、Hook、权限、sandbox、执行和结果回灌",
  },
  controls: [
    {
      id: "approval",
      label: "审批决定",
      type: "select",
      defaultValue: "once",
      options: [
        { value: "once", label: "仅允许本次" },
        { value: "session", label: "本会话允许" },
        { value: "deny", label: "拒绝" },
      ],
      description: "决定是否执行，以及允许范围是否延续到本沙盘 session。",
    },
    {
      id: "preToolUse",
      label: "PreToolUse",
      type: "select",
      defaultValue: "unchanged",
      options: [
        { value: "unchanged", label: "保持原目标" },
        { value: "rewrite", label: "改到 staging" },
      ],
      description: "改写后使用新路径重新做 schema 与 permission 语义复验。",
    },
    {
      id: "toolSurface",
      label: "执行工具",
      type: "select",
      defaultValue: "edit",
      options: [
        { value: "edit", label: "Edit 文件工具" },
        { value: "bash", label: "Bash 虚拟命令" },
      ],
      description: "只有 Bash surface 进入本沙盘的 OS/filesystem sandbox 分支。",
    },
    {
      id: "sandbox",
      label: "Bash sandbox",
      type: "select",
      defaultValue: "allow",
      options: [
        { value: "allow", label: "允许工作区写入" },
        { value: "block", label: "拒绝目标写入" },
      ],
      description: "permission allow 不会覆盖独立的 sandbox 决定。",
    },
    {
      id: "diskDrift",
      label: "执行前磁盘漂移",
      type: "toggle",
      defaultValue: false,
      description: "模拟审批后、tool.call 前文件被外部进程改变。",
    },
  ],
  buildTrace: buildPermissionsTrace,
});

export default permissionsScenario;
