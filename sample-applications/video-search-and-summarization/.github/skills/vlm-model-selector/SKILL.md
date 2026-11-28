---
name: vlm-model-selector
description: "Select a Vision-Language Model (VLM) for a vision analytics task (captioning, VQA, OCR/document understanding, chart/table reading, grounding, counting, multi-image or video reasoning), constrained to Intel Core Ultra (NPU/iGPU) and discrete Arc GPUs. Use when a user asks to pick/recommend a VLM, needs a model that is accurate, compute-fit, and usably licensed for Core Ultra/Arc, or asks for a vision analytics pipeline where a VLM is one component (e.g. alongside detection/tracking, audio, or identity-matching). First decomposes the task into its component capabilities, elicits requirements, then evaluates a user-provided shortlist or runs an open Hugging Face Hub search. Produces a set of options with pros/cons rationale, not a forced ranking, and names non-VLM pipeline components explicitly when the task only partially needs a VLM. DO NOT USE FOR: training/fine-tuning a model, text-only LLM selection, or a classical CV model (YOLO/CLIP) with no language output needed."
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "vlm vision-language-model model-selection intel-core-ultra npu igpu arc xe-gpu data-center-gpu openvino huggingface"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VLM Model Selector for Intel Core Ultra and Discrete GPUs

Pick a Vision-Language Model for a user's vision analytics task: decompose the
task, elicit requirements, search the Hugging Face Hub, check compute fit
against the OpenVINO supported-models page, verify the actual license text,
and return a set of options with pros/cons — not a single unexplained answer.
Covers Core Ultra's integrated NPU/iGPU and Intel discrete GPUs in the Xe
architecture series (Arc, Arc Pro). See `references/` for supporting data;
these are dated snapshots that seed the search, never a substitute for the
live checks below.

Requires network access to huggingface.co and the canonical OpenVINO
supported-models page
(https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html)
— always fetch this exact URL rather than a remembered one, since OpenVINO
reorganizes its docs between releases.

**Currency rule (applies throughout this procedure):** never trust a
remembered model generation, license, or OpenVINO-support claim — not from
training data, and not from any name used as an example anywhere in this
skill's own text or reference files (those are dated snapshots, not a
currency claim). Model families ship new generations every few months;
always confirm the current lineup live (the family's Hub org page, sorted by
recency) before shortlisting or finalizing anything.

## When to Use

- User wants to add a vision/image/video understanding capability and needs a
  concrete VLM recommendation.
- User mentions Intel Core Ultra, NPU, iGPU, Arc, Xe architecture, OpenVINO,
  or "edge" deployment alongside a vision/VLM task.
- User names a candidate model and asks if it'll run on their hardware —
  treat it as a one-item shortlist (Step 3) instead of searching.
- The task may only partially need a VLM (e.g., also needs
  detection/tracking, audio, or identity-matching) — still use this skill for
  the VLM-needing portion(s) per Step 1's decomposition, and name the
  non-VLM components explicitly rather than answering a narrower question
  than what was asked.
- Do not use this skill if the task has no language-output requirement at all
  (pure classification/detection/segmentation) — recommend a lighter CV-only
  pipeline instead (see Edge Cases).

## Procedure

### Step 1 — Decompose the task, then elicit requirements

Before searching, confirm these details with the user in one compact
multi-question pass (e.g. via `vscode_askQuestions`); ask only what's
missing.

**Decompose first, before asking about devices or search scope.** Classify
each capability the task actually needs:
- **Visual description/captioning/VQA/grounding** — this skill's core
  territory; a VLM handles it.
- **Counting, detection, tracking, or timing/proximity logic** (e.g., "is
  this person unattended for N seconds," "how many vehicles") — not a VLM
  task; flag a specialist CV/detection model plus a rule engine instead.
- **Audio/speech content** (words, tone, conversation quality) — outside a
  vision-only VLM; widens Step 4's search to omni/audio-capable models, or
  pairs a vision-only VLM with a separate ASR/audio component.
- **Identity/biometric matching** — never assume the VLM does this; flag
  face recognition vs. a non-biometric alternative (badge/zone/schedule
  correlation) as a separate, consent-sensitive choice to surface to the
  user.
- **A capability no public VLM reliably has** (open-ended anomaly/novelty
  judgment, pixel segmentation, subjective soft-skill scoring like
  "friendliness") — flag explicitly per Edge Cases; never imply a VLM solves
  it reliably.

State this decomposition back to the user before moving on. If the task is
only visual description/VQA, proceed as a single-VLM selection. If it also
needs detection/tracking, audio, or identity-matching, say explicitly that
the deliverable is a **pipeline recommendation** that names the non-VLM
components too, rather than silently answering a narrower question than what
was actually asked.

Required:
- **Task description**: what should the model do with the image/video (e.g.,
  "describe safety-vest compliance in a factory frame", "answer questions about
  a scanned invoice", "summarize a 30-second clip").
- **Input modality**: single image, multiple images per request, or video
  (and if video: live stream with sampled frames, or short clips).
- **Output shape**: free-form text, structured/JSON (for programmatic
  downstream use), bounding boxes/grounding, or a closed label set.
- **Target device tier**: Core Ultra NPU-only (lowest power, smallest
  budget), Core Ultra iGPU (larger budget), a discrete Arc GPU (A-/B-Series
  or Arc Pro — dedicated VRAM, largest budget), or "either, pick the better
  fit." If unknown, default to a hybrid NPU+iGPU Core Ultra Series 2/3 system
  with 16–32 GB RAM and say so explicitly in the final recommendation.
- **Compute placement relative to the sensor**: is the Intel device
  physically attached to the camera (embedded edge inference under power/
  weight/thermal/connectivity limits — e.g. handheld, vehicle-, robot-, or
  drone-mounted), or a separate nearby gateway/workstation (still edge, never
  cloud, but a larger power/thermal budget)? This decides which end of the
  device-tier budget above is realistic, and whether sensor connectivity is
  itself a constraint.
- **Data sensitivity / subject matter**: does the footage include
  identifiable people, vehicles, plates, or other personal data, and/or does
  it monitor people or a public/private space? Treat this as
  surveillance-adjacent for the license-bucket gate
  (`references/license-taxonomy.md`) regardless of how the user answers the
  deployment-constraints question below — infer it from the task itself and
  confirm with the user, since they may not think to flag their own task as
  "surveillance."
- **Consequential-decision check**: does the output feed a decision with
  real-world stakes for an identifiable individual (employment, access,
  legal, financial, law-enforcement-adjacent)? If so, this is a required
  deliverable: name the applicable risk categories (biometric processing if
  identity-matching is in scope, audio-recording consent if audio is in
  scope, automated-decision/human-oversight expectations such as the EU AI
  Act or local equivalents), and carry a human-in-the-loop recommendation
  through to Step 6.
- **Alert/detection semantics** (only if flagging anomalies/unexpected
  events): closed-set enumerable conditions (e.g. "wrong-way driving") or
  fully open-ended ("anything unusual")? Open-ended alerting is a
  known-unreliable VLM capability (see Edge Cases) — flag this rather than
  implying model choice alone solves it. If closed-set, get the user's actual
  enumerated list before finalizing the search.

Helpful if available (ask if not given, but don't block on them):
- Accuracy bar (a specific benchmark/number, or "best effort within constraints").
- Latency/throughput target.
- Offline/commercial/data-residency constraints (affects the license vector).
- Language(s) required beyond English.
- Known size ceiling, or whether quantization (INT4/INT8) is acceptable.

### Step 2 — Ask: user-provided shortlist, or open search?

Before searching anything, ask the user explicitly (one question, two
options):

- **"I have a shortlist"** — the user already has specific candidate model(s)
  in mind and wants them evaluated against the 4 vectors.
- **"Search broadly"** — the user wants the hub searched for candidates, not
  limited to any particular model family.

If the user is unsure, default to **open search** and say so (it's this
skill's core job), but mention the user-provided path is faster/cheaper if
they already have names in mind. Record the choice and proceed to the
matching branch:

- Choice = shortlist → go to **Step 3 (Branch A)**.
- Choice = open search → go to **Step 4 (Branch B)**.

### Step 3 — Branch A: evaluate a user-provided shortlist

1. Get the user's exact candidate list. Resolve informal names (e.g., "the
   latest vision model from <vendor>") to a precise Hub repo ID
   (`org/model-name`) via the family's Hub org page sorted by recency — per
   the Currency rule, never from a remembered or example name — and tell the
   user which exact checkpoint you resolved it to. If the user named an older
   generation explicitly, honor it but mention a newer one if found. If a
   named model can't be found, say so rather than silently dropping it.
2. **Skip discovery** — do not browse the Hub or the leaderboard for *new*
   candidates; the scope is exactly the models the user named (plus, if
   useful, immediate sibling sizes of the same family if the user seems open
   to that — confirm before adding any model they didn't name).
3. Apply the same compute-fit tiers and license bucketing as Branch B (Step
   4.2), scoped to just this list, then do the full model-card review in
   Step 5 for each one.
4. If the Open VLM Leaderboard happens to have an entry for a named model,
   use it (third-party accuracy signal); otherwise use the model's own
   self-reported numbers, clearly labeled as self-reported.
5. If none of the user's candidates pass the license/compute-fit gates, say so
   explicitly — do not silently recommend the least-bad disqualified option —
   and offer to switch to Branch B (open search) for an alternative.
6. Continue to **Step 6** (score/rank), scoped to just this list.

### Step 4 — Branch B: open search of the hub

1. **Broad programmatic discovery (the actual top-of-funnel):** query the Hub
   filtered on `pipeline_tag=image-text-to-text` (also `any-to-any`, or
   whichever omni/audio-capable tag applies, if Step 1 found an audio
   component), sorted by trending/downloads/recency, and cross-check the
   [Open VLM Leaderboard](https://huggingface.co/spaces/opencompass/open_vlm_leaderboard).
   Use `references/candidate-vlm-families.md` only as an accelerant — a new
   or niche model surfaced by the live query is equally eligible. The Hub's
   own search matches mostly on model id/tags, not full READMEs, so "open"
   means a bounded top-of-funnel (top 50–100 under the right tag, plus
   leaderboard entries), not an exhaustive scan. For every family that
   surfaces, check its current generation live per the Currency rule — never
   let a most-memorized checkpoint stand in for the current lineup.
   Also explicitly search for domain-specialist VLMs if Step 1 matched a known
   vertical (driving/traffic, medical, document/OCR, retail/industrial,
   agriculture) — a specialist can beat a generalist on the task's actual
   judgment criteria even as a fine-tune of a familiar base, and skipping
   this search misses it.
2. **Cheap metadata triage (do this before any deep review):** for every
   discovered candidate:
   - **License bucket** (`references/license-taxonomy.md`) — bucket a clearly
     tagged permissive license (Apache-2.0, MIT, BSD) directly from the tag.
     For `other`/missing tags, follow `license_link`/`license_name` to the
     actual text (a quick resolution, not the full Step 5 review) before
     excluding — never exclude on an ambiguous tag alone, only on text that
     can't be verified or that conflicts with the deployment.
   - **Compute-fit tier** — **Validated** (architecture explicitly on the
     OpenVINO supported-models page — fetch the exact URL from the intro,
     don't rely on a remembered list), **Plausible** (architecture class
     resembles a listed one, e.g. a fine-tune of an already-supported base),
     or **Unknown** (novel architecture).
   Cut the list to roughly 8–10 candidates that pass the license gate
   (verified usable or usable-with-conditions for this deployment, per the
   actual text) and are Validated or Plausible tier. Keep an Unknown-tier
   candidate only if nothing else qualifies, and flag it explicitly as a
   stretch option.
3. **Feasibility probe for Plausible/Unknown survivors:** for any
   Plausible/Unknown-tier candidate that still scores well after review,
   recommend actually attempting
   `optimum-cli export openvino --model <id> --weight-format int4 <dir>`
   (or checking the model's Hub discussions for an existing community export)
   before finalizing it — don't resolve compute fit from metadata inference
   alone for these tiers. Do **not** add `--trust-remote-code` to this probe
   by default; if the export fails because the architecture needs custom
   code, see `references/model-handling-procedures.md` before retrying with
   it.
4. **Accuracy signal with graceful fallback:** prefer leaderboard numbers
   (third-party verified) — for video tasks this includes a video-specific
   benchmark leaderboard, not just the general-purpose Open VLM Leaderboard
   (see Step 5). Fall back to self-reported model-card numbers (labeled as
   such) or, failing that, adoption (downloads/likes/recency) as a weak
   proxy — never present these as equivalent to a verified score.
   **Cross-generation proxy rule:** always recommend the newest
   live-verified generation at the needed size; if it has no published
   numbers yet, cite the equivalent size from the newest generation that
   *does* (naming both checkpoints explicitly, labeled as a cross-generation
   proxy) rather than presenting an older generation's number as if measured
   on the newer checkpoint.
5. **Verification rigor for unfamiliar models:** every factual claim about a
   long-tail candidate (size, license, capability, OpenVINO compatibility)
   must come from a freshly fetched source, not training-data recall —
   mandatory per field, not a spot-check. This is the Currency rule applied
   to a model's other attributes, not just its generation number.
6. Continue to **Step 5** (model-card review) on the triaged ~8–10, then
   **Step 6** (score/rank).

### Step 5 — Review each candidate's model card

For each shortlisted candidate (Branch A's list, or Branch B's triaged ~8–10),
open its Hub model card and extract:

- **Task relevance**: intended-use section, capability tags (grounding, OCR,
  chart/doc, video) — does it explicitly claim the capability needed? For a
  specialist/vertical model (Step 4.1), go further than the label: verify its
  training/benchmark scenario (camera viewpoint, sensor type, environment)
  matches the user's real deployment — a model can match the task category on
  paper (e.g. "driving") while its real data distribution (e.g. ego-vehicle
  dashcam) differs materially from the user's (e.g. an aerial drone), which
  the capability label alone won't surface.
- **Accuracy**: benchmark numbers relevant to the task. Prefer third-party
  leaderboard numbers over self-reported model-card numbers, since the
  latter can be cherry-picked. Match the benchmark to the task (OCRBench/
  DocVQA for documents, ChartQA for charts, MMMU/MMBench for general
  reasoning, MVBench/Video-MME for video). **For video-modality tasks**, the
  general-purpose Open VLM Leaderboard is often thin on video coverage —
  before falling back to self-reported or adoption-proxy signals, check a
  video-specific benchmark leaderboard (e.g. Video-MME, MVBench, TempCompass,
  LongVideoBench — illustrative, not exhaustive; see
  `references/candidate-vlm-families.md` for the fetch strategy) for each
  candidate first.
- **Compute fit**: parameter count, available precisions (fp16/bf16, and
  critically int8/int4 or an existing OpenVINO IR / GGUF release), max image
  resolution or tiling behavior, video frame-count support. Cross-check
  against `references/intel-core-ultra-compute-envelope.md`, which covers both
  Core Ultra NPU/iGPU tiers and discrete Arc GPU tiers.
- **License**: the actual license terms, not just the short tag — follow
  `license_link`/`license_name` if the tag is `other`, and check for
  acceptable-use-policy riders even on named licenses (e.g., Gemma, MiniCPM,
  Qwen large variants — alphabetical, not a priority order). Use
  `references/license-taxonomy.md` to classify as usable /
  usable-with-conditions / not usable. If the repo is gated, see
  `references/model-handling-procedures.md` before reading the full card.
- **Maintenance signal**: last update date and download/like counts, as a weak
  proxy for community support and longevity.

### Two conditional sub-procedures — read before you need them

`references/model-handling-procedures.md` has the full, mandatory steps for
two situations that arise during Step 5 and Step 6:
- **A candidate is gated** (access-request wall): never accept the gate or
  request a token *value* on the user's behalf — only confirm a token's
  *presence*.
- **A candidate needs `--trust-remote-code`**: never enable it by default —
  it executes arbitrary repo code locally. Only add it, pinned to a commit
  SHA, after the user explicitly approves that specific revision.

Follow the reference file's full procedure when either situation applies;
these summaries are not a substitute for it.

### Step 6 — Build a decision-support comparison, not a forced ranking

Build a comparison across the 4 vectors (task relevance, accuracy, compute
fit, license) for the shortlist. Show each candidate's compute-fit tier
(Validated/Plausible/Unknown) and accuracy source confidence
(leaderboard-verified / self-reported / adoption-proxy) so the user isn't
comparing numbers of different trustworthiness as if equivalent.

Do not collapse this into a single ranked list or a lone forced "winner."
For every candidate that passes the license and compute-fit gates, write
explicit **pros and cons framed against this user's task and constraints** —
not generic strengths. A set of 2–4 viable options with genuine trade-offs is
normal and often preferable to one pick, since the user is better positioned
to weigh e.g. "slower but simpler license" against "faster but needs a
license sign-off." State which option matches a specific stated priority as
a conditional ("if license simplicity matters most, X"), never as an
unqualified "best." If one candidate truly dominates every vector, say so —
as an observed outcome, not the default shape of the output.

If Step 1 flagged a consequential-decision context, add auditability as an
explicit vector: a decomposed pipeline with inspectable intermediate outputs
is usually easier to justify in review/dispute than a single opaque
end-to-end model, even when the latter scores higher elsewhere — name this
trade-off explicitly.

Include deployment notes for every viable option:
- Target device placement and why, informed by Step 1's compute-placement
  answer.
- Expected quantization path, e.g.:
  ```bash
  optimum-cli export openvino --model <hf-model-id> --weight-format int4 <output-dir>
  ```
  Omit `--trust-remote-code` by default; if an architecture requires it, say
  so and follow `references/model-handling-procedures.md`.
- Any export caveats on the OpenVINO supported-models page (e.g.
  `transformers` version pins, extra packages).

### Step 7 — Present results

Show the comparison and the pros/cons for each viable option in the response
— this is the primary deliverable, not a single-line verdict. State which
approach was used (user-provided shortlist vs. open search) so the user knows
the scope of what was and wasn't searched. Only write the analysis to a file
if the user asks for it (e.g., "save this analysis"); don't create files
unprompted.

### Pre-flight checklist — run this before presenting results

A capable model can reason its way to a good pipeline shape on its own, but
it cannot guarantee a named checkpoint's generation, license, or OpenVINO
support from parametric knowledge alone — that always needs the live checks
above. This checklist exists so that guarantee holds even on a smaller model
that may not retain every instruction from a long procedure. Verify each item
before presenting the answer; if any is unmet, fix it rather than presenting
incomplete work:

- [ ] Decomposition stated back to the user (pipeline vs. single-VLM).
- [ ] Every Required Step 1 item covered (compute placement, data
      sensitivity, consequential-decision check, alert semantics).
- [ ] Every candidate has a stated compute-fit tier and how it was
      determined.
- [ ] Every candidate's license is resolved from actual text, not just the
      Hub tag, and bucketed per `references/license-taxonomy.md`.
- [ ] If video modality: checked a video-specific benchmark leaderboard
      before falling back to self-reported/adoption-proxy signals.
- [ ] Ran the bias self-check (Notes): is the shortlist family-skewed, and
      if so, is that because it genuinely scored best?
- [ ] Output is a set of options with pros/cons, not a forced ranking,
      unless one candidate truly dominates (stated as an observed outcome).
- [ ] If consequential-decision: named the risk categories and included a
      human-in-the-loop recommendation.
- [ ] Deployment notes (export command, device placement) for every viable
      option, not just one.

## Examples

### Industrial defect description on an NPU-only edge box

**Input:** "...describes visible defects in a short sentence, running on an
NPU-only Core Ultra box with no internet access at runtime."

**Expected:** Open search → 3–5 current-generation ~2B candidates with
pros/cons on defect-description relevance (flag this is general
captioning/VQA, not a dedicated defect benchmark), MMBench/MMMU proxies,
NPU-fit at INT4, and license — labeled cross-generation proxy if needed.
2–3 options with export commands, not one forced pick; note offline
operation needs the model pre-downloaded.

### Single-model check (user-provided shortlist of one)

**Input:** "Will `<org>/<Model>-7B-Instruct` run on my Core Ultra 7 laptop's
iGPU for a document-QA chatbot?"

**Expected:** Branch A, one item — skip Step 4; confirm OpenVINO support, the
exact license for this size/variant, and INT4 fit on a typical iGPU budget;
report fit/no-fit with the export command, and check the family's Hub org
page for a newer generation to surface as an option.

## Edge Cases

- **No candidate satisfies every constraint:** relax compute tier first (NPU
  → iGPU → Arc) before accuracy or license; present the trade-off explicitly.
- **Task doesn't need a VLM** (pure counting/classification, no language
  output): say so, recommend a lighter detector/classifier instead.
- **Gated or license-ambiguous model:** don't recommend as primary for
  public/commercial use without flagging it; see
  `references/model-handling-procedures.md` if gated.
- **Named model isn't OpenVINO-validated:** not disqualifying — treat as
  Unknown/Plausible and recommend a validated fallback alongside it.
- **Shortlist (Branch A) all fail gating:** say none pass and offer Branch B,
  rather than picking the least-bad option.
- **User unsure shortlist vs. search:** default to Branch B and say why.
- **Capability no public VLM reliably has** (e.g. pixel segmentation): say so
  and suggest a hybrid pipeline (specialist CV + VLM for language).
- **Open-ended anomaly/novelty alerting:** not a benchmarked capability —
  recommend a closed, enumerable reframing, and flag that reliability needs
  validation on the user's footage plus supporting logic (windowing,
  de-duplication, human review) beyond the model call itself.
- **Sensor-mounted/mobile platform** (drone, vehicle, robot, wearable):
  confirm compute placement (Step 1) before sizing — embedded is far more
  constrained than a nearby gateway on the same feed.
- **Newest generation lacks benchmark/compute-fit data:** recommend the
  verified-newest checkpoint anyway, cite an older same-size sibling as a
  labeled proxy, and recommend an eval pass or export probe first.

## Notes

- Benchmarks shift frequently; state the date of any number cited, and note
  that production accuracy should be validated on the user's own data.
- If a fact (generation, license, benchmark number) was established earlier
  in this conversation and meaningful time has passed, re-verify rather than
  silently reusing it.
- The three `references/*.md` tables are dated snapshots that seed the
  search, never a substitute for the Currency rule's live verification.
- Family/model names used as illustrations anywhere in this skill's text —
  including reference-table row order — carry no ranking signal. Weight
  every family purely on how it scores against the 4 vectors, and check
  whether your own shortlist is skewed toward one family before presenting
  it — verify that's because it genuinely scored best, not familiarity.
