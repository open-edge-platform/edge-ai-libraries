# Routing

This guide explains how the Inference Router chooses a provider for each request, and the method to configure and validate it.

The router supports two kinds of routing rules, which plug into the same rule → strategy → policy pipeline and can be mixed freely in one policy:

- **[Rule-based routing](#rule-based-routing)**: deterministic rules that check request features (message content, context length, tools, model name, metadata) or live provider metadata (cost, performance).
- **[Model-based routing](#model-based-routing)**: a classifier model reads the last user message and maps it to an index (for example `0` → local, `1` → cloud).

## Routing Model

The router makes a decision in three layers:

1. **Rule**: checks one request feature, such as message content, context length, tools, model name, or metadata.
2. **Strategy**: combines rules with AND semantics, then filters providers with `provider_selector`.
3. **Policy**: runs strategies in order and selects the final provider using `FirstMatch` or `AllMatch`.

If the policy selects no provider, the request goes to the provider marked
`fallback: true` in `config.yaml` (at most one); when no provider is marked, the
request is rejected with a routing error.

## Built-in Strategies and Policies

The default strategies are defined in [src/rsd/strategy.yaml](../../src/rsd/strategy.yaml):

| Strategy | Trigger | Provider Selector |
| --- | --- | --- |
| `Planning` | User message contains `plan` | `label: planning`, `capability.complexity >= 0.7` |
| `DataAnalysis` | User message contains a tabular-data keyword (`csv`, `spreadsheet`, `dataframe`, `dataset`, `excel`, `pivot`) | `label: data-analysis`, `capability.complexity >= 0.6` |
| `ContextLengthQuality` | Total context length falls in configured zones | Zone-based `capability.complexity` threshold |
| `ZeroCost` | Always matches | `cost <= 0` |
| `ModelBasedRouting` | Classifier maps the last user message to index `0` or `1` | Index-based `label` (`0: local`, `1: cloud`) |
| `PerformanceBased` | Always matches | `performance.requests <= 40`, then sorts by fewest in-flight requests |

The default policies are defined in [src/rsd/policy.yaml](../../src/rsd/policy.yaml):

| Policy | Criterion | Strategy Order |
| --- | --- | --- |
| `Balanced` | `FirstMatch` | `Planning -> DataAnalysis -> ContextLengthQuality` |
| `CostFirst` | `FirstMatch` | `ZeroCost` |
| `ModelBased` | `FirstMatch` | `ModelBasedRouting` |
| `PerformanceFirst` | `FirstMatch` | `PerformanceBased -> ZeroCost` |

`FirstMatch` returns the first strategy that can produce a candidate provider.
`AllMatch` runs every strategy and selects a provider that appears in every
candidate list. The default YAML file only uses `FirstMatch`; add an `AllMatch`
policy if you need to test intersection behavior.

## Configure Providers

Routing depends on provider metadata in `config.yaml`. A provider can expose
labels, cost, performance, and capabilities:

```yaml
providers:
  - name: local
    type: hosted_vllm
    model: Qwen/Qwen3.5-9B
    enabled: true
    metadata:
      labels: [planning, local]
      cost: 0
      performance: 0.85
      capability:
        complexity: 0.75
        tool_calling: true
    settings:
      endpoint: http://localhost:5000/v1
```

`provider_selector` supports these fields:

```yaml
provider_selector:
  label: planning
  cost: 0
  capability:
    complexity: 0.7
    tool_calling: true
```

`label`, `cost`, and `capability.complexity` may also be zone maps, for example
`complexity: {0: 0.3, 1: 0.5, 2: 0.7}`. Place `complexity` and `tool_calling`
under `provider_selector.capability`; placing them at the top level is invalid.

## Select a Policy

Choose the active policy in your runtime config:

```yaml
routing:
  policy: Balanced
```

Use the `Balanced` routing policy to prioritize planning tasks and long-context quality.
Use the `CostFirst` routing policy when you prefer free or local providers.

## Rule-Based Routing

Rule-based routing decides from request features or provider metadata, with no
model inference on the request path.

### Built-in Rules

Rules are configured in [src/rsd/strategy.yaml](../../src/rsd/strategy.yaml)
with the `type` and `param` fields.

| Rule Type | Purpose | Main Parameters |
| --- | --- | --- |
| `ModelNameRule` | Match the request `model` field | `pattern`, `use_regex` |
| `MessageContentRule` | Match text in messages | `pattern`, `use_regex`, `roles` |
| `ToolCallsRule` | Require or reject tool definitions | `require_tools` |
| `MetadataRule` | Match fields in `extra_body` | `key`, `value` |
| `QueryComplexityScoreRule` | Match a complexity score | `score_range`, `target`, `operator` |
| `QueryComplexityZoneRule` | Bucket the last user message by word count | `zones` |
| `ContextLengthRule` | Bucket the total message content length by character count | `zones` |

`QueryComplexityScoreRule` is currently a placeholder: it returns the midpoint
of `score_range`, so it does not yet vary with request content.

The model-based rule `ModelBasedRule` is also a built-in rule; it is described
in [Model-Based Routing](#model-based-routing).

### Exercise Rule-Based Routing

Useful requests to exercise the default rule-based policies:

| Goal | Request Shape | Expected Route Behavior |
| --- | --- | --- |
| Hit `Planning` | User message contains `plan` | Selects a provider with `planning` label and high complexity |
| Hit `DataAnalysis` | User message mentions tabular data, e.g. "I have a CSV file of sales; find the top region" | Selects a provider with `data-analysis` label and complexity `>= 0.6` |
| Hit context zone 0 | Total message content length `0–4000` characters | Requires provider complexity `>= 0.3` |
| Hit context zone 1 | Total message content length `4001–16000` characters  | Requires provider complexity `>= 0.5` |
| Hit context zone 2 | Total message content length `16001–128000` characters  | Requires provider complexity `>= 0.7` |
| Hit `CostFirst` | Sets `routing.policy: CostFirst` | Selects a provider with `cost <= 0` |
| Test fallback | Makes every selector fail | Goes to the provider marked `fallback: true`; rejected if none is |

### Keyword Strategies

A keyword strategy routes a task type to a provider label with a
`MessageContentRule` regex over the user messages. `DataAnalysis` is the
built-in one. The strategies below follow the same pattern; add the ones you
need:

1. Copy [src/rsd/strategy.yaml](../../src/rsd/strategy.yaml) to
   `<workspace>/strategy.yaml` (a workspace file replaces the built-in one, so
   keep the strategies you still use) and append the strategies.
2. Add the target label (for example `coding`) to the `metadata.labels` of the
   provider that should serve the task.
3. Add the strategy names to a policy in `<workspace>/policy.yaml`.

With `FirstMatch`, the first matching strategy that finds a provider wins, so
order matters when patterns overlap: "write a Python function" matches both
`Coding` and `CreativeWriting`, so put `Coding` first. Put keyword strategies
before catch-all strategies such as `ContextLengthQuality`. A strategy whose
label no provider carries matches nothing, and the policy moves on.

```yaml
strategies:
  - name: Coding
    description: "Routes programming / coding requests."
    rules:
      - type: MessageContentRule
        param:
          pattern: '\b(code|coding|debug|debugging|refactor|compile|python|javascript|typescript|java|sql|regex|bash|shell|script|dockerfile|kubernetes|unit test|stack trace|programming)\b'
          use_regex: true
          roles:
            - user
    provider_selector:
      label: coding
      capability:
        complexity: 0.7

  - name: MathCalculation
    description: "Routes math / calculation requests."
    rules:
      - type: MessageContentRule
        param:
          pattern: '\b(calculate|compute|solve|equation|arithmetic|math|derivative|integral|percentage)\b|数学|计算'
          use_regex: true
          roles:
            - user
    provider_selector:
      label: math
      capability:
        complexity: 0.7

  - name: Summarization
    description: "Routes summarization requests."
    rules:
      - type: MessageContentRule
        param:
          pattern: '\b(summari[sz]e|summari[sz]ing|summari[sz]ation|summary|tldr|recap|condense|gist)\b'
          use_regex: true
          roles:
            - user
    provider_selector:
      label: summarization
      capability:
        complexity: 0.5

  - name: Translation
    description: "Routes translation requests."
    rules:
      - type: MessageContentRule
        param:
          pattern: '\btranslat(?:e|ing)\b[^.]{0,60}?\binto\b|\btranslating\b|\btranslation\b|\btranslated\b|\btranslat(?:e|ing)\b[^.]{0,60}?\b(?:english|chinese|french|spanish|german|japanese|korean|mandarin)\b|翻译|译成'
          use_regex: true
          roles:
            - user
    provider_selector:
      label: translation
      capability:
        complexity: 0.5

  - name: CreativeWriting
    description: "Routes writing / creative requests."
    rules:
      - type: MessageContentRule
        param:
          pattern: '\b(write|rewrite|draft|compose|essay|story|poem|email|blog|article|paraphrase|rephrase)\b'
          use_regex: true
          roles:
            - user
    provider_selector:
      label: writing
      capability:
        complexity: 0.6
```

A policy using all of them, most specific first:

```yaml
policies:
  - name: Balanced
    criterion: FirstMatch
    strategies:
      - Planning
      - Coding
      - DataAnalysis
      - MathCalculation
      - Summarization
      - Translation
      - CreativeWriting
      - ContextLengthQuality
```

| Strategy | Example request | Provider label |
| --- | --- | --- |
| `Coding` | "Write a Python function to merge two sorted lists" | `coding` |
| `MathCalculation` | "Solve this equation: 3x + 5 = 20" | `math` |
| `Summarization` | "Summarize this article in three sentences" | `summarization` |
| `Translation` | "Translate this paragraph into French" | `translation` |
| `CreativeWriting` | "Write a one-line birthday message for my mom" | `writing` |

### Performance-Based Routing

`PerformanceBased` routes on **live backend load** instead of request content. A
[provider probe](probe.md) scrapes each backend's Prometheus `/metrics` endpoint
on an interval, publishes the numbers into the provider's `performance.*`
metadata, and the strategy filters and ranks on those fresh values.

#### How the strategy reads the metrics

The strategy's `provider_selector.performance` is a map of
`metric -> threshold`. Two rules apply to **every** metric, so pick metrics
where both hold:

- **Lower is better.** A threshold is an *upper bound*: a provider stays
  eligible only while `performance.<metric> <= threshold`. A provider that is
  missing the field, or whose value is non-numeric, is dropped (the same
  conservative stance the `cost` selector takes). This is why the metrics below
  are *load* and *latency* signals, never capacity or throughput (which are
  higher-is-better).
- **Read straight from metadata.** The value used is whatever the probe last
  published to `performance.<metric>`; the strategy does no arithmetic. `sort`
  then orders the survivors by one `performance.*` attribute
  (`descending: false` = smallest first; a provider with no value sorts last).

#### Example — enable the probe and route on load

This runs two local backends — one vLLM, one OVMS — and routes each request to
whichever is **least loaded**. Each provider gets a `perf` probe that scrapes its
own `/metrics` and publishes the in-flight request count to the shared
`performance.requests` field; `PerformanceBased` then filters and sorts on it.

```yaml
# config.yaml
providers:
  - name: vllm-local
    type: hosted_vllm
    model: Qwen/Qwen3.6-35B-A3B
    enabled: true
    metadata:
      labels: [local]
      cost: 0
    settings:
      endpoint: http://localhost:8088/v1          # chat base (/v1)
      timeout: 300.0
      auth: { scheme: none, api_key: null, custom_headers: {} }
      probes:
        - name: perf
          enabled: true
          endpoint: http://localhost:8088/metrics # scrape target (NOT /v1)
          interval: 5
          timeout: 5
          extract:
            # Capture "requests" as the field name and the running count as the
            # value → published as performance.requests.
            - regex: 'vllm:num_(requests)_running\{[^}]*\}\s+([0-9.eE+-]+)'
          aggregate: { window: 6, method: mean }
          publish:
            - { to: metadata, prefix: performance }                 # → routing (live)
            - { to: file, path: probes/vllm-local.perf.jsonl }      # → history

routing:
  policy: PerformanceFirst
```

`PerformanceFirst` already ships in [src/rsd/policy.yaml](../../src/rsd/policy.yaml)
— it runs `PerformanceBased` first and falls back to `ZeroCost` when no provider
clears the load threshold:

```yaml
# policy.yaml (already shipped)
policies:
  - name: PerformanceFirst
    criterion: FirstMatch
    strategies:
      - PerformanceBased
      - ZeroCost          # fallback when no provider clears the perf thresholds
```

The bundled `PerformanceBased` strategy (in
[src/rsd/strategy.yaml](../../src/rsd/strategy.yaml)) consumes the field the
probes publish:

```yaml
# strategy.yaml (already shipped)
strategies:
  - name: PerformanceBased
    description: "Prefer the least-loaded backend by live in-flight request count."
    provider_selector:
      performance:
        requests: 40      # drop a backend already running 40+ concurrent requests
    sort:
      - provider_attribute: performance.requests
        descending: false # fewest in-flight requests first
```

With this config, a request is sent to `vllm-local` or `ovms-local` depending on
which currently has fewer in-flight requests; a backend above 40 concurrent
requests is skipped entirely, and if both are over the limit the request goes to
the provider marked `fallback: true` (or is rejected if none is).

#### Enable it at runtime (no restart)

Probes can also be added through the providers API — POST the provider with the
probe in `settings.probes` and it starts immediately (resend the whole
`settings` block; it is replaced wholesale). See
[probe.md](probe.md#example-2--add-the-same-probe-at-runtime-via-the-providers-api).

#### Verify the probe is feeding the router

```bash
# The live value the strategy reads (durable history is the file sink):
tail -1 <workspace>/probes/vllm-local.perf.jsonl
# {"ts": ..., "provider": "vllm-local", "probe": "perf",
#  "aggregates": {"requests": 2.0}}
```

Send traffic and confirm the route decision's `strategy_name` is
`PerformanceBased` and `provider_name` flips to the quieter backend as load
shifts. Route decisions also carry `policy_name`, `criterion`, and
`candidate_count` — use them (or the logs / metrics endpoint) to see why a
provider was selected.

## Model-Based Routing

`ModelBasedRule` runs a small classifier model on the router host against the last user message of each request and returns a routing zone index. The strategy's index-keyed `provider_selector` turns that index into a provider.

### Quick Start

1. Download the default backbone model (see
   [Prepare the Classifier Model](#prepare-the-classifier-model)):

   ```bash
   hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen3.5-2B-FP16
   export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
   ```

2. Label your providers `local` and `cloud` in `config.yaml`.

3. Select the built-in policy in `config.yaml`:

   ```yaml
   routing:
     policy: ModelBased
   ```

4. Start or redeploy the router and confirm that the log shows
   `Preloaded 1 ModelBasedRule classifier(s) for the active policy`.

The built-in `ModelBased` policy runs the `ModelBasedRouting` strategy:

```yaml
strategies:
  - name: ModelBasedRouting
    rules:
      - type: ModelBasedRule        # no param: default backbone, version v1
    provider_selector:
      label:
        0: local
        1: cloud
```

### Prepare the Classifier Model

#### Supported Backbones

| Backbone key (`model`) | Base model | Packaged version | IR path variable |
| --- | --- | --- | --- |
| `qwen35-2b` (default) | `Qwen/Qwen3.5-2B` | `v1` | `IR_OV_MODEL_QWEN35_2B`, or `IR_OV_MODEL` |
| `qwen3-0.6b` | `Qwen/Qwen3-0.6B` | `v1` | `IR_OV_MODEL_QWEN3_0P6B`, or `IR_OV_MODEL` when `IR_BACKBONE=qwen3-0.6b` |
| `llama3-1b` | `meta-llama/Llama-3.2-1B-Instruct` | `v1` | `IR_OV_MODEL_LLAMA3_1B`, or `IR_OV_MODEL` when `IR_BACKBONE=llama3-1b` |

A classifier version only works on the backbone it was trained for. The router checks this before using a version.

#### Download

Both Qwen backbones have prebuilt FP16 OpenVINO IRs on Hugging Face:

```bash
pip install -U huggingface_hub

# Qwen3.5-2B (default)
hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen3.5-2B-FP16
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16

# Qwen3-0.6B
hf download OpenVINO/Qwen3-0.6B-fp16-ov --local-dir /opt/models/Qwen3-0.6B-FP16
export IR_OV_MODEL_QWEN3_0P6B=/opt/models/Qwen3-0.6B-FP16
```

There is no prebuilt FP16 IR for Llama-3.2-1B-Instruct, so convert it once
with optimum-cli (accept the model's license on Hugging Face first via
`hf auth login`):

```bash
pip install "optimum-intel[openvino]"

# Llama-3.2-1B-Instruct
optimum-cli export openvino --model meta-llama/Llama-3.2-1B-Instruct \
    --weight-format fp16 /opt/models/Llama-3.2-1B-Instruct-FP16
export IR_OV_MODEL_LLAMA3_1B=/opt/models/Llama-3.2-1B-Instruct-FP16
```

#### Devices

`IR_DEVICE` selects the OpenVINO device: `GPU` (the default), `GPU.0`,
`GPU.1`, ... or `CPU`. When the requested GPU is not available, the router
logs a warning and falls back to the CPU. NPU is not supported yet.

### Configure the Router

Model-based routing is configured with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `IR_OV_MODEL` | none | IR directory of the default backbone |
| `IR_OV_MODEL_QWEN35_2B`, `IR_OV_MODEL_QWEN3_0P6B`, `IR_OV_MODEL_LLAMA3_1B` | none | IR directory of a specific backbone; takes precedence over `IR_OV_MODEL` |
| `IR_BACKBONE` | `qwen35-2b` | Backbone used by rules that set no `model` |
| `IR_DEVICE` | `GPU` | OpenVINO device; falls back to the CPU if no GPU is available |
| `IR_ARTIFACTS_DIR` | `artifacts/router` (relative to the working directory) | Location of your own classifier versions |
| `IR_CACHE_SIZE` | `256` | Per-classifier cache of recent query results; `0` disables it |
| `IR_FP_MIN_COS` | `0.98` | Minimum fingerprint cosine similarity accepted when checking a version against the backbone |
| `IR_SWAP_MODE` | `load_first` | Policy switch order: `load_first` keeps the old classifiers until the new ones are ready; `unload_first` releases them first to save memory |

**Docker Compose**: export `IR_OV_MODEL` and, optionally, `IR_DEVICE` on the
host before running `scripts/deploy_docker.sh`. The compose file mounts
`IR_OV_MODEL` into the container at `/models/ov-classifier` and passes
`IR_DEVICE` through; for GPU devices, the deploy script also maps
`/dev/dri`. Put the other `IR_*` variables in `workspace/.env`. The workspace
is the container's working directory, so the default `IR_ARTIFACTS_DIR` is
`workspace/artifacts/router` on the host. Compose mounts only one backbone
directory. To serve Qwen3-0.6B, point `IR_OV_MODEL` at its IR and set
`IR_BACKBONE=qwen3-0.6b` in `workspace/.env`.

### Enable ModelBasedRule

Reference the rule from a strategy, and the strategy from the active policy.
You can use the built-in `ModelBased` policy as is, or define your own
strategies in `<workspace>/strategy.yaml` and `<workspace>/policy.yaml`.
REST management goes through the strategy and policy endpoints — see the
[API Reference](./api-reference.md).

Rule parameters for the classifier-version mode:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `model` | `IR_BACKBONE`, or `qwen35-2b` | Backbone key; see [Supported Backbones](#supported-backbones) |
| `version` | `v1` | `vN`, or `default` (an alias of the packaged `v1`) |

Examples:

```yaml
rules:
  - type: ModelBasedRule                 # qwen35-2b / v1
```

```yaml
rules:
  - type: ModelBasedRule
    param:
      model: qwen3-0.6b
```

```yaml
rules:
  - type: ModelBasedRule
    param:
      model: llama3-1b
```

```yaml
rules:
  - type: ModelBasedRule
    param:
      model: qwen35-2b
      version: v2
```

### Classifier Versions

A classifier version is a single `.rcv` file. It holds a prompt, the classification head, the zone map, and a fingerprint of the backbone it was built for. The prompt is either a trained soft prompt (a `soft` version) or a text system prompt (a `hard` version, whose head is the backbone's own output rows for the answer tokens). The router reads the kind from the file; the rule is configured the same way for both. The packaged `v1` versions are soft.

- **Packaged**: `v1` for each backbone, shipped in
  `src/rsd/model_based/prompts/<backbone>/v1.rcv`. `default` always means this
  file.
- **From prompt text**: POST a strategy whose `ModelBasedRule` sets `param.text`
  (plus optional `labels` and `threshold`). The router packs a hard version
  into `<IR_ARTIFACTS_DIR>/<backbone>/vN.rcv`, checks it, and stores
  `version: vN` in the strategy. Posting the same content again reuses that
  version. See [Create or Update Strategy](./api-reference.md#create-or-update-strategy).
- **Your own**: Train your own version of classifier will be available next release.

### Multi-class Routing

Set `prompt_file` to switch `ModelBasedRule` from a classifier version to multi-class routing: the classifier sorts each request into one of your own categories, and the category's zone index picks the provider. By default the categories are the provider labels in `provider_selector.label`: zone `i` is the category routed to `label[i]`, so you write the names once. No multi-class strategy ships by default. Add one like this to the `strategy.yaml` in your workspace and reference it from a policy.

```yaml
strategies:
  - name: MultiClassModelBasedRouting
    rules:
      - type: ModelBasedRule
        param:
          prompt_file: multiclass_prompt.txt
          threshold: 0.7
    provider_selector:
      label:
        0: local
        1: cloud
        2: planning
```

## Files to Edit

```text
src/rsd/strategy.yaml              Built-in strategy definitions
src/rsd/policy.yaml                Built-in policy definitions
<workspace>/strategy.yaml          Replaces the built-in strategies when present
<workspace>/policy.yaml            Replaces the built-in policies when present
config.yaml                        Runtime providers and active policy
<IR_ARTIFACTS_DIR>/<backbone>/vN.rcv   Your own classifier versions
```
