# Open Edge Platform (OEP) CLI Installer

The **OEP CLI Installer** (`openedge-cli`) is a modular, self-contained shell
installer that discovers, bootstraps, and installs Open Edge Platform modules on
your edge system. Modules are grouped into **profiles**, so you can browse the AI
suite you want and install an individual module or a whole profile with a single command.

<p align="center">
  <a href="https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html">
    <img src="https://img.shields.io/badge/Launch%20Web%20UI-0068B5?style=for-the-badge&labelColor=0068B5" alt="Launch the OEP CLI Installer Web UI" />
  </a>
</p>

> **Web UI:** Prefer a guided experience? **[Open the OEP CLI Installer Web UI »](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html)**
> to pick a profile and module and copy the exact install command.

## Overview

The installer ships as a single `openedge-cli` script. Installable **modules**
(for example `dlstreamer`, `openvino`, or `smart_parking`) and their dependencies.

Selecting a profile in the [Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html)
lists the modules it contains; selecting a module then shows the exact install
command generated for that module, its next steps, and links to the suite
documentation.

## Profiles and Modules

Profiles are curated bundles of modules targeting specific domain workloads and
AI suites. The table below lists every profile and the modules it installs.

| Profile | Domain | Modules |
| ------- | ------ | ------- |
| `inferencing` | Core AI inferencing runtime | `openvino` |
| `computer_vision` | Computer-vision pipelines, models, and runtimes | `dlstreamer`, `vippet`, `geti`, `anomalib` |
| `metro_ai_suite` | City monitoring and traffic management | `smart_intersection`, `smart_parking`, `loitering_detection`, `live_video_captioning`, `video_search_and_summarization` |
| `manufacturing_ai_suite` | Industrial inspection and defect detection | `pallet_defect_detection`, `pcb_anomaly_detection`, `multimodal_weld_defect_detection` |
| `retail_ai_suite` | Retail buying-process monitoring | `loss_prevention`, `order_accuracy` |
| `robotics_ai_suite` | Robotics and Physical AI workflows | `autonomous_mobile_robot`, `stationary_robot_vision`, `humanoid_imitation_learning`, `physical_ai_framework`, `physical_ai_studio` |
| `federal_and_aerospace_ai_suite` | Multi-modal federal and aerospace use cases | `handheld_multi_modal` |
| `health_and_life_science_ai_suite` | Patient and vitals monitoring | `nicu_warmer` |

> Modules within some suites (for example `metro_ai_suite` and
> `manufacturing_ai_suite`) cannot run at the same time. In those cases, install
> the profile for convenience but **start and stop individual modules**.

### Module reference

| Module | Description |
| ------ | ----------- |
| `openvino` | OpenVINO™ inference runtime and toolkit. |
| `dlstreamer` | Intel® DL Streamer video-analytics pipeline framework. |
| `vippet` | Visual Pipeline and Platform Evaluation Tool. |
| `geti` | Intel® Geti™ computer-vision model training platform. |
| `anomalib` | Deep-learning library for visual anomaly detection. |
| `smart_intersection` | Traffic-intersection monitoring reference application. |
| `smart_parking` | Smart-parking occupancy and monitoring application. |
| `loitering_detection` | Loitering-detection video analytics application. |
| `live_video_captioning` | Real-time video captioning application. |
| `video_search_and_summarization` | Video search and summarization (VLM-based) application. |
| `pallet_defect_detection` | Pallet defect-detection inspection application. |
| `pcb_anomaly_detection` | PCB anomaly-detection inspection application. |
| `multimodal_weld_defect_detection` | Multi-modal weld defect-detection application. |
| `loss_prevention` | Retail loss-prevention application. |
| `order_accuracy` | Retail order-accuracy verification application. |
| `handheld_multi_modal` | Handheld multi-modal application for federal/aerospace use cases. |
| `nicu_warmer` | NICU warmer patient-monitoring application. |
| `autonomous_mobile_robot` | Robotics AI Suite ROS 2 SDK for sensing, SLAM, and navigation. |
| `stationary_robot_vision` | Vision-guided pick-and-place reference application (RVC). |
| `humanoid_imitation_learning` | Imitation-learning track (ACT and Pi0.5 policies). |
| `physical_ai_framework` | Physical AI training/deployment SDK (`physicalai` CLI). |
| `physical_ai_studio` | Physical AI Studio backend + web UI for data collection and training. |

## Installation

Use the [Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html)
to select a profile and module and get the exact command. The `curl | bash`
pattern bootstraps and installs the selected module in a single step — just swap
the module name to install a different one:

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_parking
```

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_intersection
```

The **Computer Vision** and **Inferencing** profiles install every module in the
profile at once, so they do not require a module selection:

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install computer_vision
```

## Start and Stop

Once installed, start or stop a module:

```bash
openedge-cli start smart_parking
openedge-cli stop smart_parking
```

Select a module in the Web UI to see its Start and Stop commands. When a module
starts, the installer prints any runtime details (such as a URL) to the terminal.

## Advanced Usage

The `rendered/` directory already contains a ready-to-ship `openedge-cli` with
all modules and profiles included. The steps below describe how to regenerate it.

### Bootstrapping

By default, the base installer does not contain any installable components — they
live under the [`module/`](module) and [`profile/`](profile) directories. Use the
`bootstrap` command to self-construct the final installer:

```bash
./openedge-cli bootstrap                                               
```

After bootstrapping, the `openedge-cli` script includes all components specified
by the chosen profile and is ready to ship.

For bootstrapping with different modules/profiles, use the commands below:

```bash
# include all profiles and modules, or
./openedge-cli bootstrap metro_ai_suite

# include a specific profile/module
./openedge-cli bootstrap --install=metro_ai_suite metro_ai_suite

# install metro_ai_suite by default
./openedge-cli bootstrap --setup --install=metro_ai_suite metro_ai_suite  # setup installer locally and install metro_ai_suite
```

### Installation and Removal

Install or remove a component or a profile:

```bash
./rendered/openedge-cli install metro_ai_suite
./rendered/openedge-cli remove metro_ai_suite
```

### Start and Stop

Start or stop a component:

```bash
./rendered/openedge-cli start smart_parking
./rendered/openedge-cli stop smart_parking
```

> If components within a profile are not compatible with each other, you cannot
> start/stop the profile as a whole — start/stop the component directly.
> `./rendered/openedge-cli stop` stops all apps.

### Deployment

The installer can be hosted on a website for click-to-download. Instruct users to
copy and paste the command:

```bash
# with default command(s)
curl ... | bash

# with an explicit command
curl ... | bash -s -- install smart_parking
```

You can bake in any default commands during the bootstrap process. If you pass
`--setup` during bootstrap, the installer reconstructs itself locally at
`~/.local/bin` with bash completion, so you can use it as a local command.

### AI-assisted Module Generation

New installer components can be added by committing code directly to the
[`module/`](module) and/or [`profile/`](profile) directories, or with the help of
an AI coding agent. Drop a Markdown spec file into the
[`specification/`](specification/) directory, push it to `main`, and a GitHub
Actions workflow automatically opens a task for the Copilot coding agent, which
writes `module/<component>` and opens a pull request.

- For **new** spec files, the agent is dispatched automatically.
- For **modified** spec files, an issue is created but the agent is held until a
  maintainer explicitly adds the `GENERATE-COMPONENT` label — ensuring a human
  reviews the spec change before AI code generation begins.

See [SPEC](specification/README.md) for instructions on how to write a spec file.
