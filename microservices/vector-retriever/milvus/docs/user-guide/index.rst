Retriever Microservice
======================

Retrieves embeddings based on vector similarity. Usually it is used along with a
`dataprep` microservice.

Overview
########

The Retrieval Microservice is designed to perform efficient, vector-based searches
 using a vector database such as Milvus. It provides a RESTful API for retrieving
 relevant results based on text queries and optional filters. This microservice is
 optimized for handling large-scale datasets and supports flexible query configurations.

Key Features:

-   Text-Based Image/Video Retrieval:

    Accepts text queries and retrieves the top-k most relevant results based on vector
    similarity. Supports optional filters to refine search results.

-   Integration with Milvus:

    Utilizes the Milvus vector database for efficient storage and retrieval of embeddings.
    Ensures high performance and scalability for large datasets.


**Programming Language:** Python

How It Works
############

1. Query Processing:

   The microservice accepts a text query and optional filters via the
   `/v1/retrieval` endpoint. The query is processed with an embedding model to generate
   embeddings and to retrieve embeddings from the Milvus database.

2. Result Generation:

   The retrieved results include metadata, similarity scores, and unique identifiers.
   Results are returned in JSON format for easy integration with downstream applications.

Workflow
########

1. The embedding model generates text embeddings for input descriptions
   (e.g., "traffic jam").
2. The search engine searches the vector database for the top-k most similar matches.
3. Generate results with the matched vector ids and metadata.


Learn More
##########

- Begin with the :doc:`Get Started Guide <./get-started>`

.. toctree::
   :hidden:

   get-started
   api-reference
   release-notes