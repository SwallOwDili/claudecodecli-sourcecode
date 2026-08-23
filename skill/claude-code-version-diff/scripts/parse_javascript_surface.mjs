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
const toolObjectCalls = [];
const declarations = {};
const maxReferenceLength = 160;
const maxFiniteValues = 64;
const maxResolutionDepth = 16;
const assignmentNodes = [];
const functionScopes = [];
const allCallNodes = [];
const memberAliases = [];
const environmentResolutionCandidates = [];
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

function objectPropertyName(property) {
  if (!property || property.type !== "Property") return null;
  return propertyName(property.key);
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

function scopePath(context) {
  return context.map((item) => item.id);
}

function parameterName(node) {
  if (node?.type === "Identifier") return node.name;
  if (node?.type === "AssignmentPattern" && node.left.type === "Identifier") {
    return node.left.name;
  }
  return null;
}

function sourceRange(node) {
  return node ? [node.start, node.end] : null;
}

function boundedLabel(value) {
  return typeof value === "string" && value.length <= maxReferenceLength
    ? value
    : null;
}

function staticReference(node, depth = 0) {
  if (!node || depth > 8) return null;
  if (node.type === "Identifier" || node.type === "PrivateIdentifier") {
    return boundedLabel(node.name);
  }
  if (node.type === "ThisExpression") return "this";
  if (node.type === "Super") return "super";
  if (node.type !== "MemberExpression") return null;

  const object = staticReference(node.object, depth + 1);
  if (object === null) return null;
  if (!node.computed && node.property.type === "Identifier") {
    return boundedLabel(`${object}.${node.property.name}`);
  }
  if (
    node.computed &&
    node.property.type === "Literal" &&
    (typeof node.property.value === "string" ||
      typeof node.property.value === "number")
  ) {
    const property = JSON.stringify(node.property.value);
    return boundedLabel(`${object}[${property}]`);
  }
  return null;
}

function callTargetNames(node) {
  if (!node) return [];
  if (node.type === "ChainExpression") return callTargetNames(node.expression);
  if (node.type === "SequenceExpression") {
    return callTargetNames(node.expressions.at(-1));
  }
  const names = [];
  const reference = staticReference(node);
  if (reference !== null) names.push(reference);
  if (node.type === "Identifier") names.push(node.name);
  if (node.type === "MemberExpression") {
    const property = propertyName(node.property);
    if (property !== null) names.push(property);
  }
  return [...new Set(names)];
}

function baseConsumer(node, parent, parentKey) {
  return {
    role: "other",
    parentType: parent?.type ?? null,
    relation: parentKey ?? null,
    consumerRange: sourceRange(parent),
    valueRange: sourceRange(node),
  };
}

function consumerRecord(node, parent, parentKey, parentIndex) {
  const consumer = baseConsumer(node, parent, parentKey);
  if (!parent) return consumer;

  if (parent.type === "IfStatement" && parentKey === "test") {
    consumer.role = "if";
    consumer.target = "test";
  } else if (
    (parent.type === "WhileStatement" ||
      parent.type === "DoWhileStatement" ||
      parent.type === "ForStatement" ||
      parent.type === "SwitchCase") &&
    parentKey === "test"
  ) {
    consumer.role = "test";
    consumer.target = parent.type;
  } else if (parent.type === "ReturnStatement" && parentKey === "argument") {
    consumer.role = "return";
  } else if (parent.type === "VariableDeclarator" && parentKey === "init") {
    consumer.role = "variable";
    consumer.target = staticReference(parent.id);
    consumer.targetRange = sourceRange(parent.id);
  } else if (parent.type === "AssignmentExpression" && parentKey === "right") {
    consumer.role = "assignment";
    consumer.target = staticReference(parent.left);
    consumer.targetRange = sourceRange(parent.left);
    consumer.operator = parent.operator;
  } else if (parent.type === "AssignmentExpression" && parentKey === "left") {
    consumer.role = "assignment-target";
    consumer.target = staticReference(parent.left);
    consumer.targetRange = sourceRange(parent.left);
    consumer.operator = parent.operator;
  } else if (
    (parent.type === "CallExpression" || parent.type === "NewExpression") &&
    parentKey === "arguments"
  ) {
    consumer.role = "call-argument";
    consumer.callee = staticReference(parent.callee);
    consumer.calleeRange = sourceRange(parent.callee);
    consumer.argumentIndex = parentIndex;
    consumer.callKind = parent.type === "NewExpression" ? "new" : "call";
  } else if (parent.type === "BinaryExpression") {
    consumer.role = "binary";
    consumer.target = parentKey;
    consumer.operator = parent.operator;
  } else if (parent.type === "LogicalExpression") {
    consumer.role = "logical";
    consumer.target = parentKey;
    consumer.operator = parent.operator;
  } else if (parent.type === "ConditionalExpression") {
    consumer.role = "conditional";
    consumer.target = parentKey;
  } else if (parent.type === "Property" && parentKey === "value") {
    consumer.role = "object-property";
    consumer.target = boundedLabel(propertyName(parent.key));
    consumer.targetRange = sourceRange(parent.key);
    consumer.propertyKind = parent.kind;
  } else if (parent.type === "MemberExpression") {
    consumer.role = "member";
    consumer.target = boundedLabel(propertyName(parent.property));
    consumer.targetRange = sourceRange(parent.property);
    consumer.operator = parent.computed ? "[]" : ".";
  } else if (parent.type === "UnaryExpression") {
    consumer.role = parent.operator === "delete" ? "delete" : "unary";
    consumer.operator = parent.operator;
  } else if (parent.type === "UpdateExpression") {
    consumer.role = "update";
    consumer.operator = parent.operator;
  } else if (typeof parent.operator === "string") {
    consumer.operator = parent.operator;
  }
  return consumer;
}

function environmentAccessMode(parent, parentKey) {
  if (parent?.type === "AssignmentExpression" && parentKey === "left") {
    return parent.operator === "=" ? "write" : "read-write";
  }
  if (parent?.type === "UpdateExpression" && parentKey === "argument") {
    return "read-write";
  }
  if (
    parent?.type === "UnaryExpression" &&
    parent.operator === "delete" &&
    parentKey === "argument"
  ) {
    return "delete";
  }
  return "read";
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

const stack = [
  {
    node: ast,
    parent: null,
    parentKey: null,
    parentIndex: null,
    context: [],
  },
];
while (stack.length > 0) {
  const { node, parent, parentKey, parentIndex, context } = stack.pop();
  let childContext = context;
  if (
    node.type === "FunctionDeclaration" ||
    node.type === "FunctionExpression" ||
    node.type === "ArrowFunctionExpression"
  ) {
    const name = inferredFunctionName(node, parent);
    const scope = {
      id: nextScopeId++,
      name,
      node,
      parentContext: context,
      parentScopePath: scopePath(context),
      params: node.params.map(parameterName),
      returnNodes: [],
      callback:
        parent?.type === "CallExpression" && parentKey === "arguments"
          ? { call: parent, argumentIndex: parentIndex }
          : null,
    };
    functionScopes.push(scope);
    childContext = [...context, scope];
    if (node.type === "FunctionDeclaration" && name && targetCallees.has(name)) {
      declarations[name] = (declarations[name] ?? 0) + 1;
    }
  }

  if (node.type === "CallExpression" || node.type === "NewExpression") {
    allCallNodes.push({
      node,
      targets: callTargetNames(node.callee),
      context: childContext,
    });
    const callee = identifierName(node.callee);
    if (callee && targetCallees.has(callee)) {
      calls.push({
        ...location(node.callee),
        callee,
        callKind: node.type === "NewExpression" ? "new" : "call",
        start: node.start,
        end: node.end,
        arguments: node.arguments.map((argument) => [argument.start, argument.end]),
        consumer: consumerRecord(node, parent, parentKey, parentIndex),
        ...functionRecord(childContext),
      });
    }

    if (
      node.type === "CallExpression" &&
      node.arguments[0]?.type === "ObjectExpression"
    ) {
      const object = node.arguments[0];
      const properties = object.properties
        .map((property) => ({ property, name: objectPropertyName(property) }))
        .filter((item) => item.name !== null);
      const propertyNames = new Set(properties.map((item) => item.name));
      const nameProperty = properties.find((item) => item.name === "name")?.property;
      const aliasesProperty = properties.find(
        (item) => item.name === "aliases",
      )?.property;
      if (
        nameProperty?.value &&
        propertyNames.has("call") &&
        propertyNames.has("inputSchema") &&
        propertyNames.has("description") &&
        propertyNames.has("prompt") &&
        (propertyNames.has("mapToolResultToToolResultBlockParam") ||
          propertyNames.has("userFacingName"))
      ) {
        toolObjectCalls.push({
          ...location(node),
          callee: identifierName(node.callee),
          calleeStart: node.callee.start,
          calleeEnd: node.callee.end,
          start: node.start,
          end: node.end,
          nameExpression: [nameProperty.value.start, nameProperty.value.end],
          aliasesExpression: aliasesProperty?.value
            ? [aliasesProperty.value.start, aliasesProperty.value.end]
            : null,
          properties: [...propertyNames].sort(),
          ...functionRecord(childContext),
        });
      }
    }
  }

  if (node.type === "ReturnStatement" && childContext.length > 0) {
    childContext.at(-1).returnNodes.push(node.argument);
  }

  if (node.type === "VariableDeclarator" && node.init && node.id.type === "Identifier") {
    const assignment = {
      ...location(node.id),
      name: node.id.name,
      start: node.init.start,
      end: node.init.end,
      ...functionRecord(childContext),
    };
    assignments.push(assignment);
    assignmentNodes.push({ ...assignment, valueNode: node.init, context: childContext });
  } else if (
    node.type === "AssignmentExpression" &&
    node.operator === "=" &&
    node.left.type === "Identifier"
  ) {
    const assignment = {
      ...location(node.left),
      name: node.left.name,
      start: node.right.start,
      end: node.right.end,
      ...functionRecord(childContext),
    };
    assignments.push(assignment);
    assignmentNodes.push({ ...assignment, valueNode: node.right, context: childContext });
  } else if (
    node.type === "AssignmentExpression" &&
    node.operator === "=" &&
    node.left.type === "MemberExpression" &&
    node.right.type === "Identifier"
  ) {
    const alias = propertyName(node.left.property);
    if (alias !== null) {
      memberAliases.push({
        alias,
        functionName: node.right.name,
        offset: node.start,
        scopePath: scopePath(childContext),
      });
    }
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
  if (environment) {
    const record = {
      ...environment,
      accessMode: environmentAccessMode(parent, parentKey),
      consumer: consumerRecord(node, parent, parentKey, parentIndex),
      ...functionRecord(childContext),
    };
    environmentAccesses.push(record);
    if (record.name === null && node.computed) {
      environmentResolutionCandidates.push({
        record,
        expressionNode: node.property,
        context: childContext,
      });
    }
  }

  const children = [];
  for (const [key, value] of Object.entries(node)) {
    if (key === "loc" || key === "start" || key === "end") continue;
    if (isNode(value)) {
      children.push({ node: value, parentKey: key, parentIndex: null });
    } else if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index += 1) {
        if (isNode(value[index])) {
          children.push({ node: value[index], parentKey: key, parentIndex: index });
        }
      }
    }
  }
  children.sort(
    (left, right) =>
      left.node.start - right.node.start || left.node.end - right.node.end,
  );
  for (let index = children.length - 1; index >= 0; index -= 1) {
    stack.push({
      ...children[index],
      parent: node,
      context: childContext,
    });
  }
}

const assignmentsByName = new Map();
for (const assignment of assignmentNodes) {
  if (!assignmentsByName.has(assignment.name)) {
    assignmentsByName.set(assignment.name, []);
  }
  assignmentsByName.get(assignment.name).push(assignment);
}
for (const values of assignmentsByName.values()) {
  values.sort((left, right) => left.offset - right.offset);
}

const functionsByName = new Map();
for (const scope of functionScopes) {
  if (scope.name === null) continue;
  if (!functionsByName.has(scope.name)) functionsByName.set(scope.name, []);
  functionsByName.get(scope.name).push(scope);
}

const callsByTarget = new Map();
for (const call of allCallNodes) {
  for (const target of call.targets) {
    if (!callsByTarget.has(target)) callsByTarget.set(target, []);
    callsByTarget.get(target).push(call);
  }
}

function isPathPrefix(prefix, path) {
  return (
    prefix.length <= path.length &&
    prefix.every((value, index) => value === path[index])
  );
}

function nearestVisibleFunction(name, context) {
  const path = scopePath(context);
  const candidates = (functionsByName.get(name) ?? []).filter((scope) =>
    isPathPrefix(scope.parentScopePath, path),
  );
  if (candidates.length === 0) return null;
  const deepest = Math.max(...candidates.map((scope) => scope.parentScopePath.length));
  const nearest = candidates.filter(
    (scope) => scope.parentScopePath.length === deepest,
  );
  return nearest.length === 1 ? nearest[0] : null;
}

function staticObjectKeys(node, context, seen = new Set()) {
  if (!node || seen.size > maxResolutionDepth) return null;
  if (node.type === "ObjectExpression") {
    const keys = new Set();
    for (const property of node.properties) {
      if (property.type === "SpreadElement") {
        const spreadKeys = staticObjectKeys(property.argument, context, seen);
        if (spreadKeys === null) return null;
        for (const key of spreadKeys) keys.add(key);
        continue;
      }
      if (property.type !== "Property" || property.computed) return null;
      const key = propertyName(property.key);
      if (key === null) return null;
      keys.add(key);
    }
    return keys;
  }
  if (node.type === "ConditionalExpression") {
    const consequent = staticObjectKeys(node.consequent, context, seen);
    const alternate = staticObjectKeys(node.alternate, context, seen);
    if (consequent === null || alternate === null) return null;
    return new Set([...consequent, ...alternate]);
  }
  if (node.type === "CallExpression" && node.callee.type === "Identifier") {
    const scope = nearestVisibleFunction(node.callee.name, context);
    if (scope === null || seen.has(scope.id) || scope.returnNodes.length === 0) {
      return null;
    }
    const keys = new Set();
    const nextSeen = new Set([...seen, scope.id]);
    for (const returned of scope.returnNodes) {
      if (returned === null) continue;
      const returnedKeys = staticObjectKeys(returned, scope.parentContext, nextSeen);
      if (returnedKeys === null) return null;
      for (const key of returnedKeys) keys.add(key);
    }
    return keys.size > 0 ? keys : null;
  }
  return null;
}

function resolutionStep(kind, node, extra = {}) {
  return {
    kind,
    ...location(node),
    range: sourceRange(node),
    ...extra,
  };
}

function callerStep(kind, call, extra = {}) {
  return {
    kind,
    ...location(call.node),
    callee: staticReference(call.node.callee),
    range: sourceRange(call.node),
    function: functionRecord(call.context).function,
    ...extra,
  };
}

function valueKey(value) {
  if (typeof value === "string") return `s:${value}`;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    value === null
  ) {
    return `p:${JSON.stringify(value)}`;
  }
  if (value?.kind === "array") {
    return `a:[${value.items.map(valueKey).join(",")}]`;
  }
  if (value?.kind === "object") {
    return `o:{${[...value.properties.entries()]
      .map(([key, values]) => `${key}:${values.map(valueKey).join("|")}`)
      .join(",")}}!${[...(value.unsafeKeys ?? [])].sort().join(",")}`;
  }
  return "unknown";
}

function uniqueValues(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const key = valueKey(value);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(value);
    if (result.length > maxFiniteValues) return null;
  }
  return result;
}

function mergeResults(results) {
  if (results.length === 0 || results.some((result) => !result.complete)) {
    return { complete: false, values: [], evidence: [], callers: [] };
  }
  const values = uniqueValues(results.flatMap((result) => result.values));
  if (values === null || values.length === 0) {
    return { complete: false, values: [], evidence: [], callers: [] };
  }
  return {
    complete: true,
    values,
    evidence: results.flatMap((result) => result.evidence),
    callers: results.flatMap((result) => result.callers),
  };
}

function stringResult(value, evidence = [], callers = []) {
  return { complete: true, values: [value], evidence, callers };
}

function unresolvedResult() {
  return { complete: false, values: [], evidence: [], callers: [] };
}

function nearestParameterScope(name, context) {
  for (let index = context.length - 1; index >= 0; index -= 1) {
    const parameterIndex = context[index].params.indexOf(name);
    if (parameterIndex >= 0) return { scope: context[index], parameterIndex };
  }
  return null;
}

function nearestAssignment(name, before, context, parameterScope) {
  const path = scopePath(context);
  const minimumDepth = parameterScope
    ? parameterScope.scope.parentScopePath.length + 1
    : 0;
  const candidates = (assignmentsByName.get(name) ?? []).filter((assignment) => {
    const assignmentPath = assignment.scopePath ?? [];
    return (
      assignment.offset < before &&
      assignmentPath.length >= minimumDepth &&
      isPathPrefix(assignmentPath, path)
    );
  });
  if (candidates.length === 0) return null;
  candidates.sort(
    (left, right) =>
      right.scopePath.length - left.scopePath.length || right.offset - left.offset,
  );
  return candidates[0];
}

function exportedAliases(scope) {
  return memberAliases
    .filter(
      (alias) =>
        alias.functionName === scope.name &&
        alias.scopePath.length === scope.parentScopePath.length &&
        isPathPrefix(scope.parentScopePath, alias.scopePath),
    )
    .map((alias) => alias.alias);
}

function callsForFunction(scope) {
  const calls = [];
  if (scope.name !== null) {
    for (const call of callsByTarget.get(scope.name) ?? []) {
      if (nearestVisibleFunction(scope.name, call.context) === scope) calls.push(call);
    }
  }
  for (const alias of exportedAliases(scope)) {
    for (const call of callsByTarget.get(alias) ?? []) calls.push(call);
  }
  return [...new Map(calls.map((call) => [call.node.start, call])).values()].sort(
    (left, right) => left.node.start - right.node.start,
  );
}

const callbackMethods = new Set([
  "every",
  "filter",
  "find",
  "findIndex",
  "flatMap",
  "forEach",
  "map",
  "some",
]);

function callbackParameterResult(scope, parameterIndex, state) {
  const callback = scope.callback;
  const callee = callback?.call?.callee;
  if (
    !callback ||
    parameterIndex !== 0 ||
    callee?.type !== "MemberExpression" ||
    !callbackMethods.has(propertyName(callee.property))
  ) {
    return unresolvedResult();
  }
  const receiver = evaluateNode(callee.object, scope.parentContext, callback.call.start, {
    ...state,
    depth: state.depth + 1,
  });
  if (!receiver.complete) return unresolvedResult();
  const items = [];
  for (const value of receiver.values) {
    if (value?.kind !== "array") return unresolvedResult();
    items.push(...value.items);
  }
  const values = uniqueValues(items);
  if (values === null || values.length === 0) return unresolvedResult();
  return {
    complete: true,
    values,
    evidence: [
      ...receiver.evidence,
      resolutionStep("static-callback-collection", callback.call, {
        method: propertyName(callee.property),
        parameter: scope.params[parameterIndex],
      }),
    ],
    callers: [
      ...receiver.callers,
      callerStep("array-callback", { node: callback.call, context: scope.parentContext }, {
        argumentIndex: callback.argumentIndex,
      }),
    ],
  };
}

function functionParameterResult(scope, parameterIndex, state) {
  const callback = callbackParameterResult(scope, parameterIndex, state);
  if (callback.complete) return callback;
  const calls = callsForFunction(scope);
  if (calls.length === 0) return unresolvedResult();
  const results = [];
  for (const call of calls) {
    const argument = call.node.arguments[parameterIndex];
    if (!argument || argument.type === "SpreadElement") return unresolvedResult();
    const result = evaluateNode(argument, call.context, call.node.start, {
      ...state,
      depth: state.depth + 1,
    });
    if (!result.complete) return unresolvedResult();
    results.push({
      ...result,
      evidence: [
        ...result.evidence,
        resolutionStep("finite-function-argument", argument, {
          function: scope.name,
          parameter: scope.params[parameterIndex],
        }),
      ],
      callers: [
        ...result.callers,
        callerStep("function-call", call, { argumentIndex: parameterIndex }),
      ],
    });
  }
  return mergeResults(results);
}

function evaluateIdentifier(node, context, before, state) {
  const parameter = nearestParameterScope(node.name, context);
  const assignment = nearestAssignment(node.name, before, context, parameter);
  if (assignment !== null) {
    const key = `assignment:${assignment.offset}`;
    if (state.seen.has(key)) return unresolvedResult();
    const result = evaluateNode(
      assignment.valueNode,
      assignment.context,
      assignment.offset,
      {
        ...state,
        depth: state.depth + 1,
        seen: new Set([...state.seen, key]),
      },
    );
    if (!result.complete) return result;
    return {
      ...result,
      evidence: [
        ...result.evidence,
        resolutionStep("lexical-assignment", assignment.valueNode, {
          identifier: node.name,
          assignmentOffset: assignment.offset,
          assignmentScopePath: assignment.scopePath,
        }),
      ],
    };
  }
  if (parameter !== null) {
    const key = `parameter:${parameter.scope.id}:${parameter.parameterIndex}`;
    if (state.seen.has(key)) return unresolvedResult();
    return functionParameterResult(parameter.scope, parameter.parameterIndex, {
      ...state,
      depth: state.depth + 1,
      seen: new Set([...state.seen, key]),
    });
  }
  return unresolvedResult();
}

function evaluateTemplate(node, context, before, state) {
  let values = [""];
  let evidence = [resolutionStep("static-template", node)];
  let callers = [];
  for (let index = 0; index < node.quasis.length; index += 1) {
    const quasi = node.quasis[index].value.cooked;
    if (quasi === null) return unresolvedResult();
    values = values.map((value) => value + quasi);
    if (index >= node.expressions.length) continue;
    const expression = evaluateNode(node.expressions[index], context, before, {
      ...state,
      depth: state.depth + 1,
    });
    if (!expression.complete || expression.values.some((value) => typeof value !== "string")) {
      return unresolvedResult();
    }
    const expanded = [];
    for (const prefix of values) {
      for (const value of expression.values) {
        expanded.push(prefix + value);
        if (expanded.length > maxFiniteValues) return unresolvedResult();
      }
    }
    values = expanded;
    evidence.push(...expression.evidence);
    callers.push(...expression.callers);
  }
  return { complete: true, values, evidence, callers };
}

function evaluateNode(node, context, before, state) {
  if (!node || state.depth > maxResolutionDepth) return unresolvedResult();
  if (node.type === "ChainExpression") {
    return evaluateNode(node.expression, context, before, state);
  }
  if (node.type === "Literal") {
    if (typeof node.value === "string") {
      return stringResult(node.value, [resolutionStep("static-string", node)]);
    }
    if (
      typeof node.value === "number" ||
      typeof node.value === "boolean" ||
      node.value === null
    ) {
      return {
        complete: true,
        values: [node.value],
        evidence: [resolutionStep("static-primitive", node)],
        callers: [],
      };
    }
  }
  if (node.type === "TemplateLiteral") {
    return evaluateTemplate(node, context, before, state);
  }
  if (node.type === "Identifier") {
    return evaluateIdentifier(node, context, before, state);
  }
  if (node.type === "ConditionalExpression") {
    return mergeResults([
      evaluateNode(node.consequent, context, before, {
        ...state,
        depth: state.depth + 1,
      }),
      evaluateNode(node.alternate, context, before, {
        ...state,
        depth: state.depth + 1,
      }),
    ]);
  }
  if (node.type === "ArrayExpression") {
    const items = [];
    const evidence = [resolutionStep("static-array", node)];
    const callers = [];
    for (const element of node.elements) {
      if (!element || element.type === "SpreadElement") return unresolvedResult();
      const result = evaluateNode(element, context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (!result.complete) return unresolvedResult();
      items.push(...result.values);
      evidence.push(...result.evidence);
      callers.push(...result.callers);
    }
    const unique = uniqueValues(items);
    if (unique === null) return unresolvedResult();
    return {
      complete: true,
      values: [{ kind: "array", items: unique }],
      evidence,
      callers,
    };
  }
  if (node.type === "ObjectExpression") {
    const properties = new Map();
    const unsafeKeys = new Set();
    const evidence = [resolutionStep("static-object", node)];
    const callers = [];
    for (const property of node.properties) {
      if (property.type === "SpreadElement") {
        const spreadKeys = staticObjectKeys(property.argument, context);
        if (spreadKeys === null) return unresolvedResult();
        for (const key of spreadKeys) {
          properties.delete(key);
          unsafeKeys.add(key);
        }
        evidence.push(
          resolutionStep("static-object-spread-keys", property.argument, {
            keys: [...spreadKeys].sort(),
          }),
        );
        continue;
      }
      if (
        property.type !== "Property" ||
        property.computed ||
        property.kind !== "init"
      ) {
        return unresolvedResult();
      }
      const key = propertyName(property.key);
      if (key === null) return unresolvedResult();
      const result = evaluateNode(property.value, context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (!result.complete) return unresolvedResult();
      properties.set(key, result.values);
      unsafeKeys.delete(key);
      evidence.push(...result.evidence);
      callers.push(...result.callers);
    }
    return {
      complete: true,
      values: [{ kind: "object", properties, unsafeKeys }],
      evidence,
      callers,
    };
  }
  if (node.type === "MemberExpression") {
    const object = evaluateNode(node.object, context, before, {
      ...state,
      depth: state.depth + 1,
    });
    if (!object.complete) return unresolvedResult();
    let keys;
    let keyEvidence = [];
    let keyCallers = [];
    if (node.computed) {
      const keyResult = evaluateNode(node.property, context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (
        !keyResult.complete ||
        keyResult.values.some(
          (value) =>
            typeof value !== "string" &&
            typeof value !== "number",
        )
      ) {
        return unresolvedResult();
      }
      keys = keyResult.values.map(String);
      keyEvidence = keyResult.evidence;
      keyCallers = keyResult.callers;
    } else {
      const key = propertyName(node.property);
      if (key === null) return unresolvedResult();
      keys = [key];
    }
    const values = [];
    for (const value of object.values) {
      for (const key of keys) {
        if (value?.kind === "object") {
          if (value.unsafeKeys?.has(key)) return unresolvedResult();
          const propertyValues = value.properties.get(key);
          if (!propertyValues) return unresolvedResult();
          values.push(...propertyValues);
        } else if (value?.kind === "array" && /^\d+$/.test(key)) {
          const item = value.items[Number(key)];
          if (item === undefined) return unresolvedResult();
          values.push(item);
        } else {
          return unresolvedResult();
        }
      }
    }
    const unique = uniqueValues(values);
    if (unique === null || unique.length === 0) return unresolvedResult();
    return {
      ...object,
      values: unique,
      evidence: [...object.evidence, ...keyEvidence],
      callers: [...object.callers, ...keyCallers],
    };
  }
  if (node.type === "CallExpression" && node.arguments.length === 0) {
    const callee = node.callee.type === "ChainExpression" ? node.callee.expression : node.callee;
    if (callee?.type === "MemberExpression") {
      const method = propertyName(callee.property);
      if (method === "toUpperCase" || method === "toLowerCase") {
        const object = evaluateNode(callee.object, context, before, {
          ...state,
          depth: state.depth + 1,
        });
        if (!object.complete || object.values.some((value) => typeof value !== "string")) {
          return unresolvedResult();
        }
        return {
          ...object,
          values: object.values.map((value) =>
            method === "toUpperCase" ? value.toUpperCase() : value.toLowerCase(),
          ),
          evidence: [
            ...object.evidence,
            resolutionStep("static-string-transform", node, { method }),
          ],
        };
      }
    }
  }
  return unresolvedResult();
}

function dedupeRecords(records, limit = maxFiniteValues) {
  const seen = new Set();
  const result = [];
  for (const record of records) {
    const key = JSON.stringify(record);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(record);
    if (result.length >= limit) break;
  }
  return result;
}

function uniqueRecordCount(records) {
  return new Set(records.map((record) => JSON.stringify(record))).size;
}

for (const candidate of environmentResolutionCandidates) {
  const result = evaluateNode(
    candidate.expressionNode,
    candidate.context,
    candidate.expressionNode.start,
    { depth: 0, seen: new Set() },
  );
  if (
    !result.complete ||
    result.values.length === 0 ||
    result.values.some(
      (value) =>
        typeof value !== "string" ||
        value.length === 0 ||
        value.length > maxReferenceLength ||
        !/^[A-Za-z_][A-Za-z0-9_]*$/.test(value),
    )
  ) {
    continue;
  }
  const values = [...new Set(result.values)].sort();
  if (values.length === 1) candidate.record.resolvedStaticValue = values[0];
  else candidate.record.resolvedFiniteValues = values;
  const evidence = dedupeRecords(result.evidence);
  const callers = dedupeRecords(result.callers);
  const evidenceCount = uniqueRecordCount(result.evidence);
  const callerCount = uniqueRecordCount(result.callers);
  const kinds = [...new Set(evidence.map((item) => item.kind))].sort();
  candidate.record.resolutionEvidence = {
    complete: true,
    strategy: kinds.join("+") || "static-expression",
    valueCount: values.length,
    stepCount: evidenceCount,
    stepsTruncated: evidence.length < evidenceCount,
    callerCount,
    callersTruncated: callers.length < callerCount,
    steps: evidence,
  };
  candidate.record.caller = callers;
}

calls.sort((left, right) => left.offset - right.offset);
assignments.sort((left, right) => left.offset - right.offset);
strings.sort((left, right) => left.offset - right.offset);
templates.sort((left, right) => left.offset - right.offset);
environmentAccesses.sort((left, right) => left.offset - right.offset);
toolObjectCalls.sort((left, right) => left.offset - right.offset);

process.stdout.write(
  JSON.stringify({
    parser: { name: "acorn", version: "8.15.0", ecmaVersion: "latest" },
    calls,
    assignments,
    strings,
    templates,
    environmentAccesses,
    toolObjectCalls,
    declarations,
    discoveredSymbols,
  }),
);
