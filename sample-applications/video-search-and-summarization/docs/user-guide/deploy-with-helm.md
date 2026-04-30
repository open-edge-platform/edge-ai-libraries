# How to deploy with Helm\* Chart

This section shows how to deploy the Video Search and Summarization Sample Application using Helm chart.

## Prerequisites

Before you begin, ensure that you have the following:

- Kubernetes\* cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. See the [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm chart installed on your system. See the [Installation Guide](https://helm.sh/docs/intro/install/).
- **Storage Requirement :** Application requests for **50GiB** of storage in its default configuration. (This should change with choice of models and needs to be properly configured). Please make sure that required storage is available in you cluster.

## Helm Chart Installation

In order to setup the end-to-end application, we need to acquire the charts and install it with optimal values and configurations. Subsequent sections will provide step by step details for the same.

### 1. Acquire the helm chart

There are 2 options to get the charts in your workspace:

#### Option 1: Get the charts from Docker Hub

##### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from Docker Hub:

```bash
helm pull oci://registry-1.docker.io/intel/video-search-and-summarization --version <version-no>
```

Refer to the release notes for details on the latest version number to use for the sample application.

##### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:

```bash
tar -xvf video-search-and-summarization-<version-no>.tgz
```

This will create a directory named `video-search-and-summarization` containing the chart files. Navigate to the extracted directory to access the charts.

```bash
cd video-search-and-summarization
```

#### Option 2: Install from Source

##### Step 1: Clone the Repository

Clone the repository containing the Helm chart:

```bash
# Clone the latest on mainline
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
# Alternatively, Clone a specific release branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
```

##### Step 2: Change to the Chart Directory

Navigate to the chart directory:

```bash
cd edge-ai-libraries/sample-applications/video-search-and-summarization/chart
```

### 2. Configure Required Values

The application requires several values to be set by user in order to work. To make it easier, we have included a `user_values_override.yaml` file, which contains only the values that user needs to tweak. Open the file in your favorite editor or use nano:

```bash
nano user_values_override.yaml
```

Update or edit the values in YAML file as follows:

| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.sharedPvcName` | Name for PVC to be used for storage by all components of application | `vss-shared-pvc` |
| `global.keepPvc` | PVC gets deleted by default once helm is uninstalled. Set this to true to persist PVC (helps avoid delay due to model re-downloads when re-installing chart). | `true` or `false` |
| `global.huggingfaceToken` | Your Hugging Face API token | `<your-huggingface-token>` |
| `global.proxy.http_proxy` | HTTP proxy if required | `http://proxy-example.com:000` |
| `global.proxy.https_proxy` | HTTPS proxy if required | `http://proxy-example.com:000` |
| `global.vlmName` | VLM model to be used by OVMS or vLLM for captioning and summarization | `Qwen/Qwen2.5-VL-3B-Instruct` (CPU) or `OpenVINO/Phi-3.5-vision-instruct-int8-ov` (GPU) |
| `global.llmName` | Optional separate LLM model for final summarization (OVMS split-model mode). Leave empty for shared-model mode. | `Intel/neural-chat-7b-v3-3` (CPU) or `Intel/neural-chat-7b-v3-3` (GPU) or `OpenVINO/Qwen3-8B-int4-cw-ov` (NPU) |
| `global.env.POSTGRES_USER` | PostgreSQL user | `<your-postgres-user>` |
| `global.env.POSTGRES_PASSWORD` | PostgreSQL password | `<your-postgres-password>` |
| `global.env.MINIO_ROOT_USER` | MinIO server user name | `<your-minio-user>` (at least 3 characters) |
| `global.env.MINIO_ROOT_PASSWORD` | MinIO server password | `<your-minio-password>` (at least 8 characters) |
| `global.env.RABBITMQ_DEFAULT_USER` | RabbitMQ username | `<your-rabbitmq-username>` |
| `global.env.RABBITMQ_DEFAULT_PASS` | RabbitMQ password | `<your-rabbitmq-password>` |
| `global.env.OTLP_ENDPOINT` | OTLP endpoint | Leave empty if not using telemetry |
| `global.env.OTLP_ENDPOINT_TRACE` | OTLP trace endpoint | Leave empty if not using telemetry |
| `global.env.EMBEDDING_MODEL_NAME` | Default embedding model used by all services when not overridden | `CLIP/clip-vit-b-32` (search) or `QwenText/qwen3-embedding-0.6b` (summary+search) |
| `global.env.TEXT_EMBEDDING_MODEL_NAME` | Optional text-only embedding model. Required when `global.embedding.preferTextModel` is `true`. | `QwenText/qwen3-embedding-0.6b` |
| `global.embedding.preferTextModel` | When set to `true`, forces all services to use the text embedding model (for unified summary + search deployments). | `true` or `false` |
| `global.devices.multimodalEmbedding.device` | Device for multimodal-embedding service | `CPU` or `GPU` |
| `global.devices.multimodalEmbedding.key` | K8s resource key for GPU (required when device=GPU) | `gpu.intel.com/i915` or `gpu.intel.com/xe` |
| `global.devices.vdmsDataprep.device` | Device for vdms-dataprep service | `CPU` or `GPU` |
| `global.devices.vdmsDataprep.key` | K8s resource key for GPU (required when device=GPU) | `gpu.intel.com/i915` or `gpu.intel.com/xe` |
| `global.devices.ovms.vlm.device` | Device for OVMS VLM model | `CPU`, `GPU`, `NPU`, or `HETERO:GPU,CPU` |
| `global.devices.ovms.vlm.key` | K8s resource key (required when device is GPU/NPU/HETERO) | `gpu.intel.com/i915` or `gpu.intel.com/xe` |
| `global.devices.ovms.llm.device` | Device for OVMS LLM model (split-model mode) | `CPU`, `GPU`, `NPU`, or `HETERO:GPU,CPU` |
| `global.devices.ovms.llm.key` | K8s resource key (required when device is GPU/NPU/HETERO) | `gpu.intel.com/i915` or `gpu.intel.com/xe` |
| `ovms.env.VLM_WEIGHT_FORMAT` | Override weight format for VLM model conversion | `int4` or `int8` (auto-detected if not set) |
| `ovms.env.LLM_WEIGHT_FORMAT` | Override weight format for LLM model conversion | `int4` or `int8` (auto-detected if not set) |
| `ovms.enabled` | Enable OVMS as the inference backend (default: true in summary mode) | `true` or `false` |
| `vllm.enabled` | Enable vLLM as the inference backend (alternative to OVMS) | `true` or `false` |
| `pipelinemanager.env.USE_VLLM` | Set to `CONFIG_ON` when using vLLM backend | `CONFIG_OFF` (default) or `CONFIG_ON` |
| `pipelinemanager.env.AUDIO_DEVICE` | Device used for audio transcription (Whisper) | `cpu` (default) |
| `pipelinemanager.env.AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` | Default for audio transcript summarization. When enabled, the full audio transcript is summarized by the LLM and included in the final video summary. Users can override this per-video via the UI toggle. | `true` (default) or `false` |
| `videoingestion.odModelName` | Name of object detection model used during video ingestion | `yolov8l-worldv2` |
| `videoingestion.odModelType` | Type/Category of the object detection Model | `yolo_v8` |
| `vsscollector.enabled` | Enable the telemetry collector sidecar (telegraf-based) | `true` or `false` |
| `vsscollector.websocketUrl` | Override the telemetry websocket URL (defaults to `ws://pipeline-manager:80/metrics/ws/collector`) | `ws://pipeline-manager:80/metrics/ws/collector` |
| `vsscollector.signalVolume.subPath` | Subpath under the shared volume for telemetry signal files | `collector-signals` |

> **Tip:** Set `global.env.EMBEDDING_MODEL_NAME` to pick the default embedding model for both the multimodal embedding service and DataPrep. When deploying the unified summary + search mode, also set `global.env.TEXT_EMBEDDING_MODEL_NAME` and flip `global.embedding.preferTextModel` to `true` so the chart enforces the text embedding requirement automatically. Review the supported model list in [supported-models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md) before choosing model IDs.

> **Note:** `multimodal-embedding-ms` and `vdms-dataprep` share the same PVC for model/cache storage. If you enable GPU for one of them, enable it for the other as well (`global.devices.multimodalEmbedding.device=GPU` **and** `global.devices.vdmsDataprep.device=GPU`). Mixing GPU/CPU modes between the two causes the GPU pod to wait forever because the shared PVC can only be attached to a single node at a time. The Helm chart validates this pairing and will fail the install/upgrade when the devices do not match while both services are enabled.

> **Telemetry (vss-collector):** When `vsscollector.enabled=true`, the chart deploys a telegraf-based collector and wires it to the pipeline-manager websocket at `/metrics/ws/collector`. If your cluster uses a non-default Service port or a custom ingress, set `vsscollector.websocketUrl` explicitly. **Note:** The vss-collector is only deployed in **search mode** (using `search_override.yaml`) or **unified summary+search mode** (using `unified_summary_search.yaml`). It is not part of the summary-only stack; setting `vsscollector.enabled=true` in `user_values_override.yaml` has no effect when deploying with `summary_override.yaml` alone.


> **Split-device OVMS example (GPU VLM + NPU LLM):**
>
> To run VLM on GPU and LLM on NPU, set the following in `user_values_override.yaml`:
>
> ```yaml
> global:
>   vlmName: "OpenVINO/Phi-3.5-vision-instruct-int8-ov"
>   llmName: "OpenVINO/Qwen3-8B-int4-cw-ov"
>   devices:
>     ovms:
>       vlm:
>         device: GPU
>         key: "gpu.intel.com/i915"
>       llm:
>         device: NPU
>         key: "npu.intel.com/accel"
> ```

### 3. Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency update
```

### 4. Set and Create a Namespace

We will install the helm chart in a new namespace. Create a shell variable to refer a new namespace and create it.

1. Refer a new namespace using shell variable `my_namespace`. Set any desired unique value.

   ```bash
   my_namespace=foobar
   ```

2. Create the Kubernetes namespace. If it is already created, creation will fail. You can update the namespace in previous step and try again.

   ```bash
   kubectl create namespace $my_namespace
   ```

> **_NOTE :_** All subsequent steps assume that you have `my_namespace` variable set and accessible on your shell with the desired namespace as its value.

### 5. Deploy the Helm Chart

At present, there are multiple deployment modes for **Video Search and Summarization Application**. We will learn how to deploy each use-case using the helm chart.

> **Note:** Before switching to a different use-case always stop the current running use-case's application stack (if any) by uninstalling the chart : `helm uninstall vss -n $my_namespace`. This is not required if you are installing the helm chart for the first time.

#### **Use Case 1: Video Summarization with OVMS (Default - CPU)**

Deploy the Video Summarization application using OVMS (OpenVINO Model Server) for both VLM captioning and LLM summarization:

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml -n $my_namespace
```

This is the default and recommended deployment mode. OVMS hosts the VLM model specified in `global.vlmName` and uses it for both chunk-wise captioning and final summarization (shared-model mode).

> **Note:** When deploying OVMS, the service may take longer to start on first run due to model conversion. Subsequent starts are faster as models are cached.

#### **Use Case 1a: OVMS with Separate LLM Model (Split-Model Mode)**

To use a separate LLM model for final summarization while using VLM for captioning, set `global.vlmName` and `global.llmName` in `user_values_override.yaml`:

```yaml
global:
  vlmName: "Qwen/Qwen2.5-VL-3B-Instruct"
  llmName: "Intel/neural-chat-7b-v3-3"
```

Then deploy:

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml -n $my_namespace
```

This deploys OVMS hosting both models:

- VLM model (from `global.vlmName`) for chunk-wise captioning
- LLM model (from `global.llmName`) for final summarization

#### **Use Case 1b: OVMS with GPU Acceleration**

To enable GPU acceleration for OVMS, configure the device settings and model in `user_values_override.yaml`:

```yaml
global:
  vlmName: "OpenVINO/Phi-3.5-vision-instruct-int8-ov"
  devices:
    ovms:
      vlm:
        device: GPU
        key: "gpu.intel.com/i915"
```

Then deploy:

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml -n $my_namespace
```

> **Note:** GPU deployment requires the Intel device plugin to be installed on your cluster. Verify your GPU node label with `kubectl describe node <node-name>` and set the appropriate `key` value accordingly.

##### Discovering Available Device Resource Keys

Before configuring GPU or NPU devices, verify what resources are available in your cluster:

**List all allocatable resources across all nodes:**

```bash
kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.name):\n" + (.status.allocatable | to_entries | map(select(.key | test("gpu|npu|vpu|accel";"i"))) | map("  \(.key): \(.value)") | join("\n"))'
```

**Alternative - inspect a specific node:**

```bash
kubectl describe node <node-name> | grep -A20 "Allocatable:" | grep -E "gpu|npu|vpu|accel"
```

**Common Intel device resource keys:**

| Device Type | Common Resource Keys |
| ----------- | -------------------- |
| Intel Integrated GPU | `gpu.intel.com/i915` |
| Intel Discrete GPU (Arc/Flex) | `gpu.intel.com/xe` |
| Intel NPU (AI Boost) | `npu.intel.com/accel` |

> **Tip:** If no GPU/NPU resources appear, ensure the Intel device plugin is installed. See [Intel Device Plugins for Kubernetes](https://github.com/intel/intel-device-plugins-for-kubernetes).
>
> **Split-device note:** When using different devices for VLM and LLM (e.g., GPU + NPU), ensure at least one node in your cluster has **both** resources available. The pod will only schedule on nodes that satisfy all resource requests.
>
> **NPU Support:** Not all models support NPU execution. Verify model and hardware compatibility at the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page before selecting `NPU` as target device.

##### Model Weight Format

OVMS automatically selects the optimal weight compression format based on the target device:

| Device | Default Weight Format |
| ------ | -------------------- |
| CPU | `int8` |
| GPU | `int4` |
| NPU | `int4` |
| HETERO:GPU,CPU | `int4` |

**Overriding Weight Format:**

To explicitly set the weight format for VLM or LLM models, set `ovms.env.VLM_WEIGHT_FORMAT` and/or `ovms.env.LLM_WEIGHT_FORMAT` in `user_values_override.yaml`:

```yaml
ovms:
  env:
    VLM_WEIGHT_FORMAT: "int8"
    LLM_WEIGHT_FORMAT: "int8"
```

> **Note:** Models from the `OpenVINO/` namespace (e.g., `OpenVINO/Phi-3.5-vision-instruct-int8-ov`) are pre-converted and do not undergo weight format conversion. The weight format in the model name indicates its native format.
>
> **Storage Model Names:** Converted models are stored with device and weight format in the path (e.g., `Qwen_Qwen2.5-VL-3B-Instruct_GPU_int4`). Changing the device or weight format creates a new conversion, preserving existing models.

#### **Use Case 2: Video Summarization with vLLM (CPU-based)**

If you want to use vLLM as the inference backend for CPU-based deployment, deploy with the vLLM override values:

```bash
helm install vss . -f summary_override.yaml -f xeon_vllm_values.yaml -f user_values_override.yaml -n $my_namespace
```

**vLLM Configuration Details:**

- vLLM provides an OpenAI-compatible API for efficient LLM inference on CPU
- The `xeon_vllm_values.yaml` override file includes:
  - vLLM service with 16 CPU cores and 128Gi memory allocation
  - Resource configurations for all dependent services (PostgreSQL, RabbitMQ, audio-analyzer, etc.)
  - Automatic disabling of OVMS (`ovms.enabled=false`)

**Prerequisites for vLLM:**

- Ensure your Kubernetes node has sufficient CPU resources (minimum 32 logical cores recommended)
- The vLLM container requires at least 128Gi of memory for typical LLM models
- Cache storage must be configured (default 80Gi PVC for model cache)

> **Model Selection:** vLLM uses the model specified in `global.vlmName`. Ensure the model is compatible with vLLM and available on Hugging Face. Update `global.huggingfaceToken` if using private models.
>
> **Performance Tip:** vLLM's performance scales with available CPU cores. If you have nodes with different CPU counts, consider using node affinity to deploy vLLM on high-CPU nodes.

#### **Use Case 3: Video Search Only**

To deploy only the Video Search functionality, use the search override values:

```bash
helm install vss . -f search_override.yaml -f user_values_override.yaml -n $my_namespace
```

#### **Use Case 4: Unified Video Search and Summarization**

To deploy the combined video search and summarization functionality, use the unified override values:

```bash
helm install vss . -f unified_summary_search.yaml -f user_values_override.yaml -n $my_namespace
```

> **Requirement:** Before installing the unified stack, populate `global.env.TEXT_EMBEDDING_MODEL_NAME` and set `global.embedding.preferTextModel=true` (the supplied `unified_summary_search.yaml` does this for you). The chart will raise an error if the text embedding model is omitted while unified mode is enabled. Review the supported model list in [supported-models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md) before choosing model IDs.
>
> **GPU Tip:** In unified mode the `multimodal-embedding-ms` and `vdms-dataprep` pods always share the same PVC, so either enable GPU for both (`global.devices.multimodalEmbedding.device=GPU` and `global.devices.vdmsDataprep.device=GPU`) or keep both on CPU. Mixing GPU/CPU settings leaves the GPU pod pending because the shared PVC cannot mount on two nodes simultaneously, and the Helm chart blocks such mismatches during install/upgrade.

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly:

```bash
kubectl get pods -n $my_namespace
```

**Before proceeding to access the application we must ensure the following status of output of the above command:**

1. Ensure all pods are in the "Running" state. This is denoted by **Running** state mentioned in the **STATUS** column.

2. Ensure all containers in each pod are _Ready_. As all pods are running single container only, this is typically denoted by mentioning **1/1** in the **READY** column.

> **Important:**
>
> - When deployed for first time, it may take up-to around 50 Mins to bring all the pods/containers in running and ready state, as several containers try to download models which can take a while. The time to bring up all the pods depends on several factors including but not limited to node availability, node load average, network speed, compute availability etc.
> -If you want to persist the downloaded models and avoid delays pertaining to model downloads when re-installing the charts, please set the `global.keepPvc` value to `true` in `user_values_override.yaml` file before installing the chart.

### Step 7: Accessing the application

Nginx service running as a reverse proxy in one of the pods, helps us to access the application. We need to get Host IP and Port on the node where the nginx service is running.

Run the following command to get the host IP of the node and port exposed by Nginx service:

```bash
vss_hostip=$(kubectl get pods -l app=vss-nginx -n $my_namespace -o jsonpath='{.items[0].status.hostIP}')
vss_port=$(kubectl get service vss-nginx -n $my_namespace -o jsonpath='{.spec.ports[0].nodePort}')
echo "http://${vss_hostip}:${vss_port}"
```

Copy the output of above bash snippet and paste it into your browser to access the **Video Search and Summarization Application**.

### Step 8: Update Helm Dependencies

If any changes are made to the sub-charts, always remember to update the Helm dependencies using the following command before re-installing or upgrading your helm installation:

```bash
helm dependency update
```

### Step 9: Uninstall Helm chart

To uninstall the Video Summary Helm chart, use the following command:

```bash
helm uninstall vss -n $my_namespace
```

## Updating PVC Storage Size

If any of the microservice requires more or less storage than the default allotted storage in values file, this can be overridden for one or more services.

### Updating storage for VDMS-Dataprep and MultiModal Embedding Service

Set the required `sharedClaimSize` value while installing the helm chart.

For example, if installing chart in search only mode :

```bash
helm install vss . -f search_override.yaml -f user_values_override.yaml --set sharedClaimSize=10Gi -n $my_namespace
```

If installing the chart in the combined Video Search and Summarization mode :

```bash
helm install vss . -f unified_summary_search.yaml -f user_values_override.yaml --set sharedClaimSize=10Gi -n $my_namespace
```

### Updating storage for other microservices

To update storage for other microservices we can, override the corresponding `claimSize` value in the main chart values file, while installing the chart.

For example, for updating storage for VLM-Inference Microservice in Video Summarization mode :

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml --set vlminference.claimSize=50Gi -n $my_namespace
```

Similarly, for updating storage for OVMS in Video Summarization mode, we can install the chart in following ways :

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml -f ovms_override.yaml --set ovms.claimSize=10Gi -n $my_namespace
```

For updating storage for vLLM in Video Summarization mode with vLLM backend :

```bash
helm install vss . -f summary_override.yaml -f xeon_vllm_values.yaml -f user_values_override.yaml --set vllm.pvc.size=100Gi -n $my_namespace
```

Let's look at one more example, for updating storage for Minio Server in the combined Video Search and Summarization mode :

```bash
helm install vss . -f unified_summary_search.yaml -f user_values_override.yaml --set minioserver.claimSize=10Gi -n $my_namespace
```

If not set while installing the chart, all services will claim a default amount of storage set in the values file.

## Verification

- Ensure that all pods are running and the services are accessible.
- Access the Video Summarization application dashboard and verify that it is functioning as expected.
- Upload a test video to verify that the ingestion, processing, and summarization pipeline works correctly.
- Check that all components (MinIO, PostgreSQL, RabbitMQ, video ingestion, VLM inference, audio analyzer) are functioning properly.

## Troubleshooting

- **Pods not coming in Ready or Running state for a long time.**

  There could be several possible reasons for this. Most likely reasons are storage unavailability, node unavailability, network slow-down or faulty network etc. Please check with your cluster admin or try fresh installation of charts, **after deleting the PVC _(see next issue)_ and un-installing the current chart**.

- **All containers Ready, all Pods in Running state, application UI is accessible but search or summarization is failing.**

  If PVC has been configured to be retained, most common reason for application to fail to work is a stale PVC. This problem most likely occurs when helm charts are re-installed after some updates to helm chart or the application image. To fix this, delete the PVC before re-installing the helm chart by following command:

    ```bash
    kubectl delete pvc vss-shared-pvc -n $my_namespace
    ```

  If you have updated the `global.pvcName` in the values file, use the updated name instead of default PVC name `vss-shared-pvc` in above command.

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:

    ```bash
    kubectl logs <pod-name> -n $my_namespace
    ```

- For component-specific issues:
  - Video ingestion problems: Check the logs of the videoingestion pod
  - VLM inference issues: Check the logs of the vlm-inference-microservice pod
  - Database connection problems: Verify the PostgreSQL pod is running correctly
  - Storage issues: Check the MinIO server status and connectivity

- Some issues might be fixed by freshly setting up storage. This is helpful in cases where deletion of PVC is prohibited by configuration on charts un-installation (when `global.keepPvc` is set to true):

    ```bash
    kubectl delete pvc <pvc-name> -n $my_namespace
    ```

- If you're experiencing issues with the Hugging Face API, ensure your API token `global.huggingfaceToken` is valid and properly set in the `user_values_override.yaml` file.

## Related links

- [How to Build from Source](./build-from-source.md)

## Monitoring and Metrics

### OVMS Prometheus Metrics

When OVMS is enabled, the application exposes Prometheus-compatible metrics at the `/ovms/metrics` endpoint. These metrics provide valuable insights into inference performance and can be used for monitoring and auto-scaling.

**Accessing metrics:**

```bash
# Port-forward to the nginx service (replace <release-name> with your helm release name, e.g., "vss")
kubectl port-forward svc/<release-name>-nginx 8081:80 -n $my_namespace

# Fetch metrics
curl http://localhost:8081/ovms/metrics
```

**Available metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `ovms_streams` | gauge | Number of OpenVINO execution streams |
| `ovms_current_requests` | gauge | Requests currently being processed |
| `ovms_requests_success` | counter | Total successful requests |
| `ovms_requests_fail` | counter | Total failed requests |
| `ovms_request_time_us` | histogram | Request processing time (microseconds) |
| `ovms_inference_time_us` | histogram | Inference execution time (microseconds) |
| `ovms_wait_for_infer_req_time_us` | histogram | Queue wait time (microseconds) |

**Labels:** Metrics include labels for `api` (KServe, TensorFlowServing, V3), `interface` (REST, gRPC), `method`, `name` (model name), and `version`.

**Prometheus integration:**

Add the following scrape configuration to your Prometheus config:

```yaml
scrape_configs:
  - job_name: 'vss-ovms'
    static_configs:
      - targets: ['<release-name>-nginx.<namespace>.svc.cluster.local:80']
    metrics_path: '/ovms/metrics'
```

> **Note:** Metrics are only available when OVMS is enabled (`ovms.enabled=true`). When using vLLM backend, this endpoint is not available.
