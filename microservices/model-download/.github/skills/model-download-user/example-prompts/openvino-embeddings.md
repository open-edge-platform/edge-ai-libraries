<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Convert `sentence-transformers/all-MiniLM-L6-v2` to an OVMS-ready OpenVINO embedding model for a RAG pipeline:
- Enable the required Model Download plugins
- Use INT8 precision on CPU
- Submit the conversion job and poll it until completion
- Verify the converted model output path

Also provide an equivalent conversion request for a reranker model such as `cross-encoder/ms-marco-MiniLM-L-6-v2`.
