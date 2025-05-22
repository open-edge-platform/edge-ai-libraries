# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from sqlalchemy.ext.asyncio import create_async_engine
from langchain.globals import set_verbose
from langchain.callbacks import streaming_stdout
from langchain_postgres.vectorstores import PGVector as EGAIVectorDB
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda,
)
from langchain_core.vectorstores import VectorStoreRetriever as EGAIVectorStoreRetriever
from langchain_community.llms import VLLMOpenAI as EGAIModelServing
from langchain_openai import OpenAIEmbeddings as EGAIEmbeddings
from .custom_reranker import CustomReranker
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

set_verbose(True)

logging.basicConfig(level=logging.INFO)

# Check if OTLP endpoint is set in environment variables
otlp_endpoint = os.environ.get("OTLP_ENDPOINT", False)

# Initialize OpenTelemetry
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

if otlp_endpoint:
    otlp_exporter = OTLPSpanExporter()
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)

PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")
MODEL_NAME = os.getenv("EMBEDDING_MODEL","BAAI/bge-small-en-v1.5")
EMBEDDING_ENDPOINT_URL = os.getenv("EMBEDDING_ENDPOINT_URL","http://localhost:6006")
COLLECTION_NAME = os.getenv("INDEX_NAME")
FETCH_K = os.getenv("FETCH_K")

engine = create_async_engine(PG_CONNECTION_STRING)

# Init Embeddings via Intel Edge GenerativeAI Suite
embedder = EGAIEmbeddings(
            openai_api_key="EMPTY",
            openai_api_base="{}".format(EMBEDDING_ENDPOINT_URL),
            model=MODEL_NAME,
            tiktoken_enabled=False
        )


knowledge_base = EGAIVectorDB(
    embeddings=embedder,
    collection_name=COLLECTION_NAME,
    connection=engine,
)
retriever = EGAIVectorStoreRetriever(
    vectorstore=knowledge_base,
    search_type="mmr",
    search_kwargs={"k": 1, "fetch_k": FETCH_K},
)

# Define our prompt
template = """
Use the following pieces of context from retrieved
dataset to answer the question. Do not make up an answer if there is no
context provided to help answer it.

Context:
---------
{context}

---------
Question: {question}
---------

Answer:
"""


prompt = ChatPromptTemplate.from_template(template)

ENDPOINT_URL = os.getenv("ENDPOINT_URL", "http://localhost:8080")
LLM_MODEL = os.getenv("LLM_MODEL", "Intel/neural-chat-7b-v3-3")
RERANKER_ENDPOINT = os.getenv("RERANKER_ENDPOINT", "http://localhost:9090/rerank")
callbacks = [streaming_stdout.StreamingStdOutCallbackHandler()]

async def process_chunks(question_text,max_tokens):
    model = EGAIModelServing(
        openai_api_key="EMPTY",
        openai_api_base="{}".format(ENDPOINT_URL),
        model_name=LLM_MODEL,
        top_p=0.99,
        temperature=0.01,
        streaming=True,
        callbacks=callbacks,
        seed=42,
        max_tokens=max_tokens,
        stop=["\n\n"]
    )

    re_ranker = CustomReranker(reranking_endpoint=RERANKER_ENDPOINT)
    re_ranker_lambda = RunnableLambda(re_ranker.rerank)

    # RAG Chain
    chain = (
        RunnableParallel({"context": retriever, "question": RunnablePassthrough()})
        | re_ranker_lambda
        | prompt
        | model
        | StrOutputParser()
    )
    # Run the chain with the question text
    async for log in chain.astream(question_text):
        yield f"data: {log}\n\n"
