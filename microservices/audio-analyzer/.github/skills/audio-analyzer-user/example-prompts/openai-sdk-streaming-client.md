<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Point the official OpenAI Python SDK at the Audio Analyzer service for streaming transcription:
- Set `base_url` to this service's `/v1` path and use a placeholder API key
- Call `audio.transcriptions.create` with `model="whisper-1"`, `stream=True`, and a valid `response_format`
- Handle the `transcript.text.delta` and `transcript.text.done` events as they arrive
- Stop reading at the `[DONE]` sentinel

Explain why `response_format` must be `json` or `verbose_json` for this to work, and what happens if `srt`/`vtt`/`text` is requested with streaming enabled.
