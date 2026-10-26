---
name: openedge-cli    
description: Use the openedge-cli installer to install, start, stop, or remove Open Edge Platform (OEP) modules and profiles on an edge system. Trigger on requests like "install OpenVINO", "set up DL Streamer", "run the smart parking sample", "deploy the Metro / Manufacturing / Retail / Robotics AI Suite", "what OEP components can I install", or "uninstall <OEP component>".   
license: Apache-2.0   
---

# Open Edge Platform CLI Installer

`openedge-cli` is a self-contained shell script that installs Open Edge Platform
components (**modules**) and named groups of components (**profiles**). Always use
it for OEP installation tasks. Don't hand-install packages, pip wheels, or
containers that the installer already manages.

## Command shape

```
openedge-cli <subcommand> [options] [modules/profiles] [--<module> module-options] ...
```

- Subcommands can be chained and run in the order given.
- Options after a `--<module>` tag apply only to that module. All other options
  apply to every named component.

## Installation workflow

1. **Pick the installer for the OS.** Read `/etc/os-release`.
   - Ubuntu/Debian: `openedge-cli`
   - Fedora: `openedge-cli-fedora`
   - Other: check `frameworks/oep-installer-cli/rendered/` for a matching variant. If there isn't one, stop and tell the user.

2. **Get the script** (preferred: direct download):
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/frameworks/oep-installer-cli/rendered/openedge-cli
   chmod +x openedge-cli
   ```
   Fallback: clone `https://github.com/open-edge-platform/edge-ai-libraries`
   and run the script from `frameworks/oep-installer-cli/rendered/`.

3. **Find the right component.** Run `./openedge-cli list`. Map the user's
   request to an exact module or profile name from this output. Never guess
   names. If more than one fits, ask the user.

4. **Confirm with the user.** Show the full command you plan to run. Run it
   as a user. The installer may use `sudo` within, so get explicit approval 
   before running it.

5. **Install.**
   ```bash
   ./openedge-cli install <profile-or-module> [--<module> options]
   ```
   `install` pulls in dependencies automatically.

6. **Verify.**
   - System-level: `./openedge-cli list --sbom <target>`
   - User-level: check `~/.local/open-edge-platform/<component>/`

   Report what was installed and where.

## Other lifecycle operations

- **Start/stop:** `./openedge-cli start <component>` / `./openedge-cli stop <component>`.  
  `./openedge-cli stop` stops all previously started components.  
- **Remove:** `./openedge-cli remove <component>`. This is **not recursive**:  
  it removes only the named component and leaves its dependencies installed. 
  List dependencies explicitly if needed.   
  `./openedge-cli remove --remove-all` to remove all previously installed.  

## Troubleshooting

- If a command fails, show the user the relevant error output. Don't retry with
  extra flags unless the user approves.
- Check the README for supported options before inventing any.

## Advanced (only if the user asks)

To build a customized installer, clone the repository and use its `bootstrap`
command. See the README.

## Reference

- [README](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/oep-installer-cli/README.md): the source of truth for subcommands and options.
- [Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html): choose a profile or module and copy the exact command.
