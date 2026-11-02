<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I'm calling `POST /summary` directly with `sampling.samplingFrame: 10`, `sampling.frameOverlap: 4`, and `sampling.multiFrame: 12`, and the pipeline manager rejects it with a BadRequestException. My compose deployment has `PM_MULTI_FRAME_COUNT=12`. Why is this failing and what values should I use instead?
