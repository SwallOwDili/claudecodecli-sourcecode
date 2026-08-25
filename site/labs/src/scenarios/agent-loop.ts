import { registerLabScenario } from "../runtime/registry";
import type {
  LabControlValues,
  LabEffect,
  LabEvidence,
  LabFileMap,
  LabScenario,
  LabStep,
} from "../runtime/types";

const DEFAULT_INPUT =
  "读取 src/config.ts，搜索 port，把 8080 改成 9090，然后运行测试";
const DEFAULT_FILE = "src/config.ts";
const DEFAULT_FROM = "8080";
const REPOSITORY =
  "https://github.com/SwallOwDili/claudecodecli-sourcecode/blob/2.1.235";

const READ_PROBE_EVIDENCE: LabEvidence[] = [
  {
    label: "2.1.235 Read 正向 Probe",
    href: `${REPOSITORY}/analysis/runtime-probes/agent-loop-tool-result-resume.json`,
    detail:
      "evidence_owner=observed client wire; 精确二进制证明 tool_use、实际 Read 与同 ID tool_result 的两轮闭环。",
  },
];

const STATIC_PIPELINE_EVIDENCE: LabEvidence[] = [
  {
    label: "单工具执行管线",
    href: `${REPOSITORY}/analysis/agent-loop.md#单个工具调用的执行管线`,
    detail: "2.1.235 可读 bundle 中的校验、Hook、权限、执行与结果回灌顺序。",
  },
];

const LOOP_EVIDENCE: LabEvidence[] = [
  {
    label: "Agent Loop 主调用链",
    href: `${REPOSITORY}/analysis/agent-loop.md#主调用链`,
    detail: "请求、流式工具调度、结果 drain 与下一轮状态更新。",
  },
];

const TOOL_CHOICE_FIXTURE_EVIDENCE: LabEvidence[] = [
  {
    label: "Explanatory fixture",
    href: `${REPOSITORY}/analysis/agent-loop.md#亲手改变一次-agent-loop`,
    detail:
      "evidence_owner=teaching fixture; 具体工具、参数、虚拟输出和控件分支由浏览器内确定性规则生成，不冒充 Claude 模型输出。",
  },
];

export interface ParsedAgentLoopInput {
  source: string;
  filePath: string;
  searchRequested: boolean;
  searchTerm?: string;
  editRequested: boolean;
  from?: string;
  to?: string;
  testRequested: boolean;
  recognized: string[];
  assumptions: string[];
}

export interface AgentLoopTraceControls {
  permission: "allow" | "deny";
  testResult: "pass" | "fail";
}

export interface AgentLoopTraceResult {
  parsed: ParsedAgentLoopInput;
  steps: LabStep[];
  initialFiles: LabFileMap;
  notes: string[];
}

interface LoopView {
  phase: string;
  turnCount: number;
  pendingToolUseIds: string[];
  completedToolUseIds: string[];
  terminalReason?: "success" | "permission_denied" | "tests_failed";
}

interface RequiredStepFields {
  id: string;
  title: string;
  actor: LabStep["actor"];
  kind: LabStep["kind"];
  summary: string;
  tool: string;
  tool_use_id: string;
  input: unknown;
  output: unknown;
  before: unknown;
  after: unknown;
  files: LabFileMap;
  effects: Array<string | LabEffect>;
  evidence: LabEvidence[];
  visualTarget: string | string[];
  status: NonNullable<LabStep["status"]>;
}

function cloneFiles(files: LabFileMap): LabFileMap {
  return { ...files };
}

function cloneLoop(view: LoopView): LoopView {
  return {
    ...view,
    pendingToolUseIds: [...view.pendingToolUseIds],
    completedToolUseIds: [...view.completedToolUseIds],
  };
}

function normalizeVirtualPath(candidate: string | undefined): string {
  if (!candidate) return DEFAULT_FILE;

  const parts: string[] = [];
  const cleaned = candidate
    .trim()
    .replace(/^file:\/\//i, "")
    .replace(/\\/g, "/")
    .replace(/^[`'"“”‘’]+|[`'"“”‘’，。；：!?！？]+$/g, "");

  for (const part of cleaned.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      parts.pop();
      continue;
    }
    parts.push(part);
  }

  return parts.join("/") || DEFAULT_FILE;
}

function extractFilePath(input: string): string {
  const quotedPath = input.match(
    /[`'"“‘]((?:\.?\.?[\\/])?(?:[\w@.-]+[\\/])*(?:\.[A-Za-z0-9_-]+|[\w@.-]+\.[A-Za-z0-9_-]+))[`'"”’]/u,
  )?.[1];
  const plainPath = input.match(
    /(?:\.?\.?[\\/])?(?:[\w@.-]+[\\/])*(?:\.[A-Za-z0-9_-]+|[\w@.-]+\.[A-Za-z0-9_-]+)/u,
  )?.[0];
  return normalizeVirtualPath(quotedPath ?? plainPath);
}

function extractSearch(input: string): {
  requested: boolean;
  term?: string;
} {
  const requested = /(?:搜索|查找|检索|\bgrep\b|\bsearch(?:\s+for)?\b)/iu.test(
    input,
  );
  if (!requested) return { requested: false };

  const match = input.match(
    /(?:搜索|查找|检索|\bgrep\b|\bsearch(?:\s+for)?\b)\s*(?:字段|文本|关键字|keyword)?\s*[`'"“‘]?([\w.-]+|[\u3400-\u9fff]{1,16})/iu,
  );
  const candidate = match?.[1]?.replace(/[`'"”’。，；：!?！？]+$/u, "");
  return {
    requested: true,
    term:
      candidate && !/^(?:一下|字段|文本|关键字)$/u.test(candidate)
        ? candidate
        : "port",
  };
}

function extractReplacement(input: string): {
  requested: boolean;
  from?: string;
  to?: string;
  assumedFrom: boolean;
} {
  const replacementWords =
    /(?:改成|改为|替换为|变成|修改为|更新为|change|replace|update|->|=>)/iu;
  const requested = replacementWords.test(input);

  const pairPatterns = [
    /(?:从|把|将|from)\s*[`'"“‘]?(-?\d+(?:\.\d+)?)[`'"”’]?[^\d\n]{0,30}?(?:改成|改为|替换为|变成|修改为|更新为|到|至|to|->|=>)\s*[`'"“‘]?(-?\d+(?:\.\d+)?)/iu,
    /(-?\d+(?:\.\d+)?)\s*(?:->|=>|改成|改为|替换为|变成|到|至|to)\s*(-?\d+(?:\.\d+)?)/iu,
    /(?:change|replace|update)\D{0,20}?(-?\d+(?:\.\d+)?)\D{0,20}?(?:to|with)\D{0,8}?(-?\d+(?:\.\d+)?)/iu,
  ];

  for (const pattern of pairPatterns) {
    const match = input.match(pattern);
    if (match) {
      return {
        requested: true,
        from: match[1],
        to: match[2],
        assumedFrom: false,
      };
    }
  }

  const targetOnly = input.match(
    /(?:改成|改为|替换为|变成|修改为|更新为|to|with)\s*[`'"“‘]?(-?\d+(?:\.\d+)?)/iu,
  )?.[1];
  if (requested && targetOnly) {
    return {
      requested: true,
      from: DEFAULT_FROM,
      to: targetOnly,
      assumedFrom: true,
    };
  }

  return { requested, assumedFrom: false };
}

export function parseAgentLoopInput(rawInput: string): ParsedAgentLoopInput {
  const source = rawInput.trim() || DEFAULT_INPUT;
  const filePath = extractFilePath(source);
  const search = extractSearch(source);
  const replacement = extractReplacement(source);
  const testRequested =
    /(?:运行|执行|跑|run)?\s*(?:测试|测一下|tests?|test suite|npm test|pnpm test|bun test)/iu.test(
      source,
    );
  const recognized = [`文件 ${filePath}`];
  const assumptions: string[] = [];

  if (search.requested) recognized.push(`搜索 ${search.term}`);
  if (replacement.from && replacement.to) {
    recognized.push(`替换 ${replacement.from} -> ${replacement.to}`);
  } else if (replacement.requested) {
    assumptions.push(
      "识别到修改意图，但没有找到明确的旧值和新值，因此不执行 Edit。",
    );
  }
  if (replacement.assumedFrom) {
    assumptions.push(`输入只给出新值，教学夹具把旧值设为 ${DEFAULT_FROM}。`);
  }
  if (testRequested) recognized.push("运行测试");

  return {
    source,
    filePath,
    searchRequested: search.requested,
    searchTerm: search.term,
    editRequested: Boolean(replacement.from && replacement.to),
    from: replacement.from,
    to: replacement.to,
    testRequested,
    recognized,
    assumptions,
  };
}

function seedFile(filePath: string, from: string): string {
  const lower = filePath.toLowerCase();
  if (lower.endsWith(".json")) {
    return `{
  "port": ${from},
  "host": "127.0.0.1",
  "timeoutMs": 30000
}\n`;
  }
  if (/\.(?:ya?ml)$/u.test(lower)) {
    return `port: ${from}\nhost: 127.0.0.1\ntimeoutMs: 30000\n`;
  }
  if (/\.(?:env|properties|conf)$/u.test(lower)) {
    return `PORT=${from}\nHOST=127.0.0.1\nTIMEOUT_MS=30000\n`;
  }
  return `export const config = {
  port: ${from},
  host: "127.0.0.1",
  timeoutMs: 30_000,
};\n`;
}

function replaceFirst(source: string, from: string, to: string): string {
  const index = source.indexOf(from);
  if (index < 0) return source;
  return `${source.slice(0, index)}${to}${source.slice(index + from.length)}`;
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

function lineMatches(source: string, term: string): string[] {
  const needle = term.toLocaleLowerCase();
  return source
    .split("\n")
    .map((line, index) => ({ line, number: index + 1 }))
    .filter(({ line }) => line.toLocaleLowerCase().includes(needle))
    .map(({ line, number }) => `${number}:${line}`);
}

function normalizeControls(controls: LabControlValues): AgentLoopTraceControls {
  return {
    permission: controls.permission === "deny" ? "deny" : "allow",
    testResult: controls.testResult === "fail" ? "fail" : "pass",
  };
}

function fullStep(step: RequiredStepFields): LabStep {
  return {
    ...step,
    files: cloneFiles(step.files),
    effects: [...step.effects],
    evidence: step.evidence.map((entry) => ({ ...entry })),
    visualTarget: Array.isArray(step.visualTarget)
      ? [...step.visualTarget]
      : step.visualTarget,
  };
}

export function buildAgentLoopTrace(
  rawInput: string,
  rawControls: LabControlValues = {},
): AgentLoopTraceResult {
  if (
    !/(?:读取|打开|查看|搜索|查找|检索|改成|改为|替换|修改|更新|测试|\bread\b|\bgrep\b|\bsearch\b|\bedit\b|\bchange\b|\breplace\b|\btest\b)/iu.test(
      rawInput,
    )
  ) {
    throw new Error(
      "没有识别到支持的动作。请描述 Read/搜索/数值修改/运行测试中的至少一项。",
    );
  }
  const parsed = parseAgentLoopInput(rawInput);
  const controls = normalizeControls(rawControls);
  const fixtureFrom = parsed.from ?? DEFAULT_FROM;
  const initialFiles = {
    [parsed.filePath]: seedFile(parsed.filePath, fixtureFrom),
  };
  if (parsed.editRequested && parsed.from && parsed.to) {
    if (parsed.from === parsed.to) {
      throw new Error("Edit 的旧值和新值相同；目标版本会在执行前拒绝这个输入。");
    }
    const matches = occurrenceCount(initialFiles[parsed.filePath], parsed.from);
    if (matches !== 1) {
      throw new Error(
        `Edit 旧值必须在目标文件中唯一出现；当前夹具找到 ${matches} 次。请提供更精确的旧值。`,
      );
    }
  }
  let files = cloneFiles(initialFiles);
  let loop: LoopView = {
    phase: "idle",
    turnCount: 0,
    pendingToolUseIds: [],
    completedToolUseIds: [],
  };
  const steps: LabStep[] = [];
  let stepNumber = 0;
  let toolNumber = 0;

  const nextStepId = (kind: string): string =>
    `agent-loop-${String(++stepNumber).padStart(2, "0")}-${kind}`;
  const nextToolId = (tool: string): string =>
    `toolu_lab_${String(++toolNumber).padStart(2, "0")}_${tool.toLowerCase()}`;
  const snapshot = (): LabFileMap => cloneFiles(files);
  const transition = (
    patch: Partial<LoopView>,
  ): { before: LoopView; after: LoopView } => {
    const before = cloneLoop(loop);
    loop = {
      ...loop,
      ...patch,
      pendingToolUseIds: patch.pendingToolUseIds
        ? [...patch.pendingToolUseIds]
        : [...loop.pendingToolUseIds],
      completedToolUseIds: patch.completedToolUseIds
        ? [...patch.completedToolUseIds]
        : [...loop.completedToolUseIds],
    };
    return { before, after: cloneLoop(loop) };
  };
  const add = (
    fields: Omit<RequiredStepFields, "id" | "files" | "before" | "after"> & {
      slug: string;
      state?: Partial<LoopView>;
      before?: unknown;
      after?: unknown;
    },
  ): void => {
    const stateChange = transition(fields.state ?? {});
    steps.push(
      fullStep({
        id: nextStepId(fields.slug),
        title: fields.title,
        actor: fields.actor,
        kind: fields.kind,
        summary: fields.summary,
        tool: fields.tool,
        tool_use_id: fields.tool_use_id,
        input: fields.input,
        output: fields.output,
        before: fields.before ?? stateChange.before,
        after: fields.after ?? stateChange.after,
        files: snapshot(),
        effects: fields.effects,
        evidence: fields.evidence,
        visualTarget: fields.visualTarget,
        status: fields.status,
      }),
    );
  };

  add({
    slug: "input",
    title: "用户提交任务",
    actor: "user",
    kind: "input",
    summary: `解析到：${parsed.recognized.join("；")}`,
    tool: "",
    tool_use_id: "",
    input: parsed.source,
    output: parsed,
    state: { phase: "queued" },
    effects: [
      { label: "输入进入当前用户 turn", state: "proposed", reversible: true },
    ],
    evidence: LOOP_EVIDENCE,
    visualTarget: "state",
    status: "success",
  });

  const availableTools = ["Read", "Grep", "Edit", "Bash"];
  const teachingPlan = [
    "Read",
    ...(parsed.searchRequested ? ["Grep"] : []),
    ...(parsed.editRequested ? ["Edit"] : []),
    ...(parsed.testRequested ? ["Bash"] : []),
  ];
  const toolUseBlocks = new Map<string, Record<string, unknown>>();
  const completedMessagePairs: Array<{
    assistant: { role: "assistant"; content: Array<Record<string, unknown>> };
    user: { role: "user"; content: Array<Record<string, unknown>> };
  }> = [];
  let modelRequestCount = 0;
  const emitModelRequest = (
    fixtureNextAction: string,
    status: NonNullable<LabStep["status"]> = "success",
  ): void => {
    const requestNumber = ++modelRequestCount;
    const completedToolUseIds = [...loop.completedToolUseIds];
    add({
      slug: `request-${requestNumber}`,
      title: `客户端装配第 ${requestNumber} 次模型请求`,
      actor: "client",
      kind: "request",
      summary:
        requestNumber === 1
          ? "文件内容尚未进入上下文；沙盘固定暴露四个可用工具 schema。"
          : `只有到这次请求，模型才看到前面 ${completedToolUseIds.length} 个 tool_result。`,
      tool: "",
      tool_use_id: "",
      input: {
        request: requestNumber,
        messages: [
          { role: "user", content: parsed.source },
          ...completedMessagePairs.flatMap((pair) => [pair.assistant, pair.user]),
        ],
        tools: availableTools,
      },
      output: {
        request: requestNumber,
        teaching_fixture_plan: teachingPlan,
        teaching_fixture_next_action: fixtureNextAction,
        client_state_not_sent_to_model: {
          completed_tool_use_ids: completedToolUseIds,
          current_virtual_files: snapshot(),
        },
      },
      state: { phase: "model_stream", turnCount: requestNumber },
      effects: [
        {
          label: `开始第 ${requestNumber} 个模型 iteration`,
          state: "applied",
          reversible: true,
        },
      ],
      evidence: [
        ...LOOP_EVIDENCE,
        ...TOOL_CHOICE_FIXTURE_EVIDENCE,
        ...(requestNumber <= 2 ? READ_PROBE_EVIDENCE : []),
      ],
      visualTarget: ["state", "request"],
      status,
    });
  };

  emitModelRequest("Read");

  const emitToolUse = (
    tool: string,
    toolUseId: string,
    input: unknown,
  ): void => {
    const wireBlock = { type: "tool_use", id: toolUseId, name: tool, input };
    toolUseBlocks.set(toolUseId, wireBlock);
    add({
      slug: `${tool.toLowerCase()}-tool-use`,
      title: `模型提出 ${tool}`,
      actor: "model",
      kind: "tool_use",
      summary: `第 ${modelRequestCount} 次模型响应提出 ${tool}；完整 block 到达后，客户端按 ${toolUseId} 登记。`,
      tool,
      tool_use_id: toolUseId,
      input,
      output: wireBlock,
      state: {
        phase: "tool_scheduled",
        pendingToolUseIds: [...loop.pendingToolUseIds, toolUseId],
      },
      effects: [
        {
          label: `${tool} 仍只是提案，尚无外部副作用`,
          state: "proposed",
          reversible: true,
        },
      ],
      evidence: [
        ...TOOL_CHOICE_FIXTURE_EVIDENCE,
        ...(tool === "Read" ? READ_PROBE_EVIDENCE : []),
      ],
      visualTarget: ["request", "schedule"],
      status: "success",
    });
  };

  const emitExecution = (
    tool: string,
    toolUseId: string,
    input: unknown,
    output: unknown,
    effects: Array<string | LabEffect>,
    status: NonNullable<LabStep["status"]> = "success",
    before?: unknown,
    after?: unknown,
  ): void => {
    add({
      slug: `${tool.toLowerCase()}-execute`,
      title: `客户端执行 ${tool}`,
      actor: "tool",
      kind: "execute",
      summary: `${tool} 在浏览器虚拟文件系统中执行；这里不会访问读者的真实文件。`,
      tool,
      tool_use_id: toolUseId,
      input,
      output,
      before,
      after,
      state: { phase: "tool_running" },
      effects,
      evidence: [
        ...(tool === "Read" ? READ_PROBE_EVIDENCE : STATIC_PIPELINE_EVIDENCE),
        ...TOOL_CHOICE_FIXTURE_EVIDENCE,
      ],
      visualTarget: ["schedule", "execute", "external", "surface"],
      status,
    });
  };

  const emitToolResult = (
    tool: string,
    toolUseId: string,
    output: unknown,
    status: NonNullable<LabStep["status"]> = "success",
    effects: Array<string | LabEffect> = [],
  ): void => {
    const outputRecord =
      typeof output === "object" && output !== null
        ? (output as Record<string, unknown>)
        : undefined;
    const wireBlock =
      outputRecord && typeof outputRecord.wireBlock === "object"
        ? (outputRecord.wireBlock as Record<string, unknown>)
        : (output as Record<string, unknown>);
    const toolUseBlock = toolUseBlocks.get(toolUseId);
    if (!toolUseBlock) throw new Error(`Missing tool_use block for ${toolUseId}`);
    completedMessagePairs.push({
      assistant: { role: "assistant", content: [toolUseBlock] },
      user: { role: "user", content: [wireBlock] },
    });
    add({
      slug: `${tool.toLowerCase()}-result`,
      title: `${tool} 结果按同一 ID 入账`,
      actor: "client",
      kind: "tool_result",
      summary: `tool_result.tool_use_id=${toolUseId}；它先在客户端入账，下一次模型请求才会读取。`,
      tool,
      tool_use_id: toolUseId,
      input: { tool_use_id: toolUseId },
      output,
      state: {
        phase: "tool_result_ready",
        pendingToolUseIds: loop.pendingToolUseIds.filter(
          (id) => id !== toolUseId,
        ),
        completedToolUseIds: [...loop.completedToolUseIds, toolUseId],
      },
      effects,
      evidence: [
        ...(tool === "Read" ? READ_PROBE_EVIDENCE : STATIC_PIPELINE_EVIDENCE),
        ...TOOL_CHOICE_FIXTURE_EVIDENCE,
      ],
      visualTarget: ["execute", "feedback", "surface"],
      status,
    });
  };

  const readToolId = nextToolId("Read");
  const readInput = { file_path: parsed.filePath };
  const readOutput = files[parsed.filePath];
  emitToolUse("Read", readToolId, readInput);
  emitExecution("Read", readToolId, readInput, readOutput, [
    {
      label: "读取虚拟文件，不改变文件状态",
      state: "applied",
      reversible: true,
    },
  ]);
  emitToolResult("Read", readToolId, {
    type: "tool_result",
    tool_use_id: readToolId,
    content: readOutput,
    is_error: false,
  });

  if (parsed.searchRequested && parsed.searchTerm) {
    emitModelRequest("Grep");
    const grepToolId = nextToolId("Grep");
    const grepInput = {
      pattern: parsed.searchTerm,
      path: parsed.filePath,
      output_mode: "content",
    };
    const matches = lineMatches(files[parsed.filePath], parsed.searchTerm);
    emitToolUse("Grep", grepToolId, grepInput);
    emitExecution(
      "Grep",
      grepToolId,
      grepInput,
      matches.length ? matches.join("\n") : "No matches found",
      [
        {
          label: "搜索结果只进入观察，不改变文件",
          state: "applied",
          reversible: true,
        },
      ],
    );
    emitToolResult("Grep", grepToolId, {
      type: "tool_result",
      tool_use_id: grepToolId,
      content: matches.length ? matches.join("\n") : "No matches found",
      is_error: false,
    });
  }

  const requestPermission = (
    tool: "Edit" | "Bash",
    toolUseId: string,
  ): boolean => {
    const allowed = controls.permission === "allow";
    add({
      slug: `${tool.toLowerCase()}-permission`,
      title: allowed ? `允许执行 ${tool}` : `拒绝执行 ${tool}`,
      actor: "permission",
      kind: "permission",
      summary: allowed
        ? "权限裁决允许继续；此时工具仍未产生副作用。"
        : "权限裁决在调用前终止执行，虚拟文件保持原样。",
      tool,
      tool_use_id: toolUseId,
      input: { decision: controls.permission, tool_use_id: toolUseId },
      output: { allowed, source: "interactive-lab-control" },
      state: { phase: allowed ? "permission_granted" : "permission_denied" },
      effects: [
        {
          label: allowed
            ? `${tool} 获得一次执行许可`
            : `${tool} 被阻止，未执行`,
          state: allowed ? "applied" : "blocked",
          reversible: true,
        },
      ],
      evidence: [
        ...STATIC_PIPELINE_EVIDENCE,
        ...TOOL_CHOICE_FIXTURE_EVIDENCE,
      ],
      visualTarget: ["schedule", "execute"],
      status: allowed ? "success" : "denied",
    });
    return allowed;
  };

  const finishDenied = (
    tool: string,
    toolUseId: string,
  ): AgentLoopTraceResult => {
    emitToolResult(
      tool,
      toolUseId,
      {
        wireBlock: {
          type: "tool_result",
          tool_use_id: toolUseId,
          content: `Permission denied before ${tool} execution`,
          is_error: true,
        },
        clientMetadata: {
          non_execution_kind: "user-rejected",
        },
      },
      "denied",
      [
        {
          label: "拒绝结果进入下一轮，但没有工具副作用",
          state: "blocked",
          reversible: true,
        },
      ],
    );
    emitModelRequest("finish_after_permission_denied", "denied");
    add({
      slug: "denied",
      title: "本次模拟在权限边界结束",
      actor: "model",
      kind: "denied",
      summary: `${tool} 未执行；${parsed.filePath} 保持修改前内容。`,
      tool,
      tool_use_id: toolUseId,
      input: { observation: "permission_denied" },
      output: `没有获得 ${tool} 权限，已停止后续有副作用的工具。`,
      state: { phase: "terminal", terminalReason: "permission_denied" },
      effects: [
        { label: "Edit/Bash 后续链停止", state: "blocked", reversible: true },
      ],
      evidence: [...LOOP_EVIDENCE, ...TOOL_CHOICE_FIXTURE_EVIDENCE],
      visualTarget: ["decide", "state"],
      status: "denied",
    });
    return {
      parsed,
      steps,
      initialFiles,
      notes: [
        "这是教学模拟：输入规划由页面内确定性规则完成，不是远端 Claude 模型输出。",
        "权限拒绝发生在执行前，因此虚拟文件没有修改，也不会继续运行测试。",
      ],
    };
  };

  if (parsed.editRequested && parsed.from && parsed.to) {
    emitModelRequest("Edit");
    const editToolId = nextToolId("Edit");
    const editInput = {
      file_path: parsed.filePath,
      old_string: parsed.from,
      new_string: parsed.to,
      replace_all: false,
    };
    emitToolUse("Edit", editToolId, editInput);
    if (!requestPermission("Edit", editToolId))
      return finishDenied("Edit", editToolId);

    const beforeContent = files[parsed.filePath];
    const afterContent = replaceFirst(beforeContent, parsed.from, parsed.to);
    files = { ...files, [parsed.filePath]: afterContent };
    emitExecution(
      "Edit",
      editToolId,
      editInput,
      { updated: beforeContent !== afterContent, file_path: parsed.filePath },
      [
        {
          label: `${parsed.filePath}: ${parsed.from} -> ${parsed.to}`,
          state: "applied",
          reversible: false,
        },
      ],
      "success",
      { loop: cloneLoop(loop), file: beforeContent },
      {
        loop: { ...cloneLoop(loop), phase: "tool_running" },
        file: afterContent,
      },
    );
    emitToolResult("Edit", editToolId, {
      type: "tool_result",
      tool_use_id: editToolId,
      content: `Updated ${parsed.filePath}`,
      is_error: false,
    });
  }

  if (parsed.testRequested) {
    emitModelRequest("Bash");
    const bashToolId = nextToolId("Bash");
    const bashInput = { command: "npm test", timeout: 120000 };
    emitToolUse("Bash", bashToolId, bashInput);
    if (!requestPermission("Bash", bashToolId))
      return finishDenied("Bash", bashToolId);

    const testFailed = controls.testResult === "fail";
    const bashOutput = testFailed
      ? {
          stdout:
            "FAIL config.test.ts\nExpected configured port to be reachable",
          stderr: "1 test failed",
          exit_code: 1,
        }
      : {
          stdout: "PASS config.test.ts\n1 test passed",
          stderr: "",
          exit_code: 0,
        };
    emitExecution(
      "Bash",
      bashToolId,
      bashInput,
      bashOutput,
      [
        {
          label: testFailed
            ? "测试进程以 exit 1 结束"
            : "测试进程以 exit 0 结束",
          state: testFailed ? "failed" : "applied",
          reversible: false,
        },
      ],
      testFailed ? "failed" : "success",
    );
    emitToolResult(
      "Bash",
      bashToolId,
      {
        type: "tool_result",
        tool_use_id: bashToolId,
        content: JSON.stringify(bashOutput, null, 2),
        is_error: testFailed,
      },
      testFailed ? "failed" : "success",
      [
        {
          label: "测试结果成为下一次模型决策的新观察",
          state: testFailed ? "failed" : "applied",
          reversible: true,
        },
      ],
    );
  }

  const testFailed = parsed.testRequested && controls.testResult === "fail";
  emitModelRequest(
    testFailed ? "finish_after_test_failure" : "finish_after_success",
    testFailed ? "failed" : "success",
  );

  const edited = parsed.editRequested;
  const tested = parsed.testRequested;
  const finalTitle = testFailed
    ? "模型看到测试失败并停止冒充成功"
    : edited && tested
      ? "模型确认修改和测试均完成"
      : edited
        ? "模型确认文件修改完成"
        : tested
          ? "模型确认测试完成"
          : parsed.searchRequested
            ? "模型完成读取和搜索"
            : "模型完成文件读取";
  const finalSummary = testFailed
    ? edited
      ? "文件修改已经发生，测试失败不会自动回滚这个外部副作用。"
      : "测试失败已进入因果记录；本次没有文件修改需要回滚。"
    : edited && tested
      ? `修改与测试结果都已进入因果记录，${parsed.filePath} 保留新值。`
      : edited
        ? `${parsed.filePath} 已修改；用户没有要求运行测试。`
        : tested
          ? "测试结果已进入因果记录；本次没有请求文件修改。"
          : parsed.searchRequested
            ? "读取和搜索结果已进入因果记录；虚拟文件保持原样。"
            : "读取结果已进入因果记录；虚拟文件保持原样。";
  const finalOutput = testFailed
    ? edited
      ? "配置已修改，但测试失败；需要检查失败输出后再决定修复或显式回滚。"
      : "测试失败；需要检查 stderr 和退出码后再决定下一步。"
    : edited && tested
      ? "配置修改完成，测试通过。"
      : edited
        ? "配置修改完成；未运行测试。"
        : tested
          ? "测试通过；没有修改文件。"
          : parsed.searchRequested
            ? "读取和搜索完成；没有修改文件。"
            : "读取完成；没有修改文件。";
  add({
    slug: testFailed ? "failed" : "complete",
    title: finalTitle,
    actor: "model",
    kind: testFailed ? "failed" : "complete",
    summary: finalSummary,
    tool: "",
    tool_use_id: "",
    input: { observations: loop.completedToolUseIds },
    output: finalOutput,
    state: {
      phase: "terminal",
      terminalReason: testFailed ? "tests_failed" : "success",
    },
    effects: [
      {
        label: testFailed
          ? edited
            ? "保留失败现场与已完成文件修改"
            : "保留失败输出与退出码"
          : edited
            ? "保留已完成文件修改"
            : "结束时没有文件副作用",
        state: testFailed ? "failed" : "applied",
        reversible: true,
      },
    ],
    evidence: [...LOOP_EVIDENCE, ...TOOL_CHOICE_FIXTURE_EVIDENCE],
    visualTarget: ["decide", "state"],
    status: testFailed ? "failed" : "success",
  });

  return {
    parsed,
    steps,
    initialFiles,
    notes: [
      "这是教学模拟：输入规划由页面内确定性规则完成，不是远端 Claude 模型输出。",
      "Read 闭环绑定 2.1.235 精确二进制 Probe；Grep/Edit/Bash 分支按本版静态工具管线重建。",
      "后退通过初始夹具和步骤快照重放；它不表示真实外部副作用可以被 Agent Loop 撤销。",
      ...parsed.assumptions,
    ],
  };
}

export const agentLoopScenario: LabScenario = {
  id: "agent-loop",
  title: "Agent Loop：从输入到工具结果回灌",
  description:
    "输入文件、搜索词和数值修改，逐步观察 Claude Code 客户端如何装配请求、配对 tool_use/tool_result、执行权限裁决并进入下一轮。",
  defaultInput: DEFAULT_INPUT,
  examples: [
    {
      label: "完整成功链",
      input: DEFAULT_INPUT,
      controls: { permission: "allow", testResult: "pass" },
    },
    {
      label: "只读并搜索",
      input: "读取 config.json，搜索 timeoutMs",
      controls: { permission: "allow", testResult: "pass" },
    },
    {
      label: "拒绝写入权限",
      input: "读取 settings.yaml，把 8080 改成 3000，然后运行测试",
      controls: { permission: "deny", testResult: "pass" },
    },
    {
      label: "修改成功但测试失败",
      input: "读取 .env，搜索 PORT，把 8080 改为 9091，然后运行测试",
      controls: { permission: "allow", testResult: "fail" },
    },
  ],
  initialFiles: { [DEFAULT_FILE]: seedFile(DEFAULT_FILE, DEFAULT_FROM) },
  graph: {
    src: "../assets/visuals/agent-loop-lifecycle.svg",
    label: "Agent Loop 请求、受控执行与结果回灌流程",
  },
  controls: [
    {
      id: "permission",
      label: "Edit / Bash 权限",
      type: "select",
      defaultValue: "allow",
      options: [
        { value: "allow", label: "允许" },
        { value: "deny", label: "拒绝" },
      ],
      description: "拒绝发生在工具调用前；后续有副作用的工具不会执行。",
    },
    {
      id: "testResult",
      label: "测试结果",
      type: "select",
      defaultValue: "pass",
      options: [
        { value: "pass", label: "通过" },
        { value: "fail", label: "失败" },
      ],
      description:
        "测试失败会作为 is_error tool_result 回到下一轮，不自动回滚文件。",
    },
  ],
  buildTrace: buildAgentLoopTrace,
};

export default registerLabScenario(agentLoopScenario);
