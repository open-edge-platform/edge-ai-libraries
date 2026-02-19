# Chat Question-and-Answer Sample Application

Chat Question-and-Answer sample application is a foundational Retrieval-Augmented Generation (RAG) pipeline that allows users to ask questions and receive answers, including those based on their own private data corpus.

Compared to the [Chat Question-and-Answer Core](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/sample-applications/chat-question-and-answer-core) implementation, this implementation of Chat Question-and-Answer is a modular microservices based approach with each constituent element of the RAG pipeline bundled as an independent microservice. Each constituent element, viz document ingestion, embedding creation, retriver, reranking, llm, are independent microservices which are stitched together in the LangChain application. The flexibility is also reflected in the deployment options as it supports docker compose and HELM based options.

Below, you'll find links to detailed documentation to help you get started, configure, and deploy the microservice.

## Documentation

- **Overview**
  - [Overview](./docs/user-guide/index.md): A high-level introduction.
  - [How it works](./docs/user-guide/how-it-works.md): An overview of the architecture.

- **Getting Started**
  - [Get Started](./docs/user-guide/get-started.md): Step-by-step guide to getting started with the sample application.
  - [System Requirements](./docs/user-guide/get-started/system-requirements.md): Hardware and software requirements for running the sample application.

- **Deployment**
  - [How to Build from Source](./docs/user-guide/get-started/build-from-source.md): Instructions for building from source code.
  - [How to Deploy with Helm](./docs/user-guide/get-started/deploy-with-helm.md): Guide for deploying using Helm.

- **API Reference**
  - [API Reference](./docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](./docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.
