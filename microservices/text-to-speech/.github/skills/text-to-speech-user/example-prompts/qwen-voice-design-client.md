<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Generate speech with a custom-described voice on a Qwen3-TTS `voice_design` deployment:
- Compose a request that omits `voice` entirely and describes the desired voice in `instructions`
- Explain what happens if `voice` is supplied anyway, or if `instructions` is left empty
- Synthesize the audio and save it as a WAV file

Contrast this request shape with the equivalent request for a Qwen3-TTS `custom_voice` deployment, where `voice` selects a named speaker instead.
