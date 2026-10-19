<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Enable speaker diarization and voice sentiment on an existing Audio Analyzer deployment:
- Set `models.asr.diarization: true` and configure `min_speakers`/`max_speakers` for the scenario
- Obtain a Hugging Face token, accept the Pyannote speaker-diarization model license, and wire `HF_TOKEN` into the deployment
- Set `sentiment.enabled: true` and choose a provider/device appropriate for the host
- Restart the service and confirm both features are active without breaking plain transcription

Explain the soft-fail behavior when diarization credentials are missing or incomplete, and how to tell it apart from a hard startup failure.
