from src.utils.data_models import (
    ChatCompletionChoice,
    ChatCompletionDelta,
    ChatCompletionResponse,
    ChatCompletionStreamingChoice,
    ChatCompletionStreamingResponse,
    ChatRequest,
    ChatUsageStats,
    Message,
    MessageContentImageUrl,
    MessageContentText,
    MessageContentVideo,
    MessageContentVideoUrl,
    ModelData,
    ModelsResponse,
)


def test_chat_request_validation():
    message = Message(
        role="user",
        content=[MessageContentText(type="text", text="Describe this image.")],
    )
    request = ChatRequest(
        messages=[message], model="test-model", max_completion_tokens=100
    )
    assert request.model == "test-model"
    assert len(request.messages) == 1
    assert request.messages[0].role == "user"


def test_message_content_image_url():
    content = MessageContentImageUrl(
        type="image_url", image_url={"url": "http://example.com/image.jpg"}
    )
    assert content.type == "image_url"
    assert content.image_url["url"] == "http://example.com/image.jpg"


def test_message_content_video():
    content = MessageContentVideo(type="video", video=["frame1", "frame2"])
    assert content.type == "video"
    assert content.video == ["frame1", "frame2"]


def test_message_content_video_url():
    content = MessageContentVideoUrl(
        type="video_url",
        video_url={"url": "http://example.com/video.mp4"},
        max_pixels=1080,
        fps=30.0,
    )
    assert content.type == "video_url"
    assert content.video_url["url"] == "http://example.com/video.mp4"
    assert content.max_pixels == 1080
    assert content.fps == 30.0


def test_chat_completion_delta():
    delta = ChatCompletionDelta(role="assistant", content="Hello!")
    assert delta.role == "assistant"
    assert delta.content == "Hello!"


def test_chat_usage_stats():
    stats = ChatUsageStats(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        tps=2.5,
        time_to_first_token=0.1,
        latency=0.5,
        completion_tokens_details={"details": "test"},
    )
    assert stats.prompt_tokens == 10
    assert stats.completion_tokens == 20
    assert stats.total_tokens == 30
    assert stats.tps == 2.5
    assert stats.time_to_first_token == 0.1
    assert stats.latency == 0.5
    assert stats.completion_tokens_details["details"] == "test"


def test_chat_completion_choice():
    delta = ChatCompletionDelta(role="assistant", content="Hello!")
    choice = ChatCompletionChoice(index=0, message=delta, finish_reason="stop")
    assert choice.index == 0
    assert choice.message.role == "assistant"
    assert choice.finish_reason == "stop"


def test_chat_completion_response():
    delta = ChatCompletionDelta(role="assistant", content="Hello!")
    choice = ChatCompletionChoice(index=0, message=delta, finish_reason="stop")
    response = ChatCompletionResponse(
        id="response-1",
        created=1234567890,
        model="test-model",
        choices=[choice],
        usage=None,
    )
    assert response.id == "response-1"
    assert response.created == 1234567890
    assert response.model == "test-model"
    assert len(response.choices) == 1


def test_chat_completion_streaming_choice():
    delta = ChatCompletionDelta(role="assistant", content="Hello!")
    streaming_choice = ChatCompletionStreamingChoice(
        index=0, delta=delta, finish_reason="stop"
    )
    assert streaming_choice.index == 0
    assert streaming_choice.delta.role == "assistant"
    assert streaming_choice.finish_reason == "stop"


def test_chat_completion_streaming_response():
    delta = ChatCompletionDelta(role="assistant", content="Hello!")
    streaming_choice = ChatCompletionStreamingChoice(
        index=0, delta=delta, finish_reason="stop"
    )
    streaming_response = ChatCompletionStreamingResponse(
        id="stream-response-1",
        created=1234567890,
        model="test-model",
        system_fingerprint="fingerprint-1",
        choices=[streaming_choice],
    )
    assert streaming_response.id == "stream-response-1"
    assert streaming_response.created == 1234567890
    assert streaming_response.model == "test-model"
    assert streaming_response.system_fingerprint == "fingerprint-1"
    assert len(streaming_response.choices) == 1


def test_model_data():
    model_data = ModelData(id="model-1", created=1234567890, owned_by="owner-1")
    assert model_data.id == "model-1"
    assert model_data.created == 1234567890
    assert model_data.owned_by == "owner-1"


def test_models_response():
    model_data = ModelData(id="model-1", created=1234567890, owned_by="owner-1")
    models_response = ModelsResponse(object="list", data=[model_data])
    assert models_response.object == "list"
    assert len(models_response.data) == 1
    assert models_response.data[0].id == "model-1"
