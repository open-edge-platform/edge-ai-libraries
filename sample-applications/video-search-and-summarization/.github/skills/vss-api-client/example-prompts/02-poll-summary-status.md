<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0 -->

I already have a `videoId` from uploading a clip to VSS. Now I need Python code that calls `POST /manager/summary` with a sampling config (30 second chunks, 4 frames per chunk) to kick off summarization, then repeatedly polls `GET /manager/summary/{stateId}` every few seconds until `videoSummaryStatus` says complete, and finally prints the summary text.
