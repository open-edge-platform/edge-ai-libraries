# Deploy with Helm Chart

This section describes how to deploy the Alert Agent Service on a Kubernetes cluster using a Helm chart.

## Prerequisites

Before you begin, ensure that the following prerequisites are met:

- A Kubernetes cluster (1.27 or later) is running and accessible.
- The cluster supports **dynamic provisioning of Persistent Volumes (PV)**. See [Kubernetes Documentation on Dynamic Volume Provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for details.
- `kubectl` is installed and configured to access your cluster. See [Install kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/).
- Helm 3.x is installed. See [Installing Helm](https://helm.sh/docs/intro/install/).
- For GPU-accelerated inference, at least one node in the cluster should have an Intel GPU. Alternatively, set `TARGET_DEVICE=CPU` for CPU-only deployments.

## Install the Helm Chart

### Option 1: Install from Docker Hub

1. Pull the chart from Docker Hub:

   ```bash
   helm pull oci://registry-1.docker.io/intel/alert-agent-service-chart --version <version-no>
   ```

   See the [Docker Hub tags page](https://hub.docker.com/r/intel/alert-agent-service-chart/tags) for the latest version number.

2. Extract the `.tgz` file:

   ```bash
   tar -xvf alert-agent-service-chart-<version-no>.tgz
   ```

3. Navigate to the extracted directory:

   ```bash
   cd alert-agent-service-chart
   ```

### Option 2: Install from Source

1. Clone the repository:

   ```bash
   # Clone the latest on the mainline
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, clone a specific release branch
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
   ```

2. Navigate to the chart directory:

   ```bash
   cd edge-ai-libraries/microservices/alert-services/alert-agent-service/chart
   ```

## Configure `values.yaml`

Edit the `values.yaml` file in the chart directory to match your environment. The following table summarises the key configuration parameters:

| Parameter | Description | Example Value | Required |
|-----------|-------------|---------------|----------|
| `image.repository` | Alert Agent Service image repository | `intel/alert-agent-service` | Yes |
| `image.tag` | Image tag | `latest` | Yes |
| `service.nodePort` | Kubernetes NodePort for the service API (30000–32767) | `30901` | Yes |
| `env.PORT` | Port the container listens on | `9001` | No |
| `env.LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` | No |
| `env.AGENT_MODE` | Enable ADK (LLM-reasoned) dispatch | `"true"` | No |
| `env.LLM_URL` | OpenAI-compatible LLM endpoint | `http://ovms-llm:9000/v3` | Yes (ADK mode) |
| `env.LLM_MODEL` | LLM model name | `OpenVINO/Phi-4-mini-instruct-int4-ov` | Yes (ADK mode) |
| `env.TARGET_DEVICE` | OVMS inference device (`GPU` or `CPU`) | `GPU` | No |
| `env.LLM_TIMEOUT` | LLM request timeout in seconds | `"10.0"` | No |
| `env.WEBHOOK_URL` | Default webhook endpoint | `https://your-hook.example.com` | No |
| `env.WEBHOOK_SECRET` | HMAC signing secret for webhooks | | No |
| `env.MQTT_BROKER` | MQTT broker hostname or IP | `mqtt.example.com` | No |
| `env.MQTT_PORT` | MQTT broker port | `"1883"` | No |
| `env.MQTT_USERNAME` | MQTT broker username | | No |
| `env.MQTT_PASSWORD` | MQTT broker password | | No |
| `env.MQTT_BASE_TOPIC` | Base MQTT topic prefix | `alerts` | No |
| `env.ACTION_WORKERS` | Concurrent tool execution worker pool size | `"2"` | No |
| `env.MCP_ENABLED` | Enable MCP server integration | `"true"` | No |
| `gpu.enabled` | Enable GPU resource requests | `true` | No |
| `gpu.key` | Kubernetes GPU node label key (from device plugin) | `gpu.intel.com/i915` | No |
| `affinity.enabled` | Enable node affinity | `false` | No |
| `affinity.key` | Affinity node label key | `kubernetes.io/hostname` | No |
| `affinity.value` | Affinity node label value | | No |

> **Note:** See the chart's `values.yaml` for the full list of configurable parameters.

### Example `values.yaml` snippet

```yaml
image:
  repository: intel/alert-agent-service
  tag: latest

service:
  type: NodePort
  nodePort: 30901

env:
  PORT: "9001"
  LOG_LEVEL: INFO
  AGENT_MODE: "true"
  TARGET_DEVICE: "GPU"    # set to "CPU" for Intel devices without discrete GPU
  LLM_URL: "http://ovms-llm:9000/v3"
  LLM_MODEL: "OpenVINO/Phi-4-mini-instruct-int4-ov"
  WEBHOOK_URL: "https://your-webhook.example.com/hook"
  MQTT_BROKER: "mqtt.example.com"
  MQTT_BASE_TOPIC: "alerts"
  MCP_ENABLED: "true"

gpu:
  enabled: true
  key: gpu.intel.com/i915

affinity:
  enabled: false
```

## Deploy the Helm Chart

```bash
helm install alert-agent-service . -n <your-namespace>
```

To override individual values at install time:

```bash
helm install alert-agent-service . -n <your-namespace> \
  --set env.WEBHOOK_URL=https://my-hook.example.com \
  --set service.nodePort=30901
```

## Verify the Deployment

Check that all pods are running:

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

Confirm the alert-agent-service pod reaches `Running` state and passes its health check:

```bash
kubectl describe pod -l app=alert-agent-service -n <your-namespace>
```

## Access the Service

Once deployed, access the Swagger UI through:

```
http://<node-ip>:<node-port>/docs
```

Verify the health endpoint:

```bash
curl http://<node-ip>:<node-port>/api/v1/health
```

## Upgrade the Deployment

```bash
helm upgrade alert-agent-service . -n <your-namespace>
```

## Uninstall the Helm Chart

```bash
helm uninstall alert-agent-service -n <your-namespace>
```

If a Persistent Volume Claim was created and is not removed automatically:

```bash
# List PVCs in the namespace
kubectl get pvc -n <your-namespace>

# Delete the PVC
kubectl delete pvc <pvc-name> -n <your-namespace>
```

## Troubleshooting

**Pod is stuck in `Pending` state:**

- Check for insufficient GPU or CPU resources:

  ```bash
  kubectl describe pod -l app=alert-agent-service -n <your-namespace>
  ```

- If `gpu.enabled=true` but no GPU node is available, set `gpu.enabled=false` and `env.TARGET_DEVICE=CPU`.

**Service is unreachable at the NodePort:**

- Confirm the NodePort is in the valid range (30000–32767).
- Check that the Kubernetes service was created: `kubectl get svc -n <your-namespace>`.

**View pod logs:**

```bash
kubectl logs -l app=alert-agent-service -n <your-namespace>
```

## Learn More

- [Get Started (Docker Compose)](../get-started.md)
- [System Requirements](./system-requirements.md)
