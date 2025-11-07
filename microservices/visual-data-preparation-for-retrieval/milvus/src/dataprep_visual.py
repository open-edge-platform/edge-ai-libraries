# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import re
import logging
import json
from tqdm import tqdm
from pathlib import Path

from indexer import Indexer

from pydantic import BaseModel
from typing import Optional, Dict, Union

logger = logging.getLogger("dataprep_visual")
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s.%(msecs)03d [%(name)s]: %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler = logging.StreamHandler()
logger.addHandler(console_handler)

class IngestHostDirRequest(BaseModel):
    file_dir: str
    frame_extract_interval: int = 15  # Default value is 15
    do_detect_and_crop: bool = True  # Default value is True

class IngestHostFileRequest(BaseModel):
    file_path: str
    meta: dict = {}  # Metadata for the file
    frame_extract_interval: int = 15  # Default value is 15
    do_detect_and_crop: bool = True  # Default value is True

#placeholder for IngestFileURLRequest
class IngestFileURLRequest(BaseModel):
    file_url: str
    meta: dict = {}  # Metadata for the file
    frame_extract_interval: int = 15  # Default value is 15
    do_detect_and_crop: bool = True  # Default value is True

app = FastAPI()

DEVICE = os.getenv("DEVICE", "CPU")
MOUNT_DATA_PATH = "/home/user/data"
HOST_DATA_PATH = os.getenv("HOST_DATA_PATH", "/home/user/data")
LOCAL_EMBED_MODEL_ID = os.getenv("LOCAL_EMBED_MODEL_ID", "CLIP-ViT-H-14")

indexer = Indexer()


def helper_map2host(file_path: str):
    """
    Helper function to map a file path from the container to the host.
    """
    if file_path.startswith(MOUNT_DATA_PATH):
        return file_path.replace(MOUNT_DATA_PATH, HOST_DATA_PATH)
    else:
        return file_path
    
def helper_map2container(file_path: str):
    """
    Helper function to map a file path from the host to the container.
    """
    if file_path.startswith(HOST_DATA_PATH):
        return file_path.replace(HOST_DATA_PATH, MOUNT_DATA_PATH)
    else:
        return file_path

@app.get("/v1/dataprep/health")
def health():
    """
    Health check endpoint.
    """
    try:
        # Perform a simple health check
        return JSONResponse(content={"status": "healthy"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

    
@app.get("/v1/dataprep/info")
def info():
    """
    Get current status info.
    """
    try:
        status_info = {
            "embed_svc_url": indexer.embed_url,
            "model_name": indexer.model_name,
            "device": DEVICE,
        }
        return JSONResponse(content=status_info, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving status info: {str(e)}")

@app.post("/v1/dataprep/ingest")
async def ingest(request: Union[IngestHostDirRequest, IngestHostFileRequest] = Body(...)):
    """
    Ingest files from a directory or a single file.

    Args:
        request (Union[IngestHostDirRequest, IngestHostFileRequest]): The request body containing file_dir, file_path, metadata, frame_extract_interval, and do_detect_and_crop.

    Returns:
        JSONResponse: A response indicating success or failure.
    """   
    if isinstance(request, IngestHostDirRequest):
        logger.info(f"Received IngestHostDirRequest: {request}")
        return await ingest_host_dir(request)
    elif isinstance(request, IngestHostFileRequest):
        logger.info(f"Received IngestHostFileRequest: {request}")
        return await ingest_host_file(request)
    else:
        raise HTTPException(status_code=422, detail="Invalid request type. Provide either 'file_dir' or 'file_path'.")

async def ingest_host_dir(request: IngestHostDirRequest = Body(...)):
    """
    Ingest files from a directory.

    Args:
        request (IngestHostDirRequest): The request body containing file_dir, frame_extract_interval, and do_detect_and_crop.

    Returns:
        JSONResponse: A response indicating success or failure.
    """
    try:
        file_dir = request.file_dir
        frame_extract_interval = request.frame_extract_interval
        do_detect_and_crop = request.do_detect_and_crop

        file_dir_cont = helper_map2container(file_dir)

        # Validate the directory
        if not os.path.isdir(file_dir_cont):
            raise HTTPException(status_code=404, detail="Invalid directory path.")

        proc_files = []
        metas = []
        for root, _, files in os.walk(file_dir_cont): 
            if root.split("/")[-1] == "meta":
                continue
            for file_name in tqdm(files):                
                if not file_name.lower().endswith(('.jpg', '.png', '.jpeg', '.mp4')):
                    logger.debug(f"Unsupported file type: {file_name}, skipped. Supported types are: jpg, jpeg, png, mp4")
                    continue
                file_path = os.path.join(root, file_name)
                # find a json file with the same name as the file to get its metadata
                base_name, _ = os.path.splitext(file_name)
                meta_path = os.path.join(file_dir_cont, "meta", f"{base_name}.json")
                if os.path.exists(meta_path):
                    with open(meta_path, "r") as meta_file:
                        meta = json.load(meta_file)
                    meta["file_path"] = helper_map2host(file_path)
                    proc_files.append(file_path)
                    metas.append(meta)
                else:
                    meta = {}
                    meta["file_path"] = helper_map2host(file_path)
                    proc_files.append(file_path)
                    metas.append(meta)
                
        res = indexer.add_embedding(proc_files, metas, frame_extract_interval=frame_extract_interval, do_detect_and_crop=do_detect_and_crop)

        return JSONResponse(
            content={
                "message": f"Files successfully processed. db returns {res}"
            },
            status_code=200,
        )
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions to preserve their status code and message
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing files: {str(e)}")
    

async def ingest_host_file(request: IngestHostFileRequest = Body(...)):
    """
    Ingest a file with user specified metadata.

    Args:
        request (IngestHostFileRequest): The request body containing file_path, metadata, frame_extract_interval, and do_detect_and_crop.

    Returns:
        JSONResponse: A response indicating success or failure.
    """
    try:
        file_path = request.file_path
        meta = request.meta
        frame_extract_interval = request.frame_extract_interval
        do_detect_and_crop = request.do_detect_and_crop

        file_path_cont = helper_map2container(file_path)

        if not os.path.exists(file_path_cont):
            raise HTTPException(status_code=404, detail="Invalid file path.")
                
        meta["file_path"] = file_path
        res = indexer.add_embedding([file_path_cont], [meta], frame_extract_interval=frame_extract_interval, do_detect_and_crop=do_detect_and_crop)

        return JSONResponse(
            content={
                "message": f"Files successfully processed. db returns {res}"
            },
            status_code=200,
        )
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions to preserve their status code and message
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    
@app.get("/v1/dataprep/get")
def get_file_info(file_path: str):
    """
    Get file info from db.

    Args:
        file_path (str): The path to the file.

    Returns:
        FileResponse: The requested file info.
    """
    try:
        if not file_path or not isinstance(file_path, str):
            raise HTTPException(status_code=400, detail="Invalid file_path parameter. It must be a non-empty string.")

        file_path_cont = helper_map2container(file_path)
        if not os.path.exists(file_path_cont):
            raise HTTPException(status_code=404, detail="File not found.")
        
        res, ids = indexer.query_file(file_path)
        
        return JSONResponse(
            content={
                "file_path": file_path,
                "ids_in_db": ids,
            },
            status_code=200,
        )
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions to preserve their status code and message
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving file: {str(e)}")

@app.delete("/v1/dataprep/delete")
def delete_file_in_db(file_path: str):
    """
    Delete file entity in db. Note that the orginal file will NOT be deleted.

    Args:
        file_path (str): The path to the file.

    Returns:
        JSONResponse: A response indicating success or failure.
    """
    try:
        if not file_path or not isinstance(file_path, str):
            raise HTTPException(status_code=400, detail="Invalid file_path parameter. It must be a non-empty string.")

        file_path_cont = helper_map2container(file_path)
        if not os.path.exists(file_path_cont):
            raise HTTPException(status_code=404, detail="File not found.")
        
        res, ids = indexer.delete_by_file_path(file_path)
        
        return JSONResponse(
            content={
                "message": f"File successfully deleted. db returns: {res}",
                "removed_ids": ids,
            },
            status_code=200,
        )
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions to preserve their status code and message
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

@app.delete("/v1/dataprep/delete_all")
def clear_db():
    """
    Clear the database. Note that the orginal file will NOT be deleted.

    Returns:
        JSONResponse: A response indicating success or failure.
    """
    try:
        res, _ = indexer.delete_all()
        return JSONResponse(
            content={
                "message": f"Database successfully cleared. db returns: {res}"
            },
            status_code=200,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing database: {str(e)}")
