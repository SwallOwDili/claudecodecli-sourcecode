export type LabActor =
  | "user"
  | "client"
  | "model"
  | "hook"
  | "permission"
  | "tool"
  | "external";

export type LabStepKind =
  | "input"
  | "assemble"
  | "request"
  | "stream"
  | "tool_use"
  | "hook"
  | "permission"
  | "execute"
  | "tool_result"
  | "feedback"
  | "complete"
  | "denied"
  | "failed";

export type LabControlValue = string | number | boolean;
export type LabControlValues = Record<string, LabControlValue>;
export type LabFileMap = Record<string, string>;

export interface LabControlOption {
  value: string | number;
  label: string;
}

export interface LabControl {
  id: string;
  label: string;
  type: "select" | "toggle";
  defaultValue: LabControlValue;
  options?: LabControlOption[];
  description?: string;
}

export interface LabEvidence {
  label: string;
  href: string;
  detail?: string;
}

export interface LabEffect {
  label: string;
  state?: "proposed" | "applied" | "blocked" | "failed";
  reversible?: boolean;
}

export interface LabStep {
  id: string;
  title: string;
  actor: LabActor;
  kind: LabStepKind | (string & {});
  summary?: string;
  detail?: string;
  tool?: string;
  tool_use_id?: string;
  input?: unknown;
  output?: unknown;
  before?: unknown;
  after?: unknown;
  /** Complete virtual file-system snapshot after this step. */
  files?: LabFileMap;
  effects?: Array<string | LabEffect>;
  evidence?: LabEvidence[];
  /** Stable SVG node IDs or embedded <title> values to highlight. */
  visualTarget?: string | string[];
  status?: "pending" | "running" | "success" | "denied" | "failed";
}

export interface LabTrace {
  parsed?: unknown;
  steps: LabStep[];
  initialFiles?: LabFileMap;
  notes?: string[];
}

export interface LabExample {
  label: string;
  input: string;
  controls?: LabControlValues;
}

export interface LabGraph {
  src: string;
  label: string;
}

export interface LabScenario {
  id: string;
  title: string;
  description: string;
  defaultInput: string;
  examples: Array<string | LabExample>;
  initialFiles: LabFileMap;
  graph?: string | LabGraph;
  controls?: LabControl[];
  buildTrace(input: string, controls: LabControlValues): LabTrace | LabStep[];
}

export interface LabScenarioRegistry {
  register(scenario: LabScenario): void;
  get(id: string): LabScenario | undefined;
  list(): readonly LabScenario[];
  subscribe(listener: () => void): () => void;
}

export function normalizeExample(example: string | LabExample): LabExample {
  return typeof example === "string"
    ? { label: example, input: example }
    : example;
}

export function normalizeTrace(
  trace: LabTrace | LabStep[],
  initialFiles: LabFileMap,
): LabTrace {
  return Array.isArray(trace)
    ? { steps: trace, initialFiles }
    : { ...trace, initialFiles: trace.initialFiles ?? initialFiles };
}
