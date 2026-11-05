<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Synthesize speech from text using the Text To Speech REST API:
- Check `GET /v1/audio/voices` first to confirm the active model and supported speakers
- Request a raw WAV file for a short kiosk-style prompt
- Request the same text again with `response_format=json` and decode `audio_base64` to a WAV file
- Capture `X-Session-ID` / `session_id` from both responses

Explain what the `model` field in the request body actually does (and does not do) for this service.
