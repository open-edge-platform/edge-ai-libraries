# OKF extractor service

A standalone, synchronous REST service that accepts a **task containing multiple
content blobs or shared file references** and returns **JSON with the completed
OKF bundle's relative path**. Input files and output folders live in a shared
upload directory, not in HTTP uploads/downloads or ZIP archives. The service
does not require the engine's Python/model-runtime dependencies.

## Two-stage pipeline

1. **Plan instructions.** Decode every source, review its complete text in bounded
   chunks, then synthesize corpus-specific instructions. Large sets of reviews
   are reduced hierarchically; no first-file sampling or tail truncation is used.
   The generated segments match the `instructions` section in
   [config.yaml](config.yaml): `DOMAIN`, `GRANULARITY`,
   `TITLE_RULES`, `RELATION_RULES`, `MERGE_STANCE`, `ESCALATION_RULES`, `TYPE_HINTS`.
2. **Extract OKF.** Use those instructions in bounded, whitelisted read/write
   tool sessions. Long sources are fragmented before extraction so every read
   fits the configured line/byte/token limits. Fold identical titles, optionally
   canonicalize entity variants using the generated merge rules, resolve links,
   and write the final bundle. Fragment provenance is restored to the original
   task source paths.

The completed bundle directory contains:

- A bundle index and one Markdown concept per type/title, with mandatory
  `source_files` and body relation links.
- A generated YAML instruction artifact (the non-secret task configuration).
- A task manifest containing `task_id`, concept count and source path/asset-ID
  mappings. No original documents or model credentials are included.
- Escalation findings, when present. Service tasks never block for human input.

## Run locally

From the repository root, using an activated virtual environment:

```sh
pip install -r data-intelligence-engine/tools/okf_extractor/requirements.txt
export OKF_EXTRACTOR_LLM_BASE_URL=http://localhost:8000/v1
export OKF_EXTRACTOR_LLM_MODEL=Qwen/Qwen3.5-122B-A10B
export ENGINE_UPLOAD_DIR="$PWD/engine/workspace/uploads"
PYTHONPATH=data-intelligence-engine/tools python -m okf_extractor
```

Use an OpenAI-compatible model that supports tool calls. `/docs` exposes the
OpenAPI UI, `/openapi.json` the schema, and `GET /health` a liveness check (not a
model readiness probe).

| Environment variable | Default / purpose |
|---|---|
| `OKF_EXTRACTOR_HOST` | `0.0.0.0` |
| `OKF_EXTRACTOR_PORT` | `8080` |
| `OKF_EXTRACTOR_CONFIG` | Bundled [config.yaml](config.yaml) |
| `OKF_EXTRACTOR_LLM_BASE_URL` | Override configured model base URL, including `/v1` |
| `OKF_EXTRACTOR_LLM_MODEL` | Override configured model name |
| `OKF_EXTRACTOR_LLM_API_KEY` | Override configured model credentials |
| `OKF_EXTRACTOR_API_KEY` | Optional service bearer token; empty disables authentication |
| `ENGINE_UPLOAD_DIR` | Shared input/output root; defaults to the engine workspace's uploads directory |
| `ENGINE_WORKSPACE` | Optional workspace root used to derive the upload default |
| `OKF_EXTRACTOR_MAX_TASK_BYTES` | `67108864` (64 MiB), applied to input files/blobs and normalized content |

Put a request-body/concurrency limit at the ingress when exposing the service to
untrusted clients. Task bodies are parsed before the content limit is
checked. The API is synchronous: set engine/ingress timeouts for the full corpus
review **and** extraction duration. There is no background task queue or polling.
Private working directories are cleaned after success/failure. Completed bundles
remain on the shared filesystem until their caller consumes or deletes them.

## JSON tasks: `POST /v1/tasks`

```json
{
  "task_id": "customer-corpus-01",
  "items": [
    {
      "path": "profiles/customer.md",
      "asset_id": "customer-asset",
      "media_type": "text/markdown",
      "file_path": "reports/customer.md"
    },
    {
      "path": "notes.txt",
      "content": "Ada owns the project."
    }
  ],
  "options": {
    "language": "en",
    "goal": "Capture recurring entities and their supported relationships",
    "instructions": {
      "MERGE_STANCE": "Merge only when the stable identity is unambiguous."
    }
  }
}
```

`task_id` is optional (generated when absent). Each item needs a unique safe
relative POSIX `path` and **exactly one** of `content` (already-decoded UTF-8 text)
or `file_path` (a file **relative to `ENGINE_UPLOAD_DIR`**). `path` is the logical
source name used in OKF `source_files`; `file_path` is where its bytes actually
live. In this example, create the customer document in the shared root's reports
subdirectory before submitting. `asset_id` and `media_type` are optional. Inline
text blobs may retain a PDF filename; file references are decoded according to
their physical filename/MIME type. No arbitrary URLs or absolute filesystem
paths are fetched. Tasks support up to 1000
sources; parent traversal, hidden paths, duplicate names and path conflicts are
rejected. Symlinked files and directory components are rejected too.

Binary file readers support PDF text, DOCX paragraphs/tables and all XLSX/XLSM
worksheets. Other files must be UTF-8 text (including Markdown, CSV, JSON, HTML).
Scanned PDFs without extractable text require OCR **before** submission; engine
assets use their persisted, already-extracted text/captions instead of re-reading
the original binary. Empty or unsupported content fails explicitly.

A successful response is `200 application/json`, with `X-OKF-Task-ID`:

```json
{
  "task_id": "customer-corpus-01",
  "bundle_path": "okf-extractor/customer-corpus-01/bundle",
  "concept_count": 12
}
```

Read the bundle directly beneath your own shared upload mount using
`bundle_path`. The directory is published atomically only after both extraction
stages and its manifest finish. No archive is created or returned. Errors use
standard FastAPI JSON: `401` authentication, `409` duplicate/running task,
`413` content size limit, `422`
invalid/unreadable task or unsuccessful extraction, `502` model transport or
planning-response error. Model output failures are not request-schema failures.
Errors from accepted tasks include `X-OKF-Task-ID`; the engine records the
service's error detail (not just its HTTP status) in the source failure status.

## Shared file exchange

Mount the same physical upload directory into the engine and extractor. Their
absolute mount locations may differ: all API paths are relative to each
process's configured upload root. Both processes need read/write permission.

The engine writes normalized asset text/captions to task-specific source files.
Each item's logical `path` is the document's location under the upload root
(`<library-id>/02_theft.md`), so logs and OKF `source_files` name the real file;
documents stored elsewhere use `<hash of asset ID>/<file name>`. It posts **only file
references and task options**, reads the resulting bundle locally, and publishes
it as an `okf` asset of the pool (`uploads/<library-id>/okf-extracted/...`). File-only assets already in the upload root are
referenced in place; files outside it are staged locally first. Original shared
uploads are never deleted by the extractor or engine client.

There is no multipart endpoint or base64-file input. An external caller should
put files into the shared folder and pass `file_path`. Inline `content` remains
available for small text blobs.

Completed task IDs cannot be overwritten or run concurrently; submit a fresh
ID for a new extraction. The engine removes its task staging directory once a
bundle is safely published. If no destination is requested, the completed
bundle stays in the shared task folder. Failed/timed-out task inputs are retained
for diagnosis because the service may still be reading them. Remove abandoned
task directories (including stale running markers after a crash) only after
confirming that no extraction is using them. Direct API callers own cleanup of
their source files and completed bundles.

When service authentication is enabled, add `Authorization: Bearer <token>`.
Model credentials and the shared root are deployment settings, not task options.

## Task options

`language` controls summary language, `goal` guides planning, and non-empty
`instructions` segments override the generated segments. Non-empty operator
segments in the server config are defaults for those overrides. The planning
pass still runs over all sources even when overrides are provided. Task options
cannot change model endpoints, tool implementations, prompt template paths,
filesystem locations or execution limits.

Planning budgets are configured under `planning`; extraction read/session
budgets under `batch`; optional canonicalization under `merge` in the server
configuration. Each extraction session may read
`llm.context_window * batch.safe_fraction - batch.reserve_tokens` tokens of input
(131072 * 0.3 - 6000 = 33321 by default; logged as `@ budget 33321` and
`2368/33321 tok used`) from at most `batch.max_files_per_batch` fragments, in at most
`batch.max_steps` model turns. `turn 18 (limit 60)` is a session that finished on
its own at turn 18; the limit is a cap, not a planned step count. The instruction artifact contains only the final seven segments,
not the LLM configuration.

`planning.summary_tokens` (1500) and `planning.max_tokens` (4096) are initial
review and instruction-output budgets. If the model reports `finish_reason=length`,
the same input is retried with a doubled output budget up to
`planning.max_response_tokens` (8192), always bounded by context headroom. No
truncated output is accepted or source text discarded. Exhausted retries report
the planning phase, finish reason and final token limit in a `502` response and
service log; reduce `planning.chunk_tokens` or raise the ceiling if needed.

Successful output allowances are reused for later requests in the same task and
phase. If a review-reduction group needs 3000 tokens, later groups start at 3000
instead of each repeating the 1500-token failure. Source reviews, reductions,
and final instruction synthesis have separate budgets; tasks never share learned
limits or change the server configuration. Every request still obeys its current
context headroom and `planning.max_response_tokens`.

### Tool-loop recovery and diagnostics

A planning log such as `truncated at max_tokens=1500; retrying ... 3000` followed
by `recovered with complete output` and `reviewed all content` means the planning
retry succeeded; it does not mean that the source was skipped. Reviews request
compact extraction-design notes, not an inventory of every fact in the document.
Reduction also requests compact notes while preserving distinct design rules
and uncommon exceptions. `reducing reviews: pass N, group X/Y` and
`condensed reviews: ...` show reduction progress; these are separate groups,
not a replay of the original source review.

Concept extraction tracks complete line coverage of each assigned fragment.
Readers report EOF explicitly and do not recharge or replay an already-read
fragment. A continuation uses only the offset supplied by a capped read; guessing
`offset=200` after EOF does not count as a successful read. Once all assigned
fragments are complete, the model is offered writing/escalation tools only.

`write_concept` errors name the rejected field/type (including nested relation
fields), not the raw argument payload. `source_files` must be a JSON array of
full fragment paths already read in the current batch, not their parent source
directory. Each tool call records one concept; several independent calls in one
model response are allowed. Exact duplicate writes are ignored.

Every call must repeat its own `source_files`; provenance is never inherited
from the previous concept. The tool schema lists only fragment paths already
read in that session, and correction feedback repeats those paths. The model
must select the subset supporting the concept; the extractor never fills in
missing citations or attributes a concept to every read file automatically.
Rejected writes remain unresolved by `(type, title)` until that same concept is
corrected. A valid write for another concept cannot clear the error, and a stop
with unresolved writes triggers bounded correction before batch retry/failure.

Links are optional per call. A session that finishes with several concepts and
no links at all is asked once to re-emit them with relations; the log shows
`no relations recorded — asking for links once`. Each write logs its link count,
and the final `links: kept N, dropped M with unknown targets (e.g. ...)` line
explains a bundle with few or no graph edges.

Truncated tool responses retry the same history with a larger output allowance
up to `batch.max_response_tokens` (8192); partial tool writes are never applied.
Once every assigned fragment is read, two turns that only re-send concepts
already recorded end the batch as complete (`model repeats recorded concepts
only — batch complete`); short documents otherwise stalled the whole task.
`batch.max_idle_steps` (4) bounds turns that only repeat reads or invalid calls,
and `batch.final_emit_steps` (4) reserves final turns for emitting concepts.
An incomplete batch shrinks in file count as well as tokens (`8 -> 4 -> 2 -> 1`)
and later sessions reuse the learned file cap. Strict task extraction requires
complete reads and a natural finish; it never treats `max_steps` as success.
Exhausted recovery returns `502` with the batch reason and latest tool error,
rather than blaming the request schema with `422`.

## Engine integration and deployment

The engine calls this service from a background extraction job, never from a
pool sync. A job submits all of the pool's document references in one request
and, after reading the shared result, ingests the bundle as an `okf` asset of
the pool -- visible in the engine's asset list -- and syncs the pool to build it.
It resolves task source paths to existing vector chunks by asset ID, including
inline documents and duplicate basenames; the job brings the vector sources up
to date first. The graph source's `external_extractor.trigger` decides when jobs
run: `auto` once document changes settle (`debounce_seconds`), `schedule` on a
cron expression, `manual` only on
`POST /v1/libraries/{library}/asset_pools/{pool}/extractions`. Re-extraction
updates the same bundle asset in place.

The auto delay starts after the engine's document materialization/vector sync.
Only a real document change extends an active job's deadline; repeated unchanged
syncs do not. A follow-up job waits only the remaining quiet time, not a second
full delay after a long extraction. Check the pool's effective
`extraction.trigger_options` and `extraction.active.not_before` to distinguish
the quiet timer, worker queue, and running extraction. Extractor settings must
be nested under the graph source's `operator_options.external_extractor` with
`asset_types: ["okf", "document"]`; a plain OKF-only graph source never starts
document extraction.

From the engine deployment directory, the optional
[extractor Compose stack](../../deployment/docker/docker-compose-okf-extractor.yml)
joins `ENGINE_NETWORK` (the same existing network as the engine). Configure
`OKF_EXTRACTOR_LLM_BASE_URL` and `OKF_EXTRACTOR_LLM_MODEL`, then launch it:

```sh
docker compose -f docker-compose-okf-extractor.yml up -d --build
```

Set a graph source's `external_extractor.url` to `http://okf-extractor:8080` and
match its `api_key` to `OKF_EXTRACTOR_API_KEY` if enabled. Increase its `timeout`
for multi-document tasks (for example 1800 seconds). No document volume mount
is sent over the API: both services must use the same writable upload volume.
The Compose stacks default to the uploads subdirectory of `ENGINE_WORKSPACE_PATH`,
mounted at `ENGINE_UPLOAD_DIR` (normally `/workspace/uploads`). Set the same
absolute `ENGINE_UPLOAD_PATH` in both stacks to share a different host folder.
The extractor runs as UID/GID `1000:1000` by default, matching the engine image;
set `OKF_EXTRACTOR_UID`/`OKF_EXTRACTOR_GID` to match the actual engine/file ownership
if your deployment differs. Do not fix permissions by running the service as root.

Extractor URLs and model endpoints are **trusted operator configuration** and
may intentionally address internal services. Restrict who can edit them; use
egress policy/allowlisting if the engine's source-configuration API is exposed
to untrusted callers.

The local CLI remains available and uses the identical two-stage pipeline:

```sh
PYTHONPATH=data-intelligence-engine/tools python -m okf_extractor.cli --data ./documents --out ./bundle
```

`--config`, `--limit`, `--no-progress` and local `--interactive` are retained.