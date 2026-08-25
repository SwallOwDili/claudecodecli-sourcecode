/// <reference types="vite/client" />

import "./cc-agent-lab";
import { labScenarioRegistry } from "./runtime/registry";
import type { LabScenario } from "./runtime/types";

type ScenarioModule = {
  default?: unknown;
  scenario?: unknown;
  scenarios?: unknown;
};

function isScenario(value: unknown): value is LabScenario {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<LabScenario>;
  return Boolean(candidate.id && candidate.title && typeof candidate.buildTrace === "function");
}

function registerModule(module: ScenarioModule): void {
  const candidates = [
    module.default,
    module.scenario,
    ...(Array.isArray(module.scenarios) ? module.scenarios : []),
  ];
  candidates.filter(isScenario).forEach((scenario) => labScenarioRegistry.register(scenario));
}

const modules = import.meta.glob<ScenarioModule>("./scenarios/*.ts", { eager: true });
Object.values(modules).forEach(registerModule);

export * from "./runtime/registry";
export * from "./runtime/types";
