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
import logging

set_verbose(True)


from .custom_reranker import CustomReranker


import openlit

logging.basicConfig(level=logging.INFO)

otlp_endpoint = os.environ.get("OTLP_ENDPOINT", False)
if otlp_endpoint:
    openlit.init(
        otlp_endpoint=os.environ.get("OTLP_ENDPOINT", "http://localhost:4318"),
        application_name=os.environ.get("SERVICE_NAME", "chatqna"),
        environment=os.environ.get("SERVICE_ENV", "chatqna"),
    )
    logging.info("OpenLit initialized")


PG_CONNECTION_STRING = os.getenv("PG_CONNECTION_STRING")
MODEL_NAME = os.getenv("EMBEDDING_MODEL")
EMBEDDING_ENDPOINT_URL = os.getenv("EMBEDDING_ENDPOINT_URL")
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


model = EGAIModelServing(
    openai_api_key="EMPTY",
    openai_api_base="{}".format(ENDPOINT_URL),
    model_name=LLM_MODEL,
    top_p=0.99,
    temperature=0.01,
    streaming=True,
    callbacks=callbacks,
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


async def process_chunks(question_text):
    async for log in chain.astream(question_text):
        yield f"data: {log}\n\n"
