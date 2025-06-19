# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
from typing import Any

from langchain_community.vectorstores import VDMS
from langchain_community.vectorstores.vdms import VDMS_Client
from langchain_core.runnables import ConfigurableField

from src.common import Strings
from src.core.embedding import vCLIPEmbeddings
from src.core.embedding_wrapper import vCLIPEmbeddingsWrapper
from src.core.util import read_config
from src.logger import logger


class VDMSClient:
    def __init__(
        self,
        host: str,
        port: str,
        collection_name: str,
        model: Any,
        video_metadata_path: pathlib.Path,
        embedding_dimensions: int = 512,
        video_search_type: str = "similarity",
    ):

        logger.debug("Initializing VDMS Client . . .")
        self.host: str = host
        self.port: int = int(port)
        self.video_search_type = video_search_type
        self.constraints = None
        self.video_collection = collection_name
        if isinstance(model, vCLIPEmbeddingsWrapper):
            self.video_embedder = model
        else:
            self.video_embedder = vCLIPEmbeddings(model=model)
        self.embedding_dimensions = embedding_dimensions
        self.video_metadata_path = video_metadata_path

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

    def store_embeddings(self) -> list[str]:
        """
        Reads the metadata json file. For each video in metdata file
        adds video metadata and its embeddings to the VDMS Vector DB.

        Args:
            None

        Returns:
            ids (list) : List of string IDs for videos added to vector DB.
        """

        # Read metadata file containing all information about video files
        metadata = read_config(self.video_metadata_path, type="json")
        logger.info(f"store_embeddings Metadata: \n{metadata}")
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
