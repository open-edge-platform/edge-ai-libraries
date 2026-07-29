<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Download `meta-llama/Llama-3.2-1B` and convert it into an OVMS-ready OpenVINO model:
- Use INT4 precision on CPU
- Enable the required Model Download plugins
- Configure Hugging Face authentication for the gated model
- Set an appropriate cache size
- Submit the conversion job and monitor it until completion
- Verify the converted model path can be mounted into OVMS

Also describe the required precision when the target device is an NPU.
