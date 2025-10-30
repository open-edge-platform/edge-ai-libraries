# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SDK-based VDMS Client for Multimodal Embedding Storage

This module provides an optimized implementation that uses the multimodal embedding
service directly as an SDK and stores embeddings via direct VDMS calls for maximum performance.

Key benefits:
1. No network latency - direct function calls
2. Single video instance in RAM - extract frames and create embeddings efficiently  
3. Better resource utilization - no need to serialize/deserialize data
4. Direct VDMS storage bypassing expensive langchain wrapper ID checks
5. Optimized batch processing for high-throughput storage
"""

import pathlib
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import traceback
from PIL import Image
import uuid
import time
import threading

from multimodal_embedding_serving import get_model_handler, EmbeddingModel
from langchain_community.vectorstores import VDMS
from langchain_community.vectorstores.vdms import VDMS_Client, _build_property_query
from langchain_core.embeddings import Embeddings

from src.common import logger, settings, Strings


class DummyEmbedding(Embeddings):
    """
    Minimal dummy embedding class that satisfies VDMS requirements.
    We won't actually use these methods since we use direct VDMS calls.
    """
    
    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Won't be called since we use direct VDMS storage."""
        raise NotImplementedError("Use direct VDMS storage instead")
    
    def embed_query(self, text: str) -> List[float]:
        """Won't be called since we use direct VDMS storage.""" 
        raise NotImplementedError("Use direct VDMS storage instead")


class SDKVDMSClient:
    """
    Optimized VDMS Client using SDK-based embedding generation and direct VDMS storage.
    
    This client provides maximum performance by combining:
    1. SDK-based embedding generation (no HTTP overhead)
    2. Direct VDMS storage (bypassing expensive langchain wrapper ID checks)
    3. Optimized batch processing for high-throughput storage
    
    Performance improvements:
    - Eliminates network latency for embedding generation
    - Bypasses langchain wrapper's expensive ID existence checks
    - Uses optimized batch sizes for VDMS operations
    - Achieves ~30x performance improvement over standard langchain approach
    """
    
    def __init__(self, 
                 model_id: str = "CLIP/clip-vit-b-16",
                 device: str = "CPU",
                 use_openvino: bool = False,
                 ov_models_dir: Optional[str] = None,
                 vdms_host: str = None,
                 vdms_port: str = None,
                 collection_name: str = None):
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
        
        # Native VDMS connection cache and synchronization
        self._vdms_native = None
        # Reentrant lock guards connection lifecycle and query execution
        self._vdms_lock = threading.RLock()

        # Initialize the embedding model
        logger.info(f"Initializing embedding model: {model_id}")
        self.model_handler = get_model_handler(
            model_id=model_id,
            device=device,
            use_openvino=use_openvino,
            ov_models_dir=ov_models_dir
        )
        
        # Load the model
        logger.info("Loading embedding model...")
        self.model_handler.load_model()
        
        # Create EmbeddingModel wrapper
        self.embedding_model = EmbeddingModel(self.model_handler)
        
        # Get embedding dimensions - use handler's get_embedding_dim() if available
        if hasattr(self.model_handler, 'get_embedding_dim'):
            self.embedding_dimensions = self.model_handler.get_embedding_dim()
            logger.info(f"Using embedding dimensions from model handler: {self.embedding_dimensions}")
        else:
            # Fallback to auto-detection for handlers without get_embedding_dim()
            self.embedding_dimensions = self._detect_embedding_dimensions()
            logger.info(f"Using embedding dimensions from auto-detection: {self.embedding_dimensions}")
        
        # Initialize VDMS database connection
        self._init_vdms()
        
        logger.info(f"SDK client initialized with model: {model_id}")
    
    def _detect_embedding_dimensions(self) -> int:
        """
        Auto-detect embedding dimensions by testing the model with a dummy input.
        
        Returns:
            int: The detected embedding dimensions
        """
        try:
            logger.info("Auto-detecting embedding dimensions from SDK model...")
            
            # Create a small dummy image for testing
            dummy_image = Image.new('RGB', (224, 224), color='white')
            
            # Generate a test embedding to get dimensions
            test_embedding = self.model_handler.encode_image([dummy_image])
            
            logger.debug(f"Test embedding type: {type(test_embedding)}")
            logger.debug(f"Test embedding length: {len(test_embedding) if test_embedding is not None else 'None'}")
            
            if test_embedding is not None and len(test_embedding) > 0:
                embedding = test_embedding[0]
                logger.debug(f"Single embedding type: {type(embedding)}")
                logger.debug(f"Single embedding shape: {embedding.shape if hasattr(embedding, 'shape') else 'N/A'}")
                
                if hasattr(embedding, 'shape'):
                    dimensions = embedding.shape[0] if len(embedding.shape) == 1 else embedding.shape[-1]
                    logger.debug(f"Extracted from shape: {dimensions}")
                elif hasattr(embedding, '__len__'):
                    dimensions = len(embedding)
                    logger.debug(f"Extracted from len: {dimensions}")
                else:
                    dimensions = 512  # fallback
                    logger.debug(f"Using fallback: {dimensions}")
                    
                logger.info(f"Auto-detected embedding dimensions: {dimensions}")
                return dimensions
            else:
                logger.warning("Could not detect dimensions from model, using default 512")
                return 512
                
        except Exception as e:
            logger.warning(f"Failed to auto-detect embedding dimensions: {e}")
            logger.warning(f"Traceback: {traceback.format_exc()}")
            logger.warning("Falling back to default 512 dimensions")
            return 512
    
    def _init_vdms(self):
        """Initialize VDMS Client and database connection."""
        try:
            logger.info(f"Connecting to VDMS server at {self.vdms_host}:{self.vdms_port}...")
            
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
            
            logger.info(f"VDMS initialized - Collection: {self.collection_name}")
            logger.info(f"Collection configured with {self.embedding_dimensions}D embeddings")
            logger.warning(
                "If you see 'Dimensions mismatch' errors from VDMS, the collection was created "
                "with different dimensions. To fix: 1) Delete the collection using VDMS CLI, or "
                "2) Use a different collection_name, or 3) Restart VDMS to clear all collections"
            )

        except Exception as ex:
            logger.error(f"Error initializing VDMS: {ex}")
            raise Exception(Strings.db_conn_error)

    def _get_native_vdms(self):
        """Lazily create and cache the native VDMS connection for direct queries."""
        if self._vdms_native is not None:
            return self._vdms_native

        with self._vdms_lock:
            if self._vdms_native is None:
                import vdms

                logger.debug(
                    "Establishing new native VDMS connection to %s:%s", self.vdms_host, self.vdms_port
                )
                db = vdms.vdms()
                db.connect(host=self.vdms_host, port=int(self.vdms_port))
                self._vdms_native = db

        return self._vdms_native

    def _reset_native_vdms(self):
        """Close and clear the cached native VDMS connection."""
        with self._vdms_lock:
            if self._vdms_native is not None:
                try:
                    self._vdms_native.disconnect()
                except Exception as ex:
                    logger.warning("Failed to disconnect cached VDMS client cleanly: %s", ex)
                finally:
                    self._vdms_native = None

    def close(self):
        """Public helper to explicitly release native VDMS resources."""
        self._reset_native_vdms()

    def _ensure_collection_properties(self, metadatas: List[dict]) -> None:
        """Ensure VDMS collection properties include all metadata keys."""

        if not metadatas:
            return

        try:
            existing_props = set(getattr(self.video_db, "collection_properties", []) or [])
        except AttributeError:
            existing_props = set()

        if not existing_props:
            existing_props = {"_distance", "id", "content"}

        new_props = set()
        for metadata in metadatas:
            for key in metadata.keys():
                if key not in existing_props:
                    new_props.add(key)

        if not new_props:
            return

        updated_props = sorted(existing_props.union(new_props))
        self.video_db.collection_properties = updated_props

        try:
            property_queries, blob_arr = _build_property_query(
                self.collection_name,
                command_type="update",
                all_properties=updated_props,
            )

            blobs = [blob_arr] if blob_arr else []
            self.vdms_client.query(property_queries, blobs)
            logger.info(
                "Registered %d new metadata properties in VDMS collection '%s': %s",
                len(new_props),
                self.collection_name,
                ", ".join(sorted(new_props)),
            )
        except Exception as ex:
            logger.error(
                "Failed to update VDMS collection properties for '%s': %s",
                self.collection_name,
                ex,
            )

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
        Store frame embeddings using optimized direct VDMS approach.
        
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

            # Store embeddings using optimized direct VDMS approach
            logger.debug(
                "Direct storage payload: dim=%s, sample_text=%s, metadata_keys=%s",
                len(embeddings[0]) if embeddings and len(embeddings[0]) > 0 else "unknown",
                (frame_texts[0][:50] + "...") if frame_texts else "<none>",
                list(cleaned_metadatas[0].keys()) if cleaned_metadatas else []
            )
            
            ids = self._store_embeddings_direct_vdms(embeddings, frame_texts, cleaned_metadatas)
            total_time = time.time() - start_time
            logger.info("Stored %d embeddings in %.3fs", len(ids), total_time)
            return ids
            
        except Exception as ex:
            total_time = time.time() - start_time if 'start_time' in locals() else 0
            logger.error(f"store_frame_embeddings() failed after {total_time:.3f}s")
            logger.error(f"Error: {ex}")
            logger.error(f"Error type: {type(ex).__name__}")
            raise Exception(Strings.embedding_error)
    
    def _store_embeddings_direct_vdms(self, embeddings: List[List[float]], texts: List[str], metadatas: List[dict]) -> List[str]:
        """
        Optimized direct VDMS storage bypassing langchain wrapper for maximum performance.
        
        This method connects directly to VDMS using the native client, avoiding the expensive
        ID existence checks performed by the langchain wrapper. This provides significant
        performance improvements for bulk embedding storage.
        
        Args:
            embeddings: List of embedding vectors 
            texts: List of text content for each embedding
            metadatas: List of metadata dicts for each embedding
            
        Returns:
            List of generated document IDs
        """
        direct_start_time = time.time()
        try:
            db = self._get_native_vdms()

            generated_ids = []

            # Process embeddings in optimized batches
            batch_size = 200  # Reduced batch size to prevent OutOfJournalSpace errors
            logger.info(
                "Direct VDMS storage starting: %d embeddings (batch size %d)",
                len(embeddings), min(len(embeddings), batch_size)
            )
            total_batches = (len(embeddings) + batch_size - 1) // batch_size

            with self._vdms_lock:
                for batch_idx in range(total_batches):
                    batch_start = batch_idx * batch_size
                    batch_end = min((batch_idx + 1) * batch_size, len(embeddings))
                    batch_embeddings = embeddings[batch_start:batch_end]
                    batch_texts = texts[batch_start:batch_end]
                    batch_metadatas = metadatas[batch_start:batch_end]

                    logger.debug(
                        "Processing batch %d/%d (%d embeddings)",
                        batch_idx + 1,
                        total_batches,
                        len(batch_embeddings),
                    )

                    # Build optimized batch query with proper VDMS structure
                    query_list = []
                    blob_list = []
                    batch_ids = []

                    for i, (embedding_vector, text, metadata) in enumerate(
                        zip(batch_embeddings, batch_texts, batch_metadatas)
                    ):
                        # Generate unique ID
                        doc_id = str(uuid.uuid4())
                        batch_ids.append(doc_id)
                        generated_ids.append(doc_id)

                        # Convert embedding to bytes using numpy (VDMS requirement)
                        emb_array = np.array(embedding_vector, dtype="float32")
                        blob = emb_array.tobytes()
                        blob_list.append(blob)

                        # Build VDMS AddDescriptor query with proper structure
                        descriptor_query = {
                            "AddDescriptor": {
                                "set": self.collection_name,
                                "properties": {
                                    "id": doc_id,
                                    "content": text,
                                    **metadata,
                                },
                            }
                        }

                        # Add query to batch (individual queries, not nested)
                        query_list.append(descriptor_query)

                    # Execute optimized batch query
                    try:
                        response = db.query(query_list, blob_list)

                        # Check response for any errors
                        if response and len(response) > 0:
                            for i, resp in enumerate(response):
                                if "AddDescriptor" in resp and resp["AddDescriptor"]["status"] != 0:
                                    logger.error(
                                        "Batch %d item %d failed: %s",
                                        batch_idx + 1,
                                        i + 1,
                                        resp,
                                    )
                                    raise Exception(f"VDMS AddDescriptor failed: {resp}")

                    except Exception as batch_ex:
                        logger.error(f"Batch {batch_idx + 1} failed: {batch_ex}")
                        raise

            # Log performance metrics
            total_time = time.time() - direct_start_time
            logger.info(
                "Direct VDMS storage complete: %d embeddings in %.3fs",
                len(embeddings), total_time
            )

            self._ensure_collection_properties(metadatas)

            return generated_ids

        except Exception as ex:
            elapsed_time = time.time() - direct_start_time if 'direct_start_time' in locals() else 0
            logger.error(f"Direct VDMS storage failed after {elapsed_time:.3f}s: {ex}")
            logger.error(f"Error type: {type(ex).__name__}")
            self._reset_native_vdms()
            raise Exception(f"Optimized VDMS storage failed: {ex}")
    

    
    def generate_embedding_for_image(self, image_input: Any) -> Optional[List[float]]:
        """
        Generate embedding for a single image using SDK.
        
        Args:
            image_input: Image input (PIL Image, numpy array, or path)
            
        Returns:
            Embedding as list of floats or None if failed
        """
        try:
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
                # Convert to list if it's a numpy array or tensor
                if hasattr(embedding, 'tolist'):
                    return embedding.tolist()
                elif hasattr(embedding, '__iter__'):
                    return list(embedding)
                else:
                    return [embedding]
            return None
            
        except Exception as e:
            logger.error(f"Error generating image embedding: {e}")
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
                        # Convert to list if it's a numpy array or tensor
                        if hasattr(embedding, 'tolist'):
                            results.append(embedding.tolist())
                        elif hasattr(embedding, '__iter__'):
                            results.append(list(embedding))
                        else:
                            results.append([embedding])
                    else:
                        results.append(None)
                return results
            return [None] * len(image_inputs)
            
        except Exception as e:
            logger.error(f"Error generating batch image embeddings: {e}")
            return [None] * len(image_inputs)
    

