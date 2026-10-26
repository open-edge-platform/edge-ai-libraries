<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Open Edge Platform (OEP) CLI Installer

The **OEP CLI Installer** (`openedge-cli`) is a modular, self-contained shell
script that discovers, bootstraps, and installs Open Edge Platform components on
your edge system. The OEP installer can install individual components (libraries, SDKs, samples etc)
as well as virtual groups (**profiles**). 

<p align="center">
  <a href="https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html">
    <img src="https://img.shields.io/badge/Launch%20Web%20UI-0068B5?style=for-the-badge&labelColor=0068B5" alt="Launch the OEP CLI Installer Web UI" />
  </a>
</p>

## Profiles and Modules

Profiles are groupings of installable components targeting specific domain workloads or
marketing segments. The table lists the profiles:

| Profile | Description |
| ------- | ------ |
| `inferencing` | Core AI inferencing runtime |
| `computer_vision` | Computer-vision pipelines, models, and runtimes | 
| `metro_ai_suite` | City monitoring and traffic management |
| `manufacturing_ai_suite` | Industrial inspection and defect detection |
| `retail_ai_suite` | Retail buying-process monitoring |
| `robotics_ai_suite` | Robotics and Physical AI workflows |
| `federal_and_aerospace_ai_suite` | Multi-modal federal and aerospace use cases |
| `health_and_life_science_ai_suite` | Patient and vitals monitoring |

> See [`modules`](module) or [`packages`](package) for the list of available modules.   

## Installation

For simplicity, the OEP installer is presented as a single self-contained shell script (located at [`rendered/openedge-cli`](rendered/openedge-cli)) that can be 
downloaded and then run in a shell environment. 

- install components from a profile, or
```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install computer_vision
```

- install an individual component
```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_parking
```

<hr>

> Prefer a guided experience? **[Open the OEP CLI Installer Web UI »](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html)**
> to pick a profile and module and copy the exact install command.

<hr>

> After the very first invocation, the OEP installer saves itself under `~/.local/bin/openedge-cli`. You can subsequently invoke any installer command locally:

```bash
openedge-cli start smart_intersection
```

<hr>

## Start and Stop

Start or stop a component:

```bash
openedge-cli start smart_parking
openedge-cli stop smart_parking        # or openedge-cli stop to stop all
```

> You cannot start/stop a profile element as the profile contains many components. They may be in conflict
> to start simutenously. Start/stop only individual components.

## Remove

Remove a profile or a component:

```bash
openedge-cli remove video_conferencing
```

> Unlike installation where dependency items are installed automatically, the OEP installer removes a component without touching any dependency items. For example, the OEP installer does not uninstall GPU and NPU drivers upon a sample removal operation. You have to invoke the OEP installer explicitly to remove the GPU and NPU drivers. Use `remove --remove-all` to force removing all installed components.    

## Advanced Usage

### Commandline Options

The OEP installer uses the following commandline options:

```
Usage: openedge-cli <subcommand> [options] [modules/profiles] [module options] ...
```

Multiple subcommands can be specified at once. They are executed in order and the component list from a previous command is passed to next:

```bash
# install with --gpu, start, stop and then start again with --npu
openedge-cli install smart_parking --gpu start stop start -npu
```

The following global options are supported:

| Option | Description |
|:-------|:------------|
| `--dry-run` | Dry run the install/start/stop/remove commands.|
| `--continue` | Ignore errors and let the install operation to proceed to the end. |
| `--validate` | Validate features after installation. |
| `--reinstall` | Force to reinstall a component, if already installed. |
| `--gpu`/`--npu`/`--cpu` | Select GPU/NPU/CPU device at the component level. |
| `--docker`/`--k3s` | Select the deployment model (Docker or K3s) for `edge_node_infrastructure_blueprint` and the Federal and Aerospace components that depend on it. If neither is given, the installed model is kept, or Docker is used for a new installation. |

To specify component specific options, insert a `--<component-name>` tag:

```bash
openedge-cli install smart_parking smart_intersection --smart_parking --gpu
```
where `--gpu` applies to the smart_parking component.  

> Omit `--<component-name>` if there is only a single component or the specified options apply to all components.  

For example, the Federal and Aerospace components install the Edge Node Infrastructure Blueprint first, using the selected deployment model:

```bash
openedge-cli install uav_mission_compute_sdk --k3s
openedge-cli install handheld_multi_modal uav_mission_compute_sdk --uav_mission_compute_sdk --docker
openedge-cli install edge_node_infrastructure_blueprint --k3s
```

> The Edge Node Infrastructure Blueprint is shared, so `--docker` or `--k3s` scoped to any component that depends on it (or to the `federal_and_aerospace_ai_suite` profile) selects that model for the whole installation. Selecting both `--docker` and `--k3s` is rejected.

> To switch an installed blueprint to the other deployment model, run `openedge-cli install edge_node_infrastructure_blueprint --reinstall --k3s` (or `--reinstall --docker`). Requesting a different model without `--reinstall` fails with this hint. Switching from K3s to Docker, or running `openedge-cli remove edge_node_infrastructure_blueprint` on a K3s installation, also removes the K3s runtime installed by the blueprint (using `k3s-uninstall.sh`) and its unmodified `~/.kube/config` copy; Docker, Helm and other shared components are kept.

> The K3s deployment model is not yet supported with `handheld_multi_modal`: both K3s and the application use TCP port 6443. Installing K3s together with, or after, `handheld_multi_modal` (including `federal_and_aerospace_ai_suite --k3s`) is rejected; use Docker.

### List Profiles and Components

Use the `list` subcommand to list components and profiles properties:

```bash
openedge-cli list                          # list supported subcommands of all components
openedge-cli list openvino                 # list supported subcommands of specific component(s)
openedge-cli list --sbom computer_vision   # list installed system-level components
```

> The `sbom` listing is limited to system-level installation only. 

### Installation Locations 

The OEP installer installs the specified components under the following locations:
- Any component workspace files under `~/.local/open-edge-platform/<component-name>`.  
- Installation logs under `~/.local/open-edge-platform/openedge-cli/*.logs`.  
- A replica of the OEP installer under `~/.local/bin`.  
- A bash auto-completion script under `~/.local/share/bash-completion`.  
- A `SKILL.md` under `~/.agents/skills/openedge-cli/SKILL.md`.    

### Bootstrapping

By default, the complete and ready-to-ship installer is committed under [`rendered/openedge-cli`](rendered/openedge-cli). If you modify any source and need to regenerate the installer, use the following steps:

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/frameworks/oep-installer-cli
./openedge-cli bootstrap      # saved to rendered/openedge-cli
```

For bootstrapping with different modules/profiles, use the commands below:

```bash
# include all profiles and modules, or
./openedge-cli bootstrap metro_ai_suite -o rendered/openedge-cli-metro

# include a specific profile/module, or
./openedge-cli bootstrap --install=metro_ai_suite metro_ai_suite -o rendered/openedge-cli-metro

# install metro_ai_suite by default
./openedge-cli bootstrap --setup --install=metro_ai_suite metro_ai_suite -o rendered/openedge-cli-metro
```

> Let `rendered/openedge-cli` be a reserved location for the full installer. If you generate a partial installer, save it other than `rendered/openedge-cli`. 

> **Automated rendering.** You normally do not need to run `bootstrap` by hand. A GitHub
> Actions workflow ([`oep-cli-render-on-merge.yml`](../../.github/workflows/oep-cli-render-on-merge.yml))
> regenerates `rendered/openedge-cli` and commits it back automatically whenever the
> installer source (`openedge-cli`, `common/`, `license/`, `module/`, or `profile/`) changes
> on `main` or a release branch — i.e. after a pull request is merged. The committed
> `rendered/openedge-cli` therefore stays in sync with source without manual steps.

### Web UI Configuration

The [OEP CLI Installer Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html)
is driven by `docs/oep-cli-installer-files/config.json`, which is **generated**
from decentralized, per-profile sources — you edit a small
`profile/<name>/web_config.json` fragment next to each profile instead of one large
shared file. Regenerate it with:

```bash
python3 scripts/build-web-config.py          # regenerate config.json
python3 scripts/build-web-config.py --check   # verify no drift
```

See [`profile/README.md` → *Web UI configuration*](profile/README.md#web-ui-configuration)
for the fragment format and the step-by-step guide to adding a new profile.

> **Automated generation.** The workflow
> ([`oep-cli-config-on-merge.yml`](../../.github/workflows/oep-cli-config-on-merge.yml))
> regenerates `config.json` and commits it back after merge when the base config,
> a profile fragment, or the generator changes, and fails pull requests whose
> committed `config.json` is stale.

### Credentials

During installer operations, if credentials are required, the installer will prompt for sudo password. 
You can avoid the password prompt by providing a `SUDO_PASSWORD` environment variable, a `SUDO_ASKPASS`
helper, or grant passwordless access. 

Other credentials may be required such as `HF_TOKEN` during a gated model download.  

### AI-assisted Module Generation

New installer components can be added by committing code directly to the
[`module/`](module) and/or [`profile/`](profile) directories, or with the help of
an AI coding agent. Drop a Markdown spec file into the
[`specification/`](specification/) directory, push it to `main`, and a GitHub
Actions workflow automatically opens a task for the Copilot coding agent, which
writes `module/<component>` and opens a pull request.

See [SPEC](specification/README.md) for instructions on how to write a spec file.
