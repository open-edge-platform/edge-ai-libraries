# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import uvicorn
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from .chain import process_chunks
import httpx
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI(title="Chat Question and Answer", root_path="/v1/chatqna")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(
        ","
    ),  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=os.getenv("CORS_ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("CORS_ALLOW_HEADERS", "*").split(","),
)

# health check LLM model server
async def check_server_health(host, server_type):
    if host.startswith(("vllm", "text", "tei")):
        return await check_health(f"http://{host}/health", server_type)
    elif host.startswith(("ovms", "openvino")):
        return await check_health(f"http://{host}/v2/health/ready", server_type)
    else:
        raise HTTPException(status_code=503, detail=f"Unknown server type for {server_type}")

async def check_health(url, server_type):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return {"status": "healthy", "details": f"{server_type} is ready to serve"}
            else:
                raise HTTPException(status_code=503, detail=f"{server_type} is not ready to accept connections, please try after a few minutes")
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail=f"{server_type} is not ready to accept connections, please try after a few minutes")

@app.get("/")
async def redirect_root_to_docs():
    return RedirectResponse("/docs")


class QuestionRequest(BaseModel):
    input: str
    max_tokens: int


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify if the LLM and embedding model servers are ready to serve connections.

    Returns:
        The status of the LLM and embedding model servers.
    """
    endpoint_url = os.getenv("ENDPOINT_URL")
    embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT_URL")

    if not endpoint_url or not embedding_endpoint:
        raise HTTPException(status_code=503, detail="ENDPOINT_URL or EMBEDDING_ENDPOINT_URL is not set")

    result = []
    model_host = endpoint_url.split("//")[-1].split("/")[0].lower()
    #health check LLM model server
    result.append(await check_server_health(model_host, "LLM model server"))

    embed_host = embedding_endpoint.split("//")[-1].split("/")[0].lower()
    #health check Embedding model server
    result.append(await check_server_health(embed_host, "Embedding model server"))    
    
    if any(status["status"] != "healthy" for status in result):
        raise HTTPException(status_code=503, detail=f"LLM/Embedding model server is not ready")

    return result

@app.get("/model")
async def get_llm_model():
    """
    Endpoint to get the current LLM model.

    Returns:
        The current LLM model.
    """
    llm_model = os.getenv("LLM_MODEL")
    if not llm_model:
        raise HTTPException(status_code=503, detail="LLM_MODEL is not set")
    return {"status": "success", "llm_model": llm_model}

@app.post("/chat", response_class=StreamingResponse)
async def query_chain(payload: QuestionRequest):
    """
    Handles POST requests to the /chat endpoint.

    This endpoint receives a question in the form of a JSON payload, validates the input,
    and returns a streaming response with the processed chunks of the question text.

    Args:
        payload (QuestionRequest): The request payload containing the input question text
        max_tokens (int): The maximum number of tokens to process. Defaults to 512 if not provided.
        or set to 1024 if provided.

    Returns:
        StreamingResponse: A streaming response with the processed chunks of the question text.

    Raises:
        HTTPException: If the input question text is empty or not provided, a 422 status code is returned.
    """
    try:
        question_text = payload.input
        max_tokens = payload.max_tokens if payload.max_tokens else 512
        if max_tokens > 1024:
            raise HTTPException(status_code=422, detail="max tokens cannot be greater than 1024")
        if not question_text or question_text == "":
            raise HTTPException(status_code=422, detail="Question is required")
        
        # Additional validation
        if len(question_text.strip()) == 0:
            raise HTTPException(status_code=422, detail="Question cannot be empty or whitespace only")
            
        return StreamingResponse(process_chunks(question_text, max_tokens), media_type="text/event-stream")
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

FastAPIInstrumentor.instrument_app(app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=True)
