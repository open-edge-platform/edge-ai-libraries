import os
import logging
from fastapi import FastAPI

from api.routes import pipelines, devices, models, metrics

# Configure logging
loglevel = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=loglevel)

# Initialize FastAPI app
app = FastAPI(
    title="Visual Pipeline and Platform Evaluation Tool API",
    description="API for Visual Pipeline and Platform Evaluation Tool",
    version="1.0.0",
)

# Include routers from different modules
app.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
