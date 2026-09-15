import asyncio
import io
import json
import zipfile

import httpx
import pytest

from src.plugins.geti_plugin import GetiPlugin


def model_archive() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("models/vehicle.xml", "xml")
        archive.writestr("models/vehicle.bin", "bin")
    return stream.getvalue()


@pytest.fixture
def rest_client(monkeypatch):
    requests = []
    models = [{
        "id": "model-1", "name": "Vehicle Detector", "task": "detection",
        "architecture": "YOLOX",
        "variants": [
            {"id": "variant-fp16", "format": "openvino", "precision": "fp16"},
            {"id": "variant-int8", "format": "openvino", "precision": "int8"},
        ],
    }]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "Authorization" not in request.headers
        if request.url.path == "/api/projects":
            return httpx.Response(200, json=[{"id": "project-1", "name": "Vision"}])
        if request.url.path == "/api/projects/project-1/models":
            return httpx.Response(200, json=models)
        if request.url.path == "/api/projects/project-1/models/model-1":
            return httpx.Response(200, json=models[0])
        if request.url.path.endswith("/variants/variant-fp16/binary"):
            return httpx.Response(200, content=model_archive())
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://geti.test/api")

    async def get_client(self, session):
        session.http_client = client
        return client

    monkeypatch.setattr(GetiPlugin, "_get_http_client", get_client)
    return requests


@pytest.mark.asyncio
async def test_list_models_uses_project_model_api(rest_client):
    plugin = GetiPlugin()
    session = plugin._build_session({"GETI_HOST": "https://geti.test"})
    result = await plugin._list_models_async(session, {"precision": "FP16"})

    assert result["total"] == 1
    assert result["items"][0]["name"] == "Vehicle Detector"
    assert result["items"][0]["model_type"] == "detection"
    assert result["items"][0]["metadata"]["variants"][0]["variant_id"] == "variant-fp16"
    assert [str(request.url) for request in rest_client] == [
        "https://geti.test/api/projects",
        "https://geti.test/api/projects/project-1/models",
    ]


@pytest.mark.asyncio
async def test_list_models_applies_architecture_and_variant_filters(rest_client):
    plugin = GetiPlugin()
    session = plugin._build_session({"GETI_HOST": "https://geti.test"})

    result = await plugin._list_models_async(session, {
        "architecture": "yolox",
        "variant_id": "variant-int8",
        "precision": "INT8",
    })

    assert result["total"] == 1
    assert result["items"][0]["metadata"]["variants"][0]["variant_id"] == "variant-int8"


@pytest.mark.asyncio
async def test_download_uses_model_variant_binary_and_extracts(rest_client, tmp_path):
    plugin = GetiPlugin()
    session = plugin._build_session({"GETI_HOST": "https://geti.test"})
    download_dir = []
    path, error, ignored = await plugin.download_model_from_geti(
        session, "model-1", str(tmp_path), "Vehicle Detector",
        project_id="project-1", precision="FP16", model_format="OpenVINO",
        _model_download_dir=download_dir,
    )

    assert error is None
    assert ignored == []
    assert path == str(tmp_path / "geti" / "vehicle detector" / "fp16")
    assert (tmp_path / "geti" / "vehicle detector" / "fp16" / "vehicle.xml").read_text() == "xml"
    assert download_dir == [path]
    assert str(rest_client[-1].url) == (
        "https://geti.test/api/projects/project-1/models/model-1/variants/variant-fp16/binary"
    )


@pytest.mark.asyncio
async def test_download_unwraps_enum_precision_from_config(rest_client, tmp_path):
    """Regression test: the API's shared ``Config`` model types ``precision`` as
    the ``ModelPrecision`` (str, Enum), not a plain string. ``str(enum_member)``
    yields ``"ModelPrecision.FP16"`` rather than ``"fp16"`` on this project's
    Python version, so passing the enum straight through to variant filtering
    previously caused every variant match to fail with "Model not found",
    even though the *same* request without ``config`` succeeded.
    """
    from src.api.models import ModelPrecision

    plugin = GetiPlugin()
    result = await plugin.download(
        "Vehicle Detector", str(tmp_path),
        resolved_config={"GETI_HOST": "https://geti.test"},
        config={"model_format": "openvino", "precision": ModelPrecision.FP16},
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_list_models_sync_entrypoint_survives_repeated_thread_offload():
    """Regression test: the API layer calls the sync `list_models()` via
    `asyncio.to_thread(...)` on every request. Each call previously used two
    separate `asyncio.run()` invocations (one for the listing, one to close
    the session), which opened and closed two different event loops. httpx's
    real (socket-bound) transport is created under the first loop, so closing
    it under the second, already-different loop raised "Event loop is
    closed". `list_models()` must run the listing and the session close
    inside a single event loop.

    A real TCP server is used here (rather than `httpx.MockTransport`)
    because the mock transport bypasses the asyncio selector/transport
    machinery entirely and does not reproduce the failure.
    """
    responses = {
        "/api/projects": [{"id": "project-1", "name": "Vision"}],
        "/api/projects/project-1/models": [{
            "id": "model-1", "name": "Vehicle Detector", "task": "detection",
            "architecture": "YOLOX",
            "variants": [{"id": "variant-fp16", "format": "openvino", "precision": "fp16"}],
        }],
    }

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = await reader.readline()
        path = request_line.decode().split(" ")[1]
        while (await reader.readline()) not in (b"\r\n", b""):
            pass
        body = json.dumps(responses.get(path)).encode()
        status = "200 OK" if path in responses else "404 Not Found"
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        serve_task = asyncio.create_task(server.serve_forever())
        try:
            plugin = GetiPlugin()
            resolved_config = {"GETI_HOST": f"http://127.0.0.1:{port}"}
            for _ in range(2):
                result = await asyncio.to_thread(
                    plugin.list_models, filters={}, limit=50, offset=0, resolved_config=resolved_config,
                )
                assert result["total"] == 1
        finally:
            serve_task.cancel()


def test_geti_config_requires_only_the_server_host():
    keys = {key.name: key for key in GetiPlugin().hub_config_keys()}
    assert set(keys) == {"GETI_HOST"}
    assert keys["GETI_HOST"].required is True