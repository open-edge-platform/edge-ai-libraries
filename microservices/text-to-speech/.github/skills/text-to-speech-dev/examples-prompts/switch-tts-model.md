<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Switch an existing Text To Speech deployment from the shipped Kokoro default to Qwen3-TTS:
- Update `models.tts.name`, `runtime`, `device`, and `model_variant` in `config.yaml`
- Pick `custom_voice` or `voice_design` and explain what changes in the client request shape for each
- Restart the service and confirm `GET /v1/audio/voices` reflects the new model
- Note what happens to the old Kokoro model assets already cached under `models/`

Explain why `runtime`/`device` settings have no effect while Kokoro is configured, and why that changes once Qwen is selected.
