<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I edited the `object_detection` pipeline string in `video-ingestion/resources/conf/config.json` to insert a `videoscale` step before `gvadetect`, restarted `video-ingestion`, and now every POST to `/pipelines/user_defined_pipelines/object_detection` fails immediately instead of returning a pipeline id. TypeScript compiled fine. What's the most likely cause and how do I isolate it?
