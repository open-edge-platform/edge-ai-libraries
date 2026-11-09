<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Deploy the Audio Analyzer microservice with Docker Compose:
- Configure `.env` (`REGISTRY`, `RELEASE_TAG`) and review `config.yaml` before starting
- Start the service with the prebuilt image (pull) rather than rebuilding from source
- Confirm the container is healthy and listening on port 8010
- Run a batch transcription smoke test against the sample audio file
- Explain where model, chunk, storage, and Hugging Face cache data are persisted

Call out the fixed UID/GID `1000:1000` requirement and why host volumes should not be reused across a root-only run.
