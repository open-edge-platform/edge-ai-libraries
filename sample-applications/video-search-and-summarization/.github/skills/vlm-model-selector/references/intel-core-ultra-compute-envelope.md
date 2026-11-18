<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Intel Core Ultra and Discrete GPU Compute Envelope for VLM Placement

**Snapshot date:** 2026-10-23. Re-verify current generation specs and OpenVINO
device support before relying on this for a production decision — Intel ships
new Core Ultra and Arc GPU generations roughly annually, and NPU/GPU driver
and OpenVINO support matures after hardware launch. For architecture/model
compute-fit specifically, the canonical source is the
[OpenVINO supported-models page](https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html)
— always fetch that exact URL live rather than a remembered or guessed
OpenVINO docs URL.

## Core Ultra generations at a glance (integrated NPU/iGPU)

| Generation | Codename | NPU | iGPU | Typical RAM (shared with GPU/NPU) |
|---|---|---|---|---|
| Core Ultra Series 1 | Meteor Lake | NPU 3 (~10–11 TOPS) | Arc (Xe-LPG), up to 8 Xe-cores | 16–32 GB |
| Core Ultra Series 2 | Lunar Lake (mobile) | NPU 4 (~40–48 TOPS) | Arc (Xe2), up to 8 Xe2-cores | 16–32 GB on-package LPDDR5X (fixed, not user-upgradable) |
| Core Ultra Series 2 | Arrow Lake (desktop/HX) | NPU 3 (~13 TOPS) — same NPU generation and a similar TOPS class as Meteor Lake, well below Lunar Lake's NPU 4 | Arc (Xe-LPG), not Xe2 — fewer Xe-cores than Lunar Lake (desktop: up to 4 Xe-cores; HX mobile: up to 8 Xe-cores) | Desktop: user-upgradable DDR5 system RAM, typically 32–128 GB+, shared with the iGPU; HX mobile: 16–32 GB shared RAM |
| Core Ultra Series 3 | Panther Lake | NPU 5 (~50 TOPS class) | Arc (Xe3) | 16–32 GB+ |

Arrow Lake's NPU 3 is markedly less capable than Lunar Lake's NPU 4 despite
both shipping under the "Core Ultra Series 2" label — do not assume an
Arrow Lake (desktop/HX) system has Lunar Lake's NPU/iGPU headroom. For
NPU-tier VLM placement specifically, treat an Arrow Lake system the same as
Meteor Lake (NPU 3 class) rather than as a Lunar Lake-class NPU, and confirm
which specific SKU/codename the user has before sizing a model to the NPU.

TOPS figures are vendor-reported INT8 NPU peak throughput and are not directly
comparable to a VLM's end-to-end tokens/sec — actual throughput depends on KV
cache size, image-token count (resolution/tiling), and OpenVINO runtime
version. Treat TOPS as a relative generation-over-generation indicator, not an
absolute latency predictor.

## Intel discrete GPUs — Xe architecture series

Discrete Arc GPU products give a VLM its own dedicated VRAM pool instead of
sharing system RAM with the CPU/NPU, which relaxes the size ceiling that
applies to integrated Core Ultra placement. Confirm current VRAM and
driver/OpenVINO support per SKU before committing — card configurations vary
by OEM.

| Product line | Codename / Xe generation | Segment | Representative SKUs | VRAM |
|---|---|---|---|---|
| Arc A-Series | Alchemist (Xe-HPG, 1st gen) | Consumer desktop/laptop | A380, A580, A750, A770 | 6–16 GB GDDR6 |
| Arc B-Series | Battlemage (Xe2-HPG) | Consumer desktop | B570, B580 | 10–12 GB GDDR6 |
| Arc Pro A-Series | Alchemist (Xe-HPG) | Workstation | Arc Pro A40, A50, A60 | 4–16 GB GDDR6 |
| Arc Pro B-Series | Battlemage (Xe2-HPG) | Workstation | Arc Pro B50, B60, B65, B70 | 16–32 GB GDDR6 |
| Crescent Island (upcoming, not yet launched) | Celestial (Xe3P) | Data center / AI inference | SKUs not yet named; previewed with up to 480 GB LPDDR5X | Up to 480 GB LPDDR5X (preview spec, confirm at launch) |

Notes:
- All of these expose as an OpenVINO `"GPU"` device (`"GPU.0"`, `"GPU.1"`, …
  when more than one GPU is present, including an iGPU + discrete GPU mix) —
  the same exported INT4/INT8 IR used for Core Ultra iGPU placement runs here
  without re-conversion; only the device string and available VRAM change.
- Treat Arc/Arc Pro as the "iGPU-class, but with materially more headroom"
  tier — dedicated VRAM comfortably covers mid-size models the Core Ultra
  guidance below flags as tight on integrated silicon.
- Crescent Island is Intel's next-generation (Celestial / Xe3P) data-center
  GPU aimed at AI inference, previewed at Computex 2026 with a claimed
  "second-half 2026" launch and up to 480 GB of LPDDR5X per card — it is not
  yet shipping as of this snapshot. Treat it as forward-looking only: do not
  recommend it for a current deployment until SKUs, driver support, and
  OpenVINO GenAI device support are confirmed at launch.

## Model-size guidance by target device

These are starting buckets for the Step 2 compute-fit gate, validated against
OpenVINO GenAI's supported-models list and typical INT4 weight-compression
ratios (~4x vs. fp16). Always confirm with an actual export + timed inference
on target hardware before committing. The example checkpoints below are drawn
from `candidate-vlm-families.md`'s "Generations observed at snapshot time"
column — that column is a historical record, not a currency claim, so verify
live which generation of each family is actually current before recommending
it; treat any generation shown here that isn't the one you verified as live
as a same-size-class benchmark/compute-fit proxy only, not the recommendation.

| Target | Dense parameter count | Precision | Notes |
|---|---|---|---|
| NPU-only, lowest power, single image, short responses | ≤2–4B | INT4 (NNCF weight compression) | Best fit for always-on/background inference (e.g., a ~2B-class checkpoint from the Qwen-VL, InternVL, or MiniCPM-V families — confirm which generation of each is current before naming one). If the live-verified current generation's checkpoint has no published NPU/INT4 benchmark yet, the equivalent size from the newest generation that *does* have one can be cited as a same-size-class proxy — name both checkpoints and label it as such. Confirm the architecture is in OpenVINO GenAI's VLM supported list before committing to NPU. |
| Core Ultra iGPU, interactive chat/QA over images or short video | ≤7–8B | INT4, INT8 fallback if accuracy-sensitive | Comfortable range for a ~7–8B-class checkpoint from the Qwen-VL, MiniCPM-V, LLaVA-NeXT, InternVL, or Phi-vision/multimodal families (confirm current generation live for each before naming one). Where the live-verified current generation lacks published numbers, the newest generation that does have numbers can serve as a labeled same-size proxy. |
| Core Ultra iGPU, higher accuracy, batch/offline acceptable | 8–14B | INT4 | e.g., a ~14B-class InternVL checkpoint or an ~8B-class Qwen-VL checkpoint from whichever generation is live-verified as current. Expect noticeably higher latency; validate it meets the user's throughput target before recommending for interactive use. |
| Discrete Arc (A-/B-Series) or Arc Pro, interactive or batch | up to ~14–24B | INT4, INT8 if accuracy-sensitive | Dedicated 6–32 GB VRAM removes the shared-RAM pressure of iGPU placement; a good fit when a user has an Arc/Arc Pro card but the model is a size tier above comfortable Core Ultra iGPU placement. The ~20–24B end of the range needs the 24–32 GB Arc Pro B60/B65/B70 cards specifically, not the 6–16 GB consumer Arc A-/B-Series. |
| Avoid for real-time Core Ultra (NPU/iGPU) or discrete Arc deployment | >24B dense (or large MoE) | any | Memory and latency typically unacceptable for Core Ultra NPU/iGPU or a single discrete Arc card outside of batch/offline analysis; recommend a cloud/data-center fallback instead if accuracy at this scale is required. |

## Practical export reference

```bash
pip install optimum[openvino] nncf
optimum-cli export openvino \
  --model <hf-model-id> \
  --weight-format int4 \
  <output-dir>
```

Do not add `--trust-remote-code` to this command by default — it executes
arbitrary Python from the Hub repository with the user's own permissions and
credentials, and passing license/architecture checks does not establish that
code is safe to run. Only add it for a specific, pinned revision
(`<hf-model-id>@<commit-sha>`) after the user has explicitly approved running
that revision's custom code — see SKILL.md's "Handling a model that requires
custom code" procedure.

Run inference device-agnostically via OpenVINO GenAI's `VLMPipeline`, selecting
`"CPU"`, `"GPU"` (`"GPU.0"`/`"GPU.1"` to target a specific integrated or
discrete device when more than one is present), or `"NPU"` as the device
string — this lets the same exported IR be benchmarked across Core Ultra and
discrete Arc devices without re-converting.
