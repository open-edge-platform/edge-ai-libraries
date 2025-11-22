# Video Search Scoring The aggregation pipeline itself has five concrete steps:

1. **Segment** – Frames sharing a `video_id` are bucketed into `⌊timestamp / segment_duration⌋` ranges (default 8 s). Missing video duration metadata falls back to a 30 s baseline for downstream logging only.
2. **Score** – Every segment is evaluated by `calculate_segment_score` (explained in detail below). `determine_seek_point` picks a playback timestamp just before the best frame.
3. **Normalize** – Raw scores are scaled to [0, 1] range using min-max normalization, preserving relative ordering while ensuring consistent score ranges across queries.
4. **Filter** – `apply_temporal_overlap_filtering` removes lower-ranked segments that collide with stronger ones from the same video by more than `AGGREGATION_MIN_GAP` seconds. The default gap (`0`) effectively disables suppression so consecutive windows may surface.
5. **Rank & format** – Winners are sorted by final score, truncated to `AGGREGATION_MAX_RESULTS`, and converted back into user-facing documents.ok

This document walks through the search microservice end-to-end, explains how the qualitative-only scorer works, and shows how to tune each knob with concrete examples.

---

## 🔎 TL;DR

- We fetch the top `AGGREGATION_INITIAL_K` frame hits from VDMS, group them into 8 s windows, score each window by *peak* and *sustained* quality, optionally boost windows that sit near the globally best frame, then keep the top `AGGREGATION_MAX_RESULTS` non-overlapping segments per query.
- Only two signals influence rank today: (1) the strength of the frames inside the window and (2) temporal proximity to the single best frame across the whole result set.
- Tweaking weights lets you bias toward “spiky” matches (raise `AGGREGATION_QUAL_MAX_WEIGHT`) or stretches of consistent quality (raise `AGGREGATION_QUAL_TOP_WEIGHT`). Turning down `AGGREGATION_CONTEXT_BOOST_STRENGTH` removes the proximity bonus entirely.

---

## 🚦 End-to-end request flow

| Stage | What happens | Key knobs |
| --- | --- | --- |
| 1. Retrieval | `server.py::query_endpoint` calls `VDMS.similarity_search_with_score` to pull up to `AGGREGATION_INITIAL_K` frames per query. | `AGGREGATION_INITIAL_K` |
| 2. Metadata enrichment | Each frame gets its VDMS score stored as `relevance_score`; optional tag filtering happens here. | Query payload tags |
| 3. Temporal aggregation | `aggregate_frame_results_to_videos` drives segmentation → scoring → filtering → ranking. | See below |
| 4. Response shaping | `format_aggregated_results` returns LangChain-style docs with timing, scores, and URLs. | `AGGREGATION_MAX_RESULTS`, seek offset |

The aggregation pipeline itself has four concrete steps:

1. **Segment** – Frames sharing a `video_id` are bucketed into `⌊timestamp / segment_duration⌋` ranges (default 8 s). Missing video duration metadata falls back to a 30 s baseline for downstream logging only.
2. **Score** – Every segment is evaluated by `calculate_segment_score` (explained in detail below). `determine_seek_point` picks a playback timestamp just before the best frame.
3. **Filter** – `apply_temporal_overlap_filtering` removes lower-ranked segments that collide with stronger ones from the same video by more than `AGGREGATION_MIN_GAP` seconds. The default gap (`0`) effectively disables suppression so consecutive windows may surface.
4. **Rank & format** – Winners are sorted by final score, truncated to `AGGREGATION_MAX_RESULTS`, and converted back into user-facing documents.

---

## 🧮 Scoring breakdown

`calculate_segment_score` is intentionally lean—only frame quality and contextual proximity affect the outcome. Legacy length/density bonuses were stripped to keep the math transparent.

### Step 1 — Gather raw scores

For each segment we collect the list of frame scores $\{s_1, \dots, s_n\}$ and note the timestamp of the strongest frame `$t_{\text{segment}}`.

### Step 2 — Dynamic top-N selection

We choose how many frames participate in the sustained quality average:

$$
N = \min\bigl(\max(\lceil n \cdot \text{top\_ratio}\rceil,\ \text{top\_min\_count}),\ \text{top\_max\_count},\ n\bigr)
$$

The top $N$ scores (sorted descending) are averaged to obtain $\overline{s}_{\text{top}}$.

### Step 3 — Base quality blend

Weights are normalised so `max_component + top_component = 1`. With $s_{\max} = \max(s_i)$ we compute:

$$
s_{\text{base}} = w_{\max} \cdot s_{\max} + w_{\text{top}} \cdot \overline{s}_{\text{top}}
$$

`quality_score` in the breakdown is exactly $s_{\text{base}}$.

### Step 4 — Contextual proximity (optional)

We find the global best frame across every segment, `$t_{\text{global}}`. The segment receives a proximity weight:

$$
	ext{contextual\_weight} = e^{-(\Delta t / \sigma)^2},\quad \Delta t = |t_{\text{segment}} - t_{\text{global}}|
$$

Finally, the raw score is computed as:

$$
s_{\text{raw}} = s_{\text{base}} \times \left(1 + \text{boost\_strength} \times \text{contextual\_weight}\right)
$$

Setting `boost_strength` to `0` disables the contextual boost entirely.

**Score normalization:** After all segments are scored, the raw scores are normalized to the [0, 1] range using min-max scaling:

$$
s_{\text{final}} = \frac{s_{\text{raw}} - s_{\min}}{s_{\max} - s_{\min}}
$$

This ensures consistent score ranges across queries while preserving relative ordering.

### What you get in `score_breakdown`

| Field | Meaning |
| --- | --- |
| `max_frame_score` | Highest single-frame score inside the segment ($s_{\max}$). |
| `top_n_avg_score` | Average across the dynamically selected top-N frames ($\overline{s}_{\text{top}}$). |
| `top_n_frame_count` | The value of $N$ chosen for the sustained average. |
| `quality_score` | Base blend $s_{\text{base}}$. |
| `contextual_weight` | Gaussian weight in $[0,1]$ describing proximity to the global best frame. |
| `contextual_boost_factor` | The configured `boost_strength`. |
| `raw_score` | Pre-normalization score $s_{\text{raw}}$ before min-max scaling. |
| `score` | Final normalized value $s_{\text{final}} \in [0,1]$ used for ranking. |

---

## 🛠️ Configuration cheat sheet

All knobs are surfaced as environment variables (and mirrored in `config.yaml`).

| Knob | Default | Intuition | When to tweak |
| --- | --- | --- | --- |
| `AGGREGATION_ENABLED` | `true` | Master switch for aggregation. When `false`, we return raw frame hits. | Disable only for debugging or when aggregation latency must be zero. |
| `AGGREGATION_INITIAL_K` | `1000` | Size of the frame pool fetched from VDMS before aggregation. | Increase for long videos or very diverse scenes; decrease to reduce VDMS load. |
| `AGGREGATION_SEGMENT_DURATION` | `8` | Segment length (seconds). | Shorten for fast action scenes; lengthen for slow-moving footage. |
| `AGGREGATION_MIN_GAP` | `0` | Minimum allowed gap between winning segments from the same video. | Raise to suppress near-duplicates; keep at `0` for continuous coverage. |
| `AGGREGATION_MAX_RESULTS` | `20` | Final number of video segments returned. | Trim for snappier UX or expand for investigative tooling. |
| `AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS` | `0.0` | How far to rewind from the best frame when choosing the seek timestamp. | Add 1–2 s to give viewers extra context before the key moment. |
| `AGGREGATION_QUAL_MAX_WEIGHT` | `0.65` | Blend weight for $s_{\max}$. | Raise for “needle in a haystack” searches where the sharpest frame matters most. |
| `AGGREGATION_QUAL_TOP_WEIGHT` | `0.35` | Blend weight for $\overline{s}_{\text{top}}$. | Raise when you care about sustained relevance across multiple frames. |
| `AGGREGATION_QUAL_TOP_RATIO` | `0.35` | Fraction of frames tested for the sustained average before clamping. | Push higher to reward dense clusters of good frames. |
| `AGGREGATION_QUAL_TOP_MIN_COUNT` | `2` | Lower bound on the sustained average frame count. | Increase when segments often contain very few frames but you still want a minimum evidence bar. |
| `AGGREGATION_QUAL_TOP_MAX_COUNT` | `6` | Upper bound on the sustained average frame count. | Lower to focus on just the very best frames; raise to account for long dense clusters. |
| `AGGREGATION_CONTEXT_SIGMA_SECONDS` | `40.0` | Width of the Gaussian proximity curve (seconds). | Shrink to reward segments right next to the global best; expand for looser grouping. |
| `AGGREGATION_CONTEXT_BOOST_STRENGTH` | `0.5` | Multiplier applied to `contextual_weight`. | Dial down to reduce the influence of the global peak, or set to `0` to disable. |

All values are loaded through `src/utils/common.py::Settings` and cached in-process.

---

## 🧪 Walk-through example

Imagine we retrieved 1,000 frames for a traffic query. The single best frame scores **0.92** at **t = 360.5 s**.

### Segment A — downtown crosswalk (352–360 s)

- Scores: `[0.18, 0.19, 0.20, 0.24]` → $s_{\max}=0.24$.
- With the defaults, $N = 2$ and $\overline{s}_{\text{top}} = 0.22$.
- $s_{\text{base}} = 0.65·0.24 + 0.35·0.22 = 0.233$.
- Proximity: segment best frame at 359.5 s → $\Delta t = 1.0$ → `contextual_weight ≈ 0.999`.
- Raw: $s_{\text{raw}} = 0.233 × (1 + 0.5 × 0.999) ≈ 0.349$.

### Segment B — out-of-town freeway (160–168 s)

- Scores: `[0.21, 0.23, 0.19]` → $s_{\max}=0.23$, $\overline{s}_{\text{top}}=0.22$.
- Base equals `0.226` (same sustained quality, slightly weaker peak).
- Proximity: best frame 196 s away → `contextual_weight ≈ 0`. 
- Raw: $s_{\text{raw}}$ stays `0.226`.

### After normalization

Suppose the raw score range across all segments is [0.180, 0.360]:
- **Segment A**: $s_{\text{final}} = (0.349 - 0.180) / (0.360 - 0.180) ≈ 0.94$
- **Segment B**: $s_{\text{final}} = (0.226 - 0.180) / (0.360 - 0.180) ≈ 0.26$

**Take-away:** Even though both segments have similar sustained quality, the crosswalk segment jumps ahead because it sits next to the globally strongest frame. After normalization, the relative ordering is preserved but scores are scaled to [0, 1] for easier interpretation. Setting `AGGREGATION_CONTEXT_BOOST_STRENGTH=0` would make these two segments rank almost identically.

---

## ⚙️ Operational notes

- **Aggregation fallback:** If aggregation is disabled or fails, the API returns the top 20 frame hits. Failures are marked with `aggregation_stats.aggregation_failed = true` so clients can degrade gracefully.
- **Tag filtering:** Before aggregation, frame metadata can be filtered by query-specified tags. This affects both the global max score and the segment pool.
- **Telemetry:** Each response reports stage-by-stage timings (`segmentation_time_ms`, `scoring_time_ms`, etc.) plus the `score_breakdown` payload described above—use this for regression checks when retuning knobs.

---

## 📚 Code map

| Component | Where | Responsibility |
| --- | --- | --- |
| API entry | `server.py::query_endpoint` | Orchestrates retrieval, filtering, aggregation, and formatting. |
| Segmentation/scoring | `src/vdms_retriever/retriever.py` | Houses `create_temporal_segments`, `calculate_segment_score`, `determine_seek_point`, and `apply_temporal_overlap_filtering`. |
| Formatting | `server.py::format_aggregated_results` | Converts scored segments back into LangChain `Document`s with metadata, seek info, and debug fields. |

Armed with these details, you can confidently retune the knobs, reason about why a segment outranks another, or extend the pipeline with new qualitative signals.
