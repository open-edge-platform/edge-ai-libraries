---
name: vss-e2e-smoke
description: Run this skill whenever the user asks to verify my VSS install works, smoke test VSS, check whether the deployment succeeded, or run an end-to-end test of summary/search for the video-search-and-summarization sample app. It provides one-command smoke tests that use the real Pipeline Manager and Search service APIs to upload a video, trigger summary or search embedding work, poll results, and print PASS/FAIL. Use it proactively for fresh deployments, mode changes, or suspected broken VSS services.
---

# VSS end-to-end smoke tests

Use this skill for the Video Search & Summarization sample application when a user wants a quick, real deployment check rather than unit tests. The bundled scripts exercise the same public APIs exposed by the running app.

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
# in-repo it is .github/skills/vss-e2e-smoke. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-e2e-smoke"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## Which smoke test to run

- **Summary mode (`source setup.sh --summary`)**: run `scripts/e2e_summary.sh`. It uploads a video through Pipeline Manager, starts the summary pipeline, polls state, verifies chunking, and requires a non-empty final summary.
- **Search mode (`source setup.sh --search`)**: run `scripts/e2e_search.sh`. It uploads a video through Pipeline Manager, creates search embeddings, queries the search service, and requires non-empty hits.
- **Dual mode (`source setup.sh --summary --search` or `--dual`)**: run both scripts. Summary and frame-search are independent capabilities.
- **Unified mode (`source setup.sh --summary-and-search`, `--search-and-summary`, `--all`, or `--unified`)**: run `scripts/e2e_summary.sh` first, then `scripts/e2e_search.sh`. Unified mode uses both summary and search services; if search is configured over summary text, the summary pass confirms the source content exists.

## Prerequisites

- Start VSS first with `source setup.sh --summary`, `--search`, `--dual`, or `--unified`.
- Default external API base is `http://localhost:12345/manager` through nginx (`APP_HOST_PORT=12345`). The scripts also accept a host root such as `http://localhost:12345` and will detect `/manager`.
- `curl`, `bash`, and `python3` must be available.
- Provide a streamable MP4 if the repository sample fallback is not suitable. The checked `APP_ROOT/data` directory currently contains no sample videos; see `references/sample-assets.md`.

## Commands

From this skill directory:

```bash
# Summary smoke; optional first arg is a video path, optional second arg is Pipeline Manager API base
./scripts/e2e_summary.sh [video.mp4] [http://localhost:12345/manager]

# Search smoke; optional first arg is a video path, optional second arg is Pipeline Manager API base
./scripts/e2e_search.sh [video.mp4] [http://localhost:12345/manager]
```

Useful environment overrides:

```bash
VSS_API_BASE=http://localhost:12345/manager   # upload, summary, embeddings, manager search
VSS_SEARCH_BASE=http://localhost:7890         # optional direct video-search service base for /query
VSS_QUERY='person walking near shelves'       # natural-language query for search smoke
VSS_TIMEOUT_SECONDS=1800                      # summary/search polling timeout
VSS_POLL_INTERVAL_SECONDS=5                   # poll interval
VSS_CHUNK_DURATION=10                         # summary sampling.chunkDuration
VSS_SAMPLING_FRAME=5                          # summary sampling.samplingFrame
VSS_FRAME_OVERLAP=0                           # summary sampling.frameOverlap; multiFrame is derived
VSS_EVAM_PIPELINE=object_detection            # summary evam.evamPipeline; API also allows video_ingestion
```

## Interpreting results

- `PASS` means the script reached the expected final condition using real HTTP calls.
- `FAIL` means the deployment is not ready, the wrong mode is running, the video was rejected, processing timed out, or a backend component returned an error.
- For summary, check the printed `videoId`, `stateId`, chunk counts, statuses, and summary excerpt.
- For search, check the printed `videoId`, embedding response, query text, and hit count.
- A failing health check usually points at `APP_HOST_PORT`, nginx, or Pipeline Manager. A failing search query with successful embedding usually points at `video-search`, VDMS, or embedding/dataprep services.

## Grounding

These scripts are grounded in the current app code:

- Pipeline Manager OpenAPI: `docs/user-guide/_assets/vss-api.yaml`
- nginx API prefix: `docs/user-guide/api-reference.md` says Pipeline Manager paths are prefixed with `/manager/` through nginx
- Upload: `POST /manager/videos` multipart field `video`
- Summary: `POST /manager/summary`, poll `GET /manager/states/{stateId}`
- Search embeddings: `POST /manager/videos/search-embeddings/{videoId}`
- Search query: direct search service `POST /query` with a list of `{query_id, query}`, or manager shim `POST /manager/search/query`
