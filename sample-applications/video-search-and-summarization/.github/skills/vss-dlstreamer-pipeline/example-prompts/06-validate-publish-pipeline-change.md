<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I just changed the `chunk_duration` default and touched `video-ingestion/src/publish.py` slightly to log extra fields. How do I confirm the pipeline is still writing correct frame JPEGs and metadata to MinIO and that RabbitMQ is still getting chunk messages, without guessing from the UI?
