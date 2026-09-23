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
marketing segments. The table lists the profiles and their components.  

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

### Module reference

| Module | Description |
| ------ | ----------- |
| `openvino` | The OpenVINO™ inference runtime and toolkit. |
| `dlstreamer` | The Intel® DL Streamer video-analytics pipeline framework. |
| `vippet` | The Visual Pipeline and Platform Evaluation Tool. |
| `geti` | The Intel® Geti™ computer-vision model training platform. |
| `anomalib` | The deep-learning library for visual anomaly detection. |
| `smart_intersection` | A traffic-intersection monitoring reference sample. |
| `smart_parking` | A smart-parking occupancy and monitoring sample. |
| `loitering_detection` | A loitering-detection video analytics sample. |
| `live_video_captioning` | A real-time video captioning sample. |
| `video_search_and_summarization` | A video search and summarization (VLM-based) sample. |
| `pallet_defect_detection` | A pallet defect-detection inspection sample. |
| `pcb_anomaly_detection` | A PCB anomaly-detection inspection sample. |
| `multimodal_weld_defect_detection` | A multi-modal weld defect-detection sample. |
| `loss_prevention` | A Retail loss-prevention sample. |
| `order_accuracy` | A Retail order-accuracy verification sample. |
| `handheld_multi_modal` | A handheld multi-modal sample for federal/aerospace use cases. |
| `nicu_warmer` | A NICU warmer patient-monitoring sample. |
| `autonomous_mobile_robot` | Robotics AI Suite ROS 2 SDK for sensing, SLAM, and navigation. |
| `stationary_robot_vision` | Vision-guided pick-and-place reference sample (RVC). |
| `humanoid_imitation_learning` | Imitation-learning track (ACT and Pi0.5 policies). |
| `physical_ai_framework` | Physical AI training/deployment SDK (`physicalai` CLI). |
| `physical_ai_studio` | Physical AI Studio backend + web UI for data collection and training. |

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

> Unlike installation where dependency items are installed automatically, the OEP installer removes a component without touching any dependency items. For example, the OEP installer does not uninstall GPU and NPU drivers upon a sample removal operation. You have to invoke the OEP installer explicitly to remove the GPU and NPU drivers.

## Advanced Usage

### Commandline Options

The OEP installer uses the following commandline options:

```
Usage: openedge-cli <subcommand> [options] [modules/profiles] [module options] ...
```

Multiple subcommands can be specified at once. They are executed in order:

```bash
openedge-cli install smart_parking --gpu start smart_parking --gpu
```

The following global options are supported:

| Option | Description |
|:-------|:------------|
| `--dry-run` | Dry run the install/start/stop/remove commands.|
| `--continue` | Ignore errors and let the install operation to proceed to the end. |
| `--validate` | Validate features after installation. |
| `--reinstall` | Force to reinstall a component, if already installed. |
| `--gpu`/`--npu`/`--cpu` | Select GPU/NPU/CPU device at the component level. |

To specify component specific options, insert a `--<component-name>` tag:

```bash
openedge-cli install smart_park smart_intersection --smart_parking --gpu
```

> Omit `--<component-name>` if there is only a single component or the specified options apply to all components.  

### List Profiles and Components

Use the `list` subcommand to list all components and profiles 

```bash
openedge-cli list
```

### List SBOM

Use the `sbom` subcommand to discover what is installed by the OEP installer system wide. 

```bash
openedge-cli sbom computer_vision
```

> The listing is limited to system-level installation only.

> User level installation is under `~/.local/open-edge-platform/<component-name>`.  

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
