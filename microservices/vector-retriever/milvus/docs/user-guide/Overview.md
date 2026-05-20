# Vector retriever microservice

Retrieve relevant visual data from a vector database using text or image queries

## Overview
The Vector Retriever microservice is designed to search visual data efficiently by querying embeddings stored in a vector database. It uses the CLIP model’s text and image encoders to transform user queries into embeddings and perform similarity search for accurate retrieval.

Key Features:

-    Text-to-Image Retrieval:

        Converts text prompts into embeddings and returns the most relevant images.

-    Image-to-Image Retrieval:

        Uses a query image to find visually similar images.

-    Vector Search with Metadata:

        Performs top-k similarity search in Milvus and returns linked metadata for each result.

-    Scalable Retrieval:

        Supports large-scale datasets with fast nearest-neighbor search.

**Programming Language:** Python

## How It Works

The Vector Retriever microservice provides efficient semantic retrieval over visual datasets by searching embedding vectors stored in Milvus.

-    Query Encoding:
        User input (text or image) is encoded into a vector embedding with CLIP.

-    Similarity Search:
        The query embedding is matched against indexed embeddings in Milvus to find the nearest vectors.

-    Result Ranking:
        Retrieved candidates are ranked by similarity score, and top-k results are returned.

-    Metadata Resolution:
        The service returns associated metadata (for example file path, source reference, or original image linkage) to provide context for each match.

## Learn More
-    Start with the [Get Started](./get-started.md).
