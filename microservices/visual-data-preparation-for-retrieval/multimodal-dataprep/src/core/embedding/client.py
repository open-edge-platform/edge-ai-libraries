# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SDK-based embedding client that stores embeddings produced by the MME SDK."""

import threading
import time
import traceback
from collections.abc import Iterable
from typing import Any
from typing import List
from typing import Optional

import numpy as np
from multimodal_embedding_serving import EmbeddingModel
from multimodal_embedding_serving import get_model_handler
from PIL import Image

from src.common import Strings
from src.common import logger
from src.common import settings
from src.core.vectorstores import get_vector_store


class EmbeddingClient:
    """
    Optimized embedding client using SDK-based embedding generation with vector store persistence.

    This client provides maximum performance by combining:
    1. SDK-based embedding generation (no HTTP overhead)
    2. Standard vector store APIs for durability across restarts
    3. Optimized batch processing for high-throughput storage

    Performance improvements:
    - Eliminates network latency for embedding generation
    - Uses optimized batch sizes for vector store operations
    - Aligns with standard persistence flows to maintain index continuity
    """
    @staticmethod
    def _to_list(embedding: Any) -> List[float]:
        """Convert an embedding tensor/array into a plain Python list."""
        if embedding is None:
            return []

        candidate = embedding
        # Normalize common tensor interfaces
        if hasattr(candidate, "detach"):
            candidate = candidate.detach()
        if hasattr(candidate, "cpu"):
            candidate = candidate.cpu()
        if hasattr(candidate, "numpy"):
            candidate = candidate.numpy()

        if hasattr(candidate, "tolist"):
            return candidate.tolist()

        if isinstance(candidate, list):
            return candidate

        try:
            if isinstance(candidate, Iterable) and not isinstance(candidate, (str, bytes)):
                return [float(x) for x in candidate]
            return [float(candidate)]
        except TypeError:
            return [float(candidate)]

    def __init__(
        self,
        model_id: str = "",
        device: str = "CPU",
        use_openvino: bool = False,
        ov_models_dir: Optional[str] = None,
        db_host: Optional[str] = None,
        db_port: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        """
        Initialize the SDK client with embedding model and the vector store.
        
        Args:
            model_id: Model identifier for embedding generation
            device: Device to run the model on (CPU, GPU, etc.)
            use_openvino: Whether to use OpenVINO optimization
            ov_models_dir: Directory for OpenVINO models
            db_host: Vector DB host (defaults to settings)
            db_port: Vector DB port (defaults to settings)  
            collection_name: Vector DB collection name (defaults to settings)
        """
        # Store embedding model configuration
        self.model_id = model_id
        self.device = device
        self.use_openvino = use_openvino
        self.ov_models_dir = ov_models_dir
        
        # Store Vector DB configuration  
        self.db_host = db_host or settings.VDMS_VDB_HOST
        self.db_port = db_port or settings.VDMS_VDB_PORT
        self.collection_name = collection_name or settings.DB_COLLECTION
        
        # Synchronization for vector store operations
        self._store_lock = threading.RLock()

        # Initialize the embedding model
        logger.info("Initializing embedding model: %s", model_id or "<unspecified>")
        self.model_handler = get_model_handler(
            model_id=model_id,
            device=device,
            ov_models_dir=ov_models_dir,
            use_openvino=use_openvino,
        )

        self.supports_text, self.supports_image = self._detect_modalities(model_id)

        logger.info("Loading embedding model...")
        self.model_handler.load_model()

        self.embedding_model = EmbeddingModel(self.model_handler)

        self.embedding_dimensions = self._resolve_embedding_dimensions()
        
        # Initialize vector store connection
        self._init_vector_store()

        logger.info("SDK client initialized with model: %s", self.model_id)
    
    def _detect_modalities(self, model_id: str) -> tuple[bool, bool]:
        text_supported = False
        image_supported = False

        if hasattr(self.model_handler, "supports_text"):
            try:
                text_supported = bool(self.model_handler.supports_text())
            except Exception as exc:
                logger.warning(
                    "Could not determine text support for %s: %s",
                    model_id,
                    exc,
                )
        else:
            logger.warning(
                "Model handler for %s is missing supports_text(); assuming text is unsupported.",
                model_id,
            )

        if hasattr(self.model_handler, "supports_image"):
            try:
                image_supported = bool(self.model_handler.supports_image())
            except Exception as exc:
                logger.warning(
                    "Could not determine image support for %s: %s",
                    model_id,
                    exc,
                )
        else:
            logger.warning(
                "Model handler for %s is missing supports_image(); assuming image is unsupported.",
                model_id,
            )

        return text_supported, image_supported

    def _resolve_embedding_dimensions(self) -> int:
        if hasattr(self.model_handler, "get_embedding_dim"):
            try:
                dims = int(self.model_handler.get_embedding_dim())
                if dims > 0:
                    logger.info("Using embedding dimensions reported by handler: %d", dims)
                    return dims
                logger.warning("Handler reported non-positive embedding dimension; probing instead")
            except Exception as exc:
                logger.warning("get_embedding_dim() failed: %s; probing dimensions", exc)

        return self._probe_embedding_dimensions()

    def _probe_embedding_dimensions(self) -> int:
        """
        Auto-detect embedding dimensions by testing the model with a dummy input.
        
        Returns:
            int: The detected embedding dimensions
        """
        try:
            logger.info("Auto-detecting embedding dimensions from SDK model...")

            if self.supports_image:
                logger.debug("Probing dimensions via image pathway")
                dummy_image = Image.new("RGB", (224, 224), color="white")
                test_embedding = self.model_handler.encode_image([dummy_image])
                logger.debug(
                    "Image probe type=%s length=%s",
                    type(test_embedding),
                    len(test_embedding) if test_embedding is not None else 'None',
                )
                if test_embedding is not None and len(test_embedding) > 0:
                    embedding_list = self._to_list(test_embedding[0])
                    if embedding_list:
                        dimensions = len(embedding_list)
                        logger.info("Auto-detected embedding dimensions: %d", dimensions)
                        return dimensions
                    logger.warning("Image probe returned empty embedding vector")

            if self.supports_text:
                logger.debug("Probing dimensions via text pathway")
                test_embedding = self.model_handler.encode_text(["dimension probe"])
                logger.debug(
                    "Text probe type=%s length=%s",
                    type(test_embedding),
                    len(test_embedding) if test_embedding is not None else 'None',
                )
                if test_embedding is not None and len(test_embedding) > 0:
                    embedding_list = self._to_list(test_embedding[0])
                    if embedding_list:
                        dimensions = len(embedding_list)
                        logger.info("Auto-detected embedding dimensions from text: %d", dimensions)
                        return dimensions
                    logger.warning("Text probe returned empty embedding vector")

            logger.warning("Could not detect dimensions from model, using default 512")
            return 512

        except Exception as exc:
            logger.warning("Failed to auto-detect embedding dimensions: %s", exc)
            logger.debug(traceback.format_exc())
            logger.warning("Falling back to default 512 dimensions")
            return 512
    
    def _init_vector_store(self):
        """Initialize the active vector store backend via the factory.

        Persistence is delegated to the pluggable vector store
        (``VECTORDB_BACKEND``); this client no longer talks to VDMS directly.
        """
        try:
            self.vector_store = get_vector_store()
            # Propagate the resolved embedding dimensions to backends that need
            # them at collection-creation time (e.g. VDMS).
            if self.embedding_dimensions and hasattr(
                self.vector_store, "embedding_dimensions"
            ):
                self.vector_store.embedding_dimensions = self.embedding_dimensions
            self.vector_store.connect()
            logger.info("Vector store backend initialized for EmbeddingClient")
        except Exception as ex:
            logger.error("Error initializing vector store: %s", ex)
            raise Exception(Strings.db_conn_error)

    def store_frame_embeddings(self, embeddings: List[List[float]], frame_metadatas: List[dict]) -> List[str]:
        """
        Store frame embeddings using optimized vector store batching.

        Args:
            embeddings: Pre-computed embeddings from SDK
            frame_metadatas: Metadata for each frame

        Returns:
            List of IDs for stored embeddings
        """
        try:
            start_time = time.time()
            total_embeddings = len(embeddings)
            logger.info("Storing %d frame embeddings...", total_embeddings)
            logger.debug("Embedding dimensions: %d", self.embedding_dimensions)
            
            # Validate inputs
            if len(embeddings) != len(frame_metadatas):
                raise ValueError(f"Mismatch: {len(embeddings)} embeddings vs {len(frame_metadatas)} metadata entries")
            
            # Generate frame texts and clean metadata
            frame_texts = []
            cleaned_metadatas = []
            
            for i, metadata in enumerate(frame_metadatas):
                video_id = metadata.get('video_id', 'unknown')
                frame_num = metadata.get('frame_number', i)
                frame_type = metadata.get('frame_type', 'full_frame')
                crop_index = metadata.get('crop_index')
                
                # Generate descriptive text for crops vs full frames
                if frame_type == "detected_crop" and crop_index is not None:
                    frame_text = f"frame_{frame_num}_crop_{crop_index}_{video_id}"
                else:
                    frame_text = f"frame_{frame_num}_{video_id}"
                
                # Pass canonical metadata through unmodified; the active vector
                # store backend adapts it per-backend (VDMS flattens lists,
                # Milvus preserves them).
                frame_texts.append(frame_text)
                cleaned_metadatas.append(metadata)
            logger.debug("Prepared metadata for %d frames", len(frame_texts))

            # Store embeddings using optimized vector store approach
            logger.debug(
                "Storage payload: dim=%s, sample_text=%s, metadata_keys=%s",
                len(embeddings[0]) if embeddings and len(embeddings[0]) > 0 else "unknown",
                (frame_texts[0][:50] + "...") if frame_texts else "<none>",
                list(cleaned_metadatas[0].keys()) if cleaned_metadatas else []
            )
            
            ids = self._store_embeddings(embeddings, frame_texts, cleaned_metadatas)
            total_time = time.time() - start_time
            logger.info("Stored %d embeddings in %.3fs", len(ids), total_time)
            return ids
            
        except Exception as ex:
            total_time = time.time() - start_time if 'start_time' in locals() else 0
            logger.error("store_frame_embeddings() failed after %.3fs", total_time)
            logger.error("Error: %s", ex)
            logger.error("Error type: %s", type(ex).__name__)
            raise Exception(Strings.embedding_error)
    
    def _store_embeddings(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadatas: List[dict],
    ) -> List[str]:
        """Persist embeddings via the active vector store backend.

        Metadata is passed through unmodified (canonical form); the backend
        adapts it. The store lock is retained to serialize concurrent stores from
        the SDK's parallel pipeline.
        """

        if not embeddings:
            return []

        logger.info("Storing %d embeddings via vector store backend", len(embeddings))
        with self._store_lock:
            generated_ids = self.vector_store.add_embeddings(
                texts=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )

        logger.info("Stored %d embeddings", len(generated_ids))
        return generated_ids
    

    
    def generate_embedding_for_image(self, image_input: Any) -> Optional[List[float]]:
        """
        Generate embedding for a single image using SDK.
        
        Args:
            image_input: Image input (PIL Image, numpy array, or path)
            
        Returns:
            Embedding as list of floats or None if failed
        """
        try:
            if not self.supports_image:
                logger.debug(
                    "Model %s does not support image embeddings; skipping single image request.",
                    self.model_id,
                )
                return None

            # Ensure we have a PIL Image
            if isinstance(image_input, str):
                # If it's a path, load the image
                image = Image.open(image_input)
            elif isinstance(image_input, np.ndarray):
                # If it's a numpy array, convert to PIL
                image = Image.fromarray(image_input)
            else:
                # Assume it's already a PIL Image
                image = image_input
            
            # Generate embedding using the model handler
            embeddings = self.model_handler.encode_image([image])
            
            if embeddings is not None and len(embeddings) > 0:
                embedding = embeddings[0]
                vector = self._to_list(embedding)
                return vector or None
            return None
            
        except Exception as exc:
            logger.error("Error generating image embedding: %s", exc)
            return None

    def generate_embeddings_for_images(self, image_inputs: List[Any], metrics_out: bool = False) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple images using SDK in batch.
        
        Args:
            image_inputs: List of image inputs (numpy arrays)
            metrics_out: Whether to return metrics along with embeddings

        Returns:
            List of embeddings as lists of floats or None for failed images
        """
        image_len = len(image_inputs)
        try:
            if not self.supports_image:
                logger.info(
                    "Model %s does not support image embeddings; skipping batch of %d images.",
                    self.model_id,
                    image_len,
                )
                return [None] * image_len

            # Generate embeddings using the model handler in batch
            results = []
            infer_result = self.model_handler.encode_image(image_inputs, metrics_out=metrics_out)
            embeddings = infer_result["embeddings"] if metrics_out else infer_result
            results.extend([self._to_list(e) if e is not None else None for e in embeddings])
            del embeddings, image_inputs

            if metrics_out:
                return results, infer_result.get("inference_time_s")
            return results

        except Exception as exc:
            logger.error("Error generating batch image embeddings: %s", exc)
            return [None] * image_len

    def generate_embedding_for_text(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text input using the SDK model."""
        if not self.supports_text:
            logger.error(
                "Model %s does not support text embeddings; cannot embed provided text.",
                self.model_id,
            )
            return None

        try:
            embeddings = self.model_handler.encode_text([text])
            if embeddings is None or len(embeddings) == 0:
                logger.warning("Text embedding call returned empty result")
                return None
            return self._to_list(embeddings[0]) or None
        except Exception as exc:
            logger.error("Error generating text embedding: %s", exc)
            logger.debug(traceback.format_exc())
            return None

    def generate_embeddings_for_texts(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple text inputs."""
        if not self.supports_text:
            logger.error(
                "Model %s lacks text embedding support; cannot embed %d texts.",
                self.model_id,
                len(texts),
            )
            return [None] * len(texts)

        try:
            embeddings = self.model_handler.encode_text(texts)
            if embeddings is None:
                return [None] * len(texts)
            results: List[Optional[List[float]]] = []
            for embedding in embeddings:
                results.append(self._to_list(embedding) or None)
            return results
        except Exception as exc:
            logger.error("Error generating embeddings for texts: %s", exc)
            logger.debug(traceback.format_exc())
            return [None] * len(texts)

    def store_text_embedding(
        self,
        text: str,
        metadata: Optional[dict] = None,
        embedding_vector: Optional[List[float]] = None,
    ) -> List[str]:
        """Generate (if needed) and store a single text embedding."""
        metadata = metadata or {}

        vector = embedding_vector or self.generate_embedding_for_text(text)
        if vector is None:
            raise ValueError("Failed to generate text embedding for storage")

        return self.store_text_embedding_with_vector(text, vector, metadata)

    def store_text_embedding_with_vector(
        self,
        text: str,
        embedding_vector: List[float],
        metadata: Optional[dict] = None,
    ) -> List[str]:
        """Store a pre-computed text embedding vector via the vector store."""
        metadata = metadata or {}
        if not embedding_vector:
            raise ValueError("Embedding vector cannot be empty")

        return self._store_embeddings(
            embeddings=[embedding_vector],
            texts=[text],
            metadatas=[metadata],
        )
