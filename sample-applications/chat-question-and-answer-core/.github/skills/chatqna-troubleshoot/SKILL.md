---
name: chatqna-troubleshoot
description: >
  Troubleshoot Chat Question-and-Answer Core end-to-end across Docker Compose and Helm deployments,
  including startup failures, health/API errors, runtime mismatches (OpenVINO vs Ollama), model/config issues,
  UI access problems, and log-driven root-cause isolation with concrete fix steps.
  Use this skill whenever the user mentions "troubleshoot", "debug", "not working", "health check failed",
  "chat endpoint error", "container crash", "helm pod failing", "docs page unavailable", or similar symptoms,
  even if they do not explicitly ask for a troubleshooting workflow.
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "chatqna troubleshoot debug diagnostics docker compose helm openvino ollama api health logs"
argument-hint: >
  Describe symptom and environment, for example "docker deployment returns 500 on /chat",
  "helm pods crashloop in namespace chatqna", or "UI not reachable on port 8102".
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Troubleshooting

Systematic troubleshooting for Chat Question-and-Answer Core issues using repo-documented commands and runtime-aware checks.

Codebase root: `sample-applications/chat-question-and-answer-core/`

## Environment setup (run first)

This skill drives Chat Question-and-Answer Core through its real source files,
so the ChatQnA application must be present and commands must run from the app
root. Do this before any troubleshooting steps, whether or not the source is
already in your workspace.

Run the bundled bootstrap. It first tries to find an existing ChatQnA checkout
by walking up from the current directory and checking the enclosing git repo,
then reuses it without re-cloning. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/chat-question-and-answer-core` from `main`.

It prints the resolved app root on stdout:

```bash
# SKILL_DIR is this skill directory. In-repo it is:
# .github/skills/chatqna-troubleshoot
SKILL_DIR=".github/skills/chatqna-troubleshoot"
APP_ROOT="$(bash "$SKILL_DIR/scripts/chatqna-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`.

To use a fork/branch or a specific clone path, override these before running
the bootstrap script:

- `CHATQNA_REPO_URL`
- `CHATQNA_REPO_BRANCH`
- `CHATQNA_CLONE_DIR`
- `CHATQNA_FORCE_CLONE` (set to `1` to force clone)

## What This Skill Produces

- A symptom-to-root-cause troubleshooting path tailored to deployment mode:
  - Docker Compose deployment
  - Helm/Kubernetes deployment
  - Local build and unit test workflow
- Command evidence for each hypothesis tested (status, logs, endpoint output).
- A concise diagnosis summary:
  - observed symptom
  - validated root cause
  - exact corrective action
  - verification command confirming fix

## When to Use

- "ChatQnA is not working"
- "health endpoint fails"
- "chat returns 500"
- "containers keep restarting"
- "helm pod is crashlooping"
- "docs/openapi page is unavailable"
- "documents upload fails"
- "OpenVINO/Ollama runtime mismatch issues"

## Inputs To Confirm

Collect or infer these first:

1. Deployment type: `docker-compose` or `helm`
2. Runtime: `openvino` or `ollama`
3. Device mode for OpenVINO: `cpu` or `gpu`
4. Host/namespace context:
   - Docker: `HOST_IP` (default `127.0.0.1`)
   - Helm: namespace and release name
5. User-visible symptom and first failure point:
   - startup
   - UI reachability
   - API endpoint behavior
   - model/runtime errors
   - ingestion/chat failures

If any value is missing, infer from active services/logs and state assumptions explicitly.

## Diagnostic Decision Tree

1. If deployment does not start or pods/containers are not healthy:
   - run startup diagnostics first.
2. If deployment starts but UI/docs are unreachable:
   - run gateway/network diagnostics.
3. If health is up but `/chat` or `/documents` fails:
   - run API/runtime diagnostics.
4. If failures mention model loading, private model, or device:
   - run model/config diagnostics.
5. For Helm issues, include PVC and namespace checks.

## Troubleshooting Workflow

Run from `sample-applications/chat-question-and-answer-core` unless noted.

### 1. Baseline Environment Checks

Validate required tools and environment:

```bash
docker --version
```

For Docker deployment paths:

```bash
docker compose version
```

For Helm deployment paths:

```bash
helm version
kubectl version --client
```

If commands are missing, stop and report install prerequisites from docs.

### 2. Startup Diagnostics

#### Docker Compose

Ensure correct runtime profile export was done in the current shell:

```bash
# OpenVINO CPU
source scripts/setup_env.sh

# OpenVINO GPU
# source scripts/setup_env.sh -d gpu

# Ollama CPU
# source scripts/setup_env.sh -b ollama
```

Start and inspect:

```bash
docker compose -f docker/compose.yaml up -d
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml logs --tail=200
```

If GPU requested, verify render nodes:

```bash
ls -l /dev/dri/render*
```

If GPU nodes are absent, recommend CPU fallback and re-run with CPU profile.

#### Helm/Kubernetes

Check workload state:

```bash
kubectl get pods -n <namespace>
kubectl get svc -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
```

If PVC or scheduling blocks startup, inspect PVC and node constraints:

```bash
kubectl get pvc -n <namespace>
```

If stale PVC blocks recovery, delete only the affected PVC after user confirmation:

```bash
kubectl delete pvc <pvc-name> -n <namespace>
```

### 3. Gateway and Reachability Diagnostics

Probe gateway endpoints through nginx exposure on port 8102:

```bash
HOST_IP=${HOST_IP:-127.0.0.1}
BASE_URL="http://${HOST_IP}:8102/v1/chatqna"

curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/health"
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP}:8102/v1/chatqna/docs"
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP}:8102/v1/chatqna/openapi.json"
```

If docs/openapi fail but containers are up, check nginx container logs and service exposure.

### 4. API and Runtime Diagnostics

Validate model and runtime-specific endpoints:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/model"
```

OpenVINO runtime checks:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/devices"
```

Ollama runtime checks:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/ollama-models"
```

Chat check (non-stream for deterministic troubleshooting evidence):

```bash
curl -sS -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"input":"health-check prompt","stream":false}' \
  -w "\nHTTP_STATUS:%{http_code}\n"
```

Interpretation guidance:

- `422` on `/chat`: malformed or empty `input` payload.
- `500` on `/chat`: backend inference/runtime/model failure; inspect backend logs.
- runtime endpoint mismatch (`/devices` on Ollama or `/ollama-models` on OpenVINO): profile mismatch.

### 5. Document Ingestion Diagnostics

List current documents:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/documents"
```

If upload fails:

- confirm format is one of `pdf`, `txt`, `docx`
- confirm request is multipart with `files` field
- inspect backend logs for embedding/model exceptions

Example upload probe:

```bash
curl -sS -X POST "${BASE_URL}/documents" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@./doc1.pdf" \
  -w "\nHTTP_STATUS:%{http_code}\n"
```

### 6. Model Configuration and Token Diagnostics

If symptoms mention missing model, auth errors, or unexpected model behavior:

1. Verify runtime-appropriate setup command was used.
2. Verify `MODEL_CONFIG_PATH` points to a readable YAML file if set.
3. For private/gated Hugging Face models on OpenVINO paths, verify token export in shell:

```bash
echo "${HUGGINGFACEHUB_API_TOKEN:+SET}"
```

4. If token is missing for a gated model, set token and restart deployment.

### 7. Build and Test Diagnostics (When Asked)

If the issue starts after code/image changes, run targeted checks:

```bash
# Build images from compose-defined build graph
docker compose -f docker/compose.yaml build

# Backend unit tests (select runtime)
RUNTIME=openvino uv run pytest -vv tests/
# or
RUNTIME=ollama uv run pytest -vv tests/

# UI unit tests
cd ui && npm test -- --runInBand
```

Use test failures to narrow likely regression area before redeploying.

## Common Root Causes and Fix Mapping

- Wrong runtime profile selected:
  - symptom: runtime-specific endpoints fail or model path mismatch.
  - fix: re-source correct setup script and restart services.
- GPU requested without GPU availability:
  - symptom: startup failures or device initialization errors.
  - fix: switch to CPU profile or correct GPU host configuration.
- Missing/invalid model configuration path:
  - symptom: model load errors at startup or first chat.
  - fix: correct `MODEL_CONFIG_PATH` and restart.
- Missing Hugging Face token for gated model:
  - symptom: model download/auth failure.
  - fix: export token and restart backend.
- Helm PVC stuck:
  - symptom: pods pending/crashloop due to volume mount issues.
  - fix: inspect and remove stale PVC, then redeploy.

## Reporting Format

Always finish with this structure:

1. Symptom observed
2. Checks run (commands + key outputs)
3. Root cause identified
4. Fix applied or recommended
5. Verification evidence after fix
6. Next fallback step if still failing

## Completion Criteria

1. Symptom reproduced or clearly characterized.
2. Relevant startup, endpoint, and log checks executed.
3. Root cause tied to evidence (not guesswork).
4. User receives exact command(s) to fix and verify.
5. Final state is either:
   - issue resolved with verification output, or
   - narrowed to one remaining blocker with next concrete action.
