import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { unsafeSVG } from "lit/directives/unsafe-svg.js";
import { diffFiles, filesAtStep } from "./runtime/files";
import {
  createPlaybackController,
  type PlaybackSnapshot,
} from "./runtime/machine";
import { labScenarioRegistry } from "./runtime/registry";
import {
  normalizeExample,
  normalizeTrace,
  type LabControl,
  type LabControlValue,
  type LabControlValues,
  type LabEffect,
  type LabExample,
  type LabFileMap,
  type LabScenario,
  type LabScenarioRegistry,
  type LabStep,
  type LabTrace,
} from "./runtime/types";

type InspectorTab = "messages" | "context" | "control" | "files" | "diff" | "evidence";

const inspectorTabs: Array<[InspectorTab, string]> = [
  ["messages", "Messages"],
  ["context", "Context"],
  ["control", "Control"],
  ["files", "Files"],
  ["diff", "Diff"],
  ["evidence", "Evidence"],
];

const actorLabels: Record<string, string> = {
  user: "用户",
  client: "客户端",
  model: "模型",
  hook: "Hook",
  permission: "权限",
  tool: "工具",
  external: "外部状态",
};

const defaultGraph = `
<svg viewBox="0 0 1020 184" role="img" aria-label="Claude Code 客户端任务循环">
  <defs>
    <marker id="lab-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" />
    </marker>
  </defs>
  <g class="edge"><title>input-&gt;assemble</title><path d="M122 88 H168" marker-end="url(#lab-arrow)" /></g>
  <g class="edge"><title>assemble-&gt;request</title><path d="M282 88 H328" marker-end="url(#lab-arrow)" /></g>
  <g class="edge"><title>request-&gt;tool_use</title><path d="M442 88 H488" marker-end="url(#lab-arrow)" /></g>
  <g class="edge"><title>tool_use-&gt;permission</title><path d="M602 88 H648" marker-end="url(#lab-arrow)" /></g>
  <g class="edge"><title>permission-&gt;execute</title><path d="M762 88 H808" marker-end="url(#lab-arrow)" /></g>
  <g class="edge"><title>execute-&gt;tool_result</title><path d="M920 88 C980 88 980 156 864 156 H386 C340 156 342 116 368 102" marker-end="url(#lab-arrow)" /></g>
  <g class="node" id="input"><title>input</title><rect x="10" y="58" width="112" height="60" rx="4"/><text x="66" y="84">用户输入</text><text class="sub" x="66" y="103">task</text></g>
  <g class="node" id="assemble"><title>assemble</title><rect x="170" y="58" width="112" height="60" rx="4"/><text x="226" y="84">装配请求</text><text class="sub" x="226" y="103">context</text></g>
  <g class="node" id="request"><title>request</title><rect x="330" y="58" width="112" height="60" rx="4"/><text x="386" y="84">模型决策</text><text class="sub" x="386" y="103">stream</text></g>
  <g class="node" id="tool_use"><title>tool_use</title><rect x="490" y="58" width="112" height="60" rx="4"/><text x="546" y="84">工具提议</text><text class="sub" x="546" y="103">tool_use</text></g>
  <g class="node" id="permission"><title>permission</title><rect x="650" y="58" width="112" height="60" rx="4"/><text x="706" y="84">权限裁决</text><text class="sub" x="706" y="103">policy</text></g>
  <g class="node" id="execute"><title>execute</title><rect x="810" y="58" width="112" height="60" rx="4"/><text x="866" y="84">执行工具</text><text class="sub" x="866" y="103">effect</text></g>
  <g class="node" id="tool_result"><title>tool_result</title><rect x="488" y="128" width="116" height="48" rx="4"/><text x="546" y="157">结果回灌</text></g>
</svg>`;

function formatValue(value: unknown): string {
  if (value === undefined) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch (_error) {
    return String(value);
  }
}

function controlDefaults(controls: LabControl[] = []): LabControlValues {
  return Object.fromEntries(controls.map((control) => [control.id, control.defaultValue]));
}

function targetsFor(step?: LabStep): string[] {
  if (!step?.visualTarget) return step?.kind ? [step.kind] : [];
  return Array.isArray(step.visualTarget) ? step.visualTarget : [step.visualTarget];
}

function normalizeGraphTitle(value: string): string {
  return value.replace(/\s+/g, "").replaceAll("→", "->").toLowerCase();
}

export class ClaudeCodeAgentLab extends LitElement {
  static properties = {
    scenario: { type: String, reflect: true },
    headingLevel: { type: Number, attribute: "heading-level" },
    registry: { attribute: false },
    _scenarioData: { state: true },
    _taskInput: { state: true },
    _controls: { state: true },
    _trace: { state: true },
    _snapshot: { state: true },
    _activeTab: { state: true },
    _selectedFile: { state: true },
    _speed: { state: true },
    _svgMarkup: { state: true },
    _graphMessage: { state: true },
    _error: { state: true },
    _isFullscreen: { state: true },
    _reducedMotion: { state: true },
  };

  static styles = css`
    :host {
      display: block;
      width: 100%;
      min-width: 0;
      margin: 2rem 0;
      color: var(--cc-ink, #202722);
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
      --lab-bg: var(--cc-surface, #fff);
      --lab-bg-soft: var(--cc-surface-subtle, #f0f4f1);
      --lab-ink: var(--cc-ink, #202722);
      --lab-muted: var(--cc-ink-soft, #536159);
      --lab-line: var(--cc-line, #d5ddd7);
      --lab-line-strong: var(--cc-line-strong, #aebbb2);
      --lab-accent: var(--cc-green, #176b50);
      --lab-accent-strong: var(--cc-green-strong, #0f563f);
      --lab-accent-soft: var(--cc-green-soft, #e7f2ec);
      --lab-alert: var(--cc-coral, #c95e4d);
      --lab-alert-soft: var(--cc-coral-soft, #fbece8);
      --lab-code: var(--cc-code, #f0f3f1);
    }

    :host(:fullscreen) {
      margin: 0;
      padding: 18px;
      overflow: auto;
      background: var(--cc-paper, #f7f9f7);
    }

    * {
      box-sizing: border-box;
    }

    button,
    textarea,
    select,
    input {
      font: inherit;
      letter-spacing: 0;
    }

    button,
    select,
    input[type="checkbox"] {
      cursor: pointer;
    }

    button:focus-visible,
    textarea:focus-visible,
    select:focus-visible,
    input:focus-visible,
    a:focus-visible {
      outline: 2px solid var(--lab-accent);
      outline-offset: 2px;
    }

    .lab {
      min-width: 0;
      overflow: hidden;
      border: 1px solid var(--lab-line-strong);
      border-radius: 6px;
      background: var(--lab-bg);
      box-shadow: 0 16px 34px rgb(22 43 31 / 9%);
    }

    .lab__header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 18px;
      padding: 18px 20px 16px;
      border-bottom: 1px solid var(--lab-line);
    }

    .lab__identity {
      min-width: 0;
    }

    .lab__eyebrow {
      margin: 0 0 5px;
      color: var(--lab-accent);
      font-size: 11px;
      font-weight: 760;
      line-height: 1.2;
      text-transform: uppercase;
    }

    .lab__title {
      margin: 0;
      color: var(--lab-ink);
      font-size: 24px;
      font-weight: 720;
      line-height: 1.3;
    }

    .lab__description {
      max-width: 68ch;
      margin: 7px 0 0;
      color: var(--lab-muted);
      font-size: 14px;
      line-height: 1.6;
    }

    .icon-button,
    .transport-button {
      display: inline-grid;
      width: 36px;
      height: 36px;
      flex: 0 0 36px;
      place-items: center;
      padding: 0;
      border: 1px solid var(--lab-line);
      border-radius: 4px;
      background: var(--lab-bg);
      color: var(--lab-ink);
      font-size: 17px;
      line-height: 1;
    }

    .icon-button:hover,
    .transport-button:hover:not(:disabled) {
      border-color: var(--lab-accent);
      color: var(--lab-accent);
    }

    .transport-button:disabled {
      cursor: default;
      opacity: 0.38;
    }

    .composer {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      padding: 16px 20px;
      border-bottom: 1px solid var(--lab-line);
      background: color-mix(in srgb, var(--lab-bg) 88%, var(--lab-bg-soft));
    }

    .composer__input {
      display: grid;
      min-width: 0;
      gap: 7px;
    }

    .field-label,
    .control-label {
      color: var(--lab-ink);
      font-size: 12px;
      font-weight: 680;
      line-height: 1.35;
    }

    textarea {
      width: 100%;
      min-height: 76px;
      resize: vertical;
      padding: 10px 12px;
      border: 1px solid var(--lab-line-strong);
      border-radius: 4px;
      background: var(--lab-bg);
      color: var(--lab-ink);
      line-height: 1.55;
    }

    textarea::placeholder {
      color: var(--lab-muted);
    }

    .examples {
      display: flex;
      min-width: 0;
      gap: 7px;
      overflow-x: auto;
      padding: 1px 1px 3px;
      scrollbar-width: thin;
    }

    .example-button {
      max-width: 260px;
      flex: 0 0 auto;
      overflow: hidden;
      padding: 5px 8px;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      background: var(--lab-bg);
      color: var(--lab-muted);
      font-size: 11px;
      line-height: 1.35;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .example-button:hover {
      border-color: var(--lab-accent);
      color: var(--lab-accent);
    }

    .composer__actions {
      display: flex;
      align-items: flex-end;
      gap: 8px;
    }

    .command-button {
      display: inline-flex;
      min-height: 38px;
      align-items: center;
      justify-content: center;
      gap: 7px;
      padding: 8px 13px;
      border: 1px solid var(--lab-line-strong);
      border-radius: 4px;
      background: var(--lab-bg);
      color: var(--lab-ink);
      font-size: 13px;
      font-weight: 680;
    }

    .command-button--primary {
      border-color: var(--lab-accent);
      background: var(--lab-accent);
      color: #fff;
    }

    .command-button:hover {
      border-color: var(--lab-accent-strong);
      color: var(--lab-accent);
    }

    .command-button--primary:hover {
      background: var(--lab-accent-strong);
      color: #fff;
    }

    .scenario-controls {
      display: flex;
      min-width: 0;
      align-items: end;
      gap: 14px;
      padding: 12px 20px;
      overflow-x: auto;
      border-bottom: 1px solid var(--lab-line);
      scrollbar-width: thin;
    }

    .scenario-control {
      display: grid;
      flex: 0 0 auto;
      gap: 5px;
    }

    .scenario-control select,
    .speed-select {
      min-height: 32px;
      padding: 4px 28px 4px 8px;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      background: var(--lab-bg);
      color: var(--lab-ink);
      font-size: 12px;
    }

    .toggle-control {
      display: inline-flex;
      min-height: 32px;
      align-items: center;
      gap: 8px;
      padding: 4px 9px;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      background: var(--lab-bg);
      color: var(--lab-ink);
      font-size: 12px;
    }

    .transport {
      display: flex;
      min-width: 0;
      align-items: center;
      gap: 7px;
      padding: 10px 20px;
      border-bottom: 1px solid var(--lab-line);
      background: var(--lab-bg-soft);
    }

    .transport__count {
      min-width: 74px;
      color: var(--lab-muted);
      font-variant-numeric: tabular-nums;
      font-size: 12px;
      text-align: center;
    }

    .transport__progress {
      height: 3px;
      min-width: 70px;
      flex: 1;
      overflow: hidden;
      border-radius: 2px;
      background: var(--lab-line);
    }

    .transport__progress > span {
      display: block;
      width: var(--progress, 0%);
      height: 100%;
      background: var(--lab-accent);
      transition: width 180ms ease;
    }

    .graph-region {
      position: relative;
      min-width: 0;
      max-height: 520px;
      padding: 16px 20px 14px;
      overflow: auto;
      border-bottom: 1px solid var(--lab-line);
      background: var(--lab-bg);
      scrollbar-width: thin;
    }

    .graph-frame {
      display: grid;
      min-width: 0;
      justify-items: center;
      color: var(--lab-muted);
    }

    .graph-frame svg {
      display: block;
      width: min(100%, 680px);
      height: auto;
      max-height: none;
    }

    .graph-frame svg[data-lab-orientation="portrait"] {
      width: min(100%, 420px);
    }

    .graph-frame svg .node rect,
    .graph-frame svg .node polygon,
    .graph-frame svg .node ellipse,
    .graph-frame svg .node path {
      fill: var(--lab-bg) !important;
      stroke: var(--lab-line-strong) !important;
      stroke-width: 1.3 !important;
      transition: fill 180ms ease, stroke 180ms ease, filter 180ms ease;
    }

    .graph-frame svg .node text,
    .graph-frame svg text {
      fill: var(--lab-ink) !important;
      font-family: inherit !important;
    }

    .graph-frame svg:not([data-lab-orientation]) text {
      font-size: 13px;
      text-anchor: middle;
    }

    .graph-frame svg text.sub {
      fill: var(--lab-muted) !important;
      font-family: "SFMono-Regular", Consolas, monospace !important;
      font-size: 10px;
    }

    .graph-frame svg .edge path,
    .graph-frame svg .edge polyline {
      fill: none !important;
      stroke: var(--lab-line-strong) !important;
      stroke-width: 1.3 !important;
      transition: stroke 180ms ease, stroke-width 180ms ease;
    }

    .graph-frame svg marker path,
    .graph-frame svg .edge polygon {
      fill: var(--lab-line-strong) !important;
      stroke: var(--lab-line-strong) !important;
    }

    .graph-frame svg > g.graph > polygon {
      fill: transparent !important;
      stroke: none !important;
    }

    .graph-frame svg [data-lab-active="true"].node rect,
    .graph-frame svg [data-lab-active="true"].node polygon,
    .graph-frame svg [data-lab-active="true"].node ellipse,
    .graph-frame svg [data-lab-active="true"].node path,
    .graph-frame svg [data-lab-active="true"] > rect,
    .graph-frame svg [data-lab-active="true"] > polygon,
    .graph-frame svg [data-lab-active="true"] > ellipse {
      fill: var(--lab-accent-soft) !important;
      stroke: var(--lab-accent) !important;
      stroke-width: 2.7 !important;
      filter: drop-shadow(0 3px 5px rgb(23 107 80 / 18%));
    }

    .graph-frame svg [data-lab-active="true"].edge path,
    .graph-frame svg [data-lab-active="true"] > path {
      stroke: var(--lab-alert) !important;
      stroke-width: 2.6 !important;
    }

    .graph-message {
      position: sticky;
      left: 0;
      margin: 6px 0 0;
      color: var(--lab-muted);
      font-size: 11px;
    }

    .workbench {
      display: grid;
      min-height: 460px;
      grid-template-columns: minmax(240px, 0.78fr) minmax(0, 1.72fr);
    }

    .trace-panel {
      min-width: 0;
      border-right: 1px solid var(--lab-line);
      background: color-mix(in srgb, var(--lab-bg) 93%, var(--lab-bg-soft));
    }

    .panel-heading {
      display: flex;
      min-height: 44px;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin: 0;
      padding: 0 15px;
      border-bottom: 1px solid var(--lab-line);
      color: var(--lab-ink);
      font-size: 12px;
      font-weight: 720;
    }

    .panel-heading__state {
      color: var(--lab-muted);
      font-size: 10px;
      font-weight: 600;
    }

    .trace {
      max-height: 570px;
      margin: 0;
      padding: 14px 10px 18px 13px;
      overflow-y: auto;
      list-style: none;
      scrollbar-width: thin;
    }

    .trace__item {
      position: relative;
      min-width: 0;
      padding: 0 0 10px 20px;
    }

    .trace__item::before {
      position: absolute;
      top: 17px;
      bottom: -2px;
      left: 6px;
      width: 1px;
      background: var(--lab-line);
      content: "";
    }

    .trace__item:last-child::before {
      display: none;
    }

    .trace__dot {
      position: absolute;
      top: 12px;
      left: 2px;
      width: 9px;
      height: 9px;
      border: 2px solid var(--lab-line-strong);
      border-radius: 50%;
      background: var(--lab-bg);
    }

    .trace__item[data-state="passed"] .trace__dot {
      border-color: var(--lab-accent);
      background: var(--lab-accent);
    }

    .trace__item[data-state="current"] .trace__dot {
      width: 12px;
      height: 12px;
      top: 10px;
      left: 0;
      border-color: var(--lab-alert);
      background: var(--lab-alert-soft);
      box-shadow: 0 0 0 4px color-mix(in srgb, var(--lab-alert-soft) 72%, transparent);
    }

    .trace__button {
      display: block;
      width: 100%;
      min-width: 0;
      padding: 7px 8px 8px;
      border: 1px solid transparent;
      border-radius: 3px;
      background: transparent;
      color: var(--lab-ink);
      text-align: left;
    }

    .trace__button:hover {
      border-color: var(--lab-line);
      background: var(--lab-bg);
    }

    .trace__item[data-state="current"] .trace__button {
      border-color: var(--lab-line-strong);
      background: var(--lab-bg);
    }

    .trace__meta {
      display: flex;
      min-width: 0;
      align-items: center;
      gap: 6px;
      margin-bottom: 3px;
      color: var(--lab-muted);
      font-size: 9px;
      font-weight: 740;
      line-height: 1.25;
      text-transform: uppercase;
    }

    .trace__actor {
      color: var(--lab-accent);
    }

    .trace__title {
      overflow-wrap: anywhere;
      font-size: 12px;
      font-weight: 670;
      line-height: 1.4;
    }

    .trace__summary {
      display: -webkit-box;
      margin-top: 3px;
      overflow: hidden;
      color: var(--lab-muted);
      font-size: 10px;
      line-height: 1.45;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }

    .inspector {
      min-width: 0;
      background: var(--lab-bg);
    }

    .tabs {
      display: flex;
      min-width: 0;
      overflow-x: auto;
      border-bottom: 1px solid var(--lab-line);
      scrollbar-width: thin;
    }

    .tab {
      min-height: 44px;
      flex: 0 0 auto;
      padding: 0 13px;
      border: 0;
      border-bottom: 2px solid transparent;
      background: transparent;
      color: var(--lab-muted);
      font-size: 11px;
      font-weight: 670;
    }

    .tab:hover,
    .tab[aria-selected="true"] {
      color: var(--lab-accent);
    }

    .tab[aria-selected="true"] {
      border-bottom-color: var(--lab-accent);
    }

    .inspector__body {
      min-width: 0;
      min-height: 415px;
      max-height: 570px;
      padding: 16px;
      overflow: auto;
      scrollbar-width: thin;
    }

    .inspector__body[hidden] {
      display: none;
    }

    .empty-state {
      display: grid;
      min-height: 260px;
      place-items: center;
      color: var(--lab-muted);
      font-size: 13px;
      text-align: center;
    }

    .data-section + .data-section {
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid var(--lab-line);
    }

    .data-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 7px;
      color: var(--lab-muted);
      font-size: 10px;
      font-weight: 760;
      line-height: 1.35;
      text-transform: uppercase;
    }

    .data-value,
    .code-view {
      max-width: 100%;
      margin: 0;
      padding: 11px 12px;
      overflow: auto;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      background: var(--lab-code);
      color: var(--lab-ink);
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 11px;
      line-height: 1.55;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      scrollbar-width: thin;
    }

    .summary-text {
      margin: 0;
      color: var(--lab-ink);
      font-size: 13px;
      line-height: 1.65;
    }

    .fact-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1px;
      overflow: hidden;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      background: var(--lab-line);
    }

    .fact {
      min-width: 0;
      padding: 9px 10px;
      background: var(--lab-bg);
    }

    .fact dt {
      margin: 0 0 3px;
      color: var(--lab-muted);
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .fact dd {
      margin: 0;
      overflow-wrap: anywhere;
      color: var(--lab-ink);
      font-size: 12px;
      line-height: 1.45;
    }

    .effects,
    .evidence-list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .effect {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 8px 10px;
      border-left: 3px solid var(--lab-line-strong);
      background: var(--lab-bg-soft);
      color: var(--lab-ink);
      font-size: 12px;
      line-height: 1.5;
    }

    .effect[data-state="applied"] {
      border-left-color: var(--lab-accent);
    }

    .effect[data-state="blocked"],
    .effect[data-state="failed"] {
      border-left-color: var(--lab-alert);
    }

    .file-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 9px;
    }

    .file-select {
      min-width: 0;
      max-width: 100%;
      padding: 5px 28px 5px 8px;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      background: var(--lab-bg);
      color: var(--lab-ink);
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 11px;
    }

    .file-count,
    .diff-stats {
      flex: 0 0 auto;
      color: var(--lab-muted);
      font-size: 10px;
      font-variant-numeric: tabular-nums;
    }

    .diff-file + .diff-file {
      margin-top: 16px;
    }

    .diff-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 7px 9px;
      border: 1px solid var(--lab-line);
      border-bottom: 0;
      border-radius: 3px 3px 0 0;
      background: var(--lab-bg-soft);
      color: var(--lab-ink);
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 10px;
    }

    .diff-lines {
      margin: 0;
      padding: 6px 0;
      overflow: auto;
      border: 1px solid var(--lab-line);
      border-radius: 0 0 3px 3px;
      background: var(--lab-code);
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 10px;
      line-height: 1.5;
      scrollbar-width: thin;
    }

    .diff-line {
      display: grid;
      min-width: max-content;
      grid-template-columns: 38px 38px 18px minmax(300px, 1fr);
      padding-right: 10px;
      white-space: pre;
    }

    .diff-line[data-kind="add"] {
      background: color-mix(in srgb, var(--lab-accent-soft) 76%, transparent);
    }

    .diff-line[data-kind="remove"] {
      background: color-mix(in srgb, var(--lab-alert-soft) 80%, transparent);
    }

    .line-number {
      padding-right: 7px;
      color: var(--lab-muted);
      text-align: right;
      user-select: none;
    }

    .line-sign {
      color: var(--lab-muted);
      text-align: center;
      user-select: none;
    }

    .evidence-link {
      display: block;
      padding: 10px 11px;
      border: 1px solid var(--lab-line);
      border-radius: 3px;
      color: var(--lab-accent);
      font-size: 12px;
      line-height: 1.45;
      text-decoration: none;
    }

    .evidence-link:hover {
      border-color: var(--lab-accent);
    }

    .evidence-link small {
      display: block;
      margin-top: 3px;
      color: var(--lab-muted);
      font-size: 10px;
    }

    .error {
      margin: 0;
      padding: 12px 20px;
      border-bottom: 1px solid color-mix(in srgb, var(--lab-alert) 42%, var(--lab-line));
      background: var(--lab-alert-soft);
      color: var(--lab-ink);
      font-size: 12px;
      line-height: 1.5;
    }

    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }

    @media (max-width: 760px) {
      :host {
        margin: 1.5rem 0;
      }

      .lab__header,
      .composer,
      .scenario-controls,
      .transport,
      .graph-region {
        padding-inline: 13px;
      }

      .lab__title {
        font-size: 20px;
      }

      .composer {
        grid-template-columns: minmax(0, 1fr);
      }

      .composer__actions {
        align-items: stretch;
      }

      .command-button {
        flex: 1;
      }

      .scenario-controls {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        align-items: start;
        gap: 10px;
        overflow-x: visible;
      }

      .scenario-control {
        min-width: 0;
      }

      .scenario-control select,
      .toggle-control {
        width: 100%;
        min-width: 0;
      }

      .workbench {
        grid-template-columns: minmax(0, 1fr);
      }

      .trace-panel {
        border-right: 0;
        border-bottom: 1px solid var(--lab-line);
      }

      .trace {
        max-height: 310px;
      }

      .graph-region {
        max-height: 420px;
      }

      .inspector__body {
        min-height: 360px;
        max-height: none;
        padding: 13px;
      }

      .fact-grid {
        grid-template-columns: minmax(0, 1fr);
      }

      .transport {
        gap: 5px;
      }

      .transport__count {
        min-width: 58px;
      }

      .speed-select {
        max-width: 66px;
        padding-right: 20px;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *,
      *::before,
      *::after {
        scroll-behavior: auto !important;
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
      }
    }
  `;

  declare scenario: string;
  declare headingLevel: number;
  declare registry: LabScenarioRegistry;
  declare _scenarioData?: LabScenario;
  declare _taskInput: string;
  declare _controls: LabControlValues;
  declare _trace: LabTrace;
  declare _snapshot: PlaybackSnapshot;
  declare _activeTab: InspectorTab;
  declare _selectedFile: string;
  declare _speed: number;
  declare _svgMarkup: string;
  declare _graphMessage: string;
  declare _error: string;
  declare _isFullscreen: boolean;
  declare _reducedMotion: boolean;

  readonly #playback = createPlaybackController();
  #registryUnsubscribe?: () => void;
  #playbackUnsubscribe?: { unsubscribe(): void };
  #timer?: number;
  #graphController?: AbortController;
  #motionQuery?: MediaQueryList;
  #lastScrolledIndex = -2;

  constructor() {
    super();
    this.scenario = "";
    this.headingLevel = 3;
    this.registry = labScenarioRegistry;
    this._scenarioData = undefined;
    this._taskInput = "";
    this._controls = {};
    this._trace = { steps: [] };
    this._activeTab = "messages";
    this._selectedFile = "";
    this._speed = 1;
    this._svgMarkup = defaultGraph;
    this._graphMessage = "";
    this._error = "";
    this._isFullscreen = false;
    this._reducedMotion = false;
    this.#playback.start();
    this._snapshot = this.#playback.getSnapshot();
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.tabIndex = 0;
    this.setAttribute("role", "region");
    this.setAttribute("aria-label", "Claude Code 交互机制沙盘");
    this.addEventListener("keydown", this.#onKeydown);
    document.addEventListener("fullscreenchange", this.#onFullscreenChange);

    this.#playbackUnsubscribe = this.#playback.subscribe((snapshot) => {
      this._snapshot = snapshot;
      this.#syncPlaybackTimer();
    });
    this.#bindRegistry();
    this.#observeReducedMotion();
    this.#resolveScenario();
  }

  disconnectedCallback(): void {
    this.removeEventListener("keydown", this.#onKeydown);
    document.removeEventListener("fullscreenchange", this.#onFullscreenChange);
    this.#registryUnsubscribe?.();
    this.#playbackUnsubscribe?.unsubscribe();
    this.#graphController?.abort();
    this.#clearTimer();
    this.#motionQuery?.removeEventListener("change", this.#onMotionChange);
    super.disconnectedCallback();
  }

  protected updated(changed: PropertyValues): void {
    if (changed.has("scenario")) this.#resolveScenario();
    if (changed.has("registry")) {
      this.#bindRegistry();
      this.#resolveScenario();
    }
    if (changed.has("_snapshot") || changed.has("_svgMarkup")) {
      this.#highlightGraph();
      this.#scrollActiveTrace();
      this.#ensureSelectedFile();
    }
  }

  #bindRegistry(): void {
    this.#registryUnsubscribe?.();
    this.#registryUnsubscribe = this.registry.subscribe(() => this.#resolveScenario());
  }

  #observeReducedMotion(): void {
    if (!window.matchMedia) return;
    this.#motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    this._reducedMotion = this.#motionQuery.matches;
    this.#motionQuery.addEventListener("change", this.#onMotionChange);
  }

  #onMotionChange = (event: MediaQueryListEvent): void => {
    this._reducedMotion = event.matches;
  };

  #resolveScenario(): void {
    const selected = this.scenario
      ? this.registry.get(this.scenario)
      : this.registry.list()[0];
    if (!selected || selected === this._scenarioData) return;

    this._scenarioData = selected;
    this._taskInput = selected.defaultInput;
    this._controls = controlDefaults(selected.controls);
    this._trace = { steps: [], initialFiles: selected.initialFiles };
    this._error = "";
    this._activeTab = "messages";
    this._selectedFile = Object.keys(selected.initialFiles)[0] ?? "";
    this.#playback.send({ type: "LOAD", total: 0 });
    void this.#loadGraph(selected);
    this.#compileTrace(false);
  }

  #compileTrace(autoplay: boolean): void {
    const scenario = this._scenarioData;
    if (!scenario) return;
    const input = this._taskInput.trim();
    if (!input) {
      this._error = "请输入要交给 Claude Code 的任务。";
      return;
    }

    try {
      const trace = normalizeTrace(
        scenario.buildTrace(input, { ...this._controls }),
        scenario.initialFiles,
      );
      if (!trace.steps.length) throw new Error("场景没有生成执行步骤");
      const ids = new Set<string>();
      for (const step of trace.steps) {
        if (!step.id || !step.title || !step.actor || !step.kind) {
          throw new Error("场景步骤缺少 id、title、actor 或 kind");
        }
        if (ids.has(step.id)) throw new Error(`场景步骤 id 重复：${step.id}`);
        ids.add(step.id);
      }

      this._trace = trace;
      this._error = "";
      this._selectedFile = Object.keys(trace.initialFiles ?? scenario.initialFiles)[0] ?? "";
      this.#playback.send({ type: "LOAD", total: trace.steps.length });
      if (autoplay) {
        this.#playback.send({ type: "NEXT" });
        this.#playback.send({ type: "PLAY" });
      }
    } catch (error) {
      this._trace = { steps: [], initialFiles: scenario.initialFiles };
      this.#playback.send({ type: "LOAD", total: 0 });
      this._error = error instanceof Error ? error.message : "场景构建失败";
    }
  }

  #reset(): void {
    const scenario = this._scenarioData;
    if (!scenario) return;
    this._taskInput = scenario.defaultInput;
    this._controls = controlDefaults(scenario.controls);
    this._error = "";
    this._activeTab = "messages";
    this._selectedFile = Object.keys(scenario.initialFiles)[0] ?? "";
    this.#compileTrace(false);
  }

  #clearTimer(): void {
    if (this.#timer !== undefined) window.clearTimeout(this.#timer);
    this.#timer = undefined;
  }

  #syncPlaybackTimer(): void {
    this.#clearTimer();
    if (!this._snapshot.matches("playing")) return;
    this.#timer = window.setTimeout(() => {
      this.#playback.send({ type: "TICK" });
    }, Math.round(1350 / this._speed));
  }

  #togglePlayback(): void {
    this.#playback.send({
      type: this._snapshot.matches("playing") ? "PAUSE" : "PLAY",
    });
  }

  #seek(index: number): void {
    this.#playback.send({ type: "SEEK", index });
  }

  #selectExample(example: LabExample): void {
    this._taskInput = example.input;
    this._controls = {
      ...this._controls,
      ...(example.controls ?? {}),
    };
    this.#compileTrace(true);
  }

  #setControl(control: LabControl, value: LabControlValue): void {
    this._controls = { ...this._controls, [control.id]: value };
    this.#compileTrace(true);
  }

  #onKeydown = (event: KeyboardEvent): void => {
    const interactiveTarget = event.composedPath().some(
      (node) =>
        node instanceof HTMLElement &&
        (node.matches(
          "a[href], button, input, textarea, select, [contenteditable='true'], [role='button'], [role='link'], [role='tab'], [role='checkbox'], [role='switch'], [role='slider']",
        ) || node.isContentEditable),
    );
    if (interactiveTarget) return;

    if (event.key === "ArrowRight") {
      event.preventDefault();
      this.#playback.send({ type: "NEXT" });
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      this.#playback.send({ type: "PREV" });
    } else if (event.key === " ") {
      event.preventDefault();
      this.#togglePlayback();
    } else if (event.key === "Home") {
      event.preventDefault();
      this.#reset();
    } else if (event.key.toLowerCase() === "f") {
      event.preventDefault();
      void this.#toggleFullscreen();
    }
  };

  #onFullscreenChange = (): void => {
    this._isFullscreen = document.fullscreenElement === this;
  };

  async #toggleFullscreen(): Promise<void> {
    try {
      if (document.fullscreenElement === this && document.exitFullscreen) {
        await document.exitFullscreen();
      } else if (this.requestFullscreen) {
        await this.requestFullscreen();
      }
    } catch (_error) {
      this._isFullscreen = false;
    }
  }

  async #loadGraph(scenario: LabScenario): Promise<void> {
    this.#graphController?.abort();
    this.#graphController = new AbortController();
    this._graphMessage = "";

    const graph = scenario.graph;
    if (!graph) {
      this._svgMarkup = defaultGraph;
      return;
    }
      const source = typeof graph === "string" ? graph : graph.src;
      const graphLabel =
        typeof graph === "string" ? `${scenario.title} 流程图` : graph.label;
    try {
      const bundleUrl = new URL(import.meta.url);
      const assetMarker = "/assets/";
      const markerIndex = bundleUrl.pathname.indexOf(assetMarker);
      const bundleRoot = markerIndex >= 0
        ? new URL(
            bundleUrl.pathname.slice(0, markerIndex + assetMarker.length),
            bundleUrl.origin,
          )
        : new URL("./", bundleUrl);
      const rootRelativeSource = source.replace(/^(?:\.\.?\/)+/u, "");
      const bundleRelativeSource = markerIndex >= 0
        ? rootRelativeSource.replace(/^assets\//u, "")
        : rootRelativeSource;
      const candidates = [
        new URL(source, document.baseURI),
        new URL(bundleRelativeSource, bundleRoot),
      ].filter((url, index, urls) =>
        url.origin === window.location.origin &&
        urls.findIndex((candidate) => candidate.href === url.href) === index,
      );
      if (!candidates.length) throw new Error("流程图必须来自本站");

      let markup = "";
      let lastStatus = 0;
      for (const url of candidates) {
        const response = await fetch(url, {
          credentials: "same-origin",
          signal: this.#graphController.signal,
        });
        lastStatus = response.status;
        if (!response.ok) continue;
        try {
          markup = this.#sanitizeSvg(await response.text(), graphLabel);
          break;
        } catch (_error) {
          continue;
        }
      }
      if (!markup) throw new Error(`流程图返回 ${lastStatus || "空响应"}`);
      if (scenario !== this._scenarioData) return;
      this._svgMarkup = markup;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      this._svgMarkup = defaultGraph;
      this._graphMessage = "场景图未载入，当前显示通用任务循环。";
    }
  }

  #sanitizeSvg(markup: string, label: string): string {
    const documentNode = new DOMParser().parseFromString(markup, "image/svg+xml");
    if (documentNode.querySelector("parsererror")) throw new Error("流程图不是有效 SVG");
    const svg = documentNode.documentElement;
    if (svg.localName !== "svg") throw new Error("流程图缺少 SVG 根节点");

    svg.querySelectorAll("script, foreignObject, iframe, object, embed").forEach((node) => node.remove());
    svg.querySelectorAll("*").forEach((node) => {
      for (const attribute of [...node.attributes]) {
        const name = attribute.name.toLowerCase();
        if (name.startsWith("on")) node.removeAttribute(attribute.name);
        if ((name === "href" || name.endsWith(":href")) && !attribute.value.startsWith("#")) {
          node.removeAttribute(attribute.name);
        }
      }
    });
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    const viewBox = (svg.getAttribute("viewBox") ?? "")
      .trim()
      .split(/[\s,]+/u)
      .map(Number);
    if (
      viewBox.length === 4 &&
      viewBox.every(Number.isFinite) &&
      viewBox[2] > 0 &&
      viewBox[3] > 0
    ) {
      svg.setAttribute(
        "data-lab-orientation",
        viewBox[2] / viewBox[3] < 0.75 ? "portrait" : "landscape",
      );
    }
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    return new XMLSerializer().serializeToString(svg);
  }

  #activateInspectorTab(id: InspectorTab, focus = false): void {
    this._activeTab = id;
    if (!focus) return;
    void this.updateComplete.then(() => {
      this.renderRoot.querySelector<HTMLButtonElement>(`#tab-${id}`)?.focus();
    });
  }

  #onInspectorTabKeydown(event: KeyboardEvent, index: number): void {
    let nextIndex: number | undefined;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % inspectorTabs.length;
    else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + inspectorTabs.length) % inspectorTabs.length;
    } else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = inspectorTabs.length - 1;
    if (nextIndex === undefined) return;
    event.preventDefault();
    this.#activateInspectorTab(inspectorTabs[nextIndex][0], true);
  }

  #highlightGraph(): void {
    requestAnimationFrame(() => {
      const svg = this.renderRoot.querySelector(".graph-frame svg");
      if (!svg) return;
      const targets = new Set(targetsFor(this.#currentStep()).map(normalizeGraphTitle));
      svg.querySelectorAll("[data-lab-active]").forEach((node) => node.removeAttribute("data-lab-active"));
      if (!targets.size) return;

      svg.querySelectorAll<SVGElement>("g, [id]").forEach((node) => {
        const identities = [
          node.id,
          node.getAttribute("data-step") ?? "",
          node.querySelector(":scope > title")?.textContent ?? "",
        ].map(normalizeGraphTitle);
        if (identities.some((identity) => targets.has(identity))) {
          node.setAttribute("data-lab-active", "true");
        }
      });
      const activeNode =
        svg.querySelector<SVGElement>(".node[data-lab-active='true']") ??
        svg.querySelector<SVGElement>("[data-lab-active='true']");
      const region = this.renderRoot.querySelector<HTMLElement>(".graph-region");
      if (activeNode && region) {
        const activeRect = activeNode.getBoundingClientRect();
        const regionRect = region.getBoundingClientRect();
        region.scrollTo({
          top:
            region.scrollTop +
            activeRect.top -
            regionRect.top -
            (regionRect.height - activeRect.height) / 2,
          left:
            region.scrollLeft +
            activeRect.left -
            regionRect.left -
            (regionRect.width - activeRect.width) / 2,
          behavior: this._reducedMotion ? "auto" : "smooth",
        });
      }
    });
  }

  #scrollActiveTrace(): void {
    const index = this._snapshot.context.index;
    if (index < 0 || index === this.#lastScrolledIndex) return;
    this.#lastScrolledIndex = index;
    requestAnimationFrame(() => {
      const trace = this.renderRoot.querySelector<HTMLElement>(".trace");
      const item = this.renderRoot.querySelector<HTMLElement>(
        `[data-step-index="${index}"]`,
      );
      if (!trace || !item) return;
      const traceRect = trace.getBoundingClientRect();
      const itemRect = item.getBoundingClientRect();
      if (itemRect.top >= traceRect.top && itemRect.bottom <= traceRect.bottom) return;
      trace.scrollTo({
        top:
          trace.scrollTop +
          itemRect.top -
          traceRect.top -
          (traceRect.height - itemRect.height) / 2,
        behavior: this._reducedMotion ? "auto" : "smooth",
      });
    });
  }

  #currentStep(): LabStep | undefined {
    return this._trace.steps[this._snapshot.context.index];
  }

  #initialFiles(): LabFileMap {
    return this._trace.initialFiles ?? this._scenarioData?.initialFiles ?? {};
  }

  #currentFiles(): LabFileMap {
    return filesAtStep(this.#initialFiles(), this._trace.steps, this._snapshot.context.index);
  }

  #ensureSelectedFile(): void {
    const files = this.#currentFiles();
    if (!this._selectedFile || !(this._selectedFile in files)) {
      this._selectedFile = Object.keys(files)[0] ?? "";
    }
  }

  #renderControl(control: LabControl) {
    const value = this._controls[control.id] ?? control.defaultValue;
    if (control.type === "toggle") {
      return html`
        <label class="scenario-control" title=${control.description ?? ""}>
          <span class="control-label">${control.label}</span>
          <span class="toggle-control">
            <input
              type="checkbox"
              .checked=${Boolean(value)}
              @change=${(event: Event) =>
                this.#setControl(control, (event.currentTarget as HTMLInputElement).checked)}
            />
            <span>${Boolean(value) ? "开启" : "关闭"}</span>
          </span>
        </label>
      `;
    }

    return html`
      <label class="scenario-control" title=${control.description ?? ""}>
        <span class="control-label">${control.label}</span>
        <select
          .value=${String(value)}
          @change=${(event: Event) => {
            const selected = (event.currentTarget as HTMLSelectElement).value;
            const original = control.options?.find((option) => String(option.value) === selected)?.value;
            this.#setControl(control, original ?? selected);
          }}
        >
          ${(control.options ?? []).map(
            (option) => html`
              <option
                value=${String(option.value)}
                ?selected=${String(option.value) === String(value)}
              >${option.label}</option>
            `,
          )}
        </select>
      </label>
    `;
  }

  #renderTrace() {
    const activeIndex = this._snapshot.context.index;
    return html`
      <section class="trace-panel" aria-label="执行轨迹">
        <h3 class="panel-heading">
          <span>执行轨迹</span>
          <span class="panel-heading__state">${this.#playbackLabel()}</span>
        </h3>
        <ol class="trace">
          ${this._trace.steps.map((step, index) => {
            const state = index < activeIndex ? "passed" : index === activeIndex ? "current" : "future";
            return html`
              <li class="trace__item" data-state=${state} data-step-index=${index}>
                <span class="trace__dot" aria-hidden="true"></span>
                <button
                  class="trace__button"
                  type="button"
                  aria-current=${state === "current" ? "step" : nothing}
                  @click=${() => this.#seek(index)}
                >
                  <span class="trace__meta">
                    <span class="trace__actor">${actorLabels[step.actor] ?? step.actor}</span>
                    <span>${step.kind}</span>
                  </span>
                  <span class="trace__title">${step.title}</span>
                  ${step.summary ? html`<span class="trace__summary">${step.summary}</span>` : nothing}
                </button>
              </li>
            `;
          })}
        </ol>
      </section>
    `;
  }

  #playbackLabel(): string {
    if (this._snapshot.matches("playing")) return "运行中";
    if (this._snapshot.matches("completed")) return "已结束";
    if (this._snapshot.context.index < 0) return "待运行";
    return "已暂停";
  }

  #renderInspector() {
    return html`
      <section class="inspector" aria-label="步骤检查器">
        <div class="tabs" role="tablist" aria-label="检查器视图">
          ${inspectorTabs.map(
            ([id, label], index) => html`
              <button
                class="tab"
                id="tab-${id}"
                type="button"
                role="tab"
                aria-selected=${this._activeTab === id ? "true" : "false"}
                aria-controls="panel-${id}"
                tabindex=${this._activeTab === id ? "0" : "-1"}
                @click=${() => this.#activateInspectorTab(id)}
                @keydown=${(event: KeyboardEvent) =>
                  this.#onInspectorTabKeydown(event, index)}
              >${label}</button>
            `,
          )}
        </div>
        ${inspectorTabs.map(([id]) => html`
          <div
            class="inspector__body"
            id="panel-${id}"
            role="tabpanel"
            aria-labelledby="tab-${id}"
            ?hidden=${this._activeTab !== id}
          >
            ${this.#renderInspectorBody(id)}
          </div>
        `)}
      </section>
    `;
  }

  #renderInspectorBody(activeTab: InspectorTab) {
    const step = this.#currentStep();
    if (!step && activeTab !== "files" && activeTab !== "diff") {
      return html`<div class="empty-state">运行或选择一个步骤后查看状态。</div>`;
    }
    switch (activeTab) {
      case "messages": return this.#renderMessages(step);
      case "context": return this.#renderContext(step);
      case "control": return this.#renderControlInspector(step);
      case "files": return this.#renderFiles();
      case "diff": return this.#renderDiff();
      case "evidence": return this.#renderEvidence(step);
    }
  }

  #dataSection(title: string, value: unknown) {
    if (value === undefined) return nothing;
    return html`
      <section class="data-section">
        <h4 class="data-title">${title}</h4>
        <pre class="data-value">${formatValue(value)}</pre>
      </section>
    `;
  }

  #renderMessages(step?: LabStep) {
    if (!step) return nothing;
    return html`
      ${step.summary || step.detail ? html`
        <section class="data-section">
          <h4 class="data-title">当前事件</h4>
          <p class="summary-text">${step.detail ?? step.summary}</p>
        </section>
      ` : nothing}
      ${step.tool_use_id ? this.#dataSection("tool_use_id", step.tool_use_id) : nothing}
      ${step.tool ? this.#dataSection("工具", step.tool) : nothing}
      ${this.#dataSection("Input", step.input)}
      ${this.#dataSection("Output", step.output)}
    `;
  }

  #renderContext(step?: LabStep) {
    return html`
      ${this.#dataSection("输入解析", this._trace.parsed)}
      ${this.#dataSection("Before", step?.before)}
      ${this.#dataSection("After", step?.after)}
      ${this._trace.notes?.length ? this.#dataSection("场景注记", this._trace.notes) : nothing}
    `;
  }

  #renderControlInspector(step?: LabStep) {
    if (!step) return nothing;
    const effects = step.effects ?? [];
    return html`
      <dl class="fact-grid">
        <div class="fact"><dt>Actor</dt><dd>${actorLabels[step.actor] ?? step.actor}</dd></div>
        <div class="fact"><dt>Kind</dt><dd>${step.kind}</dd></div>
        <div class="fact"><dt>Status</dt><dd>${step.status ?? "success"}</dd></div>
        <div class="fact"><dt>Visual</dt><dd>${targetsFor(step).join(", ") || "—"}</dd></div>
      </dl>
      ${effects.length ? html`
        <section class="data-section">
          <h4 class="data-title">Effects</h4>
          <ul class="effects">
            ${effects.map((effect) => {
              const item: LabEffect = typeof effect === "string" ? { label: effect } : effect;
              return html`
                <li class="effect" data-state=${item.state ?? "proposed"}>
                  <span>${item.label}</span>
                  ${item.reversible === false ? html`<strong>不可由对话回滚</strong>` : nothing}
                </li>
              `;
            })}
          </ul>
        </section>
      ` : nothing}
    `;
  }

  #renderFiles() {
    const files = this.#currentFiles();
    const paths = Object.keys(files).sort((left, right) => left.localeCompare(right));
    if (!paths.length) return html`<div class="empty-state">这个场景没有虚拟项目文件。</div>`;
    const selected = paths.includes(this._selectedFile) ? this._selectedFile : paths[0];
    return html`
      <div class="file-toolbar">
        <select
          class="file-select"
          aria-label="选择虚拟文件"
          .value=${selected}
          @change=${(event: Event) => (this._selectedFile = (event.currentTarget as HTMLSelectElement).value)}
        >
          ${paths.map((path) => html`<option value=${path}>${path}</option>`)}
        </select>
        <span class="file-count">${paths.length} files</span>
      </div>
      <pre class="code-view">${files[selected]}</pre>
    `;
  }

  #renderDiff() {
    const changes = diffFiles(this.#initialFiles(), this.#currentFiles());
    if (!changes.length) return html`<div class="empty-state">当前步骤尚未改变虚拟文件。</div>`;
    return html`
      ${changes.map((change) => html`
        <section class="diff-file">
          <header class="diff-header">
            <span>${change.path}</span>
            <span class="diff-stats">+${change.additions} / -${change.removals}</span>
          </header>
          <pre class="diff-lines" aria-label="${change.path} 的差异">${change.lines.map((line) => html`<span class="diff-line" data-kind=${line.kind}><span class="line-number">${line.oldLine ?? ""}</span><span class="line-number">${line.newLine ?? ""}</span><span class="line-sign">${line.kind === "add" ? "+" : line.kind === "remove" ? "−" : " "}</span><span>${line.text}</span></span>`)}</pre>
        </section>
      `)}
    `;
  }

  #renderEvidence(step?: LabStep) {
    const evidence = step?.evidence ?? [];
    if (!evidence.length) return html`<div class="empty-state">本步没有单独的证据链接。</div>`;
    return html`
      <ul class="evidence-list">
        ${evidence.map((item) => html`
          <li>
            <a class="evidence-link" href=${item.href} target="_blank" rel="noopener noreferrer">
              ${item.label}
              ${item.detail ? html`<small>${item.detail}</small>` : nothing}
            </a>
          </li>
        `)}
      </ul>
    `;
  }

  render() {
    const scenario = this._scenarioData;
    if (!scenario) {
      return html`
        <section class="lab">
          <div class="empty-state">正在装入交互场景…</div>
        </section>
      `;
    }

    const index = this._snapshot.context.index;
    const total = this._trace.steps.length;
    const progress = total ? `${Math.max(0, ((index + 1) / total) * 100)}%` : "0%";
    const examples = scenario.examples.map(normalizeExample);
    const playing = this._snapshot.matches("playing");

    return html`
      <section class="lab">
        <header class="lab__header">
          <div class="lab__identity">
            <p class="lab__eyebrow">Teaching simulation · ${scenario.id}</p>
            <div
              class="lab__title"
              role="heading"
              aria-level=${Math.min(6, Math.max(1, this.headingLevel || 3))}
            >${scenario.title}</div>
            <p class="lab__description">${scenario.description}</p>
          </div>
          ${typeof this.requestFullscreen === "function" && typeof document.exitFullscreen === "function" ? html`
            <button
              class="icon-button"
              type="button"
              aria-label=${this._isFullscreen ? "退出全屏" : "全屏查看"}
              title=${this._isFullscreen ? "退出全屏" : "全屏查看"}
              @click=${this.#toggleFullscreen}
            >${this._isFullscreen ? "⤢" : "⛶"}</button>
          ` : nothing}
        </header>

        <div class="composer">
          <div class="composer__input">
            <label class="field-label" for="lab-task-input">任务</label>
            <textarea
              id="lab-task-input"
              .value=${this._taskInput}
              @input=${(event: Event) => (this._taskInput = (event.currentTarget as HTMLTextAreaElement).value)}
              @keydown=${(event: KeyboardEvent) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  this.#compileTrace(true);
                }
              }}
            ></textarea>
            ${examples.length ? html`
              <span class="examples" aria-label="示例任务">
                ${examples.map((example) => html`
                  <button
                    class="example-button"
                    type="button"
                    title=${example.input}
                    @click=${() => this.#selectExample(example)}
                  >${example.label}</button>
                `)}
              </span>
            ` : nothing}
          </div>
          <div class="composer__actions">
            <button class="command-button" type="button" @click=${this.#reset}>
              <span aria-hidden="true">↺</span><span>重置</span>
            </button>
            <button class="command-button command-button--primary" type="button" @click=${() => this.#compileTrace(true)}>
              <span aria-hidden="true">▶</span><span>运行</span>
            </button>
          </div>
        </div>

        ${scenario.controls?.length ? html`
          <div class="scenario-controls" aria-label="场景控制项">
            ${scenario.controls.map((control) => this.#renderControl(control))}
          </div>
        ` : nothing}

        ${this._error ? html`<p class="error" role="alert">${this._error}</p>` : nothing}

        <div class="transport" aria-label="回放控制">
          <button class="transport-button" type="button" aria-label="上一步" title="上一步" ?disabled=${index < 0} @click=${() => this.#playback.send({ type: "PREV" })}>←</button>
          <button class="transport-button" type="button" aria-label=${playing ? "暂停" : "播放"} title=${playing ? "暂停" : "播放"} ?disabled=${!total || this._snapshot.matches("completed")} @click=${this.#togglePlayback}>${playing ? "Ⅱ" : "▶"}</button>
          <button class="transport-button" type="button" aria-label="下一步" title="下一步" ?disabled=${!total || index >= total - 1} @click=${() => this.#playback.send({ type: "NEXT" })}>→</button>
          <span class="transport__count">${Math.max(0, index + 1)} / ${total}</span>
          <span class="transport__progress" role="progressbar" aria-label="播放进度" aria-valuemin="0" aria-valuemax=${total} aria-valuenow=${Math.max(0, index + 1)}><span style=${`--progress: ${progress}`}></span></span>
          <label>
            <span class="sr-only">播放速度</span>
            <select class="speed-select" .value=${String(this._speed)} @change=${(event: Event) => {
              this._speed = Number((event.currentTarget as HTMLSelectElement).value);
              this.#syncPlaybackTimer();
            }}>
              <option value="0.5" ?selected=${this._speed === 0.5}>0.5×</option>
              <option value="1" ?selected=${this._speed === 1}>1×</option>
              <option value="2" ?selected=${this._speed === 2}>2×</option>
            </select>
          </label>
        </div>

        <div
          class="graph-region"
          role="region"
          aria-label=${typeof scenario.graph === "object"
            ? scenario.graph.label
            : `${scenario.title} 流程节点`}
        >
          <div class="graph-frame">${unsafeSVG(this._svgMarkup)}</div>
          ${this._graphMessage ? html`<p class="graph-message">${this._graphMessage}</p>` : nothing}
        </div>

        <div class="workbench">
          ${this.#renderTrace()}
          ${this.#renderInspector()}
        </div>

        <p class="sr-only" aria-live="polite">
          ${this.#currentStep() ? `第 ${index + 1} 步：${this.#currentStep()?.title}` : "任务尚未开始"}
        </p>
      </section>
    `;
  }
}

if (!customElements.get("cc-agent-lab")) {
  customElements.define("cc-agent-lab", ClaudeCodeAgentLab);
}

declare global {
  interface HTMLElementTagNameMap {
    "cc-agent-lab": ClaudeCodeAgentLab;
  }
}
