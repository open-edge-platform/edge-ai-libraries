# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
import asyncio
import json
from typing import Optional, List, Tuple, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.vectorstores.vdms import VDMS

from src.utils.common import logger, settings
from src.utils.directory_watcher import (
    get_initial_upload_status,
    get_last_updated,
    start_watcher,
)
from src.vdms_retriever.retriever import get_vectordb
from pydantic import BaseModel

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
    tags: Optional[list[str]] = None


@app.post("/query")
async def query_endpoint(request: list[QueryRequest]):
    try:
        db: VDMS = get_vectordb()
        if not db:
            logger.error("VectorDB could not be initialized. Please verify the connection.")
            raise HTTPException(status_code=500, detail="Some error ocurred at the DataPrep Service.")
        
        async def process_query(query_request):
            """ Process a single query request. """
            
            logger.debug(f"Processing query: {query_request.query} with filter: {filter}")
            docs_with_score: List[Tuple[Any, float]] = db.similarity_search_with_score(
                query_request.query, k=20, normalize_distance=True
            )
            query_results = []
            for res, score in docs_with_score:
                res.metadata["relevance_score"] = score
                # filter the results on tags
                if query_request.tags:
                    result_tags: list = []
                    if res.metadata.get("tags"):
                        # construct a list of tags from the tag string in results metadata
                        if isinstance(res.metadata["tags"], str):
                            result_tags = res.metadata["tags"].split(",")
                        else:
                            result_tags = res.metadata["tags"]

                    # check if any of the query tags are in the result tags
                    if not set(query_request.tags).intersection(set(result_tags)):
                        continue
                        
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
    
    except KeyError as e:
        if str(e) == "'entities'":
            logger.error(f"KeyError in query_endpoint: {str(e)}")
            logger.error(f"No entities were found. Perhaps, no index is created or no \
                         embeddings have been generated yet in the index: {settings.INDEX_NAME}")
            raise HTTPException(status_code=404, detail=f"No entities were found.")
        else:
            logger.error(f"KeyError in query_endpoint: {str(e)}")
            raise HTTPException(status_code=500, detail="Some error ocurred while running the search query.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error in query_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Some error ocurred at the DataPrep Service.")


@app.get("/watcher-last-updated")
async def watcher_last_updated():
    try:
        last_updated = get_last_updated()
        return {"last_updated": last_updated}
    except Exception as e:
        logger.error(f"Error in watcher_last_updated: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Simple health check endpoint to verify the service is running."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


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
