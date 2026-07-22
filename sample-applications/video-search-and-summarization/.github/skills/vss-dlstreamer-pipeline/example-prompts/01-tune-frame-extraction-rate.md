<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

Our surveillance clips have fast-moving forklifts and the current summaries miss short events. Right now we're extracting frames too sparsely. Can you show me where the `frame` and `chunk_duration` parameters are defined for VSS's ingestion pipelines, and change the defaults so we sample about 4 frames per 8-second chunk instead of the current 2-per-10?
