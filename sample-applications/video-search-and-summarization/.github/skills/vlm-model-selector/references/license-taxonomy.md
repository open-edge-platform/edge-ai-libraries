<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VLM License Taxonomy — Public/Commercial Usability

License wording on VLM repos varies widely and the short Hub `license` tag does
not always tell the whole story. Classify each candidate into one of three
buckets before recommending it, and always read the linked license text (not
just the tag) when the tag is `other` or when the family is known to carry an
acceptable-use rider.

## Bucket 1 — Usable without special conditions

Plain OSI-approved permissive licenses with no additional acceptable-use
policy layered on top:

- **Apache-2.0** (common for Qwen small/mid-size checkpoints, many research
  releases)
- **MIT** (Phi family, many DeepSeek releases)
- **BSD-style** variants

These are safe to recommend for public and commercial deployment without
further review, assuming the rest of the repo (datasets used, any bundled
third-party code) doesn't introduce separate restrictions.

## Bucket 2 — Usable, but with conditions to surface to the user

Permissive for most practical purposes, including commercial use, but the
license text includes an acceptable-use policy, attribution requirement, or a
scale-based condition. Flag these explicitly rather than silently treating them
as equivalent to Bucket 1:

- **Gemma Terms of Use** (Google) — broad commercial grant, but incorporates a
  Prohibited Use Policy; redistribution of modified models carries naming/
  notice requirements.
- **Llama Community License** (Meta) — commercial use allowed, but includes a
  monthly-active-users threshold clause and a naming/attribution requirement
  for derivatives; relevant for any LLaVA-NeXT or other model with a Llama
  backbone.
- **Qwen-specific size licenses** — most small/mid Qwen-VL sizes across its
  generations are Apache-2.0, but verify each size and generation
  individually, including whatever the current generation turns out to be —
  some larger or older checkpoints in the Qwen lineage have used a custom
  Tongyi Qianwen license with its own use restrictions.
- **MiniCPM Model License** (OpenBMB) — generally commercial-friendly but has
  historically required registration/notification for certain commercial
  usage scales; confirm current terms on the specific checkpoint.
- **OpenRAIL-family licenses** — generally permissive with embedded
  "restricted use cases" lists (e.g., no use for unlawful surveillance); the
  restrictions are usually narrow and compatible with typical industrial/
  enterprise vision analytics tasks, but must still be read and disclosed.

For Bucket 2, the skill should still recommend the model if it's otherwise the
best fit, but must state the condition in the final recommendation so the user
(or their legal/compliance process) can confirm acceptability.

## Bucket 3 — Not usable for a public/commercial deployment without explicit confirmation

- **"Research only" / "non-commercial" / CC-BY-NC** style licenses.
- **Gated repos requiring per-user manual approval** where the approval
  criteria are restrictive (e.g., limited to academic institutions).
- Any license whose acceptable-use terms directly conflict with the user's
  stated deployment (e.g., a no-surveillance clause on a model being
  considered for a surveillance-adjacent use case).

Do not recommend a Bucket 3 model as the primary choice for a public/
commercial task. It may still be mentioned as an accuracy reference point
(e.g., "the research-only model scores highest on this benchmark, but is not
licensed for your deployment — here is the best Bucket 1/2 alternative").

## Verification steps (always, not a one-time check)

1. Read the model card's `license` YAML field.
2. If `license: other`, follow `license_name`/`license_link` to the actual
   text.
3. Search the license text for "commercial", "research", "non-commercial",
   "prohibited use", "acceptable use policy", and any numeric threshold
   (users/revenue/requests) — these are the clauses most likely to change a
   model's bucket.
4. Re-check per model **size** within a family, not just per family — license
   terms sometimes differ between the small and large checkpoints of the same
   model line.
