---
contract-version: "3.0.0"
source-files:
  - src/server/gstreamer_pipeline.py
  - src/server/schema.py
---

# Parameter Binding Contract — Normative Reference

This document is the normative specification for how pipeline parameters are applied to
GStreamer element properties by DL Streamer Pipeline Server. It is versioned by the
`contract-version` field in the YAML front matter above, which matches the service release
version in `document-versions.yaml`.

The machine-readable form of this contract is committed at
[`contract.json`](../../../../contract.json) (repo-relative, stable across patch releases).

For worked examples and request formats, see:
- [Defining Pipelines](defining_pipelines.md)
- [Customizing Pipeline Requests](customizing_pipeline_requests.md)

---

## 1. Scope

This contract covers GStreamer pipeline parameter binding only. FFmpeg pipeline parameter
binding is a separate concern and is not covered here.

A **pipeline definition** is a JSON document stored under `configs/` or loaded at startup.
It may contain a `parameters` section. A **pipeline request** is the JSON body sent to
`POST /pipelines/{name}/{version}`. The `parameters` field of the request is validated
against the JSON schema in the pipeline definition's `parameters` section, then applied
to the running GStreamer pipeline by `_set_section_properties` in
`src/server/gstreamer_pipeline.py`.

---

## 2. The `element` Field

Each property entry inside `parameters.properties` may carry an `element` field that
controls which GStreamer element(s) and property receive the value. There are three
binding forms.

### 2.1 String Form

```
"element": "<element-name>"
```

**Resolution:** The string is treated as the GStreamer element name. The property name
set on the element is taken from the parameter key itself.

**Implementation reference:** `_get_element_property` — `isinstance(element, str)` branch
returns `(element, key, None)`.

**Example:**

```json
"parameters": {
  "type": "object",
  "properties": {
    "inference-interval": {
      "element": "detection",
      "type": "integer",
      "default": 1
    }
  }
}
```

A request value of `{"inference-interval": 4}` calls
`detection.set_property("inference-interval", 4)`.

---

### 2.2 Object Form

```json
"element": {
  "name": "<element-name>",
  "property": "<property-name>",
  "format": "<format-value>"
}
```

`name` is required. `property` defaults to the parameter key when absent.
`format` is optional; see Section 3.

**Implementation reference:** `_get_element_property` — `isinstance(element, dict)` branch
returns `(element["name"], element.get("property", None), element.get("format", None))`.

**Example:**

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

A request value of `{"interval": 4}` calls
`detection.set_property("inference-interval", 4)`.

---

### 2.3 Array Form

```json
"element": [
  {"name": "<element-name-1>", "property": "<property-name-1>"},
  {"name": "<element-name-2>", "property": "<property-name-2>"}
]
```

Each entry in the array follows the object form rules. The same value is applied to
all listed element/property pairs.

**Implementation reference:** `_set_section_properties` — `isinstance(config[key]["element"], list)`
branch builds a list of `(element_name, property_name, format_type)` tuples and iterates them.

**Example:**

```json
"interval": {
  "element": [
    {"name": "detection",     "property": "inference-interval"},
    {"name": "classification","property": "inference-interval"}
  ],
  "type": "integer",
  "default": 1
}
```

A request value of `{"interval": 4}` calls `set_property("inference-interval", 4)` on both
`detection` and `classification`.

---

## 3. The `format` Field

The `format` field is valid inside an object or array element entry. It controls how the
parameter value is transformed before being passed to `element.set_property`.

### 3.1 `format: element-properties`

The parameter value must be a JSON object. Each key/value pair in the object is applied
as a separate `set_property` call on the named element.

**Use case:** Exposing all writable properties of an element through a single pipeline
parameter without enumerating each property explicitly.

**Implementation reference:** `_set_section_properties` — `format_type == "element-properties"`
branch iterates `request[key].items()` and calls `_set_element_property` for each pair.

**Example:**

```json
"properties": {
  "type": "object",
  "element": {
    "name": "source",
    "format": "element-properties"
  }
}
```

Request `{"properties": {"uri": "rtsp://camera/stream", "latency": 100}}` results in:
- `source.set_property("uri", "rtsp://camera/stream")`
- `source.set_property("latency", 100)`

### 3.2 `format: json`

The parameter value is passed to `json.dumps` before being set on the element property.

**Use case:** GStreamer properties that expect a JSON string rather than a native type.

**Implementation reference:** `_set_element_property` — `format_type == "json"` branch calls
`element.set_property(property_name, json.dumps(property_value))`.

**Example:**

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

Request `{"tags": {"location": "building-1"}}` passes the string
`'{"location": "building-1"}'` to `metaconvert.set_property("tags", ...)`.

### 3.3 No `format` (default)

The parameter value is passed directly to `element.set_property` without transformation.

---

## 4. Unresolved-Property Behavior

### 4.1 Element not found in pipeline

If `pipeline.get_by_name(element_name)` returns `None`, the binding is skipped. A DEBUG
message is logged:

```
Parameter <property_name> given for element <element_name> but no element found
```

The pipeline continues normally. No exception is raised.

### 4.2 Property not in element's property list

If the element is found but the property name is not in `element.list_properties()`, the
binding is skipped. A DEBUG message is logged:

```
Parameter <property_name> given for element <element_gtype_name> but no property found
```

The unset binding is appended to `_unset_properties` for observability. The pipeline
continues normally. No exception is raised.

---

## 5. Reserved Element Names

The following element names have special handling wired into the pipeline server modules.
Using these names in a pipeline template triggers that handling automatically.

| Name | Special handling |
|------|-----------------|
| `source` | Auto-wired from the `source` section of the request (URI, webcam device, GST element, or application source). |
| `destination` | Auto-wired from the `destination` section of the request. |
| `appsink` | Used internally for frame-level destinations (RTSP, WebRTC). Setting `name=appsink` on an appsink element enables frame capture. |
| `metaconvert` | Used for metadata publishing. The `source` and `tags` properties have built-in element bindings in `schema.py`. |

---

## 6. Downstream Adapter Responsibilities

The parser applies values to elements — it does not generate or validate the values
themselves. A downstream adapter (the component that constructs the pipeline request)
is responsible for:

- Supplying parameter values that are valid for the target GStreamer property type.
- Providing `format: json` values as JSON-serializable Python objects, not pre-encoded strings.
- Using reserved element names only when intending to trigger their built-in handling.
- Checking `_unset_properties` (surfaced in pipeline status) to detect silently dropped bindings.

---

## 7. Contract Stability Guarantees

| Category | Stability |
|----------|-----------|
| Three binding forms (string, object, array) | Stable across all releases in this major version. |
| `format: element-properties` behavior | Stable. |
| `format: json` behavior | Stable. |
| Unresolved-element behavior (log, no raise) | Stable. |
| Reserved element names | Additive changes only (new names may be added; existing names will not change behavior within a major version). |

A **contract-breaking change** is any change that alters the items marked Stable above.
Such changes are release blockers until a migration note is published using the template at
[`../release-notes/contract-migration-template.md`](../release-notes/contract-migration-template.md)
and `contract.json` is updated with the new `contract-version`.
