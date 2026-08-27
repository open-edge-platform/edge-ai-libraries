<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I ran `source setup.sh --summary` and every container shows as up. The UI is reachable on port 12345 and the job gets created, but after I upload an MP4 the summary just sits in `Ready` or `In Progress` forever and no final summary ever appears. `video-ingestion` seems alive because `curl http://localhost:8090/pipelines` returns data. What should I check for this "everything is up but nothing happens" case?
