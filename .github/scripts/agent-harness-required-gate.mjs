// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import {fileURLToPath} from "node:url";

export function evaluateGate(env) {
  if (env.CHANGE_RESULT !== "success")
    throw Error(`Change detection did not succeed: ${env.CHANGE_RESULT}`);
  if (env.RELEVANT !== "true" && env.RELEVANT !== "false")
    throw Error(`Missing or invalid change decision: ${env.RELEVANT}`);

  const expected = env.RELEVANT === "true" ? "success" : "skipped";
  if (env.STATIC_RESULT !== expected)
    throw Error(`Static analysis: expected ${expected}, received ${env.STATIC_RESULT}`);
  return env.RELEVANT === "true"
    ? "Passed: Agent Harness static analysis succeeded."
    : "Not applicable: no Agent Harness changes; static analysis was skipped.";
}

if (process.argv[1] &&
    fs.realpathSync(fileURLToPath(import.meta.url)) === fs.realpathSync(process.argv[1])) {
  try {
    const message = evaluateGate(process.env);
    console.log(message);
    if (process.env.GITHUB_STEP_SUMMARY)
      fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `## Agent Harness required static gate\n\n${message}\n`);
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
}
