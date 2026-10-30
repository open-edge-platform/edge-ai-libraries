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

### Optional: prepare the INT4 model yourself

You do not have to prepare a model: on its first start (Step 3), the service
downloads GME from Hugging Face and exports it to OpenVINO INT4 by itself.
Prepare the INT4 model yourself when the host cannot reach Hugging Face, or to
convert it once and reuse it.

Do it now, before Step 2, while `GME_PRECISION=int4` and `TAG=latest` from
Step 1 are still set. Follow
[Use a prepared GME OpenVINO model](./get-started.md#use-a-prepared-gme-openvino-model)
in this terminal, with these changes:

| Step there | What to do here |
| --- | --- |
| 1. Select the precision and build the image | Skip it: Step 1 above already built the image with these settings. |
| 2. Download the original checkpoint | Follow it as written. |
| 3. Convert it to OpenVINO | Follow it as written. It writes the model to `./gme-ov/gme-qwen2-vl-2b-instruct-openvino-int4`. |
| 4. Copy the model into the volume | Follow it as written. |
| 5. Start the service | Skip it: continue with Step 2 below, and start the service in Step 3. |

If you already have an INT4 package, for example one converted on another host,
skip steps 2 and 3 there and put it at
`./gme-ov/gme-qwen2-vl-2b-instruct-openvino-int4` before step 4. Only a package
written by [`scripts/export_gme_ov.py`](../../scripts/export_gme_ov.py) with
`GME_PRECISION=int4` works: the service needs its `gme_openvino_config.json`
and finds the model only under the `-int4` directory name. A directory without
the suffix holds the INT8 package.

The model files do not depend on the GPU plugin, so the same package works with
the standard and the patched image. In Step 3, the log then shows
`Reusing existing GME OpenVINO package` instead of an export.

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
depending on the CPU; later starts reuse the package. If you
[prepared the INT4 model yourself](#optional-prepare-the-int4-model-yourself),
the log shows `Reusing existing GME OpenVINO package` instead.
The service becomes healthy once loading finishes.

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
