import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from api.middleware import InitializationMiddleware
from api.routes import health, metrics
from internal_types import InternalAppStatus
from managers.app_state_manager import AppStateManager
from managers.pipeline_manager import PipelineManager
from managers.pipeline_template_manager import PipelineTemplateManager
from videos import VideosManager

BASE_DIR = Path(__file__).resolve().parent

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
logger.setLevel(os.environ.get("APP_LOG_LEVEL", "INFO").upper())
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
            InternalAppStatus.INITIALIZING, "Downloading videos and loading metadata..."
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

        app_state_manager.set_status(InternalAppStatus.READY)
        logger.info("Application initialization complete")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        app_state_manager.set_status(
            InternalAppStatus.SHUTDOWN, f"Initialization failed: {e}"
        )


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
    app_state_manager.set_status(InternalAppStatus.STARTING)

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
    app_state_manager.set_status(InternalAppStatus.SHUTDOWN)


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
    docs_url=None,  # disable default /docs endpoint
    redoc_url=None,  # disable default /redoc endpoint
)

# Mount static files directory with absolute path
static_dir = BASE_DIR / "static"
logger.debug(f"Mounting static files from: {static_dir}")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Custom Swagger UI endpoint with custom CSS
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        <link type="text/css" rel="stylesheet" href="/static/css/swagger-custom.css">
        <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
        <title>Visual Pipeline and Platform Evaluation Tool API - Swagger UI</title>
    </head>
    <body>
        <div id="swagger-ui">
        </div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>
        const ui = SwaggerUIBundle({
            url: '/api/v1/openapi.json',
            "dom_id": "#swagger-ui",
            "layout": "BaseLayout",
            "deepLinking": true,
            "showExtensions": true,
            "showCommonExtensions": true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
        })
        </script>
    </body>
    </html>
    """)


# Custom ReDoc endpoint
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Visual Pipeline and Platform Evaluation Tool API - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <style>
            body { margin: 0; padding: 0; }
        </style>
    </head>
    <body>
        <redoc spec-url='/api/v1/openapi.json'></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@2.0.0/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """)


# Add middleware to block requests during initialization
app.add_middleware(InitializationMiddleware)

# Register health router immediately (before initialization) so health checks work while app is initializing
app.include_router(health.router, tags=["health"])
# Register metrics router immediately (it does not depend on VideosManager) so collector can connect as soon as possible
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
