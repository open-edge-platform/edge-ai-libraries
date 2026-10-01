<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# QwenText Models on NPU

QwenText models (`QwenText/qwen3-embedding-0.6b`, `-4b`, `-8b`) run on Intel
NPU via `EMBEDDING_DEVICE=NPU`, but the NPU imposes two constraints that do not
apply on CPU or GPU: the graph must have a **static shape**, and the resulting
fixed sequence length caps how much text is read per inference pass.

This page covers both, and the settings that control them. Everything here is
specific to the QwenText family on NPU - all variables described are ignored on
CPU and GPU, where these models run with dynamic shapes and use their full
`max_length` context. Chunking is likewise NPU-only: on CPU and GPU, text
beyond `max_length` is truncated by the tokenizer as it always has been.

## Why static shapes are required

The exported OpenVINO IR for Qwen3-Embedding is dynamic on **both** batch and
sequence length. The NPU compiler tolerates at most one unbounded dynamic
dimension and rejects the graph outright:

```text
Reshape node '__module.layers.0.self_attn/aten::view/Reshape':
expected exactly 1 dynamic output bound dimension, got 2
```

The handler therefore reshapes the model to a fixed `[batch, sequence_length]`
before compiling. This happens automatically on NPU; no configuration is
required to get a working service.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EMBEDDING_STATIC_SEQ_LEN` | `2048` | Tokens read per inference pass. |
| `EMBEDDING_CHUNK_LONG_TEXT` | `true` | Split over-long text instead of truncating it. |

Both are optional. The defaults produce a working, correct service on NPU.

Static-shape compilation itself, the batch size (`1`) and the chunk overlap
(`0.1`) are not configurable - each has exactly one value that is correct or
useful, so they are built in rather than left as settings to get wrong. The
reasoning is recorded below.

### Batch size is fixed at 1

Batch 1 is the only shape known to compile for Qwen3-Embedding on NPU, so it is
built in rather than exposed as a setting - there is no other working value to
choose. Larger static batches are rejected by the NPU compiler; the exact
message depends on the OpenVINO release (a `ConstantFolding` buffer-size
mismatch on 2026.2.x, a Level Zero / VCL `Compilation failed` on 2026.4.0).
Setting `NPU_BATCH_MODE` does not help either: `COMPILER` and `AUTO` both fail
in the compiler, and `PLUGIN` fails immediately with `Cannot debatch a model`.

This does **not** limit how many texts you can send: requests containing more
texts are split into batch-1 passes automatically, so multi-text requests work
normally.

### Choosing a sequence length

`EMBEDDING_STATIC_SEQ_LEN` must be one of `128`, `256`, `512`, `1024`, `2048`,
`4096`, or `8192`, capped at the model's `max_length`. Any other value is
rounded **up** to the next supported value with a warning - rounding down would
discard more text than requested. The set is restricted because each distinct
value triggers its own NPU compilation.

Every input is padded to this length, so it is the **fixed cost of every
inference**, not merely an upper limit. Measured on the Intel NPU of an
Intel(R) Core(TM) Ultra 9 285H with Qwen3-Embedding-0.6B at batch 1; compile
time is one-time and cached per shape:

| Sequence length | Compile (first start) | Latency per text |
|---|---|---|
| 512 | 11 s | 0.26 s |
| 1024 | 22 s | 0.63 s |
| 2048 (default) | 75 s | 1.7 s |
| 4096 | 6.9 min | 4.6 s |
| 8192 | 20 min | 35.8 s |

Pick the smallest value that covers your typical input: latency is paid on
every request, while compile time is paid once. 8192 is compilable but
impractical for serving at 35.8 s per embedding.

The default of 2048 preserves the reason to choose QwenText at all - it is
roughly 27x the context of the CLIP-family text encoders (CLIP 77 tokens,
SigLIP 64, CN-CLIP 52) and covers a typical 1000-word video summary in full.

## Long text handling

### The problem: truncation silently discards text

A model reads at most `EMBEDDING_STATIC_SEQ_LEN` tokens. By default a tokenizer
handles longer input by *truncating* it - keeping the first N tokens and
throwing the rest away. The embedding is computed from the surviving portion
only, so the discarded remainder has **no effect whatsoever** on the vector.

This fails quietly rather than raising an error, which makes it easy to miss.
Consider two video summaries that open with the same lengthy scene description
but end very differently:

```text
Summary A: <600 tokens of identical warehouse description> ... then a fire breaks out.
Summary B: <600 tokens of identical warehouse description> ... then a birthday party begins.
```

At `EMBEDDING_STATIC_SEQ_LEN=512`, truncation keeps only part of the shared
opening and drops both endings entirely. The two summaries produce **the same
vector** - measured cosine similarity `1.000000`, meaning they are
indistinguishable. A search for "warehouse fire" then matches the birthday
party just as strongly, and nothing in the logs indicates a problem.

### The fix: chunking

Instead of discarding the overflow, the text is split into overlapping chunks
that each fit the budget. Every chunk is embedded, and the resulting vectors
are combined into one, so the whole document contributes. The API contract is
unchanged - one input still returns exactly one vector.

Chunks are combined as a **weighted** average, where each chunk's weight is the
number of tokens it contributes that no earlier chunk already covered, so every
token of the document counts exactly once. Weighting matters because the final
window is anchored to the end of the text rather than left as a short stub: an
unweighted mean would then let a window that is almost entirely overlap count
as much as a full one. Measured on NPU at `EMBEDDING_STATIC_SEQ_LEN=512`,
adding a **single** token to a 511-token document moved its embedding by
`6.81%` under an unweighted mean, versus `0.00%` when weighted by novel tokens
- and adding 200 tokens moved it by `6.07%`, barely more than the one-token
case. That is the tell: the shift was governed by where the chunk boundary
landed rather than by how much text was actually added. With novel-token
weighting the shift tracks the content instead (`0.00%` for one token,
`1.52%` for 200).

With chunking enabled the pair above scores about `0.99` instead of an exact
`1.000000`. Still high, because these summaries genuinely are ~98% identical
text (600 of 612 tokens are shared), but no longer identical - the differing
endings now influence ranking instead of being invisible.

The effect is starker when the appended text is unrelated. Embedding a
document that exactly fills the budget, then embedding that same document with
a long unrelated passage appended, and comparing the two vectors (NPU,
`EMBEDDING_STATIC_SEQ_LEN=512`, 511-token document plus a 1500-token unrelated
tail) - appending unrelated content *should* change the vector, so a similarity
near 1.0 means the addition was ignored:

| Mode | Cosine similarity | What it means |
|---|---|---|
| Truncation (`EMBEDDING_CHUNK_LONG_TEXT=false`) | `1.000000` | Identical vectors. The appended passage was dropped and had zero influence. |
| Chunking (default) | ~`0.80` | Vectors differ substantially, correctly reflecting that the documents are not the same. |

The truncation result is exactly `1.000000` by construction - the extra text
never reaches the model. The chunking figure is illustrative: its exact value
depends on the sample text, but it stays far below `1.0`, which is the point.

Consecutive chunks overlap by a fixed 10% so a sentence spanning a chunk
boundary is still fully represented in at least one chunk. This is not
configurable: sweeping the overlap from 0% to 45% on NPU changed the final
embedding by only 1-2% (cosine `0.974`-`0.989` against the 10% default) while
raising the chunk count - and therefore the inference cost - by up to 50%.
There is no value an operator could pick that is reliably better, only slower.

### Cost

Chunking runs one inference pass per chunk, so a document twice the budget
takes roughly twice as long to embed. Raising `EMBEDDING_STATIC_SEQ_LEN` fits
more text per pass and produces fewer chunks, at the cost of higher latency for
*every* request (see the table above). If your text reliably fits within the
budget, chunking never activates and costs nothing.

Setting `EMBEDDING_CHUNK_LONG_TEXT=false` restores truncation. A warning naming
the token count is then logged whenever input is truncated.

## Compilation caching

The first startup for a given device and shape compiles an NPU blob, which is
cached per shape under `<EMBEDDING_OV_MODELS_DIR>/.../ov_cache/`, in a
directory named for the device and shape - for example `npu_1x2048` for the
defaults. Later startups with the same shape reuse it and are fast.

Because the cache is keyed by shape, changing `EMBEDDING_STATIC_SEQ_LEN` incurs
a one-time recompile at the next startup.

## Example

```bash
export EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"
export EMBEDDING_DEVICE=NPU
export EMBEDDING_STATIC_SEQ_LEN=1024   # optional; 2048 is the default

source setup.sh
docker compose -f docker/compose.yaml up -d
```

Confirm what was loaded:

```bash
curl -s localhost:9777/model/current
```

```json
{"model":"QwenText/qwen3-embedding-0.6b","device":"NPU","use_openvino":true}
```

## Related

- [Get Started](./get-started.md) - deployment and general configuration
- [Supported Models](./supported-models.md) - the full model list
- [System Requirements](./get-started/system-requirements.md) - hardware prerequisites
