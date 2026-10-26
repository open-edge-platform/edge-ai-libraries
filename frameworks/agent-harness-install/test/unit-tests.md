<!--
Copyright (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# OpenShell unit and offline regression test cases

This catalogue documents the OpenShell unit and offline regression tests:
what each case checks, why it matters and how to execute it. It does not
catalogue the existing host smoke/full-flow tests or live sandbox acceptance.

These are not all pure unit tests. They combine isolated functions, mocked CLI
and lifecycle operations, real local configuration processing, Node SQLite/FTS5
and a temporary loopback HTTP server. Docker, OpenShell, system services and
model downloads are mocked; a passing case does not prove the corresponding
live operation succeeds.

## Prerequisites and execution

Run from the Agent Harness Install component directory on Linux, using Bash,
Node.js 24 (CI uses 24.21.0) and standard utilities including curl, GNU timeout,
flock and stat. No running Docker daemon, OpenShell gateway, GPU, model download
or external network is required. The tests create temporary HOME/state fixtures
and clean them up; no sudo or real deployment is needed.

### Run the complete offline gate

```bash
set -o pipefail
bash test/openshell-test.sh | tee openshell-offline.tap
```

The outer suite currently reports 73 cases. Three are wrapper cases that run
the managed-inference, lifecycle and model-default suites below. Their case
counts must not be added to the outer count as independent top-level results.

### Run a focused suite

| Scope | Command | Current cases |
|---|---|---|
| Startup, runtime, profiles, boundaries, removal and nested suites | `bash test/openshell-test.sh` | 73, including three nested-suite wrappers |
| Model selection and managed inference | `bash test/managed-inference-test.sh` | 33 |
| Model lifecycle, cleanup and CLI locking | `bash test/model-lifecycle-test.sh` | 40 |
| Agent model defaults | `node --test test/model-defaults-test.mjs` | 9; two require the Hermes image runtime |

The Bash runners execute their registered cases in order; they do not currently
accept a case-name filter. Use the focused suite to reproduce a Bash failure.
Do not source the test scripts to invoke individual fixture functions.

Node supports a name filter, for example:

```bash
node --test --test-name-pattern='selection-only' test/model-defaults-test.mjs
```

Successful shell cases emit TAP `ok`; failures emit `not ok` and cause a nonzero
exit status. The Node runner reports pass/fail/skip separately. A skipped Hermes
case is not a pass. Use the TAP output for execution results rather than treating
this catalogue as a permanent pass report.

Both relevant PRs and relevant pushes to `main` run the same offline coverage in
the [quality-gates workflow](../../../.github/workflows/agent-harness-openshell.yml).
CI separates the suites into named steps and TAP artifacts rather than invoking
the nested wrappers: `HARNESS_TEST_SKIP_NESTED=1 bash test/openshell-test.sh`
runs the 70 direct cases; the other three suites run once in their own steps.
The all-in-one local command still runs 73 outer registrations as documented
above. CI additionally runs the reporting-helper tests described below.
CI triggers, syntax checks and prepared-runner instructions are described in
the [test README](README.md).

### Reporting-helper regression tests

Run `node --test --test-reporter=tap test/tap-summary-test.mjs` to verify the
[TAP summary helper](tap-summary.mjs). Its five registered cases cover:

| Registered test name | Objective |
|---|---|
| counts passing, failing and skipped cases without counting diagnostics | Separate executed/pass/fail/skip counts and retain skip reasons. |
| rejects empty, truncated, bailed out and inconsistent reports | Never accept absent plans, incomplete counts, duplicate plans or invalid numbering as complete evidence. |
| ignores indented subtests and treats TODO as unfinished validation | Avoid double counting nested TAP and do not turn unfinished tests into passes. |
| provides a reason for an unspecified skip | Explicitly identify a skip lacking a supplied explanation. |
| summary reports skips, missing files and failed process outcomes | Check totals, skip details, missing reports and non-successful runner outcomes. |

The summary runs even after suite failure and lists unavailable reports as
missing, not passed. Each suite's TAP report is uploaded with the job artifacts.
The Hermes cases now supply an explicit image-runtime skip reason.

## Startup, runtime, profiles and boundaries

Source and execution: [openshell-test.sh](openshell-test.sh),
`bash test/openshell-test.sh`.

The **case reference** names the registered fixture function (or the inline
registration label). Parameterized variants have separate rows so their
expected outcomes are visible. These references are not CLI filter arguments.

| Case reference | Test case | Objective / expected result |
|---|---|---|
| `startup_fresh` | Fresh OpenClaw startup | Export the private SQLite temp path before Node and initialize real on-disk FTS5 successfully. |
| `startup_inherited_temp` | Inherited SQLite temp path | Replace an inherited path with the sandbox-safe private directory. |
| `startup_private_temp` | Existing SQLite temp directory | Restrict permissions to mode 700. |
| `startup_restart` | OpenClaw restart | Preserve configuration, gateway token and database content. |
| `startup_model_switch` | Restart after model selection | Honor the durable new model despite the original sandbox environment. |
| `startup_blocked_temp` | Temp-directory creation failure | Fail before Node starts rather than continue without usable temporary storage. |
| `startup_permissions_failure` | Temp-directory permission failure | Fail before Node starts when private permissions cannot be established. |
| `dcode_startup` | Deep Agents Code startup | Configure and persist its provider model. |
| `runtime_default` | Non-interactive runtime omitted | Keep host as the default. |
| `runtime_supported host openclaw` | Explicit host runtime | Continue accepting the existing host deployment mode. |
| `runtime_supported openshell openclaw` | OpenClaw sandbox support | Accept this runtime/agent combination. |
| `runtime_supported openshell deepagents-code` | Deep Agents Code sandbox support | Accept this runtime/agent combination. |
| `dcode_connect_args` | Deep Agents Code connection | Supply the placeholder API key for the connection without persisting it. |
| `runtime_supported openshell hermes` | Hermes sandbox support | Accept this runtime/agent combination. |
| `runtime_supported openshell invalid-agent` | Unsupported agent | Reject the combination with the intended diagnostic. |
| `runtime_supported invalid openclaw` | Invalid runtime | Reject an unknown runtime. |
| `profile_paths` | Per-agent state locations | Keep agent profile paths separate. |
| `profile_valid` | Valid saved profile | Load the recorded deployment identity. |
| `profile_workspace` | Saved workspace selection | Use the recorded workspace instead of caller defaults for OpenShell commands. |
| `profile_creation_persists_workspace` | New profile creation | Persist the selected workspace for later operations. |
| `profile_missing` | Missing profile | Fail explicitly rather than fabricate deployment identity. |
| `profile_symlink` | Symlinked profile | Reject an unexpected state-file target. |
| `profile_invalid` (malformed JSON) | Invalid profile syntax | Reject malformed persisted JSON. |
| `profile_invalid` (wrong agent) | Profile for another agent | Reject identity belonging to a different agent. |
| `profile_invalid` (invalid owner) | Invalid ownership field | Reject an invalid owner identifier. |
| `profile_invalid` (newline in model) | Invalid model field | Reject control characters in the saved model. |
| `owned` | Matching ownership label | Accept the resource belonging to the recorded owner. |
| `unowned` | Mismatched ownership label | Reject operations on an unrelated resource. |
| `unavailable` | Gateway unavailable | Do not treat failed ownership inspection as authorization. |
| `resource_case sandbox` (present) | Sandbox discovery | Find the named sandbox in a valid response. |
| `resource_case sandbox` (absent) | Sandbox absence | Return absence for a valid empty list. |
| `resource_case provider` (present) | Provider discovery | Find the named provider in a valid response. |
| `resource_case` (paginated) | Incomplete discovery | Reject a response with another page rather than assume absence. |
| `resource_case` (malformed JSON) | Invalid discovery syntax | Reject malformed resource JSON. |
| `resource_case` (unexpected schema) | Invalid discovery structure | Reject a response without the expected resource list. |
| `resource_unavailable` | List command fails | Distinguish discovery failure from absence. |
| `version_case 0.1.5` | Supported CLI version | Accept the pinned OpenShell version. |
| `version_case 0.1.4` | Unsupported CLI version | Reject a different installed version. |
| `invalid_bind` | LAN bind requested | Reject non-loopback publication in OpenShell mode. |
| `invalid_port invalid` | Non-numeric IR port | Reject invalid port text. |
| `invalid_port 0` | IR port below range | Reject port zero. |
| `invalid_port 65536` | IR port above range | Reject a port outside the valid range. |
| `invalid_publication` (LAN) | Docker all-interface binding | Reject actual publication on `0.0.0.0`. |
| `invalid_publication` (IPv6) | Additional IPv6 binding | Reject extra all-interface IPv6 exposure even with a loopback IPv4 binding. |
| `invalid_publication` (wrong port) | Published-port mismatch | Reject a Docker mapping that differs from the recorded endpoint. |
| `invalid_publication` (missing) | No published endpoint | Reject missing Docker publication. |
| `missing_ir` | Missing router container | Fail instead of reporting usable inference. |
| `model_response` (served model) | Exact model advertised | Accept the requested model through the local HTTP fixture. |
| `model_response` (unserved model) | Different model advertised | Reject a response that does not contain the requested model. |
| `model_response` (HTTP 503) | Inference discovery unavailable | Reject an HTTP failure. |
| `model_response` (malformed JSON) | Invalid model-discovery response | Reject malformed JSON. |
| `removal_success` | Owned removal | Delete resources in order and archive identity state. |
| `removed_sandbox_allows_ir_port_change` | Port change after scoped removal | Do not let the removed sandbox's stale provider record block the new port. |
| `removal_unowned` | Unowned removal request | Perform no deletion. |
| `removal_pending` | Remote deletion incomplete | Retain ownership and provider state for retry. |
| `removal_deletes_orphaned_profile` | Provider already absent | Remove the orphaned local provider profile. |
| `removal_profile_failure_retains_identity_for_retry` | Profile cleanup failure | Retain the ownership record needed for another attempt. |
| `removal_uses_installation_lock` | Concurrent install/removal | Use the per-agent installation lock during removal. |
| `runner_failure_propagation` | Intermediate assertion failure | Ensure an earlier failed assertion cannot be masked by a later successful command. |
| Docker build context includes model configuration helper | Build-input wiring | Check the helper's inclusion, Dockerfile copy and Dcode installer dispatch text; this is not an image build. |
| Dcode provider policy allows its pinned Python and avoids nested interpreter | Dcode runtime wiring | Check provider-policy and connection-command text for pinned Python, transient key/update flags and `--no-interpreter`; this is not a live network check. |
| installer documents runtime | Installer help | Keep the runtime option in CLI help. |
| uninstaller documents runtime | Uninstaller help | Keep the runtime option in CLI help. |
| invalid runtime CLI fails before setup | Real CLI entrypoint | Reject an invalid runtime without starting setup. |
| host connect is rejected | Unsupported host connection | Fail with the OpenShell-specific connection diagnostic. |
| sandbox removal requires consent | Destructive-command consent | Reject sandbox removal without confirmation. |
| scoped sandbox removal requires OpenShell runtime | Invalid cleanup combination | Reject `--sandbox-only` with host runtime. |
| live suite requires explicit opt-in | Live-test safety | Refuse live execution without the opt-in variable. |
| interactive policy adds only sandbox-local PTY paths to the base policy | Policy structure | Verify the interactive policy differs only by `/dev/ptmx` and `/dev/pts`, ignoring comments/blank lines. |
| `policy_paths` | Agent policy selection | Select the base policy for OpenClaw and the interactive policy for Hermes and Deep Agents Code. |

The remaining three outer registrations invoke entire suites:

| Registration | Objective |
|---|---|
| managed Qwen inference regression suite | Propagate the result of the managed-inference suite into the offline gate. |
| model switch and complete uninstall regression suite | Propagate the result of the lifecycle/CLI suite into the offline gate. |
| Qwen local-model defaults regression suite | Propagate the result of the Node model-default suite into the offline gate, including reported skips. |

## Model selection and managed inference

Source and execution: [managed-inference-test.sh](managed-inference-test.sh),
`bash test/managed-inference-test.sh`. Service, download and container operations
are fixture-driven, not live OVMS or GPU tests.

| Case reference | Test case | Objective / expected result |
|---|---|---|
| `default_model` | Fresh OpenShell defaults | Select Qwen and the snapshot exporter without creating state during selection. |
| `host_model` | Host model selection | Preserve the requirement for an explicit/reusable model rather than add a host fallback. |
| `explicit_model` | Explicit model | Leave the requested model unchanged. |
| `explicit_exporter` | Explicit exporter | Leave the requested exporter unchanged. |
| `explicit_hub` | Non-default hub | Do not assign an incompatible Qwen fallback. |
| `external_model` | External endpoint | Do not assign the fresh managed Qwen fallback. |
| `registered_model` | Existing OVMS registry | Do not silently replace an existing model. |
| `saved_model` | Repeated install | Reuse the saved shared model. |
| `saved_override` | Explicit change after saved selection | Let the explicit model take precedence. |
| `invalid_saved` | Invalid saved model | Fail explicitly on invalid saved state. |
| `symlink_saved` | Symlinked saved model | Reject an unexpected state-file target. |
| `profile_model` | Older agent profile | Prefer the shared selection over an outdated agent profile. |
| `fresh_provisioning` | Fresh install and rerun | Persist the selection and avoid provisioning again on rerun. |
| `existing_provisioning` | Existing inference | Validate services without replacing them. |
| `partial_provisioning` | Partial deployment | Require explicit repair rather than silently reconstruct services. |
| `docker_unavailable` | Docker discovery failure | Do not mistake a command failure for a fresh host. |
| `invalid_route` | Route mismatch | Fail without provisioning or persisting an incorrect model. |
| `lan_provisioning` | LAN publication | Fail before provisioning against an exposed endpoint. |
| `skip_lan_prompt` | OpenShell setup interaction | Skip the host-only LAN-publication prompt. |
| `backend_response ready` | Valid managed backend | Accept the exact ready model with private networking and loopback publication. |
| `backend_response lan` | Exposed OVMS | Reject managed OVMS LAN publication. |
| `backend_response network` | Backend-network mismatch | Reject incompatible IR/OVMS networking. |
| `backend_response unready` | Model not ready | Reject an unready managed model. |
| `router_proxy` | Proxy bypass lists | Preserve both bypass lists and add the managed backend hostname. |
| `cached_snapshot` | Cached snapshot registration | Register Qwen idempotently and write the managed IR route. |
| `snapshot_download cpu` | CPU graph-generation path | Invoke native OVMS graph generation before registration. |
| `snapshot_download gpu` | GPU graph-generation path | Invoke the GPU graph-generation path before registration. |
| `snapshot_download failure` | Graph generation fails | Retain downloaded weights and report failure. |
| `snapshot_download no-graph` | Success without graph output | Reject incomplete graph generation despite a successful command exit. |
| `cli_install` | Full installation CLI | Provision inference before the sandbox and reuse it on rerun. |
| `cli_inference` | Inference-only CLI | Apply the Qwen default without installing an agent. |
| `cli_mismatch` | Selected-model readiness failure | Retain pending-transition information when validation fails. |
| `cli_host` | Host CLI compatibility | Preserve the original host installation flow and exporter. |

## Model lifecycle, cleanup and CLI locking

Source and execution: [model-lifecycle-test.sh](model-lifecycle-test.sh),
`bash test/model-lifecycle-test.sh`. Model/service/resource operations are mocked.
Locking and CLI-entrypoint fixtures exercise local processes, not simultaneous
real sandbox operations.

| Case reference | Test case | Objective / expected result |
|---|---|---|
| `switch_both` | Coordinated model switch | Update/restart the agent fixtures and preserve token/history data; not a live cross-agent switch. |
| `source_roundtrip` | Source selection persistence | Preserve hub, exporter, revisions and conversion configuration across reruns. |
| `delayed_startup` | Sandbox Ready before agent startup | Wait for model readback instead of treating sandbox readiness as application readiness. |
| `select_served_model` | Managed serving selection | Register only the new serving model while retaining previous cached weights. |
| `qwen_alias` | Bare Qwen name | Resolve the alias to the preconfigured OpenVINO source. |
| `external_model_id_is_preserved` | External model ID | Preserve the identifier verbatim. |
| `ir_port_change_is_rejected_before_backend_update` | Port change with active sandbox | Reject before modifying shared inference. |
| `model_sync_locks_agents_without_sandboxes` | Absent sandbox during sync | Still lock the relevant recorded agent profiles. |
| `retry_transition` | Interrupted switch | Retain the old selection and resume the pending target on retry. |
| `pending_conflict` | Different model during recovery | Prevent overwriting an interrupted transition. |
| `legacy_image` | Incompatible older image | Fail before modifying shared inference. |
| `complete_uninstall` | Full removal | Remove all owned deployment data by default. |
| `explicit_host_agent_selection` | Explicit host harness | Prefer explicit selection to the recorded installed agent. |
| `full_openshell_with_host_agent` | Recorded host agent in full cleanup | Do not use the sandbox selector to choose which recorded host agent is removed. |
| `failed_uninstall` | Cleanup failure | Retain models and recovery information. |
| `scoped_uninstall` | Sandbox-only removal | Preserve shared services and model data. |
| `owned_runtime_remove` | Owned OpenShell runtime | Remove its gateway service, package and state. |
| `owned_runtime_loads_node` | Cleanup dependency ordering | Load Node before inspecting runtime ownership. |
| `shared_runtime_refused` | Unrelated sandbox | Block gateway and CLI purge. |
| `preexisting_runtime` | Pre-existing OpenShell | Do not claim ownership or remove it. |
| `runtime_other_workspace` | Other-workspace runtime containers | Block package removal when another workspace depends on it. |
| `runtime_global_resource_check sandbox` | Other-workspace sandbox | Block global removal based on all-workspace discovery. |
| `runtime_global_resource_check provider` (present) | Provider without a sandbox | Block global removal even if only the unrelated provider remains. |
| `runtime_global_resource_check provider` (paginated) | Incomplete global list | Block removal when another page exists. |
| `runtime_global_resource_check sandbox` (malformed) | Invalid global JSON | Block removal on malformed discovery output. |
| `runtime_global_resource_check provider` (invalid schema) | Invalid global list shape | Block removal instead of treating an invalid list as empty. |
| `runtime_purge_failure` (receipt registration) | Package purge fails | Retain the ownership receipt needed for retry. |
| `runtime_sudo_authorization_failure` | Missing sudo authorization | Fail before stopping the owned gateway. |
| `runtime_purge_failure` (restoration registration) | Package purge fails after gateway stop | Attempt to restore the gateway. This registration runs the same fixture as the receipt case. |
| `runtime_purge_and_restore_failure` | Gateway restoration also fails | Report the manual recovery required. |
| `owned_service_retry` | Owned gateway startup interrupted | Retry service startup during installer reruns. |
| `register_owned_gateway` | Fresh gateway registration | Register local package TLS with the CLI. |
| `validate_all_profiles` | Multiple recorded profiles | Include all recorded agents in complete cleanup. |
| `reject_unowned_profile` | One profile fails ownership | Validate all profiles before deleting the first sandbox. |
| `no_profiles_without_node` | Host-only cleanup | Do not require Node to inspect absent sandbox profiles. |
| `deployment_lock_serializes_mutations` | Concurrent deployment changes | Serialize mutations with a lock outside the removable state root. |
| `status_and_connect_skip_deployment_lock` | Read/connect dispatch | Bypass deployment locking and prerequisite setup. |
| `missing_option_values_fail_promptly` | Missing CLI values | Fail within the timeout with intended diagnostics rather than hang. |
| `connect_works_while_deployment_is_locked` | Connections during mutation | Connect to different agent fixtures while another process holds the deployment lock. |
| `group_refresh_precedes_deployment_lock` | Docker-group reexecution | Preserve arguments and refresh permissions before lock acquisition; verify the replacement mutation holds the lock. |

## Agent model defaults

Source and execution: [model-defaults-test.mjs](model-defaults-test.mjs),
`node --test test/model-defaults-test.mjs`. These cases run the configuration
helper against temporary files, not an LLM.

| Registered test name | Objective / expected result |
|---|---|
| Qwen OpenClaw defaults cover catalog, request parameters and lean prompt | Verify 65536 context, 512 output cap, sampling/thinking/prompt settings, preservation of unrelated values and idempotence. |
| explicit OpenClaw overrides survive initial application and restarts | Preserve explicit catalog, sampling, thinking, prompt and tool settings. |
| user edits to generated defaults survive later restarts and model changes | Retain edits rather than overwrite them as managed defaults. |
| switching away removes managed Qwen tuning and restores generic catalog defaults | Remove unchanged Qwen defaults, restore generic budgets and reapply Qwen defaults when selected again. |
| non-Qwen models retain existing configuration | Preserve existing budgets/tool settings without injecting Qwen-specific thinking defaults. |
| selection-only updates do not modify agent defaults | Leave configuration unchanged and do not create the managed-default tracking file. |
| pre-existing empty configuration sections retain their identity and ordering | Keep existing empty sections and stable serialization across applications and model changes. |
| Hermes Qwen defaults normalize into actual custom-provider request overrides | In the Hermes runtime, verify YAML settings, real provider normalization into request overrides, idempotence and removal of unchanged defaults when switching away. |
| Hermes explicit overrides survive restart and switching away | In the Hermes runtime, preserve explicit context, sampling, output and reasoning overrides across restart and model changes. |

### Hermes runtime-dependent cases

The final two cases skip when the pinned Hermes runtime is unavailable at
`/home/node/.local/bin/hermes`. The normal offline host/CI run therefore
executes seven cases and reports two skips, not nine passes.

To require these cases rather than permit a missing-runtime skip, run inside
the prepared Hermes image environment:

```bash
HARNESS_TEST_REQUIRE_HERMES=1 node --test test/model-defaults-test.mjs
```

The image must have Node, the pinned Hermes Python/YAML runtime, and the current
test/helper files. `HARNESS_TEST_MODEL_CONFIG` can point to the current helper
when it is mounted at a different location. See the
[prepared-runner gate](README.md#opt-in-prepared-runner-gate) for the existing
image-based execution path; do not run these as configuration changes in a
user's active sandbox.

## Interpretation and maintenance

- These tests do not certify live filesystem/network enforcement, host reboot
  persistence, browser chat, latency, model-driven tool use or a live coordinated
  model switch. Validate those separately.
- Static policy/build-input assertions check wiring, not effective permissions
  or a successful container build.
- When adding or changing a registered case, update its catalogue row in the
  same change. Keep parameterized variants and runtime skips explicit.
- Use source registrations and TAP output to identify cases. Table order and
  case counts are descriptive, not stable test IDs.
- Store commit-specific execution evidence in CI artifacts or a separate
  acceptance report; do not replace objectives with permanent "passed" labels.
