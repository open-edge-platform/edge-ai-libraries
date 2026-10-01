<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Download `meta-llama/Llama-3.2-1B` and convert it into an OVMS-ready OpenVINO model:
- Use INT4 precision on CPU
- Enable the required Model Download plugins
- Configure Hugging Face authentication for the gated model: either a plain-text
  `HUGGINGFACEHUB_API_TOKEN`/`HF_TOKEN` at service/CLI startup, or a per-request
  top-level `override_credentials.HF_TOKEN` (base64-encoded, sibling of
  `name`/`hub`/`config`) plus `validate_credentials: true` to fail fast on a bad
  token before conversion runs
- Set an appropriate cache size
- Submit the conversion job and monitor it until completion
- Verify the converted model path can be mounted into OVMS

Also describe the required precision when the target device is an NPU.

Also describe how the output directory name is derived when the target device is a HETERO combination (e.g. `HETERO:GPU,CPU`), since `:` and `,` are not filesystem-safe and get slugified (e.g. `hetero_gpu_cpu`).
