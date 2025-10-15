# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
from typing import Any

from langchain_vdms.vectorstores import VDMS, VDMS_Client

from src.common import Strings, logger
from src.core.util import read_config


class VDMSClient:
    def __init__(
        self,
        host: str,
        port: str,
        collection_name: str,
        embedder: Any,
        embedding_dimensions: int = 512,
        video_search_type: str = "similarity",
    ):

        logger.debug("Initializing VDMS Client . . .")
        self.host: str = host
        self.port: int = int(port)
        self.video_search_type = video_search_type
        self.constraints = None
        self.video_collection = collection_name
        self.video_embedder = embedder
        self.embedding_dimensions = embedding_dimensions

        # initialize_db
        self.init_db()

    def init_db(self):
        """
        Initializes VDMS Client and creates a langchain based vectorstore object.
        """

        try:
            logger.info("Connecting to VDMS DB server . . .")
            self.client = VDMS_Client(host=self.host, port=self.port)

            logger.info("Loading DB instance . . .")
            self.video_db = VDMS(
                client=self.client,
                embedding=self.video_embedder,
                collection_name=self.video_collection,
                engine="FaissFlat",
                distance_strategy="IP",
                embedding_dimensions=self.embedding_dimensions,
            )

        except Exception as ex:
            logger.error(f"Error in init_db: {ex}")
            raise Exception(Strings.db_conn_error)

    def store_embeddings(self, video_metadata_path: pathlib.Path) -> list[str]:
        """
        Reads the metadata json file. For each video in metdata file
        adds video metadata and its embeddings to the VDMS Vector DB.

        Args:
            video_metadata_path (pathlib.Path): Path to the metadata file containing video information.

        Returns:
            ids (list) : List of string IDs for videos added to vector DB.
        """

        # Read metadata file containing all information about video files
        metadata = read_config(video_metadata_path, type="json")
        logger.debug(f"Metadata stored : \n{metadata}")
        if metadata is None:
            raise Exception(Strings.metadata_read_error)

        logger.info("Storing embeddings . . .")
        videos_ids: list = []
        try:
            # Add video embeddings in db for each video
            for _, (_, data) in enumerate(metadata.items()):
                paths = [data["video_temp_path"]]
                del data["video_temp_path"]
                ids: list = self.video_db.add_videos(
                    metadatas=[data],
                    paths=paths,
                    start_time=[data["timestamp"]],
                    clip_duration=[data["clip_duration"]],
                )
                # Put list of ids returned into final videos_ids list.
                if ids:
                    videos_ids.extend(ids)

            return videos_ids
        except Exception as ex:
            logger.error(f"Error in store_embeddings: {ex}")
            raise Exception(Strings.embedding_error)

    def store_text_embedding(self, text: str, metadata: dict = {}) -> list[str]:
        """
        Embeds text and stores it in the VDMS Vector DB with associated metadata.

        Args:
            text (str): Text content to embed
            metadata (dict): [Optional] Metadata associated with the text.

        Returns:
            ids (list): List of string IDs for documents added to vector DB
        """

        logger.info("Storing text embedding...")
        try:
            text_metadata = [metadata] if metadata else []

            # Add text embedding to the vector DB
            ids: list = self.video_db.add_texts(texts=[text], metadatas=text_metadata)

            logger.debug(f"Text embedding stored with ids: {ids}")
            return ids

        except Exception as ex:
            logger.error(f"Error in occurred while storing text embeddings in VectorDB: {ex}")
            raise Exception(Strings.embedding_error)
