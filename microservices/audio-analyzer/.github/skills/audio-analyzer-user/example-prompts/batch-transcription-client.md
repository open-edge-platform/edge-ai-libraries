<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Build a batch transcription client against the Audio Analyzer REST API:
- Upload a finite audio file to `POST /v1/audio/transcriptions`
- Capture the `X-Session-ID` response header for later reuse
- Request `verbose_json` to get per-segment timestamps alongside the full text
- Re-upload a second file with the captured `session_id` to continue the same conversation

Verify both calls succeed and explain where the accumulated session transcript is stored.
