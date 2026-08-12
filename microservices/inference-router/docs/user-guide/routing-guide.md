# Routing Guide

This guide explains how to configure provider metadata, routing rules,
strategies, and policies in Inference Router.

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
| `ModelNameRule` | Match the request `model` field | `pattern`, `use_regex` |
| `MessageContentRule` | Match text in messages | `pattern`, `use_regex`, `roles` |
| `ToolCallsRule` | Require or reject tool definitions | `require_tools` |
| `MetadataRule` | Match fields in `extra_body` | `key`, `value` |
| `QueryComplexityScoreRule` | Match a complexity score | `score_range`, `target`, `operator` |
| `QueryComplexityZoneRule` | Bucket the last user message by word count | `zones` |
| `ContextLengthRule` | Bucket total message content length by character count | `zones` |
| `IntelligentRule` | Map the last user message to index `0` or `1` via the intelligent model-based classifier | _(none)_ |

`QueryComplexityScoreRule` is currently a placeholder: it returns the midpoint
of `score_range`, so it does not yet vary with request content.

## Built-in Strategies and Policies

The default strategies are defined in [src/rsd/strategy.yaml](src/rsd/strategy.yaml):

| Strategy | Trigger | Provider selector |
| --- | --- | --- |
| `Planning` | user message contains `plan` | `label: planning`, `capability.complexity >= 0.7` |
| `ContextLengthQuality` | total context length falls in configured zones | zone-based `capability.complexity` threshold |
| `ZeroCost` | always matches | `cost <= 0` |
| `IntelligentRouting` | classifier maps the last user message to index `0` or `1` | index-based `label` (`0: local`, `1: cloud`) |

The default policies are defined in [src/rsd/policy.yaml](src/rsd/policy.yaml):

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

`IntelligentRule` routes with the intelligent model-based classifier. It uses
the vendored [src/rsd/tools](../../src/rsd/tools/) Qwen3.5 classifier: the last
user message is mapped to an index (`0` or `1`). A strategy's index-keyed
`provider_selector` then picks a provider. For example, index `0` can require a
provider labelled `local`, and index `1` can require a provider labelled `cloud`.

This strategy is **available by default**，Reference it from a policy
to use it:

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


### Install

The classifier and its OpenVINO backend are ordinary dependencies of this
project. Use the normal project install:

```bash
pip install -e .
```

### Model Location

The OpenVINO classifier model is multi-GB and is not shipped in the package.
Set `IR_OV_MODEL` to the model directory on this host; there is no default
location.

```bash
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
```

`IR_OV_MODEL` must point to the converted OpenVINO IR directory for the
intelligent classifier, containing the OpenVINO model files (for the vision-
language export used here, `openvino_language_model.xml` / `.bin`,
`openvino_vision_embeddings_*`, etc.) and the matching tokenizer/config
artifacts loadable by `optimum-intel`.


Typical preparation flow:

```bash
# install huggingface CLI
pip install -U huggingface_hub
```

```bash
hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen2.5-2B-FP16
```

> ⚠️ **`/opt` permissions:** the default `/opt/models` is typically root-owned.
> Grant your user access
> (`sudo mkdir -p /opt/models && sudo chown "$USER:$USER" /opt/models`)

> For PRC users, you might need to set `export HF_ENDPOINT=https://hf-mirror.com`


Docker Compose uses the same variable: `IR_OV_MODEL` is the model path on the
host, and the compose file mounts it into the container automatically.

```bash
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
bash scripts/deploy_docker.sh
```

The directory must remain loadable by both
`AutoTokenizer.from_pretrained(...)` and
`OVModelForVisualCausalLM.from_pretrained(...)`, so keep the tokenizer,
chat template, model config, and OpenVINO IR files together in that directory.

The classifier is instantiated and loaded once at engine startup and cached, so
the first request pays no classifier cold-start penalty.

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

Route decisions include metadata such as `provider_name`, `policy_name`,
`criterion`, `strategy_name`, and `candidate_count`. Use these fields, logs, or
the metrics endpoint to verify why a provider was selected.

## Files to Edit

```text
src/rsd/strategy.yaml    Built-in strategy definitions
src/rsd/policy.yaml      Built-in policy definitions
config.yaml              Runtime providers and active policy
```