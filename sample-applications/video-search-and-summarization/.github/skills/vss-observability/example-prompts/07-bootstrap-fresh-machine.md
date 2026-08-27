<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I ran a batch of videos through VSS summarization yesterday with tracing enabled, and I want to compare how long chunking, captioning, and final summarization each took across those runs. What's the best way to pull per-stage span durations out of my OTLP backend so I can see which stage is actually the bottleneck?
