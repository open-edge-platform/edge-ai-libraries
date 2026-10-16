<!--SPDX-License-Identifier: Apache-2.0-->

# Custom GStreamer plugins

This directory hosts custom GStreamer plugins that ship with ViPPET and are
discovered automatically by the pipeline runner.

## Layout

```text
gst_plugins/
├── python/                 # Python-based elements (loaded by libgstpython.so)
│   └── <element_name>.py   # Each file exports __gstelementfactory__
└── README.md
```

## How discovery works

At runtime the pipeline runner prepends the absolute path of `gst_plugins/`
to `GST_PLUGIN_PATH` before spawning the `gst_runner.py` subprocess. GStreamer
scans that path at `Gst.init()`, and the bundled Python plugin loader
(`libgstpython.so`) imports every `*.py` file in the `python/` subdirectory
that defines an `__gstelementfactory__` tuple. Any pipeline that references
one of those factory names will pick it up transparently — no per-element
registration required.

## Adding a new Python element

1. Drop a new `.py` file into `python/`.
2. Subclass `GstBase.BaseTransform` (or another `Gst.Element` subclass).
3. Register the factory at module scope:

   ```python
   __gstelementfactory__ = ("<element_name>", Gst.Rank.NONE, <ClassName>)
   ```

4. Reference the element by its factory name in any pipeline description.
