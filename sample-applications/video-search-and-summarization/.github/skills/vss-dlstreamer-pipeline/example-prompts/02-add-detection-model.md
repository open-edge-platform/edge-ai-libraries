<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

We converted a custom YOLOv8 model to OpenVINO IR and want VSS's ingestion pipeline to use it instead of the default `yolov8l-worldv2.xml`. Where do I drop the model files and what code needs to change so `object_detection` requests pick it up on CPU?
