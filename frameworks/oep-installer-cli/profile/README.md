
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
  "profile": { "label": "My AI Suite", "value": "my_ai_suite", "installAll": true },

  // Required. The modules that belong to this profile.
  //   startStop: true   -> the module exposes start/stop lifecycle commands and
  //                        gets a "Next Steps" (Start/Stop) section.
  "modules": [
    { "label": "My Module", "value": "my_module" },
    { "label": "My Service", "value": "my_service", "startStop": true }
  ],

  // Optional. A profile-level install command (typically used with installAll).
  // Omit it and the Web UI falls back to "install <module>" per module.
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
output rule's `when` condition (`{ "PROFILE": <value>, "OP_SYSTEM": <default> }`).

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

