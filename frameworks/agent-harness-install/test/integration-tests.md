<!--
Copyright (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# OpenShell prepared-runner integration tests

## Purpose and when to execute

[openshell-integration-test.sh](openshell-integration-test.sh) exercises real
Docker images, OpenShell sandboxes and an existing inference deployment.
Unlike the [offline tests](unit-tests.md), it does not mock those components.
A prepared runner can be a manually operated Linux validation machine, such as
PTL, or the configured self-hosted GitHub Actions runner.

Run this suite:

- Before accepting changes to sandbox images, pinned agent installers, startup,
  filesystem/provider policies, inference attachment or sandbox lifecycle.
- After changing the supported OpenShell version, gateway environment or
  deployment-host configuration, to check compatibility.
- As a scheduled or release-readiness check against a reviewed revision.
- After the offline suite passes, outside active demos or important inference
  sessions. Builds, inference requests and local image tags consume or affect
  shared machine resources even though test sandbox ownership is isolated.

It is **not** an automatic PR or `main`-push job. Those events run the offline
gate. Live CI requires explicit manual dispatch and a protected prepared runner.
Use only reviewed code on a machine with Docker/gateway privileges.

This document describes implemented cases, not an execution report. Record the
commit, environment, date, pass/fail/skips and TAP evidence for each actual run.
Manual PTL checks are not proof that this automated suite passed.

## Prerequisites

- Linux, Bash, Node.js 24, curl, GNU timeout and standard shell utilities.
- Docker accessible to the execution account, with sufficient RAM/disk for
  OpenClaw, Deep Agents Code and Hermes images and sandboxes.
- OpenShell **0.1.5**, with a healthy authenticated gateway available to that
  account.
- Installer-managed IR already running, published only on host loopback and
  serving the exact model selected for the test.
- For managed inference, OVMS ready with that model and connected to IR through
  the expected private backend network. The IR and OVMS REST ports must differ.
- For externally routed inference, `HARNESS_LLM_ROUTER_ENDPOINT` set to the
  existing route. The suite does not manage that external backend.
- Pinned build dependencies accessible over the network or available in caches.
  Runtime sandbox egress restrictions are not image-build restrictions.

The suite does not provision missing shared inference, download a serving model
or create a missing OpenShell gateway. Prepare these using the normal
[installation guide](../docs/agentic-ai-security/agent-sandboxing.md#getting-started)
before running it.

## Execute on a prepared Linux machine

1. Check out the reviewed revision and enter the Agent Harness Install component
   directory. Run under the account that can access Docker and the gateway.
2. Run the offline gate first:

   ```bash
   set -o pipefail
   bash test/openshell-test.sh | tee openshell-offline.tap
   ```

3. Confirm that the prepared inference deployment serves the required exact
   model ID. Do not request a model switch as part of this test run.
4. Run the live suite. This example assumes the prepared service already serves
   `Qwen3.5-9B-int8-ov`:

   ```bash
   set -o pipefail
   env -u HARNESS_HF_MODEL \
     HARNESS_RUN_OPENSHELL_INTEGRATION=1 \
     HARNESS_LLM_MODEL=Qwen3.5-9B-int8-ov \
     bash test/openshell-integration-test.sh \
     | tee openshell-integration.tap
   ```

   Substitute the actual served ID if different. Unsetting `HARNESS_HF_MODEL`
   avoids explicitly requesting model reconfiguration through the environment.
   For a non-default prepared environment, set `HARNESS_OPENSHELL_GATEWAY`,
   `HARNESS_IR_CONTAINER`, `HARNESS_IR_PORT`, `HARNESS_OVMS_CONTAINER` and
   `HARNESS_OVMS_REST_PORT` as appropriate. Preserve the external-route setting
   when testing externally routed inference.

5. Inspect the exit status and TAP report. A passing complete run currently has
   **30 top-level cases**, including final cleanup. The model-default case
   invokes nine nested Node cases with Hermes required; these are not additional
   top-level cases. A failure stops subsequent dependent cases, so a partial
   report is not a complete pass.
6. Retain the TAP report with the tested commit and environment information.
   Verify final cleanup passed before handing the machine back to other users.

There is no supported individual-case filter. Cases depend on earlier
installation, workspace fixtures and inference snapshots; run the complete
script rather than sourcing it or manually calling its internal functions.

## Execute through GitHub Actions

The [quality-gates workflow](../../../.github/workflows/agent-harness-openshell.yml)
contains a prepared-runner job. Administrators must first configure the
`openshell-validation` runner label and protected environment, including
maintainer approval and suitable branch restrictions.

1. Select the workflow's manual **Run workflow** action on an available,
   reviewed ref.
2. Enable the `live` input and supply the exact already-served `model` ID.
3. Approve the protected environment if required.
4. The live job runs only after the offline job succeeds.
5. Review the job result and download the integration TAP artifact.

A new workflow may not appear in manual-dispatch UI until it exists on the
default branch. Before that, execute the script directly on the prepared Linux
machine. For runner-variable and security setup, see the
[quality-gates README](README.md#github-actions-setup).

## Individual cases and objectives

The IDs below are catalogue references, not executable selectors. They follow
the source registration order. Each row is a separately registered top-level
case, except that final cleanup is registered by the exit handler.

| ID | Registered case / source function | Objective and expected result |
|---|---|---|
| LIVE-01 | Prepared gateway and loopback inference are healthy (`preflight`) | Validate Docker/gateway access, exact model and inference boundary configuration; require distinct IR/OVMS ports and snapshot shared container identity/start times/bindings. |
| LIVE-02 | OpenClaw installation and native inference (`install_agent openclaw`) | Build/install a real OpenClaw sandbox, complete installer onboarding and reach Ready. |
| LIVE-03 | OpenClaw status dispatch (`status_agent openclaw`) | Confirm the installer's status command succeeds against the real deployment. |
| LIVE-04 | OpenClaw repeated install preserves identity (`idempotent_install openclaw`) | Rerun installation and confirm the sandbox name remains unchanged. |
| LIVE-05 | OpenClaw implicit model change rejected (`model_change_rejected openclaw`) | Reject an unserved environment-model override with an intended diagnostic instead of silently changing the route/model. |
| LIVE-06 | OpenClaw non-root workspace and network boundaries (`sandbox_boundaries openclaw`) | Check non-root execution, host-resource absence, exact workspace read/write, successful IR access and failed direct OVMS-port connection. |
| LIVE-07 | OpenClaw stop/start retains config, workspace and inference (`restart_persistence openclaw`) | Stop/start the sandbox, compare config/workspace hashes and rerun native onboarding inference. |
| LIVE-08 | Deep Agents Code installation and native inference (`install_agent deepagents-code`) | Install a real Dcode sandbox, reach Ready and verify the provider contains its pinned Python path. |
| LIVE-09 | Deep Agents Code status dispatch (`status_agent deepagents-code`) | Confirm status succeeds for the real Dcode deployment. |
| LIVE-10 | Deep Agents Code repeated install preserves identity (`idempotent_install deepagents-code`) | Confirm installation reruns do not replace the sandbox identity. |
| LIVE-11 | Deep Agents Code implicit model change rejected (`model_change_rejected deepagents-code`) | Reject the unserved environment-model override. |
| LIVE-12 | Deep Agents Code non-root workspace and network boundaries (`sandbox_boundaries deepagents-code`) | Exercise the same actual resource-visibility, workspace and network assertions for Dcode. |
| LIVE-13 | Deep Agents Code stop/start retains config, workspace and inference (`restart_persistence deepagents-code`) | Verify config/workspace hashes and native inference after restart. |
| LIVE-14 | Hermes installation and native inference (`install_agent hermes`) | Install a real Hermes sandbox, complete onboarding and reach Ready. |
| LIVE-15 | Hermes status dispatch (`status_agent hermes`) | Confirm status succeeds for the real Hermes deployment. |
| LIVE-16 | Hermes repeated install preserves identity (`idempotent_install hermes`) | Confirm installation reruns preserve sandbox identity. |
| LIVE-17 | Hermes implicit model change rejected (`model_change_rejected hermes`) | Reject the unserved environment-model override. |
| LIVE-18 | Hermes non-root workspace and network boundaries (`sandbox_boundaries hermes`) | Exercise the same actual resource-visibility, workspace and network assertions for Hermes. |
| LIVE-19 | Hermes stop/start retains config, workspace and inference (`restart_persistence hermes`) | Verify config/workspace hashes and native inference after restart. |
| LIVE-20 | Built image applies Qwen defaults and Hermes request overrides offline (`local_model_defaults`) | Run all nine model-default tests in a disposable, network-disabled Hermes image with its real Python/YAML runtime; missing Hermes runtime must fail, not skip. |
| LIVE-21 | Deep Agents Code can allocate sandbox-local PTYs (`dcode_pty`) | Allocate and close a real pseudo-terminal inside the Dcode sandbox. |
| LIVE-22 | Hermes browser terminal can allocate sandbox-local PTYs (`hermes_pty`) | Allocate and close a real pseudo-terminal using Hermes's Python runtime; this checks a browser-terminal prerequisite, not browser chat. |
| LIVE-23 | Complete uninstall requires explicit consent | Invoke full uninstall without confirmation/non-interactive consent and require the intended refusal; do not perform a full uninstall. |
| LIVE-24 | OpenClaw owned uninstall removes sandbox and provider (`remove_agent openclaw`) | Perform scoped removal, require the active profile to disappear and archive to exist, and confirm sandbox/provider absence. |
| LIVE-25 | Deep Agents Code owned uninstall removes sandbox and provider (`remove_agent deepagents-code`) | Apply the same scoped-removal and record assertions to Dcode. |
| LIVE-26 | Hermes owned uninstall removes sandbox and provider (`remove_agent hermes`) | Apply the same scoped-removal and record assertions to Hermes. |
| LIVE-27 | Hermes can be freshly provisioned after removal (`install_agent hermes`) | Verify installation/onboarding succeeds again after cleanup. |
| LIVE-28 | Fresh Hermes installation can be removed (`remove_agent hermes`) | Verify the reinstalled sandbox/provider can also be removed and archived. |
| LIVE-29 | Shared inference containers, bindings and model remain unchanged (`inference_unchanged`) | Compare before/after container IDs, start times and bindings; revalidate shared inference and the selected model. |
| LIVE-30 | Final owned-resource cleanup (`on_exit` / `cleanup_resources`) | Attempt scoped cleanup of remaining recorded test sandboxes and the host marker on exit, including after ordinary failure or interruption; report cleanup failure as a failed case. |

### What the boundary checks establish

For each agent, the script checks:

- Its process is not root.
- The supplied host agent-home path, host-only marker and Docker socket are not
  visible at their tested paths.
- A random token written directly to `/sandbox` is read back exactly.
- IR access succeeds before checking that the direct OVMS-port connection fails
  with curl exit code 7.

These are targeted observations, not proof of complete isolation. In particular,
the failed OVMS connection alone does not distinguish policy enforcement from
every possible service-side cause, and it does not test all external egress.

## Cleanup and operational safety

Every invocation creates a random `.agent-harness-ci-<random>` state directory
under the runner account's home and prints it in the TAP header. Only profiles
recorded there are passed to scoped uninstall. Test images, archived ownership
records and shared OpenShell/inference services are intentionally retained.

The exit handler attempts cleanup after normal completion, a failed gate,
SIGINT or SIGTERM. SIGKILL, loss of connectivity or host power loss cannot
guarantee cleanup. If resources remain:

1. Read the exact state-directory basename from that run's TAP header.
2. Inspect its remaining active agent profiles.
3. Rerun scoped removal for each remaining agent, substituting that basename:

   ```bash
   HARNESS_STATE_DIRNAME=.agent-harness-ci-<recorded-suffix> \
     bash uninstall.sh --runtime openshell --sandbox-only \
     --harness hermes --yes
   ```

   Replace the angle-bracket placeholder before execution. Select `openclaw` or
   `deepagents-code` instead when cleaning that agent's recorded profile.
4. Verify success and retain the archived records as evidence. Never perform
   broad gateway deletion or full shared-service uninstall to clean up a test.

## Limits and reporting

- Stop/start is not a host reboot test.
- Native inference and direct file checks do not certify model-driven tool use.
- PTY allocation is not automated browser UI/chat acceptance.
- The suite does not perform a real coordinated model switch, full deployment
  uninstall, MCP/messaging acceptance, performance benchmarking or exhaustive
  filesystem isolation testing across kernel/Landlock configurations.
- A successful run does not override known model-response issues, including
  repetition observed during a separate browser test.
- Report unexecuted or skipped cases explicitly. A case catalogue or manual
  smoke test is not an automated integration execution report.
