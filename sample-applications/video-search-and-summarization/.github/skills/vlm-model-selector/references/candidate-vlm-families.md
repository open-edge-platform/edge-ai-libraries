<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Candidate VLM Families — Seed Shortlist

**Snapshot date:** 2026-10-13, cross-referenced against the OpenVINO GenAI
supported-models page and general Hub popularity at time of writing. This is a
**starting seed list only** — re-verify license, size variants, and OpenVINO
export notes live before recommending, since families release new sizes and
license terms can differ by size within the same family.

| Family | Representative sizes | Notable capabilities | License pattern (verify per size) | OpenVINO GenAI support |
|---|---|---|---|---|
| **Qwen2-VL / Qwen2.5-VL / Qwen3-VL** (Alibaba) | 2B, 3B, 7B, 8B, 32B+ | Strong general VQA, grounding/bounding-box output, document/chart understanding, video (frame sampling) | Mostly Apache-2.0 for small/mid sizes; verify the specific checkpoint's license tag — some large variants or older Qwen-VL releases use a custom Tongyi Qianwen license. | Yes — Qwen2-VL, Qwen2.5-VL, Qwen3-VL explicitly listed; the 2B–8B range covers NPU/iGPU tiers, and 32B+ sizes exceed the supported discrete Arc envelope — flag as a cloud/data-center fallback case. |
| **Phi-3-vision / Phi-3.5-vision / Phi-4-multimodal** (Microsoft) | ~4.2B (3.5-vision), ~5.6B (Phi-4-multimodal) | General VQA/captioning, OCR-leaning, compact size fits NPU/iGPU well | MIT | Yes — listed, with noted `eos_token_id` override needed for `phi3_v`, and a transformers-version patch needed for `phi4mm` export. |
| **MiniCPM-V** (OpenBMB) | MiniCPM-V-2_6 (~8B), MiniCPM-V-4.5, MiniCPM-V-4.7-1B / -35B-A3B (MoE) | Strong OCR/document understanding, multi-image, efficient for its accuracy class | Custom "MiniCPM Model License" — generally permits commercial use but historically required a usage-registration step for large-scale commercial use; always read the linked license, don't assume unrestricted. | Yes — MiniCPM-V-2_6, -4.5, -4.7 variants listed, with specific `transformers` version pins per variant; the 1B size fits NPU, and the 35B-A3B MoE variant exceeds the supported discrete Arc envelope — flag as a cloud/data-center fallback case. |
| **Gemma 3 / 3n / 4 (vision)** (Google) | 4B, 12B, 27B (Gemma3); E2B/E4B (3n, effective params smaller); up to 31B (Gemma4) | General multimodal reasoning, video input (Gemma4), efficient "effective parameter" variants (3n) for constrained devices | Gemma Terms of Use — permissive for most use including commercial, but carries Google's Prohibited Use Policy (acceptable-use rider) layered on top of the base grant; not a plain OSI license. | Yes — gemma3/gemma3n/gemma4 conditional-generation variants listed; 3n variants fit NPU/iGPU, 27B/31B sizes exceed the supported discrete Arc envelope — flag as a cloud/data-center fallback case. |
| **InternVL2 / 2.5 / 3** (OpenGVLab) | 1B, 2B, 4B, 8B, 9B, 14B | Broad VQA/grounding, strong on several leaderboard benchmarks at small sizes | Mix of MIT (code) and model-specific weight licenses depending on the base LLM used in a given size — verify per checkpoint. | Yes — wide size range explicitly listed (1B–14B), good coverage of NPU/iGPU tiers, with the 14B size also comfortable on a discrete Arc GPU. Requires `timm`/`einops` for export. |
| **LLaVA-NeXT / nanoLLaVA** | nanoLLaVA ~1B class; LLaVA-NeXT 7B–8B (Mistral/Vicuna/Llama3 backbones) | General VQA/captioning; nanoLLaVA targets edge/mobile explicitly | Depends on backbone LLM license (e.g., Llama Community License for Llama3-backed variants) — check the backbone, not just the vision-tower repo. | Yes — LLaVA-v1.5, LLaVA-NeXT (Mistral/Vicuna/Llama3), nanoLLaVA/nanoLLaVA-1.5 listed. |
| **DeepSeek-OCR-2** | — | Narrow, OCR/document-text-extraction specialist (single image per request) | MIT-style (DeepSeek permissive) — verify current tag | Yes — listed, with the caveat it accepts exactly one image and has no built-in chat template. |

## How to use this table

1. Match the "Notable capabilities" column against the task keywords from
   Step 2 of the skill to cut the list to 3–5 plausible families.
2. Pick the specific size within the family from
   `intel-core-ultra-compute-envelope.md`'s guidance for the user's target
   device tier — that reference now covers Core Ultra NPU/iGPU tiers and
   discrete Arc GPU tiers.
3. Open the live Hub model card for that exact checkpoint and run Step 4 of
   the skill (license, benchmark numbers, maintenance signal) — do not treat
   the notes above as sufficient on their own.
