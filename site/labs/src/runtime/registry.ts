import type { LabScenario, LabScenarioRegistry } from "./types";

class DefaultScenarioRegistry implements LabScenarioRegistry {
  readonly #scenarios = new Map<string, LabScenario>();
  readonly #listeners = new Set<() => void>();

  register(scenario: LabScenario): void {
    if (!scenario.id.trim()) throw new Error("Scenario id is required");
    this.#scenarios.set(scenario.id, scenario);
    this.#listeners.forEach((listener) => listener());
  }

  get(id: string): LabScenario | undefined {
    return this.#scenarios.get(id);
  }

  list(): readonly LabScenario[] {
    return [...this.#scenarios.values()];
  }

  subscribe(listener: () => void): () => void {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }
}

export const labScenarioRegistry: LabScenarioRegistry = new DefaultScenarioRegistry();

export function registerLabScenario(scenario: LabScenario): LabScenario {
  labScenarioRegistry.register(scenario);
  return scenario;
}

declare global {
  interface Window {
    registerClaudeCodeLabScenario?: typeof registerLabScenario;
  }
}

if (typeof window !== "undefined") {
  window.registerClaudeCodeLabScenario = registerLabScenario;
}
