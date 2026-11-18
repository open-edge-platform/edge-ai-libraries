# Video embedding benchmark

Evaluate ViCLIP-B, ViCLIP-L and Cosmos-224p with the engine's OpenVINO encoders; no running services are needed.

## Environment

Run from the `data-intelligence-engine` directory with Python 3.11+ and the [engine dependencies](../../../pyproject.toml):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . --extra-index-url https://download.pytorch.org/whl/cpu
```

## Prepare models

Prepare the required packages with [prepare-models.sh](../../prepare-models.sh):

```bash
bash scripts/prepare-models.sh viclip-b viclip-l cosmos-224p
```

Prepare only the models you need; packages default to FP16 under `workspace/models`.

## Prepare dataset: MSR-VTT

Download the videos and 1K test captions from [Hugging Face](https://huggingface.co/datasets/friedrichor/MSR-VTT), then extract the videos (about 2.2 GB to download):

```bash
hf download --repo-type dataset friedrichor/MSR-VTT \
  msrvtt_test_1k.json MSRVTT_Videos.zip --local-dir ./msrvtt
python -m zipfile -e ./msrvtt/MSRVTT_Videos.zip ./msrvtt
```

Use the downloaded JSON directly; keep the extracted `video/` directory beside it.

## Run

Compare all three models on an OpenVINO GPU:

```bash
python scripts/eval_retrieval/video-embeddings/benchmarking.py \
	--manifest ./msrvtt/msrvtt_test_1k.json \
	--models viclip-b viclip-l cosmos-224p --device GPU.0 \
	--out-dir ./results/video-embeddings-1k
```

Run a quick Cosmos-only subset on the default CPU device:

```bash
python scripts/eval_retrieval/video-embeddings/benchmarking.py \
	--manifest ./msrvtt/msrvtt_test_1k.json \
	--models cosmos-224p --limit 10 \
	--out-dir ./results/cosmos-10
```

Remove `--limit 10` for the full dataset; subset scores use a smaller gallery and are not comparable.

## Options

- `--manifest`: MSR-VTT JSON or JSONL (`media_path` and `captions` per row).
- `--models`: one or more of `viclip-b` (default), `viclip-l`, `cosmos-224p`.
- `--device` defaults to `CPU`; use `GPU.0` to select an available OpenVINO GPU.
- `--model-root`: engine `workspace/models`; respects `ENGINE_MODEL_ROOT_PATH` or `ENGINE_WORKSPACE`.
- `--viclip-b-model-path`, `--viclip-l-model-path`, `--cosmos-224p-model-path`: individual package paths, including FP32 variants.
- `--text-batch-size` defaults to `32`; `--limit` defaults to `0`, meaning the full manifest.
- `--out-dir` defaults to `./results/video-embeddings` relative to the working directory and must be new or empty.
- `--dry-run`: check files and print commands without inference or output files.

## Results

Models run sequentially. Retrieval uses exact cosine similarity and the best caption rank per video.

Each model writes `<model>.json` and `<model>.log`; combined reports are `results.csv` and `summary.json`. R@1, R@5 and R@10 are percentages in CSV and fractions in JSON.

Duration includes model loading, video decoding and inference; average query time is total duration divided by caption count, not online query latency.
