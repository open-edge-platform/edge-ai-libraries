<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

My nodes have Intel GPUs and NPUs available via device plugins. For my VSS summary-mode Helm deployment I want captioning to run on the GPU with `OpenVINO/Phi-3.5-vision-instruct-int8-ov` and the final summarization LLM to run on the NPU with `OpenVINO/Qwen3-8B-int4-cw-ov`. What `global.devices` values do I need, and how do I discover the right device plugin resource keys on my nodes first?
