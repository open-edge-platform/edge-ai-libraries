<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0 -->

After I call `/manager/summary` and get back a `summaryPipelineId`, I want a Node.js script using `socket.io-client` that connects to VSS, joins that room, and logs each `chunks`, `frameSummary`, and `summaryStream` event as they arrive so I can show a live progress bar in my app.
