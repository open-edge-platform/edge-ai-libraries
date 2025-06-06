from fastapi import APIRouter

from audio_intelligence.api.endpoints import health, models, transcription

api_router = APIRouter()

# Include routers for each endpoints in the API
api_router.include_router(health.router)
api_router.include_router(transcription.router)
api_router.include_router(models.router)