<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

How do I scaffold a `keyframe-extraction` module in pipeline-manager that listens on `AppEvents.FAST_TICK` and processes queued items the way `SummaryQueueService` does? It should enqueue work when a new `PipelineEvents.CHUNKING_COMPLETE` event fires, keep `waiting`/`processing` arrays, and emit a `keyframe.extraction.complete` event when done.
