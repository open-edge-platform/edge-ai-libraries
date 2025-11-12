# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SDK-based VDMS client that stores embeddings produced by the MME SDK."""

import threading
import time
import traceback
import uuid
from collections.abc import Iterable
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image
from langchain_core.embeddings import Embeddings
from langchain_vdms.vectorstores import VDMS, VDMS_Client
from multimodal_embedding_serving import EmbeddingModel, get_model_handler

from src.common import Strings, logger, settings


class DummyEmbedding(Embeddings):
    """
    Minimal dummy embedding class that satisfies VDMS requirements.
    We won't actually use these methods since storage is handled entirely by langchain-vdms.
    """
    
    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Won't be called since we use pre-computed embeddings."""
        raise NotImplementedError("Use pre-computed embeddings instead")
    
    def embed_query(self, text: str) -> List[float]:
        """Won't be called since we use pre-computed embeddings.""" 
        raise NotImplementedError("Use pre-computed embeddings instead")


class SDKVDMSClient:
    """
    Optimized VDMS Client using SDK-based embedding generation with langchain-vdms persistence.

    This client provides maximum performance by combining:
    1. SDK-based embedding generation (no HTTP overhead)
    2. Standard langchain-vdms vector store APIs for durability across restarts
    3. Optimized batch processing for high-throughput storage

    Performance improvements:
    - Eliminates network latency for embedding generation
    - Uses optimized batch sizes for VDMS operations
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
        vdms_host: Optional[str] = None,
        vdms_port: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        """
        Initialize the SDK client with embedding model and VDMS storage.
        
        Args:
            model_id: Model identifier for embedding generation
            device: Device to run the model on (CPU, GPU, etc.)
            use_openvino: Whether to use OpenVINO optimization
            ov_models_dir: Directory for OpenVINO models
            vdms_host: VDMS database host (defaults to settings)
            vdms_port: VDMS database port (defaults to settings)  
            collection_name: VDMS collection name (defaults to settings)
        """
        # Store embedding model configuration
        self.model_id = model_id
        self.device = device
        self.use_openvino = use_openvino
        self.ov_models_dir = ov_models_dir
        
        # Store VDMS configuration  
        self.vdms_host = vdms_host or settings.VDMS_VDB_HOST
        self.vdms_port = vdms_port or settings.VDMS_VDB_PORT
        self.collection_name = collection_name or settings.DB_COLLECTION
        
        # Synchronization for VDMS operations
        self._vdms_lock = threading.RLock()

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
        
        # Initialize VDMS database connection
        self._init_vdms()

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
                dummy_image = Image.new('RGB', (224, 224), color='white')
                test_embedding = self.model_handler.encode_image([dummy_image])
                logger.debug(
                    "Image probe type=%s length=%s",
                    type(test_embedding),
                    len(test_embedding) if test_embedding is not None else 'None',
                )
                if test_embedding and len(test_embedding) > 0:
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
    
    def _init_vdms(self):
        """Initialize VDMS Client and database connection."""
        try:
            logger.info("Connecting to VDMS server at %s:%s...", self.vdms_host, self.vdms_port)
            
            # Create VDMS client for collection management only
            self.vdms_client = VDMS_Client(host=self.vdms_host, port=int(self.vdms_port))
            
            # For VDMS v2.10.0, skip connection test to avoid API validation issues
            # The client will fail later if the connection is not valid
            logger.info("VDMS client created successfully")
            logger.info("Connection will be validated when first query is executed")

            # Initialize VDMS database with minimal dummy embedding for collection setup
            dummy_embedding = DummyEmbedding(self.embedding_dimensions)
            
            self.video_db = VDMS(
                client=self.vdms_client,
                embedding=dummy_embedding,  # Only used for collection setup
                collection_name=self.collection_name,
                engine="FaissFlat",
                distance_strategy="IP",
                # distance_strategy="L2",
                embedding_dimensions=self.embedding_dimensions
            )
            
            logger.info("VDMS initialized - Collection: %s", self.collection_name)
            logger.info("Collection configured with %dD embeddings", self.embedding_dimensions)
            logger.warning(
                "If you see 'Dimensions mismatch' errors from VDMS, the collection was created "
                "with different dimensions. To fix: 1) Delete the collection using VDMS CLI, or "
                "2) Use a different collection_name, or 3) Restart VDMS to clear all collections"
            )

        except Exception as ex:
            logger.error("Error initializing VDMS: %s", ex)
            raise Exception(Strings.db_conn_error)

    def _clean_metadata_for_vdms(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
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

    def store_frame_embeddings(self, embeddings: List[List[float]], frame_metadatas: List[dict]) -> List[str]:
        """
        Store frame embeddings using optimized langchain-vdms batching.

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
                
                # Clean metadata to remove problematic fields for VDMS
                cleaned_metadata = self._clean_metadata_for_vdms(metadata)
                
                frame_texts.append(frame_text)
                cleaned_metadatas.append(cleaned_metadata)
            logger.debug("Prepared metadata for %d frames", len(frame_texts))

            # Store embeddings using optimized langchain-vdms approach
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
        """Persist embeddings using the langchain-vdms vector store."""

        if not embeddings:
            return []

        logger.info("Storing %d embeddings via langchain-vdms", len(embeddings))
        batch_size = 200
        generated_ids: List[str] = []

        with self._vdms_lock:
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

    def generate_embeddings_for_images(self, image_inputs: List[Any]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple images using SDK in batch.
        
        Args:
            image_inputs: List of image inputs (PIL Images, numpy arrays, or paths)
            
        Returns:
            List of embeddings as lists of floats or None for failed images
        """
        try:
            if not self.supports_image:
                logger.info(
                    "Model %s does not support image embeddings; skipping batch of %d images.",
                    self.model_id,
                    len(image_inputs),
                )
                return [None] * len(image_inputs)

            # Convert all inputs to PIL Images
            pil_images = []
            for image_input in image_inputs:
                if isinstance(image_input, str):
                    # If it's a path, load the image
                    image = Image.open(image_input)
                elif isinstance(image_input, np.ndarray):
                    # If it's a numpy array, convert to PIL
                    image = Image.fromarray(image_input)
                else:
                    # Assume it's already a PIL Image
                    image = image_input
                pil_images.append(image)
            
            # Generate embeddings using the model handler in batch
            embeddings = self.model_handler.encode_image(pil_images)
            
            if embeddings is not None:
                results = []
                for embedding in embeddings:
                    if embedding is not None:
                        vector = self._to_list(embedding)
                        results.append(vector or None)
                    else:
                        results.append(None)
                return results
            return [None] * len(image_inputs)
            
        except Exception as exc:
            logger.error("Error generating batch image embeddings: %s", exc)
            return [None] * len(image_inputs)

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
        """Store a pre-computed text embedding vector in VDMS."""
        metadata = metadata or {}
        if not embedding_vector:
            raise ValueError("Embedding vector cannot be empty")

        cleaned_metadata = self._clean_metadata_for_vdms(metadata)
        return self._store_embeddings(
            embeddings=[embedding_vector],
            texts=[text],
            metadatas=[cleaned_metadata],
        )
    

