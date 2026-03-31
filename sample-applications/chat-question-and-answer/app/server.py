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
from .agent import run_agent_stream, TOOLS
import httpx
from typing import List
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
        raise HTTPException(
            status_code=503, detail=f"Unknown server type for {server_type}"
        )


async def check_health(url, server_type):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "details": f"{server_type} is ready to serve",
                }
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"{server_type} is not ready to accept connections, please try after a few minutes",
                )
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail=f"{server_type} is not ready to accept connections, please try after a few minutes",
            )


@app.get("/")
async def redirect_root_to_docs():
    return RedirectResponse("/docs")


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class QuestionRequest(BaseModel):
    conversation_messages: List[Message]
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
        raise HTTPException(
            status_code=503, detail="ENDPOINT_URL or EMBEDDING_ENDPOINT_URL is not set"
        )

    result = []
    model_host = endpoint_url.split("//")[-1].split("/")[0].lower()
    # health check LLM model server
    result.append(await check_server_health(model_host, "LLM model server"))

    embed_host = embedding_endpoint.split("//")[-1].split("/")[0].lower()
    # health check Embedding model server
    result.append(await check_server_health(embed_host, "Embedding model server"))

    if any(status["status"] != "healthy" for status in result):
        raise HTTPException(
            status_code=503, detail=f"LLM/Embedding model server is not ready"
        )

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

    This endpoint receives a conversation history along with the question in the form of a JSON payload, validates
    the input, and returns a streaming response with the processed chunks of the question text.

    Args:
        payload (QuestionRequest): The request payload containing conversation history with the input question text
        max_tokens (int): The maximum number of tokens to process. Defaults to 512 if not provided.
        or set to 1024 if provided.

    Returns:
        StreamingResponse: A streaming response that delivers processed chunks generated from both the conversation
        history and the user question.

    Raises:
        HTTPException: If the input question text is empty or not provided, a 422 status code is returned.
    """
    try:
        # conversation_messages contain conversation history with roles and content along with current question
        conversation_messages = payload.conversation_messages
        question_text = conversation_messages[-1].content  # latest user message

        max_tokens = payload.max_tokens if payload.max_tokens else 512
        if max_tokens > 1024:
            raise HTTPException(
                status_code=422, detail="max tokens cannot be greater than 1024"
            )
        if not question_text or question_text == "":
            raise HTTPException(status_code=422, detail="Question is required")

        # Additional validation
        if len(question_text.strip()) == 0:
            raise HTTPException(
                status_code=422, detail="Question cannot be empty or whitespace only"
            )

        return StreamingResponse(
            process_chunks(conversation_messages, max_tokens),
            media_type="text/event-stream",
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/agent/health")
async def agent_health():
    """
    Returns the list of tools available to the ReAct agent.
    Useful for confirming the agent is set up correctly without running a full query.
    """
    tool_info = [{"name": t.name, "description": t.description} for t in TOOLS]
    return {"status": "ready", "tools": tool_info}


@app.post("/agent/chat", response_class=StreamingResponse)
async def agent_chat(payload: QuestionRequest):
    """
    Agentic chat endpoint powered by a LangGraph ReAct agent.

    The agent can use three tools to answer the question:
      - vector_search: queries the knowledge base
      - web_search: searches the web via DuckDuckGo
      - calculator: evaluates math expressions

    Returns a streaming SSE response. Intermediate steps (which tool is being
    called and its result) are prefixed with "[agent]" so the UI can
    display them separately from the final answer.

    Args:
        payload: Same QuestionRequest as /chat (conversation_messages + max_tokens).

    Returns:
        StreamingResponse with text/event-stream content-type.
    """
    try:
        conversation_messages = payload.conversation_messages
        question_text = conversation_messages[-1].content

        if not question_text or not question_text.strip():
            raise HTTPException(status_code=422, detail="Question is required")

        # Build conversation history string (all messages except the last)
        if len(conversation_messages) > 1:
            history_parts = []
            for msg in conversation_messages[:-1]:
                if hasattr(msg, "role") and hasattr(msg, "content") and msg.content:
                    history_parts.append(f"{msg.role}: {msg.content}")
            history = "\n".join(history_parts)
        else:
            history = ""

        return StreamingResponse(
            run_agent_stream(question_text, history),
            media_type="text/event-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


FastAPIInstrumentor.instrument_app(app)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=True)
