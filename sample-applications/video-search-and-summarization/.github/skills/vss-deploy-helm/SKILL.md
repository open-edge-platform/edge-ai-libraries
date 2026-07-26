---
name: vss-deploy-helm
description: Use this skill whenever a developer needs to deploy VSS to Kubernetes, helm install VSS, configure values.yaml for VSS, or run VSS on k8s with GPU/vLLM for the video-search-and-summarization sample app. This skill is especially useful when translating Docker Compose/setup.sh modes (--summary, --search, --summary-and-search/--unified, dual UI, ENABLE_VLLM, OVMS GPU/NPU) into the actual Helm chart override files and values keys. Prefer this skill for VSS Helm install/upgrade/troubleshooting even if the user only says “put VSS on k8s” or “make values.yaml for VSS”.
---

# VSS Helm deploy

Use this workflow for the VSS sample app Helm chart at `sample-applications/video-search-and-summarization/chart`. The chart’s real dependencies are `ovms`, `minioserver`, `audioanalyzer`, `postgresql`, `rabbitmq`, `videoingestion`, `videosearch`, `vdmsvectordb`, `vdmsdataprep`, `multimodalembeddingms`, `vllm` (alias of `vllm-server`), `summaryui`, and `searchui` (aliases of `vssui`).

If the user asks to map Compose or `setup.sh` settings to Helm values, read `references/helm-values-map.md`.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-deploy-helm. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-deploy-helm"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

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
  sharedPvcName: vss-shared-pvc
  huggingfaceToken: "hf_..."   # needed for gated/private Hugging Face models
  vlmName: "Qwen/Qwen2.5-VL-3B-Instruct"
  llmName: ""                  # optional OVMS split-model summarization model
  embeddingModelName: ""       # set per mode below
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
```

Why these matter:
- `global.usePvc` and `global.sharedPvcName` control shared model/cache storage for `vdmsdataprep`, `multimodalembeddingms`, pipeline-manager collector signals, and OVMS model storage paths.
- `global.keepPvc: true` avoids re-downloading/re-converting models after uninstall, but stale PVCs can also preserve incompatible old state.
- `global.vlmName` is required for summary/unified modes and is used by OVMS or by vLLM.
- `global.embeddingModelName` is required when search components are enabled.

## 2. Choose the mode using the real override files

Use exactly these chart override files:

| Docker/setup concept | Helm command files | What the chart enables |
|---|---|---|
| `source setup.sh --summary` | `-f summary_override.yaml -f user_values_override.yaml` | `rabbitmq`, `ovms`, `videoingestion`, `audioanalyzer`, `summaryui`; `pipelinemanager.env.SUMMARY_FEATURE=FEATURE_ON` |
| `--summary` with `ENABLE_VLLM=true` | `-f summary_override.yaml -f xeon_vllm_values.yaml -f user_values_override.yaml` | summary mode plus `vllm.enabled=true`, `ovms.enabled=false`, `pipelinemanager.env.USE_VLLM=CONFIG_ON` |
| `source setup.sh --search` | `-f search_override.yaml -f user_values_override.yaml` | `multimodalembeddingms`, `vdmsdataprep`, `vdmsvectordb`, `videosearch`, `searchui`; `global.vdmsIndexName=video_frame_embeddings` |
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
    vdmsDataprep:
      device: GPU
      key: "gpu.intel.com/i915"
```

Why: the chart validates `global.devices.multimodalEmbedding.device` equals `global.devices.vdmsDataprep.device` when both subcharts are enabled, because they share storage and must schedule compatibly. Each GPU setting also requires its `key`.

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

OVMS metrics, when `ovms.enabled=true`:
```bash
kubectl port-forward svc/vss-nginx 8081:80 -n "$NAMESPACE"
curl http://localhost:8081/ovms/metrics
```

## 7. Common fixes

- Helm fails with missing credentials: fill `global.env.POSTGRES_USER`, `global.env.POSTGRES_PASSWORD`, `global.env.MINIO_ROOT_USER`, `global.env.MINIO_ROOT_PASSWORD`, `global.env.RABBITMQ_DEFAULT_USER`, `global.env.RABBITMQ_DEFAULT_PASS`.
- Helm fails with GPU key errors: set `global.devices.*.key` for every non-CPU device.
- Helm fails with embedding/dataprep pairing: set both `global.devices.multimodalEmbedding.device` and `global.devices.vdmsDataprep.device` to the same value.
- Search returns bad/no results: confirm `global.embeddingModelName` matches the mode and `global.vdmsIndexName` came from the right override file.
- Reinstall still broken with `global.keepPvc: true`: stale PVC contents may be incompatible. Delete the relevant PVC only if the user accepts losing cached models/data:
  ```bash
  kubectl delete pvc vss-shared-pvc -n "$NAMESPACE"
  ```
- Need larger storage: set `sharedClaimSize`, `minioserver.claimSize`, `postgresql.claimSize`, `ovms.claimSize`, `vdmsvectordb.claimSize`, or `vllm.pvc.size` as needed.
