# Retriever Microservice

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/vector-retriever/milvus">
     GitHub
  </a>
</div>
hide_directive-->

Retrieves embeddings based on vector similarity. Usually it is used along with a
`dataprep` microservice.

## Overview

The Retrieval Microservice is designed to perform efficient, vector-based searches
 using a vector database such as Milvus. It uses the CLIP model's text and image encoders
 to transform queries into embeddings and perform similarity search. It provides a RESTful
 API for retrieving relevant results based on text or image queries and optional filters.
 This microservice is optimized for handling large-scale datasets and supports flexible
 query configurations.

Key Features:

- Text-Based Image/Video Retrieval:

  Accepts text queries and retrieves the top-k most relevant results based on vector
  similarity. Supports optional filters to refine search results.

- Image-to-Image Retrieval:

  Uses a query image to find visually similar images.

- Integration with Milvus:

  Utilizes the Milvus vector database for efficient storage and retrieval of embeddings.
  Ensures high performance and scalability for large datasets.

**Programming Language:** Python

## How It Works

1. Query Processing:

   The microservice accepts a text query and optional filters via the
   `/v1/retrieval` endpoint. The query is processed with an embedding model to generate
   embeddings and to retrieve embeddings from the Milvus database.

2. Similarity Search:

   The query embedding is matched against indexed embeddings in Milvus to find the
   nearest vectors.

3. Result Generation:

   The retrieved results include metadata, similarity scores, and unique identifiers.
   Results are returned in JSON format for easy integration with downstream applications.

4. Result Ranking:

   Retrieved candidates are ranked by similarity score and top-k results are returned.

5. Metadata Resolution:

   The service returns associated metadata (for example file path, source reference, or
   original image linkage) to provide context for each match.

## Workflow

1. The embedding model generates text embeddings for input descriptions
   (e.g., "traffic jam").
2. The search engine searches the vector database for the top-k most similar matches.
3. Generate results with the matched vector ids and metadata.

## Learn More

- Begin with the [Get Started Guide](./get-started).

<!--hide_directive
:::{toctree}
:hidden:

get-started
api-reference
release-notes

:::
hide_directive-->
