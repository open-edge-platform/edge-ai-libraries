# Adding new installer components via AI

Drop a Markdown spec file named `<component_name>.md` into this folder and
commit it to `main`. A GitHub Actions workflow creates a GitHub issue for the
component; assignment to the Copilot coding agent depends on dispatch rules
below (status-based with maintainer gating for modified/rejected-prior-art
cases).

All generated PRs require a human review before merging.

---

## Naming rules

| Rule | Example |
|------|---------|
| Filename must use only `a-z`, `0-9`, and `_`; no spaces or special characters | `smart_parking.md` |
| `_` may be used as a word separator | `loss_prevention.md` |
| The filename (without `.md`) becomes the component name verbatim | `my_app.md` → `module/my_app/debian` |
| Do **not** use a name that already exists under `module/` for a **new** spec; editing an existing spec is supported via the label-gated update flow | – |

Files whose names start with `_` (like `_template.md`) or `README.md` are
ignored by the dispatch workflow.

---

## Recommended spec structure

A spec file should answer the following questions.  The more detail you
provide, the better the generated implementation will be.

### 1. Purpose

One paragraph describing what the component does and why it is useful in an
Open Edge Platform context.

### 2. Installation order / category

Pick the numeric range that fits the component's role:

| Range | Category |
|-------|----------|
| 00–29 | Kernel modules / drivers |
| 30–59 | Low-level libraries |
| 60–89 | Middle-level libraries / microservices |
| 90–98 | Applications |
| 99    | Profiles |

### 3. Dependencies

List every other component that must be installed first.  Only name components
that actually exist under `module/`.  The agent will echo these from
`debian_<NN>_profile_<name>`.

### 4. Profile membership

State whether this component should be added to one or more profiles under
`profile/`.  Profiles are virtual groups that install a set of components
together (e.g. `metro_ai_suite`, `manufacturing_ai_suite`).

- If yes, name the exact profile directories (e.g. `manufacturing_ai_suite`).
  The agent will **propose** the profile edit in its PR description; a
  maintainer applies the actual change to `profile/*/debian`.
- If the component is a standalone utility or library that no suite depends on,
  write "none".
- A note on helper function uniqueness: function names in component scripts
  must be globally unique across all installer scripts.  CI enforces this in
  `.github/workflows/validate-modules.yml`.

### 5. Installation steps

Describe what the install procedure does: which packages to install, which
repos to clone, which scripts to run, what environment variables or files are
configured.  Include the upstream repository URL and the release tag or branch
if cloning from source.

For a SDK, application or service, highlight what is next for the user. For example,
go to certain directory and run additional setup. 

### 6. Verification

Describe a reliable test the agent can use in `verify_<name>()` to confirm
the component is correctly installed (e.g. presence of a specific file or
binary, a version check, a health-check URL).

### 7. Start / stop behaviour

Describe how to start and stop the component at runtime (Docker Compose
services, systemd units, scripts, etc.).  If the component is a stateless
system package with no runtime service (e.g. `curl`, `jq`) you can note that
`start` and `stop` are not needed.

For a SDK, application or service, highlight what is next for the user after the 
comonent is started, for example, launching the browser to a specified URL.

### 8. Ports and network endpoints

List any TCP/UDP ports opened by the component, and note the UI entrypoint URL
if applicable.

### 9. Removal

Describe what `remove` should clean up (Docker images, git workspace, config
files, apt packages).

### 10. License requirements

State whether the component requires the user to accept a click-through license
before installation.  If yes, provide the license ID, title, and the URL or
full text of the license.

---

## How the workflow works

### New spec file (automatic dispatch)

1. You push `specification/<component_name>.md` to `main`.
2. The workflow `.github/workflows/instructions-to-component.yml` detects the
   **new** file (git status `A`).
3. It creates a GitHub issue titled *"Implement installer component: `<name>`"*
   and **immediately assigns it to the Copilot coding agent** unless a recent
   rejected prior attempt is detected, in which case it is label-gated.
4. The agent reads the issue (which embeds the full spec and detailed
   implementation requirements), writes `module/<name>/debian`, runs
   `.github/scripts/validate-modules.sh module/<name>` — the same script that
   CI invokes, so a local pass means CI will pass — and opens a pull request.
5. The PR triggers `.github/workflows/validate-modules.yml` which re-validates
   syntax and function naming.
6. A maintainer reviews the PR.  When satisfied that the static checks pass,
   they apply the **`validate-platform`** label.
7. `.github/workflows/platform-validate.yml` runs on a self-hosted lab runner
   and posts install → start → stop → remove results as a PR comment.
8. On success (or after the agent fixes any failures), a maintainer merges.

### Modified spec file (label-gated dispatch)

1. You push a change to an existing `specification/<component_name>.md` on `main`.
2. The same workflow detects the **modified** file (git status `M`).
3. It creates a GitHub issue titled *"Update installer component: `<name>`"*
   **without** assigning the agent.  The issue is labelled `NEEDS-GENERATION`.
4. A maintainer reviews the spec diff and, when satisfied, applies the
   **`GENERATE-COMPONENT`** label to the issue.
5. `.github/workflows/generate-on-label.yml` fires: it assigns
   `copilot-swe-agent`, removes `NEEDS-GENERATION`, and posts a comment
   recording who authorised dispatch.
6. The agent reads the update issue (which embeds the spec, detailed update
   rules, and the existing implementation as a baseline), edits
   `module/<name>/debian` in place, and opens a pull request.
7. Steps 5–8 from the new-spec path apply (validate-modules, platform
   validation, human review, merge).

> **Prerequisite**: the Copilot coding agent must be enabled for the repository
> or organisation and must be assignable as `copilot-swe-agent`.  If it is not
> available, the issue-creation step will succeed but no automated PR will be
> opened; a developer can implement the component manually using the issue body
> as a detailed specification.

See [`.github/PLATFORM_VALIDATION.md`](../.github/PLATFORM_VALIDATION.md)
for the threat model and admin setup guide.

---

## Updating an existing component

Editing a spec file that already has a corresponding `module/<name>/` triggers
the **label-gated** path described above.  The key difference from new
components:

- **No auto-dispatch**: the issue is created with `NEEDS-GENERATION` and
  awaits a maintainer decision.
- **Incremental update**: the agent is instructed to modify the existing
  `module/<name>/debian` in place, not rewrite it.  It must enumerate every
  new or changed requirement in the spec diff and implement or justify each
  one.
- **Label to dispatch**: a maintainer applies `GENERATE-COMPONENT` to the
  issue to start the agent.  This is an explicit trust decision — the label
  signals "I have reviewed the spec change and authorise code generation."

The naming rule "Do not use a name that already exists under `module/`" applies
only to **new** spec files.  Editing an existing spec is expected and supported
via this label-gated flow.
