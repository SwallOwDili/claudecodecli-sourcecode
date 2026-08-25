import type { LabFileMap, LabStep } from "./types";

export interface DiffLine {
  kind: "context" | "add" | "remove";
  text: string;
  oldLine?: number;
  newLine?: number;
}

export interface FileDiff {
  path: string;
  lines: DiffLine[];
  additions: number;
  removals: number;
}

export function filesAtStep(
  initialFiles: LabFileMap,
  steps: LabStep[],
  index: number,
): LabFileMap {
  const files = { ...initialFiles };
  for (let cursor = 0; cursor <= index && cursor < steps.length; cursor += 1) {
    if (steps[cursor]?.files) Object.assign(files, steps[cursor].files);
  }
  return files;
}

function fallbackDiff(before: string[], after: string[]): DiffLine[] {
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) {
    prefix += 1;
  }

  let suffix = 0;
  while (
    suffix < before.length - prefix &&
    suffix < after.length - prefix &&
    before[before.length - suffix - 1] === after[after.length - suffix - 1]
  ) {
    suffix += 1;
  }

  const lines: DiffLine[] = [];
  let oldLine = 1;
  let newLine = 1;
  for (let index = 0; index < prefix; index += 1) {
    lines.push({ kind: "context", text: before[index], oldLine: oldLine++, newLine: newLine++ });
  }
  for (const line of before.slice(prefix, before.length - suffix)) {
    lines.push({ kind: "remove", text: line, oldLine: oldLine++ });
  }
  for (const line of after.slice(prefix, after.length - suffix)) {
    lines.push({ kind: "add", text: line, newLine: newLine++ });
  }
  for (const line of before.slice(before.length - suffix)) {
    lines.push({ kind: "context", text: line, oldLine: oldLine++, newLine: newLine++ });
  }
  return lines;
}

function lineDiff(beforeText: string, afterText: string): DiffLine[] {
  const before = beforeText.split("\n");
  const after = afterText.split("\n");
  if (before.length * after.length > 90_000) return fallbackDiff(before, after);

  const table = Array.from({ length: before.length + 1 }, () =>
    new Uint16Array(after.length + 1),
  );
  for (let left = before.length - 1; left >= 0; left -= 1) {
    for (let right = after.length - 1; right >= 0; right -= 1) {
      table[left][right] = before[left] === after[right]
        ? table[left + 1][right + 1] + 1
        : Math.max(table[left + 1][right], table[left][right + 1]);
    }
  }

  const lines: DiffLine[] = [];
  let left = 0;
  let right = 0;
  let oldLine = 1;
  let newLine = 1;
  while (left < before.length || right < after.length) {
    if (left < before.length && right < after.length && before[left] === after[right]) {
      lines.push({ kind: "context", text: before[left], oldLine: oldLine++, newLine: newLine++ });
      left += 1;
      right += 1;
    } else if (
      right < after.length &&
      (left >= before.length || table[left][right + 1] >= table[left + 1][right])
    ) {
      lines.push({ kind: "add", text: after[right], newLine: newLine++ });
      right += 1;
    } else {
      lines.push({ kind: "remove", text: before[left], oldLine: oldLine++ });
      left += 1;
    }
  }
  return lines;
}

export function diffFiles(initialFiles: LabFileMap, currentFiles: LabFileMap): FileDiff[] {
  return [...new Set([...Object.keys(initialFiles), ...Object.keys(currentFiles)])]
    .sort((left, right) => left.localeCompare(right))
    .filter((path) => (initialFiles[path] ?? "") !== (currentFiles[path] ?? ""))
    .map((path) => {
      const lines = lineDiff(initialFiles[path] ?? "", currentFiles[path] ?? "");
      return {
        path,
        lines,
        additions: lines.filter((line) => line.kind === "add").length,
        removals: lines.filter((line) => line.kind === "remove").length,
      };
    });
}
