# Deploying VSS with vLLM on Kubernetes Using Helm

## Overview

This guide covers deploying the Video Search and Summarization (VSS) application on Kubernetes using **vLLM** as the LLM inference backend. vLLM provides an OpenAI-compatible API for efficient CPU-based inference on Intel Xeon systems - no GPU required.

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
# Clone the repository (main branch)
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries

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
| `global.vlmName` | Vision Language Model used for video analysis | `Qwen/Qwen2.5-VL-3B-Instruct` |
| `global.env.POSTGRES_USER` | PostgreSQL username | `vsadmin` |
| `global.env.POSTGRES_PASSWORD` | PostgreSQL password | `<secure-password>` |
| `global.env.MINIO_ROOT_USER` | MinIO username (min 3 chars) | `minioadmin` |
| `global.env.MINIO_ROOT_PASSWORD` | MinIO password (min 8 chars) | `<secure-password>` |
| `global.env.RABBITMQ_DEFAULT_USER` | RabbitMQ username | `guest` |
| `global.env.RABBITMQ_DEFAULT_PASS` | RabbitMQ password | `<secure-password>` |
| `global.env.EMBEDDING_MODEL_NAME` | Multimodal embedding model | `CLIP/clip-vit-b-32` (search) or `QwenText/qwen3-embedding-0.6b` (unified) |

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

Deploys both the search and summarization pipelines with vLLM. Before installing, ensure `global.env.TEXT_EMBEDDING_MODEL_NAME` is set and `global.embedding.preferTextModel: true` in `user_values_override.yaml` (built into `unified_summary_search.yaml`).

```bash
helm install vss . \
  -f unified_summary_search.yaml \
  -f xeon_vllm_values.yaml \
  -f user_values_override.yaml \
  -n ${NAMESPACE}
```

> **Requirement:** The chart will raise an error if `global.env.TEXT_EMBEDDING_MODEL_NAME` is omitted while unified mode is enabled. Review the supported model list in [supported-models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md) before choosing model IDs.

**Understanding the override files:**

| File | Purpose |
| --- | --- |
| `summary_override.yaml` | Enables the summarization pipeline |
| `unified_summary_search.yaml` | Enables combined search and summarization; sets `preferTextModel: true` |
| `xeon_vllm_values.yaml` | Enables vLLM, disables VLM Microservice, sets Xeon-optimized resource allocations |
| `user_values_override.yaml` | Your credentials, model selections, and environment-specific overrides |

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

> By default, PVCs are deleted with the Helm release. If you set `global.keepPvc: true`, PVCs are retained and reusable in future deployments to avoid re-downloading models.
