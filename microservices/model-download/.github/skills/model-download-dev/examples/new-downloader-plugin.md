# Example: New Downloader Plugin

## Scenario

Add a new **downloader** plugin for an arbitrary model hub named `myhub`.

This walkthrough is intentionally generic so it can be adapted to any provider:

- SDK-based hub
- REST API client
- CLI/subprocess downloader
- authenticated or public downloads

---

## Step 1 — Create the Plugin File

Create `src/plugins/myhub_plugin.py` using the reusable structure from
[plugin-blueprint.md](./plugin-blueprint.md).

Key expectations:

- `plugin_name == "myhub"`
- `plugin_type == "downloader"`
- `can_handle()` returns `True` only for the `myhub` hub value
- `download()` creates `output_dir/myhub/<model-name>`
- the returned path is host-visible, not container-only

---

## Step 2 — Register It in `src/plugins/__init__.py`

Use the current tuple-based registration format:

```python
PLUGINS = {
    # ... existing entries ...
    "myhub": ("src.plugins.myhub_plugin", "MyHubPlugin"),
}
```

This is what the startup import loop reads when plugin loading is enabled.

---

## Step 3 — Add the Hub Enum

In `src/api/models.py`:

```python
class ModelHub(str, Enum):
    ...
    MYHUB = "myhub"
```

Without this, request validation will reject `"hub": "myhub"`.

---

## Step 4 — Add Optional Dependencies

In `pyproject.toml`:

```toml
[project.optional-dependencies]
myhub = ["myhub-sdk>=1.0"]
```

Use the real dependency set for the provider. Keep the extra name aligned with the plugin name.

---

## Step 5 — Enable Startup Activation

Update `docker/entrypoint.sh` so `--plugins myhub` works:

1. add `myhub` to `AVAILABLE_PLUGINS`
2. ensure the plugin extra can be installed for that activation path

If this step is missing, the code may exist but the plugin will not be available at runtime.

---

## Step 6 — Add Tests

Create `tests/unit/test_myhub_plugin.py`.

At minimum, cover:

- plugin properties
- `can_handle()`
- successful download
- provider error propagation
- host-path rewriting
- token/env lookup if the plugin is authenticated

See [writing-tests.md](./writing-tests.md) for concrete patterns.

---

## Step 7 — Smoke Test the Flow

Start the service:

```bash
cd microservices/model-download
source scripts/run_service.sh up --plugins myhub --model-path $PWD/models
```

Check health and plugin visibility:

```bash
curl -s http://localhost:8200/api/v1/health
curl -s http://localhost:8200/api/v1/plugins | python3 -m json.tool
```

Submit a request:

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=myhub-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "org/model-name",
        "hub": "myhub"
      }
    ]
  }'
```

If the plugin does not show up, inspect:

- `src/plugins/__init__.py`
- `docker/entrypoint.sh`
- service logs for `ImportError`
- the plugin name string across all registration points

---

## Common Mistakes

- using a registration format that does not match the current tuple-based `PLUGINS` mapping
- adding the plugin file but forgetting `ModelHub`
- forgetting `docker/entrypoint.sh`, so `--plugins myhub` never activates it
- returning a container-only path like `/opt/models/...` instead of the host-visible path
- doing blocking SDK work directly inside an async method

---

## Exit Criteria

You are done when all of these are true:

- `curl /api/v1/plugins` shows the plugin after startup
- a request with `"hub": "myhub"` is accepted
- a download job reaches `completed`
- the result contains a correct host-visible `download_path`

