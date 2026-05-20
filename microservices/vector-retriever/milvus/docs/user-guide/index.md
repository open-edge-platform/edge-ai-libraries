# Vector Retriever - Milvus Microservice

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/vector-retriever/milvus">
     GitHub
  </a>
</div>
hide_directive-->

Retrieve relevant visual data from a vector database using text or image queries

## Overview
The Vector Retriever microservice is designed to search visual data efficiently by querying embeddings stored in a vector database. It uses the CLIP model's text and image encoders to transform user queries into embeddings and perform similarity search for accurate retrieval.

### Key Features:

- Text-to-Image Retrieval:

  Converts text prompts into embeddings and returns the most relevant images. Supports
  optional filters to refine search results.

- Image-to-Image Retrieval:

  Uses a query image to find visually similar images.

- Vector Search with Metadata:

  Performs top-k similarity search in Milvus and returns linked metadata for each result.

- Scalable Retrieval:

  Supports large-scale datasets with fast nearest-neighbor search.

- Integration with Milvus:

  Utilizes the Milvus vector database for efficient storage and retrieval of embeddings.
  Ensures high performance and scalability for large datasets.

**Programming Language:** Python

## How It Works

The Vector Retriever microservice provides efficient semantic retrieval over visual datasets by searching embedding vectors stored in Milvus.

- Query Encoding:

  User input (text or image) is encoded into a vector embedding with CLIP.

- Similarity Search:

  The query embedding is matched against indexed embeddings in Milvus to find the
  nearest vectors.

- Result Generation:

  The retrieved results include metadata, similarity scores, and unique identifiers.
  Results are returned in JSON format for easy integration with downstream applications.

- Result Ranking:

  Retrieved candidates are ranked by similarity score, and top-k results are returned.

- Metadata Resolution:

  The service returns associated metadata (for example file path, source reference, or
  original image linkage) to provide context for each match.

## Workflow

1. The embedding model generates text embeddings for input descriptions
   (e.g., "traffic jam").
2. The search engine searches the vector database for the top-k most similar matches.
3. Generate results with the matched vector ids and metadata.

## Learn More

- Begin with the [Get Started Guide](./get-started.md).

<!--hide_directive
:::{toctree}
:hidden:

get-started
api-reference
release-notes

:::
hide_directive-->
