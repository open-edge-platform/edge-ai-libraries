<!-- Copyright (C) 2026 Intel Corporation
     SPDX-License-Identifier: Apache-2.0 -->

# Skills for agent

This directory ships ready-to-install skills that let an external agent query the
engine's retrieval API. A skill returns the engine's retrieved chunks; the agent
writes the answer from them. The engine itself never generates an answer.

| Skill | What it does | Files |
|---|---|---|
| [`knowledgebase`](knowledgebase/SKILL.md) | Retrieves the most relevant chunks for a question from an asset library and has the agent answer, summarize, compare or report from them | `SKILL.md`, `data_intelligence_engine` |

The `data_intelligence_engine` wrapper sends one `POST /v1/retrieve` request with
`curl`, the same request as [`scripts/retrieve.sh query`](../scripts/README.md#retrieval),
and prints the chunks as a numbered list. It needs only `bash` and `curl`; with
`jq` installed the output is the numbered list, otherwise the raw JSON response.
It does not need the engine's scripts, Python or a checkout of this repository, so
the skill directory can be copied to the agent's host on its own.

## Prerequisites

1. A running engine; see [Get Started](../docs/user-guide/get-start.md). The agent's
   host must reach its port (`16022` by default).
2. An asset library with a pool and ingested assets. Any library works (see
   [Library selection](#library-selection)); for example, from [`scripts/`](../scripts/):

   ```bash
   ./library.sh create '{"name":"enterprise-kb"}'
   ./sources.sh create enterprise-kb '{"name":"docs","database_id":"local-milvus","collection_name":"enterprise_kb_docs"}'
   ./pools.sh create enterprise-kb '{"id":"documents","name":"Documents","sources":["docs"]}'
   ./assets.sh add enterprise-kb /path/to/your/docs/ --pool documents --wait
   ```

   Replace `/path/to/your/docs/` with your own documents: one or more files or
   folders anywhere on this host, for example
   `./assets.sh add enterprise-kb ~/manuals/ ~/notes/spec.pdf --pool documents --wait`.
   They do not have to be copied to a particular directory; the helper uploads
   them through the API, and a folder contributes every supported file in it.
   A relative path is looked up from the current directory, then from `scripts/`.
   A path that does not exist on this host is sent to the engine unchanged as a
   path on the engine host, so a typo there makes the ingest fail. Check the
   result with `./assets.sh read enterprise-kb`. Supported formats and other file
   types are covered in
   [How to ingest multimodal data](../docs/user-guide/how-to-guides/how-to-ingest-mm-data.md).

## Try the wrapper

Run it directly before handing it to an agent:

```bash
cd data-intelligence-engine/skills/knowledgebase
./data_intelligence_engine "What is Intel Core Ultra X7 358H?"
./data_intelligence_engine "thermal limits" --pool documents --media document --top-k 10 --rerank 5
./data_intelligence_engine --help
```

| Option | Meaning |
|---|---|
| `--library NAME` | Asset library name or ID (default `KB_LIBRARY`, then a discovered library) |
| `--pool ID` | Asset pool ID, repeatable (default `KB_POOL`, then every pool in the library) |
| `--top-k N` | Candidates per serving source, 1-100 (default `5`) |
| `--media LIST` | Comma-separated `document`, `image`, `video`, `audio`; `document` returns text passages only (default `KB_TARGET_MEDIA`, then every modality) |
| `--rerank N` | Rerank the candidates with the engine's default reranker and keep the best N (default `KB_RERANK_TOP_N`, then no reranking) |

A text chunk prints its passage. A figure, image, video or audio chunk has no
passage; it prints a `media:` URL served by
[`GET /v1/blob`](../docs/user-guide/api.md#media-bytes) and its caption or
surrounding page text as `context:`. With `--rerank`, the reranker must be prepared
(the default Qwen3-VL INT8 reranker scores text and media chunks together). See the [API reference](../docs/user-guide/api.md#retrieval) for
`top_k`, `target_media` and `postprocess` semantics.

On failure the wrapper prints the engine's error and exits non-zero, for example
`Asset library 'x' not found` (`404`), `asset pool not found` (`404`) or
`search unavailable for: video` (`503`, no serving source for that modality).
Invalid options exit with `2` without contacting the engine.

## Configuration

The wrapper reads its defaults from the environment of the process that runs it,
which for OpenClaw is the gateway:

| Variable | Default | Meaning |
|---|---|---|
| `KB_ENGINE_URL` | `ENGINE_URL`, then `http://localhost:${ENGINE_PORT:-16022}` | Engine base URL |
| `KB_LIBRARY` | discovered | Asset library name or ID |
| `KB_POOL` | every pool | One asset pool ID |
| `KB_TARGET_MEDIA` | every modality | Default for `--media` |
| `KB_RERANK_TOP_N` | no reranking | Default for `--rerank` |
| `KB_CONNECT_TIMEOUT` | `10` | Connection timeout in seconds |

A command-line option overrides its variable for that call, and a variable
overrides the built-in default. Library references accept a name or an ID; pool
references must be the pool ID (`asset_pool_id`), which `./pools.sh read <library>`
lists. Sources cannot be selected directly: the engine searches every serving
source of the selected pools, so a source that needs its own search goes in its
own pool.

### Library selection

With neither `--library` nor `KB_LIBRARY`, the wrapper lists the engine's libraries
(`GET /v1/libraries` and each library's `asset_pools`) and searches one of them:

1. Candidates are the libraries that hold every `--pool`/`KB_POOL` ID given, or,
   without a pool, the libraries with at least one pool that has assets.
2. `enterprise-kb` is chosen when it is a candidate; otherwise the first candidate
   in the engine's order.
3. The choice is reported on stderr, with the other candidates, for example
   `Note: searching library 'alpha'; also available: beta. Pass --library NAME to choose.`
   With no candidate the wrapper exits with an error.

Discovery needs `jq`; without it the wrapper searches `enterprise-kb`. Set
`KB_LIBRARY` when the engine holds several libraries and the agent should always
search the same one.

## Install the skill into OpenClaw

### Before you start

This section only adds the skill to an existing OpenClaw setup. It assumes:

- OpenClaw is installed and onboarded, and `~/.openclaw/openclaw.json` and the
  agent workspace `~/.openclaw/workspace` exist. To install it, follow
  [Set Up OpenClaw](https://github.com/open-edge-platform/metro-ai-suite/blob/main/enterprise-data-intelligence/docs/user-guide/get-started.md#3-set-up-openclaw)
  (Node.js >= 22.14.0, `npm install -g openclaw@2026.5.6`, `openclaw onboard --install-daemon`).
- A model provider is configured in `openclaw.json` and the agent already answers
  in `openclaw tui`. The model must support tool calls, because the skill works by
  running the wrapper through the agent's shell tool.
- The engine meets the [Prerequisites](#prerequisites) above and is reachable from
  the OpenClaw host. Check it there with
  `curl http://<engine-host>:16022/health`.
- `bash` and `curl` are installed on the OpenClaw host, and `jq` for the numbered
  output and automatic library selection.
- Any `KB_*` variable you need, for example `KB_ENGINE_URL` when the engine runs on
  another host, is set in the environment the OpenClaw gateway runs in; see
  [Configuration](#configuration).

### Install and enable

OpenClaw loads skills only from an agent's workspace, so copy the whole skill
directory (keep the wrapper executable) into it:

```bash
mkdir -p ~/.openclaw/workspace/skills
cp -r data-intelligence-engine/skills/knowledgebase ~/.openclaw/workspace/skills/
```

Enable it in `~/.openclaw/openclaw.json`, next to any existing entries under
`skills.entries`:

```json
{
  "skills": {
    "entries": {
      "knowledgebase": {
        "enabled": true
      }
    }
  }
}
```

Restart the gateway so it loads the skill, then check that the agent sees it:

```bash
openclaw gateway restart
openclaw tui
# In tui:
/reset
# Then ask:
"Can you use the knowledgebase skill?"
```
