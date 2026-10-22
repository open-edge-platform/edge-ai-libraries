---
name: openedge-cli
description: Install, start, stop, or remove Open Edge Platform components and profiles on an edge system with the openedge-cli installer. Use for requests like "install OpenVINO", "set up DL Streamer", "run the smart parking sample", "deploy the Metro/Manufacturing/Retail/Robotics AI Suite", or uninstalling any OEP component.
license: Apache-2.0
---

# Open Edge Platform CLI Installer

`openedge-cli` is a self-contained shell script that installs Open Edge Platform
components (**modules**) and named groups of them (**profiles**).

## Read this first

The installer is available from any of the following methods:
1. Clone the repository `https://github.com/openedge-platform/edge-ai-libraries`. The installers are under `frameworks/oep-installer-cli/rendered/openedge-cli`. Other OS installers are available, for example, `openedge-cli-fedora`.  
2. Directly download the installer script from the above github link.  
3. Clone the repository `https://github.com/openedge-platform/edge-ai-libraries`. Use the `bootstrap` command to generate a customized installer.  

Prefer (2) for simplicity.

The installable components can be obtained by:
1. Use `openedge-cli list` to show the profiles and modules available for `install` or other commands.  

## Shape of the tool

```
openedge-cli <subcommand> [options] [modules/profiles] [module options] ...
```

Subcommands chain and execute in order. Options after a `--<module>` tag apply
only to that module; otherwise they apply to all named components.

## Rules

- **`remove` is not recursive.** It deletes only the named component and leaves
  dependencies installed, unlike `install`, which pulls dependencies in.
- **The installer may ask for priviledged access.** Show the user the
  command and get agreement before running it.

## Where things land

- System-level installs — enumerate with `openedge-cli list --sbom <target>`.
- User-level installs — `~/.local/open-edge-platform/<component>/`.

## Reference

- [README](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/oep-installer-cli/README.md) — source of truth
- [Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html) — pick a profile/module and copy the exact command

