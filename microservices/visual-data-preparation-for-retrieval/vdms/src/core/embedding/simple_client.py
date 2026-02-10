# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import datetime
import pathlib
import time
import uuid
from typing import Any, List

import requests

from langchain_vdms.vectorstores import VDMS, VDMS_Client
from langchain_core.embeddings import Embeddings

from src.common import Strings, logger
from src.core.utils.config_utils import read_config


class DummyEmbedding(Embeddings):
    """
    Minimal dummy embedding class that satisfies VDMS requirements.
    We won't actually use these methods since we use add_from() directly.
    """
    
    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Won't be called since we use add_from() directly."""
        raise NotImplementedError("Use add_from() method instead")
    
    def embed_query(self, text: str) -> List[float]:
        """Won't be called since we use add_from() directly.""" 
        raise NotImplementedError("Use add_from() method instead")


class SimpleVDMSClient:
    """
    Dramatically simplified VDMS client that doesn't need any embedding service.
    
    This client:
    1. Creates VDMS without embedding function (just provides dimensions)
    2. Gets embeddings directly from multimodal API
    3. Stores embeddings using add_from() method
    
    Much simpler than the previous complex wrapper architecture!
    """
    
    def __init__(
        self,
        host: str,
        port: str,
        collection_name: str,
        embedding_dimensions: int = None,  # Make optional, will be auto-detected
        multimodal_api_url: str = None,
        model_name: str = None  # Must be explicitly provided
    ):
        logger.debug("Initializing Simple VDMS Client...")
        if not model_name:
            raise ValueError("Model name must be explicitly provided - no default model name is allowed")
        self.host = host
        self.port = int(port)
        self.collection_name = collection_name
        self.multimodal_api_url = multimodal_api_url
        self.model_name = model_name
        
        # Auto-detect embedding dimensions if not provided
        if embedding_dimensions is None:
            self.embedding_dimensions = self._detect_embedding_dimensions()
        else:
            self.embedding_dimensions = embedding_dimensions
            
        logger.info(f"Using embedding dimensions: {self.embedding_dimensions}")
        
        # Initialize VDMS without embedding function
        self.init_db()

    def _detect_embedding_dimensions(self) -> int:
        """
        Auto-detect embedding dimensions by sending a dummy request to the multimodal API.
        
        Returns:
            int: The detected embedding dimensions
            
        Raises:
            Exception: If dimensions cannot be detected or API is not available
        """
        if not self.multimodal_api_url:
            logger.warning("No multimodal API URL provided, using default 512 dimensions")
            return 512
            
        try:
            logger.info(f"Auto-detecting embedding dimensions from multimodal API: {self.multimodal_api_url}")
            logger.info(f"Using model: {self.model_name}")
            
            # Send a dummy text to get embedding dimensions
            payload = {
                "model": self.model_name,
                "input": {
                    "type": "text",
                    "text": "Sample input text for dimension detection"
                },
                "encoding_format": "float",
            }
            logger.debug(f"Sending request payload: {payload}")
            
            response = requests.post(
                self.multimodal_api_url,
                json=payload,
                timeout=30,
            )
            logger.info(f"Response status: {response.status_code}")
            response.raise_for_status()
            
            result = response.json()
            embedding = result["embedding"]
            dimensions = len(embedding)
            
            logger.info(f"Auto-detected embedding dimensions: {dimensions}")
            logger.debug(f"First 5 embedding values: {embedding[:5] if len(embedding) > 5 else embedding}")
            return dimensions
            
        except requests.RequestException as ex:
            logger.error(f"Failed to auto-detect embedding dimensions: {ex}")
            logger.error(f"Request URL: {self.multimodal_api_url}")
            logger.warning("Falling back to default 512 dimensions")
            return 512
        except (KeyError, TypeError) as ex:
            logger.error(f"Invalid response format from multimodal API: {ex}")
            logger.error(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            logger.warning("Falling back to default 512 dimensions")
            return 512

    def init_db(self):
        """Initialize VDMS Client without any embedding function."""
        try:
            logger.info(f"Connecting to VDMS DB server at {self.host}:{self.port}...")
            self.client = VDMS_Client(host=self.host, port=self.port)

            logger.info("Creating VDMS instance with minimal dummy embedding...")
            # Use minimal dummy embedding to satisfy VDMS requirements
            # We won't actually use it since we call add_from() directly
            dummy_embedding = DummyEmbedding(self.embedding_dimensions)
            
            self.video_db = VDMS(
                client=self.client,
                embedding=dummy_embedding,  # Minimal dummy embedding
                collection_name=self.collection_name,
                engine="FaissFlat",
                distance_strategy="IP",
                # distance_strategy="L2",
                embedding_dimensions=self.embedding_dimensions
            )
            logger.info("VDMS initialized successfully with dummy embedding (won't be used)")

        except Exception as ex:
            logger.error(f"Error in init_db: {ex}")
            raise Exception(Strings.db_conn_error)

    def _clean_metadata_for_vdms(self, metadata: dict) -> dict:
        """
        Clean metadata for VDMS storage by converting complex types to VDMS-compatible formats.
        
        VDMS accepts:
        - Integers (123)
        - Doubles (123.45)
        - Booleans (true/false)
        - Strings ("hello")
        
        VDMS does NOT accept:
        - Arrays/lists (must be converted to strings)
        - Objects/nested structures (must be flattened or converted to strings)
        """
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                # Skip None values
                continue
            elif isinstance(value, (str, int, float, bool)):
                # Primitive types are accepted as-is
                cleaned[key] = value
            elif isinstance(value, list):
                # Convert arrays to comma-separated strings
                if all(isinstance(item, (int, float)) for item in value):
                    # Numeric array - join as comma-separated string
                    cleaned[key] = ",".join(str(item) for item in value)
                else:
                    # Mixed or string array - join as comma-separated string
                    cleaned[key] = ",".join(str(item) for item in value)
            elif isinstance(value, dict):
                # Convert objects to JSON strings
                import json
                cleaned[key] = json.dumps(value)
            else:
                # Convert any other type to string
                cleaned[key] = str(value)
        
        return cleaned

    def _store_embeddings(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadatas: List[dict],
    ) -> List[str]:
        """Store embeddings using the langchain-vdms vector store APIs."""

        if not embeddings:
            return []

        logger.info("Starting VDMS storage for %d embeddings", len(embeddings))
        batch_size = 200
        generated_ids: List[str] = []

        for start_idx in range(0, len(embeddings), batch_size):
            end_idx = min(start_idx + batch_size, len(embeddings))

            batch_embeddings = embeddings[start_idx:end_idx]
            batch_texts = texts[start_idx:end_idx]
            batch_metadatas = metadatas[start_idx:end_idx]
            batch_ids = [str(uuid.uuid4()) for _ in batch_embeddings]

            try:
                inserted_ids = self.video_db.add_from(
                    texts=batch_texts,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas,
                    ids=batch_ids,
                    batch_size=batch_size,
                )
            except Exception as exc:
                logger.error(
                    "VDMS add_from failed for batch %d-%d: %s",
                    start_idx,
                    end_idx - 1,
                    exc,
                )
                raise

            if not inserted_ids or len(inserted_ids) != len(batch_ids):
                raise ValueError(
                    "VDMS add_from returned unexpected result size. "
                    f"Expected {len(batch_ids)}, received {len(inserted_ids) if inserted_ids else 0}."
                )

            generated_ids.extend(inserted_ids)

        self.video_db.check_and_update_properties()
        logger.info("Stored %d embeddings in VDMS", len(generated_ids))
        return generated_ids

    def store_frame_embeddings(self, embeddings: List[List[float]], frame_metadatas: List[dict]) -> List[str]:
        """
        Store frame embeddings using optimized approach similar to SDK mode.
        
        Args:
            embeddings: Pre-computed embeddings from multimodal service
            frame_metadatas: Metadata for each frame
            
        Returns:
            List of IDs for stored embeddings
        """
        try:
            start_time = time.time()
            logger.info("Storing %d frame embeddings...", len(embeddings))
            logger.debug("Embedding sample length: %s", len(embeddings[0]) if embeddings and embeddings[0] else "unknown")

            if len(embeddings) != len(frame_metadatas):
                raise ValueError(f"Mismatch: {len(embeddings)} embeddings vs {len(frame_metadatas)} metadata entries")

            frame_texts = []
            cleaned_metadatas = []

            for index, metadata in enumerate(frame_metadatas):
                video_id = metadata.get("video_id", "unknown")
                frame_num = metadata.get("frame_number", index)
                frame_type = metadata.get("frame_type", "full_frame")
                crop_index = metadata.get("crop_index")

                # Guarantee a created_at timestamp for downstream time filtering.
                if not metadata.get("created_at"):
                    date_time_obj = metadata.get("date_time")
                    if isinstance(date_time_obj, dict) and "_date" in date_time_obj:
                        metadata["created_at"] = date_time_obj.get("_date")
                    else:
                        metadata["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

                if frame_type == "detected_crop" and crop_index is not None:
                    frame_text = f"frame_{frame_num}_crop_{crop_index}_{video_id}"
                else:
                    frame_text = f"frame_{frame_num}_{video_id}"

                cleaned_metadata = self._clean_metadata_for_vdms(metadata)
                frame_texts.append(frame_text)
                cleaned_metadatas.append(cleaned_metadata)

            logger.debug("Prepared metadata for %d frames", len(frame_texts))

            ids = self._store_embeddings(
                embeddings=embeddings,
                texts=frame_texts,
                metadatas=cleaned_metadatas,
            )

            total_time = time.time() - start_time
            logger.info("Stored %d embeddings in %.3fs", len(ids), total_time)
            return ids

        except Exception as ex:
            total_time = time.time() - start_time if "start_time" in locals() else 0
            logger.error(f"store_frame_embeddings() failed after {total_time:.3f}s")
            logger.error(f"Error: {ex}")
            logger.error(f"Error type: {type(ex).__name__}")
            raise Exception(Strings.embedding_error)

    def store_embeddings_from_manifest(self, video_metadata_path: pathlib.Path) -> dict:
        """
        Process frame metadata and store embeddings, returning timing metrics.
        
        Args:
            video_metadata_path: Path to video metadata file
            
        Returns:
            Dictionary containing stored IDs and stage timings
        """
        metadata = read_config(video_metadata_path, type="json")
        if metadata is None:
            raise Exception(Strings.metadata_read_error)

        logger.info("Processing frame metadata for embedding storage...")

        try:
            debug_path = "/tmp/debug_metadata.json"
            with open(debug_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
            logger.info("Debug: Metadata saved to %s for inspection", debug_path)
        except Exception as exc:
            logger.debug("Debug metadata dump skipped: %s", exc)

        frames_manifest_path = None
        for _, data in metadata.items():
            if isinstance(data, dict) and "frames_manifest_path" in data:
                frames_manifest_path = data["frames_manifest_path"]
                break

        if frames_manifest_path and self.multimodal_api_url:
            extracted_frames = 0
            post_detection_items = 0
            try:
                with open(frames_manifest_path, "r") as manifest_file:
                    manifest = json.load(manifest_file)
                extracted_frames = manifest.get("total_frames") or len(manifest.get("frames", []))
                post_detection_items = manifest.get("total_metadata_entries") or extracted_frames
            except Exception as exc:
                logger.debug("Unable to read manifest for counts: %s", exc)

            embedding_start = time.time()
            embeddings = self._get_embeddings_from_manifest(frames_manifest_path)
            embedding_time = time.time() - embedding_start

            frame_metadatas = []
            for _, data in metadata.items():
                clean_metadata = {
                    k: v
                    for k, v in data.items()
                    if k not in ["image_path", "video_temp_path", "frames_manifest_path"]
                }
                frame_metadatas.append(clean_metadata)

            storage_start = time.time()
            ids = self.store_frame_embeddings(embeddings, frame_metadatas)
            storage_time = time.time() - storage_start

            return {
                "ids": ids,
                "embedding_time": embedding_time,
                "storage_time": storage_time,
                "post_detection_items": post_detection_items or len(frame_metadatas),
                "extracted_frames": extracted_frames or len(frame_metadatas),
            }

        # Fallback: process frames individually
        return self._process_individual_frames(metadata)

    def _get_embeddings_from_manifest(self, frames_manifest_path: str) -> List[List[float]]:
        """Get embeddings from multimodal API using frames manifest."""
        if not self.multimodal_api_url:
            raise ValueError("Multimodal API URL not configured")

        start_time = time.time()
        try:
            logger.info("Processing frames manifest: %s", frames_manifest_path)

            response = requests.post(
                self.multimodal_api_url,
                json={
                    "model": self.model_name,
                    "input": {
                        "type": "frames_batch",
                        "frames_manifest_path": frames_manifest_path,
                    },
                    "encoding_format": "float",
                },
                timeout=120,
            )
            response.raise_for_status()
            embeddings = response.json()["embedding"]

            elapsed = time.time() - start_time
            logger.info("Retrieved %d embeddings from multimodal API in %.3fs", len(embeddings), elapsed)
            return embeddings

        except requests.RequestException as ex:
            logger.error(f"Error getting embeddings from API: {ex}")
            raise Exception(Strings.embedding_error) from ex
        except Exception as ex:
            logger.error(f"Error processing manifest: {ex}")
            raise Exception(Strings.embedding_error) from ex

    def _process_individual_frames(self, metadata: dict) -> dict:
        """Fallback: process individual frames."""
        logger.info("Processing individual frames...")
        logger.info("Metadata contains %d entries", len(metadata))

        logger.debug("Sample metadata entries:")
        for index, (key, data) in enumerate(metadata.items()):
            if index < 3:
                logger.debug("Entry %d: %s -> %s", index, key, data)

        all_ids: List[str] = []
        embedding_time_total = 0.0
        storage_time_total = 0.0

        for key, data in metadata.items():
            logger.debug("Processing metadata entry: %s", key)
            logger.debug("Data keys: %s", list(data.keys()))

            if "image_path" in data and self.multimodal_api_url:
                logger.info("Processing frame with image_path: %s", data["image_path"])
                embed_start = time.time()
                embedding = self._get_single_frame_embedding(data["image_path"])
                embedding_time_total += time.time() - embed_start

                frame_metadata = {
                    k: v
                    for k, v in data.items()
                    if k not in ["image_path", "video_temp_path", "frames_manifest_path"]
                }

                storage_start = time.time()
                ids = self.store_frame_embeddings([embedding], [frame_metadata])
                storage_time_total += time.time() - storage_start
                all_ids.extend(ids)
            else:
                if "image_path" not in data:
                    logger.warning("No image_path found in metadata entry: %s", key)
                    logger.debug("Available keys in %s: %s", key, list(data.keys()))
                if not self.multimodal_api_url:
                    logger.warning("No multimodal API URL configured")

        logger.info("Processed %d individual frames", len(all_ids))
        return {
            "ids": all_ids,
            "embedding_time": embedding_time_total,
            "storage_time": storage_time_total,
            "post_detection_items": len(all_ids),
            "extracted_frames": len(metadata),
        }

    def _get_single_frame_embedding(self, image_path: str) -> List[float]:
        """Get embedding for a single frame."""
        start_time = time.time()
        try:
            response = requests.post(
                self.multimodal_api_url,
                json={
                    "model": self.model_name,
                    "input": {
                        "type": "image_file",
                        "image_path": image_path,
                    },
                    "encoding_format": "float",
                },
                timeout=30,
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]
            logger.debug(
                "Retrieved single frame embedding in %.3fs from %s",
                time.time() - start_time,
                image_path,
            )
            return embedding

        except requests.RequestException as ex:
            logger.error(f"Error getting single frame embedding: {ex}")
            raise Exception(Strings.embedding_error) from ex

    def store_text_embedding(self, text: str, metadata: dict = {}) -> List[str]:
        """Store text embedding (if needed for compatibility)."""
        try:
            if not self.multimodal_api_url:
                raise ValueError("Multimodal API URL required for text embedding")

            request_start = time.time()
            response = requests.post(
                self.multimodal_api_url,
                json={
                    "model": self.model_name,
                    "input": {"type": "text", "text": text},
                    "encoding_format": "float",
                },
                timeout=30,
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]
            logger.debug(
                "Generated text embedding in %.3fs",
                time.time() - request_start,
            )

            import uuid

            text_id = str(uuid.uuid4())
            ids = self.video_db.add_from(
                texts=[text],
                embeddings=[embedding],
                ids=[text_id],
                metadatas=[metadata],
            )

            logger.info("Stored text embedding with ID: %s", ids[0])
            return ids

        except Exception as ex:
            logger.error(f"Error storing text embedding: {ex}")
            raise Exception(Strings.embedding_error)

    def store_text_embedding_with_vector(self, text: str, embedding_vector: List[float], metadata: dict = {}) -> List[str]:
        """
        Store text with pre-computed embedding vector (e.g., from Qwen).
        
        Args:
            text: The text content
            embedding_vector: Pre-computed embedding vector
            metadata: Metadata dictionary
            
        Returns:
            List of IDs of the stored embeddings
        """
        try:
            if not embedding_vector:
                raise ValueError("Embedding vector cannot be empty")

            import uuid

            text_id = str(uuid.uuid4())
            ids = self.video_db.add_from(
                texts=[text],
                embeddings=[embedding_vector],
                ids=[text_id],
                metadatas=[metadata],
            )

            logger.info("Stored text with pre-computed embedding, ID: %s", ids[0])
            return ids

        except Exception as ex:
            logger.error(f"Error storing text with pre-computed embedding: {ex}")
            raise Exception(Strings.embedding_error)
