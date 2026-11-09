<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Diagnose a Text To Speech deployment configured with a currently non-functional model:
- Recognize the `"qwen-tts is not installed..."` startup failure as a known dependency conflict, not a misconfiguration
- Explain the exact root cause: `qwen-tts` pins `transformers==4.57.3`, this service requires `transformers>=5.3.0` for security fixes, and the two cannot be installed together
- Recognize the separate `"parler-tts is not installed..."` failure as an unrelated missing-package gap
- Recommend SpeechT5 (`openvino`, CPU or GPU) or Kokoro (CPU) as the currently deployable alternatives

Explain why isolating by `device` (CPU vs GPU vs NPU) will not resolve either failure, since both fail during model import before any device-specific code runs.
