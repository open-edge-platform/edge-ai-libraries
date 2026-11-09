<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Build a live voice transcription client against `WS /v1/realtime`:
- Connect with `intent=transcription` and read the initial `transcription_session.created` event
- Stream base64-encoded PCM16 mono audio frames via `input_audio_buffer.append`
- React to `input_audio_buffer.speech_started`/`speech_stopped` and the per-utterance transcription events
- Tune the VAD `threshold` for a quiet audio source using `session.update`

Explain why the client — not the service — is responsible for microphone capture, and what to check if `speech_started` never fires.
