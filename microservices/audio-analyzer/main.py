from utils.logger_config import setup_logger
setup_logger()

from fastapi import FastAPI
from api.custom_endpoints import router as custom_router
from api.openai_endpoints import router as openai_router
from utils.ensure_model import ensure_model
from utils.preload_models import preload_models
import logging
import os
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

@app.on_event("startup")
def startup_event():
    ensure_model()
    preload_models()


app.include_router(openai_router)
app.include_router(custom_router)

if __name__ == "__main__":
    import uvicorn
    logger.info("App started, Starting Server...")
    host = os.environ.get("AUDIO_ANALYZER_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("AUDIO_ANALYZER_SERVER_PORT", "8010"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
