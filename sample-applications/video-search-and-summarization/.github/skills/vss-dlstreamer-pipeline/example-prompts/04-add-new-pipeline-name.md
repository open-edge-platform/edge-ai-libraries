<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

We want a third ingestion option called `motion_detection` that adds a `gvadetect` step reusing a lightweight motion model, but keeps the same publish/chunking behavior as `video_ingestion`. Walk me through every file I need to touch in VSS so it shows up as a selectable pipeline in the pipeline-manager API and actually runs.
