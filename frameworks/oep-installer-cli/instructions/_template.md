# Component spec: <component_name>

<!-- Replace every <placeholder> with real values and remove this comment. -->

## Purpose

<!-- One paragraph describing what this component does and why it is useful
     in an Open Edge Platform context. -->

## Installation order / category

<!-- Choose the numeric range that best fits this component:
     00-29  kernel modules / drivers
     30-59  low-level libraries
     60-89  middle-level libraries / microservices
     90-98  applications
     99     profiles                                   -->

**Proposed order number**: `<NN>` (range: <category>)

## Dependencies

<!-- List the names of existing components under module/ that must be
     installed before this component.  One name per line.            -->

- `<dependency_1>`
- `<dependency_2>`

## Installation steps

**Upstream repository**: `<https://github.com/...>`  
**Version / tag**: `<release-x.y.z>`

<!-- Describe step by step what the install function must do:
     - packages to install via apt
     - git clone / setup scripts
     - environment configuration                                      -->

## Verification

<!-- Describe how verify_<name>() should confirm the component is installed.
     Examples: file or binary presence, version string check, health URL.  -->

## Start / stop behaviour

<!-- Describe how to start and stop the component.
     If it is a stateless system package with no runtime service,
     note that start/stop are not needed.                             -->

**Start**: <!-- e.g. `docker compose up -d` -->  
**Stop**:  <!-- e.g. `docker compose down -v` -->  
**UI entrypoint**: <!-- e.g. `http://<host>:8080` or N/A -->

## Ports

<!-- List TCP/UDP ports opened by this component, or "none". -->

| Port | Protocol | Purpose |
|------|----------|---------|
| `<port>` | TCP | `<purpose>` |

## Removal

<!-- Describe what the remove function must clean up:
     - Docker images / volumes
     - git workspace directory
     - apt packages (if safe to remove)
     - configuration files                                            -->

## Reset flag behaviour

<!-- Describe what --reset-<component_name> should do
     (e.g. delete workspace and reinstall from scratch).             -->

## License requirements

<!-- State whether the user must accept a click-through license.
     If yes, provide:                                                  -->

**Requires click-through**: <!-- yes / no -->  
**License ID**:    <!-- e.g. INTEL-EULA-2024 -->  
**License title**: <!-- e.g. Intel End User License Agreement -->  
**License text URL**: <!-- URL or paste full text below -->
