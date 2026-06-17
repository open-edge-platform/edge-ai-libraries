from fastapi import APIRouter
from fastapi.responses import JSONResponse

from pipeline import Pipeline
from utils.latency_store import tts_latency


router = APIRouter()


@router.get("/health")
def health():
    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.get("/v1/model-info")
def tts_model_info():
    pipeline = Pipeline(session_id="metadata")
    return JSONResponse(content=pipeline.get_model_info(), status_code=200)


@router.get("/v1/performance")
def tts_performance():
    return JSONResponse(content={"latency": tts_latency.stats()})


@router.get("/v1/audio/voices")
def list_supported_voices():
    pipeline = Pipeline(session_id="metadata")
    return JSONResponse(content=pipeline.get_model_info(), status_code=200)