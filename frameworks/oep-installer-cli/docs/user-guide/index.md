# Open Edge Platform (OEP) CLI Installer

The OEP CLI Installer (`openedge-cli`) is a modular, self-contained shell
installer that discovers, bootstraps, and installs Open Edge Platform modules on
your edge system. Modules are grouped into **profiles** so you can browse the
suite you want, then install an individual module with a single command.

<!--hide_directive
<script type="module" crossorigin src="../../_static/oep-cli-installer-files/iframe-resizer.js"></script>
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<iframe id="installerFrame" src="../../_static/oep-cli-installer-files/selector.html" style="width: 100%; min-width: 350px; border: none; overflow: hidden;" title="Install with the OEP CLI Installer"></iframe>
hide_directive-->

## Overview

The installer ships as a single `openedge-cli` script. Installable **modules**
(for example `dlstreamer`, `openvino`, or `smart-parking`) and their
dependencies live under the `module/` directory, while **profiles** are virtual
groups of modules defined under the `profile/` directory. Selecting a profile in
the tool above lists the modules it contains; selecting a module then shows the
exact install command generated for that module, next steps, and links to the
suite documentation.

## Installation

Select a profile and a module above to get the exact command for that module.
The command is generated for the module you pick, for example:

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_parking
```

The **Computer Vision** and **Inferencing** profiles install every module in the
profile at once, so they do not require a module selection. Their modules are
listed for reference and the command installs the whole profile, for example
`install computer_vision` or `install inferencing`.

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install computer_vision
```

This `curl | bash` pattern bootstraps and installs the selected module in a
single step. Swap the module name to install a different module, for example
`smart-intersection`:

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_intersection
```

## Start and Stop

Once installed, start or stop a module:

```bash
openedge-cli start smart-parking
openedge-cli stop smart-parking
```

Select a module in the tool above to see its Start and Stop commands. When a
module starts, the installer prints any runtime details (such as a URL) on the
terminal.

## Next Steps

After installing a profile, continue with the getting started guide for the
corresponding suite:

::::{grid} 1 1 2 2
:::{grid-item-card} Metro AI
:link: ../../ai-suite-metro.md

City monitoring and traffic management applications.
:::
:::{grid-item-card} Manufacturing AI
:link: ../../ai-suite-manufacturing.md

Industrial environment analysis and recognition.
:::
:::{grid-item-card} Retail AI
:link: ../../ai-suite-retail.md

Monitoring and enhancing the retail buying process.
:::
:::{grid-item-card} Robotics AI
:link: ../../ai-suite-robotics.md

Software empowering robotic appliances.
:::
:::{grid-item-card} Education AI
:link: ../../ai-suite-education.md

Enhancing the classroom teaching and learning experience.
:::
:::{grid-item-card} Health and Life Sciences
:link: ../../ai-suite-health-and-life-sciences.md

New ways of monitoring patients and their vitals.
:::
:::{grid-item-card} Aerospace and Defense
:link: ../../ai-suite-fed-aero.md

Multi-modal applications for federal and aerospace use cases.
:::
::::
