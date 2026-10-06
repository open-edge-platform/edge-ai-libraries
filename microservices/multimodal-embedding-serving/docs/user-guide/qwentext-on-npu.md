<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# QwenText Models on NPU

QwenText models (`QwenText/qwen3-embedding-0.6b`, `-4b`, `-8b`) run on Intel
NPU via `EMBEDDING_DEVICE=NPU`. The NPU requires a **static graph shape**, so
the model is compiled to a fixed `[batch, sequence_length]`. That fixed
sequence length caps how much text each inference pass reads.

Everything on this page applies **only to QwenText on NPU**. On CPU and GPU
these models keep dynamic shapes and their full `max_length` context, and the
variables below are ignored.

No configuration is required - the defaults give a working, correct service.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EMBEDDING_STATIC_SEQ_LEN` | `2048` | Tokens read per inference pass. |
| `EMBEDDING_CHUNK_LONG_TEXT` | `true` | Split over-long text instead of truncating it. |

Static-shape compilation, the batch size (`1`) and the chunk overlap (`10%`)
are built in rather than configurable - each has only one correct or useful
value.

**Batch size** is fixed at 1 because it is the only shape that compiles for
Qwen3-Embedding on NPU; larger batches are rejected by the compiler, and no
`NPU_BATCH_MODE` setting helps. This does not limit request size: requests with
more texts are split into batch-1 passes automatically.

## Choosing a sequence length

`EMBEDDING_STATIC_SEQ_LEN` must be one of `128`, `256`, `512`, `1024`, `2048`,
`4096`, or `8192`, capped at the model's `max_length`. Other values are rounded
**up** with a warning - rounding down would discard more text than requested.
The set is restricted because each value triggers its own NPU compilation.

Every input is padded to this length, so it is the **fixed cost of every
inference**, not just an upper limit. Measured on an Intel(R) Core(TM) Ultra 9
285H NPU with Qwen3-Embedding-0.6B at batch 1:

| Sequence length | Compile (first start) | Latency per text |
|---|---|---|
| 512 | 11 s | 0.26 s |
| 1024 | 22 s | 0.63 s |
| 2048 (default) | 75 s | 1.7 s |
| 4096 | 6.9 min | 4.6 s |
| 8192 | 20 min | 35.8 s |

Pick the smallest value that covers your typical input - latency is paid on
every request, compile time only once. The 2048 default is ~27x the context of
the CLIP-family text encoders (CLIP 77 tokens, SigLIP 64, CN-CLIP 52) and
covers a typical 1000-word video summary in full.

## Long text handling

**The problem.** Tokenizers handle over-long input by truncating it, so the
discarded remainder has *no effect* on the embedding - and this fails silently.
Two video summaries sharing a 600-token opening but ending differently (a fire
versus a birthday party) embed to cosine `1.000000` at
`EMBEDDING_STATIC_SEQ_LEN=512`: identical vectors. A search for "warehouse
fire" then matches the birthday party just as strongly.

**The fix.** Over-long text is split into overlapping chunks that each fit the
budget. Each chunk is embedded and the vectors are combined into one, so the
whole document contributes. The API is unchanged - one input still returns one
vector.

Chunks are combined as a **weighted** average, each weighted by the tokens it
contributes that no earlier chunk covered, so every token counts exactly once.
This matters because the final window is anchored to the end of the text,
making all windows full-size; an unweighted mean would let a window that is
almost entirely overlap count as much as a full one. Measured at
`EMBEDDING_STATIC_SEQ_LEN=512`, adding **one** token to a 511-token document
moved its embedding `6.81%` unweighted versus `0.00%` weighted - while adding
200 tokens moved it `6.07%`, barely more. The shift tracked the chunk boundary
rather than the content; with novel-token weighting it tracks content
(`0.00%` for one token, `1.52%` for 200).

Embedding a 511-token document, then the same document with a 1500-token
unrelated passage appended - appending unrelated text *should* change the
vector, so a similarity near 1.0 means it was ignored:

| Mode | Cosine | Meaning |
|---|---|---|
| Truncation (`EMBEDDING_CHUNK_LONG_TEXT=false`) | `1.000000` | Identical vectors; the appended text had zero influence. |
| Chunking (default) | ~`0.80` | Vectors differ, correctly reflecting that the documents are not the same. |

The truncation result is exactly `1.000000` by construction. The chunking
figure varies with the sample text, but stays far below `1.0` - which is the
point. For the warehouse pair above, chunking gives ~`0.99`: still high, since
those summaries really are ~98% identical, but no longer indistinguishable.

Consecutive chunks overlap by a fixed **10%** so a sentence spanning a boundary
stays fully represented in at least one chunk. Sweeping the overlap from 0% to
45% changed the final embedding by only 1-2% while raising the chunk count -
and inference cost - by up to 50%, so there is no better value to choose.

**Cost.** One inference pass runs per chunk, so a document twice the budget
takes roughly twice as long. Raising `EMBEDDING_STATIC_SEQ_LEN` produces fewer
chunks but raises latency for *every* request. Text that fits the budget never
triggers chunking and costs nothing. Set `EMBEDDING_CHUNK_LONG_TEXT=false` to
restore truncation, which logs a warning naming the token count.

## Compilation caching

The first start for a given device and shape compiles an NPU blob, cached under
`<EMBEDDING_OV_MODELS_DIR>/.../ov_cache/` in a shape-named directory (for
example `npu_1x2048`). Later starts with the same shape reuse it. Because the
cache is keyed by shape, changing `EMBEDDING_STATIC_SEQ_LEN` costs a one-time
recompile.

## Example

```bash
export EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"
export EMBEDDING_DEVICE=NPU
export EMBEDDING_STATIC_SEQ_LEN=1024   # optional; 2048 is the default

source setup.sh
docker compose -f docker/compose.yaml up -d
curl -s localhost:9777/model/current
```

```json
{"model":"QwenText/qwen3-embedding-0.6b","device":"NPU","use_openvino":true}
```

## Troubleshooting

If a QwenText model fails to load on NPU with:

```text
expected exactly 1 dynamic output bound dimension, got 2
```

the model was compiled without static shapes. This is handled automatically on
NPU; the error indicates the reshape step did not run.

## Related

- [Get Started](./get-started.md) - deployment and general configuration
- [Supported Models](./supported-models.md) - the full model list
- [System Requirements](./get-started/system-requirements.md) - hardware prerequisites
