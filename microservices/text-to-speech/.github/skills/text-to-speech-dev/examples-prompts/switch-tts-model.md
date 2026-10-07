<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Switch an existing Text To Speech deployment from the shipped Kokoro default to SpeechT5:
- Update `models.tts.name`, `runtime` (must be `openvino` — SpeechT5 has no working PyTorch implementation), and `device` in `config.yaml`
- Restart the service and confirm `GET /v1/audio/voices` reflects the new model and its seven bundled voices
- Note what happens to the old Kokoro model assets already cached under `models/`

Explain why `runtime`/`device` settings have no effect while Kokoro is configured, and why that changes once SpeechT5 is selected. If the user specifically asks about switching to Qwen3-TTS instead, explain that it currently cannot run on any device due to a `qwen-tts`/`transformers` dependency conflict and the service will fail to start — do not walk them through deploying it as if it works.
