<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Configure the Audio Analyzer for OpenVINO GPU and NPU acceleration:
- Set `models.asr.provider: openvino` and the target `device` in `config.yaml`
- Pass `/dev/dri` through for GPU (already default) and set `RENDER_GID` in `.env` to the host's actual render group GID (never assume the `992` fallback is correct)
- Set `ACCEL_MOUNT_PATH` for NPU
- Verify the resolved Compose device mapping before starting the container
- Confirm `ov.Core().available_devices` reports the expected device set inside the container
- Explain the `whisper-large` NPU inference limitation and which models are safe to use on NPU

Use the Docker Compose path rather than a host `.venv`, and explain why that distinction matters for device visibility.
