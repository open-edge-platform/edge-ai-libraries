# Adding new installer components via AI

Drop a Markdown spec file named `<component_name>.md` into this folder, commit
it to `main`, and a GitHub Actions workflow automatically creates a GitHub
issue assigned to the Copilot coding agent.  The agent reads the spec, writes
`module/<component_name>/debian`, and opens a pull request.

All generated PRs require a human review before merging.

---

## Naming rules

| Rule | Example |
|------|---------|
| Filename must use only `a-z`, `0-9`, and `_`; no spaces or special characters | `smart_parking.md` |
| `_` may be used as a word separator | `loss_prevention.md` |
| The filename (without `.md`) becomes the component name verbatim | `my_app.md` → `module/my_app/debian` |
| Do **not** use a name that already exists under `module/` | – |

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

### 4. Installation steps

Describe what the install procedure does: which packages to install, which
repos to clone, which scripts to run, what environment variables or files are
configured.  Include the upstream repository URL and the release tag or branch
if cloning from source.

### 5. Verification

Describe a reliable test the agent can use in `verify_<name>()` to confirm
the component is correctly installed (e.g. presence of a specific file or
binary, a version check, a health-check URL).

### 6. Start / stop behaviour

Describe how to start and stop the component at runtime (Docker Compose
services, systemd units, scripts, etc.).  If the component is a stateless
system package with no runtime service (e.g. `curl`, `jq`) you can note that
`start` and `stop` are not needed.

### 7. Ports and network endpoints

List any TCP/UDP ports opened by the component, and note the UI entrypoint URL
if applicable.

### 8. Removal

Describe what `remove` should clean up (Docker images, git workspace, config
files, apt packages).

### 9. Reset flag

Describe the expected behaviour of `--reset-<name>` (forced reinstall, data
reset, etc.).

### 10. License requirements

State whether the component requires the user to accept a click-through license
before installation.  If yes, provide the license ID, title, and the URL or
full text of the license.

---

## How the workflow works

1. You push `instructions/<component_name>.md` to `main`.
2. The workflow `.github/workflows/instructions-to-component.yml` detects the
   new or modified file.
3. It creates a GitHub issue titled *"Implement installer component: `<name>`"*
   and assigns it to the Copilot coding agent.
4. The agent reads the issue (which embeds the full spec and detailed
   implementation requirements), writes `module/<name>/debian`, runs `bash -n`
   and `shellcheck`, and opens a pull request.
5. The PR triggers `.github/workflows/validate-modules.yml` which re-validates
   syntax and function naming.
6. A human reviews and merges the PR.

> **Prerequisite**: the Copilot coding agent must be enabled for the repository
> or organisation and must be assignable as `copilot-swe-agent`.  If it is not
> available, the issue-creation step will succeed but no automated PR will be
> opened; a developer can implement the component manually using the issue body
> as a detailed specification.
