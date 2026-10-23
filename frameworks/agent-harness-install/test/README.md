<!--
Copyright (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# OpenShell quality gates

Both suites emit TAP 13 reports and return a nonzero exit status on failure.
No test requires a GitHub token. Live inference uses the prepared runner's
shared IR, which must already have any required upstream authentication
configured. Model-generated text is not used as proof that a file operation
succeeded.

## Offline PR gate

Requirements: Linux, Bash, Node.js 24 and standard command-line tools.
No Docker daemon, OpenShell installation, GPU, model download or external network
is required. HTTP response tests use a temporary server bound to host loopback.

From the component directory:

```bash
set -o pipefail
bash test/openshell-test.sh | tee openshell-offline.tap
```

| Area | Automated assertions |
|---|---|
| OpenClaw startup | Private SQLite temp directory exported before Node starts, real on-disk FTS5 initialization, inherited SQLite temp path replaced, mode 700, config/token/database preservation across restart, fail-fast directory creation and permissions |
| Runtime selection | Host default, supported agents, invalid runtime and unsupported agent rejection |
| Persisted state | Separate agent paths, valid profile loading, missing/malformed/wrong-agent/invalid-owner/newline/symlink rejection |
| Ownership | Matching label accepted; mismatch or inaccessible gateway rejected |
| Resource discovery | Sandbox/provider lists, absence, malformed/schema-invalid/paginated/unavailable responses |
| Version pin | Exact OpenShell version accepted; incompatible version rejected |
| Inference boundary | Invalid ports, LAN/IPv6/mismatched/missing Docker publication and missing IR rejection |
| Model discovery | Exact served model accepted; unserved model, HTTP error and malformed JSON rejected |
| Managed inference | OpenShell Qwen3.5 default and snapshot exporter, native OVMS graph generation, host compatibility, explicit overrides, persisted selection, fresh-only provisioning, partial deployment refusal, managed OVMS readiness/network/publication, both proxy bypass variables |
| Model lifecycle | Source/export option roundtrip, coordinated two-agent switch, original environment overridden after restart, token/history preservation, pending-switch retry and conflict rejection, legacy-image preflight, full/scoped uninstall and OpenShell package ownership safeguards |
| Local-model defaults | Exact Qwen context/output/thinking/sampling/prompt settings, idempotence, explicit overrides and later edits, selection-only isolation, removal on model switch, non-Qwen preservation |
| Hermes browser policy | Hermes policy differs from the base only by sandbox-local `/dev/ptmx` and `/dev/pts` write access; installer selects it only for Hermes |
| CLI safety | Help, invalid runtime, host connect, explicit sandbox deletion consent and host-only deletion flags |
| Cleanup safeguards | Deletion order, archived records, unowned-resource refusal, pending deletion retaining provider/identity |
| Test infrastructure | Intermediate assertion failures produce a nonzero suite result; live suite requires explicit opt-in |

Each test runs in a separate subshell. Temporary HOME fixtures prevent access
to real agent profiles. Expected failures must match their intended diagnostic,
so an unrelated missing dependency cannot make a negative case pass.

OpenClaw startup sets `SQLITE_TMPDIR=$HOME/.openclaw/tmp/sqlite` before
configuration generation or gateway launch. SQLite's default temporary-file
locations may be denied by the sandbox filesystem policy. This directory is
created with mode 700 without expanding that policy or modifying existing
databases. The offline startup cases run the real entrypoint with a mock gateway
and Node's real SQLite/FTS5 support; they do not certify a full gateway chat turn.

`node --test test/model-defaults-test.mjs` also runs independently. Hermes cases
skip outside its image because they require the pinned bundled Python/YAML
runtime. In a disposable Hermes image with the current helper and test mounted,
the same cases validate real YAML roundtrips and Hermes provider normalization
into request overrides without inference/network access. Config checks are not
proof of chat quality, latency or model-driven tool use.

## Opt-in prepared-runner gate

Requirements:

- Linux with Bash, Node.js 24, curl and GNU timeout on PATH.
- Docker accessible to the runner account, with enough disk/RAM for both images.
- OpenShell **0.1.5**, with an already authenticated, healthy local gateway.
- A running installer-managed IR container, published only on loopback, serving
  the exact requested model. For local inference, managed OVMS must be ready
  with that model and share the configured private backend network with IR.
  For externally routed inference, also set `HARNESS_LLM_ROUTER_ENDPOINT` to
  the existing external route so sandbox installs do not require local OVMS.
- Access to pinned build dependencies (or cached image layers). The suite does
  not provision missing OpenShell/inference services or models; preflight
  requires them to be ready. Run with `HARNESS_HF_MODEL` unset to avoid
  explicitly requesting model reconfiguration through the environment.

```bash
set -o pipefail
HARNESS_RUN_OPENSHELL_INTEGRATION=1 \
HARNESS_LLM_MODEL='<exact-served-model-id>' \
bash test/openshell-integration-test.sh | tee openshell-integration.tap
```

Optional settings: `HARNESS_OPENSHELL_GATEWAY`, `HARNESS_IR_CONTAINER`,
`HARNESS_IR_PORT`, `HARNESS_OVMS_CONTAINER`, `HARNESS_OVMS_REST_PORT`.
The IR and denied direct-OVMS ports must differ.

| Area | Automated assertions |
|---|---|
| Prerequisites | Gateway health, exact model discovery and loopback-only IR publication |
| Installation | Both images build, sandboxes become Ready, native inference checks pass |
| Local-model defaults | Disposable network-isolated built Hermes image must run all defaults cases, including native YAML and provider request mapping (no runtime-dependent skips) |
| Hermes browser terminal | Real sandbox Python can allocate and close a PTY; this is a prerequisite check, not an automated dashboard/browser chat turn |
| Dispatch/idempotence | Status works; repeat installation preserves sandbox identity |
| Drift prevention | An unserved `HARNESS_LLM_MODEL` environment override fails rather than silently selecting another model; explicit CLI model switches are covered by offline lifecycle fixtures |
| Boundaries | Non-root runtime, host agent homes/host-only marker/Docker socket absence, exact workspace read/write, IR allowed and direct OVMS connection denied |
| Stop/start | Workspace and agent config hashes persist; native inference works after restart |
| Shared ownership | Full uninstall without confirmation fails; the suite uses `--sandbox-only` for cleanup, not full shared-service uninstall |
| Removal/recovery | Owned sandboxes/providers disappear, records are archived, Hermes can be freshly provisioned and removed |
| Shared services | IR/OVMS container identities, start times and port bindings remain unchanged; IR still serves the model |
| Final cleanup | All remaining test-owned sandboxes are removed, including after ordinary failure or interruption |

Every invocation generates its own `.agent-harness-ci-<random>` state directory
under the runner account's home. Only profiles in that directory are passed to
uninstall with `--sandbox-only`. Archived ownership records are retained for audit. Images and shared
OpenShell/inference services are intentionally retained. A failed cleanup is
reported as a failed test, not silently ignored.

As with any shell trap, SIGKILL or runner power loss cannot guarantee cleanup.
Use the state directory printed in the TAP header to rerun the normal sandbox
uninstall with `HARNESS_STATE_DIRNAME` set to that directory's basename. Never
run a broad sandbox deletion command on a shared gateway.

Stop/start tests do not reboot the host. Native inference and direct workspace
checks do not certify multi-step model-driven tool use, MCP, messaging,
computer use or complete filesystem isolation on all Landlock configurations.
The suite does not automate browser chat or a real cross-agent model switch.
Those require separate acceptance checks; offline lifecycle tests use fixtures
and mocks rather than live OVMS model changes.

## GitHub Actions setup

The repository-level workflow `.github/workflows/agent-harness-openshell.yml`
runs **OpenShell offline gate** for relevant pull requests and main pushes.
It attempts to upload the TAP report even when tests fail; a failure before TAP
generation (for example, a shell syntax failure) may leave no report to upload.
It does not run the existing destructive host smoke/full-flow suites.

For live validation, administrators must:

1. Register a prepared self-hosted Linux runner with the `openshell-validation`
   label, running under the account with gateway credentials.
2. Create the `openshell-validation` environment with required maintainer
   reviewers and appropriate deployment-branch restrictions. Do not allow
   unreviewed fork code to run on this privileged runner.
3. Optionally configure `OPENSHELL_GATEWAY`, `OPENSHELL_IR_CONTAINER` and
   `OPENSHELL_IR_PORT` environment variables in GitHub's **Variables** settings.
4. Manually dispatch the workflow for a reviewed ref, enable `live`, and supply
   the exact model ID. The live job runs only after the offline gate succeeds.

The workflow does not use `pull_request_target`, does not persist checkout
credentials, uses read-only repository access and serializes live runs.
Branch protection/rulesets must be configured by a repository administrator to
make the offline job a required merge check. Path-filtered workflows do not
report checks on unrelated PRs, so scope the requirement accordingly.

GitHub will normally expose a new manual workflow only after it exists on the
default branch; before merge, run the same script commands directly on a
prepared runner. Report upload does not itself make a test a required gate.
