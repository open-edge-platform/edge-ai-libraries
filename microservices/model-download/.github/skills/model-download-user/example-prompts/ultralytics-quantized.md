<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Download `yolov8n` from Ultralytics and apply INT8 post-training quantization:
- Enable the Ultralytics plugin
- Use the COCO128 calibration dataset
- Submit the download job and poll it until completion
- Verify the generated model location

Also show how to download the model without quantization and how to request multiple models. Explain why quantization can only be used with a single model per request.
