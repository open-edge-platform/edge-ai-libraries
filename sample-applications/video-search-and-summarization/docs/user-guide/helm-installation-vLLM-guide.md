# Deploying VSS with vLLM on Kubernetes Using Helm

## Overview

This guide covers deploying the Video Search and Summarization (VSS) application on Kubernetes using **vLLM** as the LLM inference backend. vLLM provides an OpenAI-compatible API for efficient CPU-based inference on Intel Xeon systems - no GPU required. It can also run on an Intel® Arc™ GPU; see [Deploying on an Intel Arc GPU (XPU)](#deploying-on-an-intel-arc-gpu-xpu).

This is one of several supported deployment configurations. For an overview of all configurations (including OVMS, VLM Microservice, and GPU-based deployment), see [Deploy with Helm](./deploy-with-helm.md). For a conceptual overview of how VSS works, see [How It Works](./how-it-works.md).

---

## Prerequisites

### Hardware Requirements

For best performance, **Intel® Xeon® 6 Processors** are recommended.

| Component | Specification |
| --- | --- |
| CPU Cores | For optimal performance: 16 cores for vLLM, additional cores for ingestion, embedding, vectordb, and other microservices |
| RAM Memory | Minimum 256GB total system memory |
| Disk Space | Minimum 500GB (SSD recommended for optimal performance) |
| Storage | Dynamic storage provisioning capability (NFS or local storage) |

For GPU-accelerated deployment, an Intel® Arc™ or Arc™ Pro GPU with 16 GB or more of memory is recommended. Cards with less memory need the additional tuning described in [Deploying on an Intel Arc GPU (XPU)](#deploying-on-an-intel-arc-gpu-xpu).

### Software Requirements

| Tool | Version | Installation Guide |
| --- | --- | --- |
| Kubernetes | v1.24 or later | [Kubernetes docs](https://kubernetes.io/docs/setup/) |
| kubectl | Latest | [kubectl docs](https://kubernetes.io/docs/tasks/tools/install-kubectl/) |
| Helm | v3.0 or later | [Helm docs](https://helm.sh/docs/intro/install/) |

Your cluster must support **dynamic provisioning of Persistent Volumes**. Confirm a default storage class is configured:

```bash
kubectl get storageclass
```

See the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) if none is available.

---

## Step 1: Acquire the Helm Chart

```bash
# Clone the main branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b main

# Navigate to the chart directory
cd edge-ai-libraries/sample-applications/video-search-and-summarization/chart
```

---

## Step 2: Configure Required Values

Open `user_values_override.yaml` in your editor:

```bash
nano user_values_override.yaml
```

### Required Parameters

| Key | Description | Example Value |
| --- | --- | --- |
| `global.sharedPvcName` | Name of the shared PVC for all components | `vss-shared-pvc` |
| `global.huggingfaceToken` | Hugging Face API token for model access | `hf_xxxxxxxxxxxxxxxxxxxx` |
| `global.vlmName` | Vision Language Model used for video analysis | `Qwen/Qwen3-VL-4B-Instruct` |
| `global.env.POSTGRES_USER` | PostgreSQL username | `vsadmin` |
| `global.env.POSTGRES_PASSWORD` | PostgreSQL password | `<secure-password>` |
| `global.env.MINIO_ROOT_USER` | MinIO username (min 3 chars) | `minioadmin` |
| `global.env.MINIO_ROOT_PASSWORD` | MinIO password (min 8 chars) | `<secure-password>` |
| `global.env.RABBITMQ_DEFAULT_USER` | RabbitMQ username | `guest` |
| `global.env.RABBITMQ_DEFAULT_PASS` | RabbitMQ password | `<secure-password>` |
| `global.embeddingModelName` | Multimodal embedding model | `CLIP/clip-vit-b-32` (search) or `QwenText/qwen3-embedding-0.6b` (unified) |

For the full parameter catalog across all deployment modes, see [Deploy with Helm](./deploy-with-helm.md).

### Optional Parameters

| Key | Description | Example Value |
| --- | --- | --- |
| `global.keepPvc` | Retain PVC on `helm uninstall` to avoid re-downloading models | `true` |
| `global.proxy.http_proxy` | HTTP proxy (if required by your environment) | `http://proxy-example.com:000` |
| `global.proxy.https_proxy` | HTTPS proxy (if required by your environment) | `http://proxy-example.com:000` |

### vLLM-Specific Parameters

The `xeon_vllm_values.yaml` override file (included in the chart) pre-configures vLLM with sensible defaults for Intel Xeon. You can override individual values as needed:

| Key | Description | Default | Notes |
| --- | --- | --- | --- |
| `vllm.resources.requests.cpu` | CPU request for the vLLM pod | `16` | Increase for higher throughput |
| `vllm.resources.requests.memory` | Memory request for the vLLM pod | `128Gi` | Increase for larger models |
| `vllm.pvc.size` | Model cache PVC size | `80Gi` | Increase for larger model footprints |
| `vllm.modelCachePath` | Model cache mount path in the pod | `/cache/vllm` | Uses shared PVC |

> **Model selection**: `vllm.enabled: true` (set by `xeon_vllm_values.yaml`) automatically disables the VLM Inference Microservice (`vlminference.enabled: false`). vLLM uses the model specified in `global.vlmName`; ensure it is compatible with vLLM and available on Hugging Face.

## Step 3: Build Helm Dependencies

From the chart directory, run:

```bash
helm dependency update
```

Verify all dependencies are resolved:

```bash
helm dependency list
```

---

## Step 4: Create a Namespace

```bash
export NAMESPACE=vss-deployment
kubectl create namespace ${NAMESPACE}
```

> All subsequent commands assume the `NAMESPACE` variable is set in your shell session.

---

## Step 5: Deploy with vLLM

Choose the deployment mode that fits your use case. In both cases, `xeon_vllm_values.yaml` enables vLLM and configures resource allocations for Intel Xeon CPUs.

> **Switching modes**: Always uninstall the current release before switching to a different mode:
>
> ```bash
> helm uninstall vss -n ${NAMESPACE}
> ```

### Option A: Video Summarization Only

Deploys the summarization pipeline with vLLM for text generation.

```bash
helm install vss . \
  -f summary_override.yaml \
  -f xeon_vllm_values.yaml \
  -f user_values_override.yaml \
  -n ${NAMESPACE}
```

### Option B: Unified Video Search and Summarization

Deploys both the search and summarization pipelines with vLLM. Before installing, ensure `global.embeddingModelName` is set to a text embedding model (e.g., `QwenText/qwen3-embedding-0.6b`) in `user_values_override.yaml`.

```bash
helm install vss . \
  -f unified_summary_search.yaml \
  -f xeon_vllm_values.yaml \
  -f user_values_override.yaml \
  -n ${NAMESPACE}
```

> **Requirement:** The chart will raise an error if `global.embeddingModelName` is not set. Review the supported model list in [supported-models](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/multimodal-embedding-serving/supported-models.html) before choosing model IDs.

**Understanding the override files:**

| File | Purpose |
| --- | --- |
| `summary_override.yaml` | Enables the summarization pipeline |
| `unified_summary_search.yaml` | Enables combined search and summarization |
| `xeon_vllm_values.yaml` | Enables vLLM, disables VLM Microservice, sets Xeon-optimized resource allocations |
| `arc_vllm_values.yaml` | Same, but targets an Intel Arc GPU instead of the CPU (see [Deploying on an Intel Arc GPU (XPU)](#deploying-on-an-intel-arc-gpu-xpu)) |
| `user_values_override.yaml` | Your credentials, model selections, and environment-specific overrides |

---

## Deploying on an Intel Arc GPU (XPU)

vLLM can run on an Intel® Arc™ or Arc™ Pro GPU instead of the CPU. Use `arc_vllm_values.yaml` everywhere this guide uses `xeon_vllm_values.yaml`:

```bash
helm install vss . \
  -f summary_override.yaml \
  -f arc_vllm_values.yaml \
  -f user_values_override.yaml \
  -n ${NAMESPACE}
```

### Additional prerequisites

| Requirement | How to check |
| --- | --- |
| [Intel GPU device plugin](https://github.com/intel/intel-device-plugins-for-kubernetes) installed, advertising the GPU as a schedulable resource | `kubectl get nodes -o jsonpath='{.items[*].status.allocatable}'` — look for `gpu.intel.com/i915` (i915 kernels) or `gpu.intel.com/xe` (newer Xe kernels) |
| `/dev/dri` present on the GPU node | `ls -l /dev/dri` |
| `global.accelGroupIds` matches the host group IDs owning `/dev/dri` | `ls -ln /dev/dri` |

`global.accelGroupIds` is added to the pod's `supplementalGroups` so the container user can open the device. This mirrors `group_add` in the Compose deployment. The chart default is `992`.

### XPU-specific parameters

| Key | Description | Default |
| --- | --- | --- |
| `vllm.device` | Selects the vLLM backend. `XPU` switches to the Intel GPU image and arguments. | `CPU` |
| `vllm.gpu.key` | Device plugin resource key. **Required** when `device` is `XPU`; rendering fails if it is empty. | `gpu.intel.com/i915` |
| `vllm.gpu.devicePath` | Host path to the GPU device nodes, mounted into the pod. | `/dev/dri` |
| `vllm.model.gpuMemoryUtilization` | Fraction of GPU memory vLLM may reserve for weights, activations, and KV cache. | `0.8` |
| `vllm.model.mmMaxPixels` | Maximum pixels per frame. Caps frame resolution, not frame count. | `16777216` |
| `vllm.model.enforceEager` | Skips graph capture. Required on the XPU backend. | `true` |

If your device plugin advertises a different resource key, override it:

```yaml
vllm:
  gpu:
    key: "gpu.intel.com/xe"
```

> [!IMPORTANT]
> **GPUs with less than 16 GB (for example Intel Arc B580, 12 GB):** the defaults above fail to start with `No available memory for the cache blocks`. Use the FP8 checkpoint together with the reduced settings commented at the bottom of `arc_vllm_values.yaml`; all of them are required together. See [Troubleshooting](./troubleshooting.md#vllm-xpu-fails-to-start-with-no-available-memory-for-the-cache-blocks) for the sizing formula and how to derive values for other cards.

---

## Step 6: Verify the Deployment

Monitor pod startup progress:

```bash
kubectl get pods -n ${NAMESPACE} -w
```

After a successful deployment, all pods should reach **Running / 1/1 Ready** state:

> **First-time startup**: All pods can take **up to 20–30 minutes** to reach Running state because models (vLLM, embedding, object detection — up to ~50 GB total) are downloaded from Hugging Face and cached. Set `global.keepPvc: true` to skip model re-downloads on reinstallation.

---

## Step 7: Access the Application

Once all pods are running, retrieve the URL:

```bash
NGINX_HOST=$(kubectl get pods -l app=vss-nginx -n ${NAMESPACE} -o jsonpath='{.items[0].status.hostIP}')
NGINX_PORT=$(kubectl get service vss-nginx -n ${NAMESPACE} -o jsonpath='{.spec.ports[0].nodePort}')
echo "http://${NGINX_HOST}:${NGINX_PORT}"
```

Open the URL in your browser to access the VSS dashboard.

---

## Managing the Deployment

### Upgrading

After editing `user_values_override.yaml`, apply changes with:

```bash
helm upgrade vss . \
  -f summary_override.yaml \
  -f xeon_vllm_values.yaml \
  -f user_values_override.yaml \
  -n ${NAMESPACE}
```

Replace `summary_override.yaml` with `unified_summary_search.yaml` for the unified mode.

---

## Troubleshooting

For troubleshooting guidance, see [Deploy with Helm — Troubleshooting](./deploy-with-helm.md#troubleshooting).

---

## Uninstallation

```bash
helm uninstall vss -n ${NAMESPACE}

# Optional: delete the namespace
kubectl delete namespace ${NAMESPACE}
```

> [!NOTE]
> By default, PVCs are deleted with the Helm release. If you set `global.keepPvc: true`, PVCs are retained and reusable in future deployments to avoid re-downloading models.
