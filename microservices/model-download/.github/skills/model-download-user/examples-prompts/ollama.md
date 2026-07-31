<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Pull `llama3.2:3b` through the Model Download REST API:
- Enable the Ollama plugin when starting the service
- Use `llama3.2` as the model name and `3b` as the revision
- Submit the download job and poll it until completion
- Verify the resulting model location

Explain the default tag behavior when no revision is provided and note how the service handles multiple Ollama downloads.
