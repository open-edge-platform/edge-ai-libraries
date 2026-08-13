# Policy Based Router Usage

This guide explains how to use and validate the policy based router in
Inference Router.

## Routing Model

The router makes a decision in three layers:

1. **Rule**: checks one request feature, such as message content, context length, tools, model name, or metadata.
2. **Strategy**: combines rules with AND semantics, then filters providers with `provider_selector`.
3. **Policy**: runs strategies in order and selects the final provider using `FirstMatch` or `AllMatch`.

If no policy can select a provider, the router falls back to the first available provider.


## Built-in Rules

Rules are configured in strategy YAML with `type` and `param`.

| Rule type | Purpose | Main params |
| --- | --- | --- |
| `MessageContentRule` | Match text in messages | `pattern`, `use_regex`, `roles` |
| `ToolCallsRule` | Require or reject tool definitions | `require_tools` |
| `MetadataRule` | Match fields in `extra_body` | `key`, `value` |
| `QueryComplexityScoreRule` | Match a complexity score | `score_range`, `target`, `operator` |
| `QueryComplexityZoneRule` | Bucket the last user message by word count | `zones` |
| `ContextLengthRule` | Bucket total message content length by character count | `zones` |
| `IntelligentRule` | Map the last user message to index `0` or `1` via the model-based classifier | _(none)_ |

`QueryComplexityScoreRule` is currently a placeholder: it returns the midpoint
of `score_range`, so it does not yet vary with request content.

## Built-in Strategies and Policies

The default strategies are defined in [src/rsd/strategy.yaml](../../src/rsd/strategy.yaml):

| Strategy | Trigger | Provider selector |
| --- | --- | --- |
| `Planning` | user message contains `plan` | `label: planning`, `capability.complexity >= 0.7` |
| `ContextLengthQuality` | total context length falls in configured zones | zone-based `capability.complexity` threshold |
| `ZeroCost` | always matches | `cost <= 0` |
| `IntelligentRouting` | classifier maps the last user message to index `0` or `1` | index-based `label` (`0: local`, `1: cloud`) |

The default policies are defined in [src/rsd/policy.yaml](../../src/rsd/policy.yaml):

| Policy | Criterion | Strategy order |
| --- | --- | --- |
| `Balanced` | `FirstMatch` | `Planning -> ContextLengthQuality` |
| `CostFirst` | `FirstMatch` | `ZeroCost` |

`FirstMatch` returns the first strategy that can produce a candidate provider.
`AllMatch` runs every strategy and selects a provider that appears in every
candidate list. The default YAML only uses `FirstMatch`; add an `AllMatch`
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
`complexity: {0: 0.3, 1: 0.5, 2: 0.7}`. Put `complexity` and `tool_calling`
under `provider_selector.capability`; placing them at the top level is invalid.

## Select a Policy

Choose the active policy in your runtime config:

```yaml
routing:
  policy: Balanced
```

Use `Balanced` when you want planning tasks and long-context quality routing.
Use `CostFirst` when you want to prefer free or local providers.

## Intelligent Routing

`IntelligentRule` routes with a model-based classifier (the vendored
[src/rsd/tools](../../src/rsd/tools/) Qwen3.5 classifier): the last user message
is mapped to an index (`0` or `1`), and a strategy's index-keyed
`provider_selector` picks the provider — for example index `0` → a
`local`-labelled provider, index `1` → a `cloud`-labelled provider.

Reference it from a policy to use it:

```yaml
strategies:
  - name: IntelligentRouting
    description: Route with the intelligent model-based classifier (0 -> local, 1 -> cloud).
    rules:
      - type: IntelligentRule
    provider_selector:
      label:
        0: local
        1: cloud
```

### Model

Set `IR_OV_MODEL` to the OpenVINO classifier model directory on the host:

```bash
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
```


## Exercise Routing Behavior

Useful requests to exercise the default policies:

| Goal | Request shape | Expected route behavior |
| --- | --- | --- |
| Hit `Planning` | user message contains `plan` | selects a provider with `planning` label and high complexity |
| Hit context zone 0 | total message content length `0-4000` chars | requires provider complexity `>= 0.3` |
| Hit context zone 1 | total message content length `4001-16000` chars | requires provider complexity `>= 0.5` |
| Hit context zone 2 | total message content length `16001-128000` chars | requires provider complexity `>= 0.7` |
| Hit `CostFirst` | set `routing.policy: CostFirst` | selects a provider with `cost <= 0` |
| Test fallback | make every selector fail | falls back to the first available provider |

### Intelligent routing examples

Simple request → routed to `local` (index `0`):

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "What is the capital of France?"}]
  }'
```

Complex request → routed to `cloud` (index `1`):

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Design a fault-tolerant, horizontally scalable rate limiter for a distributed API gateway. Compare token-bucket vs sliding-window-log, and analyze clock skew, Redis vs local counters, and behavior under network partitions."}]
  }'
```

Route decisions include metadata such as `provider_name`, `policy_name`,
`criterion`, `strategy_name`, and `candidate_count`. Use these fields, logs, or
the metrics endpoint to verify why a provider was selected.

## Files to Edit

```text
src/rsd/strategy.yaml    Built-in strategy definitions
src/rsd/policy.yaml      Built-in policy definitions
config.yaml              Runtime providers and active policy
```
