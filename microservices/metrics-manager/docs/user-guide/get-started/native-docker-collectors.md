<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Additional collectors in the native-enabled Docker image

This guide applies to the native Go collector image targeting **2026.3.0**
(currently unreleased). Build locally until the image is published.
Configure this image through its environment variables and mounted Telegraf
drop-ins, as described below.

## Default and optional inputs

The shipped `telegraf.conf` still starts CPU, GPU, NPU, process and
memory-bandwidth collectors, alongside Telegraf CPU, memory, package-temperature
and base `intel_powerstat` package-power/C-state inputs. GPU throttle/frequency
detail is already part of the native GPU collector. Optional flags do not
disable this baseline.

Memory bandwidth uses each IMC PMU's `cpumask` to cover its representative
CPUs across dies/sockets, not a fixed CPU 0. It retains one host-total series
set and refuses partial totals on controller errors. The container must see
the relevant PMU sysfs entries and have
perf access under the host policy. No new mount, capability or automatic
privilege escalation is introduced.

The following flags default to **false** in the default bridge deployment.
The opt-in host-NIC variant defaults only `ENABLE_NETWORK` to **true**; an
explicit `false` overrides it. Docker accepts only lowercase
`true` or `false`: `auto`, empty strings, numeric values and other spellings
are startup errors.

| Flag | Additional coverage |
|---|---|
| `ENABLE_RAPL` | Native RAPL package/platform (`psys`) power |
| `ENABLE_POWERSTAT_EXTRA` | Per-CPU frequency and temperature, without repeating baseline package/C-state metrics |
| `ENABLE_TURBOSTAT` | IPC, SMI and other Turbostat diagnostics; requires the explicit binary mount below |
| `ENABLE_TEMPERATURE` | 100 ms package-temperature samples and 1 s min/max/mean |
| `ENABLE_INTERRUPTS` | Numbered device IRQ counters, including per-CPU series |
| `ENABLE_NETWORK` | Primary eth*/en* traffic and NIC driver counters in the container's network namespace |
| `ENABLE_NETWORK_VIRTUAL` | Separate veth/lxc traffic and driver counters, independent of `ENABLE_NETWORK` |
| `ENABLE_STORAGE` | Filesystem usage and disk I/O; serial/WWID export disabled |

For example, from the component directory:

```bash
ENABLE_RAPL=true ENABLE_INTERRUPTS=true \
  docker compose up -d --build --force-recreate metrics-manager
docker compose logs --tail=100 metrics-manager
```

Set persistent choices in `.env`. Compose explicitly passes these settings into
the container. With plain `docker run`, pass them using `-e ENABLE_RAPL=true`,
etc. The legacy Python-image names such as `ENABLE_RAPL_POWER`, `ENABLE_DRAM_BW`
and `ENABLE_PSYS_POWER` are not aliases.

## Configuration loading and customization

At startup the entrypoint:

1. Validates the flags and Turbostat runtime settings.
2. Reads the main configuration and mounted `telegraf.d/**/*.conf` files.
3. Selects enabled bundled additions and checks for conflicts with user inputs.
4. Checks Turbostat inside the container if its automatic addition is enabled.
5. Copies the selected drop-ins to a new private temporary directory and starts:

   ```text
   telegraf --config /etc/telegraf/telegraf.conf --config-directory <selected-directory>
   ```

The main configuration remains separate. Source files are never rewritten.
Every start creates a fresh selection, so disabling an automatic addition does
not leave an old generated file active. Only `.conf` files are loaded, not
`.example` or `.disabled` files. A missing/unreadable configuration or invalid
TOML fails startup visibly.

**Mounted `.conf` files are now loaded**, unlike older native-enabled images
that mounted the directory without passing `--config-directory`. Review that
directory before upgrading, including files left there previously.

To customize selections, copy the relevant
`native/packaging/etc/telegraf-*.conf.example` into your host `telegraf.d/`
directory with a `.conf` extension and leave its automatic `ENABLE_*` flag
**false**. Alternatively, use `TELEGRAF_CONFIG_DIR` to mount another directory
or `TELEGRAF_CONFIG` to replace the main file. Do not concatenate snippets into
the main configuration and also enable the corresponding flags.

If an automatic addition overlaps a custom input, startup fails with the flag
and input name to resolve. Interface/device selections are handled conservatively:
automatic network/storage inputs are not combined with custom instances of the
same plugins. Keep those additions manual when using custom selections.
The shipped baseline temperature/powerstat inputs and their optional additions
are intentionally distinct and can coexist.

### Selection, export volume and identifiers

The primary example selects `eth*`/`en*` in both `net` and `ethtool`; the
virtual example selects `veth*`/`lxc*` in both, without entering another network
namespace. Names do not prove physical NICs: bridge-mode `eth0` is often virtual.
For bond, bridge, wireless or custom names, edit both interface lists in your
manual drop-ins. Avoid overlapping selections or summing traffic across layers.
On upgrade, a custom primary `interfaces = []` includes virtual links; narrow
it before adding the virtual traffic block. Existing virtual drop-ins are not
rewritten and remain driver-only until edited.

For storage, set `inputs.disk.mount_points` and `inputs.diskio.devices` in a
manual copy; RAID, partitions and device-mapper remain selectable. Defaults
retain all disk I/O layers except loop/ram, not a cross-layer aggregate.
The bundled example uses `skip_serial_number = true`, `device_tags = ["ID_MODEL"]`
and `tagexclude = ["serial", "wwid"]`. Review existing mounted copies separately:
they are **not** automatically made private. For explicit serial/WWID opt-in,
set `skip_serial_number = false`, remove those tags from `tagexclude`, and
optionally add `ID_SERIAL_SHORT` to `device_tags`, before the `tagdrop` table.
Disabling future export does not erase existing downstream data.

IRQs retain total and per-CPU fields (`cpu_as_tag = false`): D numbered IRQs on
C CPUs create roughly D * (C + 1) series per host. Add `fieldinclude = ["total"]`
before the example's `tagpass` table only if you deliberately want total-only
export. Dashboard row/device/interface limits never reduce exported series or
hide identifiers from the API; configure selection in the collector drop-ins.

### Applying changed configuration

`false` means **do not add the bundled configuration**; it does not remove a
user-configured input. You remain responsible for avoiding duplicates between
your own files, including wrappers around native executables, and for keeping
one agent, Prometheus output and HTTP listener.

The container snapshots drop-ins at startup; there is no hot reload. After
changing configuration, flags or mounts, recreate it:

```bash
docker compose up -d --no-build --force-recreate metrics-manager
```

An ordinary `docker compose restart` does not apply changed environment values.

## Compose deployment variants

There are exactly two runtime variants; both use the same image, native plugins,
configuration mounts and existing hardware access settings:

| Service | Profile | Network | Automatic network addition |
|---|---|---|---|
| `metrics-manager` | Default (no profile) | Bridge | Off |
| `metrics-manager-host-nic` | `host-nic-telemetry` | Host | On unless `ENABLE_NETWORK=false` |

The `test` profile remains a separate development test runner, not a third
deployment variant. There are no per-collector profiles.

**Choose one runtime service explicitly.** Enabling a profile alone does not
disable or stop the default service. Do not use an unqualified
`docker compose --profile host-nic-telemetry up`: it selects both variants.
Do not run the two collectors simultaneously against the same host; this can
duplicate measurements, share custom scripts, and cause port conflicts.

Start or keep the bridge variant:

```bash
docker compose up -d --build metrics-manager
```

Switch from bridge to host-NIC:

```bash
docker compose stop metrics-manager
docker compose --profile host-nic-telemetry \
  up -d --build --force-recreate metrics-manager-host-nic
docker compose --profile host-nic-telemetry logs --tail=100 metrics-manager-host-nic
```

Switch back:

```bash
docker compose --profile host-nic-telemetry stop metrics-manager-host-nic
docker compose up -d --no-build --force-recreate metrics-manager
```

`make up` and `make logs` still target the bridge service. Use the explicit
Compose commands for host-NIC. Changing a profile or stopping the other service
is not performed automatically.

An existing `.env` with `ENABLE_NETWORK=false` intentionally keeps network
collection off in either variant. Remove/comment that assignment to accept
per-variant defaults, or set `ENABLE_NETWORK=true`. The updated `.env.example`
leaves this flag commented. If you have custom `net`/`ethtool` inputs, keep the
flag false to avoid a startup conflict with the automatic input.
Virtual veth/lxc traffic and driver collection still requires
`ENABLE_NETWORK_VIRTUAL=true`.

### Ports, URLs and exposure

In bridge mode, `HOST_METRICS_PORT`, `HOST_TELEGRAF_PORT` and
`HOST_TELEGRAF_HTTP_PORT` only map host ports to fixed container ports
9090/9273/8186. This behavior is unchanged.

In host-NIC mode, the same variables set the **actual listener ports**.
Compose supplies matching API/Telegraf ports, ingestion and scraping URLs, and
the healthcheck uses the runtime API port. There is no `ports` mapping and no
Compose bridge network on this service.

For example, set three distinct unused ports in `.env`:

```bash
HOST_METRICS_PORT=19090
HOST_TELEGRAF_PORT=19273
HOST_TELEGRAF_HTTP_PORT=18186
```

Recreate the selected service, then verify:

```bash
curl -fsS http://127.0.0.1:19090/health
curl -fsS http://127.0.0.1:19273/metrics
```

Empty, malformed, out-of-range or duplicate internal listener ports fail
startup. Ports occupied by another service still cause bind errors: stop that
service or choose other ports, then inspect logs to confirm all listeners.
A custom main Telegraf configuration must use `${TELEGRAF_PORT}` and
`${TELEGRAF_HTTP_PORT}` (as the shipped file does), or explicitly match the
chosen ports. Mounted custom files are not rewritten.

**Host networking is Linux-only here and exposes the shipped listeners on all
host interfaces**, including the unauthenticated HTTP ingestion listener.
Docker publishing/loopback restrictions and bridge isolation do not apply.
Apply host firewall/access controls before starting; do not expose the service
to untrusted networks. Read-only `/sys` and `/run` mounts do not reduce this
network exposure. Docker port mappings also retain their existing all-interface
default in bridge mode.

## Turbostat: opt-in host binary

Defaults are `ENABLE_TURBOSTAT=false`, `TURBOSTAT_INTERVAL=5` seconds and
`TURBOSTAT_BIN=/usr/local/bin/turbostat` **inside the container**. The interval
must be positive integer seconds representable by Telegraf; paths must be
absolute, without spaces or shell expansion. Invalid settings fail startup
even when Turbostat is disabled.

On Ubuntu, locate the actual tool for the running kernel, not the
`/usr/bin/turbostat` wrapper that may depend on host-only paths:

```bash
export HOST_TURBOSTAT_BIN="/usr/lib/linux-tools/$(uname -r)/turbostat"
test -f "$HOST_TURBOSTAT_BIN" && test -x "$HOST_TURBOSTAT_BIN"
```

Install compatible tools first if unavailable. The path may change after a
kernel upgrade. Save this optional override as `compose.turbostat.yaml`:

```yaml
services:
  metrics-manager:
    environment:
      ENABLE_TURBOSTAT: "true"
      TURBOSTAT_BIN: /usr/local/bin/turbostat
      TURBOSTAT_INTERVAL: "${TURBOSTAT_INTERVAL-5}"
    volumes:
      - type: bind
        source: ${HOST_TURBOSTAT_BIN:?Set HOST_TURBOSTAT_BIN to the actual host binary}
        target: /usr/local/bin/turbostat
        read_only: true
        bind:
          create_host_path: false
```

```bash
docker compose -f compose.yaml -f compose.turbostat.yaml config --quiet
docker compose -f compose.yaml -f compose.turbostat.yaml \
  up -d --build --force-recreate metrics-manager
```

`HOST_TURBOSTAT_BIN` is only the host mount source; it is not executed by the
entrypoint. `TURBOSTAT_BIN` is the container path. Changing it also requires
changing the mount target. No Turbostat mount is required for the default stack,
and no per-collector Compose profile is introduced.

For the host-NIC variant, change the override's service key to
`metrics-manager-host-nic` and use that explicit service name together with
`--profile host-nic-telemetry` when starting it.

The entrypoint runs the mounted executable's `--version` **inside the container**
with a three-second timeout and checks read access to CPU 0's MSR interface.
Missing executables, incompatible libraries, timeouts or inaccessible MSRs emit
a warning and omit only the automatic Turbostat addition. Other inputs continue.
The container does not install tools or load host kernel modules automatically.

A missing bind source or another Docker mount error can stop container creation
**before the entrypoint runs**, so it cannot be converted into that warning.
The preflight also cannot guarantee support for every Turbostat counter or
prevent subsequent hardware/permission changes: inspect runtime logs.
Manually configured Turbostat inputs remain the user's responsibility and are
not removed or rewritten by the automatic preflight.

## Verification and hardware scope

```bash
docker compose logs --tail=100 metrics-manager
curl -fsS "http://127.0.0.1:${HOST_METRICS_PORT:-9090}/health"
curl -fsS "http://127.0.0.1:${HOST_TELEGRAF_PORT:-9273}/metrics" \
  | grep -E '^(powerstat_core_cpu_|temp_highres_|interrupts_|net_|ethtool_|diskio_|disk_|rapl_power_|turbostat_)'
```

Verify every selected family, not just the presence of any matching line.
Repeat after several seconds to check timestamps/counters. A healthy API alone
does not prove that Telegraf or every hardware input works.

- **Privileges:** the existing Compose deployment grants broad host access.
  Use only trusted images and configuration. MSR-based inputs require host MSR
  support and permissions; native DRAM bandwidth requires accessible IMC PMUs
  and perf-event permissions, not an external `perf` executable.
- **Network:** bridge-mode inputs observe the container's network namespace,
  not physical host NICs. Neither `pid: host` nor `/sys` changes that. Use the
  `host-nic-telemetry` variant for host NICs.
  Host networking requires resolving listener conflicts and exposure as above;
  Docker port remapping no longer applies. Review interface selection rather
  than adding physical/bridge/veth counters together.
- **Storage:** disk I/O counters and visible mounted filesystems are different
  scopes. Select the intended devices/mounts instead of summing physical disks,
  partitions and device-mapper layers. The current example requests model/serial
  tags and retains WWID where available; review those tags before exporting.
- **RAPL:** package power can appear without `psys`; that is not whole-board power.
- **Cardinality:** per-CPU IRQ and changing process/client labels increase
  exported series independently of the number of rows shown by a dashboard.

## Comparing with Python-reader images

Enabling equivalent hardware coverage does not guarantee identical names/labels:

| Python-reader name | Native-enabled image name |
|---|---|
| `dram_bw_{read,write,total}_gbps` | `memory_bandwidth_{read,write,total}_bytes_per_second` |
| `gpu_throttle_act_freq_mhz` | `gpu_frequency_act_freq_hz` |
| `gpu_throttle_driver_freq_mhz` | `gpu_frequency_cur_freq_hz` |
| `gpu_throttle_throttled` | `gpu_throttle_status` |
| `gpu_throttle_throttle_{pl1,pl2,prochot,thermal}` | `gpu_throttle_{pl1,pl2,prochot,thermal}` |

Native memory bandwidth exports **bytes/s**; convert it to decimal GB/s with
`GB/s = bytes/s / 1000000000`. Native GPU frequencies export Hz rather than MHz.
See the [2026.3.0 migration table](./native-metric-migration.md).
Sampling windows and data sources can
differ. Native GPU detail uses `gpu_id`/`driver`/`tile` rather than `card`/`gt`.
Adapt queries deliberately; do not assume exact series equivalence.
