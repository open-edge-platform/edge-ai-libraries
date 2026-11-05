<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Before writing any client code, confirm whether Qwen3-TTS is actually deployable: this model currently cannot run on any device (CPU, GPU, or NPU) due to a `qwen-tts`/`transformers` dependency conflict, so a Qwen3-TTS-configured service will fail at startup. If the user needs this today, point them at SpeechT5 or Kokoro instead.

If the goal is understanding the intended request contract for when Qwen3-TTS becomes usable, document it as reference material:
- Compose a request that omits `voice` entirely and describes the desired voice in `instructions`
- Explain what happens if `voice` is supplied anyway, or if `instructions` is left empty
- Contrast this request shape with the equivalent request for a Qwen3-TTS `custom_voice` deployment, where `voice` selects a named speaker instead

Do not present this as a working walkthrough against a live deployment.
