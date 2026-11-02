<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Add a downloader plugin for a model hub named `myhub`:
- Implement the plugin and its download behavior
- Register the plugin and add the `ModelHub` value
- Add any optional dependencies required by the provider
- Enable the plugin through the service startup flow
- Add unit tests for routing, downloads, errors, and returned paths

Start the service with the new plugin, submit a model download request, and verify that the job completes with a host-visible download path.
