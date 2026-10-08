<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Convert `sentence-transformers/all-MiniLM-L6-v2` to an OVMS-ready OpenVINO embedding model for a RAG pipeline:
- Enable the required Model Download plugins
- Use INT8 precision on CPU
- For the per-request path, prompt the user (via `ask_user`) for their
  already-base64-encoded `HF_TOKEN` before submitting the job — do not ask for
  the raw token and encode it yourself. Pass the value the user supplies
  as-is into `override_credentials.HF_TOKEN` in the request body
- Submit the conversion job and poll it until completion
- Verify the converted model output path

Also provide an equivalent conversion request for a reranker model such as `cross-encoder/ms-marco-MiniLM-L-6-v2`.
