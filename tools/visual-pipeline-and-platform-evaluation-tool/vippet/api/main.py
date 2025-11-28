import os
import logging
from fastapi import FastAPI

from api.routes import convert, devices, jobs, metrics, models, pipelines, tests, videos
from videos import get_videos_manager

# Configure logging
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
)

for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logger = logging.getLogger(logger_name)
    logger.setLevel(os.environ.get("WEB_SERVER_LOG_LEVEL", "WARNING").upper())
    logger.handlers.clear()
    logger.handlers = [handler]
    logger.propagate = False

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
logger.handlers = [handler]

# Initialize VideosManager singleton before FastAPI app
videos_manager = get_videos_manager()

# Initialize FastAPI app
app = FastAPI(
    title="Visual Pipeline and Platform Evaluation Tool API",
    description="API for Visual Pipeline and Platform Evaluation Tool",
    version="1.0.0",
    root_path="/api/v1",
    # without explicitly setting servers to the same value as root_path,
    # generating openapi schema would omit whole servers section in vippet.json
    servers=[
        {"url": "/api/v1"},
    ],
)

# Include routers from different modules
app.include_router(convert.router, prefix="/convert", tags=["convert"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
app.include_router(tests.router, prefix="/tests", tags=["tests"])
app.include_router(videos.router, prefix="/videos", tags=["videos"])
