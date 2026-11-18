---
name: vlm-model-selector
description: "Select a Vision-Language Model (VLM) from the Hugging Face model hub for a specific vision analytics task (captioning, VQA, OCR/document understanding, chart/table reading, grounding/detection-by-description, counting, multi-image or video reasoning), constrained to run on Intel's Core Ultra portfolio (NPU and/or iGPU) and/or Intel discrete GPUs in the Xe architecture series (Arc A-/B-Series, Arc Pro). Use when a user asks to pick/choose/recommend a VLM, or needs a model for a vision task on Core Ultra/NPU/iGPU or an Arc discrete GPU that is accurate, compute-fit, and has a usable public/commercial license. Elicits task details, then asks whether to evaluate a user-provided shortlist or run an open hub search, and follows the matching procedure. Produces a ranked shortlist with rationale, not just one name. DO NOT USE FOR: training/fine-tuning a model, text-only LLM selection, or a classical CV model (YOLO/CLIP) when no language output is needed."
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

Pick a Vision-Language Model for a user's vision analytics task by eliciting task
requirements, searching the Hugging Face hub, cross-referencing a benchmark
leaderboard and the
[OpenVINO supported-models page](https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html)
for compute fit, and
checking the actual license terms — then return a ranked shortlist with
rationale, not a single unexplained answer. Covers both Core Ultra's
integrated NPU/iGPU and Intel's discrete GPUs in the Xe architecture series
(Arc, Arc Pro).

This composes three independently-established practices rather than inventing a
new one: Hugging Face's own "finding the right VLM" guidance (leaderboard +
model-card review), the HuggingGPT pattern of matching a task description
against model-card descriptions/tags, and gating candidates against a
hardware-vendor-maintained compatibility list before investing analysis time in
them. See `references/` for supporting data backing this skill's design.

Requires network access to huggingface.co (model hub, model cards) and the
canonical OpenVINO supported-models page
(https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html)
— always fetch this exact URL when checking compute-fit/architecture support,
rather than a remembered or guessed OpenVINO documentation URL, since OpenVINO
reorganizes its docs between releases; no special tooling is needed beyond web
fetch.

## When to Use

- User wants to add a vision/image/video understanding capability and needs a
  concrete VLM recommendation.
- User mentions Intel Core Ultra, NPU, iGPU, Arc, discrete GPU, Xe
  architecture, OpenVINO, or "edge" deployment alongside a vision/VLM task.
- User names a candidate model and asks "will this work on my Core Ultra
  laptop?" or "will this run on my Arc GPU?" (treat it as a one-item
  user-provided shortlist — run Step 3 against that single candidate instead
  of searching).
- Do not use this skill if the task has no language-output requirement at all
  (pure classification/detection/segmentation) — recommend a lighter CV-only
  pipeline instead (see Edge Cases).

## Procedure

### Step 1 — Elicit the vision analytics task

Before searching, confirm these details with the user. Ask only for what is
missing; do not re-ask what the user already stated. Use the `vscode_askQuestions`
tool (or equivalent clarification mechanism) for a compact multi-question pass
rather than one question at a time.

Required:
- **Task description**: what should the model do with the image/video (e.g.,
  "describe safety-vest compliance in a factory frame", "answer questions about
  a scanned invoice", "summarize a 30-second clip").
- **Input modality**: single image, multiple images per request, or video
  (and if video: live stream with sampled frames, or short clips).
- **Output shape**: free-form text, structured/JSON (for programmatic
  downstream use), bounding boxes/grounding, or a closed label set.
- **Target device tier**: Core Ultra NPU-only (lowest power, smallest model
  budget), Core Ultra iGPU (larger budget), a discrete Intel GPU in the Xe
  architecture series — Arc A-/B-Series or Arc Pro (consumer/workstation,
  dedicated VRAM, a meaningfully larger budget than Core Ultra iGPU) — or
  "either, pick the better fit." If the user doesn't know, default to assuming
  a hybrid NPU+iGPU Core Ultra Series 2/3 system with 16–32 GB RAM and say so
  explicitly in the final recommendation.

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

1. Get the user's exact candidate list. If they give informal names ("the
   Qwen vision model"), resolve each to its precise Hub repo ID
   (`org/model-name`) before proceeding, and tell the user which exact
   checkpoint you resolved it to. When resolving an informal family name,
   check the family's Hub org page (sorted by most-recently-created/updated)
   for its newest shipped generation/release rather than defaulting to
   whichever checkpoint is most familiar from training data — families ship
   new generations every few months, so the generation number or name you
   recall is never a safe assumption of currency, and neither is any specific
   generation named anywhere in this skill's own instructions or reference
   files (those are dated snapshots, not a currency claim). If the user named
   an older generation explicitly, honor their choice but mention that a newer
   generation exists as an option. If a named model can't be found on the Hub,
   say so rather than silently dropping it.
2. **Skip discovery** — do not browse the Hub or the leaderboard for *new*
   candidates; the scope is exactly the models the user named (plus, if
   useful, immediate sibling sizes of the same family if the user seems open
   to that — confirm before adding any model they didn't name).
3. Apply the same gates and review as the open-search branch, just scoped to
   this list: compute-fit tiering (**Validated** — on the
   [OpenVINO supported-models page](https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html);
   **Plausible** — architecture resembles a listed one;
   **Unknown** — novel/unrecognized architecture, flag as needing an export
   feasibility probe) and license bucketing (`references/license-taxonomy.md`
   — for an unrecognized, `other`, or missing license tag, resolve it against
   the actual license text before excluding the candidate; only exclude if the
   text can't be found/verified or conflicts with the user's deployment, never
   on the tag alone and never by assuming permissive). Then do the full model-card
   review in Step 5 for each one.
4. If the Open VLM Leaderboard happens to have an entry for a named model,
   use it (third-party accuracy signal); otherwise use the model's own
   self-reported numbers, clearly labeled as self-reported.
5. If none of the user's candidates pass the license/compute-fit gates, say so
   explicitly — do not silently recommend the least-bad disqualified option —
   and offer to switch to Branch B (open search) for an alternative.
6. Continue to **Step 6** (score/rank), scoped to just this list.

### Step 4 — Branch B: open search of the hub

1. **Broad programmatic discovery (the actual top-of-funnel):** query the Hub
   filtered on `pipeline_tag=image-text-to-text`, sorted by
   trending/downloads/most-recently-created (recency matters so new releases
   aren't missed), and cross-check the
   [Open VLM Leaderboard](https://huggingface.co/spaces/opencompass/open_vlm_leaderboard)
   (filterable by size and license) for benchmark-ranked candidates. Use
   `references/candidate-vlm-families.md` only as an accelerant/cross-check —
   not the limiting set; a new or niche model surfaced by the live query is
   equally eligible for the shortlist. State to the user that the Hub's own
   search matches mostly on model id/tags, not a deep semantic scan of every
   README — so "open" means a broadened but still bounded top-of-funnel
   (e.g., top 50–100 by trending/downloads/recency under the right tag, plus
   leaderboard entries), not an exhaustive scan of the entire hub. Do not let
   a family's most-famous/most-memorized checkpoint stand in for its current
   lineup — for every family that surfaces, check that family's own Hub org
   page or release notes for whatever generation is newest *right now*, and
   shortlist that one by default. Never substitute a specific generation name
   recalled from training data, or named as an example anywhere in this
   skill's instructions or reference files, for that live check — those names
   are illustrations of a naming pattern (e.g., a family may version its
   releases as `<Family><N>` or `<Family> <major>.<minor>`), not a claim about
   which one currently ships.
2. **Cheap metadata triage (do this before any deep review):** for every
   discovered candidate, apply two checks:
   - **License bucket** (`references/license-taxonomy.md`) — bucket a clearly
     tagged permissive license (e.g. Apache-2.0, MIT, BSD) directly from the
     tag. For an unrecognized, `other`, or missing license tag, do **not**
     exclude on the tag alone: immediately follow `license_link`/`license_name`
     to the actual license text (a quick resolution, not the full Step 5
     model-card review) and bucket it per `license-taxonomy.md`. Only exclude
     a candidate at this stage if the actual text can't be found/verified, or
     its terms conflict with the user's stated deployment constraints (e.g., a
     non-commercial clause against a commercial deployment) — never exclude
     solely because the Hub tag itself was ambiguous.
   - **Compute-fit tier** — **Validated** (architecture explicitly on the
     [OpenVINO supported-models page](https://docs.openvino.ai/nightly/documentation/compatibility-and-support/supported-models.html)
     — fetch this exact URL, don't rely on a remembered support list),
     **Plausible** (architecture class
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
   before finalizing it as a recommendation — don't resolve compute fit from
   metadata inference alone for these tiers. Do **not** add `--trust-remote-code`
   to this probe by default; if the export fails because the architecture
   needs custom code, follow "Handling a model that requires custom code"
   below before retrying with it.
4. **Accuracy signal with graceful fallback:** prefer leaderboard numbers
   (third-party verified). If a candidate has no leaderboard entry, fall back
   to self-reported model-card numbers (label as self-reported, lower
   confidence) or, failing that, community adoption (downloads/likes/recency)
   as a weak usability proxy — never silently present these as equivalent to
   a verified benchmark score. **Cross-generation proxy rule:** always
   recommend whichever generation you verified is newest at the needed size
   for actual deployment; if that exact checkpoint has no published
   leaderboard/model-card benchmark numbers yet, you may cite the equivalent
   size from the immediately preceding generation of the same family (i.e.,
   the newest generation that *does* have published numbers) as a stand-in
   accuracy signal — e.g., "no Video-MME number published yet for the
   newest-generation 2B checkpoint; using the prior generation's 2B number as
   a same-size-class proxy" — but always name the exact two checkpoints you
   compared, label the substitution explicitly as a cross-generation proxy,
   and never present an older generation's measured number as if it were
   measured on the newer checkpoint.
5. **Verification rigor for unfamiliar models:** every factual claim about a
   candidate that isn't a well-known, widely-documented model (size, license,
   capability, OpenVINO compatibility) must come from a freshly fetched source
   in this conversation, not recalled from training data — treat this as
   mandatory per field, not a spot-check, since there's no familiarity safety
   net for long-tail models. This exemption never covers *which generation is
   current* — familiarity from training data (and from this skill's own
   examples and reference files) skews toward whichever version was
   best-documented or most recently written about at the time, which is
   reliably an older generation by the time of use. Always confirm the newest
   shipped generation of a well-known family from a freshly fetched Hub/org
   page before finalizing a recommendation, even if an older generation's
   details are well remembered and even if a specific generation is named as
   an example in this skill's own instructions.
6. Continue to **Step 5** (model-card review) on the triaged ~8–10, then
   **Step 6** (score/rank).

### Step 5 — Review each candidate's model card

For each shortlisted candidate (Branch A's list, or Branch B's triaged ~8–10),
open its Hub model card and extract:

- **Task relevance**: intended-use section, capability tags (grounding, OCR,
  chart/doc, video) — does it explicitly claim the capability the task needs?
- **Accuracy**: benchmark numbers relevant to the task. Prefer third-party
  leaderboard numbers (Open VLM Leaderboard) over self-reported model-card
  numbers when both exist, since self-reported numbers can be cherry-picked.
  Match the benchmark to the task (e.g., OCRBench/DocVQA for documents,
  ChartQA for charts, MMMU/MMBench for general reasoning, MVBench/Video-MME
  for video).
- **Compute fit**: parameter count, available precisions (fp16/bf16, and
  critically int8/int4 or an existing OpenVINO IR / GGUF release), max image
  resolution or tiling behavior, video frame-count support. Cross-check
  against `references/intel-core-ultra-compute-envelope.md`, which covers both
  Core Ultra NPU/iGPU tiers and discrete Arc GPU tiers.
- **License**: the actual license terms, not just the short tag — follow
  `license_link`/`license_name` if the tag is `other`, and check for
  acceptable-use-policy riders even on named licenses (Gemma, Qwen large
  variants, MiniCPM). Use `references/license-taxonomy.md` to classify as
  usable / usable-with-conditions / not usable for the stated deployment.
  If the repo itself is gated (an access-request wall instead of, or in
  addition to, a license tag), follow "Handling a gated candidate" below
  before you can read the full card or any files.
- **Maintenance signal**: last update date and download/like counts, as a weak
  proxy for community support and longevity.

### Handling a gated candidate (access-request wall)

Some Hub models (e.g., several MiniCPM-V and Llama-derived VLM checkpoints) sit
behind a gate: the repo page shows an access-request wall, and downloads/API
calls return 401/403 until the user's own Hugging Face account has accepted the
terms. The agent can read the public parts of the page (license summary,
capability description) but **cannot accept the gate on the user's behalf** —
only the user's own account can agree to it. A Hugging Face access token is a
secret: never ask for its value in a chat question, and never type or relay one
into a terminal login prompt yourself.

1. Tell the user the candidate is gated, summarize what the gate actually asks
   for from the model page (e.g., contact-info sharing, an academic-use
   affirmation, a commercial-registration step), and link to the model page so
   they can read the real terms themselves.
2. Ask a plain yes/no question — never one requesting a secret value — about
   whether they already have access to this model on their Hugging Face
   account and have an auth token available locally. Confirm *that* a token
   exists, never *what* it is.
3. If they haven't accepted the gate yet: give them the exact model URL and
   ask them to log in to huggingface.co with their own account and click
   "Agree and access repository" there. Do not attempt this for them.
4. If they don't have a token set up: tell them to create a **Read**-scope
   token at https://huggingface.co/settings/tokens, then either set it as the
   `HF_TOKEN` environment variable in their own shell/profile, or run
   `huggingface-cli login` themselves and type the token directly at that
   prompt. If you (the agent) run `huggingface-cli login` in a shared
   terminal and it pauses waiting for the token, stop and tell the user to
   type it directly into that terminal — do not send it for them.
5. Once the user confirms both steps are done, verify *presence only*, never
   the value — e.g., check that `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN` is set, or
   run `huggingface-cli whoami` to confirm authentication succeeded — before
   continuing the model-card review or attempting an export for that
   candidate.
6. If the user declines or can't get access, drop the candidate (same handling
   as a Bucket 3 license in `references/license-taxonomy.md`) and continue
   with the next-best candidate instead of blocking the whole recommendation
   on it.

### Handling a model that requires custom code (`--trust-remote-code`)

Some Hub checkpoints ship a custom `modeling_*.py`/`configuration_*.py` file
and only load with `trust_remote_code=True` (`optimum-cli export openvino`'s
`--trust-remote-code` flag). That flag executes arbitrary Python from the
selected Hub repository locally, with the user's own permissions and whatever
credentials are available in that environment — it is a code-execution
decision, not a compute-fit or license decision. Passing a candidate's
license and architecture-compatibility checks **never** establishes that its
code is safe to run, so never enable this flag by default.

1. Default to running every export or feasibility probe in this skill
   (Step 4's feasibility probe, Step 6's recommended quantization command,
   and the `references/intel-core-ultra-compute-envelope.md` export
   reference) **without** `--trust-remote-code`. Try it without the flag
   first.
2. If the export fails specifically because the architecture needs custom
   code (check the error output and the model card for a `trust_remote_code`
   mention), stop and do not add the flag yourself. Tell the user: name the
   exact repo, identify the exact revision you'd need to run (a commit SHA,
   not a floating `main`/branch pointer that can change later), and describe
   what the custom code file(s) do if that's visible from the repo.
3. Only add `--trust-remote-code` after the user explicitly approves running
   that specific pinned revision's code. Never enable it silently or because
   it's the only way to "make the export work" — if the user doesn't approve,
   drop the candidate (or keep it only as a Plausible/Unknown-tier option with
   compute-fit explicitly marked unverified) and continue with the next-best
   candidate instead of blocking the whole recommendation on it.
4. When the user does approve, pin the revision in the actual command (e.g.
   `--model <hf-model-id>@<commit-sha>`) rather than the bare repo id, so a
   later, unreviewed commit to the same repo can't silently change what code
   executes on a subsequent run.

### Step 6 — Score, rank, and recommend

Build a comparison table across the 4 vectors (task relevance, accuracy,
compute fit, license) for the shortlist (Branch A: the user's provided list;
Branch B: the triaged ~8–10). For a Branch B table, also show each
candidate's compute-fit tier (Validated/Plausible/Unknown) and the accuracy
source confidence (leaderboard-verified / self-reported / adoption-proxy) so
the user isn't comparing numbers of different trustworthiness as if
equivalent. Pick one **primary recommendation** and one **fallback**, and
state the reasoning — which vector decided it, and what the user would need
to accept to pick a non-recommended alternative (e.g., "Model X scores higher
on OCRBench but is gated under a non-commercial license and is disqualified
for your public deployment").

Include deployment notes with the recommendation:
- Target device placement (Core Ultra NPU vs. iGPU vs. a discrete Arc GPU)
  and why.
- Expected quantization path, e.g.:
  ```bash
  optimum-cli export openvino --model <hf-model-id> --weight-format int4 <output-dir>
  ```
  Do not include `--trust-remote-code` in this default command. If the
  architecture actually requires it, say so explicitly and follow "Handling a
  model that requires custom code" below instead of silently adding the flag.
- Any export caveats noted on the OpenVINO supported-models page for that
  architecture (e.g., required `transformers` version pins, extra packages).

### Step 7 — Present results

Show the comparison table and recommendation to the user in the response —
this is the primary deliverable. State which approach was used (user-provided
shortlist vs. open search) so the user knows the scope of what was and wasn't
searched. Only write the analysis to a file if the user asks for it (e.g.,
"save this analysis"); don't create files unprompted.

## Examples

### Example: industrial defect description on an NPU-only edge box

**Input:** "I need a model that looks at a camera frame from a conveyor belt
and describes any visible defects in a short sentence, running on an NPU-only
Core Ultra box with no internet access at runtime."

**Expected output:** After confirming Step 2's choice is open search, a table
comparing 3–5 candidates drawn from each matched family's *current*
generation (verified live, not assumed) at the ~2B size scored on
defect-description relevance (general captioning/VQA, not a specialized
defect benchmark — flag this gap honestly), accuracy proxies from
MMBench/MMMU, NPU-fit at INT4, and license. If a current-generation checkpoint
has no published benchmark numbers yet, cite the same-size checkpoint from the
newest generation that *does* have published numbers (naming both checkpoints
explicitly) as a labeled cross-generation proxy rather than skipping the
metric. One primary recommendation with the `optimum-cli` export command, and
a note that offline operation requires the model and tokenizer to be
pre-downloaded since the NPU box has no runtime internet access.

### Example: single-model check (user-provided shortlist of one)

**Input:** "Will `Qwen/Qwen2.5-VL-7B-Instruct` run on my Core Ultra 7 laptop's
iGPU for a document-QA chatbot?"

**Expected output:** Treat this as Branch A with a one-item list — skip Step 4
(open search); run Step 3 then Steps 5–6 against just this model — confirm
it's on the OpenVINO supported-models list, check its license (verify it's the
Apache-2.0-licensed size, since some Qwen variants differ by size), confirm 7B
at INT4 fits a typical Core Ultra iGPU memory budget, and report fit/no-fit
with reasoning and the export command. Also check the Qwen Hub org page for
whether a newer generation's 7B-class checkpoint has since shipped and would
be a straightforward upgrade — the user named a specific generation but
didn't rule out a newer one, so surface it as an option (naming the exact
newer checkpoint found) rather than silently assuming the named generation is
still current.

## Edge Cases

- **No candidate satisfies every constraint:** relax the compute tier first
  (NPU → iGPU → discrete Arc, in order of what hardware the user actually has
  available) before relaxing accuracy or license; present the trade-off
  explicitly rather than silently picking a worse-fit model.
- **Task doesn't actually need a VLM** (e.g., pure object counting/classification
  with no natural-language output): say so and recommend a lighter
  detector/classifier (or detector + small captioner) instead of forcing a VLM.
- **Model is gated or license-ambiguous:** do not recommend it as primary for a
  public/commercial deployment without flagging the restriction and asking the
  user to confirm it's acceptable for their use case. If it's gated behind an
  access-request wall, follow "Handling a gated candidate" in Step 5 — get the
  user's confirmation of access/token presence, never the token value itself.
- **User already has a specific model in mind but it's not on the OpenVINO
  supported-models list:** say this explicitly — it's not disqualifying, but
  treat it as unvalidated/engineering-risk (*Unknown* or *Plausible* compute-fit
  tier) and recommend a validated fallback alongside it.
- **User's provided shortlist (Branch A) all fail gating:** don't silently
  pick the least-bad disqualified option — say none pass and offer to switch
  to Branch B (open search) for an alternative.
- **User is unsure whether to provide a list or search broadly:** default to
  Branch B (open search) and say why; let them redirect to Branch A if they
  think of specific candidates mid-conversation.
- **Task requires a capability no public VLM reliably has** (e.g., precise
  pixel-level segmentation): say so rather than overstating a VLM's fit, and
  suggest a hybrid pipeline (specialist CV model + VLM for the language part).
- **Newest generation in a matched family lacks published benchmark/compute-fit
  data:** don't discard it or silently fall back to recommending the older
  generation instead — recommend the verified-newest checkpoint for actual
  deployment, cite the nearest-older same-size sibling's numbers (naming both
  checkpoints explicitly) as an explicitly labeled cross-generation proxy, and
  recommend an actual eval pass on the user's data (or an `optimum-cli` export
  feasibility probe, if compute-fit itself is unconfirmed) before fully
  committing to the proxy numbers.

## Notes

- Benchmarks and leaderboard rankings shift frequently; always state the date
  of any benchmark numbers cited and note that production accuracy should be
  validated on the user's own data before deployment.
- Model families release new generations every few months, often faster than
  any document (including this skill and its reference files) can be kept
  current. Never let training-data familiarity with an older, well-documented
  checkpoint — or a specific generation named as an example anywhere in this
  skill's own instructions or reference files — stand in for checking whether
  a newer generation of that family exists. Always confirm the current lineup
  live (the family's Hub org page or release notes, sorted by recency) before
  finalizing a shortlist, and default to the newest generation unless the user
  specifically asked for an older one. Use an older generation's published
  numbers only as an explicitly labeled proxy when the current generation's
  equivalent size has no benchmark data yet — never as the primary
  recommendation when a newer same-size checkpoint exists and passes the same
  gates.
- `references/intel-core-ultra-compute-envelope.md` (Core Ultra NPU/iGPU *and*
  discrete Arc GPU tiers), `references/candidate-vlm-families.md`,
  and `references/license-taxonomy.md` are dated snapshots meant to seed the
  search, not replace live verification.
