#!/usr/bin/env python3
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Cross-Project SDK Examples for Multimodal Embedding Serving

This file demonstrates how to use the multimodal embedding serving
microservice as an SDK from another project, simulating real-world usage
where you want to integrate embedding capabilities into your own application.

This example assumes you're importing from a different project directory.

NOTE: IDE may show import errors for multimodal_embedding_serving imports.
This is expected since the imports are resolved dynamically at runtime
after adding the service path to sys.path. The code will work correctly
when executed.
"""

import os
import sys
from pathlib import Path

def setup_cross_project_imports():
    """
    Setup imports for cross-project usage.
    
    This simulates importing from another project where the multimodal-embedding-serving
    is located in a sibling directory or different location.
    """
    print("=" * 70)
    print("Cross-Project Import Setup")
    print("=" * 70)
    
    # Method 1: Absolute path (recommended for production)
    # Assume we're in: /path/to/my-project/src/
    # And embedding service is at: /path/to/multimodal-embedding-serving/
    
    current_file = Path(__file__)
    
    # For this example, we'll simulate being in a different project
    # by going up from examples/ to the parent of multimodal-embedding-serving
    # then down to multimodal-embedding-serving
    embedding_service_root = current_file.parent.parent.parent
    
    print(f"Current file: {current_file}")
    print(f"Embedding service root: {embedding_service_root}")
    
    # Add the embedding service to Python path
    if str(embedding_service_root) not in sys.path:
        sys.path.insert(0, str(embedding_service_root))
        print(f"Added to sys.path: {embedding_service_root}")
    
    # Now we can import as if it's an external package
    try:
        # Import from the root package (recommended)
        # Note: IDE may show import errors until runtime when path is added
        from multimodal_embedding_serving import EmbeddingModel, get_model_handler, list_available_models  # type: ignore
        print("✅ Successfully imported from root package!")
        return EmbeddingModel, get_model_handler, list_available_models
        
    except ImportError as e:
        print(f"❌ Root package import failed: {e}")
        print("Falling back to src-level imports...")
        
        # Fallback: Import from src subpackage
        try:
            from multimodal_embedding_serving.src import EmbeddingModel  # type: ignore
            from multimodal_embedding_serving.src.models import get_model_handler, list_available_models  # type: ignore
            print("✅ Successfully imported from src subpackage!")
            return EmbeddingModel, get_model_handler, list_available_models
            
        except ImportError as e:
            print(f"❌ All import methods failed: {e}")
            raise

def demonstrate_import_patterns():
    """Demonstrate different import patterns for cross-project usage."""
    print("\n" + "=" * 70)
    print("Different Import Patterns for Cross-Project Usage")
    print("=" * 70)
    
    print("""
# ===============================================
# Pattern 1: Using Root Package (Recommended)
# ===============================================

import sys
from pathlib import Path

# Add the embedding service to your Python path
embedding_service_path = Path("/path/to/multimodal-embedding-serving")
sys.path.insert(0, str(embedding_service_path))

# Import from root package (cleanest)
from multimodal_embedding_serving import EmbeddingModel, get_model_handler

# ===============================================  
# Pattern 2: Using Relative Paths
# ===============================================

# If the embedding service is in a sibling directory
embedding_service_path = Path(__file__).parent.parent / "multimodal-embedding-serving"
sys.path.insert(0, str(embedding_service_path))

from multimodal_embedding_serving import EmbeddingModel

# ===============================================
# Pattern 3: Using Environment Variables
# ===============================================

import os
embedding_service_path = os.environ.get('EMBEDDING_SERVICE_PATH', '/default/path')
sys.path.insert(0, embedding_service_path)

from multimodal_embedding_serving import EmbeddingModel

# ===============================================
# Pattern 4: Using pip install (Production)
# ===============================================

# First install the package:
# cd /path/to/multimodal-embedding-serving
# pip install -e .

# Then import normally:
# from multimodal_embedding_serving import EmbeddingModel

""")

# Import the classes using our setup function
EmbeddingModel, get_model_handler, list_available_models = setup_cross_project_imports()


MODEL_TESTS = [
    ("CLIP/clip-vit-b-16", "A beautiful sunset over the ocean"),
    ("MobileCLIP/mobileclip_s0", "A red car on a mountain road"),
    ("SigLIP/siglip-vit-b-16", "A modern cityscape at night"),
    ("Blip2/blip2_feature_extractor", "A person riding a horse on the beach"),
    ("Blip2/blip2_transformers", "A peaceful forest with tall trees"),
]

OV_BASE_DIR = Path(__file__).parent.parent / "ov-models"


def example_list_available_models():
    """Example: List all available models"""
    print("=" * 50)
    print("Available Models:")
    print("=" * 50)

    models = list_available_models()
    for model_type, model_names in models.items():
        print(f"{model_type}:")
        for name in model_names:
            print(f"  - {name}")
    print()


def example_text_embedding():
    """Example: Generate text embeddings using CLIP"""
    print("=" * 50)
    print("Text Embedding Example (CLIP)")
    print("=" * 50)

    # Get CLIP handler
    handler = get_model_handler("CLIP/clip-vit-b-16")
    print(f"Model: {handler.model_config['model_name']}")

    # Load model (without OpenVINO conversion for this example)
    handler.load_model()

    # Create wrapper for application-level methods
    embedding_model = EmbeddingModel(handler)

    # Generate text embedding
    text = "A beautiful sunset over the ocean"
    embedding = embedding_model.embed_query(text)

    print(f"Text: '{text}'")
    print(f"Embedding shape: {len(embedding)} dimensions")
    print(f"First 5 values: {embedding[:5]}")
    print()


def example_mobileclip_text_embedding():
    """Example: Generate text embeddings using MobileCLIP"""
    print("=" * 50)
    print("Text Embedding Example (MobileCLIP)")
    print("=" * 50)

    # Get MobileCLIP handler
    handler = get_model_handler("MobileCLIP/mobileclip_s0")
    print(f"Model: {handler.model_config['model_name']}")

    # Load model
    handler.load_model()

    # Create wrapper
    embedding_model = EmbeddingModel(handler)

    # Generate text embedding
    text = "A red car on a mountain road"
    embedding = embedding_model.embed_query(text)

    print(f"Text: '{text}'")
    print(f"Embedding shape: {len(embedding)} dimensions")
    print(f"First 5 values: {embedding[:5]}")
    print()


def example_multiple_texts():
    """Example: Generate embeddings for multiple texts"""
    print("=" * 50)
    print("Multiple Text Embeddings Example")
    print("=" * 50)

    # Get handler
    handler = get_model_handler("CLIP/clip-vit-b-16")
    handler.load_model()

    embedding_model = EmbeddingModel(handler)

    # Multiple texts
    texts = [
        "A dog playing in the park",
        "A cat sleeping on a sofa",
        "A bird flying in the sky",
        "A fish swimming in the ocean",
    ]

    embeddings = embedding_model.embed_documents(texts)

    print(f"Generated embeddings for {len(texts)} texts:")
    for i, (text, embedding) in enumerate(zip(texts, embeddings)):
        print(f"{i+1}. '{text}' -> {len(embedding)} dimensions")
    print()


def example_model_comparison():
    """Example: Compare different models on the same text"""
    print("=" * 50)
    print("Model Comparison Example")
    print("=" * 50)

    text = "A modern cityscape at night"
    models_to_test = [
        "CLIP/clip-vit-b-16",
        "MobileCLIP/mobileclip_s0",
        "SigLIP/siglip-vit-b-16",
    ]

    print(f"Text: '{text}'")
    print()

    for model_name in models_to_test:
        try:
            handler = get_model_handler(model_name)
            handler.load_model()

            embedding_model = EmbeddingModel(handler)
            embedding = embedding_model.embed_query(text)

            print(f"{model_name}:")
            print(f"  Embedding dimensions: {len(embedding)}")
            print(f"  First 3 values: {embedding[:3]}")
            print()

        except Exception as e:
            print(f"{model_name}: Error - {e}")
            print()


def example_openvino_conversion():
    """Example: Convert model to OpenVINO format"""
    print("=" * 50)
    print("OpenVINO Conversion Example")
    print("=" * 50)

    # Get handler
    handler = get_model_handler("CLIP/clip-vit-b-16")
    print(f"Model: {handler.model_config['model_name']}")

    # Load model first
    handler.load_model()
    print("Model loaded successfully")

    # Convert to OpenVINO
    ov_models_dir = "/tmp/ov_models"
    os.makedirs(ov_models_dir, exist_ok=True)

    try:
        handler.convert_to_openvino(ov_models_dir)
        print(f"Model converted to OpenVINO format in: {ov_models_dir}")

        # Test with OpenVINO
        embedding_model = EmbeddingModel(handler)
        text = "Testing OpenVINO inference"
        embedding = embedding_model.embed_query(text)

        print(f"OpenVINO inference successful!")
        print(f"Text: '{text}'")
        print(f"Embedding shape: {len(embedding)} dimensions")

    except Exception as e:
        print(f"OpenVINO conversion failed: {e}")

    print()


def run_embedding_example(
    model_id, text, use_openvino=None, device=None, ov_models_dir=None
):
    print("-" * 60)
    print(f"Model: {model_id}")
    print(f"Text: {text}")
    print(
        f"use_openvino: {use_openvino}, device: {device}, ov_models_dir: {ov_models_dir}"
    )
    try:
        # Set OpenVINO model dir as required
        if use_openvino:
            model_name = model_id.replace("/", "_")
            ov_dir = OV_BASE_DIR / model_name
            ov_dir.mkdir(parents=True, exist_ok=True)
            ov_models_dir = str(ov_dir)

        # Handler creation with param overrides
        handler = get_model_handler(
            model_id,
            device=device,
            ov_models_dir=ov_models_dir,
            use_openvino=use_openvino,
        )

        # Load model (this will convert to OpenVINO if needed)
        handler.load_model()

        # If OpenVINO is requested but models don't exist, convert them
        if use_openvino and not handler.use_openvino:
            print("Converting model to OpenVINO format...")
            handler.convert_to_openvino(ov_models_dir)
            # Reload with OpenVINO enabled
            handler = get_model_handler(
                model_id,
                device=device,
                ov_models_dir=ov_models_dir,
                use_openvino=use_openvino,
            )
            handler.load_model()

        embedding_model = EmbeddingModel(handler)
        embedding = embedding_model.embed_query(text)
        print(f"✓ Success! Embedding shape: {len(embedding)} dimensions")
        print(f"  First 5 values: {embedding[:5]}")
        print(f"  Using {'OpenVINO' if handler.use_openvino else 'PyTorch'} inference")
    except Exception as e:
        print(f"✗ Error: {e}")
    print()


def example_all_models_native_and_openvino():
    print("=" * 50)
    print("All Model Types: Native and OpenVINO SDK Usage")
    print("=" * 50)
    for model_id, text in MODEL_TESTS:
        # Native (no OpenVINO)
        run_embedding_example(model_id, text, use_openvino=False)
        # OpenVINO (with explicit device and ov_models_dir)
        run_embedding_example(model_id, text, use_openvino=True, device="CPU")


def example_cross_project_integration():
    """
    Example: Real-world cross-project integration scenario.
    
    This demonstrates how you might integrate the embedding service
    into your own application or microservice.
    """
    print("=" * 70)
    print("Cross-Project Integration Example")
    print("=" * 70)
    
    # Simulate a real application class that uses embeddings
    class MyApplicationEmbeddingClient:
        """
        Example client class for integrating embeddings into your application.
        
        This could be part of a recommendation system, search engine,
        content analysis tool, etc.
        """
        
        def __init__(self, model_name="CLIP/clip-vit-b-16", use_openvino=False):
            print(f"Initializing embedding client with model: {model_name}")
            
            # Initialize the embedding service
            self.handler = get_model_handler(
                model_name,
                use_openvino=use_openvino,
                device="CPU"
            )
            self.handler.load_model()
            self.embedding_model = EmbeddingModel(self.handler)
            
            print(f"✅ Embedding client ready!")
            print(f"   Model: {model_name}")
            print(f"   Embedding dimensions: {self.embedding_model.get_embedding_length()}")
            print(f"   Using OpenVINO: {use_openvino}")
        
        def analyze_content(self, content_items):
            """Analyze multiple content items and return embeddings."""
            results = []
            
            for item in content_items:
                if item["type"] == "text":
                    embedding = self.embedding_model.embed_query(item["content"])
                    results.append({
                        "type": "text",
                        "content": item["content"][:50] + "..." if len(item["content"]) > 50 else item["content"],
                        "embedding_dim": len(embedding),
                        "embedding_preview": embedding[:3]
                    })
                # Could add image/video support here
                
            return results
        
        def find_similar_content(self, query_text, content_database):
            """Find similar content using embeddings (simplified similarity)."""
            query_embedding = self.embedding_model.embed_query(query_text)
            
            # This is a simplified similarity calculation
            # In practice, you'd use proper vector similarity (cosine, etc.)
            print(f"🔍 Searching for content similar to: '{query_text}'")
            print(f"   Query embedding dimensions: {len(query_embedding)}")
            
            # Simulate finding similar content
            similar_items = []
            for item in content_database:
                item_embedding = self.embedding_model.embed_query(item)
                # Simplified similarity score (in practice, use cosine similarity)
                similarity_score = 0.85 + (hash(item) % 100) / 1000  # Mock score
                similar_items.append({
                    "content": item,
                    "similarity": similarity_score
                })
            
            # Sort by similarity
            similar_items.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_items[:3]  # Return top 3
    
    # Example usage
    try:
        # Initialize client
        client = MyApplicationEmbeddingClient("CLIP/clip-vit-b-16")
        
        # Example content analysis
        content_items = [
            {"type": "text", "content": "A beautiful sunset over the ocean"},
            {"type": "text", "content": "Modern city skyline at night"},
            {"type": "text", "content": "Cat sleeping on a windowsill"},
        ]
        
        print("\n📊 Analyzing content items:")
        results = client.analyze_content(content_items)
        for i, result in enumerate(results, 1):
            print(f"   {i}. {result['content']} -> {result['embedding_dim']} dims")
        
        # Example similarity search
        print("\n🔍 Similarity search example:")
        database = [
            "Beautiful ocean waves crashing on shore",
            "City lights reflecting in the water", 
            "Peaceful cat resting indoors",
            "Mountain landscape with trees",
        ]
        
        query = "Relaxing seaside view"
        similar = client.find_similar_content(query, database)
        
        print(f"   Query: '{query}'")
        print("   Most similar content:")
        for i, item in enumerate(similar, 1):
            print(f"      {i}. '{item['content']}' (similarity: {item['similarity']:.3f})")
            
    except Exception as e:
        print(f"❌ Cross-project integration example failed: {e}")
        import traceback
        traceback.print_exc()


def example_blip2_transformers():
    """Example: BLIP2 with Transformers (resolves vocabulary mismatch)"""
    print("=" * 50)
    print("BLIP2 Transformers Example (Vocab Fix)")
    print("=" * 50)
    
    try:
        # Use the new Transformers-based BLIP2 implementation
        print("🚀 Using BLIP2 Transformers implementation...")
        handler = get_model_handler("Blip2/blip2_transformers")
        print(f"Model: {handler.model_config['model_name']}")
        print(f"Handler: {handler.__class__.__name__}")

        # Load model
        print("Loading model...")
        handler.load_model()
        print("✅ Model loaded successfully (no vocabulary mismatch!)")

        # Create wrapper
        embedding_model = EmbeddingModel(handler)

        # Test text embedding
        print("\n📝 Testing text encoding...")
        texts = [
            "A cat sitting on a mat",
            "A dog running in the park", 
            "A bird flying in the sky"
        ]
        
        for text in texts:
            embedding = embedding_model.embed_query(text)
            print(f"   ✅ '{text}' → {len(embedding)} dimensions")
        
        # Test image embedding (with dummy image)
        print("\n🖼️  Testing image encoding...")
        try:
            from PIL import Image
            import numpy as np
            
            # Create a dummy RGB image
            dummy_image = Image.fromarray(
                np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
            )
            
            # Use the handler directly for image encoding
            image_features = handler.encode_image(dummy_image)
            print(f"   ✅ Image encoding successful: {image_features.shape}")
            
        except Exception as e:
            print(f"   ⚠️  Image encoding test skipped: {e}")

        print("\n📊 Model Information:")
        print(f"   • Embedding dimension: {handler.get_embedding_dim()}")
        print(f"   • Device: {handler.device}")
        print(f"   • Using OpenVINO: {handler.use_openvino}")
        
        print("\n💡 Benefits of Transformers implementation:")
        print("   ✅ No vocabulary size mismatch errors")
        print("   ✅ CPU-optimized with float32 precision")
        print("   ✅ Compatible with HuggingFace ecosystem")
        print("   ✅ Maintains same API as original handler")
        
        return True
        
    except ImportError as e:
        print(f"⚠️  Missing dependencies: {e}")
        print("   Install with: pip install transformers>=4.53.0")
        return False
        
    except Exception as e:
        print(f"❌ BLIP2 Transformers example failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def example_blip2_transformers_openvino():
    """Example: BLIP2 Transformers with OpenVINO acceleration"""
    print("=" * 50)
    print("BLIP2 Transformers + OpenVINO Example")
    print("=" * 50)
    
    try:
        # Use the new Transformers-based BLIP2 implementation with OpenVINO
        print("🚀 Using BLIP2 Transformers with OpenVINO acceleration...")
        
        # Setup OpenVINO models directory
        ov_dir = OV_BASE_DIR / "blip2_transformers"
        ov_dir.mkdir(parents=True, exist_ok=True)
        
        handler = get_model_handler(
            "Blip2/blip2_transformers", 
            use_openvino=True,
            device="CPU",
            ov_models_dir=str(ov_dir)
        )
        
        print(f"Model: {handler.model_config['model_name']}")
        print(f"Handler: {handler.__class__.__name__}")
        print(f"OpenVINO models dir: {ov_dir}")

        # Load model (this will convert to OpenVINO if needed)
        print("Loading model and converting to OpenVINO format if needed...")
        handler.load_model()
        print("✅ Model loaded successfully with OpenVINO!")

        # Create wrapper
        embedding_model = EmbeddingModel(handler)

        # Test text embedding with OpenVINO
        print("\n📝 Testing text encoding with OpenVINO...")
        texts = [
            "A beautiful landscape with mountains",
            "A futuristic city with flying cars", 
            "A peaceful garden with flowers"
        ]
        
        for text in texts:
            embedding = embedding_model.embed_query(text)
            print(f"   ✅ '{text}' → {len(embedding)} dimensions")
        
        # Test image embedding with OpenVINO (with dummy image)
        print("\n🖼️  Testing image encoding with OpenVINO...")
        try:
            from PIL import Image
            import numpy as np
            
            # Create a dummy RGB image
            dummy_image = Image.fromarray(
                np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
            )
            
            # Use the handler directly for image encoding
            image_features = handler.encode_image(dummy_image)
            print(f"   ✅ Image encoding with OpenVINO successful: {image_features.shape}")
            
        except Exception as e:
            print(f"   ⚠️  Image encoding test skipped: {e}")

        print("\n📊 OpenVINO Model Information:")
        print(f"   • Embedding dimension: {handler.get_embedding_dim()}")
        print(f"   • Device: {handler.device}")
        print(f"   • Using OpenVINO: {handler.use_openvino}")
        print(f"   • OpenVINO models dir: {ov_dir}")
        
        print("\n🚀 OpenVINO Benefits:")
        print("   ✅ Faster inference performance")
        print("   ✅ Lower memory usage")
        print("   ✅ Optimized for Intel hardware")
        print("   ✅ Production-ready deployment")
        
        return True
        
    except ImportError as e:
        print(f"⚠️  Missing dependencies: {e}")
        print("   Install with: pip install transformers>=4.53.0")
        return False
        
    except Exception as e:
        print(f"❌ BLIP2 Transformers OpenVINO example failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run cross-project SDK examples."""
    print("Multimodal Embedding Serving - Cross-Project SDK Examples")
    print("=" * 70)
    print()
    
    # Show import patterns
    demonstrate_import_patterns()
    
    try:
        # Run existing examples
        example_list_available_models()
        example_blip2_transformers()
        example_blip2_transformers_openvino()
        example_all_models_native_and_openvino()
        
        # Run cross-project integration example
        example_cross_project_integration()
        
        print("=" * 70)
        print("✅ All cross-project examples completed successfully!")
        print("\n💡 Integration Tips:")
        print("   1. Add the embedding service path to your sys.path")
        print("   2. Import from the root package when possible")
        print("   3. Initialize once and reuse the embedding client")
        print("   4. Consider using OpenVINO for production performance")
        print("   5. Handle exceptions gracefully in your application")
        print("   6. Use Blip2/blip2_transformers to avoid vocabulary issues")
        
    except Exception as e:
        print(f"❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
