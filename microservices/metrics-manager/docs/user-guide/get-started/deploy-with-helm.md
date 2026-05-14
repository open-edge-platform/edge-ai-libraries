# Helm Deployment

The `metrics-manager` Helm chart deploys the same container image onto a Kubernetes cluster with host-level access required to scrape CPU / GPU / NPU telemetry from the node.

The chart is published to the **same OCI repository as the container image**.

| Artifact      | OCI Reference                                                                |
|---------------|------------------------------------------------------------------------------|
| Image         | `registry-1.docker.io/intel/metrics-manager:2026.1.0`                      |
| Helm chart    | `oci://registry-1.docker.io/intel/metrics-manager:2026.1.0-helm`            |

## Prerequisites

| Tool       | Minimum | Notes                                                                       |
|------------|---------|-----------------------------------------------------------------------------|
| Helm       | 3.8     | Required for OCI registries                                                |
| Kubernetes | 1.25    | Older clusters use the legacy AppArmor pod annotation. The chart auto-detects. 1.30+ uses the native `appArmorProfile` field. |
| kubectl    | matching K8s | For cluster interaction                                                      |

**Security Requirements:**

The pod runs **privileged** with `hostPID: true`, mounts host paths (`/sys`, `/run`, `/dev/dri`), and disables AppArmor / seccomp confinement so it can read GPU/NPU sysfs nodes. 

**PodSecurityAdmission must allow the `privileged` profile** in the target namespace:

```bash
kubectl label namespace observability \
  pod-security.kubernetes.io/enforce=privileged --overwrite
```

**For Kubernetes < 1.30:**

The chart uses the native `appArmorProfile` field. On older clusters either upgrade or fork the chart to use the legacy `container.apparmor.security.beta.kubernetes.io/<name>` annotation.

## Install

### Basic Installation

```bash
helm install metrics-manager \
  oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --namespace observability --create-namespace
```

### View Rendered Manifests (Without Installing)

```bash
helm template metrics-manager \
  oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm
```

### Pull for Offline / Air-Gapped Deployments

```bash
helm pull oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm
# -> metrics-manager-2026.1.0-helm.tgz
```

### Show Default Values

```bash
helm show values oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm
```

---

## Common Configurations

### Deploy on Every Node (DaemonSet)

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --set controller.kind=DaemonSet
```

### CPU / NPU only host (no GPU)

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --set hardware.gpu.enabled=false
```

### Stable Hostname Label Across Pod Restarts

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --set config.hostnameOverride=lab-node-42
```

### Persist `/app/custom-metrics` to a PersistentVolume

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --set customMetrics.storage=pvc \
  --set customMetrics.size=1Gi \
  --set customMetrics.storageClassName=standard
```

### Override the Telegraf Configuration

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --set-file telegraf.config=./my-telegraf.conf
```

### Expose to Prometheus Operator (ServiceMonitor)

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --set serviceMonitor.enabled=true \
  --set serviceMonitor.labels.release=prometheus
```

This creates a `ServiceMonitor` that Prometheus Operator can scrape via the `:9273` Prometheus endpoint.

---

## Upgrade / Uninstall

### Upgrade to a Newer Version

```bash
helm upgrade metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --reuse-values
```

### Uninstall

```bash
helm uninstall metrics-manager --namespace observability
```

---

## Verification

### Check Deployment Status

```bash
kubectl -n observability get pods -l app.kubernetes.io/name=metrics-manager
```

### Port-Forward to Access the API

```bash
kubectl -n observability port-forward svc/metrics-manager 9090:9090 &
curl -s http://localhost:9090/health
```

### Access Telegraf Prometheus Endpoint

```bash
kubectl -n observability port-forward svc/metrics-manager 9273:9273 &
curl -s http://localhost:9273/metrics | head
```

### View Logs

```bash
kubectl -n observability logs -f deployment/metrics-manager
```

---

## Troubleshooting

### Pod Stuck in `CreateContainerConfigError`

**Cause**: Namespace rejects privileged pods.

**Solution**: Label the namespace:

```bash
kubectl label namespace observability \
  pod-security.kubernetes.io/enforce=privileged --overwrite
```

### Empty GPU Metrics

**Cause**: GPU not enabled or not available on the node.

**Solution**: 

```bash
# Check if GPU is available on the node
kubectl describe node <node-name> | grep nvidia.com

# If no GPU, disable GPU in the chart
helm install metrics-manager ... \
  --set hardware.gpu.enabled=false
```

### AppArmor Errors on Kubernetes < 1.30

**Cause**: Chart uses the native `appArmorProfile` field, which is not supported on older clusters.

**Solution**: Either upgrade Kubernetes or fork the chart to use the legacy annotation.

### OpenShift Compatibility

`hostPID: true` and `privileged: true` require a `SecurityContextConstraint` such as `privileged` bound to the chart's ServiceAccount:

```bash
oc adm policy add-scc-to-user privileged -z metrics-manager
```

### ServiceMonitor Not Picked Up by Prometheus

**Cause**: Prometheus Operator not configured or label selector mismatch.

**Solution**: Verify Prometheus Operator is installed:

```bash
kubectl get crd servicemonitors.monitoring.coreos.com
```

Confirm the ServiceMonitor labels match the Prometheus instance's `serviceMonitorSelector`:

```bash
kubectl get prometheus -o yaml | grep serviceMonitorSelector
```

Update the Helm install to match:

```bash
helm install metrics-manager ... \
  --set serviceMonitor.labels.release=<your-prometheus-label>
```

---

## Advanced: Custom Values File

Create a `values.yaml` file with your custom configuration:

```yaml
# my-values.yaml
controller:
  kind: DaemonSet
  replicas: 1

hardware:
  gpu:
    enabled: true
  npu:
    enabled: true

config:
  hostnameOverride: lab-node-42
  loglevel: DEBUG

customMetrics:
  storage: pvc
  size: 5Gi
  storageClassName: fast-ssd

serviceMonitor:
  enabled: true
  labels:
    release: kube-prometheus-stack
```

Install with custom values:

```bash
helm install metrics-manager oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  -f my-values.yaml
```

## Supporting Resources

- [Get Started Guide](../get-started.md)
- [Configuration Guide](./environment-variables.md)
- [System Requirements](./system-requirements.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
