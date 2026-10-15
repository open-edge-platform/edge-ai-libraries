<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Download a Hugging Face model through the Model Download REST API:
- Use `sentence-transformers/all-MiniLM-L6-v2` as the public-model example
- Use `meta-llama/Llama-3.2-1B` as the gated-model example
- Configure authentication only when the selected model requires it
- For the gated example, show both auth paths and their different token encodings:
  restarting the service with a plain-text `HUGGINGFACEHUB_API_TOKEN`/`HF_TOKEN`
  env var, versus a per-request top-level `override_credentials.HF_TOKEN`
  (sibling of `name`/`hub`/`config`) that must be base64-encoded
- For the per-request path, prompt the user (via `ask_user`) for their
  already-base64-encoded `HF_TOKEN` before submitting the job — do not ask for
  the raw token and encode it yourself. Pass the value the user supplies
  as-is into `override_credentials.HF_TOKEN` in the request body
- Show how to pin a model revision for reproducible downloads
- Submit the job and poll it until completion

Verify the downloaded model location and explain any license-acceptance requirement for gated models.
If the job fails with `401`/`403`/"is gated", check whether the token encoding
matches the auth path used (raw for env vars and the CLI, base64 for
`override_credentials`) before re-submitting.
