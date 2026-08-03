# Deploy with Helm Chart

This section shows how to deploy Model Download using Helm chart.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:

- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. See [Kubernetes Documentation on Dynamic Volume Provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for details.
- Install `kubectl` on your system. See [Kubernetes Documentation on Tool Installation](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm chart installed on your system: See [Installing Helm](https://helm.sh/docs/intro/install/).

## Install Helm Chart from Docker Hub or from Source

To deploy with Helm chart, you can either install the chart from Docker hub or from source.

### Option 1: Install from Docker Hub

1. Pull the specific chart

   Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/model-download-chart):

   ```bash
   helm pull oci://registry-1.docker.io/intel/model-download-chart --version <version-no>
   ```

   See the [Docker hub's tags page](https://hub.docker.com/r/intel/model-download-chart/tags) for details on the latest version number to use for the application.

2. Extract the `.tgz` file

   ```bash
   tar -xvf model-download-chart-<version-no>.tgz
   ```

3. This will create a directory named `model-download-chart`, containing the chart files. Navigate to the extracted directory:

   ```bash
   cd model-download-chart
   ```

### Option 2: Install from Source

1. Clone the repository containing the Helm chart:

   ```bash
   # Clone the latest on the mainline
     git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, clone a specific release branch
     git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
   ```

2. Navigate to the chart directory:

   ```bash
   cd edge-ai-libraries/microservices/model-download/chart
   ```

## Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Set your proxy settings as required.

The following is a summary of key configuration options available in the `values.yaml` file:

| Parameter                      | Description                                                                                                                                                                   | Example Value                | Required                 |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ------------------------ |
| `env.HUGGINGFACEHUB_API_TOKEN` | Hugging Face access token                                                                                                                                                     | `hf_xxx`                     | Yes                      |
| `env.MAX_UPLOAD_SIZE_MB`       | Maximum allowed upload ZIP size in MB                                                                                                                                         | `500`                        | No                       |
| `env.UPLOAD_CHUNK_SIZE_KB`     | Chunk size for streaming file uploads in KB (larger improves throughput, smaller reduces memory for concurrent uploads)                                                       | `8`                          | No                       |
| `env.EXTERNAL_SOURCES_URL_ALLOWLIST` | Comma-separated `host/path` prefixes allowed for the `remote-url` hub. When set, it replaces the default allowlist defined in `src/plugins/external_sources/sources.yaml` | `github.com/open-edge-platform/edge-ai-resources/` | No                       |
| `env.GETI_WORKSPACE_ID`        | Geti™ workspace ID                                                                                                                                                             |                              | Yes, For Geti™ connection |
| `env.GETI_HOST`                | Geti™ connection host address                                                                                                                                                  |                              | Yes, For Geti™ connection |
| `env.GETI_TOKEN`               | Geti™ Personal Access token                                                                                                                                                    |                              | Yes, For Geti™ connection |
| `env.GETI_SERVER_API_VERSION`  | Geti™ API version                                                                                                                                                              | `v1`                         | Yes, For Geti™ connection |
| `env.GETI_SERVER_SSL_VERIFY`   | Enables SSL certificate validation for HTTPS/HTTP Geti™ hosts                                                                                                                  | `False`                      | Yes, For Geti™ connection |
| `service.nodePort`             | Sets the static port (in the 30000–32767 range)                                                                                                                               | 32000                        | Yes                      |
| `env.ENABLED_PLUGINS`          | Comma-separated list of plugins to enable (e.g., `huggingface,ollama,ultralytics,pipeline-zoo-models,remote-url,omz,openvino,geti,hls`) or `all` to enable all available plugins | `all`                        | Yes                      |
| `startupConfig.enabled`        | Creates and mounts a startup-model ConfigMap and schedules its models asynchronously                                                                                         | `false`                      | No                       |
| `startupConfig.config`         | Startup configuration containing the default `download_path`, `parallel_downloads`, and `models` list                                                                        | See `values.yaml`            | When enabled             |
| `image.repository`             | image repository url                                                                                                                                                          | intel/model-download         | Yes                      |
| `image.tag`                    | latest image tag                                                                                                                                                              | latest                       | Yes                      |
| `gpu.enabled`                  | For model download deployed on GPU                                                                                                                                            | false                        |
| `gpu.key`                      | Label assigned to the GPU node on kubernetes cluster by the device plugin example- gpu.intel.com/i915, gpu.intel.com/xe. Identify by running kubectl describe node <gpu-node> | `<your-node-key-on-cluster>` |
| `affinity.enabled`             | Default is false, true to enable affinity                                                                                                                                     | `false`                      |
| `affinity.key`                 | Provide the key for the affinity,default is kubernetes.io/hostname                                                                                                            | `kubernetes.io/hostname`     |
| `affinity.value`               | Provide the values for the respective key                                                                                                                                     |                              |

> **Note:** See the chart's `values.yaml` file for a full list of configurable parameters.

### Preload Models

Startup model loading is disabled by default. To enable the chart's ConfigMap-backed,
read-only configuration, set:

```yaml
modeldownload:
  startupConfig:
    enabled: true
    config:
      download_path: /opt/models/preloaded
      parallel_downloads: false
      models:
        - name: BAAI/bge-small-en-v1.5
          hub: huggingface
          type: embeddings
        - name: yolov8n
          hub: ultralytics
          type: vision
          download_path: /opt/models/vision
```

Enable every plugin referenced by the model entries in
`modeldownload.env.ENABLED_PLUGINS`. The chart sets `STARTUP_MODELS_CONFIG` to the mounted
ConfigMap path. Keep tokens out of `startupConfig.config`; provide credentials through the
existing environment values or your deployment's secret-injection mechanism.

Model work continues after the readiness probe succeeds. Use the existing jobs endpoints or
`kubectl logs` to monitor jobs. The PVC preserves downloaded artifacts across pod restarts,
but in-memory job records are not restored and configured entries are scheduled again. For the
full schema and behavior, see [Download Models at Startup](./startup-models.md).

## Deploy the Helm Chart

```bash
helm install model-download . -n <your-namespace>
```

> **Note:** `model-download` creates and manages a shared PVC that can be used by dependent applications such as Chat Q&A.

## Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly:

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

## Access the Application

Open the application's Swagger documentation in a browser through `http://<node-ip>:<node-port>/api/v1/docs`.

## Uninstall Helm chart

```bash
helm uninstall <name> -n <your-namespace>
```

## Verify the Application

1. Ensure that all pods are running and the services are accessible.

2. Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:

  ```bash
  kubectl logs <pod-name>
  ```

- If the PVC created during a Helm chart deployment is not removed or auto-deleted due to a deployment failure or being stuck, delete it manually:

  ```bash
  # List the PVCs present in the given namespace
  kubectl get pvc -n <namespace>

  # Delete the required PVC from the namespace
  kubectl delete pvc <pvc-name> -n <namespace>
  ```

> **Note:**
> Delete the shared PVC only after confirming no other workload or application (for example,
> Chat Q&A) depends on it. In such cases, uninstall the dependent application first, then clean up `model-download` resources, and finally delete the shared PVC if required.

## Learn More

- [Build from Source](./build-from-source.md)
