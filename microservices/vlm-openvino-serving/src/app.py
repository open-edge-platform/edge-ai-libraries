# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
import sys
import time
import uuid
import warnings
from contextlib import asynccontextmanager
from multiprocessing import Manager
from pathlib import Path
from threading import Thread
from typing import Callable, Optional

import openvino_genai as ov_genai
from fastapi import FastAPI, HTTPException
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
    MessageContentImageUrl,
    MessageContentText,
    MessageContentVideo,
    MessageContentVideoUrl,
    ModelsResponse,
)
from src.utils.utils import (
    convert_model,
    decode_and_save_video,
    get_device_property,
    get_devices,
    is_model_ready,
    load_images,
    load_model_config,
    setup_seed,
    validate_video_inputs,
)
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
pipe, processor, model_dir = None, None, None


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


# Initialize the model
def initialize_model():
    """
    Initialize the model by loading it and setting up the processor.

    Raises:
        RuntimeError: If there is an error during model initialization.
    """
    global model_ready
    global pipe, processor, model_dir
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
        if ModelNames.PHI in model_name.lower():
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
        elif ModelNames.QWEN in model_name.lower():
            if not model_config:
                raise RuntimeError("Model configuration is empty or invalid.")
            pipe = OVModelForVisualCausalLM.from_pretrained(
                model_dir,
                device=settings.VLM_DEVICE.upper(),
                trust_remote_code=True,
                use_cache=False,
                ov_config=ov_config,
            )
            processor = AutoProcessor.from_pretrained(
                model_dir,
                trust_remote_code=True,
                min_pixels=int(eval(model_config.get("min_pixels"))),
                max_pixels=int(eval(model_config.get("max_pixels"))),
            )
        else:
            pipe = ov_genai.VLMPipeline(
                model_dir, device=settings.VLM_DEVICE.upper(), **ov_config
            )
            processor = None  # No processor needed for this case
        model_ready = is_model_ready(model_dir)
        logger.debug("Model is ready")
    except Exception as e:
        logger.error(f"Error initializing the model: {e}")
        raise RuntimeError(f"Error initializing the model: {e}")


# Initialize the model to create global objects of processor, model, model_ready
initialize_model()


def safe_generate(pipe, generation_kwargs, streamer):
    """
    Safely call the `generate` method of the pipeline and handle exceptions.

    Args:
        pipe: The model pipeline.
        generation_kwargs: The generation configuration arguments.
        streamer: The streamer to handle output tokens.
    """
    try:
        pipe.generate(**generation_kwargs)
    except Exception as e:
        logger.error(f"Exception in thread during generation: {e}")
        if ErrorMessages.GPU_OOM_ERROR_MESSAGE in str(e):
            logger.error("Detected GPU out-of-memory error, restarting server...")
            restart_server()
    finally:
        streamer.end_of_stream = True


def create_streaming_response(
    streamer,
    request,
    model_name,
    *,
    on_complete: Optional[Callable[[], None]] = None,
    generation_thread: Optional[Thread] = None,
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
                        )
                    ],
                ).model_dump_json()}\n\n"""
            )
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
    try:
        # Use the provided seed if available, otherwise use the default seed from settings
        seed = request.seed if request.seed is not None else settings.SEED
        setup_seed(seed)

        global pipe, processor, model_dir
        logger.info("Received a chat completion request.")
        logger.debug(f"chat request: {request}")
        # Process the request and generate a response
        if request.model != settings.VLM_MODEL_NAME:
            logger.info(
                f"Requested model {request.model} does not match the configured model {settings.VLM_MODEL_NAME}."
            )
            return JSONResponse(
                status_code=404,
                content={"error": f"Model {request.model} does not exist"},
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

        if last_user_message:
            # Initialize variables for processing the last user message
            image_urls, video_frames, video_url, prompt = [], [], None, None
            max_pixels, fps = None, None  # Initialize max_pixels and fps
            if isinstance(last_user_message.content, str):
                logger.debug(f"content: {last_user_message.content}")
                prompt = last_user_message.content
            else:
                for content in last_user_message.content:
                    error = validate_video_inputs(content, settings.VLM_MODEL_NAME)
                    if error:
                        return JSONResponse(status_code=400, content={"error": error})
                    if isinstance(content, str):
                        prompt = content
                    elif isinstance(content, MessageContentImageUrl):
                        image_urls.append(content.image_url.get("url"))
                    elif isinstance(content, MessageContentText):
                        prompt = content.text
                    elif isinstance(content, MessageContentVideo):
                        if ModelNames.QWEN not in settings.VLM_MODEL_NAME.lower():
                            logger.info(
                                "Treating video frames as multi-image input for non-Qwen2.5-VL models."
                            )
                            image_urls.extend(content.video)
                        else:
                            video_frames.extend(content.video)
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
            f"len(image_urls)={len(image_urls)}, len(video_frames)={len(video_frames)}, video_url={video_url}, max_pixels={max_pixels}, fps={fps}, len(prompt): {len(prompt)}"
        )

        if not prompt:
            logger.info("Invalid request: Missing prompt.")
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

        if ModelNames.PHI in settings.VLM_MODEL_NAME.lower():
            logger.info("Using phi-3.5-vision model for processing.")
            logger.debug("Running phi3-vision model")
            inputs = ""
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
                inputs = processor(formatted_prompt, images, return_tensors="pt")
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
                inputs = processor(formatted_prompt, return_tensors="pt")

            streamer = TextIteratorStreamer(
                processor,
                skip_special_tokens=True,
                skip_prompt=True,
                clean_up_tokenization_spaces=False,
            )
            generation_kwargs = dict(
                **inputs,
                streamer=streamer,
                max_new_tokens=request.max_completion_tokens,
                top_p=request.top_p,
                top_k=request.top_k,
                do_sample=request.do_sample,
                temperature=request.temperature,
                eos_token_id=processor.tokenizer.eos_token_id,
            )

            thread = Thread(
                target=safe_generate, args=(pipe, generation_kwargs, streamer)
            )
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
                )
            else:
                buffer = ""
                for new_text in streamer:
                    buffer += new_text
                    logger.debug(new_text)
                wait_for_generation_thread(thread)
                return ChatCompletionResponse(
                    id=str(uuid.uuid4()),
                    object="chat.completion",
                    created=int(time.time()),
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            index=0,
                            message=ChatCompletionDelta(
                                role="assistant", content=str(buffer)
                            ),
                            finish_reason="stop",
                        )
                    ],
                )

        elif ModelNames.QWEN in settings.VLM_MODEL_NAME.lower():
            logger.info(f"Using {ModelNames.QWEN} model for processing.")
            if processor.chat_template is None:
                logger.debug("Initializing chat template from tokenizer.")
                tok = AutoTokenizer.from_pretrained(model_dir)
                processor.chat_template = tok.chat_template

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
                inputs = processor(
                    text=[text],
                    padding=True,
                    return_tensors="pt",
                )
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
                inputs = processor(
                    text=[text],
                    images=image_inputs,
                    videos=video_inputs,
                    padding=True,
                    return_tensors="pt",
                )
            elif len(video_frames) > 0:
                logger.info("processing as video (list of image frames)")
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
                inputs = processor(
                    text=[text],
                    images=image_inputs,
                    videos=video_inputs,
                    # fps=fps,
                    padding=True,
                    return_tensors="pt",
                    **video_kwargs,
                )
            elif video_url:
                logger.info("processing as video_url")
                # video_frames = await load_video(video_url)
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
                inputs = processor(
                    text=[text],
                    images=image_inputs,
                    videos=video_inputs,
                    # fps=fps,
                    padding=True,
                    return_tensors="pt",
                    **video_kwargs,
                )
            else:
                logger.error(
                    "Invalid input: No valid image, video, or text prompt provided."
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Invalid input: No valid image, video, or text prompt provided."
                    },
                )

            streamer = TextIteratorStreamer(
                processor,
                skip_special_tokens=True,
                skip_prompt=True,
                clean_up_tokenization_spaces=False,
            )
            generation_kwargs = dict(
                **inputs,
                streamer=streamer,
                max_new_tokens=request.max_completion_tokens,
                top_p=request.top_p,
                top_k=request.top_k,
                do_sample=request.do_sample,
                temperature=request.temperature,
                eos_token_id=processor.tokenizer.eos_token_id,
            )

            thread = Thread(
                target=safe_generate, args=(pipe, generation_kwargs, streamer)
            )
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
                )
            else:
                buffer = ""
                for new_text in streamer:
                    buffer += new_text
                    logger.debug(new_text)
                wait_for_generation_thread(thread)
                return ChatCompletionResponse(
                    id=str(uuid.uuid4()),
                    object="chat.completion",
                    created=int(time.time()),
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            index=0,
                            message=ChatCompletionDelta(
                                role="assistant", content=str(buffer)
                            ),
                            finish_reason="stop",
                        )
                    ],
                )

        else:
            logger.info("Using default model pipeline for processing.")
            if len(image_urls) == 0:
                logger.info("processing as text prompt")
                logger.debug(f"prompt1: {prompt}")
                if not prompt or not prompt.strip():
                    logger.error("Prompt is empty or invalid. Aborting generation.")
                    raise ValueError("Invalid prompt provided.")
                output = pipe.generate(prompt, generation_config=config)
            else:
                logger.info("processing as prompt + image")
                images, image_tensors = await load_images(image_urls)
                output = pipe.generate(
                    prompt, images=image_tensors, generation_config=config
                )
        logger.debug(f"output: {str(output)}")
        response = ChatCompletionResponse(
            id=str(uuid.uuid4()),
            object="chat.completion",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionDelta(role="assistant", content=str(output)),
                    finish_reason="stop",
                )
            ],
        )

        logger.info("Chat completion request processed successfully.")
        return response
    except ValueError as e:
        logger.info("ValueError encountered during chat completion request.")
        logger.error(f"{ErrorMessages.CHAT_COMPLETION_ERROR}: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.info("Exception encountered during chat completion request.")
        logger.error(f"{ErrorMessages.CHAT_COMPLETION_ERROR}: {e}")
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
