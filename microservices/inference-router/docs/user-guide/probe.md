# Provider Probes

A **probe** is a per-provider background task that keeps a live signal about a
backend fresh. On a fixed interval it runs one small pipeline:

```
tick → GET(endpoint) → extract numeric fields → aggregate (sliding window) → publish
```

Everything a probe does is declared in config — there is no per-backend code.
The most common use is a **performance probe**: scrape a backend's Prometheus
`/metrics` endpoint, turn a few counters/gauges into numbers, and publish them
into the provider's routing metadata so the router can prefer less-loaded, faster
providers. Values can also be appended to a JSONL file for history.

---

## Probe configuration

Probes live under a provider's `settings.probes` list. Each entry:

| Field | Required | Default | Meaning |
|-------|----------|---------|---------|
| `name` | yes | — | Unique within the provider. |
| `enabled` | no | `true` | Set `false` to stop it (see [lifecycle](#starting--stopping)). |
| `endpoint` | no | provider's `endpoint` | URL to GET each tick. Set this to the `/metrics` URL — the provider's own endpoint is the chat `/v1` base. |
| `interval` | no | `10` | Seconds between ticks. |
| `timeout` | no | `5` | Per-request timeout (must not stall reporting). |
| `method` | no | `GET` | HTTP method. |
| `extract` | yes | — | One or more rules that turn the response body into `{name: value}` pairs. |
| `aggregate` | no | `{window: 20, method: mean}` | Sliding-window reduction per series. `method` ∈ `latest \| mean \| median \| p50 \| p90 \| p95 \| p99 \| ewma \| min \| max \| stdev`. |
| `publish` | no | metadata sink | Where each aggregate goes (see [sinks](#publishing--reading-values)). |
| `max_series` | no | `200` | Cardinality cap, so a broad regex can't create unbounded series. |

### Extract rules

Each rule is **either** a `regex` (for Prometheus/plain-text bodies) **or** a
`json` dot-path (for JSON bodies):

- **`regex`** — matched against the whole body. Per match, the **last capture
  group is the value** and the **group before it is the field name**. One
  pattern can therefore name and read many series at once (one per matching
  line). Non-numeric values are skipped.

  ```yaml
  # vllm:num_requests_waiting{engine="0",model_name="..."} 3.0
  #      └──────── name ─────┘                             └ value ┘
  - regex: 'vllm:(num_requests_waiting)\{[^}]*\}\s+([0-9.eE+-]+)'
  ```

- **`json`** — a dotted path into the parsed body; the field name is the last
  segment, the value is the numeric leaf.

  ```yaml
  - json: stats.pending        # {"stats": {"pending": 7}} → {"pending": 7.0}
  ```

---

## Example 1 — add a performance probe in `config.yaml`

This probes a vLLM backend's `/metrics` every 5 s, extracts two load signals
(both lower-is-better), and publishes them under the provider's
`performance.*` namespace — the exact field the `PerformanceBased` strategy
reads — plus a JSONL history file.

```yaml
providers:
- name: local
  type: hosted_vllm
  model: Qwen/Qwen3.5-9B
  enabled: true
  metadata:
    labels: [local]
    cost: 0
  settings:
    endpoint: http://localhost:8088/v1        # chat base (/v1)
    timeout: 300.0
    auth:
      scheme: none
      api_key: null
      custom_headers: {}
    probes:
    - name: perf
      enabled: true
      endpoint: http://localhost:8088/metrics # scrape target (NOT /v1)
      interval: 5
      timeout: 5
      extract:
      - regex: 'vllm:(num_requests_waiting)\{[^}]*\}\s+([0-9.eE+-]+)'
      - regex: 'vllm:(kv_cache_usage_perc)\{[^}]*\}\s+([0-9.eE+-]+)'
      aggregate: { window: 12, method: mean }
      publish:
      - { to: metadata, prefix: performance }                       # → routing (live)
      - { to: file, path: probes/local.perf.jsonl }                 # → history
```

> **File paths are workspace-relative.** A relative `path` resolves against the
> runtime workspace directory (the `config.yaml` directory, i.e.
> `$GATEWAY_WORKSPACE` or the dir of `$GATEWAY_CONFIG`), not the process CWD. So
> `probes/local.perf.jsonl` lands in `<workspace>/probes/` wherever the server is
> launched from. Use an absolute path to write elsewhere.

The metadata sink writes each aggregate to `performance.<name>`, e.g.
`performance.num_requests_waiting`. A `PerformanceBased` strategy can then filter
and rank on it (values are treated as upper bounds — lower is better):

```yaml
# strategy.yaml
strategies:
- name: performance_based
  provider_selector:
    performance:
      num_requests_waiting: 5      # drop providers with a longer queue
      kv_cache_usage_perc: 0.9     # drop providers whose KV cache is saturated
  sort:
  - { provider_attribute: performance.num_requests_waiting, descending: false }
```

> **Prefixes.** Use `prefix: performance` to feed the routing `performance.*`
> field directly. Use `prefix: attributes.probe` (the default) for generic live
> metadata that surfaces as `probe.<name>` in `metadata.to_dict()`.

> **Latency metrics.** vLLM exposes latencies as histograms
> (`vllm:time_to_first_token_seconds_sum` / `_count`). A probe reads single
> values, so it cannot divide sum by count to get a mean TTFT in one rule —
> prefer the load gauges above, or publish the raw `_sum`/`_count` and compute
> downstream.

---

## Example 2 — add the same probe at runtime via the providers API

No restart needed: POST the provider with the probe in `settings.probes`. The
providers API rebuilds the runtime on every mutation, so the probe starts
immediately. **`settings` is replaced wholesale**, so resend the full settings
block, not just the probe.

```bash
curl -X POST http://localhost:8000/v1/providers/local \
  -H 'content-type: application/json' \
  -d '{
    "settings": {
      "endpoint": "http://localhost:8088/v1",
      "timeout": 300.0,
      "auth": {"scheme": "none", "api_key": null, "custom_headers": {}},
      "probes": [
        {
          "name": "perf",
          "enabled": true,
          "endpoint": "http://localhost:8088/metrics",
          "interval": 5,
          "extract": [
            {"regex": "vllm:(num_requests_waiting)\\{[^}]*\\}\\s+([0-9.eE+-]+)"}
          ],
          "publish": [
            {"to": "metadata", "prefix": "performance"},
            {"to": "file", "path": "probes/local.perf.jsonl"}
          ]
        }
      ]
    }
  }'
```

Confirm it was persisted:

```bash
curl -s http://localhost:8000/v1/providers/local | jq '.settings.probes'
```

### Optional — edit in place: GET, append the probe, POST back

Instead of hand-writing the whole `settings` block, you can fetch the provider's
current config, splice the probe into `settings.probes`, and POST the result.
Because a GET response round-trips as a POST payload, `jq` can do the merge:

```bash
# 1. Define the probe to add.
read -r -d '' PROBE <<'JSON'
{
  "name": "perf",
  "enabled": true,
  "endpoint": "http://localhost:8088/metrics",
  "interval": 5,
  "extract": [{"regex": "vllm:(num_requests_waiting)\\{[^}]*\\}\\s+([0-9.eE+-]+)"}],
  "publish": [
    {"to": "metadata", "prefix": "performance"},
    {"to": "file", "path": "probes/local.perf.jsonl"}
  ]
}
JSON

# 2. GET current config, append the probe (replacing any probe of the same
#    name), and POST just the settings back.
curl -s http://localhost:8000/v1/providers/local \
  | jq --argjson probe "$PROBE" '{
      settings: (.settings + {
        probes: (((.settings.probes // []) | map(select(.name != $probe.name))) + [$probe])
      })
    }' \
  | curl -X POST http://localhost:8000/v1/providers/local \
      -H 'content-type: application/json' -d @-
```

> **Secrets caveat.** A GET **redacts** secrets (`api_key: "***REDACTED***"`).
> Posting that mask back would persist the literal string, breaking auth. This
> in-place edit is therefore safe for providers with no secret (e.g.
> `auth.scheme: none`, as above); for a provider that carries an `api_key`,
> re-supply the real value (or a `${VAR}` placeholder) in the merged payload
> before POSTing.

### Starting / stopping

Lifecycle is just the `enabled` flag, driven through the same providers API:

- **start / add** — POST with the probe present and `enabled: true`.
- **stop / remove** — POST again with that probe's `enabled: false` (or omit it).
- **all probes** start on boot (`initialize()`) and stop on shutdown.

---

## Publishing & reading values

A probe publishes through one or more **sinks**:

- **metadata** — writes each aggregate into the live `ProviderMetadata` at
  `<prefix>.<name>`. The strategy layer rebuilds `{**metadata.to_dict()}` on
  every route, so the next routing decision sees fresh values with no cache.
  This is how a probe influences routing.
- **file** — appends one JSONL record per tick: `{ts, provider, probe,
  aggregates}`. This is the durable/offline read path. Because a probe runs
  forever, the history is capped: the sink keeps the most recent `max_entries`
  records (default `10000`) and drops older ones. Set `max_entries` on the sink
  to change the cap, or `max_entries: 0` to disable it (unbounded growth).

  ```yaml
  - { to: file, path: probes/local.perf.jsonl, max_entries: 50000 }
  ```

```bash
tail -1 <workspace>/probes/local.perf.jsonl
# {"ts": 1790136107.6, "provider": "local", "probe": "perf",
#  "aggregates": {"num_requests_waiting": 0.0, "kv_cache_usage_perc": 0.0}}
```

There is no dedicated HTTP endpoint for reading probe values — routing consumes
them via provider metadata, and the file sink is the durable history.

---

## Tips

- Point `endpoint` at the **`/metrics`** URL; the bare provider `endpoint` is the
  chat `/v1` base and won't yield metrics.
- Anchor a regex name group (`(num_requests_running)`) for one series; use a
  wildcard (`(num_requests_\w+)`) to discover several from one pattern.
- A failed scrape never kills the probe — it increments a fail counter and the
  window keeps its last good values until the next successful tick.
- Keep `interval` sane: it is scrape load on the backend, not free.
