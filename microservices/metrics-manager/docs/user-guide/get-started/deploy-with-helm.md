<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Helm Deployment

The chart deploys Metrics Manager's native 2026.3.0 container as a Deployment
or DaemonSet. Docker Compose and the native Debian package remain separate
deployment options.

## Versions and prerequisites

| Artifact | Version |
|----------|---------|
| Local chart | `2026.3.0-helm` |
| Default application image | `intel/metrics-manager:2026.3.0` |
| Default RC image for validation | `intel/metrics-manager:2026.3.0-rc1` |
| Extended RC image for validation | `intel/metrics-manager:2026.3.0-extended-rc1` |

The chart version is independent of the application `VERSION` file.
`make helm-package` reads `Chart.yaml`; `make bump` does not update it.
These versions do not imply that the chart or stable image has been published.
Use the local chart and explicitly select the RC image until release approval.
The extended image adds inference libraries, not host kernel drivers or firmware.

Requirements:

- Helm 3.8+ for OCI chart support.
- Kubernetes 1.25+ and a matching `kubectl`. AppArmor is rendered as a legacy
  pod annotation before 1.30 and a native security-context field on 1.30+.
  Rendering compatibility is not proof of runtime compatibility on every version.
- Access to the selected image, or an explicitly configured image mirror.
- Prometheus Operator CRDs only if `serviceMonitor.enabled=true`.
- For hardware telemetry: supported Intel hardware, compatible host drivers and
  an administrator-approved namespace permitting the requested host access.

Run the examples below from `microservices/metrics-manager`.

## Restricted default profile

The default uses UID/GID 10001, a read-only root filesystem, dropped capabilities,
RuntimeDefault AppArmor/seccomp and no host namespaces or hostPath volumes.
The chart supplies a Telegraf configuration for CPU, memory, native CPU-frequency
and process metrics, custom metric scripts and HTTP ingestion/export. It does
not launch GPU/NPU/IMC/MSR collectors. CPU/memory/sysfs readings can describe the
node rather than cgroup limits; process visibility is pod-local. This is not a
full host telemetry profile.

Writable `emptyDir` volumes provide `/tmp` and, by default, `/app/custom-metrics`.
The qmassa FIFO uses `/tmp/qmassa.fifo` consistently. Telegraf configuration and
drop-ins remain read-only; the image prepares its active snapshot under `/tmp`.

```bash
helm lint ./helm/metrics-manager
helm template metrics-manager ./helm/metrics-manager \
  --namespace observability --set image.tag=2026.3.0-rc1

# Run only against your intended, approved cluster/context.
helm install metrics-manager ./helm/metrics-manager \
  --namespace observability --create-namespace \
  --set image.tag=2026.3.0-rc1 --wait --timeout 5m
```

`--wait` checks Kubernetes readiness, not the availability of every hardware
metric. Verify the data separately.

## Hardware telemetry profile

`hardware.telemetry.enabled=true` explicitly enables root, privileged access,
host PID visibility, Unconfined profiles and `/sys` plus `/run` host mounts.
It uses the image's native Telegraf configuration: CPU, GPU/NPU, top processes,
IMC memory bandwidth and package power/C-state collectors. Unsupported counters
remain unavailable; the chart cannot create hardware support.

```bash
helm install metrics-manager ./helm/metrics-manager \
  --namespace observability --create-namespace \
  --set image.tag=2026.3.0-rc1 \
  --set controller.kind=DaemonSet \
  --set hardware.telemetry.enabled=true \
  --wait --timeout 5m
```

Review host access with the cluster administrator. Do not relax namespace
admission, AppArmor, seccomp or host security settings merely to pass a test.
OpenShift deployments also need an appropriate administrator-managed SCC.

### Devices and optional executables

| Value | Behavior when hardware telemetry is enabled |
|-------|----------------------------------------------|
| `hardware.gpu.enabled` (default `true`) | Mount `/dev/dri`, add `hardware.gpuRenderGroup` and start qmassa |
| `hardware.npu.enabled` (default `false`) | Mount `/dev/accel` for NPU inference in the extended image; not needed for PMT telemetry |
| `hardware.msr.enabled` (default `false`) | Mount `/dev/cpu` for power/C-state and Turbostat MSR access |
| `hardware.turbostat.hostPath` (default empty) | Mount an operator-supplied executable read-only at `/usr/local/bin/turbostat` |

NPU/MSR directories must already exist on the target node. Prepare the host's
MSR module, NPU firmware and drivers separately; the chart does not install them.
On a CPU/NPU node without a GPU, set `hardware.gpu.enabled=false`; qmassa stays
disabled. The GPU reader in the hardware base configuration remains idle.
Privileged containers have broad device access: disabling a mount is not a
device-isolation guarantee for this profile.

Turbostat requires all of `hardware.telemetry.enabled=true`,
`hardware.msr.enabled=true`, `hardware.turbostat.hostPath` and
`config.enableTurbostat=true`. The mounted binary must run with the container's
libraries. The image logs a warning and skips it if its executable/MSR checks fail.

### Native optional collectors

All optional additions default to false. Use YAML booleans or the exact strings
`"true"`/`"false"` for these `config.enable*` values:

| Value | Environment variable |
|-------|----------------------|
| `config.enableRapl` | `ENABLE_RAPL` |
| `config.enablePowerstatExtra` | `ENABLE_POWERSTAT_EXTRA` |
| `config.enableTurbostat` | `ENABLE_TURBOSTAT` |
| `config.enableTemperature` | `ENABLE_TEMPERATURE` |
| `config.enableInterrupts` | `ENABLE_INTERRUPTS` |
| `config.enableNetwork` | `ENABLE_NETWORK` |
| `config.enableNetworkVirtual` | `ENABLE_NETWORK_VIRTUAL` |
| `config.enableStorage` | `ENABLE_STORAGE` |

`config.turbostatInterval` is positive integer seconds, default `5`.
For semantics, prerequisites, filtering and duplicate-input handling, see
[Native Docker Collectors](./native-docker-collectors.md); the chart uses the
same image entrypoint. Enabling an option does not grant host permissions.
Do not duplicate optional inputs in a custom Telegraf configuration.

### Host identity and networking

Hardware telemetry defaults `METRICS_MANAGER_HOSTNAME` to the Kubernetes node
name through the downward API. This keeps per-node time series stable across pod
restarts. `config.hostnameOverride` takes precedence; do not set one shared label
for a multi-node DaemonSet. The restricted profile keeps the pod hostname.

`pod.hostNetwork` remains false, even in the hardware profile.
For host NIC statistics explicitly set both `pod.hostNetwork=true` and
`config.enableNetwork=true`. Otherwise network metrics describe the pod network.
Host networking defaults DNS to `ClusterFirstWithHostNet`.

API, Prometheus and HTTP ingestion ports must be distinct values in 1..65535.
Changing `service.metricsPort`, `service.telegrafPort` or
`service.telegrafHttpPort` also changes the listeners and internal forwarding
URLs. With host networking, check for conflicts with existing host services and
other pods; do not schedule multiple instances using the same host ports.

Storage inputs see the container's mount namespace, not automatically every
host filesystem. No whole-host root filesystem mount is added by the chart.

## Custom configuration and storage

`telegraf.config` replaces the selected base configuration completely:

```bash
helm template metrics-manager ./helm/metrics-manager \
  --set image.tag=2026.3.0-rc1 \
  --set-file telegraf.config=./my-telegraf.conf
```

Preserve the Prometheus output and HTTP listener, including their environment
port substitutions, if using the API/SSE forwarding path.
Additional drop-ins can be supplied without replacing the base:

```yaml
telegraf:
  extraConfigs:
    application.conf: |
      [[inputs.prometheus]]
        urls = ["http://application:8080/metrics"]
```

These strings are not evaluated as Helm templates. Only simple `*.conf` filenames
are accepted. Changes to either ConfigMap trigger pod rollout using checksums.
Do not put secrets in values or ConfigMaps. `config.extraEnv` supports Kubernetes
environment entries, including `valueFrom` references to existing Secrets;
managed, legacy and duplicate variable names are rejected.

Custom metric scripts/files use `customMetrics.storage=emptyDir` by default.
For persistence, select `pvc` and either an existing claim or the chart-generated
claim (`size`, `storageClassName`, `accessModes`). For DaemonSets, design storage
access explicitly: one ReadWriteOnce claim generally cannot serve several nodes.
`storage=none` or `enabled=false` removes the writable custom-metrics volume;
with a read-only root filesystem, file uploads cannot persist.
HTTP metric ingestion remains available.

## Prometheus and terminal dashboard

Enable `serviceMonitor.enabled=true` after installing Prometheus Operator CRDs
and supplying labels matching your Prometheus instance's selector.
`serviceMonitor.namespace` may differ from the release namespace: the monitor
explicitly selects services in the release namespace. Ensure Prometheus watches
the monitor's namespace too.

The TUI runs outside the pod. Port-forward one selected pod's Prometheus port
and run your local dashboard:

```bash
kubectl -n observability get pods -l app.kubernetes.io/instance=metrics-manager
# Replace POD_NAME with a specific pod; keep this command running.
kubectl -n observability port-forward pod/POD_NAME 9273:9273
```

In another terminal, run `mm-tui -endpoint http://127.0.0.1:9273/metrics`.
For a DaemonSet select a specific pod/node rather than treating the Service as an
aggregated cluster metrics endpoint. See [Terminal Dashboard](./terminal-dashboard.md).

## Upgrade from 2026.2.0

This is a configuration and metric migration, not just an image-tag change.
Back up your explicit values (`helm get values`) and custom metric data first.
Treat exported values as potentially sensitive and store them securely.
Review the [native metric migration guide](./native-metric-migration.md):
queries and dashboards must use the native names and base units.

Recreate overrides against the new defaults. Removed keys fail rendering even
when set to false; they are not silently aliased:

| Removed `config` key | Migration |
|----------------------|-----------|
| `hardwareTelemetryEnabled` | Use `hardware.telemetry.enabled`; qmassa follows the hardware/GPU profile |
| `enableRaplPower` | Review baseline power/C-state metrics; `enableRapl` is a separate native energy/power collector, not a direct alias |
| `enableDramBw` | IMC bandwidth is part of the native hardware base; no external `perf` binary |
| `enableDiskIo` | Review `enableStorage` and device/filesystem filtering |
| `enableNetIo` | Review `enableNetwork`, `enableNetworkVirtual` and host networking |
| `enableTempStats` | Review `enableTemperature` |
| `enablePsysPower`, `enableGpuThrottle` | No equivalent old toggle; inspect available native metrics and unsupported fields |

Migrate legacy executable paths and fields in `telegraf.config` and drop-ins.
Old environment variable names in `config.extraEnv` also fail rendering.
Do not use `--reuse-values`, which can retain removed keys:

```bash
helm upgrade metrics-manager ./helm/metrics-manager \
  --namespace observability --reset-values \
  -f migrated-values.yaml --set image.tag=2026.3.0-rc1 \
  --wait --timeout 5m
```

Keep Deployment/DaemonSet kind, resource names, PVCs and selectors consistent
during an ordinary upgrade. Changing controller kind is a separate migration.
Changing the restricted profile may intentionally remove metrics that formerly
attempted unavailable privileged access.

## Verification and troubleshooting

1. Check rollout and pod events in the intended namespace.
2. Port-forward the selected pod's API and verify `/health`.
3. POST a custom metric and confirm it reaches the Prometheus endpoint.
4. Check expected native metric families and advancing timestamps for the selected
   node; healthy API status alone does not prove GPU/NPU/MSR/IMC access.
5. Inspect pod logs for configuration failures, unavailable counters or restarts.

For admission failures, ask the administrator whether the requested profile is
allowed; do not automatically relabel a shared namespace.
For missing Intel GPU metrics, check node scheduling, Intel `i915`/`xe` drivers,
`/dev/dri`, render-group permissions and qmassa logs. For missing NPU metrics,
check PMT and platform support. Device detection is not proof of inference:
see [OpenVINO smoke testing](./testing.md#openvino-accelerator-smoke-test).
AppArmor before 1.30 uses the legacy annotation automatically; do not force the
native field on an API server that does not support it.

## Packaging and publication

```bash
make helm-lint
make helm-template
make helm-package
# Creates dist/helm/metrics-manager-2026.3.0-helm.tgz
```

After validation and authorization, `make helm-push` publishes to
`oci://registry-1.docker.io/intel/metrics-manager`. Publishing the chart does not
publish either container variant. Once the chart and selected image are available,
replace the local chart path in install/upgrade commands with the OCI reference
and add `--version 2026.3.0-helm`.

To remove a release on the intended cluster:

```bash
helm uninstall metrics-manager --namespace observability
```

Back up custom metric files first and review generated PVC retention/deletion.
Existing claims are managed outside the chart.

## Supporting Resources

- [Get Started Guide](../get-started.md)
- [Environment Variables](./environment-variables.md)
- [Native Docker Collectors](./native-docker-collectors.md)
- [System Requirements](./system-requirements.md)
- [Troubleshooting](../troubleshooting.md)
