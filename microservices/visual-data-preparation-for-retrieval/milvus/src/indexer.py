# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import copy
import json
import requests
import numpy as np
from pathlib import Path

from moviepy.editor import VideoFileClip
from PIL import Image

from detector import Detector
from utils import generate_unique_id, encode_image_to_base64
from milvus_client import MilvusClientWrapper
from embedding_client import create_embedding_client


DEVICE = os.getenv("DEVICE", "CPU")


def create_milvus_data(embedding, meta=None):
    data = {}
    data["id"] = generate_unique_id()
    data["text"] = ""
    data["meta"] = meta
    data["vector"] = embedding
    return data

class Indexer:
    def __init__(self, collection_name="default"):
        # if not self.check_db_service():
        #     print("DB service is not available. Exiting.")
        #     exit(1)

        self.embedding_client = create_embedding_client()

        self.detector = Detector(device=DEVICE)

        self.id_map = {}
        self.db_inited = False
        self.client = MilvusClientWrapper()
        self.collection_name = collection_name

        if self.client.load_collection(collection_name=self.collection_name) == 3:  # loaded
            print(f"Collection '{self.collection_name}' already exist.")
            self.db_inited = True
            self.recover_id_map()


    def check_db_service(self, url="http://localhost:9091/healthz"):
        try:
            response = requests.get(url, timeout=10)  # Set a timeout to avoid hanging
            if response.status_code == 200:
                return True
            else:
                print(f"Service health check failed with status code: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to connect to the service: {e}")
            return False

    def init_db_client(self, dim):
        self.client.create_collection(dim, collection_name=self.collection_name)

        self.db_inited = True
        self.recover_id_map()

    def update_id_map(self, file_path, node_id):
        if file_path not in self.id_map:
            self.id_map[file_path] = []
        self.id_map[file_path].append(node_id)

    def recover_id_map(self):
        res = self.client.query_all(self.collection_name, output_fields=["id", "meta"])
        if not res:
            print("No data found in the collection.")
            return
        for item in res:
            if "file_path" in item["meta"]:
                file_path = item["meta"]["file_path"]
                if file_path not in self.id_map:
                    self.id_map[file_path] = []
                self.id_map[file_path].append(item["id"])

    def count_files(self):
        files = set()
        for key, value in self.id_map.items():
            if key not in files:  
                files.add(key)    
        return len(files)
    
    def query_file(self, file_path):
        ids = []
        if file_path in self.id_map:
            ids = self.id_map[file_path]

        res = None
        # TBD: are vector and meta needed from db?
        # res = self.client.get(
        #     collection_name=self.collection_name,
        #     ids=ids,
        #     output_fields=["id", "vector", "meta"]
        # )
        
        return res, ids
        
    
    def delete_by_file_path(self, file_path):
        ids = []
        if file_path in self.id_map:
            ids = self.id_map[file_path]
            res = self.client.delete(
                collection_name=self.collection_name,
                ids=ids,
            )
            del self.id_map[file_path]
        else:
            print(f"File {file_path} not found in db.")
        return res, ids
    
    def delete_all(self):
        if not self.id_map:
            return None, []
        ids = []
        for key, value in self.id_map.items():
            ids.extend(value)
        res = self.client.delete(
            collection_name=self.collection_name,
            ids=ids,
        )
        self.id_map.clear()

        return res, ids

    def _build_entities_from_embeddings(self, embeddings, metas):
        """Build entity list from embeddings and metadata, initializing DB if needed."""
        entities = []
        for embedding, meta_data in zip(embeddings, metas):
            if not self.db_inited:
                self.init_db_client(len(embedding))
            node = create_milvus_data(embedding, meta_data)
            entities.append(node)
            self.update_id_map(meta_data["file_path"], node["id"])
        return entities

    def process_video(self, video_path, meta, frame_interval=15, minimal_duration=1, do_detect_and_crop=True):
        video = VideoFileClip(video_path)
        frame_interval = int(frame_interval)
        fps = video.fps

        # First pass: collect all images and metadata
        pending_images = []
        pending_metas = []

        frame_counter = 0
        for frame in video.iter_frames():
            if frame_counter % frame_interval == 0:
                image = Image.fromarray(frame)
                seconds = frame_counter / fps
                meta_data = copy.deepcopy(meta)
                meta_data["video_pin_second"] = seconds
                if do_detect_and_crop:
                    crops = self.detector.get_cropped_images(image)
                    for crop in crops:
                        pending_images.append(crop)
                        pending_metas.append(copy.deepcopy(meta_data))

                pending_images.append(image)
                pending_metas.append(meta_data)
            frame_counter += 1

        video.close()

        # Second pass: embed in batch and build entities
        if not pending_images:
            return []
        embeddings = self.embedding_client.embed_images(pending_images)
        return self._build_entities_from_embeddings(embeddings, pending_metas)

    def process_image(self, image_path, meta, do_detect_and_crop=True):
        image = Image.open(image_path).convert('RGB')
        meta_data = copy.deepcopy(meta)

        pending_images = []
        pending_metas = []

        if do_detect_and_crop:
            crops = self.detector.get_cropped_images(image)
            for crop in crops:
                pending_images.append(crop)
                pending_metas.append(copy.deepcopy(meta_data))
        
        pending_images.append(image)
        pending_metas.append(meta_data)

        embeddings = self.embedding_client.embed_images(pending_images)
        return self._build_entities_from_embeddings(embeddings, pending_metas)

    def add_embedding(self, files, metas, **kwargs):
        if len(files) != len(metas):
            raise ValueError(f"Number of files and metas must be the same. files: {len(files)}, metas: {len(metas)}")
        
        frame_interval = kwargs.get("frame_interval", 15)
        minimal_duration = kwargs.get("minimal_duration", 1)
        do_detect_and_crop = kwargs.get("do_detect_and_crop", True)
        entities = []
        for file, meta in zip(files, metas):
            # print("processing file: ", file)
            if meta["file_path"] in self.id_map:
                print(f"File {file} already processed, skipping.")
                continue
            if file.lower().endswith(('.mp4')):
                meta["type"] = "local_video"
                entities.extend(self.process_video(file, meta, frame_interval, minimal_duration, do_detect_and_crop))
            elif file.lower().endswith(('.jpg', '.png', '.jpeg')):
                meta["type"] = "local_image"
                entities.extend(self.process_image(file, meta, do_detect_and_crop))
            else:
                print(f"Unsupported file type: {file}. Supported types are: jpg, png, mp4")

        res = {}
        if entities:
            res = self.client.insert(
                collection_name=self.collection_name,
                data=entities,
            )
        return res


    def _build_index(self):
        # build index
        pass
