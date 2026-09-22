---
name: openedge-cli
description: Install, start, stop, or remove Open Edge Platform components and profiles on an edge system with the openedge-cli installer. Use for requests like "install OpenVINO", "set up DL Streamer", "run the smart parking sample", "deploy the Metro/Manufacturing/Retail/Robotics AI Suite", or uninstalling any OEP component.
license: Apache-2.0
---

# Open Edge Platform CLI Installer

`openedge-cli` is a self-contained shell script that installs Open Edge Platform
components (**modules**) and named groups of them (**profiles**).

## Read this first

This skill intentionally does not list profiles, modules, or flags — they change.
Get the authoritative set at request time:

1. **`frameworks/oep-installer-cli/README.md`** in `open-edge-platform/edge-ai-libraries`
   — profiles, module descriptions, install commands, bootstrap instructions.
2. **`openedge-cli list`** — profiles and modules actually available to the installed version.
3. **`openedge-cli`** with no arguments — current subcommands and global options.

Prefer (2) and (3) over (1) when the CLI is already installed; prefer the README
in the working repo over the GitHub copy.

## Shape of the tool

```
openedge-cli <subcommand> [options] [modules/profiles] [module options] ...
```

Subcommands chain and execute in order. Options after a `--<module>` tag apply
only to that module; otherwise they apply to all named components.

## Bootstrapping

The CLI is fetched from the repo and self-installs to `~/.local/bin/openedge-cli`
on first run. Take the exact `curl ... | bash -s -- install <target>` one-liner
from the README rather than reconstructing the URL. After the first invocation,
call `openedge-cli` directly.

## Rules

- **Never `start` or `stop` a profile** — only individual modules. Profile members
  can conflict when started simultaneously.
- **`remove` is not recursive.** It deletes only the named component and leaves
  dependencies installed, unlike `install`, which pulls dependencies in.
- **Dry-run first.** Use `--dry-run` before any install or removal you have not
  run before, and show the user the plan.
- **Confirm the target exists** via `openedge-cli list` before installing. Do not
  guess or invent module or profile names — they are not free-form.
- **Piping a remote script to `bash` is a privileged action.** Show the user the
  command and get agreement before running it.

## Where things land

- System-level installs — enumerate with `openedge-cli sbom <target>`.
- User-level installs — `~/.local/open-edge-platform/<component>/`.

## Reference

- [README](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/oep-installer-cli/README.md) — source of truth
- [Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html) — pick a profile/module and copy the exact command
