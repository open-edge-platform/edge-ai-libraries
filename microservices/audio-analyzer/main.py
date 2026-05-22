from utils.logger_config import setup_logger
setup_logger()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from api.custom_endpoints import router as custom_router
from api.error_responses import build_openai_error, openai_error_response
from api.openai_endpoints import router as openai_router
from utils.ensure_model import ensure_model
from utils.preload_models import preload_models
import logging
import os
import shutil
from fastapi.middleware.cors import CORSMiddleware


logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # For Testing ["*"]
    allow_credentials=True,          # cookies/auth allowed
    allow_methods=["*"],             # allow all HTTP methods
    allow_headers=["*"],             # allow all headers
    expose_headers=["x-session-id"]  # expose custom headers if needed
)

def _clear_storage_on_startup() -> None:
    from utils.config_loader import config
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


@app.on_event("startup")
def startup_event():
    _clear_storage_on_startup()
    ensure_model()
    preload_models()


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
    message = detail if isinstance(detail, str) else "Request failed"
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
            "Audio transcription failed",
            error_type="server_error",
            code="internal_error",
        ),
    )

if __name__ == "__main__":
    import uvicorn
    logger.info("App started, Starting Server...")
    host = os.environ.get("AUDIO_ANALYZER_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("AUDIO_ANALYZER_SERVER_PORT", "8010"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
