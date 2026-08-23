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
const memberAssignmentNodes = [];
const iterationBindings = [];
const functionScopes = [];
const allCallNodes = [];
const identifierReferences = [];
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

function patternBindings(node, path = [], result = []) {
  if (!node) return result;
  if (node.type === "Identifier") {
    result.push({ name: node.name, path });
    return result;
  }
  if (node.type === "AssignmentPattern") {
    return patternBindings(node.left, path, result);
  }
  if (node.type === "ArrayPattern") {
    for (let index = 0; index < node.elements.length; index += 1) {
      const element = node.elements[index];
      if (!element || element.type === "RestElement") continue;
      patternBindings(element, [...path, index], result);
    }
    return result;
  }
  if (node.type === "ObjectPattern") {
    for (const property of node.properties) {
      if (property.type !== "Property" || property.computed) continue;
      const key = propertyName(property.key);
      if (key !== null) patternBindings(property.value, [...path, key], result);
    }
  }
  return result;
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
  if (node.type === "Identifier") {
    identifierReferences.push({
      node,
      parent,
      parentKey,
      parentIndex,
      context,
    });
  }
  if (
    node.type === "FunctionDeclaration" ||
    node.type === "FunctionExpression" ||
    node.type === "ArrowFunctionExpression"
  ) {
    const name = inferredFunctionName(node, parent);
    const parameterBindings = new Map();
    node.params.forEach((parameter, parameterIndex) => {
      for (const binding of patternBindings(parameter)) {
        parameterBindings.set(binding.name, {
          parameterIndex,
          path: binding.path,
        });
      }
    });
    const scope = {
      id: nextScopeId++,
      name,
      node,
      parentContext: context,
      parentScopePath: scopePath(context),
      params: node.params.map(parameterName),
      parameterBindings,
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
      bindingKind: parent?.type === "VariableDeclaration" ? parent.kind : "declaration",
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
      bindingKind: "assignment",
      ...functionRecord(childContext),
    };
    assignments.push(assignment);
    assignmentNodes.push({ ...assignment, valueNode: node.right, context: childContext });
  }

  if (
    node.type === "AssignmentExpression" &&
    node.operator === "=" &&
    node.left.type === "MemberExpression"
  ) {
    const reference = staticReference(node.left);
    if (reference !== null) {
      memberAssignmentNodes.push({
        ...location(node.left),
        reference,
        valueNode: node.right,
        context: childContext,
        scopePath: scopePath(childContext),
      });
    }
    const alias = propertyName(node.left.property);
    if (alias !== null && node.right.type === "Identifier") {
      memberAliases.push({
        alias,
        functionName: node.right.name,
        offset: node.start,
        scopePath: scopePath(childContext),
      });
    }
  }

  if (node.type === "ForOfStatement") {
    const pattern =
      node.left.type === "VariableDeclaration" && node.left.declarations.length === 1
        ? node.left.declarations[0].id
        : node.left;
    for (const binding of patternBindings(pattern)) {
      iterationBindings.push({
        ...binding,
        rightNode: node.right,
        bodyRange: sourceRange(node.body),
        offset: node.start,
        context: childContext,
        scopePath: scopePath(childContext),
        await: node.await === true,
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

const memberAssignmentsByReference = new Map();
for (const assignment of memberAssignmentNodes) {
  if (!memberAssignmentsByReference.has(assignment.reference)) {
    memberAssignmentsByReference.set(assignment.reference, []);
  }
  memberAssignmentsByReference.get(assignment.reference).push(assignment);
}
for (const values of memberAssignmentsByReference.values()) {
  values.sort((left, right) => left.offset - right.offset);
}

const iterationBindingsByName = new Map();
for (const binding of iterationBindings) {
  if (!iterationBindingsByName.has(binding.name)) {
    iterationBindingsByName.set(binding.name, []);
  }
  iterationBindingsByName.get(binding.name).push(binding);
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
    return {
      complete: false,
      values: [],
      evidence: [],
      callers: [],
      failures: results.flatMap((result) => result.failures ?? []),
    };
  }
  const values = uniqueValues(results.flatMap((result) => result.values));
  if (values === null || values.length === 0) {
    return unresolvedResult("empty-or-oversized-merged-domain");
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

function unresolvedResult(reason = "unsupported-or-incomplete", node = null, extra = {}) {
  return {
    complete: false,
    values: [],
    evidence: [],
    callers: [],
    failures: [
      {
        reason,
        ...(node
          ? {
              nodeType: node.type,
              ...location(node),
              range: sourceRange(node),
            }
          : {}),
        ...extra,
      },
    ],
  };
}

function nearestParameterScope(name, context) {
  for (let index = context.length - 1; index >= 0; index -= 1) {
    const binding = context[index].parameterBindings.get(name);
    if (binding) return { scope: context[index], ...binding };
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

function assignmentPrecedesAllKnownTopLevelExecutions(assignment, context) {
  const scope = context.at(-1);
  if (
    scope === undefined ||
    scope.name === null ||
    scope.parentScopePath.length !== 0 ||
    (assignment.scopePath ?? []).length !== 0
  ) {
    return false;
  }
  const callbackCalls = namedCallbackCallsForFunction(scope);
  if (hasUnknownFunctionReferences(scope, callbackCalls)) return false;
  const executions = [
    ...callsForFunction(scope).map((call) => call),
    ...callbackCalls.map(({ call }) => call),
  ];
  return (
    executions.length > 0 &&
    executions.every(
      (call) => call.context.length === 0 && call.node.start > assignment.offset,
    )
  );
}

function sameScopePath(left, right) {
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

function isFinalIdentifierAssignment(assignment) {
  const candidates = assignmentsByName.get(assignment.name) ?? [];
  return (
    candidates.length > 0 &&
    candidates.every((candidate) =>
      sameScopePath(candidate.scopePath ?? [], assignment.scopePath ?? []),
    ) &&
    candidates.at(-1) === assignment
  );
}

function isUniqueConstInitializer(assignment, before) {
  if (assignment.bindingKind !== "const" || assignment.offset >= before) return false;
  const candidates = assignmentsByName.get(assignment.name) ?? [];
  return candidates.length === 1 && candidates[0] === assignment;
}

function identifierAssignmentIsProvable(assignment, before, context) {
  if (isUniqueConstInitializer(assignment, before)) return true;
  return (
    isFinalIdentifierAssignment(assignment) &&
    assignmentPrecedesAllKnownTopLevelExecutions(assignment, context)
  );
}

function isFinalMemberAssignment(assignment) {
  const candidates = memberAssignmentsByReference.get(assignment.reference) ?? [];
  return (
    candidates.length > 0 &&
    candidates.every((candidate) =>
      sameScopePath(candidate.scopePath ?? [], assignment.scopePath ?? []),
    ) &&
    candidates.at(-1) === assignment
  );
}

function uniqueBundleAssignment(name, before, context, parameterScope) {
  if (context.length === 0 || parameterScope !== null) return null;
  const candidates = assignmentsByName.get(name) ?? [];
  if (candidates.length !== 1) return null;
  const [candidate] = candidates;
  if (!isPathPrefix(candidate.scopePath ?? [], scopePath(context))) return null;
  return identifierAssignmentIsProvable(candidate, before, context) ? candidate : null;
}

function nearestIterationBinding(name, before, context) {
  const path = scopePath(context);
  const candidates = (iterationBindingsByName.get(name) ?? []).filter(
    (binding) =>
      binding.await !== true &&
      binding.bodyRange !== null &&
      binding.bodyRange[0] <= before &&
      before <= binding.bodyRange[1] &&
      isPathPrefix(binding.scopePath, path),
  );
  candidates.sort(
    (left, right) =>
      left.bodyRange[1] - left.bodyRange[0] - (right.bodyRange[1] - right.bodyRange[0]) ||
      right.offset - left.offset,
  );
  return candidates[0] ?? null;
}

function memberAssignmentFor(reference, before, context) {
  const candidates = memberAssignmentsByReference.get(reference) ?? [];
  const path = scopePath(context);
  const visible = candidates.filter(
    (assignment) =>
      assignment.offset < before && isPathPrefix(assignment.scopePath, path),
  );
  const candidate = visible.length > 0 ? visible.at(-1) : candidates[0];
  if (candidate === undefined) return null;
  if (!isPathPrefix(candidate.scopePath ?? [], path)) return null;
  return isFinalMemberAssignment(candidate) &&
    assignmentPrecedesAllKnownTopLevelExecutions(candidate, context)
    ? candidate
    : null;
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

function namedCallbackCallsForFunction(scope) {
  if (scope.name === null) return [];
  return allCallNodes
    .flatMap((call) => {
      if (call.node.type !== "CallExpression" || call.node.callee.type !== "MemberExpression") {
        return [];
      }
      const method = propertyName(call.node.callee.property);
      if (!callbackMethods.has(method)) return [];
      return call.node.arguments.flatMap((argument, argumentIndex) =>
        argument.type === "Identifier" &&
        argument.name === scope.name &&
        nearestVisibleFunction(scope.name, call.context) === scope
          ? [{ call, argumentIndex, method }]
          : [],
      );
    })
    .sort((left, right) => left.call.node.start - right.call.node.start);
}

function hasUnknownFunctionReferences(scope, callbackCalls) {
  if (scope.name === null) return false;
  const callbackOffsets = new Set(
    callbackCalls.map(({ call, argumentIndex }) => call.node.arguments[argumentIndex].start),
  );
  for (const reference of identifierReferences) {
    if (reference.node.name !== scope.name) continue;
    if (nearestVisibleFunction(scope.name, reference.context) !== scope) continue;
    if (reference.node === scope.node.id) continue;
    if (callbackOffsets.has(reference.node.start)) continue;
    if (
      (reference.parent?.type === "CallExpression" ||
        reference.parent?.type === "NewExpression") &&
      reference.parentKey === "callee"
    ) {
      continue;
    }
    if (
      reference.parent?.type === "MemberExpression" &&
      reference.parentKey === "property" &&
      reference.parent.computed === false
    ) {
      continue;
    }
    if (
      reference.parent?.type === "Property" &&
      reference.parentKey === "key" &&
      reference.parent.computed === false
    ) {
      continue;
    }
    return true;
  }
  return false;
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

function namedCallbackParameterResult(scope, parameterIndex, parameterPath, state) {
  if (parameterIndex !== 0) return { matched: false, result: null };
  const callbacks = namedCallbackCallsForFunction(scope);
  if (callbacks.length === 0) return { matched: false, result: null };
  if (hasUnknownFunctionReferences(scope, callbacks)) {
    return {
      matched: true,
      result: unresolvedResult("untraced-function-reference", scope.node, {
        function: scope.name,
      }),
    };
  }
  const results = [];
  for (const { call, argumentIndex, method } of callbacks) {
    const receiver = evaluateNode(
      call.node.callee.object,
      call.context,
      call.node.start,
      {
        ...state,
        depth: state.depth + 1,
      },
    );
    if (!receiver.complete) return { matched: true, result: receiver };
    const values = [];
    for (const candidate of receiver.values) {
      if (candidate?.kind !== "array") {
        return {
          matched: true,
          result: unresolvedResult(
            "non-finite-named-callback-collection",
            call.node.callee.object,
            { function: scope.name, method },
          ),
        };
      }
      for (const item of candidate.items) {
        const selected = valueAtPath(item, parameterPath);
        if (selected === undefined) {
          return {
            matched: true,
            result: unresolvedResult(
              "incomplete-named-callback-destructuring",
              scope.node,
              { function: scope.name, parameterPath },
            ),
          };
        }
        values.push(selected);
      }
    }
    const unique = uniqueValues(values);
    if (unique === null || unique.length === 0) {
      return {
        matched: true,
        result: unresolvedResult("empty-or-oversized-named-callback-domain", call.node, {
          function: scope.name,
          method,
        }),
      };
    }
    results.push({
      complete: true,
      values: unique,
      evidence: [
        ...receiver.evidence,
        resolutionStep("static-named-callback-collection", call.node, {
          function: scope.name,
          method,
          argumentIndex,
          parameterPath,
        }),
      ],
      callers: [
        ...receiver.callers,
        callerStep("named-array-callback", call, { argumentIndex }),
      ],
    });
  }
  return { matched: true, result: mergeResults(results) };
}

function callbackParameterResult(scope, parameterIndex, parameterPath, state) {
  const callback = scope.callback;
  const callee = callback?.call?.callee;
  if (
    !callback ||
    parameterIndex !== 0 ||
    callee?.type !== "MemberExpression" ||
    !callbackMethods.has(propertyName(callee.property))
  ) {
    return unresolvedResult("not-a-static-collection-callback", scope.node, {
      function: scope.name,
      parameterIndex,
    });
  }
  const receiver = evaluateNode(callee.object, scope.parentContext, callback.call.start, {
    ...state,
    depth: state.depth + 1,
  });
  if (!receiver.complete) return receiver;
  const items = [];
  for (const value of receiver.values) {
    if (value?.kind !== "array") {
      return unresolvedResult("non-finite-callback-collection", callee.object);
    }
    for (const item of value.items) {
      const selected = valueAtPath(item, parameterPath);
      if (selected === undefined) {
        return unresolvedResult("incomplete-callback-destructuring", scope.node, {
          function: scope.name,
          parameterIndex,
          parameterPath,
        });
      }
      items.push(selected);
    }
  }
  const values = uniqueValues(items);
  if (values === null || values.length === 0) {
    return unresolvedResult("empty-or-oversized-callback-domain", callback.call);
  }
  return {
    complete: true,
    values,
    evidence: [
      ...receiver.evidence,
      resolutionStep("static-callback-collection", callback.call, {
        method: propertyName(callee.property),
        parameter: scope.params[parameterIndex],
        parameterPath,
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

function functionParameterResult(scope, parameterIndex, parameterPath, state) {
  const callback = callbackParameterResult(
    scope,
    parameterIndex,
    parameterPath,
    state,
  );
  if (callback.complete) return callback;
  const namedCallback = namedCallbackParameterResult(
    scope,
    parameterIndex,
    parameterPath,
    state,
  );
  const namedCallbackCalls = namedCallbackCallsForFunction(scope);
  if (hasUnknownFunctionReferences(scope, namedCallbackCalls)) {
    return unresolvedResult("untraced-function-reference", scope.node, {
      function: scope.name,
      parameterIndex,
    });
  }
  const calls = callsForFunction(scope);
  if (calls.length === 0 && namedCallback.matched) return namedCallback.result;
  if (calls.length === 0) {
    return unresolvedResult("no-static-function-callers", scope.node, {
      function: scope.name,
      parameterIndex,
    });
  }
  const results = [];
  for (const call of calls) {
    const argument = call.node.arguments[parameterIndex];
    if (!argument || argument.type === "SpreadElement") {
      return unresolvedResult("incomplete-function-argument", call.node, {
        function: scope.name,
        parameterIndex,
      });
    }
    const result = evaluateNode(argument, call.context, call.node.start, {
      ...state,
      depth: state.depth + 1,
    });
    if (!result.complete) return result;
    const projected = projectResultPath(
      result,
      parameterPath,
      argument,
      scope.params[parameterIndex],
    );
    if (!projected.complete) return projected;
    results.push({
      ...projected,
      evidence: [
        ...projected.evidence,
        resolutionStep("finite-function-argument", argument, {
          function: scope.name,
          parameter: scope.params[parameterIndex],
          parameterPath,
        }),
      ],
      callers: [
        ...projected.callers,
        callerStep("function-call", call, { argumentIndex: parameterIndex }),
      ],
    });
  }
  if (namedCallback.matched) results.push(namedCallback.result);
  return mergeResults(results);
}

function valueAtPath(value, path) {
  let current = value;
  for (const segment of path) {
    if (current?.kind === "array" && typeof segment === "number") {
      current = current.items[segment];
    } else if (current?.kind === "object" && typeof segment === "string") {
      if (current.unsafeKeys?.has(segment)) return undefined;
      const values = current.properties.get(segment);
      if (!values || values.length !== 1) return undefined;
      [current] = values;
    } else {
      return undefined;
    }
    if (current === undefined) return undefined;
  }
  return current;
}

function projectResultPath(result, path, node, identifier) {
  if (path.length === 0) return result;
  const values = [];
  for (const value of result.values) {
    const selected = valueAtPath(value, path);
    if (selected === undefined) {
      return unresolvedResult("incomplete-static-destructuring", node, {
        identifier,
        path,
      });
    }
    values.push(selected);
  }
  const unique = uniqueValues(values);
  if (unique === null || unique.length === 0) {
    return unresolvedResult("empty-or-oversized-destructured-domain", node, {
      identifier,
      path,
    });
  }
  return {
    ...result,
    values: unique,
    evidence: [
      ...result.evidence,
      resolutionStep("static-destructuring", node, { identifier, path }),
    ],
  };
}

function iterationBindingResult(binding, state) {
  const collection = evaluateNode(
    binding.rightNode,
    binding.context,
    binding.offset,
    {
      ...state,
      depth: state.depth + 1,
    },
  );
  if (!collection.complete) return collection;
  const values = [];
  for (const candidate of collection.values) {
    if (candidate?.kind !== "array") {
      return unresolvedResult("non-finite-iteration-source", binding.rightNode, {
        identifier: binding.name,
      });
    }
    for (const item of candidate.items) {
      const selected = valueAtPath(item, binding.path);
      if (selected === undefined) {
        return unresolvedResult("incomplete-destructuring-path", binding.rightNode, {
          identifier: binding.name,
          path: binding.path,
        });
      }
      values.push(selected);
    }
  }
  const unique = uniqueValues(values);
  if (unique === null || unique.length === 0) {
    return unresolvedResult("empty-or-oversized-iteration-domain", binding.rightNode, {
      identifier: binding.name,
    });
  }
  return {
    complete: true,
    values: unique,
    evidence: [
      ...collection.evidence,
      resolutionStep("static-for-of-collection", binding.rightNode, {
        identifier: binding.name,
        path: binding.path,
      }),
    ],
    callers: collection.callers,
  };
}

function evaluateIdentifier(node, context, before, state) {
  const parameter = nearestParameterScope(node.name, context);
  const iteration = nearestIterationBinding(node.name, before, context);
  const assignment = nearestAssignment(node.name, before, context, parameter);
  if (
    assignment !== null &&
    (iteration === null || assignment.offset > iteration.offset)
  ) {
    if (!identifierAssignmentIsProvable(assignment, before, context)) {
      return unresolvedResult(
        "assignment-does-not-dominate-function-executions",
        assignment.valueNode,
        { identifier: node.name, assignmentOffset: assignment.offset },
      );
    }
    const key = `assignment:${assignment.offset}`;
    if (state.seen.has(key)) {
      return unresolvedResult("resolution-cycle", node, { identifier: node.name });
    }
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
  if (iteration !== null) {
    const key = `iteration:${iteration.offset}:${node.name}:${JSON.stringify(iteration.path)}`;
    if (state.seen.has(key)) {
      return unresolvedResult("resolution-cycle", node, { identifier: node.name });
    }
    return iterationBindingResult(iteration, {
      ...state,
      depth: state.depth + 1,
      seen: new Set([...state.seen, key]),
    });
  }
  if (parameter !== null) {
    const key = `parameter:${parameter.scope.id}:${parameter.parameterIndex}:${JSON.stringify(parameter.path)}`;
    if (state.seen.has(key)) {
      return unresolvedResult("resolution-cycle", node, { identifier: node.name });
    }
    return functionParameterResult(
      parameter.scope,
      parameter.parameterIndex,
      parameter.path,
      {
        ...state,
        depth: state.depth + 1,
        seen: new Set([...state.seen, key]),
      },
    );
  }
  const unique = uniqueBundleAssignment(node.name, before, context, parameter);
  if (unique !== null) {
    const key = `unique-bundle-assignment:${unique.offset}`;
    if (state.seen.has(key)) {
      return unresolvedResult("resolution-cycle", node, { identifier: node.name });
    }
    const result = evaluateNode(
      unique.valueNode,
      unique.context,
      unique.offset,
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
        resolutionStep("unique-bundle-assignment", unique.valueNode, {
          identifier: node.name,
          assignmentOffset: unique.offset,
          bindingKind: unique.bindingKind,
        }),
      ],
    };
  }
  return unresolvedResult("runtime-identifier", node, { identifier: node.name });
}

function evaluateTemplate(node, context, before, state) {
  let values = [""];
  let evidence = [resolutionStep("static-template", node)];
  let callers = [];
  for (let index = 0; index < node.quasis.length; index += 1) {
    const quasi = node.quasis[index].value.cooked;
    if (quasi === null) return unresolvedResult("invalid-template-quasi", node);
    values = values.map((value) => value + quasi);
    if (index >= node.expressions.length) continue;
    const expression = evaluateNode(node.expressions[index], context, before, {
      ...state,
      depth: state.depth + 1,
    });
    if (!expression.complete) return expression;
    if (expression.values.some((value) => typeof value !== "string")) {
      return unresolvedResult("non-string-template-expression", node.expressions[index]);
    }
    const expanded = [];
    for (const prefix of values) {
      for (const value of expression.values) {
        expanded.push(prefix + value);
        if (expanded.length > maxFiniteValues) {
          return unresolvedResult("oversized-template-domain", node, {
            maxFiniteValues,
          });
        }
      }
    }
    values = expanded;
    evidence.push(...expression.evidence);
    callers.push(...expression.callers);
  }
  return { complete: true, values, evidence, callers };
}

function guaranteedFunctionReturn(scope) {
  const body = scope.node.body;
  if (scope.node.type === "ArrowFunctionExpression" && body.type !== "BlockStatement") {
    return body;
  }
  if (
    body.type === "BlockStatement" &&
    body.body.length === 1 &&
    body.body[0].type === "ReturnStatement" &&
    body.body[0].argument !== null
  ) {
    return body.body[0].argument;
  }
  return null;
}

function directFunctionResult(node, context, before, state) {
  if (node.callee.type !== "Identifier") {
    return unresolvedResult("non-direct-function-call", node);
  }
  const scope = nearestVisibleFunction(node.callee.name, context);
  if (scope === null || scope.params.length !== 0 || node.arguments.length !== 0) {
    return unresolvedResult("runtime-function-call", node, {
      callee: node.callee.name,
    });
  }
  const returned = guaranteedFunctionReturn(scope);
  if (returned === null) {
    return unresolvedResult("non-trivial-function-return", node, {
      callee: node.callee.name,
    });
  }
  const key = `function-return:${scope.id}`;
  if (state.seen.has(key)) {
    return unresolvedResult("resolution-cycle", node, { callee: node.callee.name });
  }
  const result = evaluateNode(
    returned,
    [...scope.parentContext, scope],
    returned.start,
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
      resolutionStep("static-function-return", returned, {
        function: scope.name,
      }),
    ],
    callers: [
      ...result.callers,
      callerStep("direct-function-call", { node, context }),
    ],
  };
}

function directMemberAssignmentResult(node, context, before, state) {
  const reference = staticReference(node);
  if (reference === null) return unresolvedResult("dynamic-member-reference", node);
  const assignment = memberAssignmentFor(reference, before, context);
  if (assignment === null) {
    return unresolvedResult(
      memberAssignmentsByReference.has(reference)
        ? "assignment-does-not-dominate-function-executions"
        : "runtime-object-member",
      node,
      { reference },
    );
  }
  const key = `member-assignment:${assignment.offset}`;
  if (state.seen.has(key)) {
    return unresolvedResult("resolution-cycle", node, { reference });
  }
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
      resolutionStep("unique-member-assignment", assignment.valueNode, {
        reference,
        assignmentOffset: assignment.offset,
      }),
    ],
  };
}

function primitiveBinaryResult(node, context, before, state) {
  if (node.operator !== "+") {
    return unresolvedResult("unsupported-binary-operator", node, {
      operator: node.operator,
    });
  }
  const left = evaluateNode(node.left, context, before, {
    ...state,
    depth: state.depth + 1,
  });
  const right = evaluateNode(node.right, context, before, {
    ...state,
    depth: state.depth + 1,
  });
  if (!left.complete || !right.complete) return mergeResults([left, right]);
  const values = [];
  for (const first of left.values) {
    for (const second of right.values) {
      if (
        !["string", "number", "boolean"].includes(typeof first) ||
        !["string", "number", "boolean"].includes(typeof second)
      ) {
        return unresolvedResult("non-primitive-concatenation", node);
      }
      values.push(first + second);
    }
  }
  const unique = uniqueValues(values);
  if (unique === null || unique.length === 0) {
    return unresolvedResult("empty-or-oversized-concatenation", node);
  }
  return {
    complete: true,
    values: unique,
    evidence: [
      ...left.evidence,
      ...right.evidence,
      resolutionStep("static-binary-concatenation", node, { operator: "+" }),
    ],
    callers: [...left.callers, ...right.callers],
  };
}

function evaluateNode(node, context, before, state) {
  if (!node) return unresolvedResult("missing-expression");
  if (state.depth > maxResolutionDepth) {
    return unresolvedResult("resolution-depth-limit", node, {
      maxResolutionDepth,
    });
  }
  if (node.type === "ChainExpression") {
    return evaluateNode(node.expression, context, before, state);
  }
  if (node.type === "SequenceExpression" && node.expressions.length > 0) {
    return evaluateNode(node.expressions.at(-1), context, before, {
      ...state,
      depth: state.depth + 1,
    });
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
  if (
    node.type === "UnaryExpression" &&
    (node.operator === "+" || node.operator === "-")
  ) {
    const argument = evaluateNode(node.argument, context, before, {
      ...state,
      depth: state.depth + 1,
    });
    if (!argument.complete || argument.values.some((value) => typeof value !== "number")) {
      return argument.complete
        ? unresolvedResult("non-numeric-unary-operand", node)
        : argument;
    }
    return {
      ...argument,
      values: argument.values.map((value) =>
        node.operator === "-" ? -value : +value,
      ),
      evidence: [
        ...argument.evidence,
        resolutionStep("static-unary-number", node, { operator: node.operator }),
      ],
    };
  }
  if (node.type === "BinaryExpression") {
    return primitiveBinaryResult(node, context, before, state);
  }
  if (node.type === "LogicalExpression") {
    return unresolvedResult("runtime-logical-name", node, {
      operator: node.operator,
    });
  }
  if (node.type === "AwaitExpression") {
    return unresolvedResult("runtime-await-result", node);
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
      if (!element) return unresolvedResult("array-hole", node);
      const target = element.type === "SpreadElement" ? element.argument : element;
      const result = evaluateNode(target, context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (!result.complete) return result;
      if (element.type === "SpreadElement") {
        for (const value of result.values) {
          if (value?.kind !== "array") {
            return unresolvedResult("non-finite-array-spread", element.argument);
          }
          items.push(...value.items);
        }
        evidence.push(
          resolutionStep("static-array-spread", element.argument),
        );
      } else {
        items.push(...result.values);
      }
      evidence.push(...result.evidence);
      callers.push(...result.callers);
    }
    const unique = uniqueValues(items);
    if (unique === null) return unresolvedResult("oversized-array-domain", node);
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
        const spread = evaluateNode(property.argument, context, before, {
          ...state,
          depth: state.depth + 1,
        });
        if (!spread.complete) {
          const spreadKeys = staticObjectKeys(property.argument, context);
          if (spreadKeys === null) return spread;
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
        for (const value of spread.values) {
          if (value?.kind !== "object") {
            return unresolvedResult("non-finite-object-spread", property.argument);
          }
          for (const [key, values] of value.properties) {
            if (value.unsafeKeys?.has(key)) {
              properties.delete(key);
              unsafeKeys.add(key);
            } else {
              properties.set(key, values);
              unsafeKeys.delete(key);
            }
          }
        }
        evidence.push(...spread.evidence);
        callers.push(...spread.callers);
        evidence.push(
          resolutionStep("static-object-spread", property.argument),
        );
        continue;
      }
      if (
        property.type !== "Property" ||
        property.kind !== "init"
      ) {
        return unresolvedResult("unsupported-object-property", property);
      }
      let keys;
      let keyEvidence = [];
      let keyCallers = [];
      if (property.computed) {
        const keyResult = evaluateNode(property.key, context, before, {
          ...state,
          depth: state.depth + 1,
        });
        if (
          !keyResult.complete ||
          keyResult.values.some(
            (value) => typeof value !== "string" && typeof value !== "number",
          )
        ) {
          return keyResult.complete
            ? unresolvedResult("non-finite-object-key", property.key)
            : keyResult;
        }
        keys = keyResult.values.map(String);
        keyEvidence = keyResult.evidence;
        keyCallers = keyResult.callers;
      } else {
        const key = propertyName(property.key);
        if (key === null) return unresolvedResult("unsupported-object-key", property.key);
        keys = [key];
      }
      const result = evaluateNode(property.value, context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (!result.complete) return result;
      for (const key of keys) {
        properties.set(key, result.values);
        unsafeKeys.delete(key);
      }
      evidence.push(...keyEvidence, ...result.evidence);
      callers.push(...keyCallers, ...result.callers);
    }
    return {
      complete: true,
      values: [{ kind: "object", properties, unsafeKeys }],
      evidence,
      callers,
    };
  }
  if (node.type === "MemberExpression") {
    if (isProcessEnv(node)) {
      return unresolvedResult("runtime-environment-keyset", node);
    }
    const direct = directMemberAssignmentResult(node, context, before, state);
    if (direct.complete) return direct;
    if (
      direct.failures?.some(
        (failure) =>
          failure.reason === "assignment-does-not-dominate-function-executions",
      )
    ) {
      return direct;
    }
    const object = evaluateNode(node.object, context, before, {
      ...state,
      depth: state.depth + 1,
    });
    if (!object.complete) {
      return {
        ...object,
        failures: [...(direct.failures ?? []), ...(object.failures ?? [])],
      };
    }
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
        return keyResult.complete
          ? unresolvedResult("non-finite-member-key", node.property)
          : keyResult;
      }
      keys = keyResult.values.map(String);
      keyEvidence = keyResult.evidence;
      keyCallers = keyResult.callers;
    } else {
      const key = propertyName(node.property);
      if (key === null) return unresolvedResult("unsupported-member-key", node.property);
      keys = [key];
    }
    const values = [];
    for (const value of object.values) {
      for (const key of keys) {
        if (value?.kind === "object") {
          if (value.unsafeKeys?.has(key)) {
            return unresolvedResult("unsafe-object-spread-key", node, { key });
          }
          const propertyValues = value.properties.get(key);
          if (!propertyValues) {
            return unresolvedResult("missing-static-object-key", node, { key });
          }
          values.push(...propertyValues);
        } else if (value?.kind === "array" && /^\d+$/.test(key)) {
          const item = value.items[Number(key)];
          if (item === undefined) {
            return unresolvedResult("array-index-out-of-range", node, { key });
          }
          values.push(item);
        } else {
          return unresolvedResult("runtime-object-member", node, { key });
        }
      }
    }
    const unique = uniqueValues(values);
    if (unique === null || unique.length === 0) {
      return unresolvedResult("empty-or-oversized-member-domain", node);
    }
    return {
      ...object,
      values: unique,
      evidence: [...object.evidence, ...keyEvidence],
      callers: [...object.callers, ...keyCallers],
    };
  }
  if (
    node.type === "NewExpression" &&
    identifierName(node.callee) === "Set" &&
    node.arguments.length <= 1
  ) {
    if (node.arguments.length === 0) {
      return {
        complete: true,
        values: [{ kind: "array", items: [] }],
        evidence: [resolutionStep("static-set", node)],
        callers: [],
      };
    }
    const argument = evaluateNode(node.arguments[0], context, before, {
      ...state,
      depth: state.depth + 1,
    });
    if (!argument.complete) return argument;
    if (argument.values.some((value) => value?.kind !== "array")) {
      return unresolvedResult("non-finite-set-source", node.arguments[0]);
    }
    return {
      ...argument,
      evidence: [...argument.evidence, resolutionStep("static-set", node)],
    };
  }
  if (node.type === "NewExpression") {
    return unresolvedResult("runtime-constructed-collection", node, {
      callee: staticReference(node.callee),
    });
  }
  if (node.type === "CallExpression") {
    const callee =
      node.callee.type === "ChainExpression" ? node.callee.expression : node.callee;
    if (
      callee?.type === "MemberExpression" &&
      identifierName(callee.object) === "Object" &&
      ["keys", "values", "entries"].includes(propertyName(callee.property)) &&
      node.arguments.length === 1
    ) {
      const method = propertyName(callee.property);
      const object = evaluateNode(node.arguments[0], context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (!object.complete) return object;
      const items = [];
      for (const value of object.values) {
        if (value?.kind !== "object" || (value.unsafeKeys?.size ?? 0) > 0) {
          return unresolvedResult("non-finite-object-enumeration", node.arguments[0], {
            method,
          });
        }
        for (const [key, propertyValues] of value.properties) {
          if (method === "keys") items.push(key);
          else if (method === "values") items.push(...propertyValues);
          else {
            for (const propertyValue of propertyValues) {
              items.push({ kind: "array", items: [key, propertyValue] });
            }
          }
        }
      }
      const unique = uniqueValues(items);
      if (unique === null) {
        return unresolvedResult("oversized-object-enumeration", node, { method });
      }
      return {
        complete: true,
        values: [{ kind: "array", items: unique }],
        evidence: [
          ...object.evidence,
          resolutionStep("static-object-enumeration", node, { method }),
        ],
        callers: object.callers,
      };
    }
    if (
      callee?.type === "MemberExpression" &&
      identifierName(callee.object) === "Object" &&
      propertyName(callee.property) === "freeze" &&
      node.arguments.length === 1
    ) {
      const frozen = evaluateNode(node.arguments[0], context, before, {
        ...state,
        depth: state.depth + 1,
      });
      if (!frozen.complete) return frozen;
      return {
        ...frozen,
        evidence: [
          ...frozen.evidence,
          resolutionStep("static-object-freeze", node),
        ],
      };
    }
    if (callee?.type === "MemberExpression") {
      const method = propertyName(callee.property);
      if (
        node.arguments.length === 0 &&
        (method === "toUpperCase" || method === "toLowerCase")
      ) {
        const object = evaluateNode(callee.object, context, before, {
          ...state,
          depth: state.depth + 1,
        });
        if (!object.complete) return object;
        if (object.values.some((value) => typeof value !== "string")) {
          return unresolvedResult("non-string-transform-source", callee.object, {
            method,
          });
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
      if (
        (method === "find" || method === "filter") &&
        node.arguments.length >= 1
      ) {
        const collection = evaluateNode(callee.object, context, before, {
          ...state,
          depth: state.depth + 1,
        });
        if (!collection.complete) return collection;
        const items = [];
        for (const value of collection.values) {
          if (value?.kind !== "array") {
            return unresolvedResult("non-finite-collection-method", callee.object, {
              method,
            });
          }
          if (method === "find") items.push(...value.items);
          else items.push(value);
        }
        const unique = uniqueValues(items);
        if (unique === null || unique.length === 0) {
          return unresolvedResult("empty-or-oversized-collection-method", node, {
            method,
          });
        }
        return {
          complete: true,
          values: unique,
          evidence: [
            ...collection.evidence,
            resolutionStep("finite-collection-result", node, {
              method,
              predicateIgnored: true,
            }),
          ],
          callers: collection.callers,
        };
      }
      if (method === "at" && node.arguments.length === 1) {
        const collection = evaluateNode(callee.object, context, before, {
          ...state,
          depth: state.depth + 1,
        });
        const index = evaluateNode(node.arguments[0], context, before, {
          ...state,
          depth: state.depth + 1,
        });
        if (!collection.complete || !index.complete) {
          return mergeResults([collection, index]);
        }
        if (
          collection.values.some((value) => value?.kind !== "array") ||
          index.values.some((value) => !Number.isInteger(value))
        ) {
          return unresolvedResult("non-finite-array-at", node);
        }
        const values = [];
        for (const value of collection.values) {
          for (const rawIndex of index.values) {
            const selected = value.items.at(rawIndex);
            if (selected === undefined) {
              return unresolvedResult("array-index-out-of-range", node, {
                index: rawIndex,
              });
            }
            values.push(selected);
          }
        }
        const unique = uniqueValues(values);
        if (unique === null || unique.length === 0) {
          return unresolvedResult("empty-or-oversized-array-at", node);
        }
        return {
          complete: true,
          values: unique,
          evidence: [
            ...collection.evidence,
            ...index.evidence,
            resolutionStep("static-array-at", node),
          ],
          callers: [...collection.callers, ...index.callers],
        };
      }
    }
    const direct = directFunctionResult(node, context, before, state);
    if (direct.complete) return direct;
    return direct;
  }
  return unresolvedResult("unsupported-expression-node", node, {
    nodeType: node.type,
  });
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
  const validEnvironmentNames =
    result.complete &&
    result.values.length > 0 &&
    result.values.every(
      (value) =>
        typeof value === "string" &&
        value.length > 0 &&
        value.length <= maxReferenceLength &&
        /^[A-Za-z_][A-Za-z0-9_]*$/.test(value),
    );
  if (!validEnvironmentNames) {
    const failures = dedupeRecords(
      result.complete
        ? [
            {
              reason: "non-environment-name-domain",
              ...location(candidate.expressionNode),
              range: sourceRange(candidate.expressionNode),
              valueCount: result.values.length,
              valueTypes: [...new Set(result.values.map((value) => typeof value))].sort(),
            },
          ]
        : result.failures ?? [
            {
              reason: "unsupported-or-incomplete",
              ...location(candidate.expressionNode),
              range: sourceRange(candidate.expressionNode),
            },
          ],
    );
    const failureCount = uniqueRecordCount(
      result.complete ? failures : result.failures ?? failures,
    );
    candidate.record.unresolvedResolution = {
      complete: false,
      primaryReason: failures.at(-1)?.reason ?? "unsupported-or-incomplete",
      reasons: [...new Set(failures.map((failure) => failure.reason))].sort(),
      failureCount,
      failuresTruncated: failures.length < failureCount,
      failures,
    };
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
