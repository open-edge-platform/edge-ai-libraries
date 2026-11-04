// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import {pathToFileURL} from "node:url";

export function evaluateGate(env) {
  if (env.CHANGE_RESULT !== "success")
    throw Error(`Change detection did not succeed: ${env.CHANGE_RESULT}`);
  if (env.RELEVANT !== "true" && env.RELEVANT !== "false")
    throw Error(`Missing or invalid change decision: ${env.RELEVANT}`);

  const expected = env.RELEVANT === "true" ? "success" : "skipped";
  for (const [name, result] of [
    ["Static analysis", env.STATIC_RESULT],
    ["Offline regression", env.OFFLINE_RESULT],
    ["Hermes image runtime", env.HERMES_RESULT]
  ]) {
    if (result !== expected)
      throw Error(`${name}: expected ${expected}, received ${result}`);
  }
  return env.RELEVANT === "true"
    ? "Passed: all three Agent Harness quality gates succeeded."
    : "Not applicable: no Agent Harness changes; component jobs were skipped.";
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const message = evaluateGate(process.env);
    console.log(message);
    if (process.env.GITHUB_STEP_SUMMARY)
      fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `## Agent Harness required gate\n\n${message}\n`);
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
}
