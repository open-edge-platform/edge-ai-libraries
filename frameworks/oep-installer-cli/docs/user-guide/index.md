<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

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

The selector offers Ubuntu 24.04 and Ubuntu 26.04. Modules are shown according to
their configured compatibility restrictions. Selecting an OS does not certify
all upstream components on that release; consult the component requirements.
When no compatible modules are available, no install command can be copied.

The **Options** field offers complete, developer-defined flag combinations.
Exactly one choice is selected, starting with the first listed choice. Labels
are generated automatically: for example, **GPU & Docker** passes
`--gpu --docker`. Up to five choices appear as blocks; six or more appear in a
dropdown. Shared links preserve the selected combination when it is supported.

## Installation

Select a profile and a module above to get the exact command for that module.
The command is generated for the module you pick, for example:

```bash
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_parking --gpu start
```

For modules that support Start/Stop, the generated command installs and then
starts the module automatically. Selected flags precede the final `start`.
Modules without Start/Stop support are installed without an automatic start.

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
curl -fsS https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/frameworks/oep-installer-cli/rendered/openedge-cli | bash -s -- install smart_intersection --gpu start
```

## Start and Stop

After the automatic initial start, start or stop a supported module again:

```bash
openedge-cli start smart_parking
openedge-cli stop smart_parking
```

Select a module in the tool above to see its Start and Stop commands. When a
module starts, the installer prints any runtime details (such as a URL) on the
terminal.

## Remove

Next Steps also shows **Remove** for modules that support removal, independently
of Start/Stop support:

```bash
openedge-cli remove smart_parking
```

For an install-all profile, Next Steps offers profile-level removal rather than
individual module lifecycle commands, for example:

```bash
openedge-cli remove computer_vision
```

Removal does not automatically remove shared dependencies. Install-all profiles
are not automatically started.

## Next Steps

After installing a profile, continue with the getting started guide for the
corresponding suite:

::::{grid} 1 1 2 2
:::{grid-item-card} Metro AI
:link: ../../ai-suite-metro.html

City monitoring and traffic management applications.
:::
:::{grid-item-card} Manufacturing AI
:link: ../../ai-suite-manufacturing.html

Industrial environment analysis and recognition.
:::
:::{grid-item-card} Retail AI
:link: ../../ai-suite-retail.html

Monitoring and enhancing the retail buying process.
:::
:::{grid-item-card} Robotics AI
:link: ../../ai-suite-robotics.html

Software empowering robotic appliances.
:::
:::{grid-item-card} Education AI
:link: ../../ai-suite-education.html

Enhancing the classroom teaching and learning experience.
:::
:::{grid-item-card} Health and Life Sciences
:link: ../../ai-suite-health-and-life-sciences.html

New ways of monitoring patients and their vitals.
:::
:::{grid-item-card} Aerospace and Defense
:link: ../../ai-suite-fed-aero.html

Multi-modal applications for federal and aerospace use cases.
:::
::::
