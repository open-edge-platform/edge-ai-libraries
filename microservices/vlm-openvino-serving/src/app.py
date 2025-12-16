# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import copy
import os
import sys
import time
import uuid
import warnings
from contextlib import asynccontextmanager
from multiprocessing import Manager
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, Callable, List, Optional, Union
from datetime import datetime, timezone

import openvino_genai as ov_genai
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_utils.tasks import repeat_every
from optimum.intel.openvino import OVModelForVisualCausalLM
from qwen_vl_utils import process_vision_info
from src.utils.common import ErrorMessages, ModelNames, logger, settings
from src.utils.data_models import (
    ChatCompletionChoice,
    ChatCompletionDelta,
    ChatCompletionResponse,
    ChatCompletionStreamingChoice,
    ChatCompletionStreamingResponse,
    ChatRequest,
    ChatUsageStats,
    MessageContentImageUrl,
    MessageContentText,
    MessageContentVideo,
    MessageContentVideoUrl,
    ModelsResponse,
    TelemetryListResponse,
    TelemetryMetrics,
    TelemetryRequestMetadata,
    TelemetryRecord as TelemetryRecordModel,
)
from src.utils.utils import (
    convert_model,
    convert_qwen_image_inputs,
    convert_qwen_video_inputs,
    convert_frame_urls_to_video_tensors,
    extract_qwen_video_frames,
    decode_and_save_video,
    get_best_video_backend,
    get_device_property,
    get_devices,
    is_model_ready,
    load_images,
    load_model_config,
    model_supports_video,
    setup_seed,
    validate_video_inputs,
)
from src.utils.telemetry import build_usage_and_telemetry
from src.utils.telemetry_store import telemetry_store
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import StreamingResponse
from transformers import AutoProcessor, AutoTokenizer, TextIteratorStreamer

# Suppress specific warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)


manager = Manager()
active_requests = manager.Value("i", 0)
queued_requests = manager.Value("i", 0)
request_lock = manager.Lock()

QWEN_FALLBACK_VIDEO_FRAME_LIMIT = int(os.getenv("QWEN_VIDEO_FRAME_LIMIT", "12"))


class QueueStreamer:
    """Simple queue-backed streamer compatible with ov_genai pipelines."""

    def __init__(self):
        self._queue = Queue()
        self._sentinel = object()
        self.perf_metrics = None

    def __call__(self, text: str):
        if text:
            self._queue.put(text)

    def __iter__(self):
        while True:
            chunk = self._queue.get()
            if chunk is self._sentinel:
                break
            yield chunk

    def end(self):
        self._queue.put(self._sentinel)


def extract_response_text(result) -> str:
    """Return the first decoded text from a VLM result if available."""
    if hasattr(result, "texts") and getattr(result, "texts"):
        return result.texts[0]
    return str(result)


def run_generation(pipe, generation_kwargs, streamer):
    """Invoke pipeline generation and ensure streamer termination."""
    result = None
    try:
        result = pipe.generate(**generation_kwargs)
        if hasattr(streamer, "perf_metrics") and result is not None:
            streamer.perf_metrics = getattr(result, "perf_metrics", None)
    except Exception as e:
        logger.error(f"Exception in thread during generation: {e}")
        if ErrorMessages.GPU_OOM_ERROR_MESSAGE in str(e):
            logger.error("Detected GPU out-of-memory error, restarting server...")
            restart_server()
    finally:
        if hasattr(streamer, "end"):
            streamer.end()


def launch_streaming_generation(pipe, generation_kwargs):
    """Start a background thread for streaming generation."""
    streamer = QueueStreamer()
    streaming_kwargs = dict(generation_kwargs)
    streaming_kwargs["streamer"] = streamer
    thread = Thread(target=run_generation, args=(pipe, streaming_kwargs, streamer))
    thread.daemon = True
    thread.start()
    return streamer, thread


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None
    """

    @repeat_every(seconds=2)
    async def log_request_counts():
        if active_requests.value > 0 or queued_requests.value > 0:
            logger.info(
                f"Active requests: {active_requests.value}, Queued requests: {queued_requests.value}"
            )

    log_task = asyncio.create_task(log_request_counts())
    yield
    log_task.cancel()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("VLM_CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=os.getenv("VLM_CORS_ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("VLM_CORS_ALLOW_HEADERS", "*").split(","),
)


class RequestQueueMiddleware(BaseHTTPMiddleware):
    """
    Middleware to manage request queuing and active request tracking.
    """

    def __init__(self, app):
        """
        Initialize the middleware.

        Args:
            app: The FastAPI application instance.
        """
        super().__init__(app)
        logger.info(f"RequestQueueMiddleware initialized in process: {os.getpid()}")

    async def dispatch(self, request: Request, call_next):
        """
        Handle incoming requests and manage the request queue.

        Args:
            request (Request): The incoming HTTP request.
            call_next: The next middleware or endpoint to call.

        Returns:
            Response: The HTTP response.
        """
        if request.url.path == "/v1/chat/completions":
            method = request.method
            url = request.url
            headers = dict(request.headers)
            query_params = dict(request.query_params)
            body = await request.body()  # Read the body (if applicable)

            # Log the complete request details
            logger.debug(f"Request Method: {method}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request Headers: {headers}")
            logger.debug(f"Request Query Params: {query_params}")
            logger.debug(f"Request Body: {body.decode('utf-8') if body else 'No Body'}")
            with request_lock:
                queued_requests.value += 1
                logger.info(
                    f"Queued requests incremented: {queued_requests.value} (Process: {os.getpid()})"
                )
            try:
                with request_lock:
                    active_requests.value += 1
                    queued_requests.value -= 1
                    logger.info(
                        f"Active requests incremented: {active_requests.value}, Queued requests decremented: {queued_requests.value} (Process: {os.getpid()})"
                    )
                response = await call_next(request)
            finally:
                with request_lock:
                    active_requests.value -= 1
                    logger.info(
                        f"Active requests decremented: {active_requests.value} (Process: {os.getpid()})"
                    )
        else:
            response = await call_next(request)
        return response


app.add_middleware(RequestQueueMiddleware)


@app.get("/v1/queue-status")
async def queue_status():
    """
    Get the current status of the request queue.

    Returns:
        JSONResponse: A JSON response containing the number of active and queued requests.
    """
    with request_lock:
        active = active_requests.value
        queued = queued_requests.value
    logger.info(
        f"Queue status - Active requests: {active}, Queued requests: {queued} (Process: {os.getpid()})"
    )
    return JSONResponse(
        status_code=200,
        content={
            "active_requests": active,
            "queued_requests": queued,
        },
    )



model_ready = False
pipe: Optional[Any] = None
processor: Any = None
model_dir = None
model_config = None


def cleanup_pipeline_state():
    """Release any cached runtime state held by the global pipeline."""
    global pipe
    if pipe is None:
        return

    cleanup_methods = (
        "clear_requests",
        "reset_state",
        "reset",
        "release_kv_cache",
        "clear_cache",
    )
    for method in cleanup_methods:
        if hasattr(pipe, method):
            try:
                getattr(pipe, method)()
                logger.debug(f"Pipeline state cleared using '{method}'.")
                return
            except Exception as exc:
                logger.warning(f"Failed to run pipeline cleanup via '{method}': {exc}")
    logger.debug("No cleanup method available on pipeline instance.")


def wait_for_generation_thread(thread: Optional[Thread], timeout: float = 2.0):
    """Join a generation thread to make sure resources are released."""
    if thread is None:
        return
    if not thread.is_alive():
        return
    thread.join(timeout=timeout)
    if thread.is_alive():
        logger.warning("Generation thread did not terminate within timeout.")


def restart_server():
    """
    Restart the API server.

    Raises:
        RuntimeError: If the server fails to restart.
    """
    try:
        logger.info("Restarting the API server...")
        os.execv(
            sys.executable, ["python"] + sys.argv
        )  # Restart the current Python script
    except Exception as e:
        logger.error(f"Failed to restart the server: {e}")
        raise RuntimeError(f"Failed to restart the server: {e}")


def log_telemetry(context: str, usage, telemetry):
    """Log collected telemetry/usage data for observability."""
    if telemetry is None and usage is None:
        return
    logger.info(
        "Telemetry (%s): usage=%s telemetry=%s",
        context,
        usage.model_dump() if usage else None,
        telemetry.model_dump() if telemetry else None,
    )


def safe_generate(pipe, generation_kwargs, streamer):
    """Run HF-based generation and restart the service on GPU OOM."""

    try:
        pipe.generate(**generation_kwargs)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error(f"Exception in thread during generation: {exc}")
        setattr(streamer, "end_of_stream", True)
        if ErrorMessages.GPU_OOM_ERROR_MESSAGE in str(exc):
            logger.error("Detected GPU out-of-memory error, restarting server...")
            restart_server()


# Initialize the model
def initialize_model():
    """
    Initialize the model by loading it and setting up the processor.

    Raises:
        RuntimeError: If there is an error during model initialization.
    """
    global model_ready
    global pipe, processor, model_dir, model_config
    model_name = settings.VLM_MODEL_NAME
    model_dir = Path(model_name.split("/")[-1])
    model_dir = Path("ov-model") / model_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    weight = settings.VLM_COMPRESSION_WEIGHT_FORMAT.lower()
    model_dir = model_dir / weight
    logger.info(f"Model_name: {model_name} \b Compression_Weight_Format: {weight}")

    try:
        if not model_dir.exists():
            convert_model(
                model_name,
                str(model_dir),
                model_type="vlm",
                weight_format=weight,
            )
    except Exception as e:
        logger.error(f"Error initializing the model: {e}")
        raise RuntimeError(f"Error initializing the model: {e}")

    try:
        model_config = load_model_config(model_name.split("/")[-1].lower())
        ov_config = settings.get_ov_config_dict()
        logger.debug(f"Using OpenVINO configuration: {ov_config}")
        if ModelNames.SMOLVLM in model_name.lower():
            pipe = OVModelForVisualCausalLM.from_pretrained(
                model_dir,
                device=settings.VLM_DEVICE.upper(),
                trust_remote_code=True,
                use_cache=False,
                ov_config=ov_config,
            )
            processor = AutoProcessor.from_pretrained(
                model_name, trust_remote_code=True
            )
        else:
            pipe = ov_genai.VLMPipeline(
                model_dir,
                device=settings.VLM_DEVICE.upper(),
                **ov_config,
            )

            if ModelNames.PHI in model_name.lower():
                processor = AutoProcessor.from_pretrained(
                    model_name, trust_remote_code=True
                )
            elif ModelNames.QWEN in model_name.lower():
                if not model_config:
                    raise RuntimeError("Model configuration is empty or invalid.")
                processor = AutoProcessor.from_pretrained(
                    model_dir,
                    trust_remote_code=True,
                    min_pixels=int(eval(model_config.get("min_pixels"))),
                    max_pixels=int(eval(model_config.get("max_pixels"))),
                )
            else:
                processor = None  # No processor needed for this case
        model_ready = is_model_ready(model_dir)
        logger.debug("Model is ready")
    except Exception as e:
        logger.error(f"Error initializing the model: {e}")
        raise RuntimeError(f"Error initializing the model: {e}")


# Initialize the model to create global objects of processor, model, model_ready
initialize_model()


def create_streaming_response(
    streamer,
    request,
    model_name,
    *,
    on_complete: Optional[Callable[[], None]] = None,
    generation_thread: Optional[Thread] = None,
    telemetry_callback: Optional[
        Callable[[str, Optional[ChatUsageStats], Optional[TelemetryMetrics], Optional[str]], None]
    ] = None,
):
    """
    Create a StreamingResponse for the given streamer.

    Args:
        streamer: The streamer to handle output tokens.
        request: The incoming request.
        model_name: The name of the model.

    Returns:
        StreamingResponse: The streaming response.
    """

    async def event_stream():
        buffer = ""
        completion_id = str(uuid.uuid4())
        telemetry_dispatched = False
        try:
            for new_text in streamer:
                buffer += new_text
                logger.debug(new_text)
                yield (
                    f"""data: {ChatCompletionStreamingResponse(
                        id=completion_id,
                        created=int(time.time()),
                        model=model_name,
                        system_fingerprint=f"fp_{completion_id}",
                        choices=[
                            ChatCompletionStreamingChoice(
                                index=0,
                                delta=ChatCompletionDelta(
                                    role="assistant", content=new_text
                                ),
                                finish_reason=None,
                            )
                        ],
                    ).model_dump_json()}\n\n"""
                )
            usage, telemetry = build_usage_and_telemetry(
                getattr(streamer, "perf_metrics", None)
            )
            log_telemetry("stream", usage, telemetry)
            if telemetry_callback and not telemetry_dispatched:
                telemetry_callback("success", usage, telemetry, None)
                telemetry_dispatched = True
            yield (
                f"""data: {ChatCompletionStreamingResponse(
                    id=completion_id,
                    created=int(time.time()),
                    model=model_name,
                    system_fingerprint=f"fp_{completion_id}",
                    choices=[
                        ChatCompletionStreamingChoice(
                            index=0,
                            delta={},
                            finish_reason="stop",
                            usage=usage,
                        )
                    ],
                    telemetry=telemetry,
                ).model_dump_json()}\n\n"""
            )
        except Exception as exc:
            if telemetry_callback and not telemetry_dispatched:
                telemetry_callback("server_error", None, None, str(exc))
                telemetry_dispatched = True
            raise
        finally:
            wait_for_generation_thread(generation_thread)
            if on_complete:
                on_complete()

    return StreamingResponse(
        event_stream(),
        headers={"Content-Type": "text/event-stream"},
        status_code=200,
        media_type="text/event-stream",
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """
    Handle chat completion requests.

    Args:
        request (ChatRequest): The chat request containing messages, model, and generation parameters.

    Returns:
        JSONResponse or StreamingResponse: The chat completion response.
    """
    temp_video_path = None  # Track the temporary video file path
    cleanup_deferred = False
    telemetry_request_id = str(uuid.uuid4())
    telemetry_recorded = False
    try:
        image_urls: List[str] = []
        video_frames: List[str] = []
        video_frame_groups: List[List[str]] = []
        video_url: Optional[str] = None
        prompt: Optional[str] = None
        max_pixels: Optional[Union[int, str]] = None
        fps: Optional[float] = None

        def build_request_metadata() -> TelemetryRequestMetadata:
            """Capture request statistics (message/media counts, params) for storage."""
            media_summary = {
                "images": len(image_urls),
                "video_frames": len(video_frames),
                "video_frame_groups": len(video_frame_groups),
                "video_urls": 1 if video_url else 0,
                "native_video_frames": sum(len(group) for group in video_frame_groups),
            }
            media_summary = {k: v for k, v in media_summary.items() if v}
            request_params = request.model_dump(exclude={"messages"})
            return TelemetryRequestMetadata(
                message_count=len(request.messages),
                media=media_summary,
                parameters=request_params,
            )

        def persist_telemetry(status: str, usage, telemetry, error: Optional[str]):
            """Append a telemetry record exactly once for the current request lifecycle."""
            nonlocal telemetry_recorded
            if telemetry_recorded:
                return
            try:
                timestamp = (
                    datetime.now(timezone.utc)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
                record = TelemetryRecordModel(
                    id=telemetry_request_id,
                    timestamp=timestamp,
                    status=status,
                    request=build_request_metadata(),
                    usage=usage,
                    telemetry=telemetry,
                    error=(str(error)[:512] if error else None),
                )
                telemetry_store.append(record.model_dump())
                telemetry_recorded = True
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Failed to persist telemetry record: %s", exc)

        # Use the provided seed if available, otherwise use the default seed from settings
        seed = request.seed if request.seed is not None else settings.SEED
        setup_seed(seed)

        global pipe, processor, model_dir, model_config
        logger.info("Received a chat completion request.")
        logger.debug(f"chat request: {request}")

        # Process the request and generate a response
        if request.model != settings.VLM_MODEL_NAME:
            logger.info(
                f"Requested model {request.model} does not match the configured model {settings.VLM_MODEL_NAME}."
            )
            error_message = f"Model {request.model} does not exist"
            persist_telemetry("client_error", None, None, error_message)
            return JSONResponse(
                status_code=404,
                content={"error": error_message},
            )

        # Find the last message with role == "user"
        last_user_message = next(
            (
                message
                for message in reversed(request.messages)
                if message.role == "user"
            ),
            None,
        )

        model_name_lower = settings.VLM_MODEL_NAME.lower()
        is_qwen_model = ModelNames.QWEN in model_name_lower
        supports_native_video = model_supports_video(model_name_lower)

        if last_user_message:
            if isinstance(last_user_message.content, str):
                logger.debug(f"content: {last_user_message.content}")
                prompt = last_user_message.content
            else:
                for content in last_user_message.content:
                    error = validate_video_inputs(content, settings.VLM_MODEL_NAME)
                    if error:
                        persist_telemetry("client_error", None, None, error)
                        return JSONResponse(status_code=400, content={"error": error})
                    if isinstance(content, str):
                        prompt = content
                    elif isinstance(content, MessageContentImageUrl):
                        image_urls.append(content.image_url.get("url"))
                    elif isinstance(content, MessageContentText):
                        prompt = content.text
                    elif isinstance(content, MessageContentVideo):
                        if is_qwen_model:
                            video_frames.extend(content.video)
                        elif supports_native_video:
                            logger.info(
                                "Queuing %s frame(s) for native video processing.",
                                len(content.video),
                            )
                            video_frame_groups.append(content.video)
                        else:
                            logger.info(
                                "Treating video frames as multi-image input for models without native video support."
                            )
                            image_urls.extend(content.video)
                    elif isinstance(content, MessageContentVideoUrl):
                        logger.info("Found MessageContentVideoUrl")
                        video_url = content.video_url.get("url")
                        if video_url.startswith("data:video/mp4;base64,"):
                            logger.info("Decoding base64-encoded video URL")
                            temp_video_path = decode_and_save_video(video_url)
                            video_url = temp_video_path
                        max_pixels = content.max_pixels
                        fps = content.fps
        logger.debug(
            "len(image_urls)=%s, len(video_frames)=%s, len(video_frame_groups)=%s, video_url=%s, max_pixels=%s, fps=%s, len(prompt): %s",
            len(image_urls),
            len(video_frames),
            len(video_frame_groups),
            video_url,
            max_pixels,
            fps,
            len(prompt) if prompt else 0,
        )

        if not prompt:
            logger.info("Invalid request: Missing prompt.")
            persist_telemetry("client_error", None, None, "Prompt is required")
            return JSONResponse(
                status_code=400, content={"error": "Prompt is required"}
            )
        else:
            logger.info(
                f"Processing request with {len(image_urls)} image(s), {len(video_frames)} video frame(s), video_url={video_url}, and a prompt."
            )

        config_kwargs = {
            "max_new_tokens": request.max_completion_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
            "repetition_penalty": request.repetition_penalty,
            "presence_penalty": request.presence_penalty,
            "frequency_penalty": request.frequency_penalty,
            "do_sample": request.do_sample,
        }
        config = ov_genai.GenerationConfig(
            **{k: v for k, v in config_kwargs.items() if v is not None}
        )
        logger.debug(
            f"config: { {k: v for k, v in config_kwargs.items() if v is not None} }"
        )

        def respond_with_generation(generation_kwargs):
            """Invoke the pipeline, handling streaming vs. non-stream flows consistently."""
            nonlocal cleanup_deferred
            logger.debug(
                "Invoking pipeline with kwargs: %s", list(generation_kwargs.keys())
            )
            if request.stream:
                streamer, thread = launch_streaming_generation(pipe, generation_kwargs)
                cleanup_deferred = True
                return create_streaming_response(
                    streamer,
                    request,
                    settings.VLM_MODEL_NAME,
                    on_complete=cleanup_pipeline_state,
                    generation_thread=thread,
                    telemetry_callback=persist_telemetry,
                )

            output = pipe.generate(**generation_kwargs)
            response_text = extract_response_text(output)
            usage, telemetry = build_usage_and_telemetry(
                getattr(output, "perf_metrics", None)
            )
            log_telemetry("non-stream", usage, telemetry)
            response_payload = ChatCompletionResponse(
                id=str(uuid.uuid4()),
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatCompletionDelta(
                            role="assistant", content=response_text
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=usage,
                telemetry=telemetry,
            )
            persist_telemetry("success", usage, telemetry, None)
            return response_payload

        if ModelNames.PHI in settings.VLM_MODEL_NAME.lower():
            # Phi chat variants expect ChatML-formatted prompts (system/user roles plus
            # <|image_i|> markers) and ov_genai only accepts the final prompt string, so
            # we must keep applying the tokenizer chat template ourselves to stay
            # compatible with the OpenAI-style /v1/chat/completions payload.
            logger.info("Using phi-3.5-vision model for processing.")
            logger.debug("Running phi3-vision model")
            if len(image_urls) > 0:
                logger.info(f"Processing {len(image_urls)} image(s) for the request.")
                images, image_tensors = await load_images(image_urls)
                placeholder = "".join(
                    [f"<|image_{i+1}|>\n" for i in range(len(images))]
                )
                messages = [{"role": "user", "content": placeholder + prompt}]
                formatted_prompt = processor.tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                logger.debug(f"formatted_prompt: {formatted_prompt}")
                generation_kwargs = {
                    "prompt": formatted_prompt,
                    "images": image_tensors,
                    "generation_config": config,
                }
            else:
                logger.info("processing as text prompt")
                formatted_messages = []
                for message in request.messages:
                    logger.debug(f"message: {message}")
                    if isinstance(message.content, str):
                        formatted_messages.append(
                            {"role": message.role, "content": message.content}
                        )
                    else:
                        for content in message.content:
                            if isinstance(content, MessageContentText):
                                formatted_messages.append(
                                    {"role": message.role, "content": content.text}
                                )
                    logger.debug(f"formatted_messages: {formatted_messages}")
                formatted_prompt = processor.tokenizer.apply_chat_template(
                    formatted_messages, tokenize=False, add_generation_prompt=True
                )
                logger.debug(f"formatted_prompt: {formatted_prompt}")
                generation_kwargs = {
                    "prompt": formatted_prompt,
                    "generation_config": config,
                }

            return respond_with_generation(generation_kwargs)

        elif is_qwen_model:
            # Qwen2/2.5 VL models still rely on processor-supplied chat templates and
            # qwen_vl_utils vision preprocessing (max_pixels/fps, video kwargs, tensor
            # conversion). This branch preserves multi-turn formatting and ensures the
            # processor-managed packing for images/videos before delegating to ov_genai.
            logger.info(f"Using {ModelNames.QWEN} model for processing.")
            if processor.chat_template is None:
                logger.debug("Initializing chat template from tokenizer.")
                tok = AutoTokenizer.from_pretrained(model_dir)
                processor.chat_template = tok.chat_template

            def _normalize_video_kwargs(video_kwargs: Optional[dict]):
                if not video_kwargs:
                    return video_kwargs
                normalized = {}
                for key, value in video_kwargs.items():
                    if isinstance(value, list) and len(value) == 1:
                        normalized[key] = value[0]
                    else:
                        normalized[key] = value
                return normalized

            qwen_images = None
            qwen_videos = None
            if len(image_urls) == 0 and video_url is None and len(video_frames) == 0:
                logger.info("processing as text prompt")
                # Create formatted_messages only for MessageContentText or str
                formatted_messages = []
                for message in request.messages:
                    if isinstance(message.content, str):
                        formatted_messages.append(
                            {"role": message.role, "content": message.content}
                        )
                    else:
                        for content in message.content:
                            if isinstance(content, MessageContentText):
                                formatted_messages.append(
                                    {"role": message.role, "content": content.text}
                                )
                text = processor.apply_chat_template(
                    formatted_messages, tokenize=False, add_generation_prompt=True
                )
                logger.debug(f"text: {text}")
                generation_kwargs = {
                    "prompt": text,
                    "generation_config": config,
                }
            elif len(image_urls) > 0:
                logger.info("processing as single/multiple image prompt")
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": img} for img in image_urls
                        ]
                        + [{"type": "text", "text": prompt}],
                    }
                ]
                text = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                image_inputs, video_inputs = process_vision_info(messages)
                qwen_images = convert_qwen_image_inputs(image_inputs)
                qwen_videos = convert_qwen_video_inputs(video_inputs)
                generation_kwargs = {
                    "prompt": text,
                    "generation_config": config,
                }
            elif len(video_frames) > 0:
                logger.info(
                    "processing as video (list of frame URLs) via native video modality"
                )
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "video", "video": video_frames},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ]
                text = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                image_inputs, video_inputs, video_kwargs = process_vision_info(
                    messages, return_video_kwargs=True
                )
                video_kwargs = _normalize_video_kwargs(video_kwargs)
                logger.debug("Video kwargs for frame list: %s", video_kwargs)
                logger.debug(
                    "Qwen frame list packaged as video prompt=%s, video_count=%s",
                    text,
                    len(video_inputs) if video_inputs else 0,
                )
                qwen_images = convert_qwen_image_inputs(image_inputs)
                try:
                    qwen_videos = convert_qwen_video_inputs(video_inputs)
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Failed to convert frame list into video tensors (%s); falling back to sampled frames.",
                        exc,
                    )
                    fallback_frames = extract_qwen_video_frames(
                        video_inputs, max_frames=QWEN_FALLBACK_VIDEO_FRAME_LIMIT
                    )
                    if fallback_frames:
                        frame_messages = [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "image": f"video_frame_{idx}",
                                    }
                                    for idx in range(len(fallback_frames))
                                ]
                                + [
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    }
                                ],
                            }
                        ]
                        text = processor.apply_chat_template(
                            frame_messages,
                            tokenize=False,
                            add_generation_prompt=True,
                        )
                        qwen_images = convert_qwen_image_inputs(fallback_frames)
                    else:
                        logger.warning(
                            "No fallback frames available from video input; proceeding without visual context."
                        )
                        qwen_images = None
                    qwen_videos = None
                generation_kwargs = {
                    "prompt": text,
                    "generation_config": config,
                }
            elif video_url:
                logger.info("processing as video_url")
                video_content = {
                    "type": "video",
                    "video": video_url,
                }
                if max_pixels is not None:
                    if isinstance(max_pixels, str):
                        try:
                            max_pixels = eval(max_pixels)
                        except Exception as e:
                            logger.error(f"Failed to evaluate max_pixels: {e}")
                            raise ValueError(f"Invalid max_pixels format: {max_pixels}")
                    video_content["max_pixels"] = max_pixels
                if fps is not None:
                    video_content["fps"] = fps

                messages = [
                    {
                        "role": "user",
                        "content": [
                            video_content,
                            {"type": "text", "text": prompt},
                        ],
                    }
                ]
                text = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                image_inputs, video_inputs, video_kwargs = process_vision_info(
                    messages, return_video_kwargs=True
                )
                video_kwargs = _normalize_video_kwargs(video_kwargs)
                logger.debug(f"Processed video kwargs for URL input: {video_kwargs}")
                logger.debug(
                    "Qwen video url prompt=%s, video_count=%s, frame_tensors=%s",
                    text,
                    len(video_inputs) if video_inputs else 0,
                    [tuple(t.shape) if hasattr(t, "shape") else len(t) for t in (video_inputs or [])],
                )
                qwen_images = convert_qwen_image_inputs(image_inputs)
                try:
                    qwen_videos = convert_qwen_video_inputs(video_inputs)
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Failed to convert processed video inputs to tensors (%s); falling back to frame extraction.",
                        exc,
                    )
                    qwen_videos = None

                generation_kwargs = {
                    "prompt": text,
                    "generation_config": config,
                }

                if qwen_videos:
                    logger.info(
                        "Passing %s processed video(s) directly to ov_genai pipeline.",
                        len(qwen_videos),
                    )
                else:
                    fallback_frames = extract_qwen_video_frames(
                        video_inputs, max_frames=QWEN_FALLBACK_VIDEO_FRAME_LIMIT
                    )
                    if not fallback_frames:
                        logger.warning(
                            "No frames extracted from video input; falling back to text-only prompt."
                        )
                        qwen_images = None
                        qwen_videos = None
                    else:
                        logger.info(
                            "Extracted %s fallback frame(s) for video input; sending as multi-image payload.",
                            len(fallback_frames),
                        )
                        frame_messages = [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "image": f"video_frame_{idx}",
                                    }
                                    for idx in range(len(fallback_frames))
                                ]
                                + [
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    }
                                ],
                            }
                        ]
                        text = processor.apply_chat_template(
                            frame_messages, tokenize=False, add_generation_prompt=True
                        )
                        qwen_images = convert_qwen_image_inputs(fallback_frames)
                        qwen_videos = None
                        generation_kwargs = {
                            "prompt": text,
                            "generation_config": config,
                        }
            else:
                logger.error(
                    "Invalid input: No valid image, video, or text prompt provided."
                )
                error_message = "Invalid input: No valid image, video, or text prompt provided."
                persist_telemetry("client_error", None, None, error_message)
                return JSONResponse(
                    status_code=400,
                    content={"error": error_message},
                )

            if qwen_images:
                generation_kwargs["images"] = qwen_images
            if qwen_videos:
                generation_kwargs["videos"] = qwen_videos

            return respond_with_generation(generation_kwargs)

        elif ModelNames.SMOLVLM in model_name_lower:
            logger.info("Using SmolVLM2 model for processing.")
            if processor is None:
                raise RuntimeError("Processor is not initialized for SmolVLM2.")

            hf_inputs = None
            if len(image_urls) == 0 and video_url is None:
                logger.info("processing as text prompt")
                formatted_messages = []
                for message in request.messages:
                    if isinstance(message.content, str):
                        formatted_messages.append(
                            {"role": message.role, "content": message.content}
                        )
                    else:
                        for content in message.content:
                            if isinstance(content, MessageContentText):
                                formatted_messages.append(
                                    {"role": message.role, "content": content.text}
                                )
                text = processor.apply_chat_template(
                    formatted_messages, tokenize=False, add_generation_prompt=True
                )
                hf_inputs = processor(text=[text], padding=True, return_tensors="pt")
            elif len(image_urls) > 0:
                logger.info("processing as single/multiple image prompt")
                images, _ = await load_images(image_urls)
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": img} for img in images
                        ]
                        + [{"type": "text", "text": prompt}],
                    }
                ]
                hf_inputs = processor.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                )
            elif video_url:
                logger.info("processing as video_url")
                video_path = (
                    video_url.replace("file://", "", 1)
                    if video_url.startswith("file://")
                    else video_url
                )
                video_content = {
                    "type": "video",
                    "path": video_path,
                }
                if fps is not None:
                    video_content["fps"] = fps

                messages = [
                    {
                        "role": "user",
                        "content": [
                            video_content,
                            {"type": "text", "text": prompt},
                        ],
                    }
                ]

                apply_chat_kwargs = {
                    "add_generation_prompt": True,
                    "tokenize": True,
                    "return_dict": True,
                    "return_tensors": "pt",
                    "video_load_backend": get_best_video_backend(),
                }

                if fps is not None:
                    apply_chat_kwargs["target_fps"] = fps
                if model_config:
                    max_frames = model_config.get("max_frames")
                    if max_frames is not None:
                        apply_chat_kwargs["max_frames"] = max_frames
                    video_size = model_config.get("video_size")
                    if video_size is not None:
                        apply_chat_kwargs["video_size"] = video_size

                hf_inputs = processor.apply_chat_template(
                    messages, **apply_chat_kwargs
                )
            else:
                logger.error(
                    "Invalid input: No valid image, video, or text prompt provided."
                )
                error_message = "Invalid input: No valid image, video, or text prompt provided."
                persist_telemetry("client_error", None, None, error_message)
                return JSONResponse(
                    status_code=400,
                    content={"error": error_message},
                )

            if hf_inputs is None:
                raise RuntimeError("Failed to prepare inputs for SmolVLM2 request.")

            streamer = TextIteratorStreamer(
                processor,
                skip_special_tokens=True,
                skip_prompt=True,
                clean_up_tokenization_spaces=False,
            )
            generation_kwargs = dict(
                **hf_inputs,
                streamer=streamer,
                eos_token_id=getattr(processor.tokenizer, "eos_token_id", None),
            )
            optional_params = {
                "max_new_tokens": request.max_completion_tokens,
                "top_p": request.top_p,
                "top_k": request.top_k,
                "temperature": request.temperature,
                "do_sample": request.do_sample,
            }
            generation_kwargs.update(
                {k: v for k, v in optional_params.items() if v is not None}
            )

            thread = Thread(target=safe_generate, args=(pipe, generation_kwargs, streamer))
            thread.daemon = True
            thread.start()

            if request.stream:
                cleanup_deferred = True
                return create_streaming_response(
                    streamer,
                    request,
                    settings.VLM_MODEL_NAME,
                    on_complete=cleanup_pipeline_state,
                    generation_thread=thread,
                    telemetry_callback=persist_telemetry,
                )

            buffer = []
            for new_text in streamer:
                buffer.append(new_text)
                logger.debug(new_text)
            wait_for_generation_thread(thread)
            response_text = "".join(buffer)
            persist_telemetry("success", None, None, None)
            return ChatCompletionResponse(
                id=str(uuid.uuid4()),
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatCompletionDelta(
                            role="assistant", content=response_text
                        ),
                        finish_reason="stop",
                    )
                ],
            )

        else:
            logger.info("Using default model pipeline for processing.")
            image_tensors = None
            video_tensors = None

            if image_urls:
                logger.info("processing as prompt + image")
                _, image_tensors = await load_images(image_urls)
            if video_frame_groups:
                logger.info(
                    "processing %s queued video clip(s) for %s",
                    len(video_frame_groups),
                    settings.VLM_MODEL_NAME,
                )
                try:
                    video_tensors = await convert_frame_urls_to_video_tensors(
                        video_frame_groups
                    )
                except Exception as exc:
                    logger.error(f"Failed to convert queued video frames: {exc}")
                    raise RuntimeError("Error while preparing video inputs") from exc

            if not any([image_tensors, video_tensors]):
                logger.info("processing as text prompt")
                if not prompt or not prompt.strip():
                    logger.error("Prompt is empty or invalid. Aborting generation.")
                    raise ValueError("Invalid prompt provided.")
                generation_kwargs = {
                    "prompt": prompt,
                    "generation_config": config,
                }
            else:
                generation_kwargs = {
                    "prompt": prompt,
                    "generation_config": config,
                }
                if image_tensors:
                    generation_kwargs["images"] = image_tensors
                if video_tensors:
                    generation_kwargs["videos"] = video_tensors

        response = respond_with_generation(generation_kwargs)
        logger.info("Chat completion request processed successfully.")
        return response
    except ValueError as e:
        logger.info("ValueError encountered during chat completion request.")
        logger.error(f"{ErrorMessages.CHAT_COMPLETION_ERROR}: {e}")
        persist_telemetry("client_error", None, None, str(e))
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.info("Exception encountered during chat completion request.")
        logger.error(f"{ErrorMessages.CHAT_COMPLETION_ERROR}: {e}")
        persist_telemetry("server_error", None, None, str(e))
        if ErrorMessages.GPU_OOM_ERROR_MESSAGE in str(e):
            logger.info("Detected GPU out-of-memory error. Restarting server...")
            restart_server()
        return JSONResponse(
            status_code=500,
            content={"error": f"{ErrorMessages.CHAT_COMPLETION_ERROR}: {e}"},
        )
    finally:
        # Clean up the temporary video file if it was created
        if temp_video_path:
            try:
                os.remove(temp_video_path.replace("file://", ""))
                logger.info(f"Temporary video file deleted: {temp_video_path}")
            except Exception as e:
                logger.error(f"Failed to delete temporary video file: {e}")
        if not cleanup_deferred:
            cleanup_pipeline_state()


@app.get("/v1/telemetry", response_model=TelemetryListResponse)
async def list_telemetry(
    limit: Optional[int] = Query(
        default=None,
        gt=0,
        le=settings.VLM_TELEMETRY_MAX_RECORDS,
        description="Maximum number of newest telemetry items to return.",
    )
):
    """Return the most recent telemetry entries (newest first)."""

    try:
        entries = telemetry_store.read_all()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Failed to read telemetry store: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to read telemetry history")

    if limit is not None:
        entries = entries[-limit:]

    records = [TelemetryRecordModel(**entry) for entry in reversed(entries)]
    return TelemetryListResponse(count=len(records), items=records)


@app.get("/v1/models", response_model=ModelsResponse)
async def get_models():
    """
    Retrieve the list of available models.

    Returns:
        ModelsResponse: A response containing the list of available models.
    """
    try:
        logger.info("Fetching available models.")
        models = [{"id": settings.VLM_MODEL_NAME, "object": "model"}]
        logger.info(f"Available models: {models}")
        return ModelsResponse(object="list", data=models)
    except Exception as e:
        logger.info("Exception encountered while fetching models.")
        logger.error(f"{ErrorMessages.GET_MODELS_ERROR}: {e}")
        raise RuntimeError(f"{ErrorMessages.GET_MODELS_ERROR}: {e}")


@app.get("/device", tags=["Device API"], summary="Get available device list")
async def get_device():
    """
    Retrieve a list of available devices.

    Returns:
        dict: A dictionary with a key "devices" containing the list of devices.

    Raises:
        HTTPException: If an error occurs while retrieving the devices.
    """
    try:
        logger.info("Fetching available devices.")
        devices = get_devices()
        logger.info(f"Available devices: {devices}")
        return {"devices": devices}

    except Exception as e:
        logger.info("Exception encountered while fetching devices.")
        logger.exception(f"Error getting devices list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/device/{device}", tags=["Device API"], summary="Get device property")
async def get_device_info(device: str):
    """
    Retrieve information about a specific device.

    Args:
        device (str): The name of the device to retrieve information for.

    Returns:
        JSONResponse: A JSON response containing the properties of the specified device.

    Raises:
        HTTPException: If the device is not found or if there is an error retrieving the device properties.
    """
    try:
        logger.info(f"Fetching properties for device: {device}")
        available_devices = get_devices()

        if device not in available_devices:
            logger.info(f"Device {device} not found.")
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"Device {device} not found. Available devices: {available_devices}"
                },
            )

        device_props = get_device_property(device)
        logger.info(f"Properties for device {device}: {device_props}")
        return JSONResponse(content=device_props)

    except Exception as e:
        logger.info(
            f"Exception encountered while fetching properties for device: {device}"
        )
        logger.exception(f"Error getting properties for device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """
    Perform a health check for the application.

    Returns:
        JSONResponse: A JSON response indicating the health status of the application.
    """
    if model_ready:
        logger.debug("Model is ready. Returning healthy status.")
        return JSONResponse(status_code=200, content={"status": "healthy"})
    else:
        logger.debug("Model is not ready. Returning unhealthy status.")
        return JSONResponse(status_code=503, content={"status": "model not ready"})
