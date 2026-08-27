<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

After `source setup.sh --summary`, video-ingestion logs are full of MQTT connection errors and I can't tell if it's RabbitMQ or MinIO that's actually broken. Nothing ever reaches the summarization stage even though I uploaded a video 10 minutes ago. Can you help me figure out which of RabbitMQ, MinIO, or Postgres is the actual blocker here?
