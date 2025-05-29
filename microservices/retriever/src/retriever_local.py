from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import logging
import json

from retriever_milvus import Retriever


logger = logging.getLogger("retriever")
console_handler = logging.StreamHandler()
logger.addHandler(console_handler)



retriever = Retriever()



def retrieval(query: str, filter: dict = None, max_num_results: int = 5):
    """
    Perform a retrieval task using the provided text input and embedding.

    Args:
        query (list): The embedding vector to use for retrieval.
        filter (dict): Optional filter to apply during retrieval.
        max_num_results (int): The number of top results to retrieve. Default is 5.

    Returns:
        JSONResponse: A response containing the top-k retrieved results.
    """
    try:
        # Validate the query
        # if not isinstance(query, list) or len(query) == 0:
        #     raise HTTPException(status_code=400, detail="Invalid query vector.")

        results = retriever.search(query, filter, top_k=max_num_results)
        # ret = [node.metadata for node in results]
        # add similarity score

        # Return the results
        return results
    except Exception as e:
        print(f"Error during retrieval: {e}")
        raise ValueError(f"Error during retrieval: {str(e)}")
    
# filters = None
filters = {"camera": "camera_1"}
# filters = {"timestamp_start": 1805909401}
ret = retrieval("road", filter=filters)
print(ret)