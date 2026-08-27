
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

- `<start|stop|install|remove|profile|license>`: The `profile` function works similarly to a profile, which specifies the component dependencies, and the `install/remove/start/stop` functions perform their corresponding functions. At least one of thoses functions must be defined for the component. Others are optional.

  - For simple system-level packages, for example, `curl`, it is ok to define only an installation function without an uninstaller. The assumption is that `curl` can reside on the system for future use, while uninstalling it everytime is a bit overkill and may cause potentially unintended consequence. For other non-system components, there usually should define both an `install` function and a corresponding `remove` function.
  - The function argument is as follows: `<subcommand> [global-options] <complete list of component names> -- <this component specific arguments>`, where `<subcommand>` is one of `install`, `start`, `stop`, or `remove`. The list of installed components is useful to resolve any dependency issues. For example, `openvino` can use a newer version when installed standalone but a different version when installed together with `dlstreamer`. The arguments of this component can be used for component specific configurations, for example, selecting accelerator devices ([`ensure_select_device`](../common/linux/select_device)).   
  - All component shell scripts run with `set -e` to terminate early on any errors.
  - It is highly recommended to reuse common functions defined under the [`debian`](../common/debian) and [`linux`](../common/linux) folders. Do not reinvent the wheels. 

- `profile`: The optional `profile` function returns the list of dependent components, separated by white space.
  - The dependency component name must be valid components under the `module` or `profile` directory.  
  - Applications, services and SDKs that use GPU or NPU should in general include [`edge_base`](edge_base) as a dependency, which is a virtual package for preparing the system for GPU and NPU acceleration. A similar [`edge_base_rt`](edge_base_rt) profile is available for physical AI deployment.  
  - Once a dependency component is resolved, all shell functions defined by the component are included in the finalized installer and can be utilized by parent components. See [`uv`](uv/debian) for an example. The `uv` component provides a public function `configure_uv` that can be used by other components.  

- `install`: The `install` function installs and configures the component.  
  - Use `$(ensure_project_path)/<component_name>` as the default installation path.  
  - The `install` function should cover the following conditions: (1) The component is not yet installed. (2) The component is previously installed but misconfigured. (3) The component of an older version is installed. After installation, it is assumed that the component is fully configured and ready to be launched (`start`).
  - If the component (of the same version) is already installed, the `install` function should skip the installation unless `--reset-<component_name>` is specified, in which case, the `install` function should reinstall the component cleanly.    
  - For components that support multiple device accelerations, the `install` function must use the [`ensure_select_device`](../common/linux/select_device) function to take user input and configure the component accordingly.  
  - For components that require certain memory size or disk space, use the [`ensure_disk_size`](../common/linux/disk_size) and [`ensure_ram_size`](../common/linux/ram_size) functions to enforce the requirements and exit early.
  - For components that need to download AI models from huggingface, use the [`ensure_hf_token`](../common/linux/hf_token) function to set `HF_TOKEN`. The `ensure_hf_token` function can be used to check model access permissions for gated models.   
  - For libraries, SDKs, applications or tools, after installation, the `install` function should highlight what is next to the users. For example, for SDKs, show the workspace location and instructions of how to configure and play with samples included in the SDKs. See the [`@@HIGHLIGH`](#highlight-protocol) section for more details.

- `remove`: The optional `remove` function removes the component from the system. If the component has a `stop` function, the `remove` function usually invokes the `stop` function to terminate the component before physically remove the component from the system.

- `start`: The optional `start` function launches the component.
  - The `start` function should check the system to make sure the system meet the launch criteria. Use the [`ensure_ports_open`](../common/linux/ports_open) function to ensure required TCP or UDP ports are not occupied. The `ensure_ports_open` function invokes the component `stop` function to stop the component if a previous run occupies the ports.  
  - After the launch, the `start` function should highlight what is next to the users. For example, for web services, the function should show the URL. If there are any generated usernames/passwords, show those as well. See the [`@@HIGHLIGH`](#highlight-protocol) section for more details.  

- `stop`: The optional `stop` function stops a launched component and restores the component state for next launch.  

- `license`: The optional `license` function declares a (or a set of) click-through license(s) that the users must accept before proceeding to component installation.
  - The `license` function must output one or many license sections include license-id, license-title and license-text, as follows:
```
debian_45_license_my_name () {
  cat <<EOF
@@LICENSE-ID <MY-LICENSE-ID>
@@LICENSE-TITLE <MY-LICENSE-TITLE>
<MY-LICENSE-TEXT>
EOF
}
```
where `<license-id>` must be a unique identifier to the license. Multiple licenses with the same license-id's can be accepted at once by the users. Use the [`ensure_license_fetch`](../license/linux/license_fetch) function if the license text must be fetched from the Internet. The `ensure_license_fetch` function does not use any unresolved dependencies at the time of a license clickthrough.  
   
- Helper functions: A component can provide any number of helper functions. The function names must be unique across all installer scripts. A convention is to suffix the helper functions with the component name. If the component is declared as a dependency by other components, these helper functions are available to those components.  
  
The following shows a skeleton of component functions:

```
# configure global variables to be used during start, stop, install and remove
configure_my_component () {
...
}

# check if the component is already installed
verify_my_component () {
...
}

debian_85_install_my_component () {
  configure_my_component "$@"
  if verify_my_component "$@" && [[ " $* " != *"--reset-my_component"* ]]; then
    echo "My component is already installed. Skipping"
  else
    # install component
    ...
    verify_my_component "$@"   # final check after installation
  fi
  # For a SDK, application or service, highlight what's next after installation
  echo "@@HIGHLIGHT next-steps"
}

# optional function if the component is start-able.
#debian_85_start_my_component () {
#  configure_my_component "$@"
#  ensure_ports_open "80 443" debian_85_stop_my_component "$@"
#  ...
#  # For an application or service, highlight what's next after starting the application or service.
#  echo "@@HIGHLIGHT next-steps"    # ex. echo "@@HIGHLIGHT URL: http://$(ensure_ip):$port"
#}

# optional function if the component is stoppable.
#debian_85_stop_my_component () {
#  configure_my_component "$@"
#  ...
#}

# optional function if the component is removable.
#debian_85_remove_my_component () {
#  debian_85_stop_my_component "$@" || true
#  ...
#}

# optional function if the component requires license click through
#debian_85_license_my_component () {
#  echo "@@LICENSE-ID my_component_license_id"
#  echo "@@LICENSE-TITLE my_component_license_title"
#  echo "..." # LICENSE-TEXT or $(ensure_license_fetch <URL>) to fetch license text
#}
```

### @@HIGHLIGHT protocol

`@@HIGHLIGHT` is a marker to display a short hint to the user in the left-pane summary after installation or component launch.  

**When to use it:**
- Include `@@HIGHLIGHT` for components that have a workspace, a service, a UI, an environment to source, sample content, or documentation worth surfacing. In practice these are the higher-order components (roughly **60–98**).
- **Do not** add it for simple stateless utilities (`curl`, `jq`, `gawk`, `unzip`, `make`, `libgl1`, etc.) — there is nothing meaningful to show.

**Format**:
- `@@HIGHLIGHT <label>: <value>` — human-readable text
- `@@HIGHLIGHT <label> @<path-or-command>` — human-readable paths and commands
- Keep each highlight to a single short line.

**Examples**:

- For `start`, the most useful highlight is usually the UI or API URL:

```bash
echo "@@HIGHLIGHT URL: http://$(ensure_ip):$port"
```

- For libraries and SDKs, the most useful highlight is to show the workspace and some hints of operations:

```bash
echo "@@HIGHLIGHT workspace: $workspace"
echo "@@HIGHLIGHT setup env: setup-vars.sh"
echo "@@HIGHLIGHT make help to see full list of build targets"
```
