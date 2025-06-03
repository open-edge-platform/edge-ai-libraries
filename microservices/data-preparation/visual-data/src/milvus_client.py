# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

from pymilvus import MilvusClient, DataType, Collection

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", 19530))
MILVUS_URI = f"http://{MILVUS_HOST}:{MILVUS_PORT}"


class MilvusClientWrapper:
    def __init__(self, host: str = MILVUS_HOST, port: int = MILVUS_PORT):
        self.client = MilvusClient(uri=MILVUS_URI)

    def load_collection(self, collection_name: str):
        try:
            self.client.load_collection(collection_name=collection_name)
            res = self.client.get_load_state(
                collection_name=collection_name
            )
            return res["state"]
        except Exception as e:
            print(f"Failed to load collection {collection_name}: {e}")
            return None

    def create_collection(self, dim: int, collection_name: str = "default", index_params=None, schema=None):
        if self.load_collection(collection_name) == 3:  # loaded
            print(f"Collection {collection_name} already exists and is loaded.")
            return
        
        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=True,
        )

        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, auto_id=False)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field(field_name="meta", datatype=DataType.JSON)

        index_params = MilvusClient.prepare_index_params()

        index_params.add_index(
            field_name="vector", # Name of the vector field to be indexed
            index_type="FLAT", # Type of the index to create
            index_name="vector_index", # Name of the index to create
            metric_type="IP", # Metric type used to measure similarity
            params={} # No additional parameters required for FLAT
        )

        self.client.create_collection(
            collection_name=collection_name,
            auto_id=False,
            dimension=dim,
            index_params=index_params,
            schema=schema,
            enable_dynamic_field=True,
        )

    def insert(self, data: list, collection_name):
        res = self.client.insert(
                collection_name=collection_name,
                data=data,
            )
        
        return res
    
    def delete(self, ids: list, collection_name: str):
        res = self.client.delete(
                collection_name=collection_name,
                ids=ids,
            )
        
        return res
    
    def get(self, ids: list, output_fileds: list, collection_name: str):
        res = self.client.get(
                collection_name=collection_name,
                ids=ids,
                output_fields=output_fileds
            )
        
        return res
    
    def query_all(self, collection_name: str, output_fields: list = []):
        res = self.client.query(
                collection_name=collection_name,
                filter="id >= 0",
                output_fields=output_fields
            )
        
        return res