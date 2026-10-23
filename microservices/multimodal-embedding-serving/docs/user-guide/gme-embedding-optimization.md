# Optimize GME on Intel GPU

This guide sets up the fastest GME configuration on an Intel GPU:

- GME in **INT4** precision (`GME_PRECISION=int4`), and
- an image whose OpenVINO GPU plugin is rebuilt with six GME-specific
  optimization patches.

Both steps are optional and independent. INT4 runs on the standard image, and
the patched plugin also speeds up the default INT8 precision. Use them
together for the largest gain. The standard image and the INT8 default remain
the recommended starting point; follow this guide when you need lower GME
latency on GPU.

## What changes

| Component | Standard | Optimized |
| --- | --- | --- |
| Precision | `GME_PRECISION=int8` (default) | `GME_PRECISION=int4` |
| Image | `multimodal-embedding-serving:<tag>` | the same image plus a patched GPU plugin, tagged `gme-gpu-patch` |
| OpenVINO | wheel from `pyproject.toml` | official `openvino==2026.4.1` wheel; its GPU plugin is replaced by one built from the same release with the patches applied |

The patches change only the OpenVINO GPU plugin. Model files, service code and
the API are unchanged, and the patched image runs every other model like the
standard image does. The patches are in
[`docker/gme-opt-patch/patches/openvino-2026.4.1`](../../docker/gme-opt-patch/patches/openvino-2026.4.1/)
and are applied in the order listed in its `series` file:

| Patch | Optimization |
| --- | --- |
| opt-1 | Extends SDPA broadcast/reshape fusion to stateless GQA inputs. |
| opt-2 | Fuses the SDPA output transpose into the GPU path. |
| opt-3 | Reorders eligible INT4 fully connected weights to an N-contiguous layout. |
| opt-4 | Reuses dynamic-quantization work across the RMS path. |
| opt-5 | Adds a threshold-gated visual MVN-to-dynamic-quantization fusion. |
| opt-6 | Adds a GPU kernel for the vision QKV head-first permutation. |

## Prerequisites

- A Linux host with an Intel GPU. The patches target the OpenCL GPU plugin, so
  they have no effect on `CPU` or `NPU`.
- The standard GPU setup works on this host: see
  [Running the Server with GPU](./get-started.md#running-the-server-with-gpu).
- For the one-time plugin build:
  - access to `github.com`; behind a proxy, export `http_proxy`, `https_proxy`
    and `no_proxy` before building;
  - about 10 GB of free Docker storage for the build cache;
  - roughly 2 GB of RAM per parallel compile job. The build uses one job per
    CPU by default; see [Troubleshooting](#troubleshooting) to limit it.

Run every command below from the microservice root
(`microservices/multimodal-embedding-serving`) in the same Bash terminal.

## Step 1: Build the standard image

The patched image is built on top of the standard image, so build that first
from the current source:

```bash
export EMBEDDING_MODEL_NAME=GME/gme-qwen2-vl-2b-instruct
export GME_PRECISION=int4
export EMBEDDING_DEVICE=GPU
unset REGISTRY_URL PROJECT_NAME
export TAG=latest
source setup.sh
docker compose -f docker/compose.yaml build \
  --build-arg http_proxy --build-arg https_proxy --build-arg no_proxy
```

This produces `multimodal-embedding-serving:latest`.

## Step 2: Build the patched image

```bash
docker build -f docker/gme-opt-patch/Dockerfile \
  --build-arg BASE_IMAGE=multimodal-embedding-serving:latest \
  --build-arg http_proxy --build-arg https_proxy --build-arg no_proxy \
  -t multimodal-embedding-serving:gme-gpu-patch .
```

The build:

1. clones the OpenVINO `2026.4.1` release and checks its commit,
2. applies the six patches in order and stops if any of them does not apply,
3. compiles only the GPU plugin (`openvino_intel_gpu_plugin`),
4. installs the official `openvino==2026.4.1` and `openvino-tokenizers==2026.4.1.0`
   wheels on top of the standard image and replaces the wheel's GPU plugin with
   the patched one, and
5. loads the patched plugin once and fails the build if it cannot.

The first build took about 15 minutes on a 128-core host (clone, build
dependencies, compile) and takes longer on smaller machines. Its last step
prints the loaded plugin:

```text
GPU plugin: Intel GPU plugin 2026.4.1-1-e213a147257
```

Docker caches the plugin build. Rebuilding after a change to the standard
image (Step 1) only repeats the short final stage.

## Step 3: Start the service with the patched image

Select the patched image through `TAG` and start the service:

```bash
export TAG=gme-gpu-patch
source setup.sh
# Only on the integrated GPU of an Intel Core Ultra Series 3 (Panther Lake) processor:
export OV_PERFORMANCE_MODE=LATENCY
docker compose -f docker/compose.yaml up -d --force-recreate
docker logs -f --tail=100 multimodal-embedding-serving
```

> [!IMPORTANT]
> On the integrated GPU of an Intel Core Ultra Series 3 (Panther Lake)
> processor, GME must run with `OV_PERFORMANCE_MODE=LATENCY`. With `GPU`
> selected, `setup.sh` switches the mode to `THROUGHPUT`, so export `LATENCY`
> again **after** every `source setup.sh`. In `THROUGHPUT` mode the GME handler
> lets OpenVINO create several GPU streams, and on this GPU visual inference
> (image and image+text requests) can hang in `InferRequest.wait()`; at the same
> time the host kernel log reports a reset of the `xe` driver's BCS (copy)
> engine. The request never returns, and the service has to be restarted. This
> applies to the standard image as well as the patched one. Other GPUs are not
> affected and can keep the `setup.sh` default.
>
> To check the mode of a running service, run
> `docker exec multimodal-embedding-serving printenv OV_PERFORMANCE_MODE`; the
> GME startup log also reports `streams=1` in `LATENCY` mode.

> [!IMPORTANT]
> While `TAG=gme-gpu-patch` is set, do not run `docker compose ... build` or
> `docker compose ... up --build`: they would rebuild the standard image under
> the `gme-gpu-patch` tag and overwrite the patched image. Switch back to
> `TAG=latest` before rebuilding the standard image, then repeat Step 2.

On the first start, GME is downloaded and exported to OpenVINO INT4 in the
`ov-models` volume at
`/app/ov_models/gme-qwen2-vl-2b-instruct-openvino-int4`. Export includes an
INT4 calibration pass and takes from several minutes to tens of minutes,
depending on the CPU; later starts reuse the package. The service becomes
healthy once loading finishes.

## Step 4: Verify

The GME startup log names the GPU plugin in use. The patched plugin reports:

```text
OpenVINO GPU plugin: Intel GPU plugin 2026.4.1-1-e213a147257
```

The plugin shipped in an OpenVINO wheel reports a release build number
instead, for example `2026.4.0-22959-99c81491cc3-releases/2026/4` in the
standard image. You can also compare the plugin file with the one the build
recorded:

```bash
docker exec multimodal-embedding-serving sh -c \
  'cat /opt/gme-opt-patch/plugin.sha256; sha256sum "$(python -c "import openvino, pathlib; print(pathlib.Path(openvino.__file__).parent / \"libs\" / \"libopenvino_intel_gpu_plugin.so\")")"'
```

Both lines show the same checksum. Then check the service:

```bash
curl -fsS http://localhost:9777/health
curl -fsS http://localhost:9777/model/current
```

## Expected results

The figures below come from the validation of the GME OpenVINO export and of
the patch set on an Intel GPU. They are warm, end-to-end latencies including
tokenization and image preprocessing; actual numbers depend on the GPU, driver
and image size.

**INT4 versus INT8** (standard plugin, default image-token limit; the image
used 1,260 visual tokens):

| Model | Text | Query | Image | Image+text |
| --- | ---: | ---: | ---: | ---: |
| INT8 | 65.2 ms | 64.0 ms | 2,123 ms | 2,118 ms |
| INT4 | 33.8 ms | 33.6 ms | 2,018 ms | 2,013 ms |

**Patched versus standard plugin** (latency reduction with all six patches):

| Model | 1,024-token text | 1,024-token query | 448x448 image | 448x448 image+text |
| --- | ---: | ---: | ---: | ---: |
| INT4 | 13.8% | 14.6% | 6.1% | 6.4% |
| INT8 | 3.2% | 3.4% | 2.7% | 3.1% |

The patches help INT4 most because the largest gain, the INT4 weight-layout
patch (opt-3), applies only to INT4 weights. The visual-normalization fusion
(opt-5) is gated by a GPU dynamic-quantization threshold that the service
leaves at its default, so it does not trigger here; the figures above were
measured the same way.

### Accuracy

- **Patched plugin:** with the INT8 model, every output was bitwise identical to
  the standard plugin. With the INT4 model, text, query and 448x448
  image/fused outputs were bitwise identical; full-resolution images changed
  slightly (cosine 0.995–0.997 against the standard plugin).
- **INT4 model:** INT4 trades accuracy for speed. Against the original FP32
  model, INT4 measured cosine 0.94–0.96 on text, query, image and fused
  inputs, against 0.987–0.999 for INT8. Validate retrieval quality on your own
  data before switching a production index to INT4. INT4 and INT8 embeddings
  are not interchangeable: re-embed the whole collection when you change the
  model.

## Use the patched image with INT8

To keep INT8 and still use the patched plugin, set `GME_PRECISION=int8` (or
unset it) before Step 3. An existing INT8
package in the `ov-models` volume is reused as is; it does not need to be
exported again.

## Switch back to the standard image

```bash
export TAG=latest
source setup.sh
# Only on the integrated GPU of an Intel Core Ultra Series 3 (Panther Lake) processor:
export OV_PERFORMANCE_MODE=LATENCY
docker compose -f docker/compose.yaml up -d --force-recreate
```

To return to INT8 as well, also set `GME_PRECISION=int8` (or unset it).
Each precision's package stays in the `ov-models` volume, so switching does not export
again.

## Troubleshooting

- **Image or image+text requests never return on a Panther Lake integrated
  GPU.** The service is running in `THROUGHPUT` mode: the GME startup log
  shows `streams=auto`, and the host
  kernel log (`sudo dmesg | grep -i xe`) shows a BCS engine reset. Export
  `OV_PERFORMANCE_MODE=LATENCY` after `source setup.sh` and recreate the
  container with `docker compose -f docker/compose.yaml up -d --force-recreate`.
- **The build runs out of memory or the host becomes unresponsive.** Limit the
  number of compile jobs, for example `--build-arg BUILD_JOBS=8`.
- **The clone or a submodule download fails.** The build needs `github.com`;
  check the proxy build arguments in Step 2.
- **`429 Too Many Requests` while resolving `ubuntu:24.04`.** Docker Hub rate
  limited the pull. Wait a few minutes and run the build again, or log in with
  `docker login`. The image tag is not updated by a failed build, so make sure
  the build ends without an error before you continue.
- **`git apply --check` fails.** The patches apply only to OpenVINO `2026.4.1`.
  Do not change the `OPENVINO_TAG`/`OPENVINO_COMMIT` build arguments.
- **The final build step fails to load the plugin.** The OpenVINO wheel and the
  plugin must come from the same release: keep `OPENVINO_VERSION` at `2026.4.1`.
- **The startup log shows the wheel's plugin build number.** The container
  was started from the standard image. Check `TAG` and run
  `docker compose -f docker/compose.yaml up -d --force-recreate` again.
- **The compiled-model cache is enabled (`OV_ENABLE_MODEL_CACHE`).** Clear
  `<EMBEDDING_OV_MODELS_DIR>/ov_cache` when switching between the standard and
  the patched image, so models are compiled again by the plugin in use.
