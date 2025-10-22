

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pymilvus import MilvusClient

from dependency.clip_ov.mm_embedding import EmbeddingModel

import os
import requests
import numpy as np

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", 19530))
MILVUS_URI = f"http://{MILVUS_HOST}:{MILVUS_PORT}"

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", None)
VCLIP_MODEL = os.getenv("VCLIP_MODEL", "openai/clip-vit-base-patch32")

class MilvusRetriever:
    def __init__(self, collection_name="default"):
        self.collection_name = collection_name
        self.client = MilvusClient(uri=MILVUS_URI)
        self.embed_url = EMBEDDING_BASE_URL
        if not self.embed_url:
            self.embedding_model = EmbeddingModel()

    def get_text_embedding(self, query):
        if self.embed_url:
            headers = { 'Content-Type': 'application/json'}

            payload = {
                "input": {
                    "type": "text",
                    "text": query
                },
                "model": VCLIP_MODEL,
                "encoding_format": "float"
            }
        
            response = requests.post(f"{self.embed_url}/embeddings", json=payload, headers=headers, timeout=10)
            data = response.json()
            embedding = data["embedding"]
            return [embedding]
        else:
            embedding = self.embedding_model.get_text_embedding(query)
            return embedding

    def search(self, query, filters=None, top_k=5):
        # Get the embedding for the query
        embedding = self.get_text_embedding(query)
        if embedding is None:
            raise Exception("Failed to get embedding for the query.")

        if filters:
            search_filter = ''
            filter_params = {}
            for key, value in filters.items():
                if key == "timestamp_start":
                    if search_filter:
                        search_filter += ' AND '
                    filter_params["timestamp_start"] = filters["timestamp_start"]
                    search_filter += 'meta["timestamp"] >= {timestamp_start}'
                if key == "timestamp_end":
                    filter_params["timestamp_end"] = filters["timestamp_end"]
                    if search_filter:
                        search_filter += ' AND '
                    search_filter += 'meta["timestamp"] <= {timestamp_end}'
                if key not in ["timestamp_start", "timestamp_end"]:
                    filter_params["label"] = [value]
                    if search_filter:
                        search_filter += ' AND '
                    search_filter += f'meta["{key}"] IN '
                    search_filter += '{label}'

            results = self.client.search(
                collection_name=self.collection_name,
                data=embedding,
                filter=search_filter,
                filter_params=filter_params,
                output_fields=["meta"],
                limit=top_k,  # Max number of search results to return
                search_params={"params": {}},  # Search parameters
            )
            if results:
                results = results[0]

        else:
            results = self.client.search(
                collection_name=self.collection_name,
                data=embedding,
                output_fields=["meta"],
                limit=top_k,  # Max number of search results to return
                search_params={"params": {}},  # Search parameters
            )
            if results:
                results = results[0]

        return results

