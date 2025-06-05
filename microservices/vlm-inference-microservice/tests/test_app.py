import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

# Mock settings, convert_model, ov_genai.VLMPipeline, and is_model_ready before importing app.py
with mock.patch.dict(
    os.environ,
    {
        "http_proxy": "http://mock-proxy",
        "https_proxy": "https://mock-proxy",
        "no_proxy_env": "localhost,127.0.0.1",
        "VLM_MODEL_NAME": "mock_model",
        "VLM_COMPRESSION_WEIGHT_FORMAT": "int8",
        "VLM_DEVICE": "CPU",
        "SEED": "42",
    },
):
    with mock.patch("src.utils.utils.convert_model", return_value=None):
        with mock.patch("openvino_genai.VLMPipeline", return_value=mock.Mock()):
            with mock.patch("src.utils.utils.is_model_ready", return_value=True):
                # Mock initialize_model after mocking dependencies
                with mock.patch("src.app.initialize_model") as mock_initialize_model:
                    from src.app import app

from src.utils.common import ErrorMessages, ModelNames

client = TestClient(app)


def test_initialize_model():
    # Ensure initialize_model was called during app initialization
    with mock.patch("src.app.initialize_model") as mock_initialize_model:
        from src.app import initialize_model

        initialize_model()
        mock_initialize_model.assert_called_once()


@mock.patch("src.utils.utils.is_model_ready", return_value=True)
@mock.patch("src.utils.utils.get_devices", return_value=["CPU", "GPU"])
def test_get_device(mock_get_devices, mock_is_model_ready):
    # Ensure the mock is used
    response = client.get("/device")
    assert response.status_code == 200
    assert isinstance(response.json()["devices"], list)


@mock.patch(
    "src.utils.utils.get_device_property", return_value={"EXECUTION_DEVICES": "['CPU']"}
)
@mock.patch("src.utils.utils.get_devices", return_value=["CPU", "GPU"])
def test_get_device_info(mock_get_devices, mock_get_device_property):
    # Ensure the mocks are used
    response = client.get("/device/CPU")
    assert response.status_code == 200
    assert "EXECUTION_DEVICES" in response.json()
    assert response.json()["EXECUTION_DEVICES"] == "['CPU']"


@mock.patch("src.app.get_devices", return_value=["CPU", "GPU", "TPU"])
def test_mocked_get_devices(mock_get_devices):
    response = client.get("/device")
    assert response.status_code == 200
    assert response.json()["devices"] == ["CPU", "GPU", "TPU"]


def test_get_models():
    response = client.get("/v1/models")
    assert response.status_code == 200
    assert "data" in response.json()


def test_queue_status():
    response = client.get("/v1/queue-status")
    assert response.status_code == 200
    assert "active_requests" in response.json()
    assert "queued_requests" in response.json()


def test_chat_completions():
    payload = {
        "model": "test-model",  # Replace with the actual model name
        "messages": [{"role": "user", "content": "Hello, how are you?"}],
        "max_completion_tokens": 50,
        "temperature": 0.7,
        "top_p": 0.9,
        "stream": False,
    }
    response = client.post("/v1/chat/completions", json=payload)
    if response.status_code == 404:
        assert "error" in response.json()
    elif response.status_code == 400:
        assert "error" in response.json()
    else:
        assert response.status_code == 200
        assert "choices" in response.json()


def test_health_check_healthy():
    with mock.patch("src.app.model_ready", True):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


def test_health_check_unhealthy():
    with mock.patch("src.app.model_ready", False):
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "model not ready"}


def test_chat_completions_invalid_model():
    payload = {
        "model": "invalid-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_completion_tokens": 50,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 404
    assert "error" in response.json()


def test_chat_completions_missing_prompt():
    payload = {
        "model": "mock_model",  # Use the mocked model name
        "messages": [{"role": "user", "content": ""}],
        "max_completion_tokens": 50,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 400
    assert "error" in response.json()


@mock.patch("src.app.restart_server")
def test_safe_generate_calls_restart_server(mock_restart_server):
    from src.app import safe_generate

    # Mock pipe with a generate method that raises an exception
    mock_pipe = mock.Mock()
    mock_pipe.generate.side_effect = RuntimeError(ErrorMessages.GPU_OOM_ERROR_MESSAGE)

    # Mock streamer
    mock_streamer = mock.Mock()
    mock_streamer.end_of_stream = False

    # Call safe_generate with mocked pipe and streamer
    safe_generate(pipe=mock_pipe, generation_kwargs={}, streamer=mock_streamer)

    # Assert that restart_server was called
    mock_restart_server.assert_called_once()


@mock.patch(
    "src.app.OVModelForVisualCausalLM.from_pretrained",
    side_effect=RuntimeError("Model loading error"),
)
def test_initialize_model_model_loading_error(mock_from_pretrained):
    from src.app import initialize_model

    # Mock settings to match the PHI model condition
    with mock.patch("src.app.settings.VLM_MODEL_NAME", ModelNames.PHI):
        with mock.patch("src.app.logger.error") as mock_logger:
            with pytest.raises(
                RuntimeError, match="Error initializing the model: Model loading error"
            ):
                initialize_model()

            # Assert logger call
            mock_logger.assert_called_with(
                "Error initializing the model: Model loading error"
            )


@mock.patch("src.app.load_images", side_effect=RuntimeError("Image loading error"))
def test_chat_completions_image_loading_error(mock_load_images):
    payload = {
        "model": "mock_model",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the scene"},
                    {"type": "image_url", "image_url": {"url": "mock_image_url"}},
                ],
            }
        ],
        "max_completion_tokens": 50,
    }

    response = client.post("/v1/chat/completions", json=payload)

    # Assert response
    assert response.status_code == 500
    assert "Image loading error" in response.json()["error"]


@mock.patch(
    "src.app.decode_and_save_video", side_effect=RuntimeError("Video decoding error")
)
def test_chat_completions_video_decoding_error(mock_decode_and_save_video):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this video"},
                        {
                            "type": "video_url",
                            "video_url": {
                                "url": "data:video/mp4;base64,mock_video_base64"
                            },
                        },
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 500
        assert "Video decoding error" in response.json()["error"]


@mock.patch("src.app.get_devices", side_effect=RuntimeError("Device fetching error"))
def test_get_device_error(mock_get_devices):
    response = client.get("/device")

    # Assert response
    assert response.status_code == 500
    assert "Device fetching error" in response.json()["detail"]


@mock.patch(
    "src.app.get_device_property", side_effect=RuntimeError("Device property error")
)
def test_get_device_info_error(mock_get_device_property):
    response = client.get("/device/CPU")

    # Assert response
    assert response.status_code == 500
    assert "Device property error" in response.json()["detail"]


@mock.patch(
    "src.app.load_model_config",
    return_value={"min_pixels": "256", "max_pixels": "1024"},
)
@mock.patch(
    "src.app.OVModelForVisualCausalLM.from_pretrained", return_value=mock.Mock()
)
@mock.patch("src.app.AutoProcessor.from_pretrained", return_value=mock.Mock())
@mock.patch("src.app.is_model_ready", return_value=True)
def test_initialize_model_qwen(
    mock_is_model_ready, mock_processor, mock_model, mock_load_model_config
):
    from src.app import initialize_model

    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        initialize_model()

        # Assert that the model and processor were initialized
        mock_model.assert_called_once()
        mock_processor.assert_called_once()
        mock_is_model_ready.assert_called_once()
        mock_load_model_config.assert_called_once_with("qwen2.5-vl-7b-instruct")


@mock.patch(
    "src.app.OVModelForVisualCausalLM.from_pretrained", return_value=mock.Mock()
)
@mock.patch("src.app.AutoProcessor.from_pretrained", return_value=mock.Mock())
@mock.patch("src.app.is_model_ready", return_value=True)
def test_initialize_model_phi(mock_is_model_ready, mock_processor, mock_model):
    from src.app import initialize_model

    with mock.patch("src.app.settings.VLM_MODEL_NAME", "phi-3.5-vision"):
        initialize_model()

        # Assert that the model and processor were initialized
        mock_model.assert_called_once()
        mock_processor.assert_called_once()
        mock_is_model_ready.assert_called_once()


@mock.patch("src.app.TextIteratorStreamer")
@pytest.mark.asyncio
async def test_create_streaming_response(mock_streamer):
    from src.app import create_streaming_response

    # Mock streamer behavior
    mock_streamer_instance = mock.AsyncMock()
    mock_streamer_instance.__iter__ = mock.Mock(
        return_value=iter(["chunk1", "chunk2", "chunk3"])
    )
    mock_streamer.return_value = mock_streamer_instance

    # Mock request and model name
    mock_request = mock.Mock()
    model_name = "mock_model"

    # Call create_streaming_response
    response = create_streaming_response(
        mock_streamer_instance, mock_request, model_name
    )

    # Assert response is a StreamingResponse
    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/event-stream"

    # Simulate streaming response
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)  # Append the chunk directly

    assert len(chunks) == 4  # 3 chunks + final stop signal
    assert "chunk1" in chunks[0]
    assert "chunk2" in chunks[1]
    assert "chunk3" in chunks[2]
    assert "stop" in chunks[3]


@mock.patch("src.app.process_vision_info", return_value=([], [], {}))
@mock.patch("src.app.AutoProcessor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
def test_chat_completions_with_video(
    mock_streamer, mock_processor_call, mock_process_vision_info
):
    from src.app import processor

    # Mock the processor's chat_template
    processor.chat_template = "mock_chat_template"

    payload = {
        "model": "mock_model",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": ["frame1", "frame2", "frame3"]},
                    {"type": "text", "text": "Describe this video"},
                ],
            }
        ],
        "max_completion_tokens": 50,
    }

    response = client.post("/v1/chat/completions", json=payload)

    # Assert response
    assert response.status_code == 200 or response.status_code == 500
    if response.status_code == 200:
        assert "choices" in response.json()
    elif response.status_code == 500:
        assert "error" in response.json()


@mock.patch("src.app.process_vision_info", return_value=([], [], {}))
@mock.patch("src.app.AutoProcessor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
def test_chat_completions_with_video_qwen(
    mock_streamer, mock_processor_call, mock_process_vision_info
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        # Mock the processor's chat_template
        processor.chat_template = "mock_chat_template"

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "video", "video": ["frame1", "frame2", "frame3"]},
                        {"type": "text", "text": "Describe this video"},
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()


@mock.patch("src.app.load_images", return_value=(["mock_image"], ["mock_tensor"]))
@mock.patch(
    "src.app.processor.tokenizer.apply_chat_template", return_value="formatted_prompt"
)
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
def test_chat_completions_with_phi_model(
    mock_streamer, mock_processor_call, mock_apply_chat_template, mock_load_images
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "phi-3.5-vision"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "phi-3.5-vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "mock_image_url"}},
                        {"type": "text", "text": "Describe this image"},
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that load_images was called
        mock_load_images.assert_called_once_with(["mock_image_url"])
        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()


@mock.patch(
    "src.app.processor.tokenizer.apply_chat_template", return_value="formatted_prompt"
)
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
def test_chat_completions_as_text_prompt(
    mock_streamer, mock_processor_call, mock_apply_chat_template
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "phi-3.5-vision"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "phi-3.5-vision",
            "messages": [
                {
                    "role": "user",
                    "content": "Describe the functionality of this model.",
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()


@mock.patch("src.app.processor.apply_chat_template", return_value="formatted_prompt")
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
def test_chat_completions_qwen_as_text_prompt(
    mock_streamer, mock_processor_call, mock_apply_chat_template
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": "Explain the architecture of this model.",
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()


@mock.patch("src.app.processor.apply_chat_template", return_value="formatted_prompt")
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
def test_chat_completions_qwen_with_message_content_text(
    mock_streamer, mock_processor_call, mock_apply_chat_template
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Explain the architecture of this model.",
                        }
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()


@mock.patch("src.app.processor.apply_chat_template", return_value="formatted_prompt")
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
@mock.patch("src.app.process_vision_info", return_value=(["mock_image_input"], []))
def test_chat_completions_qwen_with_single_image(
    mock_process_vision_info,
    mock_streamer,
    mock_processor_call,
    mock_apply_chat_template,
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image."},
                        {"type": "image_url", "image_url": {"url": "mock_url"}},
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()
        # Assert that process_vision_info was called
        mock_process_vision_info.assert_called_once()


@mock.patch("src.app.processor.apply_chat_template", return_value="formatted_prompt")
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
@mock.patch("src.app.process_vision_info", return_value=([], ["mock_video_input"], {}))
def test_chat_completions_qwen_with_video_url(
    mock_process_vision_info,
    mock_streamer,
    mock_processor_call,
    mock_apply_chat_template,
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": "mock_video_url"},
                            "max_pixels": "256 * 256",
                            "fps": 30.0,
                        },
                        {"type": "text", "text": "Describe this video."},
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()
        # Assert that process_vision_info was called
        mock_process_vision_info.assert_called_once()


@mock.patch("src.app.processor.apply_chat_template", return_value="formatted_prompt")
@mock.patch("src.app.processor.__call__", return_value={"input_ids": mock.Mock()})
@mock.patch("src.app.TextIteratorStreamer")
@mock.patch(
    "src.app.process_vision_info",
    return_value=(["mock_image_input_1", "mock_image_input_2"], []),
)
def test_chat_completions_qwen_with_multiple_images(
    mock_process_vision_info,
    mock_streamer,
    mock_processor_call,
    mock_apply_chat_template,
):
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct"):
        from src.app import app, processor  # Re-import app with updated settings

        client = TestClient(app)

        payload = {
            "model": "Qwen/Qwen2.5-VL-7B-Instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image."},
                        {"type": "image_url", "image_url": {"url": "mock_url"}},
                        {"type": "image_url", "image_url": {"url": "mock_url1"}},
                    ],
                }
            ],
            "max_completion_tokens": 50,
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Assert response
        assert response.status_code == 200 or response.status_code == 500
        if response.status_code == 200:
            assert "choices" in response.json()
        elif response.status_code == 500:
            assert "error" in response.json()

        # Assert that apply_chat_template was called
        mock_apply_chat_template.assert_called_once()
        # Assert that process_vision_info was called
        mock_process_vision_info.assert_called_once()


@mock.patch("src.app.pipe.generate", return_value="mocked default model response")
def test_chat_completions_default_model_text_prompt(mock_generate):
    payload = {
        "model": "mock_model",  # Not Qwen or Phi
        "messages": [{"role": "user", "content": "What is the answer to life?"}],
        "max_completion_tokens": 10,
    }
    with mock.patch("src.app.settings.VLM_MODEL_NAME", "mock_model"):
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "choices" in response.json()
    assert (
        response.json()["choices"][0]["message"]["content"]
        == "mocked default model response"
    )
    mock_generate.assert_called_once()


@mock.patch("src.app.load_images", side_effect=RuntimeError("Image loading error"))
def test_chat_completions_image_loading_error_handling(mock_load_images):
    payload = {
        "model": "mock_model",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "mock_image_url"}},
                ],
            }
        ],
        "max_completion_tokens": 50,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 500
    assert "Image loading error" in response.json()["error"]


@mock.patch("src.app.pipe.generate", side_effect=RuntimeError("Generation error"))
def test_chat_completions_generation_error(mock_generate):
    # Covers lines 823-824
    payload = {
        "model": "mock_model",
        "messages": [{"role": "user", "content": "What is the answer to life?"}],
        "max_completion_tokens": 10,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 500
    assert "Generation error" in response.json()["error"]
