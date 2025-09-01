import os
import time
import uvicorn
from pathlib import Path
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from http import HTTPStatus
from pydantic import BaseModel
from typing import Annotated
from .config import config
from .logger import logger
from .chain import (
    create_faiss_vectordb,
    get_document_from_vectordb,
    delete_embedding_from_vectordb,
    get_retriever,
    build_chain,
    process_query,
)
from .document import validate_document, save_document
from .utils import get_available_devices, get_device_property

app = FastAPI(title="Chat Question and Answer Core", root_path="/v1/chatqna")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(
        ","
    ),  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=os.getenv("CORS_ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("CORS_ALLOW_HEADERS", "*").split(","),
)


class ChatRequest(BaseModel):
    input: str
    stream: bool = True


@app.get("/health", tags=["Health API"], summary="Check API health status")
async def health():
    """
    Check the health status of the service.

    Returns:
        dict: A dictionary containing the status and message of the service health.
    """

    return {"status": "Success", "message": "Service is up and running."}


@app.get("/model", tags=["Model API"], summary="Get the LLM_MODEL details")
async def get_llm_model():
    """
    Get the details of the LLM_MODEL.

    Returns:
        dict: A dictionary containing the name of the LLM_MODEL.
    """

    llm_model = config.LLM_MODEL_ID

    return {"status": "Success", "llm_model": llm_model}


@app.get("/devices", tags=["Device API"], summary="Get available devices list")
async def get_devices():
    """
    Retrieve a list of devices.
    Returns:
        dict: A dictionary with a key "devices" containing the list of devices.
    Raises:
        HTTPException: If an error occurs while retrieving the devices, an HTTP 500 exception is raised with the error details.
    """

    try:
        devices = get_available_devices()

        return {"devices": devices}

    except Exception as e:
        logger.exception("Error getting devices list.", error=e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/devices/{device}", tags=["Device API"], summary="Get device property")
async def get_device_info(device: str = ""):
    """
    Retrieve information about a specific device.
    Args:
        device (str): The name of the device to retrieve information for. Defaults to an empty string.
    Returns:
        JSONResponse: A JSON response containing the properties of the specified device.
    Raises:
        HTTPException: If the device is not found or if there is an error retrieving the device properties.
    """

    try:
        available_devices = get_available_devices()

        if device not in available_devices:
            raise HTTPException(
                status_code=404, detail=f"Device {device} not found. Available devices: {available_devices}"
            )

        device_props = get_device_property(device)

        return JSONResponse(content=device_props)

    except Exception as e:
        logger.exception("Error getting properties for device.", error=e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/documents",
    tags=["Document Ingestion API"],
    summary="Get list of documents ingested.",
)
async def get_documents():
    """
    Get the list of documents ingested in the system.

    Returns:
        dict: A dictionary containing the list of documents ingested.
    """

    try:
        documents = get_document_from_vectordb()

        return {"status": "Success", "metadata": {"documents": documents}}

    except Exception as e:
        logger.exception("Error getting documents.", error=e)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Error getting documents.",
        )


@app.post(
    "/documents",
    tags=["Document Ingestion API"],
    summary="Upload documents to create and store embeddings.",
)
async def ingest_document(
    files: Annotated[
        list[UploadFile],
        File(description="Select single or multiple PDF, docx or pdf file(s)."),
    ],
):
    """
    Ingests and processes a list of document files by validating, saving, and creating embeddings for them.

    Args:
        files (list[UploadFile]): A list of files to be ingested. The files should be in one of the supported formats: pdf, txt, docx.

    Returns:
        dict: A dictionary containing the status, message, and metadata about the ingested files.

    Raises:
        HTTPException: If the file format is invalid, if there is an error saving the file, or if there is an error creating embeddings.
    """

    try:
        ingested_files, tmp_files = [], []

        if files:
            if not isinstance(files, list):
                files = [files]

        for file_obj in files:
            status = validate_document(file_obj)
            if status is False:
                logger.exception("Invalid file format.")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="Invalid file format. Please upload files in one of the following supported formats: pdf, txt, docx.",
                )

            # Save document in /tmp/ to ingest it
            tmp_file, err_message = await save_document(file_obj)
            if tmp_file is None:
                logger.exception("Error saving file.", error=err_message)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Error saving file: {err_message}",
                )

            tmp_files.append(tmp_file)

            try:
                create_status = create_faiss_vectordb(file_path=tmp_file)
                if create_status is False:
                    logger.exception("No text data from the document.")
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                        detail="Error creating embedding. No text data from the document.",
                    )

            except Exception as err:
                logger.exception("Error creating embedding.", error=err)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Error creating embedding: {err}",
                )

            finally:
                # Maintain the list of file that ingested successfully
                ingested_files.append(file_obj.filename)

        return {
            "status": "Success",
            "message": "Files have been successfully ingested and embeddings created.",
            "metadata": {"documents": ingested_files},
        }

    except HTTPException as ex:
        raise ex

    except Exception as e:
        logger.exception("Error ingesting document.", error=e)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))

    finally:
        # Delete the temporary files at the end
        for temp_file in tmp_files:
            if temp_file:
                Path(temp_file).unlink()


@app.delete(
    "/documents",
    tags=["Document Ingestion API"],
    summary="Delete embeddings from vectorstore.",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_embedding(document: str = "", delete_all: bool = False):
    """
    Deletes embeddings from the vectorstore.

    Args:
        document (str): The name of the document whose embeddings are to be deleted. Defaults to an empty string.
        delete_all (bool): Flag indicating whether to delete all embeddings. Defaults to False.

    Returns:
        status_code: HTTP status code of 204 indicating the success of the deletion process.

    Raises:
        HTTPException: If there is an error during the deletion process.
    """

    try:
        if not delete_all and not document:
            logger.exception(
                "Please provide document name if set delete_all flag to False."
            )
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail="Please provide document name if delete_all flag set to False.",
            )
        status = delete_embedding_from_vectordb(document, delete_all)
        if status is False:
            logger.exception("No documents exists in vectorstore")
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="No documents exists in vectorstore.",
            )

    except HTTPException as ex:
        raise ex

    except Exception as e:
        logger.exception("Error deleting embeddings.", error=e)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/chat", tags=["Chat API"], summary="Get chat response")
async def query_chat(request: ChatRequest):
    """
    Handles a chat request by processing the query through a series of models and returning the response.

    Args:
        request (ChatRequest): The chat request containing the input and response type configuration options.

    Returns:
        Union[str, StreamingResponse]: The response to the chat query. If streaming is enabled, returns a StreamingResponse object; otherwise, returns the response as a string.

    Raises:
        HHTTPException: If the input question text is empty or not provided, a HTTPStatus.UNPROCESSABLE_ENTITY is returned.
    """

    if not request.input or request.input == "":
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail="Question is required."
        )

    st = time.perf_counter()

    retriever = get_retriever(config.ENABLE_RERANK)

    rag_chain = build_chain(retriever)

    if request.stream == False:
        response = rag_chain.invoke(request.input)
        et = time.perf_counter()
        logger.info(f"Time taken {et - st}")

        return {"status": "Success", "metadata": response}

    else:

        return StreamingResponse(
            process_query(rag_chain, request.input), media_type="text/event-stream"
        )


if __name__ == "__main__":
    uvicorn.run("app", host="0.0.0.0", port=8888)
