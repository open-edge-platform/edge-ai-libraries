# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pymilvus import MilvusClient

import os
import requests

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", 19530))
MILVUS_URI = f"http://{MILVUS_HOST}:{MILVUS_PORT}"

EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", None)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "openai/clip-vit-base-patch32")

class MilvusRetriever:
    def __init__(self, collection_name="default"):
        self.collection_name = collection_name
        self.client = MilvusClient(uri=MILVUS_URI)
        self.model_name = EMBEDDING_MODEL_NAME
        self.embed_url = EMBEDDING_BASE_URL

    def get_text_embedding(self, query):
        headers = { 'Content-Type': 'application/json'}

        payload = {
            "input": {
                "type": "text",
                "text": query
            },
            "model": EMBEDDING_MODEL_NAME,
            "encoding_format": "float"
        }
    
        response = requests.post(f"{self.embed_url}/embeddings", json=payload, headers=headers, timeout=10)
        data = response.json()
        embedding = data["embedding"]
        return [embedding]
        
    def get_image_embedding(self, image_base64):
        headers = {'Content-Type': 'application/json'}

        payload = {
            "model": EMBEDDING_MODEL_NAME,
            "encoding_format": "float",
            "input": {
                "type": "image_base64",
                "image_base64": image_base64
            }
        }

        response = requests.post(f"{self.embed_url}/embeddings", json=payload, headers=headers, timeout=10)
        data = response.json()
        embedding = data.get("embedding")
        return [embedding]

    def search(self, query=None, image_base64=None, filters=None, top_k=5):
        # Validate input
        if not query and not image_base64:
            raise ValueError("Either 'query' or 'image_base64' must be provided.")
        if query and image_base64:
            raise ValueError("Provide only one of 'query' or 'image_base64', not both.")

        # Get the embedding for the query or image
        if query:
            embedding = self.get_text_embedding(query)
        else:
            embedding = self.get_image_embedding(image_base64)

        if embedding is None:
            raise Exception("Failed to get embedding for the input.")

        # Construct filters if provided
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

