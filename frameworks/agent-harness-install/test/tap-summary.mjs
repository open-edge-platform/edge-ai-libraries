// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import path from "node:path";
import {pathToFileURL} from "node:url";

export function parseTap(text) {
  const cases = [];
  const plans = [];
  let bailout = false;
  for (const line of text.split(/\r?\n/)) {
    if (/^Bail out!/i.test(line)) bailout = true;
    const plan = /^1\.\.(\d+)\s*$/.exec(line);
    if (plan) plans.push(Number(plan[1]));
    const result = /^(not ok|ok)\s+(\d+)(?:\s+-\s+(.*))?$/.exec(line);
    if (!result) continue;
    const description = result[3] ?? "";
    const directive = /(?:^|\s)#\s*(SKIP|TODO)\b\s*(.*)$/i.exec(description);
    cases.push({
      number: Number(result[2]),
      name: directive ? description.slice(0, directive.index).trim() : description,
      skipped: directive?.[1].toUpperCase() === "SKIP",
      reason: directive?.[2] || "No reason supplied",
      failed: result[1] === "not ok" || directive?.[1].toUpperCase() === "TODO"
    });
  }
  const skipped = cases.filter(c => c.skipped);
  const failed = cases.filter(c => !c.skipped && c.failed).length;
  const passed = cases.length - skipped.length - failed;
  const complete = !bailout && plans.length === 1 && plans[0] > 0 &&
    plans[0] === cases.length && cases.every((c, i) => c.number === i + 1);
  return {executed: passed + failed, passed, failed, skipped, complete};
}

const suites = [
  ["core", "OpenShell startup, runtime and boundaries"],
  ["inference", "Managed inference"],
  ["lifecycle", "Model lifecycle and CLI"],
  ["metrics", "Telemetry (metrics)"],
  ["defaults", "Agent model defaults"],
  ["reporting", "TAP reporting regression"]
];
const escape = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll("|", "&#124;").replace(/[\r\n]/g, " ");

export function summarize(directory, outcomes) {
  const lines = [
    "## OpenShell offline validation",
    "",
    "Executed excludes skipped cases. Counts are top-level cases in each independent report.",
    "",
    "| Suite | Step outcome | Executed | Passed | Failed | Skipped | Report |",
    "|---|---|---:|---:|---:|---:|---|"
  ];
  let success = true;
  const totals = {executed: 0, passed: 0, failed: 0, skipped: 0};
  const skips = [];
  for (const [id, name] of suites) {
    const file = path.join(directory, `${id}.tap`);
    const outcome = outcomes[id] ?? "unknown";
    if (!fs.existsSync(file)) {
      lines.push(`| ${name} | ${escape(outcome)} | — | — | — | — | Missing; not a pass |`);
      success = false;
      continue;
    }
    const result = parseTap(fs.readFileSync(file, "utf8"));
    for (const key of ["executed", "passed", "failed"]) totals[key] += result[key];
    totals.skipped += result.skipped.length;
    const valid = result.complete && result.failed === 0 && outcome === "success";
    success &&= valid;
    lines.push(`| ${name} | ${escape(outcome)} | ${result.executed} | ${result.passed} | ${result.failed} | ${result.skipped.length} | ${result.complete ? "Complete" : "Incomplete/invalid; not a pass"} |`);
    for (const c of result.skipped)
      skips.push(`- **${name}** — ${escape(c.name)}: ${escape(c.reason)}`);
  }
  lines.push(`| **Total observed** | | **${totals.executed}** | **${totals.passed}** | **${totals.failed}** | **${totals.skipped}** | |`,
    "", "### Skipped cases and reasons", "", ...(skips.length ? skips : ["No skipped cases observed."]),
    "", success ? "**Result: passed.**" : "**Result: failed or incomplete. Inspect step outcomes and TAP artifacts.**", "");
  return {markdown: lines.join("\n"), success};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.argv[2]) throw Error("Usage: node test/tap-summary.mjs <report-directory>");
  const {markdown, success} = summarize(process.argv[2],
    JSON.parse(process.env.TEST_STEP_OUTCOMES ?? "{}"));
  console.log(markdown);
  if (process.env.GITHUB_STEP_SUMMARY)
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, markdown);
  if (!success) process.exitCode = 1;
}
