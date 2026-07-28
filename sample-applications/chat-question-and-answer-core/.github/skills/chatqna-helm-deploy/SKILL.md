---
name: chatqna-helm-deploy
description: >
  Deploy Chat Question-and-Answer Core to Kubernetes using Helm (OpenVINO CPU, OpenVINO GPU, or Ollama),
  including values.yaml configuration, helm install/upgrade, deployment verification, uninstall,
  and translation from Docker Compose setup_env.sh variables into Helm override values.
  Use this skill  when the user says "deploy chatqna core to kubernetes", "helm install chatqna-core",
  "configure values.yaml", "convert compose config to helm", or "translate setup_env.sh to chart values".
metadata:
  version: "1.0.0"
  tags: "chatqna kubernetes helm values yaml openvino ollama gpu cpu deploy"
argument-hint: >
  Describe runtime, namespace, chart source, and configuration intent, for example "install openvino gpu in namespace ai with custom models" or "convert compose env to helm overrides and deploy ollama".
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Helm Deploy

Deploy the Chat Question and Answer Core sample application Helm chart at `sample-applications/chat-question-and-answer-core/chart/` to Kubernetes using
Helm. The chart's dependencies are `chatqna-core` and `chatqna-ui`, which are built from the same source code as the Docker Compose deployment. Also it includes `nginx` as a reverse proxy for the backend and UI.

Codebase root: `sample-applications/chat-question-and-answer-core/`

## Prerequisites

1. Confirm a reachable Kubernetes cluster is available and `kubectl` is configured to access it.
   ```bash
	 kubectl get nodes
	 ```

2. For GPU, discover resource keys before writing values:
   ```bash
	 kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.name):\n" + (.status.allocatable | to_entries | map(select(.key | test("gpu|npu|vpu|accel";"i"))) | map("  \(.key): \(.value)") | join("\n"))'
	 ```
	 Common Intel keys are `gpu.intel.com/i915`, `gpu.intel.com/xe`

## What This Skill Produces

- A running ChatQnA Core Helm release in a target namespace for one runtime:
	- OpenVINO CPU
	- OpenVINO GPU
	- Ollama
- A generated override file (`values-override.yaml`) that translates
	Docker Compose and `setup_env.sh` style inputs to Helm values keys.
- A verified deployment state using pods, services, and health endpoint checks.
- A concise deployment report containing:
	- runtime selected and GPU mode
	- chart source (local path or OCI chart)
	- values files used and major override keys
	- access URL and API docs URL
	- warnings (missing token, GPU key, model constraints)

## When to Use

- "Deploy chatqna core to Kubernetes"
- "Helm install chatqna-core"
- "Configure values.yaml for chatqna core"
- "Translate docker compose setup_env.sh into helm values"
- "Deploy OpenVINO GPU profile with Helm"
- "Deploy Ollama with chart values"

## Inputs To Confirm

Before running commands, confirm or infer these values:

1. Runtime: `openvino` or `ollama`
2. Device target: `cpu` or `gpu` (GPU valid only for OpenVINO)
3. Namespace and release name (default release: `chatqna-core`)
4. Chart source:
	- local chart path (`./chart`), or
	- OCI chart (`oci://registry-1.docker.io/intel/chat-question-and-answer-core`)
5. Image source and tags:
	- prebuilt registry tags, or
	- custom/private registry and tags
6. Model settings (`EMBEDDING_MODEL`, `LLM_MODEL`, optional `RERANKER_MODEL`)
7. Optional Hugging Face token (`HUGGINGFACEHUB_API_TOKEN`) for OpenVINO
8. Optional proxy values (`http_proxy`, `https_proxy`, `no_proxy`)

If runtime/device values are missing, default to `openvino` + `cpu`.

If prebuilt images are used and tags are not specified by the user, default to
the tags in `chart/values.yaml`.

Use Helm and kubectl commands for deployment actions in this skill.

## Decision Logic

- If runtime is `ollama`:
	- select `-f values.yaml -f values-ollama.yaml`
	- force CPU-only devices
- If runtime is `openvino` and device is `gpu`:
	- select `-f values.yaml -f values-openvino.yaml`
	- set `gpu.enabled=true`
	- require `gpu.key` from cluster labels
- If runtime is `openvino` and device is `cpu`:
	- select `-f values.yaml -f values-openvino.yaml`
	- set `gpu.enabled=false`
- If requested values conflict with chart validation (for example GPU model
	device with `gpu.enabled=false`), correct values before install.

## Compose and setup_env.sh Translation

Use the reference mapping in
[`./references/compose-setupenv-to-helm-mapping.md`](./references/compose-setupenv-to-helm-mapping.md) if the user asks to map Compose or `setup_env.sh` inputs to Helm values.

## Deployment Workflow

Run from `sample-applications/chat-question-and-answer-core`.

### 1. Preflight

```bash
kubectl version --client
helm version
kubectl config current-context
```

If using local source chart:

```bash
cd chart
helm dependency build
```

If using OCI chart:

```bash
helm pull oci://registry-1.docker.io/intel/chat-question-and-answer-core --version <version>
tar -xvf chat-question-and-answer-core-<version>.tgz
cd chat-question-and-answer-core
helm dependency build
```

Ensure namespace exists:

```bash
kubectl create namespace <namespace> --dry-run=client -o yaml | kubectl apply -f -
```

### 2. Build values override file

Create or update `values-override.yaml` by translating user intent or
Compose/setup_env style inputs using the reference mapping. Do not commit filled secrets or tokens.

If running behind a proxy, include these keys in `values-override.yaml` using
the values from your current system environment:

```yaml
global:
	http_proxy: "${http_proxy}"
	https_proxy: "${https_proxy}"
	no_proxy: "${no_proxy}"
```

Select base files by runtime:

- OpenVINO: `values.yaml` + `values-openvino.yaml` + `values-override.yaml`
- Ollama: `values.yaml` + `values-ollama.yaml` + `values-override.yaml`

### 3. Validate rendered manifests

```bash
helm template chatqna-core \
	-f values.yaml \
	-f values-<runtime>.yaml \
	-f values-override.yaml \
	.
```

### 4. Install or upgrade release

```bash
helm upgrade --install chatqna-core \
	-f values.yaml \
	-f values-<runtime>.yaml \
	-f values-override.yaml \
	. \
	--namespace <namespace>
```

### 5. Verify deployment

```bash
kubectl get pods -n <namespace>
kubectl get services -n <namespace>
kubectl get events -n <namespace> --sort-by=.lastTimestamp | tail -n 30
kubectl rollout status deploy/chatqna-core -n <namespace>
kubectl rollout status deploy/chatqna-core-nginx -n <namespace>
```

Health endpoint evidence:

```bash
chatqna_hostip=$(kubectl get pods -l app=chatqna-core-nginx -n <namespace> -o jsonpath='{.items[0].status.hostIP}')
chatqna_port=$(kubectl get service chatqna-core-nginx -n <namespace> -o jsonpath='{.spec.ports[0].nodePort}')
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${chatqna_hostip}:${chatqna_port}/v1/chatqna/health"
```

### 6. Access and teardown

```bash
# UI
echo "http://${chatqna_hostip}:${chatqna_port}"

# API docs
echo "http://${chatqna_hostip}:${chatqna_port}/v1/chatqna/docs"

# Uninstall
helm uninstall chatqna-core -n <namespace>
```

## Failure Handling

- Helm template validation fails:
	- report exact key causing failure and propose corrected key/value.
- GPU requested but `gpu.key` missing:
	- instruct user to run `kubectl describe node` and provide device plugin key,
		then re-run with `gpu.enabled=true`.
- Pods not ready:
	- collect `kubectl describe pod` and `kubectl logs` for failing pods.
- Health check non-200:
	- inspect `chatqna-core` logs for model download/config issues.
	- note first startup can take longer due to model pull/conversion.
- PVC stuck:
	- list and optionally delete stuck PVC only when explicitly requested.
- Need larger storage:
  - increase PVC size in `values-override.yaml` and re-run `helm upgrade`.

## Completion Criteria

1. Runtime-specific install command is executed with correct values files.
2. Compose/setup_env inputs (if provided) are translated into a concrete
	 `values-override.yaml`.
3. Pods/services are healthy in the target namespace.
4. Health endpoint returns `HTTP_STATUS:200`.
5. User receives UI URL, API docs URL, release/namespace, and uninstall command.
6. Response includes raw verification evidence (`kubectl get`, rollout status,
	 health check output).
