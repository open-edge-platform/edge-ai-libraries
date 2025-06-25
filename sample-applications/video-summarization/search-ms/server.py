import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.utils.common import logger, settings
from src.utils.directory_watcher import (
    get_initial_upload_status,
    get_last_updated,
    start_watcher,
)
from src.utils.minio_client import client as minio_client
from src.vdms_retriever.retriever import get_vectordb
from pydantic import BaseModel

bucket_name = f"arn:aws:s3:::{settings.VDMS_BUCKET}/*"
policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": [bucket_name],
        },
    ],
}
if minio_client.bucket_exists(settings.VDMS_BUCKET):
    logger.debug(f"{settings.VDMS_BUCKET} exists")
else:
    logger.debug(f"{settings.VDMS_BUCKET} does not exist")
    minio_client.make_bucket(settings.VDMS_BUCKET)
    logger.debug(f"created {settings.VDMS_BUCKET}")
minio_client.set_bucket_policy(settings.VDMS_BUCKET, json.dumps(policy))
logger.debug("set minio bucket policy to public")
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    import threading

    watcher_thread = threading.Thread(target=start_watcher)
    watcher_thread.daemon = True
    watcher_thread.start()


class QueryRequest(BaseModel):
    query_id: str
    query: str


@app.post("/query")
async def query_endpoint(request: list[QueryRequest]):
    try:

        async def process_query(query_request):
            docs_with_score = get_vectordb().similarity_search_with_relevance_scores(
                query_request.query, k=20
            )
            query_results = []
            for res, score in docs_with_score:
                res.metadata["relevance_score"] = score
                query_results.append(res)
            return {"query_id": query_request.query_id, "results": query_results}

        async def process_batch(batch):
            tasks = [process_query(query_request) for query_request in batch]
            return await asyncio.gather(*tasks)

        async def process_requests(requests):
            batch_size = 20
            results = []
            for i in range(0, len(requests), batch_size):
                batch = requests[i : i + batch_size]
                batch_results = await process_batch(batch)
                results.extend(batch_results)
            return results

        results = await process_requests(request)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in query_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/watcher-last-updated")
async def watcher_last_updated():
    try:
        last_updated = get_last_updated()
        return {"last_updated": last_updated}
    except Exception as e:
        logger.error(f"Error in watcher_last_updated: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/initial-upload-status")
async def initial_upload_status():
    try:
        logger.debug("Querying initial upload status")
        status = get_initial_upload_status()
        logger.debug(f"Initial upload status: {status}")
        return {"status": status}
    except Exception as e:
        logger.error(f"Error in initial_upload_status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
