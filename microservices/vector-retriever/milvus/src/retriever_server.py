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
    query: Optional[str] = None
    image_base64: Optional[str] = None
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
async def retrieval(request: RetrievalRequest):
    """
    Perform a retrieval task using the provided text or base64-encoded image input.

    Args:
        request (RetrievalRequest): The JSON body containing query, image_base64, filter, and max_num_results.

    Returns:
        JSONResponse: A response containing the top-k retrieved results.
    """
    try:
        # Validate input
        if not request.query and not request.image_base64:
            raise HTTPException(status_code=400, detail="Either 'query' or 'image_base64' must be provided.")
        if request.query and request.image_base64:
            raise HTTPException(status_code=400, detail="Provide only one of 'query' or 'image_base64', not both.")
        if not isinstance(request.max_num_results, int) or request.max_num_results <= 0:
            raise HTTPException(status_code=400, detail="Invalid max_num_results. It must be a positive integer.")
        if request.max_num_results > 16384:
            raise HTTPException(status_code=400, detail="Invalid max_num_results. It must be in the range [1, 16384].")

        # Process query or image_base64
        if request.query:
            results = retriever.search(query=request.query, filters=request.filter, top_k=request.max_num_results)
        else:
            try:
                results = retriever.search(image_base64=request.image_base64, filters=request.filter, top_k=request.max_num_results)
            except Exception as e:
                logger.error(f"Error processing image_base64: {e}")
                raise HTTPException(status_code=400, detail=f"Error processing image_base64: {str(e)}")

        # Format results
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
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions to preserve their status code and message
        raise http_exc
    except Exception as e:
        logger.error(f"Error during retrieval: {e}")
        raise HTTPException(status_code=500, detail=f"Error during retrieval: {str(e)}")


