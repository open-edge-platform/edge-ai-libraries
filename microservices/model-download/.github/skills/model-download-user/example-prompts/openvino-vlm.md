<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Convert `llava-hf/llava-1.5-7b-hf` to OpenVINO IR for OVMS deployment:
- Enable the required download and conversion plugins
- Use INT4 precision on CPU
- Select an appropriate VLM pipeline type
- Configure the cache size
- For the per-request path, prompt the user (via `ask_user`) for their
  already-base64-encoded `HF_TOKEN` before submitting the job — do not ask for
  the raw token and encode it yourself. Pass the value the user supplies
  as-is into `override_credentials.HF_TOKEN` in the request body
- Submit the conversion job and monitor it until completion
- Verify the converted model output

Include guidance for reducing memory use if the conversion fails because of insufficient memory.
