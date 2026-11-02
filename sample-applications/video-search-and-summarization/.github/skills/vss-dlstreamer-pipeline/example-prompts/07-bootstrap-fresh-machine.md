<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

Our GPU-backed ingestion pipeline is spending too much time on CPU-side colorspace conversion before `gvadetect` runs. Can you show me where the `videoconvert`/`videoscale` elements sit in VSS's DLStreamer pipeline string and adjust it so the resize and format conversion happen on the VA-API/GPU path instead, keeping the rest of the ingestion pipeline behavior unchanged?
