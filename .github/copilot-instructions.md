# Edge AI Libraries – AI Agent Instructions

**Edge AI Libraries** is a monorepo of optimized libraries, microservices, tools, and sample applications for building and deploying real-time AI solutions on edge devices. Components span computer vision, multimedia analytics, generative AI, time-series analytics, and model lifecycle management.

Components are **independently versioned and deployable**. Each component under `libraries/`, `microservices/`, `tools/`, `frameworks/`, and `sample-applications/` is self-contained with its own Dockerfile, Makefile, Helm chart, and tests.

## Licensing Requirements (Critical – All Files)

**All files must include:**

- SPDX license header: `SPDX-License-Identifier: Apache-2.0`
- Copyright line: `(C) <YEAR> Intel Corporation` (use current year for new files)
- Example:
  ```python
  # SPDX-FileCopyrightText: (C) 2026 Intel Corporation
  # SPDX-License-Identifier: Apache-2.0
  ```
- **Enforcement**: REUSE/license compliance checked in CI (see `codeql.yaml`, `zizmor-scan.yaml`)

## Language-Specific Skills (Load On-Demand)

Consult these based on the code you're working with. Skills reside under `.github/skills/`.

| Skill file | When to load |
|---|---|
| `.github/skills/security.md` | Dockerfile, Compose, Helm, auth/authz, input parsing, dependency changes, CVE-related work |

> **Instruction Placement Policy**: Keep this file focused on high-level routing and architecture context. Detailed procedural checklists belong in skill files under `.github/skills/`. Avoid duplicating checklist content between this file and skills.

## Security Defaults (Always-On)

Apply secure-by-default behavior across all code generation, changes, and reviews, regardless of language or component.

- Prefer least privilege across code, services, identities, file permissions, APIs, containers, and workflows; avoid insecure defaults.
- Treat all external input as untrusted and validate format, type, range, and length at trust boundaries.
- Never hard-code or introduce secrets, credentials, keys, tokens, or passwords in source, tests, configs, or templates; use environment variables or approved secret-management mechanisms.
- Avoid exposing sensitive data in logs, traces, errors, metrics, or test artifacts.
- Prevent injection vulnerabilities by avoiding unsafe string construction and using safe, context-appropriate APIs.
- Prefer trusted, actively maintained dependencies and images; verify sources and pin versions where feasible.
- Avoid deprecated, unmaintained, or ambiguous packages.
- Do not suggest bypassing or weakening existing security checks or validations.
- Keep authorization checks server-side and close to protected resources.
- Avoid unsafe dynamic execution patterns (`eval`, `exec`, untrusted command construction).
- Prevent time-of-check/time-of-use (TOCTOU) race conditions in state-dependent checks (e.g., certificate validation.
- Do not assume trusted inputs, networks, or environments.
- Be explicit about assumptions and limitations.
- Fail safely and visibly.

## AI Output Trust Model

Treat AI-generated output as **untrusted draft code** until reviewed and tested.
Reject suggestions that bypass security controls for convenience or introduce unsafe defaults.

For detailed security review guidance, follow:
`.github/skills/security.md`.

## Repository Structure

```
edge-ai-libraries/
├── libraries/          # Reusable AI/ML libraries (anomalib, datumaro, geti-sdk, model_api, …)
├── microservices/      # Standalone deployable services (dlstreamer-pipeline-server, model-registry,
│                       #   time-series-analytics, vlm-openvino-serving, audio-analyzer, …)
├── sample-applications/# End-to-end reference apps (chat-qna, document-summarization, …)
├── tools/              # Developer tooling (npu-monitor-tool, visual-pipeline-evaluation, …)
├── frameworks/         # Edge device enablement framework
└── .github/
    ├── workflows/      # Per-component CI (dlsps-*, timeseries-*, GENAI-*, modelregistry-*, …)
    └── skills/         # On-demand AI agent skill files
```

### Key Microservices

| Microservice | Purpose |
|---|---|
| `dlstreamer-pipeline-server` | REST/gRPC-managed DL Streamer video analytics pipelines |
| `model-registry` | Model lifecycle management, versioning, and metadata store |
| `time-series-analytics` | Industrial time-series data processing and ML inference |
| `vlm-openvino-serving` | Vision-Language Model serving via OpenVINO |
| `audio-analyzer` | Audio classification and event detection |
| `model-download` | Model artifact download and caching service |
| `multimodal-embedding-serving` | Embedding generation for multimodal retrieval |
| `multilevel-video-understanding` | Hierarchical video understanding and summarization |
| `semantic-search-agent` | Vector-based semantic search agent |
| `vector-retriever` | Retrieval layer for vector database backends |
| `visual-data-preparation-for-retrieval` | Dataset preprocessing for visual retrieval pipelines |
| `document-ingestion` | Document parsing and indexing for RAG pipelines |

## Component Layout Convention

Each component follows a consistent layout:

```
<component>/
├── Dockerfile              # Container build definition
├── Makefile                # Standard targets: build, lint, test, coverage
├── README.md               # Quick start
├── helm/ or chart/         # Helm chart for Kubernetes deployment
├── docker/                 # Docker Compose files and supporting config
├── src/                    # Application source code
├── tests/                  # Unit and integration tests
├── docs/                   # Component documentation
├── requirements.txt         # Python runtime dependencies (or pyproject.toml / uv.lock)
└── document-versions.yaml  # Tracks documentation versioning
```

> Some newer components use `pyproject.toml` + `uv.lock` instead of `requirements.txt`. Prefer `uv` for lock-file-based installs in those components.

## Code Patterns & Conventions

**Python packaging**:
- Most microservices use `src/` layout with `requirements.txt` (or `pyproject.toml`)
- Newer components (`model-download`) use `uv` with a `uv.lock` lockfile — prefer `uv sync` over `pip install` in those components

**REST APIs**:
- Services expose HTTP REST APIs; refer to each component's `docs/` or `README.md` for endpoint definitions
- OpenAPI specs, where available, are under `docs/` or `src/rest_api/`

**Helm / Kubernetes**:
- Helm charts are under `<component>/helm/` or `<component>/chart/`
- Values files follow `values.yaml` (defaults) with override patterns documented in component `docs/`

**Configuration injection**:
- Runtime configuration via environment variables and mounted config files
- Secrets must use Docker Compose secrets, Kubernetes Secrets, or environment variable injection — never baked into images

**Observability**:
- OpenTelemetry instrumentation is present in some components (e.g., `dlstreamer-pipeline-server/src/opentelemetry/`)
- Enable via environment variables; refer to component documentation

**Documentation versioning**:
- `document-versions.yaml` in each component tracks doc artifact versions
- Update when publishing new component versions

## Common Developer Workflows

**Modifying a microservice** (example: `model-registry`):

1. Edit source in `<component>/src/`
2. Rebuild image: `make build`
3. Run tests: `make test`
4. Start service: `docker compose -f docker/docker-compose.yml up`
5. Review logs: `docker compose -f docker/docker-compose.yml logs -f`

**Adding a Python dependency**:
- `requirements.txt`-based: add to `requirements.txt`, rebuild image
- `pyproject.toml`/`uv`-based: `uv add <package>`, commit updated `uv.lock`

**Running linters**:

```bash
make lint
# or directly
pylint src/
yamllint .
```

## Integration Points & Dependencies

**External runtime services** (component-specific, declared in `docker/docker-compose.yml`):
- Vector databases: Milvus (semantic-search, vector-retriever, visual-data-preparation)
- LLM backends: OpenAI-compatible API or local OpenVINO model server
- Message brokers: Kafka or MQTT (where applicable in pipeline-server)
- Object storage: MinIO or equivalent (model-download, document-ingestion)

**OpenVINO**:
- Used across inference-serving microservices for optimized edge inference
- Model format: IR (`.xml` + `.bin`) or ONNX; see individual component docs

**DLStreamer**:
- GStreamer-based video analytics pipeline server
- Pipeline definitions via JSON or REST API; see `dlstreamer-pipeline-server/docs/`

## File Organization Essentials

- **`<component>/Makefile`**: Per-component build, lint, test, and coverage targets
- **`<component>/Dockerfile`**: Container build definition (production image)
- **`<component>/docker/`**: Docker Compose files and supporting configs for local development
- **`<component>/helm/`** or **`chart/`**: Helm chart for Kubernetes deployment
- **`<component>/src/`**: Application source code
- **`<component>/tests/`**: Unit and integration tests
- **`<component>/docs/`**: Component user guide and API documentation
- **`.github/workflows/`**: Per-component CI pipeline definitions
- **`.github/skills/security.md`**: On-demand security review skill

## Documentation Requirements (Always-On)

### When to update documentation

Update documentation immediately when making any of these changes:

- Adding new features, APIs, endpoints, or configuration options
- Modifying request/response formats or default behaviors
- Changing build targets, Makefile commands, or deployment procedures
- Updating dependencies or system requirements
- Adding or removing environment variables
- Publishing a new component version (update `document-versions.yaml`)

### Key documentation locations (per component)

- `<component>/README.md` — Quick start and overview
- `<component>/docs/user-guide/` — Full user guide, API reference, build-from-source guide
- `docs.openedgeplatform.intel.com` — Published cross-component documentation

## Quick Reference: New Microservice Checklist

When adding a new microservice under `microservices/`:

1. Create folder with `Dockerfile`, `Makefile`, `src/`, `requirements.txt` (or `pyproject.toml`)
2. Add standard Makefile targets: `build`, `lint`, `test`, `coverage`, `help`
3. Add `docker/docker-compose.yml` for local development
4. Add Helm chart under `helm/` with `Chart.yaml`, `values.yaml`, and templates
5. Create tests in `tests/` with appropriate test runner configuration
6. Add a CI workflow under `.github/workflows/` for PR validation and scanning
7. Create `README.md` and `docs/` with user guide and API reference
8. Add `document-versions.yaml` for documentation versioning
9. Ensure SPDX license headers are present in all source files
10. Register component in root `README.md` component table
