# DL Streamer Pipeline Server — Agent Entry Point

## What This Service Does

Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) is a containerized
microservice for launching, managing, and monitoring video analytics pipelines. It exposes
a REST API for pipeline lifecycle (start, stop, status) and accepts per-request configuration
that controls how GStreamer element properties are set at pipeline launch time.

This file is the canonical entry point for agents and external integrators arriving at this
folder. It describes the parameter-application contract: how values supplied in a pipeline
request are bound to GStreamer element properties.

## Contract Files

| File | Purpose |
|------|---------|
| [`contract.json`](contract.json) | Machine-readable contract artifact. Stable at this repo-relative path across all patch releases. |
| [`docs/user-guide/advanced-guide/detailed_usage/rest_api/parameter_contract.md`](docs/user-guide/advanced-guide/detailed_usage/rest_api/parameter_contract.md) | Normative prose reference for all binding semantics. Contains the `contract-version` field. |
| [`docs/user-guide/release-notes/contract-migration-template.md`](docs/user-guide/release-notes/contract-migration-template.md) | Template used for any release that contains contract-breaking changes. |
| [`tests/test_parameter_contract.py`](tests/test_parameter_contract.py) | Conformance tests. Every binding form described below is covered by at least one test. |

## Parameter Binding Contract

### Overview

A pipeline definition contains a `parameters` section that declares which properties are
configurable and how they map to GStreamer elements. When a request arrives, the pipeline
server reads the `element` field from each parameter schema entry and applies the supplied
value to the corresponding GStreamer element property.

### The Three `element` Binding Forms

#### 1. String form

```json
"inference-interval": {
    "element": "detection",
    "type": "integer",
    "default": 1
}
```

The string is the element name. The property name is taken from the parameter key
(`inference-interval` in this example).

#### 2. Object form

```json
"interval": {
    "element": {
        "name": "detection",
        "property": "inference-interval"
    },
    "type": "integer",
    "default": 1
}
```

The object specifies the element `name` and the explicit `property` name to set.
An optional `format` field controls serialization (see below).

#### 3. Array form

```json
"interval": {
    "element": [
        {"name": "detection",  "property": "inference-interval"},
        {"name": "classification", "property": "inference-interval"}
    ],
    "type": "integer",
    "default": 1
}
```

The array applies the same value to all listed element/property pairs. Each entry
follows the same rules as the object form.

### The Two `format` Values

The `format` field is only valid inside an object or array element entry.

| `format` value | Behavior |
|----------------|----------|
| `element-properties` | The parameter value must be a JSON object. Each key/value pair in the object is applied as a separate property on the named element. Used when a single parameter should fan out across an element's entire property set. |
| `json` | The parameter value is JSON-serialized (`json.dumps`) before being passed to `element.set_property`. Required for GStreamer properties that expect a JSON string (e.g. `metaconvert.tags`). |
| _(absent)_ | The value is passed directly to `element.set_property` without transformation. |

**Example — `element-properties`:**

```json
"properties": {
    "type": "object",
    "element": {
        "name": "source",
        "format": "element-properties"
    }
}
```

A request value of `{"device": "/dev/video0", "do-timestamp": true}` causes
`source.device = /dev/video0` and `source.do-timestamp = true` to be set individually.

**Example — `json`:**

```json
"tags": {
    "type": "object",
    "element": {
        "name": "metaconvert",
        "property": "tags",
        "format": "json"
    }
}
```

A request value of `{"city": "Seattle"}` is passed to the element as the string
`'{"city": "Seattle"}'`.

### Unresolved-Property Behavior

| Condition | Behavior |
|-----------|---------|
| Named element not present in the pipeline | Logged at DEBUG level. Pipeline continues without error. |
| Element present but property not in its property list | Logged at DEBUG level. Value recorded in `_unset_properties`. Pipeline continues without error. |

Neither condition raises an exception or transitions the pipeline to an error state.

### Reserved Element Names

The following element names have special default handling built into the pipeline server.
Do not reuse these names for custom elements unless you intend to trigger that handling.

| Name | Default handling |
|------|-----------------|
| `source` | URI, device, or custom GST element wired automatically from the `source` section of the request. |
| `destination` | Output sink wired from the `destination` section of the request. |
| `appsink` | Used internally for frame-level destinations (RTSP, WebRTC). |
| `metaconvert` | Used for metadata publishing; `source` and `tags` properties have built-in bindings. |

## Conformance Tests

`tests/test_parameter_contract.py` asserts the following invariants:

1. String-form binding sets the property named by the parameter key on the named element.
2. Object-form binding sets the explicitly named `property` on the named element.
3. Array-form binding applies to all listed elements.
4. `format: element-properties` fans out key/value pairs as individual property calls.
5. `format: json` JSON-serializes the value before calling `set_property`.
6. An unresolved element name is logged and does not raise an exception.

## Contract-Breaking Change Policy

A change is contract-breaking if it:
- Removes or renames a supported `format` value.
- Changes the property resolution rule for any binding form.
- Changes unresolved-property behavior from log-and-continue to raise.

Contract-breaking changes are release blockers until a migration note is published using
[`docs/user-guide/release-notes/contract-migration-template.md`](docs/user-guide/release-notes/contract-migration-template.md)
and `contract.json` is updated with the new `contract-version`.

## Further Reading

- Full parameter examples: [`docs/user-guide/advanced-guide/detailed_usage/rest_api/defining_pipelines.md`](docs/user-guide/advanced-guide/detailed_usage/rest_api/defining_pipelines.md)
- Request customization: [`docs/user-guide/advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md`](docs/user-guide/advanced-guide/detailed_usage/rest_api/customizing_pipeline_requests.md)
- REST API reference: [`docs/user-guide/api-reference.md`](docs/user-guide/api-reference.md)
