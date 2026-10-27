<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

### Introduction

Profiles are virtual groups of installer components. The profile filenames use this pattern: `<profile-name>/<OS_LIKE>`, where `<OS_LIKE>` is the OS family identifier obtained from `/etc/os-release`, 
and the profile name should contain no space or special character except `_`.  

### Develop a Profile

A profile specifies the list of required components in a single shell function: `<OS_LIKE>_<order>_profile_<name>`, where `<order>` specifies the installation order. Since profiles are virtual groups, they always use order `99` to install the latest. 

A profile can be as simple as follows:

```
debian_99_profile_metro_ai_suites () {
  echo "smart_parking smart_intersection loitering_detection"
}
```
where each component is listed at the output.  

In the above sample, if we want to specify that the components can install/remove togeher but not start/stop together, we can make it conditioned on the installer subcommand:

```
debian_99_profile_metro_ai_suites () {
  case "$1" in
  install|remove)
    echo "smart_parking smart_intersection loitering_detection"
    ;;
  esac
}
```
where the `_profile_` function arguments are as follows: `<subcommand> [global options] [list of components] -- [component specific options]`.  

> If your profile function returns different list of components based on component options, you need to additionally return a superset of all components when the subcommand is `bootstrap`, critical to include all components that the profile depends on. See [`edge_base`](../module/edge_base/debian) for an example.    

### Web UI configuration

The [OEP CLI Installer Web UI](https://docs.openedgeplatform.intel.com/dev/OEP-articles/oep-cli-installer/index.html)
lets users pick a profile and module and copy the exact install command. Its
data is **decentralized per profile** so you edit configuration next to your
profile instead of one large shared file.

Sources:

- `docs/oep-cli-installer-files/config.base.json` — shared/global settings
  (title, share keys, the OS category, output templates, and `profileOrder`,
  which controls the display order of profiles and modules).
- `profile/<name>/web_config.json` — one small fragment per profile (this is the
  file you edit).
- `docs/oep-cli-installer-files/config.json` — the **generated** file the Web UI
  loads. Do not edit it by hand; it is produced by the generator script.

#### Fragment format

Copy [`profile/_web_config_template.json`](_web_config_template.json) as a starting
point. The schema is:

```jsonc
{
  // Required. The profile shown in the Profile selector.
  //   installAll: true  -> the profile installs all its modules at once; the
  //                        Module list is shown read-only and the install
  //                        command comes from the "install" block below.
  //   remove: true      -> the profile supports removal of its modules.
  "profile": {
    "label": "My AI Suite",
    "value": "my_ai_suite",
    "installAll": true,
    "remove": true,
    "supports": { "OP_SYSTEM": ["UBUNTU_24_04", "UBUNTU_26_04"] }
  },

  // Required. The modules that belong to this profile.
  //   startStop: true   -> the module exposes start/stop lifecycle commands and
  //                        starts automatically after install, and gets
  //                        standalone Start/Stop commands in "Next Steps".
  //   remove: true      -> independently adds a Remove command in "Next Steps".
  //   options: [...]    -> complete CLI flag combinations; exactly one is chosen.
  //                        The first entry is pre-selected. Labels are automatic:
  //                        "--gpu --docker" becomes "GPU & Docker".
  //                        Use "" for an explicit "Default" (no flags) choice.
  //   supports          -> optionally restrict OP_SYSTEM to configured OS values.
  "modules": [
    { "label": "My Module", "value": "my_module", "remove": true },
    {
      "label": "My Service",
      "value": "my_service",
      "startStop": true,
      "remove": true,
      "options": ["--gpu", "--docker", "--gpu --docker"],
      "supports": { "OP_SYSTEM": ["UBUNTU_24_04", "UBUNTU_26_04"] }
    }
  ],

  // Optional. A profile-level install command (typically used with installAll).
  // Omit it and the Web UI falls back to "install <selected modules>".
  "install": { "text": "wget -qO- https://.../openedge-cli | bash -s -- install my_ai_suite" },

  // Optional. The "Get Started" link for this profile.
  "getStarted": { "text": "Get Started", "link": "https://.../get-started.html" },

  // Optional. The "Resources" links for this profile.
  "resources": [
    { "text": "My Module", "url": "https://.../index.html" }
  ]
}
```

**Auto-injected — do not write these yourself:** the generator adds each
module's `supports.PROFILE` (from the owning profile's `value`) and every
output rule's `when` condition for each supported operating system.

#### Options, operating systems, and lifecycle commands

The `options` list defines every supported choice explicitly. The selector does
not infer combinations: `["--gpu", "--docker"]` offers two choices, whereas
`["--gpu", "--docker", "--gpu --docker"]` also offers **GPU & Docker**.
Only declare combinations the module actually supports. Single-flag entries
remain compatible with existing fragments. The old `multiSelect` property is
rejected; replace it with explicit combinations.

The first entry is selected by default. One through five choices use blocks;
six or more use a single-selection dropdown. Labels are generated from the flags,
so no label map or combination definitions are needed in the base configuration.
An explicit `""` entry is labeled **Default** and passes no flags. Modules without
`options` do not show an Options section.

Shared URLs retain comma-separated flag names in `OPTIONS` (for example
`OPTIONS=gpu,docker`, or `OPTIONS=none` for an explicitly configured empty
choice). A URL must match a whole configured combination; reordered flags are
canonicalized, while invalid, partial, or stale choices reset to the first entry.
Changing modules preserves a combination only if the selected configurable
modules all offer it. The Module category supports multiple selections from
one profile. Shared combinations are intersected as complete flag sets, not
individual flags; modules without options do not constrain them and receive
no flags. When every selected module offers the shared combination, flags are
global. Otherwise the UI scopes them to configurable modules. If no common
combination exists, Install copying is disabled with an explanation.

The OS values are `UBUNTU_24_04` for Ubuntu 24.04 and
`UBUNTU_26_04` for Ubuntu 26.04. Omitted `supports.OP_SYSTEM` means both are
available. Set it on a module, or on a profile, to restrict availability.
All existing profiles explicitly list both OS versions; remove a value from a
`profile.supports.OP_SYSTEM` list when the profile only supports one. An
install-all profile is unavailable if one of its modules is incompatible with
the chosen OS. If a selection has no compatible modules, the selector clears
the module and disables command copying.

Adding an OS to this selector does not certify every upstream component on that
release; check component requirements before deploying.

For modules with `startStop: true`, the generated command ends with, for example,
`install my_service --gpu --docker start`. Install-only modules and install-all
profiles do not automatically start. Standalone Start/Stop commands remain
available when at least one selected module supports them. When every selected module
supports start, the generated install command ends with bare `start`, reusing
the install selection. Mixed selections explicitly name only start-capable
modules after `start`.

Set `remove: true` only after verifying that the module has a removal handler,
or that the profile expands correctly for `remove`. This capability is
independent of `startStop`: a module can offer Remove without Start/Stop.
The UI shows `openedge-cli start`, `openedge-cli stop`, and `openedge-cli remove`
without module names, with brief scope descriptions. Start and Remove use the
CLI's saved module selection, not necessarily the current browser selection.
Stop stops all previously started modules, including those outside the current
selection. Capability flags control whether the corresponding command is shown;
they do not restrict the short command's runtime targets.
Install-all profiles with `remove: true` also show `openedge-cli remove`;
their read-only module list does not expose individual Start/Stop commands.

Shared links serialize multiple module values with commas in `MODULE`, while
`MODULE=` preserves an intentionally empty selection. Empty selections disable
command copying. No modules are selected by default. Switching profiles clears
the module selection; switching OS retains only compatible selected modules
without selecting replacements. Explicit single-module and multi-module URLs
remain supported. Install-all profiles still install the whole profile without
individual module selection.

Run selector regressions with `node --test scripts/test-selector.cjs` and
JavaScript syntax validation with
`node --check docs/oep-cli-installer-files/selector.js` from the component root.

#### Add a new profile to the Web UI

1. Create the profile shell definition as described above
   (`profile/<name>/<OS_LIKE>`).
2. Add `profile/<name>/web_config.json` by copying `profile/_web_config_template.json`
   and filling in your profile, modules, and links. Set `installAll: true` and
   an `install` command only if the profile installs everything at once;
   otherwise omit both.
3. Add your profile's `value` to the `profileOrder` array in
   `docs/oep-cli-installer-files/config.base.json` at the position you want it
   to appear.
4. Regenerate and verify locally:

   ```bash
   python3 scripts/build-web-config.py          # regenerate config.json
   python3 scripts/build-web-config.py --check   # verify no drift
   ```

5. Commit your fragment, the `config.base.json` change, and the regenerated
   `docs/oep-cli-installer-files/config.json`.

> The `[OEP CLI] Generate Web UI config on merge` GitHub Action regenerates
> `config.json` automatically after merge and fails pull requests whose
> committed `config.json` is stale (`--check`). Regenerating locally keeps your
> PR green.
