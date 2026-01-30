# Use Custom gvapython Modules

The `shared/scripts` directory contains user-defined Python scripts that can be loaded as modules by the `gvapython` element.

To add and use a new script:

1. Drop your script into `shared/scripts` (for example `tracked_object_filter.py`).
2. In your pipeline description, set the `module` property on the `gvapython` element to the script filename.
   Example: `gvapython module=tracked_object_filter.py`.

No additional effort is needed — referencing the filename via `module` is sufficient after the file is placed in this directory.

## Limitations

Passing values to the `kwarg` property of the `gvapython` element in the pipeline is not supported.

**Example of unsupported usage:**

`gvapython class=ObjectFilter module=tracked_object_filter.py kwarg="{\"reclassify_interval\": $BARCODE_RECLASSIFY_INTERVAL}"`

## Note

The `shared/scripts` directory is excluded from linter checks,
as it contains custom scripts that may not conform to standard linting rules.
