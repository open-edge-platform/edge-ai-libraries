Data Ingestion microservice
===========================

Data ingestion service loads, parses, and creates embeddings for popular document types like
pdf, docx, and txt files. The data ingestion is implemented as a microservice which in turn
interacts with other microservices, namely vectorDB, data store, and embedding to achieve
the functionality. The ingested documents are converted to embeddings, embeddings stored
in the vectorDB, and source documents stored in the data store. PGVector is used as the
vectorDB and minIO is used as the data store.

**Key Benefits**:

1. This microservice provides necessary abstraction with 3rd party vectorDB and data
   store making it easy to integrate other providers.
2. The microservice provides support for handling popular document types. It is also a
   place holder for necessary extensions to add additional document types.
3. The selected components to implement the functionality is benchmarked and validated
   for optimal performance.

Example Use Case
################

**Use Case 1**: Refer to the
`ChatQnA <https://github.com/open-edge-platform/edge-ai-libraries/tree/release-1.2.0/sample-applications/chat-question-and-answer>`__
sample application where this microservice is used.

High-Level System View Diagram
++++++++++++++++++++++++++++++

.. figure:: ./images/DataPrep_HL_Arch.png
   :alt: System View Diagram

   Figure 1: High-level system view demonstrating the microservice in a real-world use case.


Key Features
############

1. The user manages the documents using REST APIs supported by the microservice. The APIs allows the user to upload, delete, and read the documents managed by the microservice.
2. The microservice uses PGVector as the vectorDB. However, implementation is modular to support other vectorDBs.

Supporting Resources
####################

- :doc:`Get Started Guide <./get-started>`
- :doc:`System Requirements <./system-requirements>`

.. toctree::
   :hidden:

   get-started
   how-to-customize
   system-requirements
