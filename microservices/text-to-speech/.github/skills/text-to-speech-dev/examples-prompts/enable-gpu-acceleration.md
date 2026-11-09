<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Configure the Text To Speech service for OpenVINO GPU acceleration:
- Set `models.tts.runtime: openvino` and `device: GPU` for SpeechT5 or Qwen3-TTS
- Set `RENDER_GID` in `.env` to the host's actual render group GID rather than the Compose default
- Verify `/dev/dri` passthrough and confirm the container can access the render node
- Choose `dtype: fp16` and explain why `int4` should be avoided on integrated GPU

Diagnose a "[GPU] Context was not initialized for 0 device" failure if the container fails to start after this change.
