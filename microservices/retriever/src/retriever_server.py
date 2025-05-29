# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import logging

from retriever_milvus import MilvusRetriever

from pydantic import BaseModel
from typing import Optional, Dict

logger = logging.getLogger("retriever")
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s.%(msecs)03d [%(name)s]: %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler = logging.StreamHandler()
logger.addHandler(console_handler)

class RetrievalRequest(BaseModel):
    query: str
    filter: Optional[Dict] = None
    max_num_results: int = 10

app = FastAPI()

retriever = MilvusRetriever()

@app.get("/v1/retrieval/health")
def health():
    """
    Health check endpoint.
    """
    try:
        # Perform a simple health check
        return JSONResponse(content={"status": "healthy"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.post("/v1/retrieval")
def retrieval(request: RetrievalRequest):
    """
    Perform a retrieval task using the provided text input and embedding.

    Args:
        request (RetrievalRequest): The request body containing query, filter, and max_num_results.

    Returns:
        JSONResponse: A response containing the top-k retrieved results.
    """
    try:
        results = retriever.search(request.query, request.filter, top_k=request.max_num_results)
        ret = []
        for hit in results:
            ret.append({
                "id": hit.get("id"),
                "distance": hit.get('distance'),
                "meta": hit.get("entity").get("meta")
            })

        # Return the results
        return JSONResponse(
            content={
                "results": ret
            },
            status_code=200,
        )

    except Exception as e:
        logger.error(f"Error during retrieval: {e}")
        raise HTTPException(status_code=500, detail=f"Error during retrieval: {str(e)}")


