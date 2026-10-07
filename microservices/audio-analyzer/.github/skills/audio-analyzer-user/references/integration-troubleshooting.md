<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Integration Troubleshooting

Client-side integration failures, grouped by symptom.

---

## HTTP 400 on `stream=true`

**Symptom:** `POST /v1/audio/transcriptions` with `stream=true` returns 400.

**Cause:** `response_format` is `srt`, `vtt`, or `text`. Streaming only
supports `json` or `verbose_json`.

**Fix:** Either drop `stream=true` for subtitle/plain-text output, or switch
`response_format` to `json`/`verbose_json` when streaming.

---

## Lost Conversation Context Across Uploads

**Symptom:** A second upload starts a brand-new transcript instead of
continuing the first.

**Cause:** The client did not capture and resend `session_id`.

**Fix:** Read the `X-Session-ID` response header from the first call and
pass it back as the `session_id` form field on subsequent uploads (or as the
`session_id` query param when opening a new realtime WebSocket connection).

---

## Realtime WebSocket Never Emits `speech_started`

**Symptom:** Audio is streamed over `/v1/realtime` but
`input_audio_buffer.speech_started` never fires, so no transcript is ever
produced.

**Likely causes, in order:**
1. Audio is quieter than the default VAD `threshold` (`0.02` normalized RMS)
   — lower it via `session.update` (e.g. `0.005` for quiet sources).
2. Audio is not actually PCM16 mono — any other encoding (e.g. raw MP3
   bytes, stereo, float32) will not trigger VAD correctly because the
   service does not transcode in the socket layer.
3. The sample rate does not match what the session was told via
   `session.update` — mismatched rates distort timing analysis.

**Fix:** Confirm the client is sending base64 PCM16 mono at the declared
sample rate, and lower `threshold` for a quick sanity check before assuming
a deeper issue.

---

## `/v1/audio/transcriptions/stream` Rejects a `device` Field

**Symptom:** Sending `device=GPU` as a form field to the NDJSON streaming
endpoint has no visible effect, or the client assumes it was honored.

**Cause:** The per-request `device` override only exists on
`POST /v1/audio/transcriptions` (single-response and `stream=true` forms).
The NDJSON endpoint, the realtime WebSocket, and the VSS-compatible routes
always use the service-configured device.

**Fix:** If per-request device selection is a hard requirement, use
`POST /v1/audio/transcriptions` (optionally with `stream=true`) instead of
the NDJSON endpoint.

---

## Unsupported/Unavailable `device` Rejected, Not Downgraded

**Symptom:** Passing `device=NPU` (or `GPU`) fails the request outright.

**Cause:** This is deliberate — the service never silently falls back to
CPU for an unsupported or unavailable device. If the deployed service's
OpenVINO runtime does not expose that device, the request fails.

**Fix:** This is a deployment-side configuration question, not a client
bug. Ask the operator to confirm the device is actually available on that
deployment (see the `audio-analyzer-dev` skill), or drop the per-request
override and rely on the service default.

---

## VSS-Compatible `POST /transcriptions` Returns 503

**Symptom:** A MinIO-source request (`minio_bucket`/`video_id`/`video_name`)
to `/transcriptions` or `/api/v1/transcriptions` returns 503.

**Cause:** `minio.endpoint` is empty in the deployed service's
configuration — MinIO support is disabled by design until configured.

**Fix:** This requires the deployment operator to configure
`minio.endpoint`/`access_key`/`secret_key`. A direct file upload to the same
endpoint works regardless of MinIO configuration.

---

## Port Confusion (8010 vs. 8000)

**Symptom:** A client built against VSS's own Compose assumes port `8000`,
but a direct/local deployment of Audio Analyzer is unreachable there.

**Cause:** The standalone and direct-Docker-Compose default is port `8010`.
VSS's own Compose remaps this service to container port `8000` using
`AUDIO_ANALYZER_SERVER_PORT` — that remap is specific to the VSS stack, not
a general default.

**Fix:** Use `8010` unless the target deployment is explicitly known to be
the VSS-bundled Compose stack.

---

## Sentiment Fields Missing From the Response

**Symptom:** `sentiment_summary` never appears in `transcript.text.done`,
`.completed` events, or the final JSON body.

**Cause:** Sentiment analysis is a deployment-time setting
(`sentiment.enabled` in the service's `config.yaml`), not a per-request
flag. If the deployed service does not have it enabled, no amount of
request-side configuration will produce it.

**Fix:** Confirm with the deployment owner whether sentiment is enabled; if
not, this is expected behavior, not a bug.

---

## Treating `/transcriptions` as OpenAI-Compatible

**Symptom:** A client built for the OpenAI SDK contract is pointed at
`POST /transcriptions` (no `/v1` prefix) and the response shape does not
match what the SDK expects.

**Cause:** `/transcriptions` (and its `/api/v1/transcriptions` twin) is the
VSS-compatible contract — it returns a job-status object
(`status`/`job_id`/`transcript_path`), not an OpenAI-shaped transcript.

**Fix:** Use `POST /v1/audio/transcriptions` for OpenAI-SDK-compatible
integrations.
