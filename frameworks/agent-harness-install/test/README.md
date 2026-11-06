<!--
Copyright (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# OpenShell quality gates

For user-facing setup and security boundaries, see the
[Agent Sandboxing guide](../docs/agentic-ai-security/agent-sandboxing.md).

Both suites emit TAP 13 reports and return a nonzero exit status on failure.
No test requires a GitHub token. Live inference uses the prepared runner's
shared IR, which must already have any required upstream authentication
configured. Model-generated text is not used as proof that a file operation
succeeded.

## Offline PR gate

### Monorepo merge protection

The workflow starts on every PR, but only runs component jobs when changes
match `frameworks/agent-harness-install/**`, the workflow itself, or
`.github/scripts/agent-harness-required-gate.mjs`. The pinned path-filter action
uses the PR files API, including added, modified, deleted and renamed paths.
Only change detection receives `pull-requests: read`; no write permission or
repository secret is needed for fork PRs. PRs with 3000 or more changed files
run all component checks conservatively because the API cannot list more than
3000 files. A failed filter never becomes a "no changes" result.

Pushes to `main` retain these path filters, while manual dispatch always runs
component checks. The final **Agent Harness required static gate** runs with
`always()` after change detection and static analysis only. Offline regression
and Hermes image runtime remain separate conditional checks; their results do
not affect this static-analysis merge gate.

This is an intentional change from the earlier recommendation to require
static, offline and Hermes checks together: this PR provides a static-only
merge-protection policy. Offline/Hermes failures remain visible but are not
merge blockers under this policy unless separately required by administrators.
Existing required checks must not be removed automatically.

| Decision | Required outcomes |
|---|---|
| Relevant changes | Static analysis must succeed (ShellCheck and production `node --check`) |
| Unrelated changes | Static analysis must be skipped |
| Failed/cancelled detection, missing/invalid decision, or unexpected job outcome | Fail the final gate |

The final job also runs the required-gate decision tests, independently of
component selection. Workflow cancellation may prevent a final job from
finishing; a cancelled or missing required check is not successful evidence.
Live prepared-runner validation remains a separate manual opt-in, not part of
this automatic merge gate.

Administrators should require **only `Agent Harness required static gate`** for
this component in the `main` ruleset/branch protection, retaining unrelated
existing required checks. Do not separately require the conditional component
jobs or change detection for this static-only policy.
The workflow does not modify repository rulesets or bypass permissions.

The workflow also runs an independent **Agent Harness static analysis** job on
relevant pull requests, pushes to `main`, and manual dispatch. It scans production shell
and JavaScript files throughout this component, excluding `test/`, `tests/`,
`node_modules/` and `.venv/`. Existing regression tests still run separately.

- ShellCheck runs at `--severity=style` (all diagnostic levels). Any remaining
  diagnostic fails the job; there is no baseline or allowed finding count.
  CI downloads v0.11.0 and verifies its archive SHA-256 instead of depending on
  the runner's changing APT package version.
  Intentional patterns have local `shellcheck disable` directives with reasons.
  Do not add blanket exclusions to make a new finding pass.
- `node --check` parses each production `.js`, `.mjs` and `.cjs` file without
  executing it. It catches malformed JavaScript before merge, but does not
  validate runtime behavior, dependency availability or logic, nor JavaScript
  embedded in shell strings or heredocs. Regression tests remain necessary.

To reproduce the static gate on Ubuntu 24.04 with Node.js 24.21.0:

```bash
# Install ShellCheck v0.11.0 using the checksum-verified workflow step.
# From frameworks/agent-harness-install, using Bash:
mapfile -d '' shell_files < <(find . -type d \( -name test -o -name tests -o -name node_modules -o -name .venv \) -prune -o -type f -name '*.sh' -print0)
shellcheck --source-path=SCRIPTDIR --severity=style "${shell_files[@]}"
mapfile -d '' js_files < <(find . -type d \( -name test -o -name tests -o -name node_modules -o -name .venv \) -prune -o -type f \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' \) -print0)
for file in "${js_files[@]}"; do
  node --check "$file" || exit
done
```

The workflow fails if either file list is empty. The final required gate
propagates a static-job failure; adding the workflow alone does not configure
repository merge protection.

### Hermes image runtime gate

The independent **Hermes image runtime gate** runs on every relevant PR, push to
`main`, and manual dispatch. It builds the existing production Dockerfile with
`HARNESS_AGENT=hermes`, reusing the installer's pinned Hermes commit and installer
checksum. Image construction downloads the real dependencies and requires Docker
and external network access; it does not install Hermes on the host.
The pinned Buildx/build-push actions import/export a GHA layer cache scoped to
`agent-harness-hermes`. Cache misses still build and test the production image;
the gate is not path-skipped or downgraded. This reduces repeated downloads but
does not eliminate cold-build network or runner-disk requirements.

The gate runs all nine model-default cases with `HARNESS_TEST_REQUIRE_HERMES=1`.
Missing Hermes fails instead of skipping. The shared TAP parser requires a
complete, nonempty report with passing tests, zero failures and zero skips;
empty/truncated reports and summary-only text cannot satisfy the gate.
The two Hermes-specific cases exercise actual YAML serialization, provider
normalization into request overrides, preservation of user overrides, and
configuration changes on reapplication/model switching.

Tests run as the image's unprivileged user in a disposable container with no
network, a writable temporary filesystem, no Linux capabilities, and only the
test file bind-mounted read-only. Hermes writes its runtime locks in the
container's disposable writable layer; a read-only root filesystem is not
compatible with those locks. No host agent
configuration, Docker socket, credentials or OpenShell gateway is mounted.
The image's production model-config helper is tested, and TAP output is uploaded
as `hermes-runtime-results`. See the [local commands](unit-tests.md#hermes-runtime-dependent-cases).
This is real dependency/configuration coverage, not live inference or sandbox
lifecycle acceptance. Its result is reported separately from the required static gate.

### Installer runtime regression

The offline job runs `bash test/installer-runtime-test.sh`. Its 34 cases
execute production functions with disposable HOME/TMPDIR directories, a local
Git fixture and command doubles. It never invokes real Docker, sudo, OpenShell,
downloads or agent installation.

| Behavior | Runtime evidence |
|---|---|
| Bootstrap cleanup | Real standalone bootstrap with a local repository; temporary clone removed on payload success and failure; failure status retained |
| Deferred shell expansion | Generated Bash profile expands the new shell's PATH, not the writer's; repeated setup is idempotent |
| Runtime sourcing | Real Bash sources a disposable nvm fixture; absent nvm is tolerated |
| Fail-closed guards | Both IR/OVMS launch functions reject failed and empty address resolution before Docker launch and forward a valid loopback binding; both OpenShell guards reject nonnumeric, leading-zero and out-of-range ports without arithmetic diagnostics and accept canonical decimal ports 1–65535 |
| Configuration publication | Real Node config generation plus injected generation and rename failures for add/remove; errors propagate, original config survives, temporary files are removed |
| Optional npm query | Missing/failed version queries use the fallback; a valid version enables the required install flag; installation is a command double |
| Hermes staging | Actual startup script stages config in the child, preserves the parent's environment, removes staged files, and preserves live config on injected staging failure |
| Registry listing and installer retry | Registry listing verifies its JavaScript argument; a fixture installer exercises child Bash arguments, transient failure status and retry |

These complement existing startup/lifecycle tests: Hermes staging cases here
check parent-environment isolation and injected failure, whereas the startup
suite checks publication order, permissions and native configuration preservation.
No duplicate suite invocation is added to the all-in-one OpenShell command.
CI records this suite in `runtime.tap` and includes its outcome and counts in
the offline summary and uploaded reports.

These are fixture-based behavior tests, not live deployment acceptance.
Fish/csh profile output, real distro metadata, the upstream nvm
implementation, Hermes's real bundled Python/YAML runtime, network access and
Docker/OpenShell lifecycle require their matching environment/integration checks.
Do not treat fixture-based success as live deployment acceptance.

See the [unit and offline regression test catalogue](unit-tests.md) for
individual cases, objectives, execution commands and runtime-dependent skips.
The catalogue separates fixture-based assertions from real local checks and
does not claim live sandbox or browser acceptance.

Requirements: Linux, Bash, Node.js 24 and standard command-line tools.
No Docker daemon, OpenShell installation, GPU, model download or external network
is required. HTTP response tests use a temporary server bound to host loopback.

From the component directory:

```bash
set -o pipefail
bash test/openshell-test.sh | tee openshell-offline.tap
```

The command above retains the all-in-one local behavior. In CI, named steps
run each suite once: the core suite uses `HARNESS_TEST_SKIP_NESTED=1` (74 direct
cases), followed by managed inference (33), lifecycle/CLI (40), and model
defaults (7 executed offline cases; two explicit Hermes image-required skips). A separate
TAP-reporting regression step validates the reporting helper itself.

Each step writes its own TAP file. Later suites still run after an earlier
suite fails, provided syntax validation succeeded and the job was not cancelled.
The job summary shows executed (excluding skipped), passed, failed and skipped
counts, individual skip reasons, step outcomes and incomplete/missing reports.
Missing or incomplete evidence is never reported as a pass. Syntax checks are
reported separately and are not counted as test cases.

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
| Dynamic policy change | Apply a live network deny update; verify the denial and filesystem access, remove it, then confirm network access is restored |
| Interactive agent policy | Interactive policy differs from the base only by sandbox-local `/dev/ptmx` and `/dev/pts` write access; installer selects it for Hermes and Deep Agents Code, while OpenClaw uses the base policy |
| CLI safety | Help, invalid runtime, missing option values rejected without hanging, host connect rejection, interactive connections without deployment locking, Docker-group reexecution before locking, explicit sandbox deletion consent and host-only deletion flags |
| Cleanup safeguards | Deletion order, archived records, unowned-resource refusal, pending deletion retaining provider/identity, global runtime removal blocked by sandbox/provider resources across all workspaces and incomplete resource lists |
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

See the [live integration test catalogue](integration-tests.md) for individual
cases and objectives, when to execute, manual/CI execution steps, cleanup and
the limits of the evidence these tests provide.

Developers can run `bash test/validate-local-openshell.sh` to validate their
working-tree changes on a prepared machine, or explicitly add `--prepare` to
allow missing default-service preparation. See the
[developer entrypoint](integration-tests.md#developer-entrypoint-validate-local-changes)
for safeguards, stage behavior and report locations. The CI reporting step also
runs the wrapper's nine offline safety regressions, not the live wrapper itself.

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
| Installation | All three agent images build, sandboxes become Ready, native inference checks pass |
| Local-model defaults | Disposable network-isolated built Hermes image must run all defaults cases, including native YAML and provider request mapping (no runtime-dependent skips) |
| Hermes browser terminal | Real sandbox Python can allocate and close a PTY; this is a prerequisite check, not an automated dashboard/browser chat turn |
| Deep Agents Code terminal | Real sandbox Python can allocate and close a PTY for the interactive terminal |
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
It checks every shell file under `scripts`, `openshell` and `test`, plus each
top-level install/uninstall entrypoint, with `bash -n` before running the suites.
It publishes the summary and attempts to upload all per-suite TAP reports even
when tests fail; a failure before TAP generation (for example, a shell syntax
failure) may leave no report to upload.
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
