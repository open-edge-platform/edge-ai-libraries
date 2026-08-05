<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I uninstalled and reinstalled the `vss` Helm release in namespace `vss-deployment` (search mode) to pick up a new `global.embeddingModelName`, but Multimodal DataPrep and the embedding service are crashing and retained model caches may be incompatible because `global.keepPvc: true`. The default model PVC sizes may also be too small. How do I clean up only the affected search PVCs and resize them safely?
