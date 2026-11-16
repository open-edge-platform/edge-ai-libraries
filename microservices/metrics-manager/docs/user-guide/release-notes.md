# Release Notes: Metrics Manager

## Version 2026.3.0

**Release Date:** TBD

**Changed (breaking):**

- **Native Metric Names and Base Units**: Native CPU, GPU and NPU collectors now use explicit unit-bearing field names and export frequencies in Hz, memory sizes in bytes, bandwidth in bytes/second, power in W and temperature in degrees Celsius. Examples include `cpu_frequency_avg_frequency_hz`, `gpu_frequency_cur_freq_hz`, `gpu_power_power_w`, `gpu_temperature_temperature_c`, `npu_frequency_hz`, `npu_bandwidth_bytes_per_second` and `npu_memory_bytes`. GPU fan speed is now `gpu_fan_speed_hz` in rotations/second instead of RPM. Old names are not emitted as aliases. Update PromQL queries, recording and alert rules, dashboards and custom ingestion clients together with the collectors; rescale thresholds and historical values where required. Standard Telegraf input metrics are not part of this rename. See the [Native Metric Migration Guide](./get-started/native-metric-migration.md) for the complete mapping and upgrade checklist. Historical NPU frequency readings from uncorrected builds require an additional scale correction, and Arrow Lake readings also require the corrected PLL formula; a rename alone is insufficient.
- **Native Collectors Replace Bundled Python and Shell Readers**: The bundled `npu_monitor_tool.py`, `npu_reader.py`, `qmassa_reader.py` and `read_cpu_freq.sh` have been removed. Telegraf now runs native Go plugins through `inputs.execd`. Custom Telegraf configurations must migrate executable paths and metric fields. The former NPU monitor console/CSV interface is no longer shipped; use the native telemetry endpoint and, for interactive inspection, the standalone terminal dashboard.
- **Collector Configuration Interface**: The native image uses `ENABLE_RAPL`, `ENABLE_POWERSTAT_EXTRA`, `ENABLE_TURBOSTAT`, `ENABLE_TEMPERATURE`, `ENABLE_INTERRUPTS`, `ENABLE_NETWORK`, `ENABLE_NETWORK_VIRTUAL` and `ENABLE_STORAGE`. Legacy names such as `ENABLE_RAPL_POWER`, `ENABLE_PSYS_POWER`, `ENABLE_DRAM_BW`, `ENABLE_DISK_IO`, `ENABLE_NET_IO`, `ENABLE_TEMP_STATS` and `ENABLE_GPU_THROTTLE` are not aliases. Docker flags accept only the exact lowercase strings `true` and `false`; other values fail startup. The shipped hardware configuration already includes process, memory-bandwidth and package-power/C-state collection, subject to hardware support and permissions. Disabling optional additions does not disable this baseline or remove user-configured inputs. See [Native Docker Collectors](./get-started/native-docker-collectors.md).
- **Helm Values Migration**: The chart uses `hardware.telemetry.enabled` for the explicit hardware profile and the native `config.enable*` options for additional collectors. Removed legacy collector keys, including `config.hardwareTelemetryEnabled`, are rejected rather than silently ignored. Migrate saved values and custom Telegraf configuration before upgrading; do not use `--reuse-values`. The restricted default profile no longer attempts privileged GPU/NPU/IMC/MSR collection. See [Helm Deployment](./get-started/deploy-with-helm.md).
- **Latest Metrics Preserve Distinct Series**: Latest custom metrics are now identified by both metric name and tags rather than by name alone. API latest-result keys for tagged metrics use the `name{tag=value,...}` form, and the Prometheus export retains separate tagged series instead of dropping all but one. Consumers that index latest results by bare metric name must account for the series keys.

**New:**

- **Native Hardware and Process Collectors**: Go plugins provide CPU frequency and core-class telemetry, Intel GPU and NPU telemetry, top CPU/memory processes, integrated memory-controller bandwidth and optional RAPL package/platform power. CPU telemetry includes P-core, E-core and low-power E-core breakdowns where supported. GPU telemetry includes client/process information and additional frequency/throttle data. The same collector binaries are used in the Docker image and the native Debian package.
- **Bare-Metal Debian Package**: An amd64 `.deb` packages telemetry collectors, Telegraf, qmassa, the terminal dashboard and systemd services for supported Debian/Ubuntu hosts with glibc 2.34 or newer. Docker is used to build the package but is not required on the target host. The package covers telemetry and the dashboard only; REST API and SSE remain container-only. See [Bare-Metal Package](./get-started/bare-metal-package.md).
- **Terminal Dashboard (`mm-tui`)**: A standalone, read-only terminal interface provides Overview, Trends, Details and Alerts views with bounded in-memory history, hardware charts, CPU/GPU process tables, configurable thresholds and network/storage panels when the corresponding metrics are available. It reads Telegraf's Prometheus endpoint and runs independently of the REST API. The dashboard is included in the Debian package and can be built separately; the Docker service image supplies telemetry, not the interactive dashboard. See [Terminal Dashboard](./get-started/terminal-dashboard.md).
- **Additional Telemetry Inputs**: Native Docker and Helm deployments support opt-in RAPL package/platform power, extra per-CPU powerstat frequency/temperature fields, Turbostat diagnostics, high-frequency temperature statistics, device interrupts, primary and virtual network interfaces, and filesystem/disk I/O. These additions are off by default in the standard bridge deployment. Turbostat requires an explicitly supplied executable and usable MSR access.
- **Host-NIC Compose Profile**: The opt-in `metrics-manager-host-nic` service uses the `host-nic-telemetry` profile and host networking. It enables `ENABLE_NETWORK` by default unless explicitly set to `false`; the standard service retains bridge networking. Select one runtime service explicitly, since enabling the profile does not stop the default service. Host-network listeners use the configured host ports.
- **Additional NPU Fields**: `npu_power_state` reports the PCI power state as D0=0, D1=1, D2=2, D3hot=3, D3cold=4 or unknown=-1. `npu_frequency_max_hz` reports the driver's frequency ceiling when available. These fields are part of the native NPU collector, not optional `ENABLE_*` additions.
- **OTLP Histogram Summaries and Temporality**: OTLP JSON ingestion now stores histogram `count` and available finite `sum`, `min` and `max` values, plus `avg` when a sum is present and count is positive. Sum and histogram points preserve declared aggregation temporality as a `delta` or `cumulative` tag. Histogram bucket counts are not retained, and unspecified temporality is not inferred. Numeric and boolean OTLP attributes are preserved as tag strings. See the [API Reference](./api-reference.md).

**Improved:**

- **Telegraf 1.40.3 and Shared Component Versions**: Updated Telegraf from 1.39.3 to 1.40.3 and replaced the locally patched source build with the official upstream binary, verified against a pinned SHA-256 digest. The Docker image and Debian package use the same Telegraf and collector binaries. Third-party binary/toolchain versions and checksums are centralized in `versions.env`, with checks for Dockerfile version drift. The native Go toolchain does not rebuild or patch dependencies inside the official Telegraf binary.
- **Extended Image Accelerator Libraries**: The optional `INSTALL_OPENVINO=true` build now includes checksum-pinned Intel OpenCL/Level Zero GPU and NPU userspace libraries alongside OpenVINO and VAAPI tooling. Host kernel drivers and firmware must still be provided separately. The default image does not include this optional inference stack.
- **Native DRAM Bandwidth Collection**: The memory-bandwidth collector accesses performance counters directly through `perf_event_open`; no external `perf` executable or `INSTALL_PERF` image variant is required. Collection uses the representative CPUs exposed by each IMC PMU to cover multiple dies/sockets and avoids emitting partial host totals on controller errors. Host perf permissions and supported counters remain required.
- **Telegraf Drop-In Selection**: The entrypoint validates the main configuration and mounted `telegraf.d/**/*.conf` files, checks enabled automatic additions for conflicts, and snapshots selected drop-ins into a fresh private temporary directory passed through `--config-directory`. Source configuration is not rewritten, and disabled automatic additions do not leave stale generated files behind. Mounted user `.conf` files are loaded even when all optional flags are false. Invalid configuration or conflicting automatic/custom inputs fails startup with a diagnostic. Changes require container recreation; there is no hot reload.
- **Native Helm Deployment Profiles**: The default chart runs as a non-root user with a read-only root filesystem, dropped capabilities and a restricted Telegraf configuration for CPU, memory, native CPU-frequency/process collection and custom-metric ingestion/export. The explicit hardware profile enables privileged host access and native hardware telemetry, with separate options for GPU/NPU/MSR mounts and Turbostat. Hardware mode defaults the host label to the Kubernetes node name; host networking remains a separate opt-in. Additional Telegraf ConfigMaps are supported, and configuration checksums trigger pod rollouts. Port values are validated and propagated to listeners and internal forwarding URLs. Chart versioning is independent of application version bumps.
- **Dependencies and Validation**: Updated Python runtime and development dependencies and expanded tests for native collectors, metric units, TUI behavior, OTLP ingestion, series identity, Docker configuration, Helm rendering, packaging and version consistency. Optional accelerator smoke testing is documented separately from device discovery and telemetry checks.

**Fixed:**

- **NPU Frequency Calculation**: Frequency is decoded directly in Hz using the `intel_vpu` buttress formulas: MTL/ARL use `ratio * 50e6 * 2 / 3`, while LNL/PTL use `ratio * 50e6 / 2`. This corrects the former MHz-valued export and Arrow Lake's 25% under-reporting without truncating to whole MHz. The exported metric is now `npu_frequency_hz`.
- **NPU Bandwidth Sampling**: `npu_bandwidth_bytes_per_second` divides the counter delta by the actual elapsed sampling interval, removing polling-jitter distortion. A single wrap of the underlying 32-bit counter is corrected. Counter resets and multiple wraps within one interval cannot be reliably distinguished.
- **Unavailable NPU Measurements**: Utilization and memory fields are omitted when their driver attributes are absent or cannot be read, rather than emitting fake `0` or `-1` values. Memory availability is detected from `npu_memory_utilization` instead of being restricted to Panther Lake and newer platforms; readable values are exported as `npu_memory_bytes` without rounding through MiB. Consumers must distinguish missing measurements from measured zero.
- **Metric Series and Timestamps**: Series-key escaping prevents collisions involving label separators. API and SSE parsing handle Prometheus timestamp objects and preserve an explicit zero timestamp instead of replacing it with the current time.
- **Shutdown and Configuration Handling**: Background Telegraf HTTP push tasks are tracked and cancelled before the HTTP session closes, and application cleanup runs through the lifespan shutdown path even on errors. Malformed JSON-array `CORS_ORIGINS` values now produce an explicit validation error. Health checks honor the configured API port.
- **Optional Collector Availability**: Automatically selected Turbostat collection is skipped with a warning when the executable cannot run or CPU 0 MSR access is unavailable. Unsupported native hardware collection reports diagnostics rather than fabricating measurements.

## Version 2026.2.0

**Release Date:** September 9, 2026

**New:**

- **Platform & Device Capabilities API**: New `GET /api/v1/capabilities` endpoint returns a structured snapshot of the host platform and its compute devices (CPU, GPU, NPU, memory, storage, media codecs). Two detail profiles are available via `?profile=`: `minimal` (default) for a high-level summary and `expanded` for a full technical inventory. Enables workload placement without shelling out to platform-specific tools.
- **Software Capabilities Export**: The capabilities snapshot reports the software stack on each detected compute device (drivers, runtimes, supported precisions, media codecs), enabling capability-aware model and pipeline placement across heterogeneous edge fleets.
- **Hardware Discovery Tooling Bundled**: The runtime image ships `dmidecode`, `pciutils` (`lspci`), `util-linux` (`lsblk`), and `hwinfo` for out-of-the-box capability detection with no extra host packages or sidecar containers.
- **Optional OpenVINO™ Build Variant**: New `openvino` extra in `pyproject.toml` and `INSTALL_OPENVINO` Docker build argument. When enabled, adds `vainfo` and `intel-media-va-driver` for VAAPI codec detection, while keeping the default image lean.

**Improved:**

- **Telegraf 1.38.4 Built from Source**: Compiled from the upstream `v1.38.4` tag using a digest-pinned Go 1.26.4 toolchain. Patches vulnerable bundled dependencies (`rclone` → 1.73.5, `go-billy` → 5.9.0), remediating known CVEs and producing a fully reproducible build.
- **qmassa 2.1.0 and qmmd 0.2.0**: Installed with `cargo install --locked --git … --tag …` from upstream instead of crates.io, preventing build failures from yanked versions and bringing the latest Intel® GPU telemetry improvements.
- **Security Hardening**: Several attack-surface reductions in the production image: `supervisor` installed via `pip` (4.3.0), `perl-base` purged, `curl` removed (healthcheck replaced with a Python one-liner), and supervisord's Unix socket configured with an explicit user/password placeholder.
- **Build and Developer Loop**: Go module and build caches added to the `Dockerfile`, with leaner service startup/shutdown in `Makefile` and `compose.yaml` for shorter `make test` and `docker compose up/down` turnaround.
- **Documentation**: Capabilities endpoint documented in the API reference, updated system requirements, corrected links and release-branch references, improved cross-linking, and an expanded troubleshooting section.
- **Test Coverage**: New tests for the capabilities endpoint and response model, plus additional route and application wiring tests.

## Version 2026.1.0

**Release Date:** May 11, 2026

**New:**

- **Server-Sent Events (SSE) Streaming** — New `/metrics/stream` endpoint streams all metrics (system + custom) in real-time via SSE. Each connected client polls the Telegraf Prometheus endpoint independently. Browser requests receive a live HTML table; SSE clients receive raw event stream
  - **Impact**: Dashboards can now consume metrics without polling, enabling real-time visualizations. Replaces the old WebSocket relay model

- **Multiple Input Formats** — Accept custom metrics in four formats without code changes:
  - JSON Batch (`POST /api/v1/metrics`) — multiple metrics with multiple fields
  - Simple JSON (`POST /api/v1/metrics/simple`) — single metric, simplest format
  - InfluxDB Line Protocol (`POST /api/v1/metrics/influx`) — standard Influx format
  - OpenTelemetry (OTLP) (`POST /api/v1/metrics/otlp`) — CNCF standard format
  - **Impact**: Any monitoring system can integrate without client library or format conversion

- **Intel NPU Telemetry** — Bundled `npu_reader.py` script collects metrics from Intel NPU:
  - Power draw (watts)
  - Frequency, temperature, utilization
  - Memory usage, bandwidth, tile configuration
  - Supported on Meteor Lake (MTL), Arrow Lake (ARL), Lunar Lake (LNL), Panther Lake (PTL)
  - **Impact**: Full hardware observability for edge AI applications on Intel platforms

- **Custom Metrics Scripts** — Drop executable scripts into `/app/custom-metrics/` (shell or Python). Telegraf runs them every 10 seconds and publishes metrics automatically
  - **Impact**: No REST API calls needed for custom metrics. Simplest way to add application-specific metrics

- **Docker Compose & Kubernetes** — Production-ready `compose.yaml` and Helm chart included
  - Docker Compose for standalone deployments
  - Helm chart published to OCI registry (`oci://registry-1.docker.io/intel/metrics-manager:2026.1.0-helm`)
  - **Impact**: Deploy in 3 commands on Docker or Kubernetes

- **Comprehensive API Reference** — Health checks, statistics, detailed endpoint documentation
  - Basic health (`GET /health`)
  - Detailed health with store statistics (`GET /api/health`)
  - Service statistics (`GET /api/v1/stats`)
  - **Impact**: Easy to integrate into monitoring systems and dashboards

**Improved:**

- **Debounced Persistence** — Custom metrics are persisted to Telegraf with configurable debounce (default 100ms). Prevents HTTP bottleneck when ingesting high-frequency metrics
  - **Impact**: Support for 1000+ metrics per second without API latency spikes

- **Memory Protection** — Automatic eviction of oldest metrics when in-memory limit is reached (default 100k metrics)
  - **Impact**: Metrics service can not run out of memory even under sustained high ingestion

- **Structured Logging** — JSON-formatted logs by default (with human-readable text option for development)
  - **Impact**: Easy integration with log aggregators (ELK, Datadog, etc.)

- **Rate Limiting** — Per-IP token bucket rate limiting (default 1000 requests/minute per IP)
  - **Impact**: Protection against accidental/malicious floods; health and statistics endpoints exempt

- **Correlation IDs** — Every request gets a correlation ID (auto-generated UUID or from `X-Correlation-ID` header) for distributed tracing
  - **Impact**: Easy to track requests through logs and multiple services

- **GZIP Compression** — Automatic compression for HTTP responses >1 KB
  - **Impact**: Reduced bandwidth for metrics streaming (especially important for SSE)

**Known Issues:**

None at this release. See GitHub issues for feature requests and discussions.

## Version 2026.0.1

**Release Date:** May 5, 2026

**Fixed:**

- **SSE Stream HTML UI** — Browser requests to `/metrics/stream` now receive an HTML page with an in-place updated metrics table (previously showed raw SSE stream)
  - **Impact**: Live dashboard experience in browser without client-side framework

- **Content Negotiation** — `/metrics/stream` auto-detects client type:
  - Browser (`Accept: text/html`) → HTML page
  - SSE client (`Accept: text/event-stream`) → raw stream
  - **Impact**: Single endpoint works for both browsers and programmatic clients

## Version 2026.0.0

**Release Date:** April 1, 2026

**New:**

- **Initial Release** — Metrics Manager with:
  - Telegraf-based system metrics collection (CPU, RAM, temperature, GPU, NPU)
  - FastAPI REST interface for custom metrics ingestion
  - In-memory metrics store with configurable retention
  - Prometheus-compatible output (`GET /metrics`, `:9273/metrics`)
  - Real-time SSE streaming (`GET /metrics/stream`)

## Versions and Dependencies

### Current Image

- Intel® Metrics Manager **2026.2.0**
- Telegraf **1.39.3** (system metrics agent)
- qmassa **1.3.1** (Intel® GPU telemetry via named pipe)
- qmmd **0.1.1** _(optional)_ — Lightweight Prometheus GPU exporter (bundled but **not started by default**; use only if you need a separate GPU metrics port)
- Intel® NPU telemetry via bundled `npu_monitor_tool` / `npu_reader`
- Python **3.12** runtime + FastAPI service
- supervisord process supervisor

> [!NOTE]
> **Note on qmmd:** The default Metrics Manager already collects GPU metrics via `qmassa_reader.py` and Telegraf. Enable qmmd only if you need a standalone Prometheus exporter on a separate port. See [Environment Variables](./get-started/environment-variables.md#optional-components) for details.

## Support Matrix

| Component    | Version | Support                                |
| ------------ | ------- | -------------------------------------- |
| Docker       | 24.0+   | Required                               |
| Kubernetes   | 1.25+   | Via Helm chart                         |
| Python       | 3.12    | Included in image                      |
| Linux Kernel | 5.4+    | Required for system metrics collection |

## Migration Guide

### From Version 2026.0.x to 2026.1.0

No breaking changes. All existing endpoints remain compatible.

**What changed:**

- SSE stream now returns flat metric format instead of measurement/field split
- Content negotiation added for `/metrics/stream` (HTML vs SSE)

**Migration steps:**

1. Pull new image: `docker pull intel/metrics-manager:2026.1.0`
2. Update `docker-compose.yaml` or Helm values if pinning version
3. Restart: `docker compose up -d`
4. No data migration needed (in-memory store)

## Supporting Resources

- [Get Started Guide](./get-started.md)
- [API Reference](./api-reference.md)
- [Environment Variables](./get-started/environment-variables.md)
- [How It Works](./how-it-works.md)
- [Troubleshooting](./troubleshooting.md)

## Disclaimer

This container image is intended for demo and evaluation purposes and is not hardened for production deployments out of the box. To receive expanded security maintenance from Canonical on the Python/Debian base layer, you may follow the relevant Ubuntu Pro / vendor guidance and rebuild the image from the published `Dockerfile`.

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

The Metrics Manager source code is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).

### Third-Party Software

- **Telegraf** — Open source project developed by InfluxData and licensed under the MIT license. See <https://github.com/influxdata/telegraf/blob/master/LICENSE>
- **qmassa** — Open source Intel® GPU monitoring tool licensed under the MIT license. See <https://github.com/ulissesf/qmassa>
- **qmmd** — Prometheus exporter for Intel® GPUs, published on crates.io under the same project
- **Prometheus & OpenTelemetry** — CNCF projects. See <https://prometheus.io/> and <https://opentelemetry.io/> for license terms

You are solely responsible for determining if your use of these tools requires any additional licenses.

## Legal Information

Intel technologies' features and benefits depend on system configuration and may require enabled hardware, software, or service activation. Learn more at intel.com, or from the OEM or retailer.

No computer system can be absolutely secure. Intel does not assume any liability for lost or stolen data or systems or any damages resulting from such losses.

You may not use or facilitate the use of this document in connection with any infringement or other legal analysis concerning Intel products described herein. You agree to grant Intel a non-exclusive, royalty-free license to any patent claim thereafter drafted which includes subject matter disclosed herein.

No license (express or implied, by estoppel or otherwise) to any intellectual property rights is granted by this document.

Intel disclaims all express and implied warranties, including without limitation, the implied warranties of merchantability, fitness for a particular purpose, and non-infringement, as well as any warranty arising from course of performance, course of dealing, or usage in trade.

This document contains information on products, services and/or processes in development. All information provided here is subject to change without notice. Contact your Intel representative to obtain the latest forecast, schedule, specifications and roadmaps.

The products and services described may contain defects or errors which may cause deviations from published specifications. Current characterized errata are available on request.

Intel, the Intel logo, and Xeon are trademarks of Intel Corporation in the U.S. and/or other countries.

\*Other names and brands may be claimed as the property of others.

© 2025-2026 Intel Corporation
