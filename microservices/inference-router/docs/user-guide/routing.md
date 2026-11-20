# Routing

This guide explains how the Inference Router chooses a provider for each request, and the method to configure and validate it.

The router supports two kinds of routing rules, which plug into the same rule → strategy → policy pipeline and can be mixed freely in one policy:

- **[Rule-based routing](#rule-based-routing)**: deterministic rules that check request features (message content, context length, tools, model name, metadata) or live provider metadata (cost, performance).
- **[Model-based routing](#model-based-routing)**: a classifier model reads the last user message and maps it to an index (for example `0` → local, `1` → cloud).

## Routing Model

The router makes a decision in three layers:

1. **Rule**: checks one request feature -- the built-in rules are listed under [Rule-Based Routing](#rule-based-routing).
2. **Strategy**: combines rules with AND semantics, then filters providers with `provider_selector`.
3. **Policy**: runs strategies in order and selects the final provider (`FirstMatch` or `AllMatch` -- the semantics are expanded under [Built-in Strategies and Policies](#built-in-strategies-and-policies)).

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
| `PerformanceBased` | Always matches | `performance.requests <= 10`, then sorts by fewest in-flight requests |

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
`MessageContentRule` regex over the user messages. `Planning` and `DataAnalysis` are built in. You may also add below strategies as you need:

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

### Performance-Based Routing

`PerformanceBased` routes on **live backend load** instead of request content. A
[provider probe](probe.md) scrapes each backend's Prometheus `/metrics` endpoint
on an interval, publishes the numbers into the provider's `performance.*`
metadata, and the strategy filters and ranks on those fresh values.

#### How the strategy reads the metrics

The strategy's `provider_selector.performance` maps each metric to the values a
provider may report and stay eligible. Each value is one of:

| Form | Meaning |
|------|---------|
| `requests: 10` | Shorthand upper bound: `performance.requests <= 10` |
| `kv_cache_usage_perc: [null, 0.8]` | `<= 0.8` |
| `tokens_per_s: [50, null]` | `>= 50` (for higher-is-better metrics such as throughput) |
| `ttft_ms: [0, 500]` | `0 <= ttft_ms <= 500` |

- **Inclusive ranges.** `[lower, upper]` uses the same inclusive bounds as a
  `ContextLengthRule` zone; `null` leaves that side open. A provider must fall
  in range for **every** configured metric. A provider that is missing the
  field, or whose value is non-numeric, is dropped whichever side is bounded
  (the same conservative stance the `cost` selector takes).
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
        requests: 10      # drop a backend running more than 10 concurrent requests
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

`ModelBasedRule` utilizes the idea of "LLM as Jev": it runs a small language model on the router host as a decision model that generates no text.

The classifier's prompt is in the form of a binary file, which stores either a soft prompt or a hard prompt. 

### Soft Prompt

A soft prompt a set of pre-trained vectors with respect to a dataset and routing task. Router packs the vector and store it in a binary file with `rcv` as appendix.

For example, current default version of soft prompt was trained on RouterBench Dataset, with the ability to route a query to cloud or local provider based on the complexity. 

Train your own soft prompt will be available in next realese.

By default each backbone is shipped with one version of soft prompt in `src/rsd/model_based/prompts/<backbone>/v1.rcv` of the image; Docker deployments copy it to `workspace/artifacts/router/<backbone>/v1.rcv`.

### Hard Prompt

Previous method of using text prompt is still available, router will accept the text prompt and package it into an `rcv` file for further process.

Use below API to upload a hard prompt:

```bash
POST /v1/strategies/{name}
{
  "rules": [{"type": "ModelBasedRule", "param": {"text": "<prompt content>", "threshold": 0.7}}],
  "provider_selector": {"label": {"0": "local", "1": "cloud", "2": "planning"}}
}
```

### Quick Start: Route by Complexity

The built-in `ModelBased` policy fits a deployment with one **local** model and one **cloud** model: simple requests go to the local model, hard ones to the cloud. It runs the `ModelBasedRouting` strategy, which uses the trained soft prompt `v1`, `in strategy.yaml`:

```yaml
strategies:
  - name: ModelBasedRouting
    rules:
      - type: ModelBasedRule
    provider_selector:
      label:
        0: local
        1: cloud
```

1. Download the backbone and start the router.:

   ```bash
   hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen3.5-2B-FP16
   export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
   bash scripts/deploy_docker.sh
   ```

2. Label your providers `local` and `cloud`, and activate the policy.

3. Send requests and see where they go. For example:
   ```bash
   curl http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "auto", "messages": [{"role": "user", "content": "Polish this sentence: we was late to the meeting."}]}'

   docker logs inference-router 2>&1 | grep "Request completed" | tail -5
   # ... provider=<local-provider>, reason=StrategyExecutor: strategy 'ModelBasedRouting' matched for provider '<local-provider>' ...
   ```

Typical decisions of the soft prompt:

| Request | Category |
| --- | --- |
| Polish this paragraph for clarity. | `local` |
| Summarize this article in three bullet points. | `local` |
| Find the race condition in this Go worker pool and fix it. | `cloud` |
| Design a sharded database schema for a global e-commerce site and justify the trade-offs. | `cloud` |

### Multi-class Routing

Model based rule is now supporting multi-class routing. You may write a prompt that describes the categories or train a soft prompt (in next release); the router packs it into a classifier version and routes each category to a provider.

#### Prompt Example

Below is an example for API payload to upload a multi-class prompt:

```bash
curl http://localhost:8000/v1/strategies/MultiClassRouting \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{"type": "ModelBasedRule", "param": {
      "text": "You are a routing classifier. Read the task and decide which category it best fits.\n\nCategories:\n- local: simple, generative, single-file, or rule-clear tasks that a small local model handles well — writing, summarizing, polishing, extracting/filtering/sorting from one given file, routine scripts.\n- cloud: hard tasks that need a large frontier model — strict hard-format constraints, manipulating hidden/external state (git history, debugging, unfamiliar codebases, multi-hop planning), expert trade-off judgments, or cross-referencing multiple sources.\n- planning: tasks whose main work is decomposition and planning — breaking a goal into steps, drafting a project/roadmap/architecture plan, sequencing dependent subtasks.\n\nIf unsure between two, pick the higher-capability one.",
      "threshold": 0.7
    }}],
    "provider_selector": {"label": {"0": "local", "1": "cloud", "2": "planning"}}
  }'
```

#### Provider Example

Each category is routed through provider_selector.label to the providers who contain that label, and a provider may carry several labels. 

For example, in the case above, providers could be configed below in config.yaml:

```yaml
providers:
  - name: "vllm-local"
    type: "hosted_vllm"
    model: "Qwen/Qwen3.5-9B"
    enabled: true
    metadata:
      labels:
        - "local"
      cost: 0
    settings:
      endpoint: "http://localhost:5000/v1"
      timeout: 300.0
      auth:
        scheme: "none"
        api_key: null
        custom_headers: {}

  - name: "openai-cloud"
    type: "openai"
    model: "gpt-4o"
    enabled: true
    metadata:
      labels: # multi label example
        - "cloud"
        - "planning"
      cost: 5
    settings:
      endpoint: "https://api.openai.com/v1"
      timeout: 300.0
      auth:
        scheme: "bearer"
        api_key: "${OPENAI_API_KEY}"

routing:
  policy: MultiClass    
```

This leads to below category and provider relationship:

| Category | `provider_selector.label` | Provider |
| --- | --- | --- |
| `local` | `0: local` | `vllm-local` |
| `cloud` | `1: cloud` | `openai-cloud` |
| `planning` | `2: planning` | `openai-cloud` |

### Prepare the Classifier Model

#### Supported Backbones

| Backbone (`IR_BACKBONE`) | Base model | Packaged version |
| --- | --- | --- |
| `qwen35-2b` (default) | `Qwen/Qwen3.5-2B` | `v1` |
| `qwen3-0.6b` | `Qwen/Qwen3-0.6B` | `v1` |
| `llama3-1b` | `meta-llama/Llama-3.2-1B-Instruct` | `v1` |

#### Download

Both Qwen backbones have prebuilt FP16 OpenVINO IRs on Hugging Face:

```bash
pip install -U huggingface_hub

# Qwen3.5-2B (default)
hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen3.5-2B-FP16
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16

# Qwen3-0.6B
hf download OpenVINO/Qwen3-0.6B-fp16-ov --local-dir /opt/models/Qwen3-0.6B-FP16
export IR_OV_MODEL=/opt/models/Qwen3-0.6B-FP16
export IR_BACKBONE=qwen3-0.6b
```

There is no prebuilt FP16 IR for Llama-3.2-1B-Instruct, so convert it once
with optimum-cli:

```bash
pip install "optimum-intel[openvino]"

# Llama-3.2-1B-Instruct
optimum-cli export openvino --model meta-llama/Llama-3.2-1B-Instruct \
    --weight-format fp16 /opt/models/Llama-3.2-1B-Instruct-FP16
export IR_OV_MODEL=/opt/models/Llama-3.2-1B-Instruct-FP16
export IR_BACKBONE=llama3-1b
```

### When to Use Smaller Backbone

Use `qwen3-0.6b` (or `llama3-1b`) when memory or latency matters more than accuracy, for example use below command to switch to qwen3-0.6b:

```bash
hf download OpenVINO/Qwen3-0.6B-fp16-ov --local-dir /opt/models/Qwen3-0.6B-FP16
export IR_OV_MODEL=/opt/models/Qwen3-0.6B-FP16
export IR_BACKBONE=qwen3-0.6b

bash scripts/deploy_docker.sh --down && bash scripts/deploy_docker.sh
```

Check that the new backbone is serving:

```bash
docker logs inference-router 2>&1 | grep -E "Compiled backbone|Preloaded"
# Compiled backbone /models/ov-classifier on GPU (hidden=1024, ...)
# Preloaded 1 ModelBasedRule classifier(s) for the active policy
curl -s http://localhost:8000/v1/strategies/ModelBasedRouting | jq '.rules[0].prompt_info.status'
```

Other `IR_*` settings of model-based routing keep their defaults -- for example
`IR_ARTIFACTS_DIR=artifacts/router`, `IR_CACHE_SIZE=256`, `IR_FP_MIN_COS=0.98` and
`IR_SWAP_MODE=load_first`; to change one, add
it to the router's `environment:` in `deployment/docker/docker-compose-ui.yml` (or
`docker-compose.yml` with `--standalone`) and redeploy.

## Files to Edit

```text
src/rsd/strategy.yaml              Built-in strategy definitions
src/rsd/policy.yaml                Built-in policy definitions
<workspace>/strategy.yaml          Replaces the built-in strategies when present
<workspace>/policy.yaml            Replaces the built-in policies when present
config.yaml                        Runtime providers and active policy
<IR_ARTIFACTS_DIR>/<backbone>/vN.rcv   Classifier versions (Docker: workspace/artifacts/router/)
```
