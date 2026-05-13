from contextlib import asynccontextmanager

from utils.logger_config import setup_logger
setup_logger()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.custom_endpoints import router as custom_router
from api.openai_endpoints import router as openai_router
from pipeline import Pipeline
from utils.config_loader import config
from utils.ensure_model import ensure_model
from utils.preload_models import preload_models
import logging


logger = logging.getLogger(__name__)


def _cors_allow_origins() -> list[str]:
    raw_value = __import__("os").getenv(
        "TEXT_TO_SPEECH_CORS_ALLOW_ORIGINS",
        "http://127.0.0.1,http://localhost",
    )
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["http://127.0.0.1", "http://localhost"]


@asynccontextmanager
async def lifespan(app: FastAPI):
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

if __name__ == "__main__":
    import uvicorn
    logger.info("App started, Starting Server...")
    host = __import__("os").getenv("TEXT_TO_SPEECH_SERVER_HOST", "127.0.0.1")
    port = int(__import__("os").getenv("TEXT_TO_SPEECH_SERVER_PORT", "8011"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
