<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I have a fresh Kubernetes cluster with `kubectl` and Helm 3 already working, and I want to deploy VSS in summary-only mode (no search, no vLLM) using the chart under `sample-applications/video-search-and-summarization/chart`. Give me the exact `helm install` command, the override files to use, and the minimum `user_values_override.yaml` values I need to fill in for credentials and the VLM model before running it. I want to put it in a namespace called `vss-deployment`.
