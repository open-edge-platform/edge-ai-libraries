<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Create a reusable, provider-neutral blueprint for a new Model Download downloader or converter plugin:
- Implement the plugin interface and request matching
- Run synchronous provider operations without blocking the async event loop
- Handle model output directories and return host-visible paths
- Define successful and failed result shapes
- Cover plugin registration, activation, and optional dependencies
- Propagate provider errors clearly

Keep the blueprint generic so it can be adapted to an SDK, REST API, or CLI-based provider.
