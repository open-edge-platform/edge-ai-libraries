# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import copy
import faiss
import requests
from pathlib import Path

from moviepy.editor import VideoFileClip
from PIL import Image


from dependency.clip_ov.mm_embedding import EmbeddingModel
from detector import Detector
from utils import preprocess_image, generate_unique_id
from milvus_client import MilvusClientWrapper



DEVICE = os.getenv("DEVICE", "CPU")
LOCAL_EMBED_MODEL_ID = os.getenv("LOCAL_EMBED_MODEL_ID", "CLIP-ViT-H-14")
MODEL_DIR = "/home/user/models"


def create_milvus_data(embedding, meta=None):
    data = {}
    data["id"] = generate_unique_id()
    data["meta"] = meta
    data["vector"] = embedding.tolist()[0]
    return data

class Indexer:
    def __init__(self):
        # if not self.check_db_service():
        #     print("DB service is not available. Exiting.")
        #     exit(1)

        self.model_id = LOCAL_EMBED_MODEL_ID
        self.model_path = MODEL_DIR
        self.device = DEVICE

        self.model = EmbeddingModel().image_model
        self.ireq = self.model.create_infer_request()
        self.detector = Detector(device=DEVICE)

        _, _, self.h, self.w = self.model.inputs[0].shape

        self.init_db_client()

        self.id_map = {}

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

    def init_db_client(self, collection_name="default"):
        self.client = MilvusClientWrapper()
        self.collection_name = collection_name
        m, dim = self.model.outputs[0].shape
        self.client.create_collection(dim, collection_name=self.collection_name)

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
            
    def process_video(self, video_path, meta, frame_interval=15, minimal_duration=1, do_detect_and_crop=True):
        entities = []
        video = VideoFileClip(video_path)

        frame_counter = 0
        frame_interval = int(frame_interval)
        fps = video.fps
        for frame in video.iter_frames():
            if frame_counter % frame_interval == 0:
                image = Image.fromarray(frame)
                seconds = frame_counter / fps
                meta_data = copy.deepcopy(meta)
                meta_data["video_pin_second"] = seconds
                if do_detect_and_crop:
                    crops = self.detector.get_cropped_images(image)
                    for crop in crops:
                        crop = preprocess_image(crop, shape=[self.w, self.h])
                        embedding = self.ireq.infer({'x': crop[None]}).to_tuple()[0]
                        node = create_milvus_data(embedding, meta_data)
                        entities.append(node)
                        self.update_id_map(meta_data["file_path"], node["id"])
                image = preprocess_image(image, shape=[self.w, self.h])
                embedding = self.ireq.infer({'x': image[None]}).to_tuple()[0]
                node = create_milvus_data(embedding, meta_data)
                entities.append(node)
                self.update_id_map(meta_data["file_path"], node["id"])
            frame_counter += 1
            
        return entities

    def process_image(self, image_path, meta, do_detect_and_crop=True):
        entities = []
        image = Image.open(image_path).convert('RGB')
        meta_data = copy.deepcopy(meta)
        if do_detect_and_crop:
            crops = self.detector.get_cropped_images(image)
            for crop in crops:
                crop = preprocess_image(crop, shape=[self.w, self.h])
                embedding = self.ireq.infer({'x': crop[None]}).to_tuple()[0]
                node = create_milvus_data(embedding, meta_data)
                entities.append(node)
                self.update_id_map(meta_data["file_path"], node["id"])
        
        image = preprocess_image(image, shape=[self.w, self.h])
        embedding = self.ireq.infer({'x': image[None]}).to_tuple()[0]
        node = create_milvus_data(embedding, meta_data)
        entities.append(node)
        self.update_id_map(meta_data["file_path"], node["id"])
        return entities

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


    def _submit_embedding(self, entities):
        # aync thread which collects embeddings and insert to db in batch
        pass

    def _build_index(self):
        # build index
        pass
