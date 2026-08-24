
### Introduction

Components are installable modules within the OEP installer. Their filenames are in the pattern of `<component-name>/<OS_LIKE>`, where `<OS_LIKE>` is the OS family identifier (from `/etc/os-release`.) 
The component name should contain no whitespace or special character except '_'.  

### Develop a component

A component can be defined in optional shell functions: `<OS_LIKE>_<order>_<profile|install|remove|start|stop>_<component-name>`, where 
- `<OS_LIKE>`: The OS family identifier such as `debian`. You can get it from `/etc/os-release`.
- `<order>`: A number (prefixed with `0` if less than 10) from 0 to 99 to specify the installation order. The OEP installer will install components in the following order:

```
00-29   kernel modules/drivers
30-59   low level libraries
60-89   middle level libraries/microservices
90-98   applications
99      profiles
```

- `<start|stop|install|remove|profile>`: The `profile` function works similarly to a profile, which specifies the component dependencies, and the `install/remove/start/stop` functions perform their corresponding functions. At least one of thoses functions must be defined for the compoenent. Others are optional.

> For simple system-level packages, for example, `curl`, it is ok to define only an installation function without an uninstaller. The assumption is that `curl` can reside on the system for future use, while uninstalling it everytime is a bit overkill and may cause potentially unintended consequence. For other non-system components, there usually should define both an `install` function and a corresponding `remove` function. 

### Clickthrough License

Components that require explicit license agreement must define a license function:

```
debian_45_license_my_name () {
  cat <<EOF
@@LICENSE-ID <MY-LICENSE-ID>
@@LICENSE-TITLE <MY-LICENSE-TITLE>
<MY-LICENSE-TEXT>
EOF
}
```
where the function must print out license id, title and text. If you must fetch license text from a URL, use `ensure_license_fetch` as `curl` may not be available at the time of the license clickthrough.  

### Name Convention

Special care must be taken to write the shell functions such that there is no name collusion in both the function names and any used shell variables. 
It is a covention to always use local shell variables or prefix or suffix with the compoennt name. 

### @@HIGHLIGHT protocol

`@@HIGHLIGHT` is a marker consumed by `ensure_panelled_logs`
(`common/linux/panelled_logs`) to display a short hint to the user in the
left-pane summary after install or start.

**When to use it:**
- Include `@@HIGHLIGHT` for components that have a workspace, a service, a UI,
  an environment to source, sample content, or documentation worth surfacing.
  In practice these are the higher-order components (roughly **60–98**).
- **Do not** add it for simple stateless utilities (`curl`, `jq`, `gawk`,
  `unzip`, `make`, `libgl1`, etc.) — there is nothing meaningful to show.

**For `start`**, the highlight should usually show the URL the user must point
to, built with `ensure_ip`:

```bash
echo "@@HIGHLIGHT URL: http://$(ensure_ip):$port"
```

**Placement**: emit `@@HIGHLIGHT` lines **outside** the "already installed,
skipping" branch so they are printed on both fresh and skipped installs.
See `module/openvino/debian` and `module/dlstreamer/debian` for examples.

**Format**:
- `@@HIGHLIGHT <label>: <value>` — human-readable text
- `@@HIGHLIGHT <label> @<path-or-command>` — paths and commands
- Keep each highlight to a single short line.
