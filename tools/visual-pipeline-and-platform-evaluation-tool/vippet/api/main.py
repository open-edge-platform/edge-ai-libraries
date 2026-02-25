import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.api_schemas import AppStatus
from api.middleware import InitializationMiddleware
from api.routes import health, metrics
from managers.app_state_manager import AppStateManager
from managers.pipeline_manager import PipelineManager
from managers.pipeline_template_manager import PipelineTemplateManager
from videos import VideosManager

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


def _initialize_in_background(app: FastAPI) -> None:
    """
    Initialize application resources in background thread.

    This function runs in a separate thread so the server can start
    responding to health checks immediately while initialization proceeds.
    """
    app_state_manager = AppStateManager()

    try:
        app_state_manager.set_status(
            AppStatus.INITIALIZING, "Downloading videos and loading metadata..."
        )

        # Initialize VideosManager - downloads videos, scans files,
        # extracts metadata, and converts to TS format
        VideosManager()

        # Initialize PipelineManager - loads predefined pipelines
        PipelineManager()

        # Initialize PipelineTemplateManager - loads pipeline templates
        PipelineTemplateManager()

        # Register remaining routers after VideosManager, PipelineManager, and PipelineTemplateManager are initialized
        register_routers(app)

        app_state_manager.set_status(AppStatus.READY)
        logger.info("Application initialization complete")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        app_state_manager.set_status(AppStatus.SHUTDOWN, f"Initialization failed: {e}")


def register_routers(app: FastAPI) -> None:
    """
    Register all API routers (except health which is registered early).

    This function is called after VideosManager initialization to avoid
    importing modules that depend on VideosManager before it's initialized.
    """
    # Import routers here to avoid early initialization of VideosManager
    from api.routes import (
        convert,
        devices,
        jobs,
        models,
        pipeline_templates,
        pipelines,
        tests,
        videos,
        cameras,
    )

    # Include routers from different modules
    app.include_router(convert.router, prefix="/convert", tags=["convert"])
    app.include_router(devices.router, prefix="/devices", tags=["devices"])
    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    app.include_router(models.router, prefix="/models", tags=["models"])
    app.include_router(
        pipeline_templates.router,
        prefix="/pipeline-templates",
        tags=["pipeline-templates"],
    )
    app.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
    app.include_router(tests.router, prefix="/tests", tags=["tests"])
    app.include_router(videos.router, prefix="/videos", tags=["videos"])
    app.include_router(cameras.router, prefix="/cameras", tags=["cameras"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown.

    Starts initialization in background thread so server can respond
    to health checks immediately.
    """
    logger.info("Application starting...")
    app_state_manager = AppStateManager()
    app_state_manager.set_status(AppStatus.STARTING)

    # Start initialization in background thread
    init_thread = threading.Thread(
        target=_initialize_in_background,
        args=(app,),
        name="initialization-thread",
        daemon=True,
    )
    init_thread.start()

    yield

    # Shutdown
    logger.info("Application shutting down...")
    app_state_manager.set_status(AppStatus.SHUTDOWN)


# Initialize FastAPI app with lifespan
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
    lifespan=lifespan,
)

# Add middleware to block requests during initialization
app.add_middleware(InitializationMiddleware)

# Register health router immediately (before initialization) so health checks work while app is initializing
app.include_router(health.router, tags=["health"])
# Register metrics router immediately (it does not depend on VideosManager) so collector can connect as soon as possible
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
