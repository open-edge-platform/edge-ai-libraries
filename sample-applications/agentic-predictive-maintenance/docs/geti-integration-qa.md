# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Geti Integration for APM Blueprint — Q&A

Reference: ITEP-93500
Date: 2026-06-19

---

## Q1. What use-case does Geti + APM enable?

Geti enables **custom defect detection model training without writing training code**. A customer:
- Labels their own industrial images in Geti (weld defects, solar panel cracks, pipeline ruptures, pallet damage)
- Geti trains a detection model and exports it as OpenVINO IR
- APM blueprint immediately uses that model — no code changes, only config updates

This turns APM from a *demo with a pre-trained model* into a *production-grade tool for any quality-control use case*.

---

## Q2. Workflow and Architecture

```
┌─────────────────────────────────────────────────────────┐
│  DATA PREP / TRAINING (one-time, user-driven)           │
│                                                         │
│  Raw images ──► Geti (label / annotate)                 │
│                    │                                    │
│                    ► Train detection model              │
│                    ► Export → OpenVINO IR + config.json │
└────────────────────────────┬────────────────────────────┘
                             │ GETI_HOST + GETI_TOKEN
                             ▼
┌─────────────────────────────────────────────────────────┐
│  RUNTIME (model-download microservice)                  │
│                                                         │
│  models.yaml ──► POST /models/download                  │
│  { hub: geti, project_id, model_name, precision }       │
│        │                                                │
│        ► GetiPlugin → authenticates → downloads IR      │
│        ► writes model.xml + config.json to volume       │
└────────────────────────────┬────────────────────────────┘
                             │ named volume: apm_model_cache
                             ▼
┌─────────────────────────────────────────────────────────┐
│  INFERENCE (DL Streamer)                                │
│                                                         │
│  gvadetect model=<path>/model.xml                       │
│  labels read from config.json model_parameters          │
│  → publishes detections to MQTT                         │
└────────────────────────────┬────────────────────────────┘
                             ▼
              Agent pipeline (policy/analysis/evidence/ticket)
              reads labels from agents.yaml defect_classes
```

---

## Q3. Geti CV Model Support Prior to APM Alignment

The `GetiPlugin` (model-download) and DL Streamer already support these task types:

| Task Type | Geti Export | DL Streamer element |
|-----------|-------------|---------------------|
| **Detection** | OpenVINO SSD/YOLO IR | `gvadetect` |
| **Classification** | OpenVINO IR | `gvaclassify` |
| **Segmentation** | OpenVINO IR | `gvasegment` / UDF |
| **Anomaly Detection** | OpenVINO IR | Geti UDF (`geti_udf.py`) |

The Geti UDF in DL Streamer (`udfs/python/geti_udf.py`) handles complex Geti deployment packages
(with `demo_package/` Python wrappers). APM adds **MQTT publishing + agent pipeline** on top of
this existing inference capability.

---

## Q4. Replace `model_list.txt` with `models.yaml`

A YAML file captures Geti metadata, model path, labels, and download parameters in one place:

```yaml
# apps/pipeline-defect-detection/models/models.yaml
models:
  detection:
    hub: geti
    project_id: "67c1af441766e41edce24f08"
    name: "pipeline-defect-detection-v2"
    precision: FP16
    export_type: optimized
    output_path: detection/model.xml          # relative to USE_CASE_MODELS_DIR
    task_type: detection
    labels: [Rupture, Deformation, Disconnect, Obstacle]
    metadata:
      geti_version: "2.7"
      trained_date: "2026-06-01"
      dataset: "pipeline-defect-v3"
```

`setup.sh` / `model-download` reads this YAML instead of parsing a flat text file. The `labels`
field is the **single source of truth** that flows into both `pipeline-server-config.json` and
`agents.yaml`.

---

## Q5. Dataset Structure Assumptions for Geti Annotation

**Assumptions:**
- Dataset is a collection of images (JPEG/PNG), optionally with existing YOLO-format annotations
- `download_and_prep_data.py` produces the image dataset; user uploads images to a Geti project
- Geti project must be pre-created with the correct task type (Detection) and label schema matching `agents.yaml`

**Flow integration with APM:**

```
download_and_prep_data.py
    → datasets/<use-case>/images/{train,val}/
              │
              ▼ (user uploads to Geti UI or via geti-sdk)
         Geti Project (Detection task)
              │ user annotates / auto-annotates
              │ Geti trains model
              ▼
         models.yaml  →  project_id + model_name
              │
              ▼  setup.sh → model-download
         apm_model_cache/detection/model.xml
                                   config.json  (with labels)
```

**Key assumption:** Labels in the Geti project **must match** `defect_classes` in `agents.yaml`.
This coupling needs a validation step in `setup.sh` — parse `config.json` labels post-download
and warn if they diverge from `agents.yaml`.

---

## Q6. Geti Export Metadata in YAML

After `model-download` completes a Geti download, it returns a response dict with `model_name`,
`source`, `export_type`, `model_format`, `download_path`. This should be written as a
**model manifest** alongside the downloaded model:

```yaml
# <USE_CASE_MODELS_DIR>/detection/model_manifest.yaml
# Auto-generated by model-download on successful Geti download
model_name: pipeline-defect-detection-v2
source: geti
project_id: "67c1af441766e41edce24f08"
model_group_id: "..."
export_type: optimized
precision: FP16
model_format: OpenVINO
download_path: detection/model.xml
labels: [Rupture, Deformation, Disconnect, Obstacle]
downloaded_at: "2026-06-16T10:00:00Z"
geti_version: "2.7"
```

This manifest is used by `setup.sh` to skip re-download (idempotency) and by the agent service
to log which model version produced each detection batch.

---

## Q7. model-download Touchpoints with Geti

```
setup.sh
  │
  ├─ 1. READ models.yaml → extract { hub: geti, project_id, name, precision }
  │
  ├─ 2. CHECK if model_manifest.yaml exists in USE_CASE_MODELS_DIR
  │       └─ exists → skip download (cached)
  │
  ├─ 3. POST http://localhost:8200/models/download?download_path=/opt/models
  │       body: { models: [{ name, hub: "geti", config: { project_id, precision, export_type } }] }
  │       → GetiPlugin authenticates via GETI_HOST + GETI_TOKEN
  │       → fetches model.xml, model.bin, config.json
  │       → writes to /opt/models/geti/<name>/
  │
  ├─ 4. POLL GET /jobs/{job_id} until status = "completed"
  │
  ├─ 5. WRITE model_manifest.yaml from response metadata
  │
  └─ 6. START apm-dlstreamer (depends on step 4 completing)
```

**Env vars required in `.env_<use-case>`:**
- `GETI_HOST` — URL of Geti server
- `GETI_TOKEN` — API token
- `GETI_WORKSPACE_ID` — workspace ID (optional, uses default if unset)
- `GETI_SERVER_SSL_VERIFY` — set to `false` for self-signed certs (default: `false`)

---

## Q8. How `agents.yaml` is Updated

`agents.yaml` references `defect_classes` which must match Geti label names. Two approaches:

### Option A — Manual (current)
User edits `agents.yaml` to match Geti project labels. Simple but error-prone.

### Option B — Auto-sync from `config.json` (recommended)

After model-download completes, `setup.sh` reads `config.json` (Geti export) and
validates/updates `agents.yaml`:

```bash
# In setup.sh, post-download validation:
python3 scripts/sync_labels.py \
  --config   ${USE_CASE_MODELS_DIR}/geti/<name>/config.json \
  --agents   ${USE_CASE_CONFIGS_DIR}/agents.yaml \
  --warn-only   # warn if mismatch, don't overwrite
```

`config.json` from Geti already contains:
```json
{
  "task_type": "detection",
  "model_type": "ssd",
  "model_parameters": {
    "labels": "Rupture Deformation Disconnect Obstacle",
    "labels_ids": "..."
  }
}
```

This label string maps directly to `defect_classes` in `agents.yaml`.

**DL Streamer note:** `pipeline-server-config.json` does **not** reference label names directly —
`gvadetect` reads them from the model's `.xml` at inference time. Only `agents.yaml` needs
updating. The agent service stores whatever label string arrives via MQTT, so label changes
are automatically reflected in tickets without any pipeline restart.

---

## Open Questions / Next Steps

- [ ] Decide: `models.yaml` replaces `model_list.txt` — update US-2 AC
- [ ] Define `model_manifest.yaml` schema and where model-download writes it
- [ ] Implement `scripts/sync_labels.py` for label validation post-download
- [ ] Clarify Geti project creation step — manual (user) or scriptable via `geti-sdk`
- [ ] Confirm DL Streamer pipeline element for Geti models: `gvadetect` (standard IR) vs Geti UDF
- [ ] Add `GETI_HOST`, `GETI_TOKEN` to `.env_<use-case>` template with placeholder values
