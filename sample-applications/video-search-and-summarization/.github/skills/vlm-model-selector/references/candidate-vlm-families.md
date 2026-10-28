<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Candidate VLM Families — Seed Shortlist

**Snapshot date:** 2026-10-13, cross-referenced against the canonical
[OpenVINO supported-models page](https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html)
and general Hub popularity at time of writing. Always re-fetch that exact URL
live rather than relying on this snapshot or a remembered/guessed OpenVINO
docs URL — OpenVINO reorganizes its documentation between releases. This is a
**starting seed list only** — re-verify license, size variants, and OpenVINO
export notes live before recommending, since families release new sizes and
license terms can differ by size within the same family.

**Freshness rule — read before using this table:** the "Generations observed
at snapshot time" column below is a **historical record, not a currency
claim**. It lists whichever generations had shipped as of the snapshot date
above, oldest to newest. Model families ship new generations faster than this
document can be kept in sync — by the time you read this, every family below
may already have a newer generation than any name listed here. Never treat the
rightmost/newest-looking name in that column as "the latest" without checking
live; always look up the family's current lineup yourself (its Hub org page or
official release notes, sorted by recency) before recommending anything.
Use the **oldest** generation that already has published benchmark numbers
purely as a cross-generation accuracy/compute-fit proxy when the
live-verified current generation's equivalent size doesn't have numbers
published yet — never as a reason to recommend that older generation itself.

| Family | Generations observed at snapshot time (oldest → newest; verify live for anything newer) | Representative sizes (pattern, applies across generations) | Notable capabilities | License pattern (verify per size/generation) | OpenVINO GenAI support (validated architecture strings as of snapshot) |
|---|---|---|---|---|---|
| **Qwen-VL** (Alibaba) | Qwen2-VL, Qwen2.5-VL, Qwen3-VL | 2B, 3B, 7B, 8B, 32B+ | Strong general VQA, grounding/bounding-box output, document/chart understanding, video (frame sampling) | Mostly Apache-2.0 for small/mid sizes; verify the specific checkpoint's license tag — some large variants or older Qwen-VL releases use a custom Tongyi Qianwen license. | Qwen2-VL, Qwen2.5-VL, Qwen3-VL were explicitly listed as of snapshot date; the 2B–8B range covers NPU/iGPU tiers, and 32B+ sizes exceed the supported discrete Arc envelope — flag as a cloud/data-center fallback case. Check the live supported-models page for any generation shipped after Qwen3-VL. |
| **Phi-vision / multimodal** (Microsoft) | Phi-3-vision, Phi-3.5-vision (~4.2B), Phi-4-multimodal (~5.6B) | ~4.2B (3.5-vision class), ~5.6B (4-multimodal class) | General VQA/captioning, OCR-leaning, compact size fits NPU/iGPU well | MIT | Phi-3-vision/Phi-3.5-vision/Phi-4-multimodal were explicitly listed as of snapshot date, with noted `eos_token_id` override needed for `phi3_v`, and a transformers-version patch needed for `phi4mm` export. Check the live supported-models page for any generation shipped after Phi-4-multimodal. |
| **MiniCPM-V** (OpenBMB) | MiniCPM-V-2_6 (~8B), MiniCPM-V-4.5, MiniCPM-V-4.7-1B / -35B-A3B (MoE) | ~1B, ~8B, MoE variants | Strong OCR/document understanding, multi-image, efficient for its accuracy class | Custom "MiniCPM Model License" — generally permits commercial use but historically required a usage-registration step for large-scale commercial use; always read the linked license, don't assume unrestricted. | MiniCPM-V-2_6, -4.5, -4.7 variants were explicitly listed as of snapshot date, with specific `transformers` version pins per variant; the 1B size fits NPU, and the 35B-A3B MoE variant exceeds the supported discrete Arc envelope — flag as a cloud/data-center fallback case. Check the live supported-models page for any generation shipped after -4.7. |
| **Gemma (vision)** (Google) | Gemma 3 (4B/12B/27B), Gemma 3n (E2B/E4B), Gemma4 (up to 31B) | 4B/12B/27B-class, E2B/E4B effective-param class, up to ~31B-class | General multimodal reasoning, video input, efficient "effective parameter" variants for constrained devices | Gemma Terms of Use — permissive for most use including commercial, but carries Google's Prohibited Use Policy (acceptable-use rider) layered on top of the base grant; not a plain OSI license. | gemma3/gemma3n/gemma4 conditional-generation variants were explicitly listed as of snapshot date; 3n variants fit NPU/iGPU, 27B/31B-class sizes exceed the supported discrete Arc envelope — flag as a cloud/data-center fallback case. Check the live supported-models page for any generation shipped after Gemma4. |
| **InternVL** (OpenGVLab) | InternVL2, InternVL2.5, InternVL3 | 1B, 2B, 4B, 8B, 9B, 14B | Broad VQA/grounding, strong on several leaderboard benchmarks at small sizes | Mix of MIT (code) and model-specific weight licenses depending on the base LLM used in a given size — verify per checkpoint. | Wide size range (1B–14B) was explicitly listed as of snapshot date, good coverage of NPU/iGPU tiers, with the 14B size also comfortable on a discrete Arc GPU. Requires `timm`/`einops` for export. Check the live supported-models page for any generation shipped after InternVL3. |
| **LLaVA-NeXT / nanoLLaVA** | LLaVA-v1.5, LLaVA-NeXT (Mistral/Vicuna backbones, then Llama3 backbone), nanoLLaVA/nanoLLaVA-1.5 | nanoLLaVA ~1B class; LLaVA-NeXT 7B–8B (backbone-dependent) | General VQA/captioning; nanoLLaVA targets edge/mobile explicitly | Depends on backbone LLM license (e.g., Llama Community License for Llama3-backed variants) — check the backbone, not just the vision-tower repo. | LLaVA-v1.5, LLaVA-NeXT (Mistral/Vicuna/Llama3), nanoLLaVA/nanoLLaVA-1.5 were explicitly listed as of snapshot date. Check the live supported-models page for any newer backbone/release. |
| **DeepSeek-OCR** | DeepSeek-OCR-2 | — | Narrow, OCR/document-text-extraction specialist (single image per request) | MIT-style (DeepSeek permissive) — verify current tag | DeepSeek-OCR-2 was explicitly listed as of snapshot date, with the caveat it accepts exactly one image and has no built-in chat template. Check the live supported-models page for any generation shipped after -2. |

## How to use this table

1. Match the "Notable capabilities" column against the task keywords from
   Step 2 of the skill to cut the list to 3–5 plausible families.
2. For each matched family, go to its Hub org page (or release notes) and
   determine the actual current generation *live* — do not assume the
   newest-looking name in the "Generations observed at snapshot time" column
   is still current, since a newer one may have shipped since the snapshot
   date. Shortlist that live-verified current generation's checkpoint at the
   needed size by default. Only shortlist an older generation instead of the
   current one when the user explicitly asked for it, or when the current
   generation fails a hard gate (license/compute-fit) that an older one
   passes — and say so explicitly when that happens.
3. Pick the specific size within the family from
   `intel-core-ultra-compute-envelope.md`'s guidance for the user's target
   device tier — that reference now covers Core Ultra NPU/iGPU tiers and
   discrete Arc GPU tiers.
4. Open the live Hub model card for that exact checkpoint and run Step 4 of
   the skill (license, benchmark numbers, maintenance signal) — do not treat
   the notes above as sufficient on their own. If the live-verified current
   generation's model card has no published benchmark numbers yet for the
   task's relevant metric, cite the same-size checkpoint from the newest
   generation that *does* have published numbers as an explicitly labeled
   cross-generation proxy (naming both checkpoints, e.g., "the current
   generation's 2B checkpoint has no published Video-MME number yet; using
   the prior generation's 2B checkpoint's Video-MME score as a
   same-size-class proxy") rather than silently omitting the metric or
   recommending the older generation outright.
