# Platform Validation

This document describes the self-hosted platform-validation system: why it
exists, how it is secured, and how an admin configures it.

---

## Contents

1. [Threat model and label gate](#threat-model-and-label-gate)
2. [Issue labels and their trust boundaries](#issue-labels-and-their-trust-boundaries)
3. [Orchestrator vs. target](#orchestrator-vs-target)
4. [Lint/dispatch runner for allow-listed orgs](#lintdispatch-runner-for-allow-listed-orgs)
5. [Registering the self-hosted runner](#registering-the-self-hosted-runner)
6. [Preparing a libvirt target VM](#preparing-a-libvirt-target-vm)
7. [Repository variables and secrets](#repository-variables-and-secrets)
8. [Driver vs. application targets](#driver-vs-application-targets)
9. [Apt / registry cache](#apt--registry-cache)
10. [Trigger warning](#trigger-warning)
11. [Dispatch guards and idempotence](#dispatch-guards-and-idempotence)

---

## Issue labels and their trust boundaries

Three labels govern AI-assisted code generation and platform validation.  All
three should be restricted to repository maintainers.

> **Static checks vs. hardware validation**: `.github/scripts/validate-modules.sh`
> covers all static checks (bash syntax, shellcheck, function-name uniqueness,
> `@@HIGHLIGHT` guidance) and runs automatically on every PR via
> `validate-modules.yml`.  The labels and workflows below govern the separate
> concern of hardware lifecycle validation, which requires a real lab target.

| Label | Applied to | Who may apply | Effect |
|-------|-----------|---------------|--------|
| `GENERATE-COMPONENT` | Issues | **Maintainers only** | Triggers `.github/workflows/generate-on-label.yml`, which assigns `copilot-swe-agent` to the issue and removes `NEEDS-GENERATION`.  Applying this label is the explicit trust decision that authorises AI code generation for a modified spec. |
| `NEEDS-GENERATION` | Issues | Automation (created by `create-component-issue.sh`) | Signals that the issue was created from a modified spec and is waiting for a maintainer to authorise agent dispatch via `GENERATE-COMPONENT`.  Maintainers should not add this label manually. |
| `validate-platform` | Pull requests | **Maintainers only** | Triggers `.github/workflows/platform-validate.yml` to run the install/start/stop/remove lifecycle on real lab hardware.  Applying this label is the explicit trust decision that authorises executing PR code on the self-hosted runner. |

### Trust boundary: `GENERATE-COMPONENT`

Applying `GENERATE-COMPONENT` to an issue is what authorises the Copilot
coding agent to generate code for a **modified** spec.  Only repository
maintainers should have this power.  Before applying the label:

1. Review the spec diff to confirm the changes are intentional and safe.
2. Check that the issue title and body correctly describe the expected change.
3. Apply `GENERATE-COMPONENT`.  The agent will be assigned automatically.

The `generate-on-label.yml` workflow guards against bot actors (actor checks
for `github-actions[bot]`, `copilot-swe-agent[bot]`, `Copilot`, and
`vars.AUTOMATION_ACTOR`) to prevent label-triggered loops.

---

## Threat model and label gate

The Copilot coding agent produces AI-generated shell scripts committed to a PR
branch.  Those scripts may be written by an external contributor with no prior
access to the repository.

The self-hosted runner sits **inside the corporate network** and has SSH
access to lab hardware.  If the workflow ran on every PR push without approval,
any contributor could push a `module/evil/debian` that the runner would execute
inside the firewall.

The **`validate-platform` label** is the human-approval gate.  Only repository
maintainers can apply it.  The workflow in
`.github/workflows/platform-validate.yml` checks for the label before doing
anything:

```yaml
if: |
  github.event_name == 'workflow_dispatch' ||
  (github.event.label.name == 'validate-platform') ||
  (github.event.action == 'synchronize' &&
   contains(github.event.pull_request.labels.*.name, 'validate-platform'))
```

Once a maintainer applies the label (signalling "this code is safe to run in
the lab"), subsequent pushes to the same PR re-validate automatically because
the `synchronize` branch checks for the label too.  Removing the label stops
further automatic runs.

---

## Orchestrator vs. target

The self-hosted runner acts as an **orchestrator only**:

- It checks out the PR head into a local subdirectory.
- It calls `platform-target.sh` to acquire a **disposable target host** from
  the pool, reset it to a clean snapshot, sync the repo, and run commands.
- It never `source`s or directly executes anything from the checked-out repo.
- All tested code runs on the **target**, not on the runner host.

The target is reset (`virsh snapshot-revert` or equivalent) between runs so
a badly-behaved component cannot leave residue that affects the next test.

---

## Lint/dispatch runner for allow-listed orgs

The repository workflows **`Generate component from spec`** and
**`Validate modules`** run on `runs-on: [self-hosted, linux, oep-lab]`.
Reason: the `intel-sandbox` organization uses a GitHub IP allow list, which
blocks GitHub-hosted runners during `actions/checkout`.

Required tools on the runner host:
- `gh`
- `git`
- `curl`
- `jq`
- `shellcheck`

On Ubuntu/Debian hosts:
```bash
sudo apt update
sudo apt install -y gh git curl jq shellcheck
```

This runner is still an **orchestrator only** and must **never** be used as a
direct install target. Real component installs/validation belong on disposable
targets driven by `.github/workflows/platform-validate.yml`.

If your organization later enables GitHub's setting to allow GitHub Actions to
access allow-listed repositories, these two workflows can be reverted to
`ubuntu-latest`.

---

## Registering the self-hosted runner

> **Important**: use a **dedicated runner group scoped to this repository
> only** — never add the runner to a group shared with other repositories.

1. In the repository, go to **Settings → Actions → Runners → New self-hosted
   runner**.
2. Follow the installation instructions for your OS (Linux recommended).
3. When prompted for labels, enter:
   ```
   self-hosted,linux,oep-lab
   ```
4. Start the runner as a service (e.g. `./svc.sh install && ./svc.sh start`).
5. In **Settings → Actions → Runner groups**, create a group called
   `oep-lab`, add the runner to it, and **restrict it to this repository**.

The runner needs:
- `virsh` (libvirt-client) if using the libvirt backend.
- `rsync`, `ssh` for syncing and executing on the target.
- Outbound HTTPS to `github.com` (for the long-poll connection); no inbound
  ports required.

---

## Preparing a libvirt target VM

1. Create a VM with your base OS (Debian recommended for application
   components).
2. Install the OS, add the `oep` user with passwordless sudo, and configure
   SSH key-based login.
3. Install any prerequisite packages that are outside the scope of the
   installer itself (e.g. the kernel headers needed by driver modules).
4. Pre-seed an apt/registry cache if one is available on your network
   (see [Apt / registry cache](#apt--registry-cache)).
5. Take a libvirt snapshot and name it `clean-baseline` (or whatever you set
   `TARGET_SNAPSHOT` to):
   ```bash
   virsh snapshot-create-as my-target-vm clean-baseline \
     --description "Clean OS baseline for OEP platform validation" \
     --atomic
   ```
6. Verify revert works:
   ```bash
   virsh snapshot-revert my-target-vm clean-baseline
   ```

For **driver / kernel components** (order 00–29, e.g. `gpu`, `npu`,
`realsense`) you need **bare-metal targets** with the actual accelerator
hardware.  Use the `ssh` backend (`TARGET_BACKEND=ssh`) and arrange external
re-imaging (PXE, BMC, etc.) between runs.

---

## Repository variables and secrets

All of these belong to the **`platform-validation` environment** in repository
settings (**Settings → Environments → platform-validation**).  Set required
reviewers on the environment for an additional approval layer.

### Secrets

| Secret | Description | Required |
|--------|-------------|----------|
| `TARGET_SSH_KEY` | Private SSH key (PEM) for logging in to the target host | Yes |

### Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TARGET_BACKEND` | Backend to use: `libvirt` or `ssh` | `libvirt` |
| `TARGET_POOL` | Comma-separated list of VM/host names available as targets | `oep-targets` |
| `TARGET_SNAPSHOT` | libvirt snapshot name to revert to before each run | `clean-baseline` |
| `TARGET_SSH_USER` | SSH login user on the target | `oep` |
| `TARGET_SSH_PORT` | SSH port on the target | `22` |
| `LIBVIRT_URI` | libvirt connection URI | `qemu:///system` |

All variables are documented in `.github/scripts/platform-target.sh`.

---

## Driver vs. application targets

| Component range | Category | Recommended target |
|----------------|----------|--------------------|
| 00–29 | Kernel modules / drivers (e.g. `gpu`, `npu`, `realsense`) | Bare-metal with the physical accelerator; use `TARGET_BACKEND=ssh` |
| 30–59 | Low-level libraries | Snapshot-revert VM (no special hardware needed) |
| 60–98 | Middle-level / applications | Snapshot-revert VM |

For driver components, arrange external re-imaging (PXE, BMC reset, etc.)
before each validation run.  The `ssh` backend simply waits for SSH to come
up after the external reimaging is assumed to have started.

---

## Apt / registry cache

Several modules download tens of gigabytes of Docker images or apt packages.
Pre-seeding a mirror or a pull-through cache inside the firewall is strongly
recommended:

- **apt**: configure an [apt-cacher-ng](https://www.unix-ag.uni-kl.de/~bloch/acng/)
  or Nexus proxy, then set `Acquire::http::Proxy` in
  `/etc/apt/apt.conf.d/proxy.conf` on the target VM before taking the clean
  snapshot.
- **Docker / OCI registries**: configure a
  [Docker registry mirror](https://docs.docker.com/registry/recipes/mirror/)
  or Nexus repository and point `daemon.json` at it on the target VM before
  taking the clean snapshot.

---

## Trigger warning

The workflow uses `pull_request_target` so that it can access repository
secrets even for fork PRs.  This trigger is **dangerous without the label
gate** because it runs with repository context.

**Never change the trigger to plain `pull_request` while self-hosted runners
are in use.**  A plain `pull_request` trigger also loses access to the
environment secrets, which would break validation anyway.

See the security comment at the top of
`.github/workflows/platform-validate.yml` for the full explanation.

---

## Dispatch guards and idempotence

The **`Generate component from spec`** workflow (`.github/workflows/instructions-to-component.yml`)
and its helper script (`.github/scripts/create-component-issue.sh`) include
four active guards that prevent accidental or duplicate generation of Copilot
task issues.

### Guard 1 — added and modified files (workflow)

Implemented in: `.github/workflows/instructions-to-component.yml`

Push-triggered runs use `--diff-filter=AM` (Added and Modified) so that both
new and edited spec files are picked up.  The status letter (`A` or `M`) is
passed to the script as `<status>\t<path>` lines so the script can derive the
correct `mode` (`new` vs `modified`) for each spec.

`workflow_dispatch` with an explicit `spec_file` input is **not** subject to
this filter — manual dispatch is always intentional.  The `mode` input
(`auto` / `new` / `modified`) lets you override the inferred mode.

### Guard 2 — module directory already exists (script, mode-aware)

Implemented in: `.github/scripts/create-component-issue.sh`

Behaviour depends on the detected mode:

- **mode=new**: if `module/<name>/` already exists, the spec is skipped with a
  `::notice::`.  This is unchanged from before.
- **mode=modified**: the module directory is expected to exist — no skip.  If
  `module/<name>/` does *not* exist (module was never generated or was deleted),
  the script demotes the mode to `new` with a `::notice::` and proceeds as a
  new component.

**To override**: set the `force` workflow input to `true` when using
`workflow_dispatch` (Actions → Generate component from spec → Run workflow →
`force: true`).  This sets `FORCE_REGENERATE=true` in the script environment.

### Guard 3 — open issue already exists (script)

Implemented in: `.github/scripts/create-component-issue.sh`

Before creating a new issue, the script searches for an existing **open** issue
with the exact mode-appropriate title: `Implement installer component: <name>`
for new specs, `Update installer component: <name>` for modified specs.  An
exact-match filter via `jq` is applied (GitHub's issue search is fuzzy).  If a
match is found, the spec is skipped and the existing issue number is logged.

**To override**: same as Guard 2 — set `force: true` on `workflow_dispatch`.

### Guard 4 — cap tasks per run (script)

Implemented in: `.github/scripts/create-component-issue.sh`

After Guards 2 and 3 have filtered the eligible specs, the script counts them.
If the count exceeds `MAX_TASKS_PER_RUN` (default: **3**), the job fails with
a `::error::` message listing every spec that would have been dispatched, and
**no issues are created** (all-or-nothing pre-flight).

**To override**: pass a higher value via the `max_tasks` workflow input on
`workflow_dispatch` (e.g. `max_tasks: 10`).  Alternatively, dispatch each spec
individually using the `spec_file` input.

### Deliberately regenerating a component

To force regeneration of an already-implemented component (e.g. after improving
the agent prompt or the spec):

1. Go to **Actions → Generate component from spec → Run workflow**.
2. Set `spec_file` to the path of the spec (e.g. `specification/mwdd.md`).
3. Set `force` to `true`.
4. Click **Run workflow**.

This bypasses Guards 2 and 3 and creates a new issue regardless of whether the
module directory or an open issue already exists.

### Guard 5 — CODEOWNERS (commented out, inert)

`.github/CODEOWNERS` contains an **entirely commented-out** rule that, once
uncommented and activated, would require a review from `@intel-sandbox/oep-maintainers`
before any `specification/` change is merged.  The file is inert as committed.
See the comments inside the file for activation prerequisites.
