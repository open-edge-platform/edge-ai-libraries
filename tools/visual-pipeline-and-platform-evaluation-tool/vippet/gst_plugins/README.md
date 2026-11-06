<!--SPDX-License-Identifier: Apache-2.0-->

# Custom GStreamer plugins

This directory hosts custom GStreamer plugins that ship with ViPPET and are
loaded by DL Streamer Pipeline Server 2.0, which runs every pipeline.

## Layout

```text
gst_plugins/
├── python/                 # Python-based elements (loaded by libgstpython.so)
│   └── <element_name>.py   # Each file exports __gstelementfactory__
└── README.md
```

## How discovery works

The directory is copied into the `vippet` image. At startup, the one-shot
`vippet-plugins` service copies it from that image into `shared/gst-plugins/`,
replacing the previous contents, so the copy always matches the `vippet` image
in use. The `dlstreamer-pipeline-server` service mounts that folder read-only
at `/opt/vippet/gst_plugins` and sets `ADDITIONAL_GST_PLUGIN_PATH` to it; the
server appends it to `GST_PLUGIN_PATH`. GStreamer scans that path at
`Gst.init()`, and the bundled Python plugin loader (`libgstpython.so`) imports
every `*.py` file in the `python/` subdirectory that defines an
`__gstelementfactory__` tuple. Any pipeline that references one of those
factory names will pick it up transparently — no per-element registration
required.

The `vippet` process itself does not load these elements: its
`GST_PLUGIN_PATH` does not include this directory. The DL Streamer pipeline
optimizer, which runs in the `vippet` process, therefore does not see them.

## Adding a new Python element

1. Drop a new `.py` file into `python/`.
1. Subclass `GstBase.BaseTransform` (or another `Gst.Element` subclass).
1. Register the factory at module scope:

   ```python
   __gstelementfactory__ = ("<element_name>", Gst.Rank.NONE, <ClassName>)
   ```

1. Reference the element by its factory name in any pipeline description.
1. Rebuild the `vippet` image (`make build`) and restart the stack, so that
   `vippet-plugins` copies the new element for the server.
