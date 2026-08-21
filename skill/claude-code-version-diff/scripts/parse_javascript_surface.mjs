#!/usr/bin/env node

import fs from "node:fs";
import { parse } from "../vendor/acorn/acorn.mjs";

const sourcePath = process.argv[2];
if (!sourcePath) {
  process.stderr.write(
    "usage: parse_javascript_surface.mjs <source> [discovered-symbols-json]\n",
  );
  process.exit(2);
}

let discoveredSymbols = {};
if (process.argv[3]) {
  try {
    discoveredSymbols = JSON.parse(process.argv[3]);
  } catch (error) {
    process.stderr.write(`invalid discovered-symbols JSON: ${error.message}\n`);
    process.exit(2);
  }
}

const source = fs.readFileSync(sourcePath, "utf8");
const ast = parse(source, {
  ecmaVersion: "latest",
  sourceType: "script",
  locations: true,
  allowHashBang: true,
});

const targetCallees = new Set([
  ...(discoveredSymbols.targetCallees ?? []),
  "Error",
  "TypeError",
  "RangeError",
]);
const environmentProxies = new Set(discoveredSymbols.environmentProxies ?? []);
const calls = [];
const assignments = [];
const strings = [];
const templates = [];
const environmentAccesses = [];
const declarations = {};
let nextScopeId = 1;

function isNode(value) {
  return value !== null && typeof value === "object" && typeof value.type === "string";
}

function identifierName(node) {
  return node?.type === "Identifier" ? node.name : null;
}

function propertyName(node) {
  if (!node) return null;
  if (node.type === "Identifier") return node.name;
  if (node.type === "Literal" && typeof node.value === "string") return node.value;
  return null;
}

function inferredFunctionName(node, parent) {
  const ownName = identifierName(node.id);
  if (ownName) return ownName;
  if (parent?.type === "VariableDeclarator") return identifierName(parent.id);
  if (parent?.type === "AssignmentExpression") return identifierName(parent.left);
  if (parent?.type === "Property" || parent?.type === "MethodDefinition") {
    return propertyName(parent.key);
  }
  return null;
}

function location(node) {
  return {
    offset: node.start,
    line: node.loc.start.line,
    column: node.loc.start.column + 1,
  };
}

function functionRecord(context) {
  if (!context.length) {
    return { function: null, functionKind: "top-level", scopePath: [] };
  }
  const current = context[context.length - 1];
  return {
    function: current.name,
    functionKind: current.name ? "named" : "anonymous",
    scopePath: context.map((item) => item.id),
  };
}

function isProcessEnv(node) {
  return (
    node?.type === "MemberExpression" &&
    !node.computed &&
    identifierName(node.object) === "process" &&
    identifierName(node.property) === "env"
  );
}

function fallbackRecord(node, parent) {
  if (
    parent?.type === "LogicalExpression" &&
    parent.left === node &&
    (parent.operator === "??" || parent.operator === "||")
  ) {
    return {
      fallbackOperator: parent.operator,
      fallbackStart: parent.right.start,
      fallbackEnd: parent.right.end,
    };
  }
  return {};
}

function environmentRecord(node, parent) {
  if (node.type !== "MemberExpression") return null;
  if (isProcessEnv(node.object)) {
    const name = node.computed
      ? node.property.type === "Literal" && typeof node.property.value === "string"
        ? node.property.value
        : null
      : identifierName(node.property);
    return {
      ...location(node),
      accessor: node.computed ? "process.env.bracket" : "process.env.property",
      name,
      expressionStart: node.computed ? node.property.start : null,
      expressionEnd: node.computed ? node.property.end : null,
      accessEnd: node.end,
      ...fallbackRecord(node, parent),
    };
  }
  if (environmentProxies.has(identifierName(node.object))) {
    const name = node.computed
      ? node.property.type === "Literal" && typeof node.property.value === "string"
        ? node.property.value
        : null
      : identifierName(node.property);
    if (name === null || /^[A-Z][A-Z0-9_]{2,}$/.test(name)) {
      return {
        ...location(node),
        accessor: node.computed
          ? "environment-proxy.bracket"
          : "environment-proxy.property",
        name,
        expressionStart: node.computed ? node.property.start : null,
        expressionEnd: node.computed ? node.property.end : null,
        accessEnd: node.end,
        ...fallbackRecord(node, parent),
      };
    }
  }
  return null;
}

const stack = [{ node: ast, parent: null, context: [] }];
while (stack.length > 0) {
  const { node, parent, context } = stack.pop();
  let childContext = context;
  if (
    node.type === "FunctionDeclaration" ||
    node.type === "FunctionExpression" ||
    node.type === "ArrowFunctionExpression"
  ) {
    const name = inferredFunctionName(node, parent);
    const scope = { id: nextScopeId++, name };
    childContext = [...context, scope];
    if (node.type === "FunctionDeclaration" && name && targetCallees.has(name)) {
      declarations[name] = (declarations[name] ?? 0) + 1;
    }
  }

  if (node.type === "CallExpression" || node.type === "NewExpression") {
    const callee = identifierName(node.callee);
    if (callee && targetCallees.has(callee)) {
      calls.push({
        ...location(node.callee),
        callee,
        callKind: node.type === "NewExpression" ? "new" : "call",
        start: node.start,
        end: node.end,
        arguments: node.arguments.map((argument) => [argument.start, argument.end]),
        ...functionRecord(childContext),
      });
    }
  }

  if (node.type === "VariableDeclarator" && node.init && node.id.type === "Identifier") {
    assignments.push({
      ...location(node.id),
      name: node.id.name,
      start: node.init.start,
      end: node.init.end,
      ...functionRecord(childContext),
    });
  } else if (
    node.type === "AssignmentExpression" &&
    node.operator === "=" &&
    node.left.type === "Identifier"
  ) {
    assignments.push({
      ...location(node.left),
      name: node.left.name,
      start: node.right.start,
      end: node.right.end,
      ...functionRecord(childContext),
    });
  }

  if (node.type === "Literal" && typeof node.value === "string") {
    strings.push({
      ...location(node),
      start: node.start,
      end: node.end,
    });
  } else if (node.type === "TemplateLiteral") {
    templates.push({
      ...location(node),
      start: node.start,
      end: node.end,
      expressions: node.expressions.map((expression) => [expression.start, expression.end]),
    });
  }

  const environment = environmentRecord(node, parent);
  if (environment) environmentAccesses.push(environment);

  const children = [];
  for (const [key, value] of Object.entries(node)) {
    if (key === "loc" || key === "start" || key === "end") continue;
    if (isNode(value)) {
      children.push(value);
    } else if (Array.isArray(value)) {
      for (const item of value) if (isNode(item)) children.push(item);
    }
  }
  children.sort((left, right) => left.start - right.start || left.end - right.end);
  for (let index = children.length - 1; index >= 0; index -= 1) {
    stack.push({ node: children[index], parent: node, context: childContext });
  }
}

calls.sort((left, right) => left.offset - right.offset);
assignments.sort((left, right) => left.offset - right.offset);
strings.sort((left, right) => left.offset - right.offset);
templates.sort((left, right) => left.offset - right.offset);
environmentAccesses.sort((left, right) => left.offset - right.offset);

process.stdout.write(
  JSON.stringify({
    parser: { name: "acorn", version: "8.15.0", ecmaVersion: "latest" },
    calls,
    assignments,
    strings,
    templates,
    environmentAccesses,
    declarations,
    discoveredSymbols,
  }),
);
