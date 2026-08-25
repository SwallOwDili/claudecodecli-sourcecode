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
  "/compact 保留用户对 Summary、近期消息、文件附件和 Resume 的要求，并继续完成技术文章";

const BASE_FILES: LabFileMap = {
  "/session/transcript.jsonl":
    '{"type":"user","uuid":"fixture-user-01","message":"解释 /compact 的真实客户端流程"}\n',
  "/workspace/analysis-notes.md":
    "已确认：Summary、preserved messages、attachments、compact_boundary。\n待办：整理为读者可理解的文章。\n",
  "/workspace/reverse/javascript/cli.readable.js":
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\nmessagesToPreserve: groups.flat()\nsubtype: compact_boundary\n",
  "/workspace/analysis/runtime-probes/agent-loop-tool-result-resume.json":
    '{"compactBoundary":{"trigger":"manual","preTokens":104},"compactBoundaryEmitted":true}\n',
};

interface CompactRequest {
  raw: string;
  customInstructions: string;
  mentionedFiles: string[];
  keywords: string[];
}

interface CompactMessage {
  uuid: string;
  role: "user" | "assistant";
  contentType: "text" | "tool_use" | "tool_result";
  content: string;
  assistantMessageId?: string;
  pairedToolUseId?: string;
}

interface CompactGroup {
  id: string;
  messages: CompactMessage[];
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

const GROUP_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    actor,
    "Static source",
    `${REPOSITORY}/reverse/javascript/cli.readable.js#L262209-L262294`,
    "legal message grouping, messagesToPreserve, and suffix retry",
  );

const SUMMARY_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    actor,
    "Static source",
    `${REPOSITORY}/reverse/javascript/cli.readable.js#L261901-L262207`,
    "summary prompt, analysis/summary tags, and parser",
  );

const ATTACHMENT_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    actor,
    "Static source",
    `${REPOSITORY}/reverse/javascript/cli.readable.js#L263175-L263235`,
    "recent-file and current-task attachment restoration",
  );

const BOUNDARY_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    actor,
    "Exact-binary probe",
    `${REPOSITORY}/analysis/runtime-probes/agent-loop-tool-result-resume.json`,
    "exact binary emits a manual compact boundary with trigger and preTokens",
  );

const BOUNDARY_SHAPE_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    actor,
    "Static source",
    `${REPOSITORY}/reverse/javascript/cli.readable.js#L211993-L212001`,
    "transcript serialization uses compact_metadata and the structured preserved_messages object",
  );

const CONTROL_FIXTURE_EVIDENCE = (actor: LabActor): LabEvidence =>
  evidence(
    `teaching fixture/${actor}`,
    "Explanatory fixture",
    "#改变输入亲自观察这次重建",
    "the selected control values, attachment outcomes, hook match counts, and estimated token values belong to this browser fixture",
  );

function numericControl(
  controls: LabControlValues,
  id: string,
  fallback: number,
): number {
  const value = controls[id];
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stringControl(
  controls: LabControlValues,
  id: string,
  fallback: string,
): string {
  const value = controls[id];
  return typeof value === "string" && value ? value : fallback;
}

function parseCompactInput(input: string): CompactRequest {
  const raw = input.trim() || DEFAULT_INPUT;
  const customInstructions = raw.replace(/^\/compact\b/iu, "").trim();
  const mentionedFiles = Array.from(
    new Set(
      Array.from(
        raw.matchAll(/\/?(?:[A-Za-z0-9_.-]+\/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_-]+/g),
        (match) => match[0].replace(/^[`'"“‘]+|[`'"”’。，；：!?！？]+$/gu, ""),
      )
        .filter((path) => /[A-Za-z]/u.test(path))
        .filter((path) => !/^\d+(?:\.\d+)+$/u.test(path))
        .map((path) => (path.startsWith("/") ? path : `/workspace/${path}`)),
    ),
  ).slice(0, 5);
  const keywords = Array.from(
    new Set([
      ...Array.from(raw.matchAll(/`([^`]+)`/g), (match) => match[1]),
      ...["Summary", "preserved messages", "attachments", "compact_boundary"].filter(
        (keyword) => raw.toLowerCase().includes(keyword.toLowerCase()),
      ),
    ]),
  ).slice(0, 8);

  return {
    raw,
    customInstructions,
    mentionedFiles,
    keywords,
  };
}

function createHistory(count: number): CompactGroup[] {
  const evidenceFiles = [
    "/workspace/reverse/javascript/cli.readable.js",
    "/workspace/analysis/runtime-probes/agent-loop-tool-result-resume.json",
  ];
  let assistantSequence = 0;
  const userText = (content: string): Omit<CompactMessage, "uuid"> => ({
    role: "user",
    contentType: "text",
    content,
  });
  const assistantText = (content: string): Omit<CompactMessage, "uuid"> => ({
    role: "assistant",
    contentType: "text",
    content,
    assistantMessageId: `fixture-assistant-response-${String(
      ++assistantSequence,
    ).padStart(2, "0")}`,
  });
  const assistantToolUse = (
    tool: string,
    toolUseId: string,
    toolInput: string,
  ): Omit<CompactMessage, "uuid"> => ({
    role: "assistant",
    contentType: "tool_use",
    content: `tool_use ${tool}: ${toolInput}`,
    assistantMessageId: `fixture-assistant-response-${String(
      ++assistantSequence,
    ).padStart(2, "0")}`,
    pairedToolUseId: toolUseId,
  });
  const toolResult = (
    toolUseId: string,
    result: string,
  ): Omit<CompactMessage, "uuid"> => ({
    role: "user",
    contentType: "tool_result",
    content: `tool_result ${toolUseId}: ${result}`,
    pairedToolUseId: toolUseId,
  });
  const flatTemplates: Array<Omit<CompactMessage, "uuid">> = [
    userText(
      "解释 Claude Code 2.1.235 的 compact 客户端流程，并把证据整理成技术文章",
    ),
    assistantToolUse(
      "Grep",
      "toolu-grep-compact",
      "compact|messagesToPreserve|compact_boundary",
    ),
    toolResult(
      "toolu-grep-compact",
      "summary prompt, preserved suffix, attachment and boundary locations",
    ),
    assistantToolUse("Read", "toolu-read-summary", evidenceFiles[0]),
    toolResult(
      "toolu-read-summary",
      "CRITICAL prompt and analysis/summary parser",
    ),
    userText("继续确认近期消息、附件和 Resume，不要只分析提示词"),
    assistantToolUse(
      "Read",
      "toolu-read-boundary",
      evidenceFiles[1],
    ),
    toolResult(
      "toolu-read-boundary",
      "trigger, token counts and preserved UUIDs",
    ),
    assistantText("已确认客户端重建链；下一步整理文章并验证"),
    userText("保留失败原因、当前文件和下一步，不要只留下结论"),
    assistantToolUse(
      "Bash",
      "toolu-validate-snapshot",
      "validate_snapshot.py",
    ),
    toolResult("toolu-validate-snapshot", "snapshot validation PASS"),
    assistantText("当前工作：先核对附件读取与 Boundary 字段"),
    userText("同时保留当前失败现场和未完成事项"),
    assistantToolUse(
      "Read",
      "toolu-read-notes",
      "analysis-notes.md",
    ),
    toolResult(
      "toolu-read-notes",
      "current evidence, open questions and article outline",
    ),
    assistantText("已把字段语义和恢复边界补进草稿"),
    userText("继续完成文章、运行验证并保留当前工作现场"),
    assistantToolUse(
      "Bash",
      "toolu-validate-article",
      "validate article and site",
    ),
    toolResult("toolu-validate-article", "article and site validation PASS"),
    assistantText("验证已通过，正在核对 Summary 与 preserved UUID"),
    userText("最后说明哪些内容来自 Probe，哪些只是教学重建"),
    assistantText("当前工作：把 Summary、近期因果、附件和 Boundary 写成完整交接"),
  ];
  const messages: CompactMessage[] = flatTemplates.map((message, index) => ({
    ...message,
    uuid: `fixture-message-${String(index + 1).padStart(2, "0")}`,
  }));
  const groups: CompactGroup[] = [];
  let current: CompactMessage[] = [];
  let currentAssistantMessageId: string | undefined;
  for (const message of messages) {
    const startsNewAssistantGroup =
      message.role === "assistant" &&
      message.assistantMessageId !== currentAssistantMessageId &&
      current.length > 0;
    if (startsNewAssistantGroup) {
      groups.push({
        id: `group-${String(groups.length + 1).padStart(2, "0")}`,
        messages: current,
      });
      current = [message];
    } else {
      current.push(message);
    }
    if (message.role === "assistant") {
      currentAssistantMessageId = message.assistantMessageId;
    }
  }
  if (current.length) {
    groups.push({
      id: `group-${String(groups.length + 1).padStart(2, "0")}`,
      messages: current,
    });
  }
  return groups.slice(0, count);
}

function summaryFor(
  request: CompactRequest,
  summarizedGroups: CompactGroup[],
  preservedGroups: CompactGroup[],
): string {
  const historicalUserMessages = flattenGroups([
    ...summarizedGroups,
    ...preservedGroups,
  ])
    .filter(
      (message) =>
        message.role === "user" && message.contentType === "text",
    )
    .map((message) => message.content);
  const primaryRequest =
    historicalUserMessages[0] ??
    "解释 Claude Code 2.1.235 的 compact 客户端流程";
  const files = request.mentionedFiles.length
    ? request.mentionedFiles.join(", ")
    : "cli.readable.js, agent-loop-tool-result-resume.json";
  const concepts = request.keywords.length
    ? request.keywords.join(", ")
    : "Summary, preserved messages, attachments, compact_boundary";

  return [
    `1. Primary Request and Intent: ${primaryRequest}`,
    `2. Key Technical Concepts: ${concepts}`,
    `3. Files and Code Sections: ${files}`,
    `4. Errors and Fixes: 较早 ${summarizedGroups.length} 个消息组被压缩；用户纠正和失败原因需要继续保留。`,
    "5. Problem Solving: 已从 Summary prompt 追到合法消息分组、附件恢复和 Boundary。",
    `6. All User Messages: ${historicalUserMessages.join("；")}`,
    "7. Pending Tasks: 用当前证据完成文章并重新验证。",
    `8. Current Work: ${preservedGroups.length} 个近期消息组仍以原内容接续；compact 额外强调：${request.customInstructions || "按默认要求生成完整交接"}。`,
    "9. Optional Next Step: 从重建后的逻辑上下文继续当前任务。",
  ].join("\n");
}

function transcriptFor(groups: CompactGroup[]): string {
  return `${groups
    .flatMap((group) => group.messages)
    .map((message) =>
      JSON.stringify({
        type: message.role,
        uuid: message.uuid,
        content_type: message.contentType,
        content: message.content,
        assistant_message_id: message.assistantMessageId,
        tool_use_id: message.pairedToolUseId,
      }),
    )
    .join("\n")}\n`;
}

function flattenGroups(groups: CompactGroup[]): CompactMessage[] {
  return groups.flatMap((group) => group.messages);
}

function buildCompactTrace(
  input: string,
  controls: LabControlValues,
): { parsed: unknown; steps: LabStep[]; initialFiles: LabFileMap; notes: string[] } {
  if (!/(?:\/compact|\bcompact\b|压缩|总结上下文)/iu.test(input)) {
    throw new Error(
      "没有识别到 compact 意图。请输入 `/compact ...`，或明确说明要压缩/总结上下文。",
    );
  }
  const request = parseCompactInput(input);
  const historyCount = Math.min(Math.max(numericControl(controls, "historyGroups", 9), 6), 12);
  const requestedPreservedCount = Math.min(
    Math.max(numericControl(controls, "preservedGroups", 2), 1),
    3,
  );
  const preservedCount = Math.min(requestedPreservedCount, historyCount - 1);
  const attachmentMode = stringControl(controls, "attachmentRecovery", "exact");
  const preCompact = stringControl(controls, "preCompact", "allow");
  const history = createHistory(historyCount);
  const summarizedGroups = history.slice(0, history.length - preservedCount);
  const preservedGroups = history.slice(history.length - preservedCount);
  const initialFiles: LabFileMap = {
    ...BASE_FILES,
    "/session/transcript.jsonl": transcriptFor(history),
  };
  const steps: LabStep[] = [
    {
      id: "compact-trigger",
      title: "用户触发 compact",
      actor: "user",
      kind: "input",
      summary: request.raw,
      input: {
        instruction: request.raw,
        history_groups: history.length,
      },
      evidence: [
        evidence(
          "user",
          "Explanatory fixture",
          "#压缩前模型和客户端已经来回执行了很多轮",
          "the entered instruction drives this local teaching trace",
        ),
      ],
      visualTarget: "trigger",
      status: "success",
    },
    {
      id: "pre-compact-hook",
      title: "PreCompact 决定是否继续",
      actor: "hook",
      kind: "hook",
      summary:
        preCompact === "block"
          ? "Hook 阻止压缩，原 active history 保持不变"
          : "Hook 放行，客户端可以选择合法消息切点",
      output: {
        behavior: preCompact === "block" ? "block" : "allow",
      },
      files: initialFiles,
      effects: [
        {
          label: preCompact === "block" ? "不写 compact boundary" : "允许进入 group compactor",
          state: preCompact === "block" ? "blocked" : "applied",
          reversible: true,
        },
      ],
      evidence: [
        evidence(
          "hook",
          "Static source",
          `${REPOSITORY}/reverse/javascript/cli.readable.js#L331301-L331311`,
          "manual compact dispatches PreCompact and checks blockedBy before selecting the compact path",
        ),
        CONTROL_FIXTURE_EVIDENCE("hook"),
      ],
      visualTarget: "trigger",
      status: preCompact === "block" ? "denied" : "success",
    },
  ];

  if (preCompact === "block") {
    steps.push({
      id: "compact-blocked",
      title: "压缩结束于原历史",
      actor: "client",
      kind: "denied",
      summary: "Summary、保留区和 Boundary 都没有形成；下一轮仍使用原 active history。",
      output: {
        active_history: "unchanged",
        summary: null,
        preserved_messages: null,
        compact_boundary: null,
      },
      files: initialFiles,
      evidence: [
        evidence(
          "client",
          "Static source",
          `${REPOSITORY}/reverse/javascript/cli.readable.js#L262973-L262976`,
          "nyi throws on blockedBy before a rebuilt compact result can be committed",
        ),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "trigger",
      status: "denied",
    });

    return {
      parsed: {
        request,
        historyGroups: history.length,
        preservedGroups: preservedCount,
        attachmentMode,
        preCompact,
      },
      steps,
      initialFiles,
      notes: [
        "这是根据 2.1.235 客户端规则生成的教学夹具，不是新采集的 wire dump。",
        "PreCompact 阻断发生在新 Summary 和 Boundary 提交之前。",
      ],
    };
  }

  const summaryBody = summaryFor(request, summarizedGroups, preservedGroups);
  const parsedSummary = `Summary:\n${summaryBody}`;
  const modelSummaryResponse = `<analysis>按时间梳理 ${summarizedGroups.length} 个较早消息组。</analysis>\n<summary>${summaryBody}</summary>`;
  const continuedSummary = [
    "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.",
    "",
    parsedSummary,
    "",
    "If you need specific details from before compaction, read the full transcript at: /session/transcript.jsonl",
    "Continue the conversation from where it left off without asking the user any further questions. Resume directly; do not acknowledge or recap the summary.",
  ].join("\n");
  const attachmentCandidates = request.mentionedFiles.length
    ? request.mentionedFiles
    : [
        "/workspace/reverse/javascript/cli.readable.js",
        "/workspace/analysis-notes.md",
      ];
  const availableAttachments = attachmentCandidates.filter(
    (path) => path in initialFiles,
  );
  const missingAttachments = attachmentCandidates.filter(
    (path) => !(path in initialFiles),
  );
  const attachments =
    attachmentMode === "none"
      ? []
      : attachmentMode === "degraded"
        ? availableAttachments.slice(0, 1)
        : availableAttachments.slice(0, 5);
  const attachmentFailures =
    attachmentMode === "none"
      ? []
      : attachmentMode === "degraded"
        ? [
            ...availableAttachments.slice(1),
            ...missingAttachments,
            ...(attachmentCandidates.length === 1 && missingAttachments.length === 0
              ? ["/workspace/missing-evidence.md"]
              : []),
          ]
        : missingAttachments;
  const fixturePreTokens = flattenGroups(history).length * 590;
  const attachmentCharacters = attachments.reduce(
    (total, path) => total + (initialFiles[path]?.length ?? 160),
    0,
  );
  const fixturePostTokens =
    Math.ceil(continuedSummary.length / 4) + preservedGroups.length * 1_180 + Math.ceil(attachmentCharacters / 4);
  const preservedMessages = flattenGroups(preservedGroups);
  const preservedMessageUuids = preservedMessages.map((message) => message.uuid);
  const summaryMessageUuid = "fixture-compact-summary-01";
  const boundary = {
    type: "system",
    subtype: "compact_boundary",
    content: "Conversation compacted",
    level: "info",
    uuid: "fixture-compact-boundary-01",
    compact_metadata: {
      trigger: "manual",
      pre_tokens: fixturePreTokens,
      post_tokens: fixturePostTokens,
      preserved_segment: {
        head_uuid: preservedMessageUuids[0],
        anchor_uuid: summaryMessageUuid,
        tail_uuid: preservedMessageUuids.at(-1),
      },
      preserved_messages: {
        anchor_uuid: summaryMessageUuid,
        uuids: preservedMessageUuids,
        all_uuids: preservedMessageUuids,
      },
    },
  };
  const summaryMessage = {
    type: "user",
    uuid: summaryMessageUuid,
    isCompactSummary: true,
    isVisibleInTranscriptOnly: true,
    message: {
      role: "user",
      content: continuedSummary,
    },
  };
  const boundaryFiles: LabFileMap = {
    ...initialFiles,
    "/session/transcript.jsonl": `${initialFiles["/session/transcript.jsonl"]}${JSON.stringify(
      boundary,
    )}\n${JSON.stringify(summaryMessage)}\n`,
  };

  steps.push(
    {
      id: "group-history",
      title: "按合法消息组选择切点",
      actor: "client",
      kind: "assemble",
      summary: `${summarizedGroups.length} 个较早组进入 Summary，${preservedGroups.length} 个近期组原样保留。`,
      before: history,
      after: {
        summarized: summarizedGroups.map((group) => group.id),
        preserved: preservedGroups.map((group) => group.id),
        preserved_group_heads: preservedGroups.map(
          (group) => group.messages[0]?.uuid,
        ),
        preserved_message_uuids: preservedMessageUuids,
      },
      effects: [
        {
          label: `保留 ${preservedGroups.length} 个完整消息组，不拆散 tool_use/tool_result`,
          state: "applied",
          reversible: true,
        },
      ],
      evidence: [
        GROUP_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "groups",
      status: "success",
    },
    {
      id: "summary-request",
      title: "发送只允许文本的 Summary 请求",
      actor: "client",
      kind: "request",
      summary: "客户端在较早前缀末尾加入虚拟用户消息，并固定拒绝工具调用。",
      input: {
        groups: summarizedGroups,
        custom_instructions: request.customInstructions,
        virtual_user_message:
          "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools. Return <analysis> then <summary>.",
        tool_permission: "deny",
      },
      evidence: [
        SUMMARY_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "summarize",
      status: "success",
    },
    {
      id: "summary-generation",
      title: "模型总结较早历史",
      actor: "model",
      kind: "stream",
      summary: request.customInstructions
        ? `模型总结旧历史，并按 compact 参数强调“${request.customInstructions}”。`
        : "模型按默认模板总结旧历史。",
      output: modelSummaryResponse,
      evidence: [
        SUMMARY_EVIDENCE("client"),
        evidence(
          "model",
          "Explanatory fixture",
          "#较早内容变成一段新文本",
          "the wording varies with the entered request; only the client template is fixed",
        ),
      ],
      visualTarget: "summarize",
      status: "success",
    },
    {
      id: "summary-parse",
      title: "删除 analysis，提取 Summary",
      actor: "client",
      kind: "feedback",
      summary: "解析器移除 analysis 标签内容，并把 summary 变成后续上下文中的 Summary 文本。",
      before: {
        has_analysis: true,
        has_summary: true,
      },
      after: parsedSummary,
      evidence: [SUMMARY_EVIDENCE("client")],
      visualTarget: "parse",
      status: "success",
    },
    {
      id: "restore-attachments",
      title: "恢复精确附件",
      actor: "client",
      kind: "execute",
      summary:
        attachmentMode === "exact"
          ? `恢复 ${attachments.length} 个最近文件。`
          : attachmentMode === "degraded"
            ? `只恢复 ${attachments.length} 个文件，其余读取失败后降级。`
            : "本次不恢复文件附件，后续只能依赖 Summary 和近期消息。",
      output: {
        mode: attachmentMode,
        restored: attachments,
        failed: attachmentFailures,
        session_start_hook_results: [],
      },
      effects: [
        {
          label: attachments.length ? "精确材料进入重建上下文" : "没有精确文件材料进入重建上下文",
          state: attachments.length ? "applied" : "blocked",
          reversible: true,
        },
      ],
      evidence: [
        ATTACHMENT_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "rebuild",
      status: attachmentFailures.length ? "failed" : "success",
    },
    {
      id: "post-compact-hook",
      title: "PostCompact Hook 接收 Summary",
      actor: "hook",
      kind: "hook",
      summary:
        "附件恢复完成后，客户端分开发送 PostCompact；本夹具没有匹配 Hook，因此没有 userDisplayMessage。",
      input: {
        trigger: "manual",
        compactSummary: modelSummaryResponse,
      },
      output: {
        matching_hooks: 0,
        userDisplayMessage: null,
      },
      evidence: [
        evidence(
          "hook",
          "Static source",
          `${REPOSITORY}/reverse/javascript/cli.readable.js#L232866-L232868`,
          "Smi dispatches post_compact after wmi attachment and SessionStart-hook restoration",
        ),
        CONTROL_FIXTURE_EVIDENCE("hook"),
      ],
      visualTarget: "rebuild",
      status: "success",
    },
    {
      id: "rebuild-context",
      title: "组装新的逻辑上下文",
      actor: "client",
      kind: "assemble",
      summary: "客户端把解析后的 Summary 包进 synthetic user compact-summary message，再与近期完整消息和附件汇合。",
      output: {
        summary_message: summaryMessage,
        preserved_messages: preservedMessages,
        attachments,
        next_user_input: "awaiting subsequent user turn",
      },
      evidence: [
        GROUP_EVIDENCE("client"),
        ATTACHMENT_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "rebuild",
      status: "success",
    },
    {
      id: "write-boundary",
      title: "持久化 compact boundary 与 Summary",
      actor: "client",
      kind: "execute",
      summary: `Boundary 记录 ${preservedMessageUuids.length} 个 preserved message UUID，供 Resume 重建逻辑消息链。`,
      output: boundary,
      files: boundaryFiles,
      effects: [
        {
          label: "向本地 transcript 追加 boundary 与 synthetic compact-summary user message",
          state: "applied",
          reversible: false,
        },
      ],
      evidence: [
        BOUNDARY_EVIDENCE("client"),
        BOUNDARY_SHAPE_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "boundary",
      status: "success",
    },
    {
      id: "next-request",
      title: "等待 compact 后的下一条用户输入",
      actor: "client",
      kind: "complete",
      summary: "手动 /compact 先完成本地重建；只有用户随后继续输入时，下一次 Messages 请求才使用这份短历史。",
      input: {
        order: [
          "compact summary user message",
          "preserved messages",
          "attachments",
          "SessionStart hook results",
          "subsequent user input",
        ],
        compact_custom_instructions: request.customInstructions,
        next_user_input: "not yet supplied",
      },
      output: {
        active_history: "rebuilt",
        boundary_written: true,
      },
      files: boundaryFiles,
      evidence: [
        BOUNDARY_EVIDENCE("client"),
        CONTROL_FIXTURE_EVIDENCE("client"),
      ],
      visualTarget: "next",
      status: "success",
    },
  );

  return {
    parsed: {
      request,
      historyGroups: history.length,
      summarizedGroups: summarizedGroups.length,
      preservedGroups: preservedGroups.length,
      attachmentMode,
      preCompact,
    },
    steps,
    initialFiles,
      notes: [
        "这是根据 2.1.235 客户端规则生成的教学夹具，不是新采集的 wire dump。",
        "本场景只覆盖 manual compact 的 precomputed miss；precomputed hit 不会再次发送 Summary 请求。",
        "Boundary 中的 token 数是沙盘对当前夹具的估算，用于展示字段怎样随历史变化，不是 Claude Code 的实时 tokenizer 输出。",
      "附件失败只减少精确材料；它不会把已发生的外部副作用回滚。",
    ],
  };
}

export const compactScenario: LabScenario = registerLabScenario({
  id: "compact",
  title: "/compact 普通手动 miss 重建沙盘",
  description:
    "以 manual compact 的 precomputed miss 为范围，改变参数、历史长度、保留组和附件恢复状态，观察 Summary、preserved messages 与 compact boundary 怎样形成新上下文。",
  defaultInput: DEFAULT_INPUT,
  examples: [
    {
      label: "保留最近两个组并恢复附件",
      input: DEFAULT_INPUT,
      controls: {
        historyGroups: 9,
        preservedGroups: 2,
        attachmentRecovery: "exact",
        preCompact: "allow",
      },
    },
    {
      label: "长历史与附件降级",
      input: "/compact 继续核验 reverse/javascript/cli.readable.js 中的 fallback 和 Resume",
      controls: {
        historyGroups: 12,
        preservedGroups: 3,
        attachmentRecovery: "degraded",
        preCompact: "allow",
      },
    },
    {
      label: "PreCompact 阻止",
      input: "/compact 保留当前调查现场",
      controls: {
        historyGroups: 9,
        preservedGroups: 2,
        attachmentRecovery: "exact",
        preCompact: "block",
      },
    },
  ],
  initialFiles: BASE_FILES,
  graph: {
    src: "../assets/visuals/compact-lifecycle.svg",
    label: "Summary、近期消息、附件和 Boundary 的 compact 客户端流程",
  },
  controls: [
    {
      id: "historyGroups",
      label: "压缩前消息组",
      type: "select",
      defaultValue: 9,
      options: [
        { value: 6, label: "6 组" },
        { value: 9, label: "9 组" },
        { value: 12, label: "12 组" },
      ],
      description: "改变待总结前缀和压缩前 Boundary 统计。",
    },
    {
      id: "preservedGroups",
      label: "保留近期组",
      type: "select",
      defaultValue: 2,
      options: [
        { value: 1, label: "1 组" },
        { value: 2, label: "2 组" },
        { value: 3, label: "3 组" },
      ],
      description: "完整保留合法消息组，不拆散 tool_use/tool_result。",
    },
    {
      id: "attachmentRecovery",
      label: "附件恢复",
      type: "select",
      defaultValue: "exact",
      options: [
        { value: "exact", label: "精确恢复" },
        { value: "degraded", label: "部分失败后降级" },
        { value: "none", label: "不恢复文件" },
      ],
      description: "改变重建上下文里的精确文件材料。",
    },
    {
      id: "preCompact",
      label: "PreCompact",
      type: "select",
      defaultValue: "allow",
      options: [
        { value: "allow", label: "放行" },
        { value: "block", label: "阻止" },
      ],
      description: "阻止时保留原历史，不生成成功 Boundary。",
    },
  ],
  buildTrace: buildCompactTrace,
});

export default compactScenario;
