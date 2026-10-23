# Optimize GME on Intel GPU

This guide sets up the fastest GME configuration on an Intel GPU:

- the **INT4** GME model, `GME/gme-qwen2-vl-2b-instruct-int4`, and
- an image whose OpenVINO GPU plugin is rebuilt with six GME-specific
  optimization patches.

Both steps are optional and independent. The INT4 model runs on the standard
image, and the patched plugin also speeds up the default INT8 model. Use them
together for the largest gain. The standard image and the INT8 default remain
the recommended starting point; follow this guide when you need lower GME
latency on GPU.

## What changes

| Component | Standard | Optimized |
| --- | --- | --- |
| Model | `GME/gme-qwen2-vl-2b-instruct` (INT8) | `GME/gme-qwen2-vl-2b-instruct-int4` (INT4) |
| Image | `multimodal-embedding-serving:<tag>` | the same image plus a patched GPU plugin, tagged `gme-gpu-patch` |
| OpenVINO | wheel from `pyproject.toml` | official `openvino==2026.4.1` wheel; its GPU plugin is replaced by one built from the same release with the patches applied |

The patches change only the OpenVINO GPU plugin. Model files, service code and
the API are unchanged, and the patched image runs every other model like the
standard image does. The patches are in
[`docker/openvino-gpu-patch/patches/openvino-2026.4.1`](../../docker/openvino-gpu-patch/patches/openvino-2026.4.1/)
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
export EMBEDDING_MODEL_NAME=GME/gme-qwen2-vl-2b-instruct-int4
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
docker build -f docker/openvino-gpu-patch/Dockerfile \
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
docker compose -f docker/compose.yaml up -d --force-recreate
docker logs -f --tail=100 multimodal-embedding-serving
```

> [!IMPORTANT]
> While `TAG=gme-gpu-patch` is set, do not run `docker compose ... build` or
> `docker compose ... up --build`: they would rebuild the standard image under
> the `gme-gpu-patch` tag and overwrite the patched image. Switch back to
> `TAG=latest` before rebuilding the standard image, then repeat Step 2.

On the first start, the INT4 model is downloaded and exported to OpenVINO in
the `ov-models` volume at
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
  'cat /opt/openvino-gpu-patch/plugin.sha256; sha256sum "$(python -c "import openvino, pathlib; print(pathlib.Path(openvino.__file__).parent / \"libs\" / \"libopenvino_intel_gpu_plugin.so\")")"'
```

Both lines show the same checksum. Then check the service:

```bash
curl -fsS http://localhost:9777/health
curl -fsS http://localhost:9777/model/current
```
