# How to add a new element

ViPPET does not implement its own GStreamer elements. The pipeline editor
exposes every element that appears in a pipeline definition, both the
standard GStreamer/DL Streamer elements (`filesrc`, `decodebin3`, `queue`,
`gvadetect`, `gvaclassify`, `gvatrack`, `gvawatermark`, `gvametaconvert`,
`gvametapublish`, ...) and any custom Python module loaded through
`gvapython`. To make a new element show up in the editor it is enough to
reference it in a pipeline (see
[How to add a new pipeline](./new-pipeline.md)). This page focuses on the
two extension points contributors actually have:

1. Loading custom Python scripts through the `gvapython` element.
2. Controlling whether an element is visible in the simplified pipeline view.

## Use custom `gvapython` modules (deprecated)

The `shared/scripts` directory contains user-defined Python scripts that
can be loaded as modules by the `gvapython` element.

To add and use a new script:

1. Drop your script into `shared/scripts` (for example
   `tracked_object_filter.py`).
2. In your pipeline description, set the `module` property on the
   `gvapython` element to the script filename.
   Example: `gvapython module=tracked_object_filter.py`.

No additional effort is needed, referencing the filename via `module` is
sufficient after the file is placed in this directory. The backend resolves
the filename to an absolute container path
(`/scripts/<file>.py`) when building the runnable pipeline command, and
maps it back to the bare filename when storing the graph.

> **Note:** The `shared/scripts` directory is excluded from linter checks, as it
> contains custom scripts that may not conform to standard linting rules.

### Limitations

Passing values to the `kwarg` property of the `gvapython` element in the
pipeline is not supported.

**Example of unsupported usage:**

```text
gvapython class=ObjectFilter module=tracked_object_filter.py kwarg="{\"reclassify_interval\": $BARCODE_RECLASSIFY_INTERVAL}"
```

## Element visibility in the simple view

The pipeline editor offers two views of every variant:

- **Advanced view**: the full graph, with every element and every caps
  filter, exactly as stored.
- **Simple view**: a curated subset that hides technical plumbing
  (queues, converters, demuxers, caps ...) and focuses on
  sources, inference and sinks.

The Simple view is computed by `Graph.to_simple_view()` in
`vippet/graph.py` and is driven by two environment variables, both
configured on the `vippet` service in `compose.yml`:

| Variable                         | Default                                                    | Meaning                                                                                                              |
|----------------------------------|------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| `SIMPLE_VIEW_VISIBLE_ELEMENTS`   | `*src,urisourcebin,gva*,*sink,source`                      | Comma-separated wildcard patterns. An element is a candidate for the Simple view only if its type matches one entry. |
| `SIMPLE_VIEW_INVISIBLE_ELEMENTS` | `gvafpscounter,gvametapublish,gvametaconvert,gvawatermark` | Comma-separated wildcard patterns. Matches are removed from the Simple view even if they also match the visible set. |

Evaluation order is **VISIBLE first, then INVISIBLE exclusions**. Caps nodes
(internal `__node_kind=caps`) are always hidden in the Simple view.

When introducing a new element (typically by writing a new pipeline that
references it):

- If the element is a meaningful, user-facing step (a new source family,
  a new inference element following the `gva*` naming, a new sink...) it
  will appear in the Simple view automatically thanks to the default
  patterns.
- If the element is purely technical plumbing (a new converter, a new
  parser, a buffering element...) and you do not want it on the Simple
  view, add it to `SIMPLE_VIEW_INVISIBLE_ELEMENTS` in `compose.yml`.
- If your element name does not match any of the existing patterns
  (for example it is not `*src` / `gva*` / `*sink` / `urisourcebin` /
  `source`) and should be exposed, extend `SIMPLE_VIEW_VISIBLE_ELEMENTS`
  accordingly. Keep the patterns broad and named, not pipeline-specific.

Any change to these variables must also be documented in the README and
in the *Key Environment Variables* table of
[`AGENTS.md`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/tools/visual-pipeline-and-platform-evaluation-tool/AGENTS.md).

## Related pages

- [How to add a new pipeline](./new-pipeline.md)
- [Backend contributing guide](./backend.md)
