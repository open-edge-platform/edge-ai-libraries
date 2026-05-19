from contextlib import asynccontextmanager

from utils.logger_config import setup_logger
setup_logger()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.custom_endpoints import router as custom_router
from api.error_responses import build_openai_error, openai_error_response
from api.openai_endpoints import router as openai_router
from pipeline import Pipeline
from utils.config_loader import config
from utils.ensure_model import ensure_model
from utils.preload_models import preload_models
import logging
import os
import shutil


logger = logging.getLogger(__name__)


def _cors_allow_origins() -> list[str]:
    raw_value = __import__("os").getenv(
        "TEXT_TO_SPEECH_CORS_ALLOW_ORIGINS",
        "http://127.0.0.1,http://localhost",
    )
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["http://127.0.0.1", "http://localhost"]


def _clear_storage_on_startup() -> None:
    from utils.app_paths import STORAGE_ROOT
    if not getattr(getattr(config, "app", None), "clear_storage_on_startup", False):
        return
    if not os.path.isdir(STORAGE_ROOT):
        return
    count = 0
    for entry in os.listdir(STORAGE_ROOT):
        entry_path = os.path.join(STORAGE_ROOT, entry)
        if os.path.isdir(entry_path):
            shutil.rmtree(entry_path, ignore_errors=True)
            count += 1
    logger.info("Cleared %d session folder(s) from storage on startup", count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _clear_storage_on_startup()
    ensure_model()
    preload_models()

    # GPU warmup: compile kernels before the app starts serving traffic.
    try:
        tts_cfg = config.models.tts
        Pipeline(session_id="startup-warmup").synthesize(
            text="warmup",
            speaker=tts_cfg.default_speaker,
            language=tts_cfg.default_language,
            persist_output=False,
        )
        logger.info("GPU warmup completed")
    except Exception as e:
        logger.warning("GPU warmup failed: %s", e)

    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-session-id"],
)

app.include_router(openai_router)
app.include_router(custom_router)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0] if exc.errors() else {}
    loc = first_error.get("loc", ())
    param = None
    if len(loc) >= 2 and loc[0] == "body":
        param = str(loc[1])
    message = first_error.get("msg", "Request validation failed")
    return openai_error_response(
        422,
        message,
        param=param,
        code="invalid_request",
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    if isinstance(detail, str):
        message = detail
    else:
        message = "Request failed"
    return openai_error_response(
        exc.status_code,
        message,
        code="invalid_request" if exc.status_code < 500 else "internal_error",
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    logger.exception("Unhandled application failure")
    return JSONResponse(
        status_code=500,
        content=build_openai_error(
            "Speech synthesis failed",
            error_type="server_error",
            code="internal_error",
        ),
    )

if __name__ == "__main__":
    import uvicorn
    logger.info("App started, Starting Server...")
    host = __import__("os").getenv("TEXT_TO_SPEECH_SERVER_HOST", "127.0.0.1")
    port = int(__import__("os").getenv("TEXT_TO_SPEECH_SERVER_PORT", "8011"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
