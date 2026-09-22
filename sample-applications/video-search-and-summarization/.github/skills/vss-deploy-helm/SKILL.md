---
name: vss-deploy-helm
description: Use this skill whenever a developer needs to deploy VSS to Kubernetes, helm install VSS, configure values.yaml for VSS, or run VSS on k8s with GPU/vLLM for the video-search-and-summarization sample app. This skill is especially useful when translating Docker Compose/setup.sh modes (--summary, --search, --summary-and-search/--unified, dual UI, ENABLE_VLLM, OVMS GPU/NPU) into the actual Helm chart override files and values keys. Prefer this skill for VSS Helm install/upgrade/troubleshooting even if the user only says “put VSS on k8s” or “make values.yaml for VSS”.
---

# VSS Helm deploy

Use this workflow for the VSS sample app Helm chart at `sample-applications/video-search-and-summarization/chart`. The chart’s real dependencies are `ovms`, `minioserver`, `audioanalyzer`, `postgresql`, `rabbitmq`, `videoingestion`, `videosearch`, `vdmsvectordb`, `multimodaldataprep`, `multimodalembeddingms`, `vectorretriever`, `vllm` (alias of `vllm-server`), `summaryui`, and `searchui` (aliases of `vssui`).

If the user asks to map Compose or `setup.sh` settings to Helm values, read `references/helm-values-map.md`.

## Answer contract when the cluster is not reachable

The user may be planning ahead, or `kubectl`/the cluster/the chart may be
unavailable here. In that case **do not stall and do not invent output.** Answer
with the exact command sequence instead: the bootstrap step, the override files
to stack in order, the values the operator must fill in, the `helm install` /
`helm upgrade` command with its namespace, and how to verify. State plainly that
the commands were not executed. Never end the answer by asking whether to run them.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It resolves the app root in this order and prints it
as the only line on stdout:

1. **Walk up from the current directory** looking for a VSS app root - a
   directory carrying all three markers `setup.sh`, `docker/`, and
   `pipeline-manager/`.
2. **Ask git for the enclosing repository** (`git rev-parse --show-toplevel`) and
   check whether it holds `sample-applications/video-search-and-summarization`,
   or is itself a VSS app root. This is what makes your own clone - or a fork -
   work unchanged.
3. **Reuse a checkout a previous bootstrap already placed** in
   `${XDG_CACHE_HOME:-$HOME/.cache}/vss-src/edge-ai-libraries`.

If any of those hit, that checkout is **reused and NO clone is performed**. Only
when all three miss does it clone - and then only a **shallow (`--depth 1`),
single-branch, sparse** checkout of just
`sample-applications/video-search-and-summarization` from `main`:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-deploy-helm. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-deploy-helm"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it. The bootstrap refuses
to overwrite an existing non-VSS clone destination.

## Prerequisites

1. Confirm a reachable Kubernetes cluster, `kubectl`, and Helm 3:
   ```bash
   kubectl cluster-info
   kubectl get nodes
   helm version
   ```
2. Confirm dynamic PV provisioning if using PVCs:
   ```bash
   kubectl get storageclass
   ```
3. For GPU/NPU, discover resource keys before writing values:
   ```bash
   kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.name):\n" + (.status.allocatable | to_entries | map(select(.key | test("gpu|npu|vpu|accel";"i"))) | map("  \(.key): \(.value)") | join("\n"))'
   ```
   Common Intel keys are `gpu.intel.com/i915`, `gpu.intel.com/xe`, and `npu.intel.com/accel`.

## 1. Start from the real chart values

Work from the chart directory:
```bash
cd sample-applications/video-search-and-summarization/chart
helm dependency update
helm dependency list
```

Create/edit `user_values_override.yaml` for user-specific values. Do not commit filled secrets.

Minimum required values for most modes:
```yaml
global:
  usePvc: true
  keepPvc: true
  huggingfaceToken: "hf_..."   # needed for gated/private Hugging Face models
  vlmName: "Qwen/Qwen3-VL-4B-Instruct"
  llmName: ""                  # optional OVMS split-model summarization model
  embeddingModelName: ""       # set per mode below
  modelDownload:
    image:
      repository: intel/model-download
      tag: "2026.2.0-ww30"
      pullPolicy: IfNotPresent
    ovmsReleaseTag: "v2026.1"
  proxy:
    http_proxy: ""
    https_proxy: ""
  env:
    POSTGRES_USER: "vsadmin"
    POSTGRES_PASSWORD: "change-me"
    MINIO_ROOT_USER: "minioadmin"
    MINIO_ROOT_PASSWORD: "change-me-8chars"
    RABBITMQ_DEFAULT_USER: "guest"
    RABBITMQ_DEFAULT_PASS: "change-me"

# Summary/OVMS model workspace:
ovms:
  claimSize: "20Gi"

# Search model caches (needed only when search is enabled):
multimodaldataprep:
  modelPvc:
    enabled: true
    size: "10Gi"
multimodalembeddingms:
  modelPvc:
    enabled: true
    size: "10Gi"
```

Why these matter:
- `global.usePvc` enables the service-specific claims; OVMS, video-ingestion, Multimodal DataPrep, and the embedding service no longer share one PVC.
- `global.keepPvc: true` avoids re-downloading/re-converting models after uninstall, but stale PVCs can also preserve incompatible old state. The vLLM
  subchart's `vllm-model-cache` PVC does not currently honor `global.keepPvc`
  and is deleted with the release.
- `ovms.claimSize` sizes the summary-mode OVMS model workspace.
- `multimodaldataprep.modelPvc` and `multimodalembeddingms.modelPvc` independently configure search model caches.
- `global.vlmName` is required for summary/unified modes and is used by OVMS or by vLLM.
- `global.embeddingModelName` is required when search components are enabled.
- `global.modelDownload` controls the image used by the OVMS and video-ingestion
  init containers. Each init container starts its local REST service, submits a
  download job, waits for completion, and exits before the application
  container starts.

## 2. Choose the mode using the real override files

Use exactly these chart override files:

| Docker/setup concept | Helm command files | What the chart enables |
|---|---|---|
| `source setup.sh --summary` | `-f summary_override.yaml -f user_values_override.yaml` | `rabbitmq`, `ovms`, `videoingestion`, `audioanalyzer`, `summaryui`; `pipelinemanager.env.SUMMARY_FEATURE=FEATURE_ON` |
| `--summary` with `ENABLE_VLLM=true` | `-f summary_override.yaml -f xeon_vllm_values.yaml -f user_values_override.yaml` | summary mode plus `vllm.enabled=true`, `ovms.enabled=false`, `pipelinemanager.env.USE_VLLM=CONFIG_ON` |
| `source setup.sh --search` | `-f search_override.yaml -f user_values_override.yaml` | `multimodalembeddingms`, `multimodaldataprep`, `vdmsvectordb`, `vectorretriever`, `videosearch`, `searchui`; `global.vdmsIndexName=video_frame_embeddings` |
| `VECTORDB_BACKEND=milvus` + `source setup.sh --search` | `-f search_override.yaml -f search_milvus_override.yaml -f user_values_override.yaml` | switches search backend to Milvus (`global.vectordbBackend=milvus`), enables `milvusstandalone`, disables `vdmsvectordb`, keeps `multimodaldataprep` + `vectorretriever` + `videosearch` |
| `--summary-and-search` / `--all` / `--unified` | `-f unified_summary_search.yaml -f user_values_override.yaml` | combined search+summary in one `summaryui` named `unified-ui`; `global.vdmsIndexName=video_summary_embeddings` |
| unified with vLLM | `-f unified_summary_search.yaml -f xeon_vllm_values.yaml -f user_values_override.yaml` | unified mode plus vLLM backend |
| dual separate UIs | `-f summary_override.yaml -f search_override.yaml -f user_values_override.yaml` | both `summaryui` and `searchui`; nginx routes `/summary/` and `/search/` |

Embedding model rule:
- Search-only and dual UI use a multimodal embedding model, for example `global.embeddingModelName: "CLIP/clip-vit-b-32"`.
- Unified summary+search uses a text embedding model, for example `global.embeddingModelName: "QwenText/qwen3-embedding-0.6b"`.

## 3. Install

Create a namespace once:
```bash
export NAMESPACE=vss-deployment
kubectl create namespace "$NAMESPACE"
```

Summary with OVMS CPU:
```bash
helm install vss . \
  -f summary_override.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

Summary with vLLM on Xeon CPU:
```bash
helm install vss . \
  -f summary_override.yaml \
  -f xeon_vllm_values.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

Search only:
```bash
helm install vss . \
  -f search_override.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

Unified summary+search:
```bash
helm install vss . \
  -f unified_summary_search.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

Dual separate UIs:
```bash
helm install vss . \
  -f summary_override.yaml \
  -f search_override.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

Before switching modes, uninstall the release first because the enabled subcharts and UI routing change:
```bash
helm uninstall vss -n "$NAMESPACE"
```

## 4. GPU/NPU and vLLM values

OVMS GPU VLM example:
```yaml
global:
  vlmName: "OpenVINO/Phi-3.5-vision-instruct-int8-ov"
  devices:
    ovms:
      vlm:
        device: GPU
        key: "gpu.intel.com/i915"
      llm:
        device: CPU
        key: ""
```

OVMS split model, e.g. GPU VLM + NPU LLM:
```yaml
global:
  vlmName: "OpenVINO/Phi-3.5-vision-instruct-int8-ov"
  llmName: "OpenVINO/Qwen3-8B-int4-cw-ov"
  devices:
    ovms:
      vlm:
        device: GPU
        key: "gpu.intel.com/i915"
      llm:
        device: NPU
        key: "npu.intel.com/accel"
ovms:
  env:
    VLM_WEIGHT_FORMAT: ""   # auto: CPU int8, GPU/NPU int4
    LLM_WEIGHT_FORMAT: ""
```

Search GPU for embedding/dataprep:
```yaml
global:
  devices:
    multimodalEmbedding:
      device: GPU
      key: "gpu.intel.com/i915"
    multimodalDataprep:
      embedding:
        device: GPU
        key: "gpu.intel.com/i915"
      detection:
        device: CPU
        key: ""
```

Use `global.devices.multimodalDataprep.embedding` for in-process DataPrep
embedding, `global.devices.multimodalEmbedding` for the query-side embedding
service, and `global.devices.multimodalDataprep.detection` for DataPrep object
detection. These settings are independent; every GPU/NPU setting requires its
own resource `key`.

vLLM tuning keys from the actual `vllm` subchart:
```yaml
vllm:
  enabled: true
  pvc:
    size: 80Gi
  env:
    vllmCpuKvCacheSpace: "48"
    vllmRpcTimeout: "100000"
    vllmAllowLongMaxModelLen: "1"
    vllmEngineIterationTimeoutS: "120"
    vllmCpuNumReservedCpu: "0"
    vllmLoggingLevel: "INFO"
  model:
    dtype: bfloat16
    maxModelLen: 32000
    maxNumBatchedTokens: 2048
    maxNumSeqs: 256
    tensorParallelSize: 1
  resources:
    requests:
      cpu: "16"
      memory: 128Gi
    limits:
      cpu: "16"
      memory: 128Gi
```

Prefer using `xeon_vllm_values.yaml` rather than hand-setting all of this; it also sets `pipelinemanager.env.USE_VLLM=CONFIG_ON` and resource requests for dependent services.

## 5. Upgrade safely

After editing values, keep the same override-file stack used at install:
```bash
helm upgrade vss . \
  -f summary_override.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

For vLLM summary:
```bash
helm upgrade vss . \
  -f summary_override.yaml \
  -f xeon_vllm_values.yaml \
  -f user_values_override.yaml \
  -n "$NAMESPACE"
```

If changing subchart code or dependencies:
```bash
helm dependency update
```

## 6. Verify

Watch pods; first startup may take 20–50 minutes because models are downloaded/converted:
```bash
kubectl get pods -n "$NAMESPACE" -w
kubectl get svc -n "$NAMESPACE"
```

Get the NodePort URL. The release name `vss` makes nginx service `vss-nginx`:
```bash
VSS_HOST=$(kubectl get pods -l app=vss-nginx -n "$NAMESPACE" -o jsonpath='{.items[0].status.hostIP}')
VSS_PORT=$(kubectl get service vss-nginx -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}')
echo "http://${VSS_HOST}:${VSS_PORT}"
```

UI paths:
- Summary/search/unified singleton modes: `/`
- Dual UI mode: `/summary/` and `/search/`; root redirects to `/summary/`

Check logs for slow or failed startup:
```bash
kubectl logs -n "$NAMESPACE" deploy/vss-pipelinemanager
kubectl logs -n "$NAMESPACE" deploy/vss-nginx
kubectl get events -n "$NAMESPACE" --sort-by=.lastTimestamp
```

When OVMS or video ingestion is stuck in `Init`, inspect the pod's
model-download init container:

```bash
kubectl describe pod -n "$NAMESPACE" <pod-name>
kubectl logs -n "$NAMESPACE" <ovms-pod> -c download-vlm
kubectl logs -n "$NAMESPACE" <ovms-pod> -c download-llm   # split-model mode only
kubectl logs -n "$NAMESPACE" <video-ingestion-pod> -c od-model-downloader
```

OVMS metrics, when `ovms.enabled=true`:
```bash
kubectl port-forward svc/vss-nginx 8081:80 -n "$NAMESPACE"
curl http://localhost:8081/ovms/metrics
```

## 7. Common fixes

- Helm fails with missing credentials: fill `global.env.POSTGRES_USER`, `global.env.POSTGRES_PASSWORD`, `global.env.MINIO_ROOT_USER`, `global.env.MINIO_ROOT_PASSWORD`, `global.env.RABBITMQ_DEFAULT_USER`, `global.env.RABBITMQ_DEFAULT_PASS`.
- Helm fails with GPU key errors: set `global.devices.*.key` for every non-CPU device.
- Model download job/init container fails: inspect the specific model-download
  log, verify `global.modelDownload.image`, proxy/token values, model id, device
  support, and available model storage before debugging the main container.
- Helm fails with a missing device key: set the matching `key` for any
  `global.devices.*` entry set to `GPU` or `NPU`.
- Search returns bad/no results: confirm `global.embeddingModelName` matches the mode and `global.vdmsIndexName` came from the right override file.
- Reinstall still broken with `global.keepPvc: true`: stale PVC contents may be incompatible. Identify the affected mode and delete only its PVCs after the user accepts losing cached models/data.:
  ```bash
  # Summary with OVMS:
  kubectl delete pvc vss-ovms-pvc -n "$NAMESPACE"

  # Search model caches:
  kubectl delete pvc vss-multimodaldataprep-models-pvc \
    vss-multimodalembeddingms-models-pvc -n "$NAMESPACE"
  ```
- Need larger storage: set `ovms.claimSize` for converted VLM/LLM models,
  `videoingestion.claimSize` for OD models,
  `multimodaldataprep.modelPvc.size`/`multimodalembeddingms.modelPvc.size` for
  search model caches, or the relevant data setting such as
  `minioserver.claimSize`, `postgresql.claimSize`, `vdmsvectordb.claimSize`, or
  `vllm.pvc.size`.
