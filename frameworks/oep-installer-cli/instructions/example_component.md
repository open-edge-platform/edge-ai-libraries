# Component spec: ollama

<!-- EXAMPLE ONLY – this file illustrates the spec format.
     The component name `ollama` does not collide with any existing module.
     Remove this banner when writing a real spec.                          -->

## Purpose

[Ollama](https://ollama.com) is a lightweight runtime for running large
language models (LLMs) locally.  It exposes an OpenAI-compatible REST API on
port 11434, supports GPU-accelerated inference via the Intel NPU or GPU
drivers, and bundles common open-weight models (Llama 3, Mistral, Phi-3,
etc.).  In an Open Edge Platform context it provides the on-device inference
back-end consumed by applications such as visual-search or chatbot services.

## Installation order / category

**Proposed order number**: `85` (range: 60–89 middle-level libraries / microservices)

## Dependencies

- `git`
- `curl`
- `docker`
- `gpu`

## Installation steps

**Upstream repository**: `https://github.com/ollama/ollama`  
**Version / tag**: `v0.5.13`

1. Pull the official Docker image `ollama/ollama:0.5.13` (avoids a large
   binary download and keeps updates reproducible).
2. Create a persistent volume `ollama_models` to store downloaded model blobs
   between container restarts.
3. Render a `docker-compose.yml` in `$(ensure_project_path)/ollama/` that
   mounts the GPU device (use `ensure_select_device` to pick the right
   `/dev/dri/renderD*` node) and binds port 11434.
4. Pull a default model (`llama3.2:3b`) so the service is usable immediately
   after install.

## Verification

`verify_ollama` should check that the Docker image `ollama/ollama:0.5.13`
exists locally:

```bash
docker image inspect ollama/ollama:0.5.13 > /dev/null 2>&1
```

## Start / stop behaviour

**Start**: `docker compose -f $(ensure_project_path)/ollama/docker-compose.yml up -d`  
**Stop**:  `docker compose -f $(ensure_project_path)/ollama/docker-compose.yml down`  
**UI entrypoint**: `http://$(ensure_ip):11434` (REST API; use with OpenWebUI)

After starting, the install function should run a basic liveness check:

```bash
curl -sf http://localhost:11434/api/tags > /dev/null
```

## Ports

| Port  | Protocol | Purpose                        |
|-------|----------|--------------------------------|
| 11434 | TCP      | Ollama REST API (OpenAI compat)|

## Removal

1. Call `debian_85_stop_ollama` (with `|| true`).
2. Remove the Docker volume `ollama_models`.
3. Remove the Docker image `ollama/ollama:0.5.13`.
4. Delete the workspace directory `$(ensure_project_path)/ollama`.

## Reset flag behaviour

`--reset-ollama` should delete the workspace and all downloaded model blobs
(the `ollama_models` Docker volume), then reinstall and re-pull the default
model from scratch.

## License requirements

**Requires click-through**: no
