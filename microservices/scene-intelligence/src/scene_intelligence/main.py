"""Main entry point for Scene Intelligence API service."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from .api.routes import router
from .services.config import ConfigService
from .services.mqtt_service import MQTTService
from .services.directional_traffic_service import DirectionalTrafficService
from .services.image_service import ImageService
from .services.mqtt_publisher import MQTTPublisher
from .services.vlm_service import VLMService


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    logger.info("Starting Scene Intelligence service")
    
    # Load configuration
    config_service = ConfigService()
    app.state.config = config_service
    
    # Initialize directional traffic service
    directional_traffic_service = DirectionalTrafficService(config_service)
    app.state.directional_traffic = directional_traffic_service
    
    # Initialize image service
    image_service = ImageService(config_service)
    app.state.image_service = image_service
    
    # Initialize VLM service
    vlm_service = VLMService(config_service)
    app.state.vlm_service = vlm_service
    
    # Initialize MQTT publisher
    mqtt_publisher = MQTTPublisher(config_service)
    await mqtt_publisher.initialize()
    app.state.mqtt_publisher = mqtt_publisher
    
    # Set MQTT publisher reference in VLM service for coordination
    vlm_service.set_mqtt_publisher(mqtt_publisher)
    
    # Initialize and start MQTT service
    mqtt_service = MQTTService(config_service, directional_traffic_service, image_service, vlm_service)
    await mqtt_service.initialize()
    
    # Set the current event loop for async task scheduling
    current_loop = asyncio.get_running_loop()
    mqtt_service.set_event_loop(current_loop)
    
    app.state.mqtt = mqtt_service
    
    # Start MQTT service in background
    mqtt_task = asyncio.create_task(mqtt_service.start())
    app.state.mqtt_task = mqtt_task
    
    logger.info("Scene Intelligence service started successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Scene Intelligence service")
    
    # Stop MQTT service
    if hasattr(app.state, 'mqtt_task'):
        app.state.mqtt_task.cancel()
        try:
            await app.state.mqtt_task
        except asyncio.CancelledError:
            pass
    
    if hasattr(app.state, 'mqtt'):
        await app.state.mqtt.stop()
    
    # Stop MQTT publisher
    if hasattr(app.state, 'mqtt_publisher'):
        await app.state.mqtt_publisher.stop()
    
    logger.info("Scene Intelligence service stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Scene Intelligence API",
        description="Multi-intersection traffic analysis microservice",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Include API routes
    app.include_router(router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "scene-intelligence"}
    
    return app


def main():
    """Main entry point."""
    # Set up logging level
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level))
    
    # Create FastAPI app
    app = create_app()
    
    # Get configuration
    port = int(os.getenv("SCENE_INTELLIGENCE_PORT", "8080"))
    host = os.getenv("SCENE_INTELLIGENCE_HOST", "0.0.0.0")
    
    # Run the application
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        access_log=True
    )


if __name__ == "__main__":
    main()
