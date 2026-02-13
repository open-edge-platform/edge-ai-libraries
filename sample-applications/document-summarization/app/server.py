# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import uvicorn
import shutil
import logging
import traceback
import openlit
import tempfile
from typing import Any
from openai import OpenAI
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.simple_summary_pack.llama_index.packs.simple_summary import SimpleSummaryPack
from llama_index.core import SimpleDirectoryReader
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.base.llms.types import CompletionResponse, CompletionResponseGen
from llama_index.core.llms.callbacks import llm_completion_callback
from app.config import Settings
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from llama_index.core.schema import Document as LlamaDocument


tmp_docs_dir = os.path.join(tempfile.gettempdir(), "docs")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check if OTLP endpoint is set in environment variables
otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", False)

config = Settings()

if not isinstance(trace.get_tracer_provider(), TracerProvider):
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)

    # Set up OTLP exporter and span processor
    if not otlp_endpoint:
        logger.warning("OTLP endpoint not set. OpenTelemetry will not be configured.")
    else:
        otlp_exporter = OTLPSpanExporter()
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        openlit.init(
            otlp_endpoint=otlp_endpoint,
            application_name=os.environ.get("OTEL_SERVICE_NAME", "document-summarization"),
            environment=os.environ.get("OTEL_SERVICE_ENV", "development"),
        )

        logger.info(f"Opentelemetry configured successfully with endpoint: {otlp_endpoint}")



LLM_INFERENCE_URL = config.LLM_ENDPOINT_URL or "http://ovms-service"
model_name = config.LLM_MODEL

app = FastAPI(root_path="/v1/docsum", title="Document Summarization API")

# Add CORS middleware to allow the Gradio UI to make requests to the FastAPI backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=config.CORS_ALLOW_METHODS.split(","),
    allow_headers=config.CORS_ALLOW_HEADERS.split(","),
)

# Update OpenAILike configuration with proper timeout and retry settings

model = OpenAILike(
    api_base="{}/v3".format(LLM_INFERENCE_URL),
    model=model_name,  
    is_chat_model=True,
    is_function_calling_model=False,
    timeout=600,  # Increased timeout for long responses
    max_retries=10,  # Allow more retries for transient failures
    api_key="not-needed"  # Some implementations require a non-empty API key
)


def save_uploaded_file(uploaded_file: UploadFile, destination: str):
    """
    Saves an uploaded file to the specified destination.

    Args:
        uploaded_file (UploadFile): The file object that has been uploaded.
        destination (str): The file path where the uploaded file should be saved.

    Returns:
        None
    """
    try:
        with open(destination, "wb+") as file_object:
            content = uploaded_file.file.read()
            file_object.write(content)
            logger.info(f"File saved successfully to {destination}. Size: {len(content)} bytes")
            # Reset file pointer for potential reuse
            uploaded_file.file.seek(0)
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        raise


def clean_directory(directory: str):
    """
    Remove all files and directories within the specified directory.

    Args:
        directory (str): The path to the directory to be cleaned.

    Raises:
        OSError: If an error occurs while deleting a file or directory.
    """
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)


def is_file_supported(file):
    _, file_extension = os.path.splitext(file)
    return file_extension in config.SUPPORTED_FILE_EXTENSIONS


def chunk_text_file(file_path, max_chars=2000):
    """Chunk a TXT file by full lines (no mid-line splits)."""
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    chunks, current_chunk = [], ""
    for line in lines:
        if len(current_chunk) + len(line) > max_chars:
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            current_chunk += line
    if current_chunk:
        chunks.append(current_chunk.strip())

    return [LlamaDocument(text=chunk, metadata={"file_path": file_path}) for chunk in chunks]


@app.get("/version")
def get_version():
    return {"version": "1.0"}


@app.post("/summarize/")
async def stream_data_endpoint(file: UploadFile = File(...), query: str = "Summarize the document"):
    """
    Endpoint to summarize a document.
    This endpoint accepts a file upload and a query string. It saves the uploaded file to the "docs" directory,
    loads the documents from the directory, and generates a summary using the SimpleSummaryPack. After processing,
    it cleans up the "docs" directory by removing all files.
    Args:
        file (UploadFile): The file to be uploaded and summarized.
        query (str): The query string for summarizing the document. Defaults to "Summarize the document".
    Returns:
        str: The summary of the document.
    """

    try:
        logger.info(f"Received file: {file.filename}, content-type: {file.content_type}, query: {query}")

        if not is_file_supported(file.filename):
            logger.warning(f"Rejected file: {file.filename} - Only {', '.join(config.SUPPORTED_FILE_EXTENSIONS)} files are allowed to upload")
            return JSONResponse(
                status_code=400,
                content={"message": f"Only {', '.join(config.SUPPORTED_FILE_EXTENSIONS)} files are allowed to upload."},
            )
        
        # Create a safe subdirectory inside the system temp dir
        os.makedirs(tmp_docs_dir, exist_ok=True)

        file_location = os.path.join(tmp_docs_dir, file.filename)

        save_uploaded_file(file, file_location)

        # Verify file exists and has content
        if not os.path.exists(file_location):
            logger.error(f"File not saved properly at {file_location}")
            return JSONResponse(status_code=500, content={"message": "Failed to save uploaded file"})

        file_size = os.path.getsize(file_location)
        logger.info(f"File saved at {file_location} with size {file_size} bytes")

        # 🔹 Load documents (with TXT chunking support)
        try:
            logger.info("Loading documents")
            if file.filename.endswith(".txt"):
                logger.info(f"Chunking TXT file before summarization with chunk size: {config.CHUNK_SIZE}")
                documents = chunk_text_file(file_location, max_chars=config.CHUNK_SIZE)
            else:
                documents = SimpleDirectoryReader(input_files=[file_location]).load_data()

            # Assign doc_ids for traceability
            doc_ids = []
            for i, doc in enumerate(documents):
                doc_id = f"{file.filename}_part{i}"
                doc.doc_id = doc_id
                doc_ids.append(doc_id)

            logger.info(f"Loaded {len(documents)} document(s) from {file_location}")
        except Exception as e:
            logger.error(f"Error loading documents: {str(e)}")
            return JSONResponse(status_code=500, content={"message": f"Failed to load document: {str(e)}"})

        try:
            logger.info("Initializing SimpleSummaryPack")
            simple_summary_pack = SimpleSummaryPack(
                documents,
                query=query,
                verbose=True,
                llm=model,
            )
            logger.info("Running SimpleSummaryPack for all chunks")
            all_summaries = []
            for doc_id in doc_ids:
                try:
                    summary = simple_summary_pack.run(doc_id)
                    # If run returns a generator/stream, join to string
                    if hasattr(summary, '__iter__') and not isinstance(summary, str):
                        summary = '\n'.join([s for s in summary])
                    all_summaries.append(summary)
                except Exception as e:
                    logger.error(f"Error summarizing chunk {doc_id}: {str(e)}")
            combined_summary = '\n\n'.join(all_summaries)
            logger.info("Successfully generated combined summary")

            # Second LLM call: distill a concise summary from chunk summaries
            logger.info("Running final LLM call to distill a concise summary from chunk summaries")
            final_doc = LlamaDocument(text=combined_summary, metadata={"file_path": file_location})
            final_doc.doc_id = f"{file.filename}_final"
            final_summary_pack = SimpleSummaryPack(
                [final_doc],
                query=query,
                verbose=True,
                llm=model,
            )
            final_doc_id = final_doc.doc_id
            try:
                final_summary = final_summary_pack.run(final_doc_id)
            except Exception as e:
                logger.error(f"Error generating final summary: {str(e)}")
                # fallback: yield the combined summary as a single chunk
                def fallback_gen():
                    yield combined_summary
                final_summary = fallback_gen()
            logger.info("Successfully generated distilled summary")
            return StreamingResponse(final_summary, media_type="text/event-stream")
        except Exception as e:
            logger.error(f"Error in processing: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(status_code=500, content={"message": f"Error processing document: {str(e)}"})

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"message": f"An error occurred: {str(e)}"})
    finally:
        try:
            if os.path.exists(tmp_docs_dir):
                logger.info(f"Cleaning {tmp_docs_dir} directory")
                clean_directory(tmp_docs_dir)
                logger.info("Directory cleaned successfully")
        except Exception as e:
            logger.error(f"Error cleaning directory: {str(e)}")

FastAPIInstrumentor.instrument_app(app)

if __name__ == "__main__":
    # Get API port and host from environment or use defaults
    port = int(config.API_PORT or "8090")
    host = "0.0.0.0"  # Uses 0.0.0.0 to allow external access

    # Start FastAPI with Uvicorn
    logger.info(f"Starting Document Summarization API on {host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=False)
    