# Chat Question-and-Answer Core Sample Application

Chat Question-and-Answer sample application is a foundational Retrieval-Augmented Generation (RAG) pipeline that allows users to ask questions and receive answers, including those based on their own private data corpus.

Compared to the [Chat Question-and-Answer](../chat-question-and-answer/) implementation, this implementation of Chat Question-and-Answer is optimized for memory footprint as it is built as a single monolithic application with the entire RAG pipeline bundled in a single microservice. This is primarily addressing deployment in configurations that are limited in available memory like Intel® Core&trade; portfolio (and hence the suffix "Core" in the name).

Below, you'll find links to detailed documentation to help you get started, configure, and deploy the microservice.

## Documentation

- **Overview**
  - [Overview](docs/user-guide/overview.md): A high-level introduction.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to getting started with the sample application.
  - [System Requirements](docs/user-guide/get-started/system-requirements.md): Hardware and software requirements for running the sample application.

- **Deployment**
  - [How to Build from Source](docs/user-guide/build-from-source.md): Instructions for building from source code.
  - [How to Deploy with Helm](docs/user-guide/deploy-with-helm.md): Guide for deploying using Helm.

- **API Reference**
  - [API Reference](docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.


