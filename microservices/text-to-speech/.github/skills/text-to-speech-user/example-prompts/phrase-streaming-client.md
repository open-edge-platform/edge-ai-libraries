<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Consume the phrase-level SSE streaming endpoint for lower time-to-first-audio:
- Call `POST /v1/audio/speech/stream` with a multi-sentence `input`
- Parse each `data: {...}` event, decode its `audio_base64`, and play/queue phrases as they arrive
- Stop reading at `data: [DONE]`
- Handle the case where only a single event is emitted before `[DONE]`

Explain what the client should do if an event's payload contains an `error` key instead of audio.
